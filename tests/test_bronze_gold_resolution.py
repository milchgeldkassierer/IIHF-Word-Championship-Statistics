"""
Test Bronze/Gold Medal placeholder resolution.

This test suite specifically tests the resolution of L(SF1), L(SF2), W(SF1), W(SF2)
placeholders that are used in Bronze and Gold medal games.
"""

import pytest
from unittest.mock import patch, MagicMock
from models import Game, ChampionshipYear, TeamStats
from utils.playoff_resolver import PlayoffResolver, resolve_playoff_code
from utils.playoff_mapping import _build_playoff_team_map_for_year
from utils.team_resolution import is_code_final, get_resolved_team_code
from constants import (
    PRELIM_ROUNDS, PLAYOFF_ROUNDS,
    QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4,
    SEMIFINAL_1, SEMIFINAL_2, BRONZE_MEDAL, GOLD_MEDAL
)


class TestBronzeGoldResolution:
    """Test suite for Bronze/Gold medal game placeholder resolution."""
    
    def setup_method(self):
        """Set up test data before each test."""
        # Create a championship year
        self.year_obj = ChampionshipYear(
            id=2024,
            name="Test Championship",
            year=2024,
            fixture_path=None  # Will mock fixture data directly
        )
        
        # Create preliminary round games for Group A and B
        self.prelim_games = []
        
        # Group A teams: CAN, FIN, CZE, SUI (ranked in this order)
        # Group B teams: SWE, USA, GER, LAT (ranked in this order)
        
        # Group A games (simplified - just enough to establish rankings)
        self.prelim_games.extend([
            Game(id=1, year_id=2024, round="Preliminary Round", group="Group A", 
                 game_number=1, team1_code="CAN", team2_code="FIN", 
                 team1_score=3, team2_score=2),
            Game(id=2, year_id=2024, round="Preliminary Round", group="Group A",
                 game_number=2, team1_code="CZE", team2_code="SUI",
                 team1_score=1, team2_score=2),
            Game(id=3, year_id=2024, round="Preliminary Round", group="Group A",
                 game_number=3, team1_code="CAN", team2_code="CZE",
                 team1_score=4, team2_score=1),
            Game(id=4, year_id=2024, round="Preliminary Round", group="Group A",
                 game_number=4, team1_code="FIN", team2_code="SUI",
                 team1_score=3, team2_score=1),
        ])
        
        # Group B games
        self.prelim_games.extend([
            Game(id=5, year_id=2024, round="Preliminary Round", group="Group B",
                 game_number=5, team1_code="SWE", team2_code="USA",
                 team1_score=4, team2_score=2),
            Game(id=6, year_id=2024, round="Preliminary Round", group="Group B",
                 game_number=6, team1_code="GER", team2_code="LAT",
                 team1_score=3, team2_score=1),
            Game(id=7, year_id=2024, round="Preliminary Round", group="Group B",
                 game_number=7, team1_code="SWE", team2_code="GER",
                 team1_score=5, team2_score=2),
            Game(id=8, year_id=2024, round="Preliminary Round", group="Group B",
                 game_number=8, team1_code="USA", team2_code="LAT",
                 team1_score=4, team2_score=1),
        ])
        
        # Quarterfinal games
        self.qf_games = [
            Game(id=57, year_id=2024, round="Quarterfinals", game_number=57,
                 team1_code="A1", team2_code="B4",
                 team1_score=None, team2_score=None),  # Will be filled in tests
            Game(id=58, year_id=2024, round="Quarterfinals", game_number=58,
                 team1_code="B1", team2_code="A4",
                 team1_score=None, team2_score=None),
            Game(id=59, year_id=2024, round="Quarterfinals", game_number=59,
                 team1_code="A2", team2_code="B3",
                 team1_score=None, team2_score=None),
            Game(id=60, year_id=2024, round="Quarterfinals", game_number=60,
                 team1_code="B2", team2_code="A3",
                 team1_score=None, team2_score=None),
        ]
        
        # Semifinal games with SF1/SF2 placeholders
        self.sf_games = [
            Game(id=SEMIFINAL_1, year_id=2024, round="Semifinals", game_number=SEMIFINAL_1,
                 team1_code=f"W({QUARTERFINAL_1})", team2_code=f"W({QUARTERFINAL_4})",
                 team1_score=None, team2_score=None),  # This is SF1
            Game(id=SEMIFINAL_2, year_id=2024, round="Semifinals", game_number=SEMIFINAL_2,
                 team1_code=f"W({QUARTERFINAL_2})", team2_code=f"W({QUARTERFINAL_3})",
                 team1_score=None, team2_score=None),  # This is SF2
        ]
        
        # Medal games
        self.medal_games = [
            Game(id=BRONZE_MEDAL, year_id=2024, round="Bronze Medal Game", game_number=BRONZE_MEDAL,
                 team1_code="L(SF1)", team2_code="L(SF2)",
                 team1_score=None, team2_score=None),
            Game(id=GOLD_MEDAL, year_id=2024, round="Gold Medal Game", game_number=GOLD_MEDAL,
                 team1_code="W(SF1)", team2_code="W(SF2)",
                 team1_score=None, team2_score=None),
        ]
        
        self.all_games = self.prelim_games + self.qf_games + self.sf_games + self.medal_games
    
    @patch('routes.year.seeding.get_custom_qf_seeding_from_db')
    def test_sf_placeholder_mapping(self, mock_custom_seeding):
        """Test that SF1 and SF2 are correctly mapped to semifinal game numbers."""
        # Mock the custom seeding function to avoid app context issues
        mock_custom_seeding.return_value = None
        
        # Set up QF results
        self.qf_games[0].team1_score = 4  # A1 (CAN) beats B4 (LAT)
        self.qf_games[0].team2_score = 1
        self.qf_games[1].team1_score = 3  # B1 (SWE) beats A4 (SUI)
        self.qf_games[1].team2_score = 2
        self.qf_games[2].team1_score = 5  # A2 (FIN) beats B3 (GER)
        self.qf_games[2].team2_score = 3
        self.qf_games[3].team1_score = 4  # B2 (USA) beats A3 (CZE)
        self.qf_games[3].team2_score = 3
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        
        # Get all resolutions to check mapping
        all_resolutions = resolver.get_all_resolutions()
        
        # Check if SF1 and SF2 are mapped to game numbers
        print("\n=== SF Placeholder Mapping ===")
        print(f"All resolutions: {all_resolutions}")
        
        # SF1 should map to SEMIFINAL_1, SF2 should map to SEMIFINAL_2
        assert all_resolutions.get('SF1') == str(SEMIFINAL_1), f"SF1 should map to {SEMIFINAL_1}, got {all_resolutions.get('SF1')}"
        assert all_resolutions.get('SF2') == str(SEMIFINAL_2), f"SF2 should map to {SEMIFINAL_2}, got {all_resolutions.get('SF2')}"
    
    @patch('routes.year.seeding.get_custom_qf_seeding_from_db')
    def test_bronze_medal_resolution_before_sf_played(self, mock_custom_seeding):
        """Test L(SF1) and L(SF2) resolution before semifinals are played."""
        # Mock the custom seeding function to avoid app context issues
        mock_custom_seeding.return_value = None
        
        # QF results set but SF not played yet
        self.qf_games[0].team1_score = 4  # A1 (CAN) beats B4 (LAT)
        self.qf_games[0].team2_score = 1
        self.qf_games[1].team1_score = 3  # B1 (SWE) beats A4 (SUI)
        self.qf_games[1].team2_score = 2
        self.qf_games[2].team1_score = 5  # A2 (FIN) beats B3 (GER)
        self.qf_games[2].team2_score = 3
        self.qf_games[3].team1_score = 4  # B2 (USA) beats A3 (CZE)
        self.qf_games[3].team2_score = 3
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        
        # Try to resolve L(SF1) and L(SF2) - should remain unresolved
        loser_sf1 = resolver.get_resolved_code("L(SF1)")
        loser_sf2 = resolver.get_resolved_code("L(SF2)")
        
        print("\n=== Before SF Played ===")
        print(f"L(SF1) resolves to: {loser_sf1}")
        print(f"L(SF2) resolves to: {loser_sf2}")
        
        # They should remain unresolved
        assert loser_sf1 == "L(SF1)", "L(SF1) should remain unresolved before SF1 is played"
        assert loser_sf2 == "L(SF2)", "L(SF2) should remain unresolved before SF2 is played"
    
    @patch('routes.year.seeding.get_custom_qf_seeding_from_db')
    def test_bronze_medal_resolution_after_sf_played(self, mock_custom_seeding):
        """Test L(SF1) and L(SF2) resolution after semifinals are played."""
        # Mock the custom seeding function to avoid app context issues
        mock_custom_seeding.return_value = None
        
        # Set up all QF results
        self.qf_games[0].team1_score = 4  # A1 (CAN) beats B4 (LAT)
        self.qf_games[0].team2_score = 1
        self.qf_games[1].team1_score = 3  # B1 (SWE) beats A4 (SUI)
        self.qf_games[1].team2_score = 2
        self.qf_games[2].team1_score = 5  # A2 (FIN) beats B3 (GER)
        self.qf_games[2].team2_score = 3
        self.qf_games[3].team1_score = 4  # B2 (USA) beats A3 (CZE)
        self.qf_games[3].team2_score = 3
        
        # Set up SF results
        self.sf_games[0].team1_score = 3  # W(57)=CAN beats W(60)=USA
        self.sf_games[0].team2_score = 2
        self.sf_games[1].team1_score = 4  # W(58)=SWE beats W(59)=FIN
        self.sf_games[1].team2_score = 3
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        
        # Check all resolutions first
        all_resolutions = resolver.get_all_resolutions()
        print("\n=== All Resolutions After SF ===")
        for key, value in sorted(all_resolutions.items()):
            print(f"{key} -> {value}")
        
        # Now resolve L(SF1) and L(SF2)
        loser_sf1 = resolver.get_resolved_code("L(SF1)")
        loser_sf2 = resolver.get_resolved_code("L(SF2)")
        
        print("\n=== After SF Played ===")
        print(f"L(SF1) resolves to: {loser_sf1}")
        print(f"L(SF2) resolves to: {loser_sf2}")
        
        # L(SF1) should be USA (loser of semifinal 1)
        # L(SF2) should be FIN (loser of semifinal 2)
        assert loser_sf1 == "USA", f"L(SF1) should resolve to USA, got {loser_sf1}"
        assert loser_sf2 == "FIN", f"L(SF2) should resolve to FIN, got {loser_sf2}"
    
    @patch('routes.year.seeding.get_custom_qf_seeding_from_db')
    def test_gold_medal_resolution_after_sf_played(self, mock_custom_seeding):
        """Test W(SF1) and W(SF2) resolution after semifinals are played."""
        # Mock the custom seeding function to avoid app context issues
        mock_custom_seeding.return_value = None
        
        # Set up all QF results
        self.qf_games[0].team1_score = 4  # A1 (CAN) beats B4 (LAT)
        self.qf_games[0].team2_score = 1
        self.qf_games[1].team1_score = 3  # B1 (SWE) beats A4 (SUI)
        self.qf_games[1].team2_score = 2
        self.qf_games[2].team1_score = 5  # A2 (FIN) beats B3 (GER)
        self.qf_games[2].team2_score = 3
        self.qf_games[3].team1_score = 4  # B2 (USA) beats A3 (CZE)
        self.qf_games[3].team2_score = 3
        
        # Set up SF results
        self.sf_games[0].team1_score = 3  # W(57)=CAN beats W(60)=USA
        self.sf_games[0].team2_score = 2
        self.sf_games[1].team1_score = 4  # W(58)=SWE beats W(59)=FIN
        self.sf_games[1].team2_score = 3
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        
        # Resolve W(SF1) and W(SF2)
        winner_sf1 = resolver.get_resolved_code("W(SF1)")
        winner_sf2 = resolver.get_resolved_code("W(SF2)")
        
        print("\n=== Gold Medal Participants ===")
        print(f"W(SF1) resolves to: {winner_sf1}")
        print(f"W(SF2) resolves to: {winner_sf2}")
        
        # W(SF1) should be CAN (winner of semifinal 1)
        # W(SF2) should be SWE (winner of semifinal 2)
        assert winner_sf1 == "CAN", f"W(SF1) should resolve to CAN, got {winner_sf1}"
        assert winner_sf2 == "SWE", f"W(SF2) should resolve to SWE, got {winner_sf2}"
    
    @patch('routes.year.seeding.get_custom_qf_seeding_from_db')
    def test_resolve_medal_game_participants(self, mock_custom_seeding):
        """Test resolving participants for both medal games."""
        # Mock the custom seeding function to avoid app context issues
        mock_custom_seeding.return_value = None
        
        # Set up complete playoff results
        self.qf_games[0].team1_score = 4  # A1 (CAN) beats B4 (LAT)
        self.qf_games[0].team2_score = 1
        self.qf_games[1].team1_score = 3  # B1 (SWE) beats A4 (SUI)
        self.qf_games[1].team2_score = 2
        self.qf_games[2].team1_score = 5  # A2 (FIN) beats B3 (GER)
        self.qf_games[2].team2_score = 3
        self.qf_games[3].team1_score = 4  # B2 (USA) beats A3 (CZE)
        self.qf_games[3].team2_score = 3
        
        # Set up SF results
        self.sf_games[0].team1_score = 3  # W(57)=CAN beats W(60)=USA
        self.sf_games[0].team2_score = 2
        self.sf_games[1].team1_score = 4  # W(58)=SWE beats W(59)=FIN
        self.sf_games[1].team2_score = 3
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        
        # Resolve Bronze Medal Game participants
        bronze_team1, bronze_team2 = resolver.resolve_game_participants(self.medal_games[0])
        print("\n=== Bronze Medal Game ===")
        print(f"Team 1: {self.medal_games[0].team1_code} -> {bronze_team1}")
        print(f"Team 2: {self.medal_games[0].team2_code} -> {bronze_team2}")
        
        # Bronze medal should be USA vs FIN
        assert bronze_team1 == "USA", f"Bronze team1 should be USA, got {bronze_team1}"
        assert bronze_team2 == "FIN", f"Bronze team2 should be FIN, got {bronze_team2}"
        
        # Resolve Gold Medal Game participants
        gold_team1, gold_team2 = resolver.resolve_game_participants(self.medal_games[1])
        print("\n=== Gold Medal Game ===")
        print(f"Team 1: {self.medal_games[1].team1_code} -> {gold_team1}")
        print(f"Team 2: {self.medal_games[1].team2_code} -> {gold_team2}")
        
        # Gold medal should be CAN vs SWE
        assert gold_team1 == "CAN", f"Gold team1 should be CAN, got {gold_team1}"
        assert gold_team2 == "SWE", f"Gold team2 should be SWE, got {gold_team2}"
    
    @patch('routes.year.seeding.get_custom_qf_seeding_from_db')
    def test_sf_placeholder_chain_resolution(self, mock_custom_seeding):
        """Test the resolution chain: L(SF1) -> L({SEMIFINAL_1}) -> Actual Team."""
        # Mock the custom seeding function to avoid app context issues
        mock_custom_seeding.return_value = None
        
        # Set up complete results
        self.qf_games[0].team1_score = 4  # A1 (CAN) beats B4 (LAT)
        self.qf_games[0].team2_score = 1
        self.qf_games[1].team1_score = 3  # B1 (SWE) beats A4 (SUI)
        self.qf_games[1].team2_score = 2
        self.qf_games[2].team1_score = 5  # A2 (FIN) beats B3 (GER)
        self.qf_games[2].team2_score = 3
        self.qf_games[3].team1_score = 4  # B2 (USA) beats A3 (CZE)
        self.qf_games[3].team2_score = 3
        
        # Set up SF results
        self.sf_games[0].team1_score = 3  # W(57)=CAN beats W(60)=USA
        self.sf_games[0].team2_score = 2
        self.sf_games[1].team1_score = 4  # W(58)=SWE beats W(59)=FIN
        self.sf_games[1].team2_score = 3
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        all_resolutions = resolver.get_all_resolutions()
        
        print("\n=== Resolution Chain ===")
        print(f"SF1 -> {all_resolutions.get('SF1', 'NOT FOUND')}")
        print(f"SF2 -> {all_resolutions.get('SF2', 'NOT FOUND')}")
        print(f"L({SEMIFINAL_1}) -> {all_resolutions.get(f'L({SEMIFINAL_1})', 'NOT FOUND')}")
        print(f"L({SEMIFINAL_2}) -> {all_resolutions.get(f'L({SEMIFINAL_2})', 'NOT FOUND')}")
        
        # Test internal resolution method to trace the chain
        # L(SF1) should resolve through: L(SF1) -> L({SEMIFINAL_1}) -> USA
        loser_sf1 = resolver.get_resolved_code("L(SF1)")
        print(f"L(SF1) final resolution: {loser_sf1}")
        
        # Verify the chain works correctly
        assert loser_sf1 == "USA", f"L(SF1) should resolve to USA through chain, got {loser_sf1}"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])