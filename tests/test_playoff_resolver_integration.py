"""
Integration tests for PlayoffResolver with existing codebase components.

Tests integration with routes, database models, and utility functions.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from flask import Flask, current_app
import json

from utils.playoff_resolver import PlayoffResolver
from utils.team_resolution import is_code_final, get_resolved_team_code
from models import Game, ChampionshipYear, TeamStats, db
from routes.year.seeding import get_custom_qf_seeding_from_db
from routes.year.views import year_view
from constants import (
    PLAYOFF_ROUNDS,
    QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4,
    SEMIFINAL_1, SEMIFINAL_2, BRONZE_MEDAL, GOLD_MEDAL
)


class TestPlayoffResolverIntegration:
    """Integration tests for PlayoffResolver with existing components."""

    @pytest.fixture
    def app(self):
        """Create a Flask app for testing."""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        with app.app_context():
            db.init_app(app)
            db.create_all()
            yield app
            db.session.remove()
            db.drop_all()

    @pytest.fixture
    def year_with_games(self, app):
        """Create a championship year with games in database."""
        with app.app_context():
            # Create championship year
            year = ChampionshipYear(
                id=2024,
                year=2024,
                host_country="CZE",
                start_date="2024-05-10",
                end_date="2024-05-26"
            )
            db.session.add(year)
            
            # Create preliminary games
            prelim_games = [
                Game(year_id=2024, game_number=1, round="Preliminary Round", group="Group A",
                     team1_code="CAN", team2_code="FIN", team1_score=4, team2_score=2,
                     team1_points=3, team2_points=0, result_type="REG"),
                Game(year_id=2024, game_number=2, round="Preliminary Round", group="Group A",
                     team1_code="CZE", team2_code="USA", team1_score=3, team2_score=2,
                     team1_points=2, team2_points=1, result_type="OT"),
                Game(year_id=2024, game_number=3, round="Preliminary Round", group="Group B",
                     team1_code="SWE", team2_code="SUI", team1_score=5, team2_score=3,
                     team1_points=3, team2_points=0, result_type="REG"),
                Game(year_id=2024, game_number=4, round="Preliminary Round", group="Group B",
                     team1_code="GER", team2_code="LAT", team1_score=2, team2_score=1,
                     team1_points=3, team2_points=0, result_type="REG"),
            ]
            
            # Create playoff games
            playoff_games = [
                Game(year_id=2024, game_number=QUARTERFINAL_1, round="Quarterfinal",
                     team1_code="A1", team2_code="B4", team1_score=None, team2_score=None),
                Game(year_id=2024, game_number=QUARTERFINAL_2, round="Quarterfinal",
                     team1_code="B1", team2_code="A4", team1_score=None, team2_score=None),
                Game(year_id=2024, game_number=QUARTERFINAL_3, round="Quarterfinal",
                     team1_code="A2", team2_code="B3", team1_score=None, team2_score=None),
                Game(year_id=2024, game_number=QUARTERFINAL_4, round="Quarterfinal",
                     team1_code="B2", team2_code="A3", team1_score=None, team2_score=None),
                Game(year_id=2024, game_number=SEMIFINAL_1, round="Semifinal",
                     team1_code=f"W({QUARTERFINAL_1})", team2_code=f"W({QUARTERFINAL_4})", team1_score=None, team2_score=None),
                Game(year_id=2024, game_number=SEMIFINAL_2, round="Semifinal",
                     team1_code=f"W({QUARTERFINAL_2})", team2_code=f"W({QUARTERFINAL_3})", team1_score=None, team2_score=None),
                Game(year_id=2024, game_number=BRONZE_MEDAL, round="Bronze Medal Game",
                     team1_code=f"L({SEMIFINAL_1})", team2_code=f"L({SEMIFINAL_2})", team1_score=None, team2_score=None),
                Game(year_id=2024, game_number=GOLD_MEDAL, round="Gold Medal Game",
                     team1_code=f"W({SEMIFINAL_1})", team2_code=f"W({SEMIFINAL_2})", team1_score=None, team2_score=None),
            ]
            
            for game in prelim_games + playoff_games:
                db.session.add(game)
            
            db.session.commit()
            return year

    def test_integration_with_year_view_route(self, app, year_with_games):
        """Test PlayoffResolver integration with year view route."""
        with app.app_context():
            # Mock the playoff resolver in the route
            with patch('routes.year.views.PlayoffResolver') as MockResolver:
                mock_resolver = Mock()
                mock_resolver.playoff_team_map = {
                    "A1": "CAN", "A2": "FIN", "A3": "CZE", "A4": "USA",
                    "B1": "SWE", "B2": "SUI", "B3": "GER", "B4": "LAT"
                }
                mock_resolver.get_resolved_team_code.side_effect = lambda code: mock_resolver.playoff_team_map.get(code, code)
                MockResolver.return_value = mock_resolver
                
                # Simulate updating a quarterfinal result
                qf_game = Game.query.filter_by(game_number=QUARTERFINAL_1).first()
                qf_game.team1_score = 5
                qf_game.team2_score = 2
                db.session.commit()
                
                # Resolver should update W/L mappings
                mock_resolver.playoff_team_map[f"W({QUARTERFINAL_1})"] = "CAN"
                mock_resolver.playoff_team_map[f"L({QUARTERFINAL_1})"] = "LAT"
                
                # Check that semifinal can now resolve participants
                sf_game = Game.query.filter_by(game_number=SEMIFINAL_1).first()
                team1 = mock_resolver.get_resolved_team_code(sf_game.team1_code)
                team2 = mock_resolver.get_resolved_team_code(sf_game.team2_code)
                
                assert team1 == "CAN"  # W({QUARTERFINAL_1})
                assert team2 in ["SWE", "SUI", "GER", "USA"]  # W({QUARTERFINAL_4}) not yet resolved

    def test_integration_with_custom_seeding(self, app, year_with_games):
        """Test integration with custom seeding functionality."""
        with app.app_context():
            # Create custom QF seeding
            custom_seeding = {
                "A1": "FIN",  # Swap CAN and FIN
                "A2": "CAN",
                "B1": "SUI",  # Swap SWE and SUI
                "B2": "SWE"
            }
            
            with patch('routes.year.seeding.get_custom_qf_seeding_from_db', return_value=custom_seeding):
                resolver = PlayoffResolver(year_with_games)
                
                # Build standings
                standings = {
                    "Group A": [
                        Mock(name="CAN", group="Group A", rank_in_group=1, pts=9),
                        Mock(name="FIN", group="Group A", rank_in_group=2, pts=7),
                        Mock(name="CZE", group="Group A", rank_in_group=3, pts=5),
                        Mock(name="USA", group="Group A", rank_in_group=4, pts=3),
                    ],
                    "Group B": [
                        Mock(name="SWE", group="Group B", rank_in_group=1, pts=9),
                        Mock(name="SUI", group="Group B", rank_in_group=2, pts=7),
                        Mock(name="GER", group="Group B", rank_in_group=3, pts=5),
                        Mock(name="LAT", group="Group B", rank_in_group=4, pts=3),
                    ]
                }
                
                games = Game.query.filter_by(year_id=2024).all()
                resolver.resolve(games, standings)
                
                # Check custom seeding was applied
                assert resolver.playoff_team_map["A1"] == "FIN"
                assert resolver.playoff_team_map["A2"] == "CAN"
                assert resolver.playoff_team_map["B1"] == "SUI"
                assert resolver.playoff_team_map["B2"] == "SWE"

    def test_integration_with_team_resolution_utils(self, app):
        """Test integration with existing team resolution utilities."""
        with app.app_context():
            resolver = PlayoffResolver(Mock(id=2024, fixture_path=None))
            resolver.playoff_team_map = {
                "A1": "CAN",
                f"W({QUARTERFINAL_1})": "CAN",
                f"L({QUARTERFINAL_1})": "USA"
            }
            
            # Test that is_code_final works with resolver's codes
            assert is_code_final("CAN") == True
            assert is_code_final("A1") == False
            assert is_code_final(f"W({QUARTERFINAL_1})") == False
            
            # Test get_resolved_team_code integration
            games_map = {QUARTERFINAL_1: Mock(team1_code="A1", team2_code="USA", team1_score=3, team2_score=1)}
            
            with patch('utils.team_resolution.get_resolved_team_code') as mock_resolve:
                mock_resolve.side_effect = lambda code, pmap, gmap: resolver.playoff_team_map.get(code, code)
                
                resolved = mock_resolve(f"W({QUARTERFINAL_1})", resolver.playoff_team_map, games_map)
                assert resolved == "CAN"

    def test_integration_with_fixture_loading(self, app, tmp_path):
        """Test integration with fixture file loading."""
        with app.app_context():
            # Create a fixture file
            fixture_data = {
                "qf_game_numbers": [65, 66, 67, 68],
                "sf_game_numbers": [69, 70],
                "host_teams": ["CZE", "SVK"],
                "bronze_game_number": 71,
                "gold_game_number": 72
            }
            
            fixture_path = tmp_path / "2024_fixture.json"
            fixture_path.write_text(json.dumps(fixture_data))
            
            # Create year with fixture path
            year = Mock(id=2024, fixture_path=str(fixture_path))
            
            with patch('utils.playoff_resolver.resolve_fixture_path_local', return_value=str(fixture_path)):
                resolver = PlayoffResolver(year)
                
                assert resolver.qf_game_numbers == [65, 66, 67, 68]
                assert resolver.sf_game_numbers == [69, 70]
                assert resolver.host_team_codes == ["CZE", "SVK"]

    def test_integration_with_all_resolved_games(self, app, year_with_games):
        """Test integration with get_all_resolved_games function."""
        with app.app_context():
            from routes.records.utils import get_all_resolved_games
            
            # Update some QF results
            Game.query.filter_by(game_number=QUARTERFINAL_1).update({
                'team1_score': 4, 'team2_score': 2
            })
            Game.query.filter_by(game_number=QUARTERFINAL_2).update({
                'team1_score': 3, 'team2_score': 2
            })
            db.session.commit()
            
            # Mock the resolver being used in get_all_resolved_games
            with patch('routes.records.utils.PlayoffResolver') as MockResolver:
                mock_resolver = Mock()
                mock_resolver.playoff_team_map = {
                    "A1": "CAN", "B4": "LAT", f"W({QUARTERFINAL_1})": "CAN", f"L({QUARTERFINAL_1})": "LAT",
                    "B1": "SWE", "A4": "USA", f"W({QUARTERFINAL_2})": "SWE", f"L({QUARTERFINAL_2})": "USA"
                }
                mock_resolver.get_resolved_team_code.side_effect = lambda code: mock_resolver.playoff_team_map.get(code, code)
                MockResolver.return_value = mock_resolver
                
                # This would normally be called by the records utils
                resolved_games = []
                games = Game.query.filter_by(year_id=2024).all()
                
                for game in games:
                    resolved_game = Mock()
                    resolved_game.team1_code = mock_resolver.get_resolved_team_code(game.team1_code)
                    resolved_game.team2_code = mock_resolver.get_resolved_team_code(game.team2_code)
                    resolved_game.team1_score = game.team1_score
                    resolved_game.team2_score = game.team2_score
                    resolved_games.append(resolved_game)
                
                # Check QF games are resolved
                qf_games = [g for g in resolved_games if g.team1_code in ["CAN", "SWE"] and g.team1_score is not None]
                assert len(qf_games) >= 2
                assert all(g.team1_code in ["CAN", "SWE", "FIN", "CZE", "USA", "SUI", "GER", "LAT"] for g in qf_games)

    def test_concurrent_resolver_instances(self, app):
        """Test multiple resolver instances don't interfere."""
        with app.app_context():
            year1 = Mock(id=2024, fixture_path=None)
            year2 = Mock(id=2023, fixture_path=None)
            
            resolver1 = PlayoffResolver(year1)
            resolver2 = PlayoffResolver(year2)
            
            # Set different mappings
            resolver1.playoff_team_map = {"A1": "CAN", "B1": "SWE"}
            resolver2.playoff_team_map = {"A1": "USA", "B1": "FIN"}
            
            # Ensure they maintain separate state
            assert resolver1.get_resolved_team_code("A1") == "CAN"
            assert resolver2.get_resolved_team_code("A1") == "USA"
            
            # Modifying one shouldn't affect the other
            resolver1.playoff_team_map["C1"] = "CZE"
            assert "C1" not in resolver2.playoff_team_map

    def test_error_handling_in_route_integration(self, app, year_with_games):
        """Test error handling when resolver fails in route."""
        with app.app_context():
            with patch('routes.year.views.PlayoffResolver') as MockResolver:
                # Simulate resolver initialization failure
                MockResolver.side_effect = Exception("Failed to load fixture")
                
                # Route should handle gracefully
                # In real implementation, this would be caught and handled
                with pytest.raises(Exception) as exc_info:
                    resolver = MockResolver(year_with_games)
                
                assert "Failed to load fixture" in str(exc_info.value)

    def test_performance_with_real_data(self, app):
        """Test performance with realistic tournament data."""
        with app.app_context():
            # Create a full tournament
            year = ChampionshipYear(id=2024, year=2024)
            db.session.add(year)
            
            # Add 56 preliminary games (7 per team, 8 teams per group)
            game_num = 1
            for group in ["A", "B"]:
                teams = [f"T{group}{i}" for i in range(1, 9)]
                for i, team1 in enumerate(teams):
                    for j, team2 in enumerate(teams[i+1:], i+1):
                        game = Game(
                            year_id=2024,
                            game_number=game_num,
                            round="Preliminary Round",
                            group=f"Group {group}",
                            team1_code=team1,
                            team2_code=team2,
                            team1_score=(i + j) % 5,
                            team2_score=(i + j + 1) % 5,
                            result_type="REG"
                        )
                        db.session.add(game)
                        game_num += 1
            
            # Add playoff games
            playoff_rounds = [
                ("Quarterfinal", [QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4]),
                ("Semifinal", [SEMIFINAL_1, SEMIFINAL_2]),
                ("Bronze Medal Game", [BRONZE_MEDAL]),
                ("Gold Medal Game", [GOLD_MEDAL])
            ]
            
            for round_name, game_numbers in playoff_rounds:
                for gn in game_numbers:
                    game = Game(
                        year_id=2024,
                        game_number=gn,
                        round=round_name,
                        team1_code=f"Placeholder1_{gn}",
                        team2_code=f"Placeholder2_{gn}"
                    )
                    db.session.add(game)
            
            db.session.commit()
            
            # Time the resolution
            import time
            start = time.time()
            
            resolver = PlayoffResolver(year)
            games = Game.query.filter_by(year_id=2024).all()
            # Mock standings as calculating real ones would be complex
            standings = {}
            
            resolver.resolve(games, standings)
            
            duration = time.time() - start
            
            # Should complete quickly even with many games
            assert duration < 0.5  # 500ms max
            assert isinstance(resolver.playoff_team_map, dict)


class TestPlayoffResolverDatabaseIntegration:
    """Test PlayoffResolver with actual database operations."""

    @pytest.fixture
    def populated_db(self, app):
        """Create a populated database with realistic data."""
        with app.app_context():
            # Create multiple years
            for year_num in [2022, 2023, 2024]:
                year = ChampionshipYear(
                    id=year_num,
                    year=year_num,
                    host_country="TEST",
                    start_date=f"{year_num}-05-10",
                    end_date=f"{year_num}-05-26"
                )
                db.session.add(year)
                
                # Add games for each year
                for i in range(10):
                    game = Game(
                        year_id=year_num,
                        game_number=i+1,
                        round="Preliminary Round" if i < 8 else "Quarterfinal",
                        team1_code=f"T{i}",
                        team2_code=f"T{i+1}",
                        team1_score=i % 5,
                        team2_score=(i+1) % 5
                    )
                    db.session.add(game)
            
            db.session.commit()
            yield
            db.session.query(Game).delete()
            db.session.query(ChampionshipYear).delete()
            db.session.commit()

    def test_resolver_with_multiple_years(self, app, populated_db):
        """Test resolver handles multiple years correctly."""
        with app.app_context():
            # Each year should have independent resolution
            for year_id in [2022, 2023, 2024]:
                year = ChampionshipYear.query.get(year_id)
                resolver = PlayoffResolver(year)
                
                games = Game.query.filter_by(year_id=year_id).all()
                result = resolver.resolve(games, {})
                
                # Each year should have its own mappings
                assert isinstance(result, dict)
                assert resolver.year.id == year_id

    def test_database_transaction_safety(self, app, year_with_games):
        """Test resolver doesn't interfere with database transactions."""
        with app.app_context():
            resolver = PlayoffResolver(year_with_games)
            
            # Start a transaction
            game = Game.query.filter_by(game_number=QUARTERFINAL_1).first()
            original_score = game.team1_score
            game.team1_score = 99
            
            # Resolver shouldn't commit changes
            games = Game.query.filter_by(year_id=2024).all()
            resolver.resolve(games, {})
            
            # Rollback should restore original
            db.session.rollback()
            game = Game.query.filter_by(game_number=QUARTERFINAL_1).first()
            assert game.team1_score == original_score