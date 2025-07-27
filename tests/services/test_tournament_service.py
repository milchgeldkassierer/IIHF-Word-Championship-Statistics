"""
Comprehensive tests for TournamentService
Tests all CRUD operations, tournament logic, and business rules
"""

import sys
import os
# Füge das Projekt-Root zum Pfad hinzu
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime

# Importiere TournamentService über das services Modul
from services import TournamentService
from services.exceptions import (
    ServiceError, ValidationError, NotFoundError, BusinessRuleError
)
from models import ChampionshipYear, Game, TeamStats
# We'll mock the repository, so we don't need to import it directly
from utils.playoff_resolver import PlayoffResolver


class TestTournamentService:
    """Test suite for TournamentService"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        mock = MagicMock()
        mock.session = MagicMock()
        return mock
    
    @pytest.fixture
    def tournament_service(self, mock_db):
        """Create TournamentService instance with mocked dependencies"""
        with patch('services.tournament_service.db', mock_db):
            with patch('services.tournament_service.TournamentRepository') as mock_repo_class:
                mock_repo = Mock()
                mock_repo_class.return_value = mock_repo
                service = TournamentService()
                service.db = mock_db
                service.repository = mock_repo
                return service
    
    @pytest.fixture
    def sample_championship(self):
        """Create a sample championship year for testing"""
        championship = Mock()
        championship.id = 2024
        championship.year = 2024
        championship.name = "IIHF World Championship 2024"
        championship.fixture_path = None
        return championship
    
    @pytest.fixture
    def sample_game(self):
        """Create a sample game for testing"""
        game = Mock()
        game.id = 1
        game.year_id = 2024
        game.game_number = 1
        game.team1_code = "CAN"
        game.team2_code = "USA"
        game.team1_score = 3
        game.team2_score = 2
        game.result_type = "REG"
        game.team1_points = 3
        game.team2_points = 0
        game.round = "Group Stage"
        game.group = "A"
        game.date = "2024-05-10"
        return game
    
    # Test create_championship_year
    
    def test_create_championship_year_success(self, tournament_service):
        """Test successful championship year creation"""
        # Arrange
        tournament_service.repository.find_by_year = Mock(return_value=None)
        tournament_service.commit = Mock()
        
        # Act
        with patch('services.tournament_service.datetime') as mock_datetime:
            mock_datetime.now.return_value.year = 2024
            result = tournament_service.create_championship_year(
                "IIHF World Championship 2024", 2024, "fixtures/2024.json"
            )
        
        # Assert
        tournament_service.db.session.add.assert_called_once()
        tournament_service.commit.assert_called_once()
        assert result.name == "IIHF World Championship 2024"
        assert result.year == 2024
        assert result.fixture_path == "fixtures/2024.json"
    
    def test_create_championship_year_invalid_year(self, tournament_service):
        """Test validation of invalid year"""
        # Arrange
        tournament_service.rollback = Mock()
        
        # Act & Assert
        with patch('services.tournament_service.datetime') as mock_datetime:
            mock_datetime.now.return_value.year = 2024
            
            # Year too old
            with pytest.raises(ValidationError) as exc:
                tournament_service.create_championship_year("Test", 1919)
            assert "Invalid year: 1919" in str(exc.value)
            assert exc.value.field == "year"
            
            # Year too far in future
            with pytest.raises(ValidationError) as exc:
                tournament_service.create_championship_year("Test", 2030)
            assert "Invalid year: 2030" in str(exc.value)
    
    def test_create_championship_year_empty_name(self, tournament_service):
        """Test validation of empty championship name"""
        # Arrange
        tournament_service.rollback = Mock()
        
        # Act & Assert
        with pytest.raises(ValidationError) as exc:
            tournament_service.create_championship_year("", 2024)
        assert "Championship name cannot be empty" in str(exc.value)
        assert exc.value.field == "name"
        
        with pytest.raises(ValidationError) as exc:
            tournament_service.create_championship_year("   ", 2024)
        assert "Championship name cannot be empty" in str(exc.value)
    
    def test_create_championship_year_duplicate(self, tournament_service):
        """Test duplicate championship year prevention"""
        # Arrange
        existing = Mock()
        tournament_service.repository.find_by_year = Mock(return_value=existing)
        tournament_service.rollback = Mock()
        
        # Act & Assert
        with patch('services.tournament_service.datetime') as mock_datetime:
            mock_datetime.now.return_value.year = 2024
            with pytest.raises(ValidationError) as exc:
                tournament_service.create_championship_year("Test", 2024)
            assert "Championship for year 2024 already exists" in str(exc.value)
            assert exc.value.field == "year"
    
    def test_create_championship_year_database_error(self, tournament_service):
        """Test handling of database errors"""
        # Arrange
        tournament_service.repository.find_by_year = Mock(return_value=None)
        tournament_service.commit = Mock(side_effect=Exception("DB Error"))
        tournament_service.rollback = Mock()
        
        # Act & Assert
        with patch('services.tournament_service.datetime') as mock_datetime:
            mock_datetime.now.return_value.year = 2024
            with pytest.raises(ServiceError) as exc:
                tournament_service.create_championship_year("Test", 2024)
            assert "Failed to create championship" in str(exc.value)
            tournament_service.rollback.assert_called_once()
    
    # Test get_tournament_structure
    
    def test_get_tournament_structure_success(self, tournament_service, sample_championship):
        """Test getting complete tournament structure"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        games = [
            Mock(team1_code="CAN", team2_code="USA", group="A", round="Group Stage", 
                 team1_score=3, team2_score=2, date="2024-05-10"),
            Mock(team1_code="SWE", team2_code="FIN", group="A", round="Group Stage",
                 team1_score=4, team2_score=3, date="2024-05-11"),
            Mock(team1_code="CZE", team2_code="SVK", group="B", round="Group Stage",
                 team1_score=None, team2_score=None, date="2024-05-12"),
            Mock(team1_code="W1", team2_code="W2", group=None, round="Quarterfinals",
                 team1_score=None, team2_score=None, date="2024-05-20")
        ]
        tournament_service.repository.get_all_games = Mock(return_value=games)
        
        # Act
        result = tournament_service.get_tournament_structure(2024)
        
        # Assert
        assert result['championship'] == sample_championship
        assert 'A' in result['groups']
        assert 'B' in result['groups']
        assert set(result['groups']['A']) == {'CAN', 'USA', 'SWE', 'FIN'}
        assert set(result['groups']['B']) == {'CZE', 'SVK'}
        assert result['total_games'] == 4
        assert result['completed_games'] == 2
        assert result['upcoming_games'] == 2
        assert len(result['rounds']) >= 2
    
    def test_get_tournament_structure_not_found(self, tournament_service):
        """Test getting structure for non-existent championship"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            tournament_service.get_tournament_structure(9999)
        assert "Championship year with ID 9999 not found" in str(exc.value)
    
    # Test _is_placeholder_team
    
    def test_is_placeholder_team(self, tournament_service):
        """Test placeholder team detection"""
        assert tournament_service._is_placeholder_team("A1") is True
        assert tournament_service._is_placeholder_team("B2") is True
        assert tournament_service._is_placeholder_team("W45") is True
        assert tournament_service._is_placeholder_team("L23") is True
        assert tournament_service._is_placeholder_team("Q1") is True
        assert tournament_service._is_placeholder_team("S3") is True
        assert tournament_service._is_placeholder_team("CAN") is False
        assert tournament_service._is_placeholder_team("USA") is False
        assert tournament_service._is_placeholder_team("") is True
        assert tournament_service._is_placeholder_team(None) is True
    
    # Test get_group_standings
    
    def test_get_group_standings_success(self, tournament_service, sample_championship):
        """Test calculating group standings"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        group_games = [
            Mock(team1_code="CAN", team2_code="USA", team1_score=3, team2_score=2,
                 result_type="REG", team1_points=3, team2_points=0),
            Mock(team1_code="CAN", team2_code="SWE", team1_score=4, team2_score=3,
                 result_type="OT", team1_points=2, team2_points=1),
            Mock(team1_code="USA", team2_code="SWE", team1_score=2, team2_score=1,
                 result_type="SO", team1_points=2, team2_points=1),
            Mock(team1_code="CAN", team2_code="FIN", team1_score=2, team2_score=4,
                 result_type="REG", team1_points=0, team2_points=3),
        ]
        tournament_service.repository.get_group_games = Mock(return_value=group_games)
        
        # Act
        standings = tournament_service.get_group_standings(2024, "A")
        
        # Assert
        assert len(standings) == 4
        assert standings[0].name == "CAN"  # Most points
        assert standings[0].pts == 5  # 3 + 2 + 0
        assert standings[0].gp == 3
        assert standings[0].w == 1
        assert standings[0].otw == 1
        assert standings[0].l == 1
        assert standings[0].gf == 9  # 3 + 4 + 2
        assert standings[0].ga == 9  # 2 + 3 + 4
        assert standings[0].rank_in_group == 1
    
    def test_get_group_standings_no_games(self, tournament_service, sample_championship):
        """Test standings for non-existent group"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        tournament_service.repository.get_group_games = Mock(return_value=[])
        
        # Act & Assert
        with pytest.raises(ValidationError) as exc:
            tournament_service.get_group_standings(2024, "Z")
        assert "Group Z not found in championship" in str(exc.value)
        assert exc.value.field == "group"
    
    def test_get_group_standings_championship_not_found(self, tournament_service):
        """Test standings when championship doesn't exist"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            tournament_service.get_group_standings(9999, "A")
        assert "Championship year with ID 9999 not found" in str(exc.value)
    
    # Test get_playoff_bracket
    
    def test_get_playoff_bracket_success(self, tournament_service, sample_championship):
        """Test getting playoff bracket with resolved teams"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        tournament_service.repository.get_all_games = Mock(return_value=[])
        
        # Mock playoff games
        qf_games = [
            Mock(id=1, team1_code="A1", team2_code="B2", team1_score=3, team2_score=2),
            Mock(id=2, team1_code="B1", team2_code="A2", team1_score=None, team2_score=None)
        ]
        sf_games = [
            Mock(id=3, team1_code="W1", team2_code="W2", team1_score=None, team2_score=None)
        ]
        
        tournament_service.repository.get_round_games = Mock(side_effect=[
            qf_games,  # Quarterfinals
            sf_games,  # Semifinals
            [],        # Bronze Medal Game
            []         # Gold Medal Game
        ])
        
        # Mock resolver
        mock_resolver = Mock(spec=PlayoffResolver)
        mock_resolver.get_resolved_code.side_effect = ["CAN", "USA", "SWE", "FIN", "CAN", "SWE"]
        
        with patch('services.tournament_service.PlayoffResolver', return_value=mock_resolver):
            # Act
            bracket = tournament_service.get_playoff_bracket(2024)
        
        # Assert
        assert 'Quarterfinals' in bracket
        assert len(bracket['Quarterfinals']) == 2
        assert bracket['Quarterfinals'][0]['team1_resolved'] == "CAN"
        assert bracket['Quarterfinals'][0]['team2_resolved'] == "USA"
        assert bracket['Quarterfinals'][0]['completed'] is True
        assert bracket['Semifinals'][0]['team1_resolved'] == "CAN"
        assert bracket['Semifinals'][0]['team2_resolved'] == "SWE"
    
    def test_get_playoff_bracket_championship_not_found(self, tournament_service):
        """Test playoff bracket for non-existent championship"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            tournament_service.get_playoff_bracket(9999)
        assert "Championship year with ID 9999 not found" in str(exc.value)
    
    # Test update_playoff_progression
    
    def test_update_playoff_progression_success(self, tournament_service, sample_championship):
        """Test updating playoff progression after game result"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        completed_game = Mock(id=1, team1_code="CAN", team2_code="USA", 
                             team1_score=3, team2_score=2, round="Quarterfinals")
        
        upcoming_game1 = Mock(id=2, team1_code="W1", team2_code="SWE")
        upcoming_game2 = Mock(id=3, team1_code="L1", team2_code="FIN")
        
        tournament_service.repository.get_all_games = Mock(return_value=[completed_game])
        tournament_service.repository.get_upcoming_playoff_games = Mock(
            return_value=[upcoming_game1, upcoming_game2]
        )
        tournament_service.commit = Mock()
        
        # Mock resolver - fix the side effects to match expected behavior
        mock_resolver = Mock(spec=PlayoffResolver)
        # W1 should resolve to CAN (winner of game 1), L1 should resolve to USA (loser of game 1)
        mock_resolver.get_resolved_code.side_effect = lambda code: {
            "W1": "CAN",
            "L1": "USA"
        }.get(code, code)
        
        with patch('services.tournament_service.Game') as mock_game:
            mock_game.query.get.return_value = completed_game
            with patch('services.tournament_service.PlayoffResolver', return_value=mock_resolver):
                # Act
                result = tournament_service.update_playoff_progression(2024, 1)
        
        # Assert
        assert result['winner'] == "CAN"
        assert result['loser'] == "USA"
        assert len(result['affected_games']) == 2
        assert upcoming_game1.team1_code == "CAN"
        assert upcoming_game2.team1_code == "USA"
        tournament_service.commit.assert_called_once()
    
    def test_update_playoff_progression_game_not_complete(self, tournament_service, sample_championship):
        """Test error when game is not complete"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        incomplete_game = Mock(id=1, team1_score=None, team2_score=None)
        
        with patch('services.tournament_service.Game') as mock_game:
            mock_game.query.get.return_value = incomplete_game
            
            # Act & Assert
            with pytest.raises(BusinessRuleError) as exc:
                tournament_service.update_playoff_progression(2024, 1)
            assert "Game must be completed to update playoff progression" in str(exc.value)
            assert exc.value.rule == "incomplete_game"
    
    def test_update_playoff_progression_game_not_found(self, tournament_service, sample_championship):
        """Test error when game doesn't exist"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        with patch('services.tournament_service.Game') as mock_game:
            mock_game.query.get.return_value = None
            
            # Act & Assert
            with pytest.raises(NotFoundError) as exc:
                tournament_service.update_playoff_progression(2024, 999)
            assert "Game with ID 999 not found" in str(exc.value)
    
    # Test get_tournament_schedule
    
    def test_get_tournament_schedule_all_games(self, tournament_service, sample_championship):
        """Test getting full tournament schedule"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        games = [
            Mock(date="2024-05-10", game_number=1),
            Mock(date="2024-05-11", game_number=2),
            Mock(date="2024-05-10", game_number=3),
        ]
        tournament_service.repository.get_filtered_games = Mock(return_value=games)
        
        # Act
        result = tournament_service.get_tournament_schedule(2024)
        
        # Assert
        assert len(result) == 3
        assert result[0].game_number == 1  # Sorted by date and game number
        assert result[1].game_number == 3
        assert result[2].game_number == 2
        tournament_service.repository.get_filtered_games.assert_called_once_with(
            2024, None, None, None
        )
    
    def test_get_tournament_schedule_with_filters(self, tournament_service, sample_championship):
        """Test getting schedule with filters"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        tournament_service.repository.get_filtered_games = Mock(return_value=[])
        
        # Act
        tournament_service.get_tournament_schedule(
            2024, round_name="Quarterfinals", 
            date_from="2024-05-20", date_to="2024-05-25"
        )
        
        # Assert
        tournament_service.repository.get_filtered_games.assert_called_once_with(
            2024, "Quarterfinals", "2024-05-20", "2024-05-25"
        )
    
    def test_get_tournament_schedule_championship_not_found(self, tournament_service):
        """Test schedule for non-existent championship"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=None)
        
        # Act & Assert
        with pytest.raises(NotFoundError) as exc:
            tournament_service.get_tournament_schedule(9999)
        assert "Championship year with ID 9999 not found" in str(exc.value)
    
    # Test get_tournament_statistics
    
    def test_get_tournament_statistics_success(self, tournament_service, sample_championship):
        """Test getting comprehensive tournament statistics"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        stats = {
            'total_games': 64,
            'completed_games': 48,
            'total_goals': 288,
            'regulation_wins': 36,
            'overtime_games': 8,
            'shootout_games': 4,
            'team_count': 16,
            'player_count': 368,
            'total_penalty_minutes': 720,
            'powerplay_goals': 45,
            'empty_net_goals': 12
        }
        tournament_service.repository.get_tournament_statistics = Mock(return_value=stats)
        
        # Act
        result = tournament_service.get_tournament_statistics(2024)
        
        # Assert
        assert result['championship'] == sample_championship
        assert result['total_games'] == 64
        assert result['completed_games'] == 48
        assert result['goals_scored'] == 288
        assert result['average_goals_per_game'] == 6.0  # 288 / 48
        assert result['regulation_wins'] == 36
        assert result['overtime_games'] == 8
        assert result['shootout_games'] == 4
        assert result['participating_teams'] == 16
        assert result['total_players'] == 368
        assert result['penalty_minutes'] == 720
        assert result['powerplay_goals'] == 45
        assert result['empty_net_goals'] == 12
    
    def test_get_tournament_statistics_no_completed_games(self, tournament_service, sample_championship):
        """Test statistics when no games are completed"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        stats = {
            'total_games': 64,
            'completed_games': 0,
            'total_goals': 0,
            'regulation_wins': 0,
            'overtime_games': 0,
            'shootout_games': 0,
            'team_count': 16,
            'player_count': 0,
            'total_penalty_minutes': 0,
            'powerplay_goals': 0,
            'empty_net_goals': 0
        }
        tournament_service.repository.get_tournament_statistics = Mock(return_value=stats)
        
        # Act
        result = tournament_service.get_tournament_statistics(2024)
        
        # Assert
        assert result['average_goals_per_game'] == 0  # Avoid division by zero
    
    # Test validate_tournament_integrity
    
    def test_validate_tournament_integrity_all_issues(self, tournament_service, sample_championship):
        """Test validation finding multiple issues"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        games = [
            # Past game without result
            Mock(id=1, game_number=1, team1_code="CAN", team2_code="USA",
                 team1_score=None, team2_score=None, date="2024-01-01", round="Group Stage"),
            # Game with negative score
            Mock(id=2, game_number=2, team1_code="SWE", team2_code="FIN",
                 team1_score=-1, team2_score=2, date="2024-01-02", round="Group Stage"),
            # OT game with wrong goal difference
            Mock(id=3, game_number=3, team1_code="CZE", team2_code="SVK",
                 team1_score=5, team2_score=2, result_type="OT", date="2024-01-03", round="Group Stage"),
            # Completed game without SOG
            Mock(id=4, game_number=4, team1_code="RUS", team2_code="GER",
                 team1_score=3, team2_score=2, date="2024-01-04", round="Group Stage"),
            # Unresolved playoff game when quarterfinals are complete
            Mock(id=5, game_number=50, team1_code="W1", team2_code="W2",
                 team1_score=None, team2_score=None, date="2024-01-20", round="Semifinals"),
            # Add completed quarterfinal games to trigger playoff issue
            Mock(id=6, game_number=45, team1_code="CAN", team2_code="USA",
                 team1_score=3, team2_score=2, date="2024-01-15", round="Quarterfinals"),
            Mock(id=7, game_number=46, team1_code="SWE", team2_code="FIN",
                 team1_score=4, team2_score=3, date="2024-01-15", round="Quarterfinals"),
            Mock(id=8, game_number=47, team1_code="CZE", team2_code="SVK",
                 team1_score=2, team2_score=1, date="2024-01-15", round="Quarterfinals"),
            Mock(id=9, game_number=48, team1_code="RUS", team2_code="GER",
                 team1_score=5, team2_score=4, date="2024-01-15", round="Quarterfinals"),
        ]
        
        tournament_service.repository.get_all_games = Mock(return_value=games)
        tournament_service.repository.get_game_shots_on_goal = Mock(side_effect=[None, None, None, None, None, None, None, None, None])
        
        # Mock quarterfinals as complete for playoff validation
        qf_complete_games = [
            Mock(team1_score=3, team2_score=2, round="Quarterfinals"),
            Mock(team1_score=4, team2_score=3, round="Quarterfinals"),
            Mock(team1_score=2, team2_score=1, round="Quarterfinals"),
            Mock(team1_score=5, team2_score=4, round="Quarterfinals"),
        ]
        
        with patch('services.tournament_service.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2024-12-31"
            
            # Act
            issues = tournament_service.validate_tournament_integrity(2024)
        
        # Assert
        assert len(issues['missing_results']) == 2  # Group game + unresolved semifinal
        assert any("Game 1: CAN vs USA" in issue for issue in issues['missing_results'])
        
        assert len(issues['invalid_scores']) == 1
        assert "Game 2: Negative score" in issues['invalid_scores'][0]
        
        assert len(issues['data_inconsistencies']) == 1
        assert "Game 3: OT game should have 1-goal difference" in issues['data_inconsistencies'][0]
        
        assert len(issues['missing_statistics']) == 7  # All completed games lack SOG (3 group + 4 QF, game 1 has no score)
        
        # Playoff validation should detect unresolved semifinal when all QFs are complete
        assert len(issues['playoff_issues']) == 1
        assert "Unresolved playoff teams in Semifinals" in issues['playoff_issues'][0]
    
    def test_validate_tournament_integrity_no_issues(self, tournament_service, sample_championship):
        """Test validation with clean data"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        
        games = [
            Mock(id=1, game_number=1, team1_code="CAN", team2_code="USA",
                 team1_score=3, team2_score=2, result_type="REG", date="2024-01-01", round="Group Stage"),
        ]
        
        tournament_service.repository.get_all_games = Mock(return_value=games)
        tournament_service.repository.get_game_shots_on_goal = Mock(return_value=[Mock()])  # Has SOG data
        
        # Act
        issues = tournament_service.validate_tournament_integrity(2024)
        
        # Assert
        assert len(issues['missing_results']) == 0
        assert len(issues['invalid_scores']) == 0
        assert len(issues['missing_statistics']) == 0
        assert len(issues['playoff_issues']) == 0
        assert len(issues['data_inconsistencies']) == 0
    
    # Test _calculate_team_stats_for_games
    
    def test_calculate_team_stats_for_games_complete(self, tournament_service):
        """Test comprehensive team statistics calculation"""
        # Arrange
        games = [
            # Win in regulation
            Mock(team1_code="CAN", team2_code="USA", team1_score=3, team2_score=2,
                 result_type="REG", team1_points=3, team2_points=0),
            # Loss in overtime
            Mock(team1_code="SWE", team2_code="CAN", team1_score=4, team2_score=3,
                 result_type="OT", team1_points=2, team2_points=1),
            # Win in shootout
            Mock(team1_code="CAN", team2_code="FIN", team1_score=2, team2_score=1,
                 result_type="SO", team1_points=2, team2_points=1),
        ]
        
        # Act
        stats = tournament_service._calculate_team_stats_for_games(games, "CAN", "A")
        
        # Assert
        assert stats.name == "CAN"
        assert stats.group == "A"
        assert stats.gp == 3
        assert stats.w == 1
        assert stats.otl == 1
        assert stats.sow == 1
        assert stats.pts == 6  # 3 + 1 + 2
        assert stats.gf == 8   # 3 + 3 + 2
        assert stats.ga == 7   # 2 + 4 + 1
    
    def test_calculate_team_stats_for_games_incomplete(self, tournament_service):
        """Test statistics with incomplete games"""
        # Arrange
        games = [
            Mock(team1_code="CAN", team2_code="USA", team1_score=3, team2_score=2,
                 result_type="REG", team1_points=3, team2_points=0),
            Mock(team1_code="CAN", team2_code="SWE", team1_score=None, team2_score=None,
                 result_type=None, team1_points=0, team2_points=0),
        ]
        
        # Act
        stats = tournament_service._calculate_team_stats_for_games(games, "CAN", "A")
        
        # Assert
        assert stats.gp == 1  # Only count completed games
        assert stats.w == 1
        assert stats.pts == 3
    
    # Test playoff resolver caching
    
    def test_playoff_resolver_caching(self, tournament_service, sample_championship):
        """Test that playoff resolver is cached properly"""
        # Arrange
        tournament_service.repository.find_by_id = Mock(return_value=sample_championship)
        tournament_service.repository.get_all_games = Mock(return_value=[])
        tournament_service.repository.get_round_games = Mock(return_value=[])
        
        with patch('services.tournament_service.PlayoffResolver') as mock_resolver_class:
            mock_resolver = Mock(spec=PlayoffResolver)
            mock_resolver.get_resolved_code.return_value = "CAN"
            mock_resolver_class.return_value = mock_resolver
            
            # Act - call twice
            tournament_service.get_playoff_bracket(2024)
            tournament_service.get_playoff_bracket(2024)
        
        # Assert - resolver created only once
        mock_resolver_class.assert_called_once()
    
    # Test edge cases
    
    def test_extract_rounds_custom_order(self, tournament_service):
        """Test round extraction with custom round names"""
        # Arrange
        games = [
            Mock(round="Custom Round 1", date="2024-05-10"),
            Mock(round="Group Stage", date="2024-05-01"),
            Mock(round="Semifinals", date="2024-05-20"),
            Mock(round="Custom Round 2", date="2024-05-15"),
        ]
        
        # Act
        rounds = tournament_service._extract_rounds(games)
        
        # Assert
        assert rounds[0]['name'] == "Group Stage"
        assert rounds[1]['name'] == "Semifinals"
        assert rounds[2]['name'] == "Custom Round 1"
        assert rounds[3]['name'] == "Custom Round 2"
    
    def test_extract_groups_with_placeholders(self, tournament_service):
        """Test group extraction ignoring placeholder teams"""
        # Arrange
        games = [
            Mock(team1_code="CAN", team2_code="USA", group="A"),
            Mock(team1_code="W1", team2_code="L2", group="A"),  # Placeholders
            Mock(team1_code="SWE", team2_code="A1", group="A"),  # Mixed
        ]
        
        # Act
        groups = tournament_service._extract_groups(games)
        
        # Assert
        assert groups['A'] == ["CAN", "SWE", "USA"]  # Only real teams, sorted