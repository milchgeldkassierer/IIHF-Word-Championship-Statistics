"""
Comprehensive tests for GameService
Tests all CRUD operations, error handling, and business logic
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime

from services.game_service import GameService
from services.exceptions import (
    ServiceError, ValidationError, NotFoundError, BusinessRuleError
)
from models import Game, ChampionshipYear, TeamStats, ShotsOnGoal, GameOverrule, Goal, Penalty
from utils.playoff_resolver import PlayoffResolver


class TestGameService:
    """Test suite for GameService"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        mock = MagicMock()
        mock.session = MagicMock()
        return mock
    
    @pytest.fixture
    def game_service(self, mock_db):
        """Create GameService instance with mocked dependencies"""
        with patch('services.game_service.db', mock_db):
            service = GameService()
            service.db = mock_db
            return service
    
    @pytest.fixture
    def sample_game(self):
        """Create a sample game for testing"""
        game = Mock(spec=Game)
        game.id = 1
        game.year_id = 2024
        game.team1_code = "CAN"
        game.team2_code = "USA"
        game.team1_score = None
        game.team2_score = None
        game.result_type = None
        game.team1_points = 0
        game.team2_points = 0
        return game
    
    @pytest.fixture
    def sample_year(self):
        """Create a sample championship year"""
        year = Mock(spec=ChampionshipYear)
        year.id = 2024
        year.year = 2024
        return year
    
    # Test update_game_score
    
    def test_update_game_score_success(self, game_service, sample_game):
        """Test successful game score update"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock()
        
        # Act
        result = game_service.update_game_score(1, 3, 2, "REG")
        
        # Assert
        assert sample_game.team1_score == 3
        assert sample_game.team2_score == 2
        assert sample_game.result_type == "REG"
        assert sample_game.team1_points == 3
        assert sample_game.team2_points == 0
        game_service.commit.assert_called_once()
        assert result == sample_game
    
    def test_update_game_score_overtime_win(self, game_service, sample_game):
        """Test overtime game score update"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock()
        
        # Act
        result = game_service.update_game_score(1, 4, 3, "OT")
        
        # Assert
        assert sample_game.team1_score == 4
        assert sample_game.team2_score == 3
        assert sample_game.result_type == "OT"
        assert sample_game.team1_points == 2
        assert sample_game.team2_points == 1
    
    def test_update_game_score_shootout_win(self, game_service, sample_game):
        """Test shootout game score update"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock()
        
        # Act
        result = game_service.update_game_score(1, 2, 3, "SO")
        
        # Assert
        assert sample_game.team1_score == 2
        assert sample_game.team2_score == 3
        assert sample_game.result_type == "SO"
        assert sample_game.team1_points == 1
        assert sample_game.team2_points == 2
    
    def test_update_game_score_game_not_found(self, game_service):
        """Test update game score when game doesn't exist"""
        # Arrange
        game_service.get_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            game_service.update_game_score(999, 3, 2, "REG")
        assert "Game with ID 999 not found" in str(exc.value)
    
    def test_update_game_score_negative_score(self, game_service, sample_game):
        """Test validation of negative scores"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.rollback = Mock()
        
        # Act & Assert
        with pytest.raises(ValidationError) as exc:
            game_service.update_game_score(1, -1, 2, "REG")
        assert "Team 1 score cannot be negative" in str(exc.value)
        assert exc.value.field == "team1_score"
        game_service.rollback.assert_called_once()
    
    def test_update_game_score_invalid_result_type(self, game_service, sample_game):
        """Test validation of invalid result type"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.rollback = Mock()
        
        # Act & Assert
        with pytest.raises(ValidationError) as exc:
            game_service.update_game_score(1, 3, 2, "INVALID")
        assert "Invalid result type: INVALID" in str(exc.value)
        assert exc.value.field == "result_type"
    
    def test_update_game_score_ot_wrong_goal_diff(self, game_service, sample_game):
        """Test business rule: OT/SO must have 1-goal difference"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.rollback = Mock()
        
        # Act & Assert
        with pytest.raises(BusinessRuleError) as exc:
            game_service.update_game_score(1, 5, 2, "OT")
        assert "OT games must have exactly 1 goal difference" in str(exc.value)
        assert exc.value.rule == "overtime_goal_difference"
    
    def test_update_game_score_partial_update(self, game_service, sample_game):
        """Test updating only one team's score"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock()
        
        # Act
        result = game_service.update_game_score(1, 3, None, None)
        
        # Assert
        assert sample_game.team1_score == 3
        assert sample_game.team2_score is None
        assert sample_game.result_type is None
        assert sample_game.team1_points == 0
        assert sample_game.team2_points == 0
    
    def test_update_game_score_database_error(self, game_service, sample_game):
        """Test handling of database errors"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock(side_effect=Exception("DB Error"))
        game_service.rollback = Mock()
        
        # Act & Assert
        with pytest.raises(ServiceError) as exc:
            game_service.update_game_score(1, 3, 2, "REG")
        assert "Failed to update game" in str(exc.value)
        game_service.rollback.assert_called_once()
    
    # Test _calculate_points
    
    def test_calculate_points_regular_win(self, game_service):
        """Test point calculation for regular time win"""
        points = game_service._calculate_points(3, 2, "REG")
        assert points == (3, 0)
        
        points = game_service._calculate_points(2, 4, "REG")
        assert points == (0, 3)
    
    def test_calculate_points_draw(self, game_service):
        """Test point calculation for draw (rare in IIHF)"""
        points = game_service._calculate_points(2, 2, "REG")
        assert points == (1, 1)
    
    def test_calculate_points_overtime(self, game_service):
        """Test point calculation for overtime"""
        points = game_service._calculate_points(4, 3, "OT")
        assert points == (2, 1)
        
        points = game_service._calculate_points(3, 4, "OT")
        assert points == (1, 2)
    
    def test_calculate_points_shootout(self, game_service):
        """Test point calculation for shootout"""
        points = game_service._calculate_points(2, 1, "SO")
        assert points == (2, 1)
        
        points = game_service._calculate_points(1, 2, "SO")
        assert points == (1, 2)
    
    def test_calculate_points_invalid_type(self, game_service):
        """Test invalid result type in point calculation"""
        with pytest.raises(ValidationError) as exc:
            game_service._calculate_points(3, 2, "INVALID")
        assert "Invalid result type: INVALID" in str(exc.value)
    
    # Test add_shots_on_goal
    
    def test_add_shots_on_goal_success(self, game_service, sample_game):
        """Test successful addition of shots on goal"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.resolve_team_names = Mock(return_value=("CAN", "USA"))
        game_service.commit = Mock()
        game_service._get_current_sog_data = Mock(return_value={
            "CAN": {1: 10, 2: 12, 3: 8, 4: 0},
            "USA": {1: 8, 2: 11, 3: 9, 4: 0}
        })
        
        with patch('services.game_service.ShotsOnGoal') as mock_sog:
            mock_sog.query.filter_by.return_value.first.return_value = None
            mock_sog.return_value = Mock()
            
            with patch('services.game_service.check_game_data_consistency') as mock_check:
                mock_check.return_value = {'consistent': True}
                
                # Act
                sog_data = {
                    "CAN": {1: 10, 2: 12, 3: 8, 4: 0},
                    "USA": {1: 8, 2: 11, 3: 9, 4: 0}
                }
                result = game_service.add_shots_on_goal(1, sog_data)
        
        # Assert
        assert result['made_changes'] is True
        assert result['sog_data'] == sog_data
        assert result['consistency']['consistent'] is True
        game_service.commit.assert_called_once()
    
    def test_add_shots_on_goal_game_not_found(self, game_service):
        """Test adding SOG when game doesn't exist"""
        # Arrange
        game_service.get_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            game_service.add_shots_on_goal(999, {})
        assert "Game with ID 999 not found" in str(exc.value)
    
    def test_add_shots_on_goal_invalid_team(self, game_service, sample_game):
        """Test adding SOG for team not playing in game"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.resolve_team_names = Mock(return_value=("CAN", "USA"))
        game_service.commit = Mock()
        
        with patch('services.game_service.logger') as mock_logger:
            # Act
            sog_data = {"SWE": {1: 10, 2: 8, 3: 7}}
            result = game_service.add_shots_on_goal(1, sog_data)
            
            # Assert
            mock_logger.warning.assert_called_with("Team SWE not playing in game 1")
    
    def test_add_shots_on_goal_negative_shots(self, game_service, sample_game):
        """Test validation of negative shot values"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.resolve_team_names = Mock(return_value=("CAN", "USA"))
        game_service.rollback = Mock()
        
        # Act & Assert
        sog_data = {"CAN": {1: -5, 2: 8, 3: 7}}
        with pytest.raises(ValidationError) as exc:
            game_service.add_shots_on_goal(1, sog_data)
        assert "Shots cannot be negative" in str(exc.value)
        game_service.rollback.assert_called_once()
    
    def test_add_shots_on_goal_invalid_period(self, game_service, sample_game):
        """Test handling of invalid period numbers"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.resolve_team_names = Mock(return_value=("CAN", "USA"))
        game_service._get_current_sog_data = Mock(return_value={})
        
        with patch('services.game_service.logger') as mock_logger:
            with patch('services.game_service.check_game_data_consistency') as mock_check:
                mock_check.return_value = {'consistent': True}
                
                # Act
                sog_data = {"CAN": {5: 10}}  # Invalid period
                result = game_service.add_shots_on_goal(1, sog_data)
                
                # Assert
                mock_logger.warning.assert_called_with("Invalid period 5 for SOG")
    
    def test_add_shots_on_goal_update_existing(self, game_service, sample_game):
        """Test updating existing SOG records"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.resolve_team_names = Mock(return_value=("CAN", "USA"))
        game_service.commit = Mock()
        
        existing_sog = Mock()
        existing_sog.shots = 8
        
        with patch('services.game_service.ShotsOnGoal') as mock_sog:
            mock_sog.query.filter_by.return_value.first.return_value = existing_sog
            
            # Act
            sog_data = {"CAN": {1: 10}}  # Update from 8 to 10
            result = game_service.add_shots_on_goal(1, sog_data)
            
            # Assert
            assert existing_sog.shots == 10
            game_service.commit.assert_called_once()
    
    # Test _is_placeholder_team
    
    def test_is_placeholder_team(self, game_service):
        """Test placeholder team detection"""
        assert game_service._is_placeholder_team("A1") is True
        assert game_service._is_placeholder_team("B2") is True
        assert game_service._is_placeholder_team("W45") is True
        assert game_service._is_placeholder_team("L23") is True
        assert game_service._is_placeholder_team("Q1") is True
        assert game_service._is_placeholder_team("S3") is True
        assert game_service._is_placeholder_team("CAN") is False
        assert game_service._is_placeholder_team("USA") is False
        assert game_service._is_placeholder_team("") is True
        assert game_service._is_placeholder_team(None) is True
    
    # Test resolve_team_names
    
    def test_resolve_team_names_success(self, game_service, sample_game, sample_year):
        """Test successful team name resolution"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        
        mock_resolver = Mock(spec=PlayoffResolver)
        mock_resolver.get_resolved_code.side_effect = ["CAN", "USA"]
        
        with patch('services.game_service.ChampionshipYear') as mock_year:
            mock_year.query.get.return_value = sample_year
            with patch('services.game_service.Game') as mock_game_model:
                mock_game_model.query.filter_by.return_value.all.return_value = [sample_game]
                with patch('services.game_service.PlayoffResolver', return_value=mock_resolver):
                    # Act
                    team1, team2 = game_service.resolve_team_names(2024, 1)
        
        # Assert
        assert team1 == "CAN"
        assert team2 == "USA"
        assert mock_resolver.get_resolved_code.call_count == 2
    
    def test_resolve_team_names_year_not_found(self, game_service):
        """Test team resolution when year doesn't exist"""
        # Arrange
        with patch('services.game_service.ChampionshipYear') as mock_year:
            mock_year.query.get.return_value = None
            
            # Act & Assert
            with pytest.raises(NotFoundError) as exc:
                game_service.resolve_team_names(9999, 1)
            assert "Championship year with ID 9999 not found" in str(exc.value)
    
    def test_resolve_team_names_game_not_found(self, game_service, sample_year):
        """Test team resolution when game doesn't exist"""
        # Arrange
        game_service.get_by_id = Mock(return_value=None)
        
        with patch('services.game_service.ChampionshipYear') as mock_year:
            mock_year.query.get.return_value = sample_year
            
            # Act & Assert
            with pytest.raises(NotFoundError) as exc:
                game_service.resolve_team_names(2024, 999)
            assert "Game with ID 999 not found" in str(exc.value)
    
    def test_resolve_team_names_cache(self, game_service, sample_game, sample_year):
        """Test that playoff resolver is cached"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        
        mock_resolver = Mock(spec=PlayoffResolver)
        mock_resolver.get_resolved_code.side_effect = ["CAN", "USA", "SWE", "FIN"]
        
        with patch('services.game_service.ChampionshipYear') as mock_year:
            mock_year.query.get.return_value = sample_year
            with patch('services.game_service.Game') as mock_game_model:
                mock_game_model.query.filter_by.return_value.all.return_value = [sample_game]
                with patch('services.game_service.PlayoffResolver', return_value=mock_resolver) as mock_resolver_class:
                    # Act - call twice
                    game_service.resolve_team_names(2024, 1)
                    game_service.resolve_team_names(2024, 2)
        
        # Assert - resolver created only once
        mock_resolver_class.assert_called_once()
    
    # Test get_game_with_stats
    
    def test_get_game_with_stats_success(self, game_service, sample_game):
        """Test getting comprehensive game statistics"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.resolve_team_names = Mock(return_value=("CAN", "USA"))
        game_service._get_current_sog_data = Mock(return_value={
            "CAN": {1: 10, 2: 12, 3: 8, 4: 0},
            "USA": {1: 8, 2: 11, 3: 9, 4: 0}
        })
        
        # Mock goals
        goal1 = Mock(spec=Goal)
        goal1.team_code = "CAN"
        goal1.goal_type = "PP"
        
        goal2 = Mock(spec=Goal)
        goal2.team_code = "USA"
        goal2.goal_type = "EV"
        
        # Mock penalties
        penalty1 = Mock(spec=Penalty)
        penalty1.team_code = "CAN"
        penalty1.penalty_type = "MINOR"
        penalty1.minute_of_game = 10
        
        penalty2 = Mock(spec=Penalty)
        penalty2.team_code = "USA"
        penalty2.penalty_type = "MAJOR"
        penalty2.minute_of_game = 15
        
        # Mock overrule
        overrule = Mock(spec=GameOverrule)
        overrule.reason = "Test overrule"
        
        with patch('services.game_service.Goal') as mock_goal:
            mock_goal.query.filter_by.return_value.all.return_value = [goal1, goal2]
            
            with patch('services.game_service.Penalty') as mock_penalty:
                mock_penalty.query.filter_by.return_value.all.return_value = [penalty1, penalty2]
                
                with patch('services.game_service.GameOverrule') as mock_overrule:
                    mock_overrule.query.filter_by.return_value.first.return_value = overrule
                    
                    with patch('services.game_service.PIM_MAP', {"MINOR": 2, "MAJOR": 5}):
                        with patch('services.game_service.POWERPLAY_PENALTY_TYPES', ["MINOR", "MAJOR"]):
                            with patch('services.game_service.TEAM_ISO_CODES', {"CAN": "ca", "USA": "us"}):
                                # Act
                                result = game_service.get_game_with_stats(1)
        
        # Assert
        assert result['game'] == sample_game
        assert result['team1_resolved'] == "CAN"
        assert result['team2_resolved'] == "USA"
        assert result['team1_iso'] == "ca"
        assert result['team2_iso'] == "us"
        assert result['sog_totals'] == {"CAN": 30, "USA": 28}
        assert len(result['goals']) == 2
        assert len(result['penalties']) == 2
        assert result['pim_totals'] == {"CAN": 2, "USA": 5}
        assert result['pp_goals'] == {"CAN": 1, "USA": 0}
        assert result['overrule'] == overrule
    
    def test_get_game_with_stats_not_found(self, game_service):
        """Test getting stats for non-existent game"""
        # Arrange
        game_service.get_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            game_service.get_game_with_stats(999)
        assert "Game with ID 999 not found" in str(exc.value)
    
    # Test _calculate_powerplay_opportunities
    
    def test_calculate_powerplay_opportunities(self, game_service):
        """Test powerplay opportunity calculation"""
        # Arrange
        penalties = [
            Mock(team_code="CAN", penalty_type="MINOR", minute_of_game=10),
            Mock(team_code="USA", penalty_type="MINOR", minute_of_game=10),  # Coincidental
            Mock(team_code="CAN", penalty_type="MAJOR", minute_of_game=15),
            Mock(team_code="USA", penalty_type="MINOR", minute_of_game=20),
        ]
        
        with patch('services.game_service.POWERPLAY_PENALTY_TYPES', ["MINOR", "MAJOR"]):
            # Act
            result = game_service._calculate_powerplay_opportunities(penalties, "CAN", "USA")
        
        # Assert
        # At minute 10: CAN and USA penalties cancel out (0-0)
        # At minute 15: CAN penalty gives USA 1 opportunity
        # At minute 20: USA penalty gives CAN 1 opportunity
        assert result == {"CAN": 1, "USA": 1}
    
    def test_calculate_powerplay_opportunities_no_penalties(self, game_service):
        """Test powerplay calculation with no penalties"""
        result = game_service._calculate_powerplay_opportunities([], "CAN", "USA")
        assert result == {"CAN": 0, "USA": 0}
    
    # Test add_overrule
    
    def test_add_overrule_success(self, game_service, sample_game):
        """Test successful overrule addition"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock()
        
        with patch('services.game_service.GameOverrule') as mock_overrule:
            mock_overrule.query.filter_by.return_value.first.return_value = None
            mock_overrule.return_value = Mock(reason="New overrule")
            
            # Act
            result = game_service.add_overrule(1, "New overrule")
        
        # Assert
        game_service.commit.assert_called_once()
        assert result.reason == "New overrule"
    
    def test_add_overrule_update_existing(self, game_service, sample_game):
        """Test updating existing overrule"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock()
        
        existing_overrule = Mock(spec=GameOverrule)
        existing_overrule.reason = "Old reason"
        
        with patch('services.game_service.GameOverrule') as mock_overrule:
            mock_overrule.query.filter_by.return_value.first.return_value = existing_overrule
            
            # Act
            result = game_service.add_overrule(1, "Updated reason")
        
        # Assert
        assert existing_overrule.reason == "Updated reason"
        game_service.commit.assert_called_once()
        assert result == existing_overrule
    
    def test_add_overrule_game_not_found(self, game_service):
        """Test adding overrule for non-existent game"""
        # Arrange
        game_service.get_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            game_service.add_overrule(999, "Test")
        assert "Game with ID 999 not found" in str(exc.value)
    
    def test_add_overrule_empty_reason(self, game_service, sample_game):
        """Test validation of empty overrule reason"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        
        # Act & Assert
        with pytest.raises(ValidationError) as exc:
            game_service.add_overrule(1, "")
        assert "Overrule reason cannot be empty" in str(exc.value)
        assert exc.value.field == "reason"
    
    def test_add_overrule_database_error(self, game_service, sample_game):
        """Test handling of database errors in overrule"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock(side_effect=Exception("DB Error"))
        game_service.rollback = Mock()
        
        with patch('services.game_service.GameOverrule'):
            # Act & Assert
            with pytest.raises(ServiceError) as exc:
                game_service.add_overrule(1, "Test")
            assert "Failed to add overrule" in str(exc.value)
            game_service.rollback.assert_called_once()
    
    # Test remove_overrule
    
    def test_remove_overrule_success(self, game_service, sample_game):
        """Test successful overrule removal"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock()
        
        existing_overrule = Mock(spec=GameOverrule)
        
        with patch('services.game_service.GameOverrule') as mock_overrule:
            mock_overrule.query.filter_by.return_value.first.return_value = existing_overrule
            
            # Act
            result = game_service.remove_overrule(1)
        
        # Assert
        game_service.db.session.delete.assert_called_once_with(existing_overrule)
        game_service.commit.assert_called_once()
        assert result is True
    
    def test_remove_overrule_not_found(self, game_service, sample_game):
        """Test removing non-existent overrule"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        
        with patch('services.game_service.GameOverrule') as mock_overrule:
            mock_overrule.query.filter_by.return_value.first.return_value = None
            
            # Act
            result = game_service.remove_overrule(1)
        
        # Assert
        assert result is False
        game_service.db.session.delete.assert_not_called()
    
    def test_remove_overrule_game_not_found(self, game_service):
        """Test removing overrule for non-existent game"""
        # Arrange
        game_service.get_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            game_service.remove_overrule(999)
        assert "Game with ID 999 not found" in str(exc.value)
    
    # Test get_games_by_year
    
    def test_get_games_by_year_without_stats(self, game_service):
        """Test getting games without detailed stats"""
        # Arrange
        games = [Mock(spec=Game), Mock(spec=Game)]
        game_service.filter_by = Mock(return_value=games)
        
        # Act
        result = game_service.get_games_by_year(2024, include_stats=False)
        
        # Assert
        assert result == games
        game_service.filter_by.assert_called_once_with(year_id=2024)
    
    def test_get_games_by_year_with_stats(self, game_service):
        """Test getting games with detailed stats"""
        # Arrange
        game1 = Mock(spec=Game)
        game1.id = 1
        game2 = Mock(spec=Game)
        game2.id = 2
        
        game_service.filter_by = Mock(return_value=[game1, game2])
        game_service.get_game_with_stats = Mock(side_effect=[
            {"game": game1, "stats": "data1"},
            {"game": game2, "stats": "data2"}
        ])
        
        # Act
        result = game_service.get_games_by_year(2024, include_stats=True)
        
        # Assert
        assert len(result) == 2
        assert result[0]["game"] == game1
        assert result[1]["game"] == game2
        assert game_service.get_game_with_stats.call_count == 2
    
    def test_get_games_by_year_with_stats_error(self, game_service):
        """Test handling errors when getting game stats"""
        # Arrange
        game1 = Mock(spec=Game)
        game1.id = 1
        
        game_service.filter_by = Mock(return_value=[game1])
        game_service.get_game_with_stats = Mock(side_effect=Exception("Stats error"))
        
        with patch('services.game_service.logger') as mock_logger:
            # Act
            result = game_service.get_games_by_year(2024, include_stats=True)
        
        # Assert
        assert len(result) == 1
        assert result[0]["game"] == game1
        assert result[0]["error"] == "Stats error"
        mock_logger.error.assert_called_once()
    
    # Test edge cases and error scenarios
    
    def test_update_game_score_none_values(self, game_service, sample_game):
        """Test updating game with None values to clear scores"""
        # Arrange
        sample_game.team1_score = 3
        sample_game.team2_score = 2
        sample_game.result_type = "REG"
        sample_game.team1_points = 3
        sample_game.team2_points = 0
        
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.commit = Mock()
        
        # Act
        result = game_service.update_game_score(1, None, None, None)
        
        # Assert
        assert sample_game.team1_score is None
        assert sample_game.team2_score is None
        assert sample_game.result_type is None
        assert sample_game.team1_points == 0
        assert sample_game.team2_points == 0
    
    def test_add_shots_on_goal_zero_shots(self, game_service, sample_game):
        """Test that zero shots don't create SOG records"""
        # Arrange
        game_service.get_by_id = Mock(return_value=sample_game)
        game_service.resolve_team_names = Mock(return_value=("CAN", "USA"))
        
        with patch('services.game_service.ShotsOnGoal') as mock_sog:
            mock_sog.query.filter_by.return_value.first.return_value = None
            
            # Act
            sog_data = {"CAN": {1: 0, 2: 0, 3: 0}}
            result = game_service.add_shots_on_goal(1, sog_data)
            
            # Assert
            game_service.db.session.add.assert_not_called()