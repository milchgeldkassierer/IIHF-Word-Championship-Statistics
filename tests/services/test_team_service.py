"""
Comprehensive tests for TeamService
Tests all team operations, roster management, and statistics
"""

import sys
import os
# Füge das Projekt-Root zum Pfad hinzu
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime

# Importiere TeamService über das services Modul
from app.services.core import TeamService
from app.exceptions import (
    ServiceError, ValidationError, NotFoundError, BusinessRuleError
)
from models import Player, Game, Goal, Penalty, ChampionshipYear, TeamStats, TeamOverallStats
from constants import TEAM_ISO_CODES


class TestTeamService:
    """Test suite for TeamService"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        mock = MagicMock()
        mock.session = MagicMock()
        return mock
    
    @pytest.fixture
    def team_service(self, mock_db):
        """Create TeamService instance with mocked dependencies"""
        with patch('app.services.core.team_service.db', mock_db):
            service = TeamService()
            service.db = mock_db
            return service
    
    @pytest.fixture
    def sample_player(self):
        """Create a sample player for testing"""
        player = Mock(spec=Player)
        player.id = 1
        player.team_code = "CAN"
        player.first_name = "Connor"
        player.last_name = "McDavid"
        player.jersey_number = 97
        return player
    
    @pytest.fixture
    def sample_team_players(self):
        """Create sample roster for testing"""
        players = []
        for i in range(3):
            player = Mock(spec=Player)
            player.id = i + 1
            player.team_code = "CAN"
            player.first_name = f"Player{i+1}"
            player.last_name = f"Name{i+1}"
            player.jersey_number = i + 1
            players.append(player)
        return players
    
    # Test get_team_roster
    
    def test_get_team_roster_success(self, team_service, sample_team_players):
        """Test successful team roster retrieval"""
        # Arrange
        with patch('app.services.core.team_service.Player') as mock_player:
            mock_player.query.filter_by.return_value.order_by.return_value.all.return_value = sample_team_players
            
            # Act
            result = team_service.get_team_roster("CAN")
        
        # Assert
        assert len(result) == 3
        assert all(player.team_code == "CAN" for player in result)
        mock_player.query.filter_by.assert_called_once_with(team_code="CAN")
    
    def test_get_team_roster_with_year(self, team_service, sample_team_players):
        """Test team roster retrieval for specific year"""
        # Arrange
        game = Mock(spec=Game)
        game.team1_code = "CAN"
        game.team2_code = "USA"
        
        goal = Mock(spec=Goal)
        goal.scorer_id = 1
        goal.assist1_id = 2
        goal.assist2_id = 3
        
        with patch('app.services.core.team_service.Game') as mock_game:
            mock_game.query.filter_by.return_value.all.return_value = [game]
            
            with patch('app.services.core.team_service.Goal') as mock_goal:
                mock_goal.query.join.return_value.filter.return_value.all.return_value = [goal]
                
                with patch('app.services.core.team_service.Player') as mock_player:
                    mock_player.query.filter.return_value.distinct.return_value.order_by.return_value.all.return_value = sample_team_players
                    
                    # Act
                    result = team_service.get_team_roster("CAN", year=2024)
        
        # Assert
        assert len(result) == 3
        mock_game.query.filter_by.assert_called_once_with(year_id=2024)
    
    def test_get_team_roster_empty(self, team_service):
        """Test getting roster for team with no players"""
        # Arrange
        with patch('app.services.core.team_service.Player') as mock_player:
            mock_player.query.filter_by.return_value.order_by.return_value.all.return_value = []
            
            # Act
            result = team_service.get_team_roster("XXX")
        
        # Assert
        assert result == []
    
    def test_get_team_roster_invalid_code(self, team_service):
        """Test roster retrieval with invalid team code"""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc:
            team_service.get_team_roster("")
        assert "Team code cannot be empty" in str(exc.value)
        assert exc.value.field == "team_code"
    
    def test_get_team_roster_database_error(self, team_service):
        """Test handling of database errors in roster retrieval"""
        # Arrange
        with patch('app.services.core.team_service.Player') as mock_player:
            mock_player.query.filter_by.side_effect = Exception("DB Error")
            
            # Act & Assert
            with pytest.raises(ServiceError) as exc:
                team_service.get_team_roster("CAN")
            assert "Failed to get team roster" in str(exc.value)
    
    # Test add_player
    
    def test_add_player_success(self, team_service):
        """Test successful player addition"""
        # Arrange
        team_service.commit = Mock()
        
        with patch('app.services.core.team_service.Player') as mock_player:
            mock_player.query.filter_by.return_value.first.return_value = None
            new_player = Mock()
            mock_player.return_value = new_player
            
            # Act
            result = team_service.add_player("CAN", "Connor", "McDavid", 97)
        
        # Assert
        assert result == new_player
        team_service.commit.assert_called_once()
        mock_player.assert_called_once_with(
            team_code="CAN",
            first_name="Connor",
            last_name="McDavid",
            jersey_number=97
        )
    
    def test_add_player_duplicate_number(self, team_service, sample_player):
        """Test adding player with duplicate jersey number"""
        # Arrange
        team_service.rollback = Mock()
        
        with patch('app.services.core.team_service.Player') as mock_player:
            mock_player.query.filter_by.return_value.first.return_value = sample_player
            
            # Act & Assert
            with pytest.raises(BusinessRuleError) as exc:
                team_service.add_player("CAN", "New", "Player", 97)
            assert "Jersey number 97 already taken" in str(exc.value)
            assert exc.value.rule == "unique_jersey_number"
            team_service.rollback.assert_called_once()
    
    def test_add_player_invalid_jersey_number(self, team_service):
        """Test validation of invalid jersey numbers"""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc:
            team_service.add_player("CAN", "Test", "Player", -1)
        assert "Jersey number must be between 1 and 99" in str(exc.value)
        assert exc.value.field == "jersey_number"
        
        with pytest.raises(ValidationError) as exc:
            team_service.add_player("CAN", "Test", "Player", 100)
        assert "Jersey number must be between 1 and 99" in str(exc.value)
    
    def test_add_player_empty_name(self, team_service):
        """Test validation of empty player names"""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc:
            team_service.add_player("CAN", "", "LastName", 10)
        assert "First name cannot be empty" in str(exc.value)
        assert exc.value.field == "first_name"
        
        with pytest.raises(ValidationError) as exc:
            team_service.add_player("CAN", "FirstName", "", 10)
        assert "Last name cannot be empty" in str(exc.value)
        assert exc.value.field == "last_name"
    
    def test_add_player_database_error(self, team_service):
        """Test handling of database errors when adding player"""
        # Arrange
        team_service.commit = Mock(side_effect=Exception("DB Error"))
        team_service.rollback = Mock()
        
        with patch('app.services.core.team_service.Player') as mock_player:
            mock_player.query.filter_by.return_value.first.return_value = None
            
            # Act & Assert
            with pytest.raises(ServiceError) as exc:
                team_service.add_player("CAN", "Test", "Player", 10)
            assert "Failed to add player" in str(exc.value)
            team_service.rollback.assert_called_once()
    
    # Test update_player
    
    def test_update_player_success(self, team_service, sample_player):
        """Test successful player update"""
        # Arrange
        team_service.get_by_id = Mock(return_value=sample_player)
        team_service.commit = Mock()
        
        # Act
        result = team_service.update_player(1, jersey_number=99)
        
        # Assert
        assert sample_player.jersey_number == 99
        assert result == sample_player
        team_service.commit.assert_called_once()
    
    def test_update_player_all_fields(self, team_service, sample_player):
        """Test updating all player fields"""
        # Arrange
        team_service.get_by_id = Mock(return_value=sample_player)
        team_service.commit = Mock()
        
        # Act
        result = team_service.update_player(
            1,
            first_name="Nathan",
            last_name="MacKinnon",
            jersey_number=29,
            team_code="COL"
        )
        
        # Assert
        assert sample_player.first_name == "Nathan"
        assert sample_player.last_name == "MacKinnon"
        assert sample_player.jersey_number == 29
        assert sample_player.team_code == "COL"
        team_service.commit.assert_called_once()
    
    def test_update_player_not_found(self, team_service):
        """Test updating non-existent player"""
        # Arrange
        team_service.get_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            team_service.update_player(999, jersey_number=10)
        assert "Player with ID 999 not found" in str(exc.value)
    
    def test_update_player_duplicate_number(self, team_service, sample_player):
        """Test updating to duplicate jersey number"""
        # Arrange
        team_service.get_by_id = Mock(return_value=sample_player)
        team_service.rollback = Mock()
        
        other_player = Mock(spec=Player)
        other_player.id = 2
        other_player.jersey_number = 99
        
        with patch('app.services.core.team_service.Player') as mock_player:
            mock_player.query.filter_by.return_value.filter.return_value.first.return_value = other_player
            
            # Act & Assert
            with pytest.raises(BusinessRuleError) as exc:
                team_service.update_player(1, jersey_number=99)
            assert "Jersey number 99 already taken" in str(exc.value)
            team_service.rollback.assert_called_once()
    
    def test_update_player_invalid_values(self, team_service, sample_player):
        """Test validation of invalid update values"""
        # Arrange
        team_service.get_by_id = Mock(return_value=sample_player)
        
        # Act & Assert
        with pytest.raises(ValidationError) as exc:
            team_service.update_player(1, jersey_number=0)
        assert "Jersey number must be between 1 and 99" in str(exc.value)
        
        with pytest.raises(ValidationError) as exc:
            team_service.update_player(1, first_name="")
        assert "First name cannot be empty" in str(exc.value)
    
    # Test remove_player
    
    def test_remove_player_success(self, team_service, sample_player):
        """Test successful player removal"""
        # Arrange
        team_service.get_by_id = Mock(return_value=sample_player)
        team_service.commit = Mock()
        
        # Act
        result = team_service.remove_player(1)
        
        # Assert
        assert result is True
        team_service.db.session.delete.assert_called_once_with(sample_player)
        team_service.commit.assert_called_once()
    
    def test_remove_player_not_found(self, team_service):
        """Test removing non-existent player"""
        # Arrange
        team_service.get_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            team_service.remove_player(999)
        assert "Player with ID 999 not found" in str(exc.value)
    
    def test_remove_player_with_stats(self, team_service, sample_player):
        """Test removing player who has game statistics"""
        # Arrange
        team_service.get_by_id = Mock(return_value=sample_player)
        team_service.rollback = Mock()
        
        with patch('app.services.core.team_service.Goal') as mock_goal:
            mock_goal.query.filter.return_value.count.return_value = 5
            
            # Act & Assert
            with pytest.raises(BusinessRuleError) as exc:
                team_service.remove_player(1)
            assert "Cannot remove player with game statistics" in str(exc.value)
            assert exc.value.rule == "player_has_stats"
            team_service.rollback.assert_called_once()
    
    def test_remove_player_database_error(self, team_service, sample_player):
        """Test handling of database errors when removing player"""
        # Arrange
        team_service.get_by_id = Mock(return_value=sample_player)
        team_service.commit = Mock(side_effect=Exception("DB Error"))
        team_service.rollback = Mock()
        
        # Act & Assert
        with pytest.raises(ServiceError) as exc:
            team_service.remove_player(1)
        assert "Failed to remove player" in str(exc.value)
        team_service.rollback.assert_called_once()
    
    # Test get_team_stats
    
    def test_get_team_stats_success(self, team_service):
        """Test successful team statistics retrieval"""
        # Arrange
        games = []
        # Regular win
        game1 = Mock(spec=Game)
        game1.team1_code = "CAN"
        game1.team2_code = "USA"
        game1.team1_score = 5
        game1.team2_score = 2
        game1.result_type = "REG"
        games.append(game1)
        
        # OT loss
        game2 = Mock(spec=Game)
        game2.team1_code = "SWE"
        game2.team2_code = "CAN"
        game2.team1_score = 3
        game2.team2_score = 2
        game2.result_type = "OT"
        games.append(game2)
        
        # Goals
        goals = [
            Mock(team_code="CAN", goal_type="EV", is_empty_net=False),
            Mock(team_code="CAN", goal_type="PP", is_empty_net=False),
            Mock(team_code="CAN", goal_type="SH", is_empty_net=True),
        ]
        
        # Penalties
        penalties = [
            Mock(team_code="CAN", penalty_type="MINOR"),
            Mock(team_code="CAN", penalty_type="MAJOR"),
        ]
        
        # SOG
        sog_data = {
            game1: {"CAN": 35, "USA": 28},
            game2: {"SWE": 30, "CAN": 25}
        }
        
        with patch('app.services.core.team_service.Game') as mock_game:
            mock_game.query.filter.return_value.all.return_value = games
            
            with patch('app.services.core.team_service.Goal') as mock_goal:
                mock_goal.query.join.return_value.filter.return_value.all.return_value = goals
                
                with patch('app.services.core.team_service.Penalty') as mock_penalty:
                    mock_penalty.query.join.return_value.filter.return_value.all.return_value = penalties
                    
                    team_service._get_team_sog_totals = Mock(return_value=sog_data)
                    team_service._calculate_team_record = Mock(return_value={
                        "w": 1, "otw": 0, "sow": 0, "l": 0, "otl": 1, "sol": 0, "pts": 4
                    })
                    
                    with patch('app.services.core.team_service.PIM_MAP', {"MINOR": 2, "MAJOR": 5}):
                        # Act
                        result = team_service.get_team_stats("CAN", 2024)
        
        # Assert
        assert result["team_code"] == "CAN"
        assert result["team_name"] == "Canada"  # Expected full name for CAN
        assert result["team_iso"] == TEAM_ISO_CODES.get("CAN", "")
        assert result["gp"] == 2
        assert result["gf"] == 7  # 5 + 2
        assert result["ga"] == 5  # 2 + 3
        assert result["eng"] == 1
        assert result["ppgf"] == 1
        assert result["pim"] == 7  # 2 + 5
        assert result["sog"] == 60  # 35 + 25
        assert result["soga"] == 58  # 28 + 30
    
    def test_get_team_stats_no_games(self, team_service):
        """Test team stats when no games played"""
        # Arrange
        with patch('app.services.core.team_service.Game') as mock_game:
            mock_game.query.filter.return_value.all.return_value = []
            
            # Act
            result = team_service.get_team_stats("NEW", 2024)
        
        # Assert
        assert result["team_code"] == "NEW"
        assert result["gp"] == 0
        assert result["gf"] == 0
        assert result["ga"] == 0
        assert all(result[key] == 0 for key in ["w", "otw", "sow", "l", "otl", "sol", "pts"])
    
    def test_get_team_stats_invalid_team_code(self, team_service):
        """Test stats retrieval with invalid team code"""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc:
            team_service.get_team_stats("", 2024)
        assert "Team code cannot be empty" in str(exc.value)
    
    def test_get_team_stats_database_error(self, team_service):
        """Test handling of database errors in stats retrieval"""
        # Arrange
        with patch('app.services.core.team_service.Game') as mock_game:
            mock_game.query.filter.side_effect = Exception("DB Error")
            
            # Act & Assert
            with pytest.raises(ServiceError) as exc:
                team_service.get_team_stats("CAN", 2024)
            assert "Failed to get team statistics" in str(exc.value)
    
    # Test get_team_vs_team_stats
    
    def test_get_team_vs_team_stats_success(self, team_service):
        """Test successful head-to-head statistics"""
        # Arrange
        games = []
        # Game 1: CAN wins
        game1 = Mock(spec=Game)
        game1.id = 1
        game1.year_id = 2024
        game1.team1_code = "CAN"
        game1.team2_code = "USA"
        game1.team1_score = 4
        game1.team2_score = 2
        game1.result_type = "REG"
        games.append(game1)
        
        # Game 2: USA wins in OT
        game2 = Mock(spec=Game)
        game2.id = 2
        game2.year_id = 2023
        game2.team1_code = "USA"
        game2.team2_code = "CAN"
        game2.team1_score = 3
        game2.team2_score = 2
        game2.result_type = "OT"
        games.append(game2)
        
        with patch('app.services.core.team_service.Game') as mock_game:
            mock_game.query.filter.return_value.all.return_value = games
            
            # Act
            result = team_service.get_team_vs_team_stats("CAN", "USA")
        
        # Assert
        assert result["team1_code"] == "CAN"
        assert result["team2_code"] == "USA"
        assert result["total_games"] == 2
        assert result["team1_wins"] == 1
        assert result["team2_wins"] == 1
        assert result["team1_goals"] == 6
        assert result["team2_goals"] == 5
        assert len(result["games"]) == 2
        assert result["games"][0]["winner"] == "CAN"
        assert result["games"][1]["winner"] == "USA"
    
    def test_get_team_vs_team_stats_with_year_filter(self, team_service):
        """Test head-to-head stats for specific year"""
        # Arrange
        game = Mock(spec=Game)
        game.id = 1
        game.year_id = 2024
        game.team1_code = "CAN"
        game.team2_code = "USA"
        game.team1_score = 3
        game.team2_score = 2
        game.result_type = "REG"
        
        with patch('app.services.core.team_service.Game') as mock_game:
            # Setup the query chain
            query_mock = Mock()
            filter_mock = Mock()
            query_mock.filter.return_value = filter_mock
            filter_mock.filter.return_value = filter_mock
            filter_mock.all.return_value = [game]
            mock_game.query = query_mock
            
            # Act
            result = team_service.get_team_vs_team_stats("CAN", "USA", year=2024)
        
        # Assert
        assert result["total_games"] == 1
        assert result["team1_wins"] == 1
        assert result["team2_wins"] == 0
    
    def test_get_team_vs_team_stats_no_games(self, team_service):
        """Test head-to-head when teams never played"""
        # Arrange
        with patch('app.services.core.team_service.Game') as mock_game:
            mock_game.query.filter.return_value.all.return_value = []
            
            # Act
            result = team_service.get_team_vs_team_stats("CAN", "AUS")
        
        # Assert
        assert result["total_games"] == 0
        assert result["team1_wins"] == 0
        assert result["team2_wins"] == 0
        assert result["draws"] == 0
        assert result["games"] == []
    
    def test_get_team_vs_team_stats_same_team(self, team_service):
        """Test validation when comparing team to itself"""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc:
            team_service.get_team_vs_team_stats("CAN", "CAN")
        assert "Cannot compare team to itself" in str(exc.value)
        assert exc.value.field == "team2_code"
    
    def test_get_team_vs_team_stats_invalid_codes(self, team_service):
        """Test validation of invalid team codes"""
        # Test empty team1
        with pytest.raises(ValidationError) as exc:
            team_service.get_team_vs_team_stats("", "USA")
        assert "Team code cannot be empty" in str(exc.value)
        
        # Test empty team2
        with pytest.raises(ValidationError) as exc:
            team_service.get_team_vs_team_stats("CAN", "")
        assert "Team code cannot be empty" in str(exc.value)
    
    # Test _calculate_team_record
    
    def test_calculate_team_record_various_results(self, team_service):
        """Test team record calculation with various game results"""
        # Arrange
        games = [
            # Regular wins
            Mock(team1_code="CAN", team2_code="USA", team1_score=5, team2_score=2, result_type="REG"),
            Mock(team1_code="SWE", team2_code="CAN", team1_score=1, team2_score=3, result_type="REG"),
            # OT win/loss
            Mock(team1_code="CAN", team2_code="FIN", team1_score=4, team2_score=3, result_type="OT"),
            Mock(team1_code="RUS", team2_code="CAN", team1_score=2, team2_score=1, result_type="OT"),
            # SO win/loss
            Mock(team1_code="CAN", team2_code="CZE", team1_score=3, team2_score=2, result_type="SO"),
            Mock(team1_code="SVK", team2_code="CAN", team1_score=1, team2_score=0, result_type="SO"),
            # Regular loss
            Mock(team1_code="CAN", team2_code="GER", team1_score=2, team2_score=4, result_type="REG"),
        ]
        
        # Act
        result = team_service._calculate_team_record(games, "CAN")
        
        # Assert
        assert result["w"] == 2     # 2 regular wins
        assert result["otw"] == 1   # 1 OT win
        assert result["sow"] == 1   # 1 SO win
        assert result["l"] == 1     # 1 regular loss
        assert result["otl"] == 1   # 1 OT loss
        assert result["sol"] == 1   # 1 SO loss
        assert result["pts"] == 13  # 2*3 + 1*2 + 1*2 + 0 + 1*1 + 1*1
    
    def test_calculate_team_record_empty_games(self, team_service):
        """Test record calculation with no games"""
        # Act
        result = team_service._calculate_team_record([], "CAN")
        
        # Assert
        assert all(result[key] == 0 for key in ["w", "otw", "sow", "l", "otl", "sol", "pts"])
    
    # Test _get_team_sog_totals
    
    def test_get_team_sog_totals(self, team_service):
        """Test shots on goal totals calculation"""
        # Arrange
        games = [
            Mock(id=1, team1_code="CAN", team2_code="USA"),
            Mock(id=2, team1_code="SWE", team2_code="CAN"),
        ]
        
        sog_records = [
            Mock(game_id=1, team_code="CAN", period=1, shots=10),
            Mock(game_id=1, team_code="CAN", period=2, shots=12),
            Mock(game_id=1, team_code="CAN", period=3, shots=8),
            Mock(game_id=1, team_code="USA", period=1, shots=9),
            Mock(game_id=1, team_code="USA", period=2, shots=11),
            Mock(game_id=1, team_code="USA", period=3, shots=10),
            Mock(game_id=2, team_code="CAN", period=1, shots=7),
            Mock(game_id=2, team_code="CAN", period=2, shots=13),
            Mock(game_id=2, team_code="CAN", period=3, shots=5),
            Mock(game_id=2, team_code="SWE", period=1, shots=12),
            Mock(game_id=2, team_code="SWE", period=2, shots=10),
            Mock(game_id=2, team_code="SWE", period=3, shots=8),
        ]
        
        with patch('app.services.core.team_service.ShotsOnGoal') as mock_sog:
            mock_sog.query.filter.return_value.all.return_value = sog_records
            
            # Act
            result = team_service._get_team_sog_totals(games)
        
        # Assert
        assert result[games[0]]["CAN"] == 30  # 10+12+8
        assert result[games[0]]["USA"] == 30  # 9+11+10
        assert result[games[1]]["CAN"] == 25  # 7+13+5
        assert result[games[1]]["SWE"] == 30  # 12+10+8
    
    # Test utility methods
    
    def test_validate_team_code(self, team_service):
        """Test team code validation"""
        # Valid codes
        team_service._validate_team_code("CAN")  # Should not raise
        team_service._validate_team_code("USA")  # Should not raise
        
        # Invalid codes
        with pytest.raises(ValidationError) as exc:
            team_service._validate_team_code("")
        assert "Team code cannot be empty" in str(exc.value)
        
        with pytest.raises(ValidationError) as exc:
            team_service._validate_team_code(None)
        assert "Team code cannot be empty" in str(exc.value)
        
        with pytest.raises(ValidationError) as exc:
            team_service._validate_team_code("CANADA")  # Too long
        assert "Team code must be 3 characters" in str(exc.value)
    
    def test_get_shutouts(self, team_service):
        """Test shutout calculation"""
        # Arrange
        games = [
            Mock(team1_code="CAN", team2_code="USA", team1_score=3, team2_score=0),  # CAN shutout
            Mock(team1_code="SWE", team2_code="CAN", team1_score=0, team2_score=2),  # CAN shutout
            Mock(team1_code="CAN", team2_code="FIN", team1_score=4, team2_score=3),  # No shutout
            Mock(team1_code="RUS", team2_code="CAN", team1_score=5, team2_score=0),  # CAN shutout against
        ]
        
        # Act
        result = team_service._get_shutouts(games, "CAN")
        
        # Assert
        assert result == 2  # CAN achieved 2 shutouts
    
    # Test edge cases
    
    def test_add_player_special_characters_in_name(self, team_service):
        """Test adding player with special characters"""
        # Arrange
        team_service.commit = Mock()
        
        with patch('app.services.core.team_service.Player') as mock_player:
            mock_player.query.filter_by.return_value.first.return_value = None
            new_player = Mock()
            mock_player.return_value = new_player
            
            # Act
            result = team_service.add_player("CAN", "Jean-François", "O'Reilly", 10)
        
        # Assert
        assert result == new_player
        team_service.commit.assert_called_once()
    
    def test_get_team_stats_incomplete_games(self, team_service):
        """Test stats calculation with games missing scores"""
        # Arrange
        games = [
            Mock(team1_code="CAN", team2_code="USA", team1_score=3, team2_score=2, result_type="REG"),
            Mock(team1_code="CAN", team2_code="SWE", team1_score=None, team2_score=None, result_type=None),
        ]
        
        with patch('app.services.core.team_service.Game') as mock_game:
            mock_game.query.filter.return_value.all.return_value = games
            
            with patch('app.services.core.team_service.Goal') as mock_goal:
                mock_goal.query.join.return_value.filter.return_value.all.return_value = []
                
                team_service._get_team_sog_totals = Mock(return_value={})
                team_service._calculate_team_record = Mock(return_value={
                    "w": 1, "otw": 0, "sow": 0, "l": 0, "otl": 0, "sol": 0, "pts": 3
                })
                
                # Act
                result = team_service.get_team_stats("CAN", 2024)
        
        # Assert
        assert result["gp"] == 2  # Both games count for games played
        assert result["gf"] == 3  # Only scored goals count
        assert result["ga"] == 2  # Only conceded goals count
