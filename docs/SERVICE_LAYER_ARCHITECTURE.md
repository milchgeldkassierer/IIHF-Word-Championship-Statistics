# Service Layer Architecture

## IIHF World Championship Statistics System

### Overview
This document defines the comprehensive service layer architecture for the IIHF World Championship Statistics system. The architecture follows Domain-Driven Design principles with clear separation of concerns between business logic (services) and data access (repositories).

---

## Architecture Principles

### 1. Layered Architecture
```
┌─────────────────────────────────────┐
│      Presentation Layer             │
│  (Routes, Controllers, Templates)   │
├─────────────────────────────────────┤
│       Service Layer                 │
│  (Business Logic & Orchestration)   │
├─────────────────────────────────────┤
│      Repository Layer               │
│    (Data Access Abstraction)        │
├─────────────────────────────────────┤
│        Data Layer                   │
│    (Models, Database, ORM)          │
└─────────────────────────────────────┘
```

### 2. Core Design Patterns

#### Service Pattern
- **Purpose**: Encapsulate business logic
- **Responsibilities**: 
  - Business rule validation
  - Transaction orchestration
  - Cross-entity operations
  - External service integration

#### Repository Pattern
- **Purpose**: Abstract data access
- **Responsibilities**:
  - CRUD operations
  - Complex queries
  - Data mapping
  - Query optimization

#### Unit of Work Pattern
- **Purpose**: Manage database transactions
- **Implementation**: Through SQLAlchemy session management

---

## Directory Structure

```
app/
├── services/
│   ├── __init__.py
│   ├── base/
│   │   ├── __init__.py
│   │   ├── base_service.py      # BaseService class
│   │   └── base_repository.py   # BaseRepository class
│   ├── core/
│   │   ├── __init__.py
│   │   ├── game_service.py
│   │   ├── player_service.py
│   │   ├── team_service.py
│   │   └── tournament_service.py
│   ├── stats/
│   │   ├── __init__.py
│   │   ├── standings_service.py
│   │   ├── records_service.py
│   │   └── analytics_service.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── decorators.py
│   │   └── validators.py
│   └── exceptions.py
│
├── repositories/
│   ├── __init__.py
│   ├── base/
│   │   ├── __init__.py
│   │   └── base_repository.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── game_repository.py
│   │   ├── player_repository.py
│   │   ├── team_repository.py
│   │   └── tournament_repository.py
│   └── stats/
│       ├── __init__.py
│       ├── goal_repository.py
│       ├── penalty_repository.py
│       └── standings_repository.py
```

---

## Service Definitions

### BaseService
```python
from typing import TypeVar, Generic, Optional, List
from sqlalchemy.orm import Session
from models import db

T = TypeVar('T')

class BaseService(Generic[T]):
    """Base service providing common patterns"""
    
    def __init__(self, repository: 'BaseRepository[T]'):
        self.repository = repository
        self.db = db
    
    def get_by_id(self, id: int) -> Optional[T]:
        """Get entity by ID"""
        return self.repository.get_by_id(id)
    
    def create(self, **kwargs) -> T:
        """Create new entity with validation"""
        # Implement validation logic
        return self.repository.create(**kwargs)
    
    def update(self, id: int, **kwargs) -> Optional[T]:
        """Update entity with validation"""
        # Implement validation logic
        return self.repository.update(id, **kwargs)
    
    def delete(self, id: int) -> bool:
        """Delete entity"""
        return self.repository.delete(id)
```

### Core Services

#### 1. GameService (Already Implemented)
- **Purpose**: Manage game-related operations
- **Key Methods**:
  - `update_game_score()`: Update scores with validation
  - `add_shots_on_goal()`: Manage SOG data
  - `resolve_team_names()`: Handle playoff team resolution
  - `get_game_with_stats()`: Comprehensive game data

#### 2. PlayerService
- **Purpose**: Manage player statistics and operations
- **Key Methods**:
  - `get_player_tournament_stats()`: Tournament performance
  - `get_career_stats()`: Career statistics
  - `calculate_points_per_game()`: Performance metrics
  - `get_player_achievements()`: Awards and milestones
  - `search_players()`: Advanced player search

#### 3. TeamService
- **Purpose**: Manage team operations and statistics
- **Key Methods**:
  - `get_team_tournament_performance()`: Tournament stats
  - `get_head_to_head_record()`: Team matchup history
  - `calculate_team_rankings()`: Power rankings
  - `get_team_roster()`: Current roster
  - `get_historical_performance()`: All-time statistics

#### 4. TournamentService
- **Purpose**: Manage tournament-level operations
- **Key Methods**:
  - `create_tournament_structure()`: Initialize tournament
  - `advance_playoff_round()`: Manage playoff progression
  - `calculate_final_standings()`: Tournament standings
  - `generate_tournament_report()`: Summary statistics
  - `validate_tournament_integrity()`: Data consistency

### Statistics Services

#### 5. StandingsService
- **Purpose**: Calculate and manage standings
- **Key Methods**:
  - `calculate_group_standings()`: Preliminary round standings
  - `calculate_final_standings()`: Complete tournament standings
  - `get_all_time_standings()`: Historical standings
  - `apply_tiebreakers()`: Complex tiebreaker logic

#### 6. RecordsService
- **Purpose**: Track and calculate records
- **Key Methods**:
  - `get_tournament_records()`: Single tournament records
  - `get_all_time_records()`: Historical records
  - `get_player_records()`: Individual achievements
  - `get_team_records()`: Team achievements
  - `check_record_broken()`: Real-time record tracking

#### 7. AnalyticsService
- **Purpose**: Advanced statistics and analytics
- **Key Methods**:
  - `calculate_advanced_stats()`: Corsi, Fenwick, etc.
  - `generate_predictions()`: Game outcome predictions
  - `analyze_team_performance()`: Performance trends
  - `calculate_player_impact()`: Player value metrics

---

## Repository Layer

### BaseRepository
```python
from typing import TypeVar, Generic, Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from models import db

T = TypeVar('T')

class BaseRepository(Generic[T]):
    """Base repository providing data access patterns"""
    
    def __init__(self, model_class: type[T]):
        self.model_class = model_class
        self.db = db
    
    def get_by_id(self, id: int, session: Optional[Session] = None) -> Optional[T]:
        """Get entity by ID"""
        session = session or self.db.session
        return session.get(self.model_class, id)
    
    def find_one(self, **filters) -> Optional[T]:
        """Find single entity by filters"""
        return self.db.session.query(self.model_class).filter_by(**filters).first()
    
    def find_all(self, **filters) -> List[T]:
        """Find all entities matching filters"""
        return self.db.session.query(self.model_class).filter_by(**filters).all()
    
    def create(self, **kwargs) -> T:
        """Create new entity"""
        entity = self.model_class(**kwargs)
        self.db.session.add(entity)
        self.db.session.flush()
        return entity
    
    def update(self, id: int, **kwargs) -> Optional[T]:
        """Update entity"""
        entity = self.get_by_id(id)
        if entity:
            for key, value in kwargs.items():
                setattr(entity, key, value)
            self.db.session.flush()
        return entity
    
    def delete(self, id: int) -> bool:
        """Delete entity"""
        entity = self.get_by_id(id)
        if entity:
            self.db.session.delete(entity)
            self.db.session.flush()
            return True
        return False
    
    def count(self, **filters) -> int:
        """Count entities"""
        query = self.db.session.query(self.model_class)
        if filters:
            query = query.filter_by(**filters)
        return query.count()
```

### Specialized Repositories

#### GameRepository
```python
class GameRepository(BaseRepository[Game]):
    """Repository for game-specific queries"""
    
    def get_games_by_round(self, year_id: int, round: str) -> List[Game]:
        """Get all games for a specific round"""
        return self.find_all(year_id=year_id, round=round)
    
    def get_playoff_games(self, year_id: int) -> List[Game]:
        """Get all playoff games"""
        return self.db.session.query(Game).filter(
            and_(
                Game.year_id == year_id,
                Game.round != 'Preliminary Round'
            )
        ).all()
    
    def get_games_by_team(self, year_id: int, team_code: str) -> List[Game]:
        """Get all games for a team"""
        return self.db.session.query(Game).filter(
            and_(
                Game.year_id == year_id,
                or_(Game.team1_code == team_code, Game.team2_code == team_code)
            )
        ).all()
```

#### PlayerRepository
```python
class PlayerRepository(BaseRepository[Player]):
    """Repository for player-specific queries"""
    
    def search_by_name(self, name: str) -> List[Player]:
        """Search players by name"""
        return self.db.session.query(Player).filter(
            Player.name.ilike(f'%{name}%')
        ).all()
    
    def get_players_by_team(self, team_code: str, year_id: int) -> List[Player]:
        """Get all players for a team in a year"""
        return self.db.session.query(Player).filter(
            and_(
                Player.team_code == team_code,
                Player.year_id == year_id
            )
        ).all()
    
    def get_top_scorers(self, year_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top scoring players with statistics"""
        # Complex query implementation
        pass
```

---

## Transaction Management

### Decorator Pattern
```python
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

def read_only(func):
    """Decorator for read-only operations"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Use a new session for isolation
        with db.session.no_autoflush:
            return func(*args, **kwargs)
    return wrapper
```

---

## Error Handling

### Service Exceptions
```python
class ServiceError(Exception):
    """Base service exception"""
    pass

class ValidationError(ServiceError):
    """Validation failed"""
    def __init__(self, message: str, field: str = None):
        self.field = field
        super().__init__(message)

class NotFoundError(ServiceError):
    """Entity not found"""
    def __init__(self, entity_type: str, entity_id: Any):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with ID {entity_id} not found")

class BusinessRuleError(ServiceError):
    """Business rule violation"""
    def __init__(self, message: str, rule: str = None):
        self.rule = rule
        super().__init__(message)

class ConcurrencyError(ServiceError):
    """Optimistic locking failed"""
    pass
```

---

## Dependency Injection

### Service Container
```python
class ServiceContainer:
    """Simple dependency injection container"""
    
    def __init__(self):
        self._services = {}
        self._repositories = {}
        self._initialize()
    
    def _initialize(self):
        """Initialize all services and repositories"""
        # Initialize repositories
        self._repositories['game'] = GameRepository(Game)
        self._repositories['player'] = PlayerRepository(Player)
        self._repositories['team'] = TeamRepository(Team)
        
        # Initialize services with dependencies
        self._services['game'] = GameService(self._repositories['game'])
        self._services['player'] = PlayerService(self._repositories['player'])
        self._services['team'] = TeamService(self._repositories['team'])
    
    def get_service(self, name: str) -> BaseService:
        """Get service by name"""
        return self._services.get(name)
    
    def get_repository(self, name: str) -> BaseRepository:
        """Get repository by name"""
        return self._repositories.get(name)

# Global container instance
container = ServiceContainer()
```

---

## Performance Optimization

### Caching Strategy
```python
from functools import lru_cache
import time

def cached(ttl: int = 300):
    """Time-based cache decorator"""
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
        
        wrapper.clear_cache = lambda: cache.clear()
        return wrapper
    return decorator
```

### Query Optimization
- Use eager loading for related entities
- Implement query result pagination
- Use database indexes effectively
- Minimize N+1 query problems

---

## Testing Strategy

### Unit Testing
```python
import pytest
from unittest.mock import Mock, patch

class TestGameService:
    def setup_method(self):
        self.mock_repo = Mock(spec=GameRepository)
        self.service = GameService(self.mock_repo)
    
    def test_update_game_score_validation(self):
        # Test negative score validation
        with pytest.raises(ValidationError):
            self.service.update_game_score(1, -1, 2, 'REG')
```

### Integration Testing
- Test service with real database
- Validate transaction behavior
- Test complex business workflows

---

## Migration Path

### Phase 1: Foundation (Current)
1. ✅ Base service and repository classes
2. ✅ GameService implementation
3. ✅ Exception hierarchy
4. ⏳ Repository layer foundation

### Phase 2: Core Services (Next)
1. PlayerService and PlayerRepository
2. TeamService and TeamRepository  
3. TournamentService and TournamentRepository
4. Service container implementation

### Phase 3: Statistics Services
1. StandingsService implementation
2. RecordsService implementation
3. AnalyticsService implementation
4. Performance optimization

### Phase 4: Complete Migration
1. Route layer refactoring
2. Remove business logic from routes
3. Implement caching layer
4. Performance monitoring

---

## Best Practices

### Service Layer
1. **Single Responsibility**: Each service handles one domain
2. **No Direct Model Access**: Always use repositories
3. **Transaction Boundaries**: Clear transaction management
4. **Business Validation**: All validation in services
5. **Error Handling**: Consistent exception hierarchy

### Repository Layer
1. **Data Access Only**: No business logic
2. **Query Optimization**: Efficient database queries
3. **Consistent Interface**: Standard CRUD methods
4. **Lazy Loading Control**: Explicit eager loading
5. **Query Builder Pattern**: Complex query composition

### General Guidelines
1. **Dependency Injection**: Loose coupling between layers
2. **Testability**: Design for testing
3. **Documentation**: Clear method documentation
4. **Logging**: Comprehensive logging
5. **Performance**: Monitor and optimize

---

## Conclusion

This architecture provides a solid foundation for the IIHF World Championship Statistics system. The clear separation of concerns enables:

- **Maintainability**: Easy to modify and extend
- **Testability**: Each layer can be tested independently
- **Scalability**: Can handle growth in features and data
- **Reusability**: Services can be used across different interfaces
- **Performance**: Optimized data access patterns

The phased migration approach ensures minimal disruption while gradually improving the codebase quality.