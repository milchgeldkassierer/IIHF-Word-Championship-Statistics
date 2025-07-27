"""
Comprehensive tests for year views routes
Tests all tournament-related endpoints including year view, stats data, and team vs team
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
from unittest.mock import Mock, MagicMock, patch
from flask import Flask, url_for
import json
from datetime import datetime

# Importiere die Services und Exceptions
from app.services.core import GameService, TournamentService, TeamService, StandingsService, PlayerService
from services.exceptions import ServiceError, ValidationError, NotFoundError, BusinessRuleError
from models import ChampionshipYear, Game, Player, TeamStats, GameDisplay


class TestYearViews:
    """Test suite for year views routes"""
    
    @pytest.fixture
    def app(self):
        """Create Flask test app with year blueprint"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        
        # Import and register the blueprint
        from routes.year import year_bp
        app.register_blueprint(year_bp, url_prefix='/year')
        
        # Erstelle auch den main blueprint für redirects
        from flask import Blueprint
        main_bp = Blueprint('main_bp', __name__)
        @main_bp.route('/')
        def index():
            return 'Home'
        app.register_blueprint(main_bp)
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    @pytest.fixture
    def mock_services(self):
        """Create mock services"""
        return {
            'tournament_service': MagicMock(spec=TournamentService),
            'game_service': MagicMock(spec=GameService),
            'standings_service': MagicMock(spec=StandingsService),
            'player_service': MagicMock(spec=PlayerService),
            'team_service': MagicMock(spec=TeamService)
        }
    
    @pytest.fixture
    def sample_year(self):
        """Create sample championship year"""
        year = Mock(spec=ChampionshipYear)
        year.id = 2024
        year.year = 2024
        year.fixture_path = 'fixtures/2024.json'
        return year
    
    @pytest.fixture
    def sample_games(self):
        """Create sample games for testing"""
        games = []
        
        # Preliminary round games
        for i in range(1, 5):
            game = Mock(spec=Game)
            game.id = i
            game.year_id = 2024
            game.game_number = i
            game.round = 'Preliminary Round'
            game.group = 'Group A'
            game.team1_code = 'CAN' if i % 2 == 0 else 'USA'
            game.team2_code = 'SWE' if i % 2 == 0 else 'FIN'
            game.team1_score = 3 if i % 2 == 0 else 2
            game.team2_score = 2 if i % 2 == 0 else 3
            game.result_type = 'REG'
            game.team1_points = 3 if i % 2 == 0 else 0
            game.team2_points = 0 if i % 2 == 0 else 3
            game.date = '2024-05-10'
            game.start_time = '15:00'
            game.location = 'Test Arena'
            game.venue = 'Test Venue'
            games.append(game)
        
        # Quarterfinal games
        for i in range(57, 61):
            game = Mock(spec=Game)
            game.id = i
            game.year_id = 2024
            game.game_number = i
            game.round = 'Quarterfinals'
            game.group = None
            game.team1_code = f'A{i-56}'
            game.team2_code = f'B{i-56}'
            game.team1_score = None
            game.team2_score = None
            game.result_type = None
            game.team1_points = 0
            game.team2_points = 0
            game.date = '2024-05-20'
            game.start_time = '15:00'
            game.location = 'Test Arena'
            game.venue = 'Test Venue'
            games.append(game)
            
        return games
    
    @pytest.fixture
    def sample_players(self):
        """Create sample players"""
        players = []
        teams = ['CAN', 'USA', 'SWE', 'FIN']
        
        for team in teams:
            for i in range(1, 4):
                player = Mock(spec=Player)
                player.id = f"{team}_{i}"
                player.first_name = f"First{i}"
                player.last_name = f"Last{i}"
                player.team_code = team
                players.append(player)
                
        return players
    
    # Test year_view GET
    
    def test_year_view_success(self, client, mock_services, sample_year, sample_games, sample_players):
        """Test successful year view loading"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.GameService', return_value=mock_services['game_service']), \
             patch('routes.year.views.StandingsService', return_value=mock_services['standings_service']), \
             patch('routes.year.views.PlayerService', return_value=mock_services['player_service']), \
             patch('routes.year.views.TeamService', return_value=mock_services['team_service']):
            
            # Mocks konfigurieren
            mock_services['tournament_service'].get_by_id.return_value = sample_year
            mock_services['game_service'].get_games_by_year.return_value = sample_games
            mock_services['game_service'].get_shots_on_goal_by_year.return_value = {}
            mock_services['game_service'].get_goals_by_games.return_value = {}
            mock_services['game_service'].get_penalties_by_games.return_value = {}
            mock_services['game_service'].get_overrules_by_year.return_value = {}
            
            # Mock standings calculation
            team_stats = {}
            for team in ['CAN', 'USA', 'SWE', 'FIN']:
                stats = Mock(spec=TeamStats)
                stats.name = team
                stats.group = 'Group A'
                stats.pts = 6
                stats.gd = 2
                stats.gf = 10
                stats.rank_in_group = 1
                team_stats[team] = stats
            mock_services['standings_service'].calculate_standings_from_games.return_value = team_stats
            
            # Mock player data
            mock_services['player_service'].get_all_players.return_value = sample_players
            mock_services['player_service'].get_player_stats_for_year.return_value = {
                'CAN_1': {'g': 5, 'a': 3, 'p': 8, 'obj': sample_players[0]}
            }
            mock_services['player_service'].get_player_penalty_stats_for_year.return_value = {
                'USA_1': {'pim': 10, 'obj': sample_players[3]}
            }
            
            # Mock team stats
            mock_services['team_service'].calculate_team_stats_for_year.return_value = []
            
            # Mock für fixture file
            with patch('os.path.exists', return_value=True), \
                 patch('builtins.open', mock_open(read_data='{"hosts": ["CAN", "USA"], "schedule": []}')):
                
                # Act
                response = client.get('/year/2024')
            
            # Assert
            assert response.status_code == 200
            mock_services['tournament_service'].get_by_id.assert_called_once_with(2024)
            mock_services['game_service'].get_games_by_year.assert_called_once_with(2024)
    
    def test_year_view_not_found(self, client, mock_services):
        """Test year view when tournament year doesn't exist"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']):
            mock_services['tournament_service'].get_by_id.side_effect = NotFoundError("Year not found")
            
            # Act
            response = client.get('/year/9999', follow_redirects=True)
            
            # Assert
            assert response.status_code == 200
            assert b'Tournament year not found' in response.data
    
    # Test year_view POST (game score update)
    
    def test_year_view_update_score_success(self, client, mock_services, sample_year, sample_games, sample_players):
        """Test successful game score update via POST"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.GameService', return_value=mock_services['game_service']), \
             patch('routes.year.views.StandingsService', return_value=mock_services['standings_service']), \
             patch('routes.year.views.PlayerService', return_value=mock_services['player_service']), \
             patch('routes.year.views.TeamService', return_value=mock_services['team_service']):
            
            # Setup mocks
            self._setup_basic_mocks(mock_services, sample_year, sample_games, sample_players)
            
            # Act
            response = client.post('/year/2024', data={
                'game_id': '1',
                'team1_score': '4',
                'team2_score': '2',
                'result_type': 'REG'
            }, follow_redirects=True)
            
            # Assert
            assert response.status_code == 200
            assert b'Game result updated!' in response.data
            mock_services['game_service'].update_game_score.assert_called_once_with(
                game_id=1,
                team1_score=4,
                team2_score=2,
                result_type='REG'
            )
    
    def test_year_view_update_score_validation_error(self, client, mock_services, sample_year, sample_games, sample_players):
        """Test game score update with validation error"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.GameService', return_value=mock_services['game_service']), \
             patch('routes.year.views.StandingsService', return_value=mock_services['standings_service']), \
             patch('routes.year.views.PlayerService', return_value=mock_services['player_service']), \
             patch('routes.year.views.TeamService', return_value=mock_services['team_service']):
            
            # Setup mocks
            self._setup_basic_mocks(mock_services, sample_year, sample_games, sample_players)
            mock_services['game_service'].update_game_score.side_effect = ValidationError("Invalid score", field="team1_score")
            
            # Act
            response = client.post('/year/2024', data={
                'game_id': '1',
                'team1_score': '-1',
                'team2_score': '2',
                'result_type': 'REG'
            }, follow_redirects=True)
            
            # Assert
            assert response.status_code == 200
            assert b'Validation error: Invalid score' in response.data
    
    def test_year_view_update_score_service_error(self, client, mock_services, sample_year, sample_games, sample_players):
        """Test game score update with service error"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.GameService', return_value=mock_services['game_service']), \
             patch('routes.year.views.StandingsService', return_value=mock_services['standings_service']), \
             patch('routes.year.views.PlayerService', return_value=mock_services['player_service']), \
             patch('routes.year.views.TeamService', return_value=mock_services['team_service']):
            
            # Setup mocks
            self._setup_basic_mocks(mock_services, sample_year, sample_games, sample_players)
            mock_services['game_service'].update_game_score.side_effect = ServiceError("Database error")
            
            # Act
            response = client.post('/year/2024', data={
                'game_id': '1',
                'team1_score': '3',
                'team2_score': '2',
                'result_type': 'REG'
            }, follow_redirects=True)
            
            # Assert
            assert response.status_code == 200
            assert b'Error updating result: Database error' in response.data
    
    # Test get_stats_data endpoint
    
    def test_get_stats_data_success(self, client, mock_services, sample_year, sample_players):
        """Test successful stats data retrieval"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.PlayerService', return_value=mock_services['player_service']):
            
            mock_services['tournament_service'].get_by_id.return_value = sample_year
            
            # Mock player stats
            mock_services['player_service'].get_player_stats_for_year.return_value = {
                'CAN_1': {'g': 5, 'a': 3, 'p': 8, 'obj': sample_players[0]},
                'USA_1': {'g': 3, 'a': 5, 'p': 8, 'obj': sample_players[3]}
            }
            mock_services['player_service'].get_player_penalty_stats_for_year.return_value = {
                'CAN_1': {'pim': 10, 'obj': sample_players[0]}
            }
            
            # Act
            response = client.get('/year/2024/stats_data')
            
            # Assert
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'top_scorers_points' in data
            assert 'top_goal_scorers' in data
            assert 'top_assist_providers' in data
            assert 'top_penalty_players' in data
            assert len(data['top_scorers_points']) == 2
    
    def test_get_stats_data_with_team_filter(self, client, mock_services, sample_year, sample_players):
        """Test stats data retrieval with team filter"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.PlayerService', return_value=mock_services['player_service']):
            
            mock_services['tournament_service'].get_by_id.return_value = sample_year
            
            # Mock filtered player stats
            mock_services['player_service'].get_player_stats_for_year.return_value = {
                'CAN_1': {'g': 5, 'a': 3, 'p': 8, 'obj': sample_players[0]}
            }
            mock_services['player_service'].get_player_penalty_stats_for_year.return_value = {}
            
            # Act
            response = client.get('/year/2024/stats_data?stats_team_filter=CAN')
            
            # Assert
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['selected_team'] == 'CAN'
            mock_services['player_service'].get_player_stats_for_year.assert_called_with(
                year_id=2024,
                team_filter='CAN'
            )
    
    def test_get_stats_data_year_not_found(self, client, mock_services):
        """Test stats data when year doesn't exist"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']):
            mock_services['tournament_service'].get_by_id.side_effect = NotFoundError("Year not found")
            
            # Act
            response = client.get('/year/9999/stats_data')
            
            # Assert
            assert response.status_code == 404
            data = json.loads(response.data)
            assert data['error'] == 'Tournament year not found'
    
    # Test team_vs_team_view
    
    def test_team_vs_team_success(self, client, mock_services, sample_year):
        """Test successful team vs team view"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.GameService', return_value=mock_services['game_service']), \
             patch('routes.year.views.get_all_resolved_games') as mock_get_resolved, \
             patch('routes.year.views.db') as mock_db:
            
            mock_services['tournament_service'].get_by_id.return_value = sample_year
            
            # Mock resolved games
            resolved_game = {
                'game': Mock(
                    id=1,
                    year_id=2024,
                    team1_score=3,
                    team2_score=2,
                    result_type='REG',
                    round='Preliminary Round',
                    date='2024-05-10',
                    location='Test Arena'
                ),
                'team1_code': 'CAN',
                'team2_code': 'USA',
                'year': sample_year
            }
            mock_get_resolved.return_value = [resolved_game]
            
            # Mock game service methods
            mock_services['game_service'].get_goals_by_games.return_value = {}
            mock_services['game_service'].get_penalties_by_games.return_value = {}
            mock_services['game_service'].get_shots_on_goal_by_year.return_value = {}
            
            # Mock year object für Anzeige
            mock_db.session.get.return_value = sample_year
            
            # Act
            response = client.get('/year/2024/team_vs_team/CAN/USA')
            
            # Assert
            assert response.status_code == 200
            assert b'CAN' in response.data
            assert b'USA' in response.data
    
    def test_team_vs_team_year_not_found(self, client, mock_services):
        """Test team vs team when year doesn't exist"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']):
            mock_services['tournament_service'].get_by_id.side_effect = NotFoundError("Year not found")
            
            # Act
            response = client.get('/year/9999/team_vs_team/CAN/USA', follow_redirects=True)
            
            # Assert
            assert response.status_code == 200
            assert b'Turnierjahr nicht gefunden' in response.data
    
    def test_team_vs_team_with_stats(self, client, mock_services, sample_year):
        """Test team vs team with complete statistics"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.GameService', return_value=mock_services['game_service']), \
             patch('routes.year.views.get_all_resolved_games') as mock_get_resolved, \
             patch('routes.year.views.db') as mock_db:
            
            mock_services['tournament_service'].get_by_id.return_value = sample_year
            
            # Mock resolved games mit mehreren Spielen
            games = []
            for i in range(3):
                game = Mock(
                    id=i+1,
                    year_id=2024,
                    team1_score=3 if i == 0 else 2,
                    team2_score=2 if i == 0 else 3,
                    result_type='REG' if i < 2 else 'OT',
                    round='Preliminary Round',
                    date=f'2024-05-{10+i}',
                    location='Test Arena'
                )
                resolved = {
                    'game': game,
                    'team1_code': 'CAN' if i == 0 else 'USA',
                    'team2_code': 'USA' if i == 0 else 'CAN',
                    'year': sample_year
                }
                games.append(resolved)
            
            mock_get_resolved.return_value = games
            
            # Mock goals - Powerplay goals
            goals = {
                1: [Mock(team_code='CAN', goal_type='PP')],
                2: [Mock(team_code='USA', goal_type='EV')],
                3: [Mock(team_code='USA', goal_type='PP')]
            }
            mock_services['game_service'].get_goals_by_games.return_value = goals
            
            # Mock penalties
            from constants import PIM_MAP
            with patch('routes.year.views.PIM_MAP', PIM_MAP):
                penalties = {
                    1: [Mock(team_code='CAN', penalty_type='MINOR')],  # 2 PIM
                    2: [Mock(team_code='USA', penalty_type='MAJOR')],  # 5 PIM
                    3: [Mock(team_code='CAN', penalty_type='MINOR')]   # 2 PIM
                }
                mock_services['game_service'].get_penalties_by_games.return_value = penalties
                
                # Mock shots on goal
                sog = {
                    1: {'CAN': {1: 10, 2: 12, 3: 8, 4: 0}, 'USA': {1: 8, 2: 10, 3: 9, 4: 0}},
                    2: {'USA': {1: 11, 2: 13, 3: 10, 4: 0}, 'CAN': {1: 9, 2: 11, 3: 8, 4: 0}},
                    3: {'USA': {1: 12, 2: 14, 3: 11, 4: 2}, 'CAN': {1: 10, 2: 12, 3: 9, 4: 1}}
                }
                mock_services['game_service'].get_shots_on_goal_by_year.return_value = sog
                
                # Mock year object
                mock_db.session.get.return_value = sample_year
                
                # Act
                response = client.get('/year/2024/team_vs_team/CAN/USA')
                
                # Assert
                assert response.status_code == 200
                # Prüfe ob Statistiken in der Response sind
                assert b'Spiele' in response.data  # Anzahl Spiele
                assert b'Tore' in response.data    # Tore
                assert b'PIM' in response.data     # Strafminuten
    
    # Edge cases und Fehlerbehandlung
    
    def test_year_view_with_playoff_resolution(self, client, mock_services, sample_year, sample_games, sample_players):
        """Test year view with playoff team resolution"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.GameService', return_value=mock_services['game_service']), \
             patch('routes.year.views.StandingsService', return_value=mock_services['standings_service']), \
             patch('routes.year.views.PlayerService', return_value=mock_services['player_service']), \
             patch('routes.year.views.TeamService', return_value=mock_services['team_service']), \
             patch('routes.year.views.PlayoffResolver') as mock_playoff_resolver:
            
            # Setup basic mocks
            self._setup_basic_mocks(mock_services, sample_year, sample_games, sample_players)
            
            # Mock playoff resolver
            resolver_instance = Mock()
            resolver_instance.get_resolved_code.side_effect = lambda code: {
                'A1': 'CAN',
                'A2': 'USA',
                'B1': 'SWE',
                'B2': 'FIN'
            }.get(code, code)
            resolver_instance._playoff_team_map = {}
            mock_playoff_resolver.return_value = resolver_instance
            
            # Mock fixture file mit playoff Struktur
            fixture_data = {
                "hosts": ["CAN", "USA"],
                "schedule": [
                    {"round": "Quarterfinals", "gameNumber": 57},
                    {"round": "Quarterfinals", "gameNumber": 58},
                    {"round": "Semifinals", "gameNumber": 61},
                    {"round": "Semifinals", "gameNumber": 62},
                    {"round": "Bronze Medal Game", "gameNumber": 63},
                    {"round": "Gold Medal Game", "gameNumber": 64}
                ]
            }
            
            with patch('os.path.exists', return_value=True), \
                 patch('builtins.open', mock_open(read_data=json.dumps(fixture_data))):
                
                # Act
                response = client.get('/year/2024')
                
                # Assert
                assert response.status_code == 200
                # Playoff resolver sollte initialisiert worden sein
                mock_playoff_resolver.assert_called_once()
    
    def test_year_view_with_custom_seeding(self, client, mock_services, sample_year, sample_games, sample_players):
        """Test year view with custom seeding configuration"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.GameService', return_value=mock_services['game_service']), \
             patch('routes.year.views.StandingsService', return_value=mock_services['standings_service']), \
             patch('routes.year.views.PlayerService', return_value=mock_services['player_service']), \
             patch('routes.year.views.TeamService', return_value=mock_services['team_service']), \
             patch('routes.year.views.get_custom_seeding_from_db') as mock_custom_seeding, \
             patch('routes.year.views.get_custom_qf_seeding_from_db') as mock_custom_qf:
            
            # Setup basic mocks
            self._setup_basic_mocks(mock_services, sample_year, sample_games, sample_players)
            
            # Mock custom seeding
            mock_custom_qf.return_value = {
                'A1': 'USA',
                'A2': 'CAN',
                'B1': 'FIN',
                'B2': 'SWE'
            }
            
            mock_custom_seeding.return_value = {
                'seed1': 'USA',
                'seed2': 'FIN',
                'seed3': 'CAN',
                'seed4': 'SWE'
            }
            
            # Act
            response = client.get('/year/2024')
            
            # Assert
            assert response.status_code == 200
            mock_custom_qf.assert_called_with(2024)
            mock_custom_seeding.assert_called_with(2024)
    
    def test_year_view_empty_scores(self, client, mock_services, sample_year, sample_games, sample_players):
        """Test year view POST with empty score fields"""
        # Arrange
        with patch('routes.year.views.TournamentService', return_value=mock_services['tournament_service']), \
             patch('routes.year.views.GameService', return_value=mock_services['game_service']), \
             patch('routes.year.views.StandingsService', return_value=mock_services['standings_service']), \
             patch('routes.year.views.PlayerService', return_value=mock_services['player_service']), \
             patch('routes.year.views.TeamService', return_value=mock_services['team_service']):
            
            # Setup mocks
            self._setup_basic_mocks(mock_services, sample_year, sample_games, sample_players)
            
            # Act - empty score fields
            response = client.post('/year/2024', data={
                'game_id': '1',
                'team1_score': '',
                'team2_score': '',
                'result_type': ''
            }, follow_redirects=True)
            
            # Assert
            assert response.status_code == 200
            # update_game_score sollte mit None aufgerufen werden
            mock_services['game_service'].update_game_score.assert_called_once_with(
                game_id=1,
                team1_score=None,
                team2_score=None,
                result_type=''
            )
    
    # Helper methods
    
    def _setup_basic_mocks(self, mock_services, sample_year, sample_games, sample_players):
        """Setup basic mocks for year view tests"""
        # Tournament service
        mock_services['tournament_service'].get_by_id.return_value = sample_year
        
        # Game service
        mock_services['game_service'].get_games_by_year.return_value = sample_games
        mock_services['game_service'].get_shots_on_goal_by_year.return_value = {}
        mock_services['game_service'].get_goals_by_games.return_value = {}
        mock_services['game_service'].get_penalties_by_games.return_value = {}
        mock_services['game_service'].get_overrules_by_year.return_value = {}
        
        # Standings service
        team_stats = {}
        for team in ['CAN', 'USA', 'SWE', 'FIN']:
            stats = Mock(spec=TeamStats)
            stats.name = team
            stats.group = 'Group A'
            stats.pts = 6
            stats.gd = 2
            stats.gf = 10
            stats.rank_in_group = 1
            team_stats[team] = stats
        mock_services['standings_service'].calculate_standings_from_games.return_value = team_stats
        
        # Player service
        mock_services['player_service'].get_all_players.return_value = sample_players
        mock_services['player_service'].get_player_stats_for_year.return_value = {}
        mock_services['player_service'].get_player_penalty_stats_for_year.return_value = {}
        
        # Team service
        mock_services['team_service'].calculate_team_stats_for_year.return_value = []


# Helper function for mocking file operations
def mock_open(read_data=''):
    """Create a mock for builtins.open"""
    import builtins
    from unittest.mock import mock_open as base_mock_open
    return base_mock_open(read_data=read_data)