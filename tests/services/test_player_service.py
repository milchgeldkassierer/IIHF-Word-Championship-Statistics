"""
Tests for PlayerService
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.services.core import PlayerService
from app.repositories.core import PlayerRepository
from services.exceptions import ValidationError, NotFoundError, DuplicateError
from models import Player, Goal, Penalty


class TestPlayerService:
    """Test cases for PlayerService"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_repository = Mock(spec=PlayerRepository)
        self.service = PlayerService(repository=self.mock_repository)
        
        # Mock database session
        self.service.db = Mock()
        self.service.db.session = Mock()
    
    def test_create_player_success(self):
        """Test successful player creation"""
        # Arrange
        team_code = "CAN"
        first_name = "Wayne"
        last_name = "Gretzky"
        jersey_number = 99
        
        self.mock_repository.get_player_by_jersey.return_value = None
        self.mock_repository.get_player_by_name.return_value = None
        
        mock_player = Player()
        mock_player.id = 1
        mock_player.team_code = team_code
        mock_player.first_name = first_name
        mock_player.last_name = last_name
        mock_player.jersey_number = jersey_number
        
        self.mock_repository.create.return_value = mock_player
        
        # Act
        result = self.service.create_player(team_code, first_name, last_name, jersey_number)
        
        # Assert
        assert result.id == 1
        assert result.team_code == team_code
        assert result.first_name == first_name
        assert result.last_name == last_name
        assert result.jersey_number == jersey_number
        
        self.mock_repository.create.assert_called_once_with(
            team_code=team_code,
            first_name=first_name,
            last_name=last_name,
            jersey_number=jersey_number
        )
        self.service.db.session.commit.assert_called_once()
    
    def test_create_player_invalid_team_code(self):
        """Test player creation with invalid team code"""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            self.service.create_player("CA", "Wayne", "Gretzky", 99)
        
        assert exc_info.value.field == "team_code"
        assert "3 characters" in str(exc_info.value)
    
    def test_create_player_empty_first_name(self):
        """Test player creation with empty first name"""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            self.service.create_player("CAN", "", "Gretzky", 99)
        
        assert exc_info.value.field == "first_name"
        assert "cannot be empty" in str(exc_info.value)
    
    def test_create_player_invalid_jersey_number(self):
        """Test player creation with invalid jersey number"""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            self.service.create_player("CAN", "Wayne", "Gretzky", 100)
        
        assert exc_info.value.field == "jersey_number"
        assert "between 1 and 99" in str(exc_info.value)
    
    def test_create_player_duplicate_jersey(self):
        """Test player creation with duplicate jersey number"""
        # Arrange
        existing_player = Player()
        existing_player.id = 1
        existing_player.jersey_number = 99
        
        self.mock_repository.get_player_by_jersey.return_value = existing_player
        
        # Act & Assert
        with pytest.raises(DuplicateError) as exc_info:
            self.service.create_player("CAN", "Wayne", "Gretzky", 99)
        
        assert "jersey_number" in str(exc_info.value)
    
    def test_update_player_success(self):
        """Test successful player update"""
        # Arrange
        player_id = 1
        mock_player = Player()
        mock_player.id = player_id
        mock_player.team_code = "CAN"
        mock_player.jersey_number = 99
        
        self.mock_repository.get_by_id.return_value = mock_player
        self.mock_repository.get_player_by_jersey.return_value = None
        self.mock_repository.update.return_value = mock_player
        
        # Act
        result = self.service.update_player(player_id, jersey_number=66)
        
        # Assert
        assert result == mock_player
        self.mock_repository.update.assert_called_once_with(player_id, jersey_number=66)
        self.service.db.session.commit.assert_called_once()
    
    def test_update_player_not_found(self):
        """Test updating non-existent player"""
        # Arrange
        self.mock_repository.get_by_id.return_value = None
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc_info:
            self.service.update_player(999, jersey_number=66)
        
        assert "Player" in str(exc_info.value)
        assert "999" in str(exc_info.value)
    
    @patch('app.services.core.player_service.Goal')
    @patch('app.services.core.player_service.Penalty')
    def test_get_player_statistics(self, mock_penalty_class, mock_goal_class):
        """Test getting player statistics"""
        # Arrange
        player_id = 1
        mock_player = Player()
        mock_player.id = player_id
        mock_player.first_name = "Wayne"
        mock_player.last_name = "Gretzky"
        
        # Mock repository statistics
        mock_stats = {
            'player': mock_player,
            'goals': 5,
            'assists': 10,
            'points': 15,
            'penalty_minutes': 12,
            'penalties_count': 3,
            'goal_types': {'EV': 3, 'PP': 2},
            'goals_list': [Mock(goal_type='EV'), Mock(goal_type='PP'), Mock(goal_type='EV'), 
                          Mock(goal_type='PP'), Mock(goal_type='EV')],
            'assists_list': [Mock(goal_type='EV')] * 10,
            'penalties_list': []
        }
        
        self.mock_repository.get_player_statistics.return_value = mock_stats
        
        # Mock games played query
        mock_goal_query = Mock()
        mock_goal_query.filter.return_value.all.return_value = [
            Mock(game_id=1), Mock(game_id=2), Mock(game_id=3)
        ]
        mock_goal_class.query = mock_goal_query
        
        mock_penalty_query = Mock()
        mock_penalty_query.filter_by.return_value.all.return_value = []
        mock_penalty_class.query = mock_penalty_query
        
        # Act
        result = self.service.get_player_statistics(player_id)
        
        # Assert
        assert result['player'] == mock_player
        assert result['goals'] == 5
        assert result['assists'] == 10
        assert result['points'] == 15
        assert result['games_played'] == 3
        assert result['goals_per_game'] == 5/3
        assert result['points_per_game'] == 15/3
        assert result['powerplay_goals'] == 2
        assert result['powerplay_assists'] == 0
        assert result['empty_net_goals'] == 0
    
    def test_search_players_success(self):
        """Test searching for players"""
        # Arrange
        search_term = "Gretz"
        mock_players = [
            Mock(spec=Player, first_name="Wayne", last_name="Gretzky")
        ]
        self.mock_repository.search_players.return_value = mock_players
        
        # Act
        result = self.service.search_players(search_term)
        
        # Assert
        assert result == mock_players
        self.mock_repository.search_players.assert_called_once_with(search_term, None)
    
    def test_search_players_term_too_short(self):
        """Test search with term too short"""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            self.service.search_players("G")
        
        assert "at least 2 characters" in str(exc_info.value)
    
    def test_get_team_roster_with_stats(self):
        """Test getting team roster with statistics"""
        # Arrange
        team_code = "CAN"
        mock_players_stats = [
            {'player': Mock(), 'goals': 10, 'assists': 15, 'points': 25},
            {'player': Mock(), 'goals': 5, 'assists': 10, 'points': 15}
        ]
        self.mock_repository.get_players_with_stats.return_value = mock_players_stats
        
        # Act
        result = self.service.get_team_roster(team_code, include_stats=True)
        
        # Assert
        assert result['team_code'] == team_code
        assert result['total_players'] == 2
        assert result['total_goals'] == 15
        assert result['total_assists'] == 25
        assert result['total_points'] == 40
    
    @patch('app.services.core.player_service.Goal')
    @patch('app.services.core.player_service.Penalty')  
    def test_merge_duplicate_players(self, mock_penalty_class, mock_goal_class):
        """Test merging duplicate players"""
        # Arrange
        keep_id = 1
        merge_id = 2
        
        keep_player = Player()
        keep_player.id = keep_id
        keep_player.team_code = "CAN"
        
        merge_player = Player()
        merge_player.id = merge_id
        merge_player.team_code = "CAN"
        
        self.mock_repository.get_by_id.side_effect = lambda id: keep_player if id == keep_id else merge_player
        self.mock_repository.delete.return_value = True
        
        mock_goal_class.query.filter_by.return_value.update = Mock()
        mock_penalty_class.query.filter_by.return_value.update = Mock()
        
        # Act
        result = self.service.merge_duplicate_players(keep_id, merge_id)
        
        # Assert
        assert result == keep_player
        
        # Verify updates were called
        mock_goal_class.query.filter_by.assert_any_call(scorer_id=merge_id)
        mock_goal_class.query.filter_by.assert_any_call(assist1_id=merge_id)
        mock_goal_class.query.filter_by.assert_any_call(assist2_id=merge_id)
        mock_penalty_class.query.filter_by.assert_called_with(player_id=merge_id)
        
        self.mock_repository.delete.assert_called_once_with(merge_id)
        self.service.db.session.commit.assert_called_once()
    
    def test_merge_players_different_teams(self):
        """Test merging players from different teams fails"""
        # Arrange
        keep_player = Player()
        keep_player.id = 1
        keep_player.team_code = "CAN"
        
        merge_player = Player()
        merge_player.id = 2
        merge_player.team_code = "USA"
        
        self.mock_repository.get_by_id.side_effect = lambda id: keep_player if id == 1 else merge_player
        
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            self.service.merge_duplicate_players(1, 2)
        
        assert "different teams" in str(exc_info.value)