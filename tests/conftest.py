"""
Shared test fixtures and configuration for PlayoffResolver tests.
"""

import pytest
from flask import Flask
from models import db, ChampionshipYear, Game, TeamStats
from unittest.mock import Mock
import tempfile
import os
from constants import (
    QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4,
    SEMIFINAL_1, SEMIFINAL_2, BRONZE_MEDAL, GOLD_MEDAL
)


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    # Initialize database
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create a test client for the Flask application."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test runner for the Flask application."""
    return app.test_cli_runner()


@pytest.fixture
def sample_year(app):
    """Create a sample championship year in the database."""
    with app.app_context():
        year = ChampionshipYear(
            id=2024,
            year=2024,
            host_country="CZE",
            start_date="2024-05-10",
            end_date="2024-05-26",
            num_teams=16
        )
        db.session.add(year)
        db.session.commit()
        return year


@pytest.fixture
def sample_tournament_data(app, sample_year):
    """Create a complete tournament with games and standings."""
    with app.app_context():
        # Group A teams
        group_a_teams = ["CAN", "FIN", "CZE", "USA"]
        # Group B teams  
        group_b_teams = ["SWE", "SUI", "GER", "LAT"]
        
        # Create preliminary round games
        game_number = 1
        games = []
        
        # Group A games
        for i, team1 in enumerate(group_a_teams):
            for j, team2 in enumerate(group_a_teams[i+1:], i+1):
                game = Game(
                    year_id=sample_year.id,
                    game_number=game_number,
                    round="Preliminary Round",
                    group="Group A",
                    team1_code=team1,
                    team2_code=team2,
                    team1_score=3 + (i % 3),
                    team2_score=2 + (j % 3),
                    result_type="REG",
                    team1_points=3 if (3 + (i % 3)) > (2 + (j % 3)) else 0,
                    team2_points=0 if (3 + (i % 3)) > (2 + (j % 3)) else 3
                )
                games.append(game)
                game_number += 1
        
        # Group B games
        for i, team1 in enumerate(group_b_teams):
            for j, team2 in enumerate(group_b_teams[i+1:], i+1):
                game = Game(
                    year_id=sample_year.id,
                    game_number=game_number,
                    round="Preliminary Round",
                    group="Group B",
                    team1_code=team1,
                    team2_code=team2,
                    team1_score=4 + (i % 2),
                    team2_score=3 + (j % 2),
                    result_type="REG",
                    team1_points=3 if (4 + (i % 2)) > (3 + (j % 2)) else 0,
                    team2_points=0 if (4 + (i % 2)) > (3 + (j % 2)) else 3
                )
                games.append(game)
                game_number += 1
        
        # Create playoff games (without scores initially)
        playoff_games = [
            # Quarterfinals
            Game(year_id=sample_year.id, game_number=QUARTERFINAL_1, round="Quarterfinal",
                 team1_code="A1", team2_code="B4"),
            Game(year_id=sample_year.id, game_number=QUARTERFINAL_2, round="Quarterfinal",
                 team1_code="B1", team2_code="A4"),
            Game(year_id=sample_year.id, game_number=QUARTERFINAL_3, round="Quarterfinal",
                 team1_code="A2", team2_code="B3"),
            Game(year_id=sample_year.id, game_number=QUARTERFINAL_4, round="Quarterfinal",
                 team1_code="B2", team2_code="A3"),
            # Semifinals
            Game(year_id=sample_year.id, game_number=SEMIFINAL_1, round="Semifinal",
                 team1_code=f"W({QUARTERFINAL_1})", team2_code=f"W({QUARTERFINAL_4})"),
            Game(year_id=sample_year.id, game_number=SEMIFINAL_2, round="Semifinal",
                 team1_code=f"W({QUARTERFINAL_2})", team2_code=f"W({QUARTERFINAL_3})"),
            # Medal games
            Game(year_id=sample_year.id, game_number=BRONZE_MEDAL, round="Bronze Medal Game",
                 team1_code=f"L({SEMIFINAL_1})", team2_code=f"L({SEMIFINAL_2})"),
            Game(year_id=sample_year.id, game_number=GOLD_MEDAL, round="Gold Medal Game",
                 team1_code=f"W({SEMIFINAL_1})", team2_code=f"W({SEMIFINAL_2})"),
        ]
        
        # Add all games to database
        for game in games + playoff_games:
            db.session.add(game)
        
        db.session.commit()
        
        return {
            'year': sample_year,
            'games': games + playoff_games,
            'group_a_teams': group_a_teams,
            'group_b_teams': group_b_teams
        }


@pytest.fixture
def mock_standings():
    """Create mock standings for testing."""
    def create_team_stats(name, group, rank, pts, gf, ga):
        stats = Mock(spec=TeamStats)
        stats.name = name
        stats.group = group
        stats.rank_in_group = rank
        stats.pts = pts
        stats.gf = gf
        stats.ga = ga
        stats.gd = gf - ga
        stats.gp = 7  # Games played in group
        stats.w = pts // 3  # Approximate wins
        stats.l = 7 - (pts // 3)  # Approximate losses
        return stats
    
    standings = {
        "Group A": [
            create_team_stats("CAN", "Group A", 1, 18, 25, 10),
            create_team_stats("FIN", "Group A", 2, 15, 22, 15),
            create_team_stats("CZE", "Group A", 3, 12, 18, 18),
            create_team_stats("USA", "Group A", 4, 9, 15, 20),
        ],
        "Group B": [
            create_team_stats("SWE", "Group B", 1, 19, 28, 12),
            create_team_stats("SUI", "Group B", 2, 14, 20, 16),
            create_team_stats("GER", "Group B", 3, 11, 17, 19),
            create_team_stats("LAT", "Group B", 4, 7, 13, 23),
        ]
    }
    return standings


@pytest.fixture
def temp_fixture_file():
    """Create a temporary fixture file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        import json
        fixture_data = {
            "qf_game_numbers": [QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4],
            "sf_game_numbers": [SEMIFINAL_1, SEMIFINAL_2],
            "bronze_game_number": BRONZE_MEDAL,
            "gold_game_number": GOLD_MEDAL,
            "host_teams": ["CZE"]
        }
        json.dump(fixture_data, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def mock_flask_app_context():
    """Create a mock Flask app context for testing utilities."""
    app = Mock()
    app.root_path = "/test/app/path"
    app.static_folder = "static"
    return app


# Helper functions for tests
def create_game(game_number, round_name, team1_code, team2_code, 
                team1_score=None, team2_score=None, year_id=2024):
    """Helper to create a game object."""
    game = Game(
        year_id=year_id,
        game_number=game_number,
        round=round_name,
        team1_code=team1_code,
        team2_code=team2_code,
        team1_score=team1_score,
        team2_score=team2_score
    )
    if team1_score is not None and team2_score is not None:
        if team1_score > team2_score:
            game.team1_points = 3
            game.team2_points = 0
        elif team2_score > team1_score:
            game.team1_points = 0
            game.team2_points = 3
        else:
            game.team1_points = 1
            game.team2_points = 1
        game.result_type = "REG"
    return game


def assert_playoff_mapping(resolver, expected_mappings):
    """Helper to assert multiple playoff mappings at once."""
    for key, expected_value in expected_mappings.items():
        actual_value = resolver.playoff_team_map.get(key)
        assert actual_value == expected_value, \
            f"Expected {key} to map to {expected_value}, but got {actual_value}"


def simulate_tournament_progression(db_session, games, results):
    """Helper to simulate tournament progression by updating game scores."""
    for game_num, (score1, score2) in results.items():
        game = next((g for g in games if g.game_number == game_num), None)
        if game:
            game.team1_score = score1
            game.team2_score = score2
            game.result_type = "REG"
            if score1 > score2:
                game.team1_points = 3
                game.team2_points = 0
            else:
                game.team1_points = 0
                game.team2_points = 3
    db_session.commit()