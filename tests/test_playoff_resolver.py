"""
Unit-Tests für die PlayoffResolver-Klasse.

Diese Tests stellen sicher, dass die PlayoffResolver-Klasse korrekt funktioniert
und alle Edge Cases behandelt.
"""

import unittest
from unittest.mock import Mock, patch
from utils.playoff_resolver import PlayoffResolver, resolve_playoff_code
from models import ChampionshipYear, Game, TeamStats
from constants import (
    QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4,
    SEMIFINAL_1, SEMIFINAL_2, BRONZE_MEDAL, GOLD_MEDAL
)


class TestPlayoffResolver(unittest.TestCase):
    """Test-Klasse für PlayoffResolver."""
    
    def setUp(self):
        """Bereitet Test-Daten vor."""
        # Mock ChampionshipYear
        self.year_obj = Mock(spec=ChampionshipYear)
        self.year_obj.id = 1
        self.year_obj.year = 2024
        self.year_obj.fixture_path = None
        
        # Mock Games - Vorrundenspiele
        self.prelim_games = [
            self._create_game(1, "Preliminary Round", "Group A", "CAN", "FIN", 4, 2),
            self._create_game(2, "Preliminary Round", "Group A", "CAN", "SWE", 3, 2),
            self._create_game(3, "Preliminary Round", "Group A", "FIN", "SWE", 2, 1),
            self._create_game(4, "Preliminary Round", "Group B", "USA", "CZE", 5, 3),
            self._create_game(5, "Preliminary Round", "Group B", "USA", "SVK", 4, 1),
            self._create_game(6, "Preliminary Round", "Group B", "CZE", "SVK", 3, 2),
        ]
        
        # Mock Games - Playoff-Spiele
        self.playoff_games = [
            self._create_game(QUARTERFINAL_1, "Quarterfinals", None, "A1", "B2", 3, 2),  # CAN vs CZE
            self._create_game(QUARTERFINAL_2, "Quarterfinals", None, "B1", "A2", 4, 3),  # USA vs FIN
            self._create_game(SEMIFINAL_1, "Semifinals", None, f"W({QUARTERFINAL_1})", f"W({QUARTERFINAL_2})", 2, 1),  # CAN vs USA
            self._create_game(GOLD_MEDAL, "Gold Medal Game", None, f"W({SEMIFINAL_1})", f"L({SEMIFINAL_1})", 4, 2),  # CAN vs USA
        ]
        
        self.all_games = self.prelim_games + self.playoff_games
        
    def _create_game(self, game_number, round_name, group, team1, team2, score1, score2):
        """Hilfsmethode zum Erstellen von Mock-Game-Objekten."""
        game = Mock(spec=Game)
        game.game_number = game_number
        game.round = round_name
        game.group = group
        game.team1_code = team1
        game.team2_code = team2
        game.team1_score = score1
        game.team2_score = score2
        game.year_id = 1
        return game
    
    @patch('utils.playoff_resolver._calculate_basic_prelim_standings')
    @patch('utils.playoff_resolver._build_playoff_team_map_for_year')
    def test_basic_resolution(self, mock_build_map, mock_calc_standings):
        """Testet die grundlegende Auflösung von Platzhaltern."""
        # Mock die Standings-Berechnung
        mock_standings = {
            "CAN": self._create_team_stats("CAN", "Group A", 1),
            "FIN": self._create_team_stats("FIN", "Group A", 2),
            "SWE": self._create_team_stats("SWE", "Group A", 3),
            "USA": self._create_team_stats("USA", "Group B", 1),
            "CZE": self._create_team_stats("CZE", "Group B", 2),
            "SVK": self._create_team_stats("SVK", "Group B", 3),
        }
        mock_calc_standings.return_value = mock_standings
        
        # Mock die Playoff-Map
        mock_playoff_map = {
            "A1": "CAN",
            "A2": "FIN",
            "A3": "SWE",
            "B1": "USA",
            "B2": "CZE",
            "B3": "SVK",
            f"W({QUARTERFINAL_1})": "CAN",  # CAN gewinnt gegen CZE
            f"L({QUARTERFINAL_1})": "CZE",
            f"W({QUARTERFINAL_2})": "USA",  # USA gewinnt gegen FIN
            f"L({QUARTERFINAL_2})": "FIN",
            f"W({SEMIFINAL_1})": "CAN",  # CAN gewinnt gegen USA
            f"L({SEMIFINAL_1})": "USA",
        }
        mock_build_map.return_value = mock_playoff_map
        
        # Erstelle Resolver
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        
        # Teste verschiedene Auflösungen
        self.assertEqual(resolver.get_resolved_code("A1"), "CAN")
        self.assertEqual(resolver.get_resolved_code("B2"), "CZE")
        self.assertEqual(resolver.get_resolved_code(f"W({QUARTERFINAL_1})"), "CAN")
        self.assertEqual(resolver.get_resolved_code(f"L({SEMIFINAL_1})"), "USA")
        
        # Teste bereits aufgelöste Codes
        self.assertEqual(resolver.get_resolved_code("CAN"), "CAN")
        self.assertEqual(resolver.get_resolved_code("USA"), "USA")
    
    def _create_team_stats(self, name, group, rank):
        """Hilfsmethode zum Erstellen von TeamStats-Objekten."""
        stats = Mock(spec=TeamStats)
        stats.name = name
        stats.group = group
        stats.rank_in_group = rank
        return stats
    
    def test_is_code_final(self):
        """Testet die _is_code_final Methode."""
        resolver = PlayoffResolver(self.year_obj, [])
        
        # Gültige finale Codes
        self.assertTrue(resolver._is_code_final("CAN"))
        self.assertTrue(resolver._is_code_final("USA"))
        self.assertTrue(resolver._is_code_final("SWE"))
        
        # Ungültige Codes
        self.assertFalse(resolver._is_code_final("A1"))
        self.assertFalse(resolver._is_code_final(f"W({QUARTERFINAL_1})"))
        self.assertFalse(resolver._is_code_final(""))
        self.assertFalse(resolver._is_code_final(None))
        self.assertFalse(resolver._is_code_final("CA"))  # Zu kurz
        self.assertFalse(resolver._is_code_final("CANADA"))  # Zu lang
        self.assertFalse(resolver._is_code_final("can"))  # Kleinbuchstaben
    
    @patch('utils.playoff_resolver._calculate_basic_prelim_standings')
    @patch('utils.playoff_resolver._build_playoff_team_map_for_year')
    def test_edge_cases(self, mock_build_map, mock_calc_standings):
        """Testet Edge Cases und Fehlerbehandlung."""
        # Mock leere Maps
        mock_calc_standings.return_value = {}
        mock_build_map.return_value = {}
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        
        # Unbekannte Platzhalter sollten unverändert zurückgegeben werden
        self.assertEqual(resolver.get_resolved_code("X1"), "X1")
        self.assertEqual(resolver.get_resolved_code("W(99)"), "W(99)")
        
        # Leere oder None-Eingaben
        self.assertEqual(resolver.get_resolved_code(""), "")
        self.assertEqual(resolver.get_resolved_code(None), "")
    
    @patch('utils.playoff_resolver._calculate_basic_prelim_standings')
    @patch('utils.playoff_resolver._build_playoff_team_map_for_year')
    def test_resolve_game_participants(self, mock_build_map, mock_calc_standings):
        """Testet die resolve_game_participants Methode."""
        # Setup mocks
        mock_calc_standings.return_value = {}
        mock_build_map.return_value = {
            "A1": "CAN",
            "B2": "CZE",
        }
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        
        # Teste Spielauflösung
        game = Mock(spec=Game)
        game.team1_code = "A1"
        game.team2_code = "B2"
        
        team1, team2 = resolver.resolve_game_participants(game)
        self.assertEqual(team1, "CAN")
        self.assertEqual(team2, "CZE")
    
    def test_convenience_function(self):
        """Testet die resolve_playoff_code Convenience-Funktion."""
        with patch('utils.playoff_resolver.PlayoffResolver') as MockResolver:
            mock_instance = Mock()
            mock_instance.get_resolved_code.return_value = "CAN"
            MockResolver.return_value = mock_instance
            
            result = resolve_playoff_code("A1", self.year_obj, self.all_games)
            
            self.assertEqual(result, "CAN")
            MockResolver.assert_called_once_with(self.year_obj, self.all_games)
            mock_instance.get_resolved_code.assert_called_once_with("A1")
    
    @patch('utils.playoff_resolver._calculate_basic_prelim_standings')
    @patch('utils.playoff_resolver._build_playoff_team_map_for_year')
    def test_cycle_detection(self, mock_build_map, mock_calc_standings):
        """Testet die Zyklenerkennung bei zirkulären Referenzen."""
        mock_calc_standings.return_value = {}
        # Erstelle eine zirkuläre Referenz
        mock_build_map.return_value = {
            "A1": "B1",
            "B1": "A1",  # Zyklus!
        }
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        
        # Sollte den ursprünglichen Platzhalter zurückgeben statt in Endlosschleife zu geraten
        self.assertEqual(resolver.get_resolved_code("A1"), "A1")
    
    @patch('utils.playoff_resolver._calculate_basic_prelim_standings')
    @patch('utils.playoff_resolver._build_playoff_team_map_for_year')
    def test_get_all_resolutions(self, mock_build_map, mock_calc_standings):
        """Testet die get_all_resolutions Methode."""
        mock_calc_standings.return_value = {}
        test_map = {
            "A1": "CAN",
            "B1": "USA",
            f"W({QUARTERFINAL_1})": "CAN",
        }
        mock_build_map.return_value = test_map
        
        resolver = PlayoffResolver(self.year_obj, self.all_games)
        all_resolutions = resolver.get_all_resolutions()
        
        # Sollte eine Kopie der Map zurückgeben
        self.assertEqual(all_resolutions, test_map)
        self.assertIsNot(all_resolutions, test_map)  # Verschiedene Objekte

    @patch('utils.playoff_resolver._build_playoff_team_map_for_year')
    @patch('utils.playoff_resolver._calculate_basic_prelim_standings')
    def test_sf_placeholder_resolution(self, mock_calc_standings, mock_build_map):
        """Testet die Auflösung von SF1/SF2 Platzhaltern in W(SF1), L(SF1), etc."""
        mock_calc_standings.return_value = {}
        
        # Setup Games für Halbfinale
        sf_games = [
            self._create_game(SEMIFINAL_1, "Semifinals", None, "CAN", "USA", 3, 2),
            self._create_game(SEMIFINAL_2, "Semifinals", None, "FIN", "SWE", 4, 3),
        ]
        all_games_with_sf = self.prelim_games + sf_games
        
        # Mock playoff_team_map mit SF1/SF2 Mappings
        test_map = {
            "SF1": str(SEMIFINAL_1),  # SF1 maps to Semifinal 1
            "SF2": str(SEMIFINAL_2),  # SF2 maps to Semifinal 2
        }
        mock_build_map.return_value = test_map
        
        resolver = PlayoffResolver(self.year_obj, all_games_with_sf)
        
        # Test W(SF1) -> W({SEMIFINAL_1}) -> CAN
        self.assertEqual(resolver.get_resolved_code("W(SF1)"), "CAN")
        
        # Test L(SF1) -> L({SEMIFINAL_1}) -> USA
        self.assertEqual(resolver.get_resolved_code("L(SF1)"), "USA")
        
        # Test W(SF2) -> W({SEMIFINAL_2}) -> FIN
        self.assertEqual(resolver.get_resolved_code("W(SF2)"), "FIN")
        
        # Test L(SF2) -> L({SEMIFINAL_2}) -> SWE
        self.assertEqual(resolver.get_resolved_code("L(SF2)"), "SWE")


if __name__ == '__main__':
    unittest.main()