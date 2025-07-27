"""
Game Service with Repository Pattern
Handles all business logic related to games, scores, and game statistics
"""

from typing import Dict, List, Optional, Tuple, Any
from models import Game, ChampionshipYear, TeamStats, ShotsOnGoal, GameOverrule, Goal, Penalty, db
from app.services.base import BaseService
from app.services.utils.cache_manager import CacheableService, cached
from app.repositories.core import GameRepository
from app.exceptions import ServiceError, ValidationError, NotFoundError, BusinessRuleError
from utils.playoff_resolver import PlayoffResolver
from utils import check_game_data_consistency, is_code_final
from constants import PIM_MAP, POWERPLAY_PENALTY_TYPES, TEAM_ISO_CODES
import logging
import os
import json

logger = logging.getLogger(__name__)


class GameService(CacheableService, BaseService[Game]):
    """
    Service for game-related business logic using repository pattern
    Manages games, scores, shots on goal, and game statistics
    """
    
    def __init__(self, repository: Optional[GameRepository] = None):
        """
        Initialize service with repository and cache
        
        Args:
            repository: GameRepository instance (optional, will create if not provided)
        """
        if repository is None:
            repository = GameRepository()
        # Use proper MRO initialization
        super().__init__(repository)
        self._playoff_resolver_cache = {}
    
    def update_game_score(self, game_id: int, team1_score: Optional[int], 
                         team2_score: Optional[int], result_type: Optional[str]) -> Game:
        """
        Update game score with proper validation and point calculation
        
        Args:
            game_id: The game ID to update
            team1_score: Score for team 1 (can be None)
            team2_score: Score for team 2 (can be None)
            result_type: Type of result (REG, OT, SO)
            
        Returns:
            Updated game object
            
        Raises:
            NotFoundError: If game not found
            ValidationError: If scores are invalid
            ServiceError: If update fails
        """
        game = self.get_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        try:
            # Validate scores
            if team1_score is not None and team1_score < 0:
                raise ValidationError("Team 1 score cannot be negative", "team1_score")
            if team2_score is not None and team2_score < 0:
                raise ValidationError("Team 2 score cannot be negative", "team2_score")
            
            # Validate result type for completed games
            if team1_score is not None and team2_score is not None:
                if result_type not in ['REG', 'OT', 'SO']:
                    raise ValidationError(f"Invalid result type: {result_type}", "result_type")
                
                # Business rule: OT/SO games must have 1-goal difference
                if result_type in ['OT', 'SO'] and abs(team1_score - team2_score) != 1:
                    raise BusinessRuleError(
                        f"{result_type} games must have exactly 1 goal difference",
                        "overtime_goal_difference"
                    )
            
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
            
            # Use repository for update
            self.flush()  # Ensure changes are flushed
            self.commit()
            
            # Invalidiere Cache für dieses Spiel und Jahr
            self.invalidate_cache(f"game:with_stats:{game_id}")
            self.invalidate_cache(f"game:by_year:{game.year_id}")
            self.invalidate_cache(f"game:by_year_details:{game.year_id}")
            
            logger.info(f"Updated game {game_id} score: {team1_score}-{team2_score} ({result_type})")
            return game
            
        except (ValidationError, BusinessRuleError):
            self.rollback()
            raise
        except Exception as e:
            self.rollback()
            logger.error(f"Error updating game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to update game: {str(e)}")
    
    def _calculate_points(self, team1_score: int, team2_score: int, 
                         result_type: str) -> Tuple[int, int]:
        """
        Calculate points based on score and result type
        
        IIHF Point System:
        - Regular win: 3 points
        - OT/SO win: 2 points
        - OT/SO loss: 1 point
        - Regular loss: 0 points
        """
        if result_type == 'REG':
            if team1_score > team2_score:
                return 3, 0
            elif team2_score > team1_score:
                return 0, 3
            else:
                # Draw in regulation (rare in IIHF)
                return 1, 1
        elif result_type in ['OT', 'SO']:
            if team1_score > team2_score:
                return 2, 1
            else:
                return 1, 2
        else:
            raise ValidationError(f"Invalid result type: {result_type}")
    
    def add_shots_on_goal(self, game_id: int, sog_data: Dict[str, Dict[int, int]]) -> Dict:
        """
        Add or update shots on goal for a game
        
        Args:
            game_id: The game ID
            sog_data: Dictionary with team codes as keys and period shots as values
                     Example: {'CAN': {1: 10, 2: 12, 3: 8, 4: 0}, 'USA': {...}}
                     
        Returns:
            Current SOG data after update
            
        Raises:
            NotFoundError: If game not found
            ServiceError: If update fails
        """
        game = self.get_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        try:
            made_changes = False
            
            # Resolve team codes first
            team1_resolved, team2_resolved = self.resolve_team_names(game.year_id, game_id)
            valid_teams = [team1_resolved, team2_resolved]
            
            for team_code, periods in sog_data.items():
                # Skip placeholder teams
                if self._is_placeholder_team(team_code):
                    continue
                
                # Validate team is playing in this game
                if team_code not in valid_teams:
                    logger.warning(f"Team {team_code} not playing in game {game_id}")
                    continue
                
                for period, shots in periods.items():
                    # Validate period
                    if period not in [1, 2, 3, 4]:
                        logger.warning(f"Invalid period {period} for SOG")
                        continue
                    
                    # Validate shots
                    if shots < 0:
                        raise ValidationError(f"Shots cannot be negative", f"period_{period}_shots")
                    
                    existing_sog = ShotsOnGoal.query.filter_by(
                        game_id=game_id, 
                        team_code=team_code, 
                        period=period
                    ).first()
                    
                    if existing_sog:
                        if existing_sog.shots != shots:
                            existing_sog.shots = shots
                            made_changes = True
                    elif shots != 0:  # Only create record for non-zero shots
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
                logger.info(f"Updated SOG for game {game_id}")
            
            # Return current SOG data
            current_sog = self._get_current_sog_data(game_id)
            
            # Check data consistency
            consistency_result = check_game_data_consistency(game, current_sog)
            
            return {
                'sog_data': current_sog,
                'made_changes': made_changes,
                'consistency': consistency_result
            }
            
        except ValidationError:
            self.rollback()
            raise
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
                sog_data[entry.team_code] = {1: 0, 2: 0, 3: 0, 4: 0}
            sog_data[entry.team_code][entry.period] = entry.shots
        
        return sog_data
    
    def resolve_team_names(self, year_id: int, game_id: int) -> Tuple[str, str]:
        """
        Resolve placeholder team names to actual team codes
        
        Args:
            year_id: Championship year ID
            game_id: Game ID
            
        Returns:
            Tuple of (team1_resolved, team2_resolved)
            
        Raises:
            NotFoundError: If year or game not found
        """
        year_obj = ChampionshipYear.query.get(year_id)
        if not year_obj:
            raise NotFoundError("Championship year", year_id)
        
        game = self.get_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        # Get or create playoff resolver
        if year_id not in self._playoff_resolver_cache:
            # Use repository to get all games
            games_raw = self.repository.get_games_by_year(year_id)
            self._playoff_resolver_cache[year_id] = PlayoffResolver(year_obj, games_raw)
        
        resolver = self._playoff_resolver_cache[year_id]
        
        # Use centralized resolver
        team1_resolved = resolver.get_resolved_code(game.team1_code)
        team2_resolved = resolver.get_resolved_code(game.team2_code)
        
        return team1_resolved, team2_resolved
    
    @cached(ttl=300, key_prefix="game:with_stats")
    def get_game_with_stats(self, game_id: int) -> Dict[str, Any]:
        """
        Get comprehensive game information with all statistics
        
        Args:
            game_id: The game ID
            
        Returns:
            Dictionary with game data, statistics, and related information
            
        Raises:
            NotFoundError: If game not found
        """
        # Use repository method to get game with statistics
        game_stats = self.repository.get_game_statistics(game_id)
        if not game_stats or not game_stats.get('game'):
            raise NotFoundError("Game", game_id)
        
        game = game_stats['game']
        
        # Resolve team names
        team1_name, team2_name = self.resolve_team_names(game.year_id, game_id)
        
        # Get SOG data
        sog_data = self._get_current_sog_data(game_id)
        
        # Calculate SOG totals
        sog_totals = {}
        for team_code, periods in sog_data.items():
            sog_totals[team_code] = sum(periods.values())
        
        # Get goals
        goals = Goal.query.filter_by(game_id=game_id).all()
        
        # Get penalties
        penalties = Penalty.query.filter_by(game_id=game_id).all()
        
        # Calculate PIM totals
        pim_totals = {team1_name: 0, team2_name: 0}
        for penalty in penalties:
            if penalty.team_code == team1_name:
                pim_totals[team1_name] += PIM_MAP.get(penalty.penalty_type, 0)
            elif penalty.team_code == team2_name:
                pim_totals[team2_name] += PIM_MAP.get(penalty.penalty_type, 0)
        
        # Calculate powerplay opportunities
        pp_opportunities = self._calculate_powerplay_opportunities(
            penalties, team1_name, team2_name
        )
        
        # Calculate powerplay goals
        pp_goals = {team1_name: 0, team2_name: 0}
        for goal in goals:
            if goal.goal_type == "PP":
                if goal.team_code == team1_name:
                    pp_goals[team1_name] += 1
                elif goal.team_code == team2_name:
                    pp_goals[team2_name] += 1
        
        return {
            'game': game,
            'team1_resolved': team1_name,
            'team2_resolved': team2_name,
            'team1_iso': TEAM_ISO_CODES.get(team1_name.upper(), ""),
            'team2_iso': TEAM_ISO_CODES.get(team2_name.upper(), ""),
            'sog_data': sog_data,
            'sog_totals': sog_totals,
            'goals': goals,
            'penalties': penalties,
            'pim_totals': pim_totals,
            'pp_opportunities': pp_opportunities,
            'pp_goals': pp_goals,
            'overrule': game_stats.get('overrule')
        }
    
    def _calculate_powerplay_opportunities(self, penalties: List[Penalty], 
                                         team1: str, team2: str) -> Dict[str, int]:
        """Calculate powerplay opportunities from penalties"""
        potential_pp_slots = []
        
        for penalty in penalties:
            if penalty.penalty_type in POWERPLAY_PENALTY_TYPES:
                # Each penalty gives exactly one powerplay opportunity
                beneficiary = None
                if penalty.team_code == team1:
                    beneficiary = team2
                elif penalty.team_code == team2:
                    beneficiary = team1
                
                if beneficiary:
                    potential_pp_slots.append({
                        'time': penalty.minute_of_game,
                        'beneficiary': beneficiary
                    })
        
        # Group by time to handle coincidental penalties
        grouped_slots = {}
        for slot in potential_pp_slots:
            time = slot['time']
            if time not in grouped_slots:
                grouped_slots[time] = []
            grouped_slots[time].append(slot)
        
        # Calculate final opportunities
        pp_opportunities = {team1: 0, team2: 0}
        for time, slots in grouped_slots.items():
            opp_team1 = sum(1 for s in slots if s['beneficiary'] == team1)
            opp_team2 = sum(1 for s in slots if s['beneficiary'] == team2)
            
            # Cancel out coincidental penalties
            cancelled = min(opp_team1, opp_team2)
            pp_opportunities[team1] += (opp_team1 - cancelled)
            pp_opportunities[team2] += (opp_team2 - cancelled)
        
        return pp_opportunities
    
    def add_overrule(self, game_id: int, reason: str) -> GameOverrule:
        """
        Add or update an overrule for a game
        
        Args:
            game_id: The game ID
            reason: Reason for the overrule
            
        Returns:
            The created or updated overrule
            
        Raises:
            NotFoundError: If game not found
            ValidationError: If reason is empty
        """
        game = self.get_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        if not reason or not reason.strip():
            raise ValidationError("Overrule reason cannot be empty", "reason")
        
        try:
            # Check if overrule already exists
            existing_overrule = GameOverrule.query.filter_by(game_id=game_id).first()
            
            if existing_overrule:
                # Update existing
                existing_overrule.reason = reason.strip()
                existing_overrule.created_at = db.func.current_timestamp()
                self.commit()
                logger.info(f"Updated overrule for game {game_id}")
                return existing_overrule
            else:
                # Create new
                new_overrule = GameOverrule(
                    game_id=game_id,
                    reason=reason.strip()
                )
                self.db.session.add(new_overrule)
                self.commit()
                logger.info(f"Added overrule for game {game_id}")
                return new_overrule
                
        except Exception as e:
            self.rollback()
            logger.error(f"Error adding overrule for game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to add overrule: {str(e)}")
    
    def remove_overrule(self, game_id: int) -> bool:
        """
        Remove an overrule for a game
        
        Args:
            game_id: The game ID
            
        Returns:
            True if removed, False if not found
            
        Raises:
            NotFoundError: If game not found
        """
        game = self.get_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        try:
            existing_overrule = GameOverrule.query.filter_by(game_id=game_id).first()
            
            if not existing_overrule:
                return False
            
            self.db.session.delete(existing_overrule)
            self.commit()
            logger.info(f"Removed overrule for game {game_id}")
            return True
            
        except Exception as e:
            self.rollback()
            logger.error(f"Error removing overrule for game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to remove overrule: {str(e)}")
    
    @cached(ttl=600, key_prefix="game:by_year")
    def get_games_by_year(self, year_id: int, include_stats: bool = False) -> List[Dict[str, Any]]:
        """
        Get all games for a championship year
        
        Args:
            year_id: Championship year ID
            include_stats: Whether to include detailed statistics
            
        Returns:
            List of games with optional statistics
        """
        # Use repository method
        games = self.repository.get_games_by_year(year_id)
        
        if not include_stats:
            return games
        
        # Include detailed stats for each game
        games_with_stats = []
        for game in games:
            try:
                game_stats = self.get_game_with_stats(game.id)
                games_with_stats.append(game_stats)
            except Exception as e:
                logger.error(f"Error getting stats for game {game.id}: {str(e)}")
                games_with_stats.append({'game': game, 'error': str(e)})
        
        return games_with_stats
    
    def search_games(self, criteria: Dict[str, Any]) -> List[Game]:
        """
        Search games with advanced criteria
        
        Args:
            criteria: Search criteria dictionary
            
        Returns:
            List of matching games
        """
        return self.repository.search_games(criteria)
    
    def get_playoff_games(self, year_id: int) -> List[Game]:
        """
        Get all playoff games for a year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            List of playoff games
        """
        return self.repository.get_playoff_games(year_id)
    
    def get_shots_on_goal_by_year(self, year_id: int) -> Dict[int, Dict[str, Dict[int, int]]]:
        """
        Get all shots on goal data for a championship year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            Nested dictionary: {game_id: {team_code: {period: shots}}}
        """
        sog_by_game_flat = {}
        sog_entries = ShotsOnGoal.query.join(Game).filter(Game.year_id == year_id).all()
        
        for sog_entry in sog_entries:
            game_sog_data = sog_by_game_flat.setdefault(sog_entry.game_id, {})
            team_period_sog_data = game_sog_data.setdefault(sog_entry.team_code, {})
            team_period_sog_data[sog_entry.period] = sog_entry.shots
            
        return sog_by_game_flat
    
    def get_goals_by_games(self, game_ids: List[int]) -> Dict[int, List[Goal]]:
        """
        Get all goals for multiple games (avoids N+1 queries)
        
        Args:
            game_ids: List of game IDs
            
        Returns:
            Dictionary with game_id as key and list of goals as value
        """
        goals = Goal.query.filter(Goal.game_id.in_(game_ids)).all()
        
        goals_by_game = {}
        for goal in goals:
            if goal.game_id not in goals_by_game:
                goals_by_game[goal.game_id] = []
            goals_by_game[goal.game_id].append(goal)
        
        return goals_by_game
    
    def get_penalties_by_games(self, game_ids: List[int]) -> Dict[int, List[Penalty]]:
        """
        Get all penalties for multiple games (avoids N+1 queries)
        
        Args:
            game_ids: List of game IDs
            
        Returns:
            Dictionary with game_id as key and list of penalties as value
        """
        penalties = Penalty.query.filter(Penalty.game_id.in_(game_ids)).all()
        
        penalties_by_game = {}
        for penalty in penalties:
            if penalty.game_id not in penalties_by_game:
                penalties_by_game[penalty.game_id] = []
            penalties_by_game[penalty.game_id].append(penalty)
        
        return penalties_by_game
    
    def get_overrules_by_year(self, year_id: int) -> Dict[int, GameOverrule]:
        """
        Get all game overrules for a championship year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            Dictionary with game_id as key and GameOverrule as value
        """
        all_overrules = GameOverrule.query.join(Game).filter(Game.year_id == year_id).all()
        return {overrule.game_id: overrule for overrule in all_overrules}
    
    def get_head_to_head_record(self, team1_code: str, team2_code: str,
                               year_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get head-to-head record between two teams
        
        Args:
            team1_code: First team code
            team2_code: Second team code
            year_id: Optional year filter
            
        Returns:
            Dictionary with head-to-head statistics
        """
        games = self.repository.get_head_to_head_games(team1_code, team2_code, year_id)
        
        # Calculate statistics
        team1_wins = 0
        team2_wins = 0
        team1_goals = 0
        team2_goals = 0
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            # Determine which team is which in this game
            if game.team1_code == team1_code:
                team1_goals += game.team1_score
                team2_goals += game.team2_score
                if game.team1_score > game.team2_score:
                    team1_wins += 1
                else:
                    team2_wins += 1
            else:
                team1_goals += game.team2_score
                team2_goals += game.team1_score
                if game.team2_score > game.team1_score:
                    team1_wins += 1
                else:
                    team2_wins += 1
        
        return {
            'games': games,
            'total_games': len(games),
            f'{team1_code}_wins': team1_wins,
            f'{team2_code}_wins': team2_wins,
            f'{team1_code}_goals': team1_goals,
            f'{team2_code}_goals': team2_goals,
            'goal_differential': team1_goals - team2_goals
        }
    
    @cached(ttl=600, key_prefix="game:by_year_details")
    def get_games_by_year_with_details(self, year_id: int) -> Dict[str, Any]:
        """
        Get all games for a year with all related data
        
        Args:
            year_id: Championship year ID
            
        Returns:
            Dictionary with games and metadata
        """
        games = self.repository.get_games_by_year(year_id)
        
        # Get additional data
        goals = Goal.query.join(Game).filter(Game.year_id == year_id).all()
        penalties = Penalty.query.join(Game).filter(Game.year_id == year_id).all()
        shots = ShotsOnGoal.query.join(Game).filter(Game.year_id == year_id).all()
        
        return {
            'games': games,
            'total_games': len(games),
            'completed_games': len([g for g in games if g.team1_score is not None]),
            'total_goals': sum(1 for goal in goals) if goals else 0,  # Korrigiert für Goal Model
            'total_penalties': len(penalties),
            'total_shots': sum(shot.shots for shot in shots) if shots else 0
        }
    
    def get_games_for_years(self, year_ids: List[int]) -> List[Game]:
        """
        Get all games for multiple years in one query
        
        Args:
            year_ids: List of championship year IDs
            
        Returns:
            List of Game objects
        """
        if not year_ids:
            return []
        
        # Optimierte Query für mehrere Jahre
        games = Game.query.filter(Game.year_id.in_(year_ids)).all()
        
        logger.info(f"Retrieved {len(games)} games for {len(year_ids)} years")
        return games
    
    def get_fixture_info(self, year_obj: ChampionshipYear) -> Dict[str, Any]:
        """
        Get fixture information for a year
        
        Args:
            year_obj: Championship year object
            
        Returns:
            Dictionary with fixture data
        """
        fixture_info = {
            'quarterfinal_games': [],
            'semifinal_games': [],
            'bronze_game_number': None,
            'gold_game_number': None,
            'hosts': []
        }
        
        # Standard defaults
        default_qf = [57, 58, 59, 60]
        default_sf = [61, 62]
        default_bronze = 63
        default_gold = 64
        
        # Versuche Fixture-Datei zu lesen
        from utils.fixture_helpers import resolve_fixture_path
        fixture_path = resolve_fixture_path(year_obj.fixture_path) if year_obj.fixture_path else None
        
        if fixture_path and os.path.exists(fixture_path):
            try:
                with open(fixture_path, 'r', encoding='utf-8') as f:
                    loaded_fixture_data = json.load(f)
                
                fixture_info['hosts'] = loaded_fixture_data.get("hosts", [])
                
                schedule_data = loaded_fixture_data.get("schedule", [])
                for game_data in schedule_data:
                    round_name = game_data.get("round", "").lower()
                    game_num = game_data.get("gameNumber")
                    
                    if "quarterfinal" in round_name:
                        fixture_info['quarterfinal_games'].append(game_num)
                    elif "semifinal" in round_name:
                        fixture_info['semifinal_games'].append(game_num)
                    elif "bronze medal game" in round_name or "bronze" in round_name or "3rd place" in round_name:
                        fixture_info['bronze_game_number'] = game_num
                    elif "gold medal game" in round_name or "final" in round_name or "gold" in round_name:
                        fixture_info['gold_game_number'] = game_num
                
                # Sortiere Semifinal-Spiele
                fixture_info['semifinal_games'].sort()
                
            except Exception as e:
                logger.warning(f"Fehler beim Lesen der Fixture-Datei: {str(e)}")
                # Use defaults
                fixture_info['quarterfinal_games'] = default_qf
                fixture_info['semifinal_games'] = default_sf
                fixture_info['bronze_game_number'] = default_bronze
                fixture_info['gold_game_number'] = default_gold
        else:
            # Use defaults
            fixture_info['quarterfinal_games'] = default_qf
            fixture_info['semifinal_games'] = default_sf
            fixture_info['bronze_game_number'] = default_bronze
            fixture_info['gold_game_number'] = default_gold
            
            # Special case for 2025
            if year_obj.year == 2025:
                fixture_info['hosts'] = ["SWE", "DEN"]
        
        return fixture_info
    
    def get_completed_games(self, year_id: Optional[int] = None) -> List[Game]:
        """
        Get all completed games (with scores)
        
        Args:
            year_id: Championship year ID (optional, if None returns all completed games)
            
        Returns:
            List of completed games
        """
        if year_id is not None:
            # Use repository method for specific year
            return self.repository.get_completed_games(year_id)
        else:
            # Get all completed games across all years using session
            from sqlalchemy import and_
            return self.db.session.query(Game).filter(
                and_(
                    Game.team1_score.isnot(None),
                    Game.team2_score.isnot(None)
                )
            ).all()
    
    def get_game_advanced_stats(self, game_id: int) -> Dict[str, Any]:
        """
        Get advanced statistics for a game organized by team
        
        This method provides a more efficient way to get team-specific stats
        compared to get_game_with_stats, optimized for team yearly stats calculations.
        
        Args:
            game_id: The game ID
            
        Returns:
            Dictionary with team_stats containing per-team statistics
            Format: {
                'team_stats': {
                    'TEAM_CODE': {
                        'shots': int,
                        'powerplay_goals': int,
                        'powerplay_opportunities': int
                    }
                }
            }
            
        Raises:
            NotFoundError: If game not found
        """
        game = self.get_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        try:
            # Resolve team names for this game
            team1_resolved, team2_resolved = self.resolve_team_names(game.year_id, game_id)
            
            # Initialize team stats structure
            team_stats = {
                team1_resolved: {
                    'shots': 0,
                    'powerplay_goals': 0,
                    'powerplay_opportunities': 0
                },
                team2_resolved: {
                    'shots': 0,
                    'powerplay_goals': 0,
                    'powerplay_opportunities': 0
                }
            }
            
            # Get shots on goal data
            sog_data = self._get_current_sog_data(game_id)
            for team_code, periods in sog_data.items():
                if team_code in team_stats:
                    team_stats[team_code]['shots'] = sum(periods.values())
            
            # Get goals for powerplay stats
            goals = Goal.query.filter_by(game_id=game_id).all()
            for goal in goals:
                if goal.goal_type == "PP" and goal.team_code in team_stats:
                    team_stats[goal.team_code]['powerplay_goals'] += 1
            
            # Get penalties for powerplay opportunities
            penalties = Penalty.query.filter_by(game_id=game_id).all()
            pp_opportunities = self._calculate_powerplay_opportunities(
                penalties, team1_resolved, team2_resolved
            )
            
            # Update powerplay opportunities
            for team_code in [team1_resolved, team2_resolved]:
                if team_code in pp_opportunities:
                    team_stats[team_code]['powerplay_opportunities'] = pp_opportunities[team_code]
            
            return {
                'team_stats': team_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting advanced stats for game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to get advanced game stats: {str(e)}")