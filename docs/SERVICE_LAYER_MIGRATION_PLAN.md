# Service Layer Migration Plan
## IIHF World Championship Statistics System

### Executive Summary
This document outlines a phased migration strategy for introducing a comprehensive service layer to the IIHF World Championship Statistics codebase. The migration is designed to minimize risk, maintain backward compatibility, and establish clear patterns for future development.

---

## Phase 1: Pattern Establishment (2 Hours)
**Goal**: Establish service layer patterns with GameService as proof of concept

### 1.1 Create Service Infrastructure (30 minutes)

#### Directory Structure
```
services/
├── __init__.py
├── base.py              # Base service class with common patterns
├── game_service.py      # First concrete implementation
├── exceptions.py        # Service-specific exceptions
└── decorators.py        # Common decorators (transaction, logging)
```

#### Base Service Pattern
```python
# services/base.py
from typing import TypeVar, Generic, Optional, List
from sqlalchemy.orm import Session
from models import db

T = TypeVar('T')

class BaseService(Generic[T]):
    """Base service class providing common database operations"""
    
    def __init__(self, model_class: type[T]):
        self.model_class = model_class
        self.db = db
    
    def get_by_id(self, id: int, session: Optional[Session] = None) -> Optional[T]:
        """Get entity by ID with optional session"""
        session = session or self.db.session
        return session.get(self.model_class, id)
    
    def get_all(self, session: Optional[Session] = None) -> List[T]:
        """Get all entities"""
        session = session or self.db.session
        return session.query(self.model_class).all()
    
    def create(self, **kwargs) -> T:
        """Create new entity"""
        entity = self.model_class(**kwargs)
        self.db.session.add(entity)
        return entity
    
    def update(self, id: int, **kwargs) -> Optional[T]:
        """Update existing entity"""
        entity = self.get_by_id(id)
        if entity:
            for key, value in kwargs.items():
                setattr(entity, key, value)
        return entity
    
    def delete(self, id: int) -> bool:
        """Delete entity by ID"""
        entity = self.get_by_id(id)
        if entity:
            self.db.session.delete(entity)
            return True
        return False
    
    def commit(self) -> None:
        """Commit current transaction"""
        self.db.session.commit()
    
    def rollback(self) -> None:
        """Rollback current transaction"""
        self.db.session.rollback()
```

### 1.2 Implement GameService (45 minutes)

#### Extract Core Business Logic
```python
# services/game_service.py
from typing import Dict, List, Optional, Tuple
from models import Game, ChampionshipYear, TeamStats, ShotsOnGoal, GameOverrule
from services.base import BaseService
from services.exceptions import ServiceError, ValidationError
from utils.playoff_resolver import PlayoffResolver
import logging

logger = logging.getLogger(__name__)

class GameService(BaseService[Game]):
    """Service for game-related business logic"""
    
    def __init__(self):
        super().__init__(Game)
    
    def update_game_score(self, game_id: int, team1_score: Optional[int], 
                         team2_score: Optional[int], result_type: Optional[str]) -> Game:
        """Update game score with proper validation and point calculation"""
        game = self.get_by_id(game_id)
        if not game:
            raise ServiceError(f"Game {game_id} not found")
        
        try:
            # Validate scores
            if team1_score is not None and team1_score < 0:
                raise ValidationError("Team 1 score cannot be negative")
            if team2_score is not None and team2_score < 0:
                raise ValidationError("Team 2 score cannot be negative")
            
            # Update scores
            game.team1_score = team1_score
            game.team2_score = team2_score
            
            # Calculate points based on result type
            if team1_score is None or team2_score is None:
                game.result_type = None
                game.team1_points = 0
                game.team2_points = 0
            else:
                game.result_type = result_type
                game.team1_points, game.team2_points = self._calculate_points(
                    team1_score, team2_score, result_type
                )
            
            self.commit()
            logger.info(f"Updated game {game_id} score: {team1_score}-{team2_score} ({result_type})")
            return game
            
        except Exception as e:
            self.rollback()
            logger.error(f"Error updating game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to update game: {str(e)}")
    
    def _calculate_points(self, team1_score: int, team2_score: int, 
                         result_type: str) -> Tuple[int, int]:
        """Calculate points based on score and result type"""
        if result_type == 'REG':
            if team1_score > team2_score:
                return 3, 0
            elif team2_score > team1_score:
                return 0, 3
            else:
                return 1, 1  # Draw in regulation
        elif result_type in ['OT', 'SO']:
            if team1_score > team2_score:
                return 2, 1
            else:
                return 1, 2
        else:
            raise ValidationError(f"Invalid result type: {result_type}")
    
    def add_shots_on_goal(self, game_id: int, sog_data: Dict[str, Dict[int, int]]) -> Dict:
        """Add or update shots on goal for a game"""
        game = self.get_by_id(game_id)
        if not game:
            raise ServiceError(f"Game {game_id} not found")
        
        try:
            made_changes = False
            
            for team_code, periods in sog_data.items():
                # Skip placeholder teams
                if self._is_placeholder_team(team_code):
                    continue
                
                for period, shots in periods.items():
                    existing_sog = ShotsOnGoal.query.filter_by(
                        game_id=game_id, 
                        team_code=team_code, 
                        period=period
                    ).first()
                    
                    if existing_sog:
                        if existing_sog.shots != shots:
                            existing_sog.shots = shots
                            made_changes = True
                    elif shots != 0:
                        new_sog = ShotsOnGoal(
                            game_id=game_id,
                            team_code=team_code,
                            period=period,
                            shots=shots
                        )
                        self.db.session.add(new_sog)
                        made_changes = True
            
            if made_changes:
                self.commit()
                
            return self._get_current_sog_data(game_id)
            
        except Exception as e:
            self.rollback()
            logger.error(f"Error adding SOG for game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to add shots on goal: {str(e)}")
    
    def _is_placeholder_team(self, team_code: str) -> bool:
        """Check if team code is a placeholder"""
        if not team_code:
            return True
        placeholders = ['A', 'B', 'W', 'L', 'Q', 'S']
        return (team_code[0] in placeholders and 
                len(team_code) > 1 and 
                team_code[1:].isdigit())
    
    def _get_current_sog_data(self, game_id: int) -> Dict[str, Dict[int, int]]:
        """Get current SOG data for a game"""
        sog_entries = ShotsOnGoal.query.filter_by(game_id=game_id).all()
        sog_data = {}
        
        for entry in sog_entries:
            if entry.team_code not in sog_data:
                sog_data[entry.team_code] = {}
            sog_data[entry.team_code][entry.period] = entry.shots
        
        return sog_data
    
    def resolve_team_names(self, year_id: int, game_id: int) -> Tuple[str, str]:
        """Resolve placeholder team names to actual team codes"""
        year_obj = ChampionshipYear.query.get(year_id)
        if not year_obj:
            raise ServiceError(f"Championship year {year_id} not found")
        
        games_raw = Game.query.filter_by(year_id=year_id).all()
        playoff_resolver = PlayoffResolver(year_obj, games_raw)
        
        game = self.get_by_id(game_id)
        if not game:
            raise ServiceError(f"Game {game_id} not found")
        
        # Use centralized resolver
        team1_resolved = playoff_resolver.get_resolved_code(game.team1_code)
        team2_resolved = playoff_resolver.get_resolved_code(game.team2_code)
        
        return team1_resolved, team2_resolved
    
    def get_game_with_stats(self, game_id: int) -> Dict:
        """Get game with all related statistics"""
        game = self.get_by_id(game_id)
        if not game:
            raise ServiceError(f"Game {game_id} not found")
        
        # Resolve team names
        team1_name, team2_name = self.resolve_team_names(game.year_id, game_id)
        
        # Get SOG data
        sog_data = self._get_current_sog_data(game_id)
        
        # Get overrule if exists
        overrule = GameOverrule.query.filter_by(game_id=game_id).first()
        
        return {
            'game': game,
            'team1_resolved': team1_name,
            'team2_resolved': team2_name,
            'sog_data': sog_data,
            'overrule': overrule
        }
```

### 1.3 Create Migration Wrapper (45 minutes)

#### Backward-Compatible Route Adapter
```python
# routes/year/games_migrated.py
from flask import request, jsonify, flash, redirect, url_for
from services.game_service import GameService
from services.exceptions import ServiceError, ValidationError
from . import year_bp

# Initialize service
game_service = GameService()

@year_bp.route('/v2/<int:year_id>/game/<int:game_id>/update', methods=['POST'])
def update_game_score_v2(year_id, game_id):
    """New service-based endpoint for game score updates"""
    try:
        # Extract form data
        team1_score = request.form.get('team1_score')
        team2_score = request.form.get('team2_score')
        result_type = request.form.get('result_type')
        
        # Convert scores to int or None
        t1_score = int(team1_score) if team1_score and team1_score.strip() else None
        t2_score = int(team2_score) if team2_score and team2_score.strip() else None
        
        # Use service to update
        game = game_service.update_game_score(game_id, t1_score, t2_score, result_type)
        
        flash('Game result updated!', 'success')
        return redirect(url_for('year_bp.year_view', year_id=year_id, _anchor=f"game-{game_id}"))
        
    except ValidationError as e:
        flash(f'Validation error: {str(e)}', 'warning')
        return redirect(url_for('year_bp.year_view', year_id=year_id))
    except ServiceError as e:
        flash(f'Error updating result: {str(e)}', 'danger')
        return redirect(url_for('year_bp.year_view', year_id=year_id))

@year_bp.route('/v2/add_sog/<int:game_id>', methods=['POST'])
def add_sog_v2(game_id):
    """New service-based endpoint for SOG updates"""
    try:
        # Extract SOG data from form
        sog_data = {}
        
        # Process team 1
        team1_code = request.form.get('sog_team1_code_resolved')
        if team1_code:
            sog_data[team1_code] = {}
            for period in range(1, 5):
                shots = request.form.get(f'team1_p{period}_shots', '0')
                sog_data[team1_code][period] = int(shots) if shots.strip() else 0
        
        # Process team 2
        team2_code = request.form.get('sog_team2_code_resolved')
        if team2_code:
            sog_data[team2_code] = {}
            for period in range(1, 5):
                shots = request.form.get(f'team2_p{period}_shots', '0')
                sog_data[team2_code][period] = int(shots) if shots.strip() else 0
        
        # Use service to update
        current_sog = game_service.add_shots_on_goal(game_id, sog_data)
        
        return jsonify({
            'success': True,
            'message': 'Shots on Goal successfully saved.',
            'game_id': game_id,
            'sog_data': current_sog
        })
        
    except ServiceError as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500
```

### 1.4 Testing & Validation (30 minutes)

#### Unit Tests for GameService
```python
# tests/services/test_game_service.py
import pytest
from services.game_service import GameService
from services.exceptions import ServiceError, ValidationError
from models import db, Game, ChampionshipYear

class TestGameService:
    def setup_method(self):
        self.service = GameService()
    
    def test_update_game_score_regular_win(self, app):
        with app.app_context():
            # Create test game
            game = Game(team1_code='CAN', team2_code='USA', year_id=1)
            db.session.add(game)
            db.session.commit()
            
            # Update score
            updated_game = self.service.update_game_score(game.id, 3, 1, 'REG')
            
            assert updated_game.team1_score == 3
            assert updated_game.team2_score == 1
            assert updated_game.team1_points == 3
            assert updated_game.team2_points == 0
    
    def test_update_game_score_overtime(self, app):
        with app.app_context():
            # Create test game
            game = Game(team1_code='SWE', team2_code='FIN', year_id=1)
            db.session.add(game)
            db.session.commit()
            
            # Update score with OT
            updated_game = self.service.update_game_score(game.id, 2, 3, 'OT')
            
            assert updated_game.team1_points == 1
            assert updated_game.team2_points == 2
    
    def test_update_game_score_validation_error(self, app):
        with app.app_context():
            with pytest.raises(ValidationError):
                self.service.update_game_score(1, -1, 2, 'REG')
```

---

## Phase 2: Critical Path Migration (Week 1-2)
**Goal**: Migrate core business logic to service layer

### 2.1 Team Statistics Service

```python
# services/team_stats_service.py
from typing import List, Dict, Optional
from models import TeamStats, Game, ChampionshipYear
from services.base import BaseService
from utils import _apply_head_to_head_tiebreaker

class TeamStatsService(BaseService[TeamStats]):
    """Service for team statistics calculations"""
    
    def calculate_preliminary_standings(self, year_id: int) -> Dict[str, List[TeamStats]]:
        """Calculate preliminary round standings by group"""
        games = Game.query.filter_by(
            year_id=year_id, 
            round='Preliminary Round'
        ).filter(Game.group.isnot(None)).all()
        
        # Build team stats
        teams_stats = self._build_team_stats(games)
        
        # Group and sort standings
        standings_by_group = self._group_and_sort_standings(teams_stats, games)
        
        return standings_by_group
    
    def _build_team_stats(self, games: List[Game]) -> Dict[str, TeamStats]:
        """Build team statistics from games"""
        teams_stats = {}
        
        # Initialize teams
        for game in games:
            if game.team1_code and game.group:
                key = (game.team1_code, game.group)
                if game.team1_code not in teams_stats:
                    teams_stats[game.team1_code] = TeamStats(
                        name=game.team1_code, 
                        group=game.group
                    )
            
            if game.team2_code and game.group:
                key = (game.team2_code, game.group)
                if game.team2_code not in teams_stats:
                    teams_stats[game.team2_code] = TeamStats(
                        name=game.team2_code, 
                        group=game.group
                    )
        
        # Calculate stats from completed games
        for game in games:
            if game.team1_score is not None:
                self._update_team_stats(teams_stats, game)
        
        return teams_stats
    
    def _update_team_stats(self, teams_stats: Dict[str, TeamStats], game: Game):
        """Update team statistics based on game result"""
        # Team 1 stats
        if game.team1_code in teams_stats:
            stats = teams_stats[game.team1_code]
            if stats.group == game.group:
                stats.gp += 1
                stats.gf += game.team1_score
                stats.ga += game.team2_score
                stats.pts += game.team1_points
                
                if game.result_type == 'REG':
                    if game.team1_score > game.team2_score:
                        stats.w += 1
                    else:
                        stats.l += 1
                elif game.result_type == 'OT':
                    if game.team1_score > game.team2_score:
                        stats.otw += 1
                    else:
                        stats.otl += 1
                elif game.result_type == 'SO':
                    if game.team1_score > game.team2_score:
                        stats.sow += 1
                    else:
                        stats.sol += 1
        
        # Team 2 stats (similar logic)
        # ... [implementation continues]
```

### 2.2 Playoff Resolution Service

```python
# services/playoff_service.py
from typing import Dict, List, Optional, Tuple
from models import Game, ChampionshipYear
from services.base import BaseService
from utils.playoff_resolver import PlayoffResolver

class PlayoffService(BaseService[Game]):
    """Service for playoff game resolution and seeding"""
    
    def __init__(self):
        super().__init__(Game)
        self._resolver_cache = {}
    
    def get_playoff_resolver(self, year_id: int) -> PlayoffResolver:
        """Get cached playoff resolver for a year"""
        if year_id not in self._resolver_cache:
            year_obj = ChampionshipYear.query.get(year_id)
            games = Game.query.filter_by(year_id=year_id).all()
            self._resolver_cache[year_id] = PlayoffResolver(year_obj, games)
        return self._resolver_cache[year_id]
    
    def resolve_playoff_matchups(self, year_id: int) -> Dict[str, str]:
        """Resolve all playoff matchups for a year"""
        resolver = self.get_playoff_resolver(year_id)
        
        # Get all playoff games
        playoff_games = Game.query.filter_by(year_id=year_id).filter(
            Game.round != 'Preliminary Round'
        ).all()
        
        matchups = {}
        for game in playoff_games:
            team1_resolved = resolver.get_resolved_code(game.team1_code)
            team2_resolved = resolver.get_resolved_code(game.team2_code)
            
            matchups[f"game_{game.game_number}"] = {
                'team1': team1_resolved,
                'team2': team2_resolved,
                'original_team1': game.team1_code,
                'original_team2': game.team2_code
            }
        
        return matchups
    
    def update_playoff_progression(self, game_id: int) -> Dict[str, str]:
        """Update playoff progression based on game result"""
        game = self.get_by_id(game_id)
        if not game or game.round == 'Preliminary Round':
            return {}
        
        if game.team1_score is None or game.team2_score is None:
            return {}
        
        resolver = self.get_playoff_resolver(game.year_id)
        
        # Determine winner and loser
        if game.team1_score > game.team2_score:
            winner = resolver.get_resolved_code(game.team1_code)
            loser = resolver.get_resolved_code(game.team2_code)
        else:
            winner = resolver.get_resolved_code(game.team2_code)
            loser = resolver.get_resolved_code(game.team1_code)
        
        # Update mappings
        updates = {
            f'W({game.game_number})': winner,
            f'L({game.game_number})': loser
        }
        
        return updates
```

### 2.3 Player Statistics Service

```python
# services/player_stats_service.py
from typing import List, Dict, Optional
from sqlalchemy import func
from models import Player, Goal, Penalty, Game
from services.base import BaseService

class PlayerStatsService(BaseService[Player]):
    """Service for player statistics and performance metrics"""
    
    def get_player_tournament_stats(self, player_id: int, year_id: int) -> Dict:
        """Get comprehensive player statistics for a tournament"""
        player = self.get_by_id(player_id)
        if not player:
            return {}
        
        # Get goals
        goals = Goal.query.join(Game).filter(
            Goal.scorer_id == player_id,
            Game.year_id == year_id
        ).all()
        
        # Get assists
        assists = Goal.query.join(Game).filter(
            db.or_(
                Goal.assist1_id == player_id,
                Goal.assist2_id == player_id
            ),
            Game.year_id == year_id
        ).all()
        
        # Get penalties
        penalties = Penalty.query.join(Game).filter(
            Penalty.player_id == player_id,
            Game.year_id == year_id
        ).all()
        
        # Calculate PIM
        total_pim = sum(PIM_MAP.get(p.penalty_type, 0) for p in penalties)
        
        return {
            'player': player,
            'goals': len(goals),
            'assists': len(assists),
            'points': len(goals) + len(assists),
            'penalties': len(penalties),
            'pim': total_pim,
            'goal_details': goals,
            'assist_details': assists,
            'penalty_details': penalties
        }
    
    def get_top_scorers(self, year_id: int, limit: int = 10) -> List[Dict]:
        """Get top scorers for a tournament"""
        # Query for goals and assists
        scorers = db.session.query(
            Player,
            func.count(Goal.id).label('goals'),
            func.count(func.distinct(
                func.case(
                    (Goal.assist1_id == Player.id, Goal.id),
                    (Goal.assist2_id == Player.id, Goal.id)
                )
            )).label('assists')
        ).join(
            Goal, 
            db.or_(
                Goal.scorer_id == Player.id,
                Goal.assist1_id == Player.id,
                Goal.assist2_id == Player.id
            )
        ).join(Game).filter(
            Game.year_id == year_id
        ).group_by(Player.id).all()
        
        # Calculate points and sort
        player_stats = []
        for player, goals, assists in scorers:
            player_stats.append({
                'player': player,
                'goals': goals,
                'assists': assists,
                'points': goals + assists
            })
        
        # Sort by points, then goals
        player_stats.sort(key=lambda x: (-x['points'], -x['goals']))
        
        return player_stats[:limit]
```

### 2.4 Migration Tracking

```python
# migrations/service_layer_tracking.py
"""
Migration tracking for service layer implementation
"""

MIGRATION_STATUS = {
    'phase_1': {
        'game_service': {
            'status': 'completed',
            'endpoints_migrated': [
                '/v2/{year_id}/game/{game_id}/update',
                '/v2/add_sog/{game_id}'
            ],
            'legacy_endpoints': [
                '/{year_id}/game/{game_id}/update',
                '/add_sog_global/{game_id}'
            ]
        }
    },
    'phase_2': {
        'team_stats_service': {
            'status': 'in_progress',
            'target_completion': '2024-02-01'
        },
        'playoff_service': {
            'status': 'planned',
            'target_completion': '2024-02-07'
        },
        'player_stats_service': {
            'status': 'planned',
            'target_completion': '2024-02-14'
        }
    },
    'phase_3': {
        'tournament_service': {'status': 'planned'},
        'records_service': {'status': 'planned'},
        'api_service': {'status': 'planned'}
    }
}

def get_migration_progress():
    """Calculate overall migration progress"""
    total_services = 0
    completed_services = 0
    
    for phase, services in MIGRATION_STATUS.items():
        for service, details in services.items():
            total_services += 1
            if details.get('status') == 'completed':
                completed_services += 1
    
    return {
        'total': total_services,
        'completed': completed_services,
        'progress_percentage': (completed_services / total_services) * 100
    }
```

---

## Phase 3: Full Migration (Month 2-3)
**Goal**: Complete service layer migration and deprecate legacy code

### 3.1 Additional Services

- **TournamentService**: Tournament management and year operations
- **RecordsService**: All-time records and statistics
- **StandingsService**: All-time standings calculations
- **APIService**: External API integrations
- **ImportService**: Data import and fixture processing

### 3.2 Route Migration Strategy

1. **Parallel Routes**: Run new service-based routes alongside legacy routes
2. **Feature Flags**: Use configuration to switch between implementations
3. **Gradual Rollout**: Migrate one route at a time with monitoring
4. **A/B Testing**: Compare performance and accuracy between implementations

### 3.3 Database Transaction Management

```python
# services/decorators.py
from functools import wraps
from models import db
import logging

logger = logging.getLogger(__name__)

def transactional(func):
    """Decorator to handle database transactions"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            db.session.commit()
            return result
        except Exception as e:
            db.session.rollback()
            logger.error(f"Transaction failed in {func.__name__}: {str(e)}")
            raise
    return wrapper

def cached(ttl=300):
    """Decorator for caching service results"""
    def decorator(func):
        cache = {}
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = str(args) + str(kwargs)
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if time.time() - timestamp < ttl:
                    return result
            
            result = func(*args, **kwargs)
            cache[cache_key] = (result, time.time())
            return result
        
        return wrapper
    return decorator
```

---

## Risk Assessment

### Phase 1 Risks (Low)
- **Risk**: Breaking existing functionality
- **Mitigation**: New endpoints run parallel to existing ones
- **Rollback**: Simply stop using new endpoints

### Phase 2 Risks (Medium)
- **Risk**: Data inconsistency between service and direct DB access
- **Mitigation**: Use same transaction scope, comprehensive testing
- **Rollback**: Feature flags to switch back to legacy code

### Phase 3 Risks (High)
- **Risk**: Complete system migration affects all users
- **Mitigation**: Phased rollout, extensive testing, monitoring
- **Rollback**: Maintain legacy code until confidence is high

---

## Rollback Strategies

### Phase 1 Rollback
```python
# config.py
SERVICE_LAYER_ENABLED = {
    'game_service': False,  # Switch to False to use legacy
}

# routes/year/games.py
if current_app.config.get('SERVICE_LAYER_ENABLED', {}).get('game_service'):
    from .games_migrated import update_game_score_v2 as update_game_score
else:
    # Use legacy implementation
    pass
```

### Phase 2 Rollback
- Database migrations are backward compatible
- Service layer can be disabled via configuration
- Legacy routes remain available

### Phase 3 Rollback
- Maintain complete legacy codebase in separate branch
- Deploy legacy version if critical issues arise
- Gradual re-migration after issues resolved

---

## Success Metrics

### Technical Metrics
1. **Response Time**: Service layer should not increase response time by >10%
2. **Error Rate**: Maintain or improve current error rates
3. **Test Coverage**: Achieve >80% coverage for service layer
4. **Code Duplication**: Reduce duplication by >50%

### Business Metrics
1. **User Satisfaction**: No degradation in user experience
2. **Data Accuracy**: 100% consistency with legacy calculations
3. **Development Velocity**: Faster feature development after migration
4. **Maintainability**: Reduced time to fix bugs and add features

### Migration Progress Metrics
1. **Endpoints Migrated**: Track percentage of routes using services
2. **Code Reduction**: Measure LOC reduction in route files
3. **Service Adoption**: Monitor service method usage
4. **Performance Comparison**: A/B test results between implementations

---

## Implementation Timeline

### Week 1-2: Phase 1
- Day 1-2: Set up service infrastructure
- Day 3-4: Implement GameService
- Day 5-6: Create migration wrappers
- Day 7-8: Testing and validation
- Day 9-10: Deploy to staging

### Week 3-4: Phase 2 Start
- Week 3: TeamStatsService and PlayoffService
- Week 4: PlayerStatsService and testing

### Month 2: Phase 2 Completion
- Week 5-6: Additional core services
- Week 7-8: Integration testing and monitoring

### Month 3: Phase 3
- Week 9-10: Remaining services
- Week 11-12: Full system testing and migration

---

## Best Practices for Migration

1. **Incremental Changes**: Small, testable commits
2. **Comprehensive Testing**: Unit, integration, and E2E tests
3. **Documentation**: Update as you migrate
4. **Code Reviews**: Thorough review of all service implementations
5. **Monitoring**: Track performance and errors closely
6. **Communication**: Keep team informed of progress and issues

---

## Conclusion

This phased migration plan provides a low-risk approach to introducing a service layer to the IIHF World Championship Statistics system. By starting with a proof of concept and gradually expanding, we can ensure system stability while improving code organization and maintainability.

The key to success is maintaining backward compatibility, comprehensive testing, and having clear rollback strategies at each phase. With careful execution, this migration will result in a more maintainable, testable, and scalable codebase.