# Service Layer Usage Example

This document demonstrates how to use the new service layer in the IIHF World Championship Statistics system.

## GameService Usage Examples

### 1. Updating Game Score

```python
from services import GameService
from services.exceptions import ValidationError, NotFoundError

# Initialize service
game_service = GameService()

try:
    # Update game score
    updated_game = game_service.update_game_score(
        game_id=123,
        team1_score=3,
        team2_score=2,
        result_type='REG'
    )
    print(f"Game updated: {updated_game.team1_code} {updated_game.team1_score} - {updated_game.team2_score} {updated_game.team2_code}")
    print(f"Points: {updated_game.team1_points} - {updated_game.team2_points}")
    
except ValidationError as e:
    print(f"Validation error: {e.message}")
    if e.field:
        print(f"Field: {e.field}")
        
except NotFoundError as e:
    print(f"Not found: {e.message}")
```

### 2. Adding Shots on Goal

```python
# Add shots on goal for a game
sog_data = {
    'CAN': {1: 12, 2: 10, 3: 15, 4: 0},
    'USA': {1: 8, 2: 14, 3: 11, 4: 0}
}

try:
    result = game_service.add_shots_on_goal(game_id=123, sog_data=sog_data)
    
    print(f"SOG updated: {result['made_changes']}")
    print(f"Current SOG: {result['sog_data']}")
    print(f"Data consistency: {result['consistency']['scores_fully_match_data']}")
    
except ServiceError as e:
    print(f"Error: {e.message}")
```

### 3. Getting Game with Full Statistics

```python
# Get comprehensive game information
try:
    game_stats = game_service.get_game_with_stats(game_id=123)
    
    print(f"Game: {game_stats['team1_resolved']} vs {game_stats['team2_resolved']}")
    print(f"Score: {game_stats['game'].team1_score} - {game_stats['game'].team2_score}")
    print(f"SOG: {game_stats['sog_totals']}")
    print(f"PIM: {game_stats['pim_totals']}")
    print(f"PP Goals: {game_stats['pp_goals']}")
    print(f"PP Opportunities: {game_stats['pp_opportunities']}")
    
except NotFoundError as e:
    print(f"Game not found: {e.message}")
```

### 4. Managing Overrules

```python
# Add an overrule
try:
    overrule = game_service.add_overrule(
        game_id=123,
        reason="Manual correction: Official scoresheet error"
    )
    print(f"Overrule added: {overrule.reason}")
    
except ValidationError as e:
    print(f"Invalid overrule: {e.message}")

# Remove an overrule
if game_service.remove_overrule(game_id=123):
    print("Overrule removed")
else:
    print("No overrule found")
```

## Integration in Flask Routes

### Before (Direct Database Access)

```python
@year_bp.route('/<int:year_id>/game/<int:game_id>/update', methods=['POST'])
def update_game_score(year_id, game_id):
    game = db.session.get(Game, game_id)
    if not game:
        flash('Game not found', 'danger')
        return redirect(url_for('year_bp.year_view', year_id=year_id))
    
    try:
        # Direct database manipulation
        game.team1_score = int(request.form.get('team1_score'))
        game.team2_score = int(request.form.get('team2_score'))
        game.result_type = request.form.get('result_type')
        
        # Complex business logic mixed with route
        if game.result_type == 'REG':
            if game.team1_score > game.team2_score:
                game.team1_points, game.team2_points = 3, 0
            else:
                game.team1_points, game.team2_points = 0, 3
        # ... more logic ...
        
        db.session.commit()
        flash('Game updated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('year_bp.year_view', year_id=year_id))
```

### After (Using Service Layer)

```python
from services import GameService
from services.exceptions import ValidationError, NotFoundError, ServiceError

game_service = GameService()

@year_bp.route('/<int:year_id>/game/<int:game_id>/update', methods=['POST'])
def update_game_score(year_id, game_id):
    try:
        # Clean separation of concerns
        team1_score = request.form.get('team1_score')
        team2_score = request.form.get('team2_score')
        
        # Convert to int or None
        t1_score = int(team1_score) if team1_score and team1_score.strip() else None
        t2_score = int(team2_score) if team2_score and team2_score.strip() else None
        
        # Service handles all business logic
        game = game_service.update_game_score(
            game_id=game_id,
            team1_score=t1_score,
            team2_score=t2_score,
            result_type=request.form.get('result_type')
        )
        
        flash('Game updated!', 'success')
        
    except ValidationError as e:
        flash(f'Validation error: {e.message}', 'warning')
    except NotFoundError as e:
        flash(e.message, 'danger')
    except ServiceError as e:
        flash(f'Error: {e.message}', 'danger')
    
    return redirect(url_for('year_bp.year_view', year_id=year_id))
```

## Benefits of Service Layer

1. **Separation of Concerns**: Business logic separated from routes
2. **Reusability**: Services can be used in multiple routes or CLI commands
3. **Testability**: Services can be unit tested without Flask context
4. **Type Safety**: Clear input/output types with proper validation
5. **Error Handling**: Consistent error handling across the application
6. **Transaction Management**: Centralized commit/rollback logic
7. **Logging**: Consistent logging for debugging and monitoring
8. **Caching**: Easy to add caching at service level

## Testing Example

```python
import pytest
from services import GameService
from services.exceptions import ValidationError, BusinessRuleError

def test_update_game_score_overtime_validation():
    """Test that OT games must have 1-goal difference"""
    service = GameService()
    
    # This should raise BusinessRuleError
    with pytest.raises(BusinessRuleError) as exc_info:
        service.update_game_score(
            game_id=1,
            team1_score=5,
            team2_score=2,
            result_type='OT'  # Invalid: 3-goal difference in OT
        )
    
    assert "OT games must have exactly 1 goal difference" in str(exc_info.value)

def test_negative_score_validation():
    """Test that negative scores are rejected"""
    service = GameService()
    
    with pytest.raises(ValidationError) as exc_info:
        service.update_game_score(
            game_id=1,
            team1_score=-1,
            team2_score=2,
            result_type='REG'
        )
    
    assert exc_info.value.field == 'team1_score'
```

## Migration Strategy

1. **Phase 1**: Create service alongside existing code
2. **Phase 2**: Add new endpoints that use services
3. **Phase 3**: Gradually migrate old endpoints
4. **Phase 4**: Remove old code after validation

This approach ensures zero downtime and allows for gradual migration with rollback capability at any stage.