"""
Edge case and error scenario tests for PlayoffResolver.

Tests unusual conditions, error handling, and boundary cases.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
from decimal import Decimal

from utils.playoff_resolver import PlayoffResolver
from models import Game, ChampionshipYear, TeamStats
from constants import (
    PLAYOFF_ROUNDS,
    QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4,
    SEMIFINAL_1, SEMIFINAL_2, BRONZE_MEDAL, GOLD_MEDAL
)


class TestPlayoffResolverEdgeCases:
    """Test edge cases and error conditions for PlayoffResolver."""

    @pytest.fixture
    def resolver(self):
        """Create a basic resolver instance."""
        year = Mock(spec=ChampionshipYear)
        year.id = 2024
        year.fixture_path = None
        return PlayoffResolver(year)

    def test_malformed_team_codes(self, resolver):
        """Test handling of malformed team codes."""
        test_cases = [
            "",              # Empty string
            " ",             # Whitespace
            "A",             # Single character
            "ABC",           # Valid code
            "W(",            # Incomplete winner
            "W()",           # Empty game number
            "W(abc)",        # Non-numeric game number
            "L(999)",        # Non-existent game
            "seed",          # Incomplete seed
            "seed99",        # Invalid seed number
            "Group A1",      # Space in code
            "A1B1",          # Multiple positions
            None,            # None value
        ]
        
        for code in test_cases:
            # Should not raise exception
            result = resolver.get_resolved_team_code(code)
            if code is None:
                assert result is None
            else:
                assert isinstance(result, str)

    def test_circular_dependencies(self, resolver):
        """Test detection and handling of circular dependencies."""
        # Simple circular reference
        resolver.playoff_team_map = {
            "A1": "B1",
            "B1": "A1"
        }
        
        result = resolver.get_resolved_team_code("A1")
        assert result == "A1"  # Should return original to avoid infinite loop
        
        # Complex circular chain
        resolver.playoff_team_map = {
            "A1": f"W({QUARTERFINAL_1})",
            f"W({QUARTERFINAL_1})": "seed1",
            "seed1": "B1",
            "B1": "A1"
        }
        
        result = resolver.get_resolved_team_code("A1")
        assert result in ["A1", f"W({QUARTERFINAL_1})", "seed1", "B1"]  # Any in the chain

    def test_mixed_case_team_codes(self, resolver):
        """Test case sensitivity in team codes."""
        resolver.playoff_team_map = {
            "CAN": "Canada",
            "can": "canada",
            "Can": "Canada Mixed"
        }
        
        assert resolver.get_resolved_team_code("CAN") == "Canada"
        assert resolver.get_resolved_team_code("can") == "canada"
        assert resolver.get_resolved_team_code("Can") == "Canada Mixed"
        assert resolver.get_resolved_team_code("CaN") == "CaN"  # No match

    def test_unicode_and_special_characters(self, resolver):
        """Test handling of unicode and special characters."""
        resolver.playoff_team_map = {
            "A1": "Россия",         # Cyrillic
            "B1": "中国",           # Chinese
            "C1": "Česko",          # Czech with diacritics
            "D1": "日本",           # Japanese
            "E1": "Team-Name",      # Hyphen
            "F1": "Team_Name",      # Underscore
            "G1": "Team.Name",      # Dot
            "H1": "Team/Name",      # Slash
        }
        
        for key, expected in resolver.playoff_team_map.items():
            assert resolver.get_resolved_team_code(key) == expected
            assert resolver.is_code_final(expected) == True

    def test_extremely_long_dependency_chains(self, resolver):
        """Test handling of very long dependency chains."""
        # Create chain: A1 -> A2 -> A3 -> ... -> A100 -> CAN
        for i in range(1, 100):
            resolver.playoff_team_map[f"A{i}"] = f"A{i+1}"
        resolver.playoff_team_map["A100"] = "CAN"
        
        # Should resolve through entire chain
        result = resolver.get_resolved_team_code("A1")
        assert result == "CAN"
        
        # Test with max_depth limit
        result = resolver.get_resolved_team_code("A1", max_depth=50)
        assert result != "CAN"  # Should stop before reaching end

    def test_concurrent_modifications(self, resolver):
        """Test behavior when playoff_team_map is modified during resolution."""
        resolver.playoff_team_map = {
            "A1": "B1",
            "B1": "C1",
            "C1": "CAN"
        }
        
        # Simulate modification during resolution
        original_get = resolver.get_resolved_team_code
        call_count = [0]
        
        def modified_resolve(code, max_depth=100):
            call_count[0] += 1
            if call_count[0] == 2:  # Modify on second call
                resolver.playoff_team_map["B1"] = "USA"  # Change mid-resolution
            return original_get(code, max_depth)
        
        resolver.get_resolved_team_code = modified_resolve
        
        # Should handle modification gracefully
        result = resolver.get_resolved_team_code("A1")
        assert result in ["CAN", "USA"]  # Either is acceptable

    def test_memory_efficiency_with_large_maps(self, resolver):
        """Test memory efficiency with very large playoff maps."""
        # Create a large map with 10,000 entries
        large_map = {}
        for i in range(10000):
            large_map[f"T{i}"] = f"Team{i}"
            large_map[f"W({i})"] = f"T{i}"
            large_map[f"L({i})"] = f"T{i+1}"
        
        resolver.playoff_team_map = large_map
        
        # Should handle lookups efficiently
        import time
        start = time.time()
        
        # Perform 1000 lookups
        for i in range(0, 10000, 10):
            resolver.get_resolved_team_code(f"W({i})")
        
        duration = time.time() - start
        assert duration < 1.0  # Should complete in under 1 second

    def test_game_with_identical_scores(self, resolver):
        """Test handling of games with identical scores (ties)."""
        games = [
            Mock(game_number=QUARTERFINAL_1, round="Quarterfinal", team1_code="A1", 
                 team2_code="B4", team1_score=3, team2_score=3, result_type="REG")
        ]
        
        standings = {
            "Group A": [Mock(name="CAN", group="Group A", rank_in_group=1)],
            "Group B": [Mock(name="LAT", group="Group B", rank_in_group=4)]
        }
        
        resolver.resolve(games, standings)
        
        # Tied games shouldn't create W/L mappings
        assert f"W({QUARTERFINAL_1})" not in resolver.playoff_team_map
        assert f"L({QUARTERFINAL_1})" not in resolver.playoff_team_map

    def test_missing_required_fields(self, resolver):
        """Test handling of games/teams with missing required fields."""
        # Game with missing game_number
        game1 = Mock(spec=Game)
        game1.game_number = None
        game1.round = "Quarterfinal"
        game1.team1_code = "A1"
        game1.team2_code = "B4"
        game1.team1_score = 3
        game1.team2_score = 2
        
        # Game with missing round
        game2 = Mock(spec=Game)
        game2.game_number = QUARTERFINAL_2
        game2.round = None
        game2.team1_code = "B1"
        game2.team2_code = "A4"
        
        # TeamStats with missing fields
        team1 = Mock(spec=TeamStats)
        team1.name = "CAN"
        team1.group = None  # Missing group
        team1.rank_in_group = None  # Missing rank
        
        standings = {"Group A": [team1]}
        games = [game1, game2]
        
        # Should handle gracefully without crashing
        resolver.resolve(games, standings)
        assert isinstance(resolver.playoff_team_map, dict)

    def test_fixture_file_errors(self):
        """Test various fixture file error conditions."""
        year = Mock(spec=ChampionshipYear)
        year.id = 2024
        
        # Test 1: File doesn't exist
        year.fixture_path = "/non/existent/path.json"
        with patch('os.path.exists', return_value=False):
            resolver = PlayoffResolver(year)
            assert resolver.qf_game_numbers == [QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4]  # Defaults
        
        # Test 2: Invalid JSON
        year.fixture_path = "bad.json"
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', Mock(side_effect=json.JSONDecodeError("test", "doc", 0))):
                resolver = PlayoffResolver(year)
                assert resolver.sf_game_numbers == [SEMIFINAL_1, SEMIFINAL_2]  # Defaults
        
        # Test 3: IO Error
        year.fixture_path = "error.json"
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', Mock(side_effect=IOError("Permission denied"))):
                resolver = PlayoffResolver(year)
                assert resolver.host_team_codes == []  # Default empty

    def test_invalid_game_numbers_in_fixture(self):
        """Test handling of invalid game numbers in fixture data."""
        year = Mock(spec=ChampionshipYear)
        year.id = 2024
        year.fixture_path = "test.json"
        
        fixture_data = {
            "qf_game_numbers": [QUARTERFINAL_1, str(QUARTERFINAL_2), None, QUARTERFINAL_4],  # Mixed types
            "sf_game_numbers": ["SF1", "SF2"],  # Non-numeric
            "host_teams": None  # Should be list
        }
        
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(fixture_data))):
                with patch('utils.playoff_resolver.resolve_fixture_path_local', return_value="test.json"):
                    resolver = PlayoffResolver(year)
                    
                    # Should filter out invalid entries or use defaults
                    assert all(isinstance(n, int) for n in resolver.qf_game_numbers)
                    assert all(isinstance(n, int) for n in resolver.sf_game_numbers)

    def test_duplicate_team_codes_in_standings(self, resolver):
        """Test handling of duplicate team codes in standings."""
        standings = {
            "Group A": [
                Mock(name="CAN", group="Group A", rank_in_group=1),
                Mock(name="CAN", group="Group A", rank_in_group=2),  # Duplicate
            ],
            "Group B": [
                Mock(name="SWE", group="Group B", rank_in_group=1),
            ]
        }
        
        resolver.resolve([], standings)
        
        # Later entry should overwrite earlier
        assert resolver.playoff_team_map["A2"] == "CAN"

    def test_overtime_and_shootout_handling(self, resolver):
        """Test proper handling of OT and SO game results."""
        games = [
            Mock(game_number=QUARTERFINAL_1, round="Quarterfinal", team1_code="A1", 
                 team2_code="B4", team1_score=4, team2_score=3, result_type="OT"),
            Mock(game_number=QUARTERFINAL_2, round="Quarterfinal", team1_code="B1", 
                 team2_code="A4", team1_score=2, team2_score=1, result_type="SO"),
        ]
        
        standings = {
            "Group A": [
                Mock(name="CAN", group="Group A", rank_in_group=1),
                Mock(name="USA", group="Group A", rank_in_group=4),
            ],
            "Group B": [
                Mock(name="SWE", group="Group B", rank_in_group=1),
                Mock(name="LAT", group="Group B", rank_in_group=4),
            ]
        }
        
        resolver.resolve(games, standings)
        
        # OT/SO winners should still be mapped correctly
        assert resolver.playoff_team_map[f"W({QUARTERFINAL_1})"] == "CAN"
        assert resolver.playoff_team_map[f"L({QUARTERFINAL_1})"] == "LAT"
        assert resolver.playoff_team_map[f"W({QUARTERFINAL_2})"] == "SWE"
        assert resolver.playoff_team_map[f"L({QUARTERFINAL_2})"] == "USA"

    def test_playoff_games_before_preliminaries_complete(self, resolver):
        """Test handling when playoff games exist but preliminaries aren't done."""
        # Playoff game referencing teams that don't exist in standings
        games = [
            Mock(game_number=QUARTERFINAL_1, round="Quarterfinal", team1_code="A1", 
                 team2_code="B4", team1_score=3, team2_score=2)
        ]
        
        # Empty standings
        standings = {}
        
        resolver.resolve(games, standings)
        
        # Should not crash, but W/L won't be resolvable
        assert "A1" not in resolver.playoff_team_map
        assert "B4" not in resolver.playoff_team_map

    def test_game_number_conflicts(self, resolver):
        """Test handling of multiple games with same game number."""
        games = [
            Mock(game_number=QUARTERFINAL_1, round="Quarterfinal", team1_code="A1", 
                 team2_code="B4", team1_score=3, team2_score=2),
            Mock(game_number=QUARTERFINAL_1, round="Quarterfinal", team1_code="B1", 
                 team2_code="A4", team1_score=4, team2_score=1),  # Duplicate number
        ]
        
        standings = {
            "Group A": [Mock(name="CAN", group="Group A", rank_in_group=1)],
            "Group B": [Mock(name="LAT", group="Group B", rank_in_group=4)]
        }
        
        resolver.resolve(games, standings)
        
        # Last game with that number should win
        assert f"W({QUARTERFINAL_1})" in resolver.playoff_team_map

    def test_invalid_round_names(self, resolver):
        """Test handling of games with invalid round names."""
        games = [
            Mock(game_number=QUARTERFINAL_1, round="Quarter-Final", team1_code="A1",  # Wrong format
                 team2_code="B4", team1_score=3, team2_score=2),
            Mock(game_number=QUARTERFINAL_2, round="QF", team1_code="B1",  # Abbreviation
                 team2_code="A4", team1_score=4, team2_score=1),
            Mock(game_number=QUARTERFINAL_3, round=None, team1_code="A2",  # None
                 team2_code="B3", team1_score=2, team2_score=1),
        ]
        
        resolver.resolve(games, {})
        
        # Only games with valid PLAYOFF_ROUNDS should create W/L
        assert len([k for k in resolver.playoff_team_map if k.startswith("W(")]) == 0

    def test_mathematical_edge_cases(self, resolver):
        """Test edge cases with scores and calculations."""
        games = [
            Mock(game_number=QUARTERFINAL_1, round="Quarterfinal", team1_code="A1", 
                 team2_code="B4", team1_score=0, team2_score=0),  # 0-0 tie
            Mock(game_number=QUARTERFINAL_2, round="Quarterfinal", team1_code="B1", 
                 team2_code="A4", team1_score=99, team2_score=0),  # Huge score
            Mock(game_number=QUARTERFINAL_3, round="Quarterfinal", team1_code="A2", 
                 team2_code="B3", team1_score=-1, team2_score=2),  # Negative score
        ]
        
        resolver.resolve(games, {})
        
        # 0-0 shouldn't determine winner
        assert f"W({QUARTERFINAL_1})" not in resolver.playoff_team_map
        
        # Large scores should work normally
        if "B1" in resolver.playoff_team_map:
            assert resolver.playoff_team_map.get(f"W({QUARTERFINAL_2})") == resolver.playoff_team_map["B1"]
        
        # Negative scores are weird but should be handled
        if "B3" in resolver.playoff_team_map:
            assert resolver.playoff_team_map.get(f"W({QUARTERFINAL_3})") == resolver.playoff_team_map["B3"]


def mock_open(read_data=""):
    """Helper to mock file opening."""
    from unittest.mock import mock_open as base_mock_open
    return base_mock_open(read_data=read_data)