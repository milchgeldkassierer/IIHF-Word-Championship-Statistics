"""
Tests für Rückwärtskompatibilität nach Magic Number Refactoring

Diese Tests stellen sicher, dass die Refaktorierung keine bestehende
Funktionalität beeinträchtigt hat.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from constants import (
    MAX_PRELIM_GAMES_PER_TEAM, 
    PRELIM_ROUNDS, 
    PLAYOFF_ROUNDS,
    PIM_MAP,
    GOAL_TYPE_DISPLAY_MAP
)
from utils.playoff_resolver import PlayoffResolver
from utils.time_helpers import convert_time_to_seconds


class TestBackwardCompatibilityConstants:
    """Tests um sicherzustellen, dass die Konstanten die gleichen Werte wie vorher haben"""
    
    def test_max_prelim_games_unchanged(self):
        """Überprüfe, dass MAX_PRELIM_GAMES_PER_TEAM noch 7 ist"""
        # Der ursprüngliche Code hatte 7 als Magic Number
        assert MAX_PRELIM_GAMES_PER_TEAM == 7
        
    def test_penalty_minutes_mapping_unchanged(self):
        """Überprüfe, dass die Strafminuten-Zuordnung unverändert ist"""
        # Die ursprünglichen Werte aus dem Code
        expected_mappings = {
            "2 Min": 2,
            "2+2 Min": 4,
            "5 Min Disziplinar": 5,
            "5 Min + Spieldauer": 5,
            "10 Min Disziplinar": 10,
        }
        
        for penalty_type, minutes in expected_mappings.items():
            assert PIM_MAP[penalty_type] == minutes, f"PIM_MAP für '{penalty_type}' hat sich geändert"
            
    def test_goal_type_display_unchanged(self):
        """Überprüfe, dass die Tor-Typ-Anzeige unverändert ist"""
        expected_display = {
            "REG": "EQ",
            "PP": "PP",
            "SH": "SH",
            "PS": "PS"
        }
        
        for internal_type, display_type in expected_display.items():
            assert GOAL_TYPE_DISPLAY_MAP[internal_type] == display_type
            

class TestPlayoffResolverBackwardCompatibility:
    """Tests für die Rückwärtskompatibilität des PlayoffResolvers"""
    
    def test_playoff_resolver_api_unchanged(self):
        """Überprüfe, dass die öffentliche API des PlayoffResolvers unverändert ist"""
        year_obj = Mock()
        games = []
        
        # Der Konstruktor sollte noch die gleichen Parameter akzeptieren
        resolver = PlayoffResolver(year_obj, games)
        
        # Die Hauptmethode sollte noch existieren
        assert hasattr(resolver, 'get_resolved_code')
        assert callable(resolver.get_resolved_code)
        
        # Die anderen öffentlichen Methoden sollten existieren
        assert hasattr(resolver, 'get_all_resolutions')
        assert hasattr(resolver, 'resolve_game_participants')
        
    def test_resolve_playoff_code_function_exists(self):
        """Überprüfe, dass die Convenience-Funktion noch existiert"""
        from utils.playoff_resolver import resolve_playoff_code
        
        # Die Funktion sollte importierbar sein
        assert callable(resolve_playoff_code)
        
        # Überprüfe die Funktionssignatur
        import inspect
        sig = inspect.signature(resolve_playoff_code)
        params = list(sig.parameters.keys())
        
        # Die Funktion sollte 3 Parameter haben
        assert len(params) == 3
        assert params[0] == 'placeholder_code'
        assert params[1] == 'year_obj'
        assert params[2] == 'all_games'
        
    def test_playoff_rounds_contain_all_expected_values(self):
        """Überprüfe, dass alle erwarteten Playoff-Runden enthalten sind"""
        # Diese Runden wurden im ursprünglichen Code verwendet
        expected_rounds = [
            "Quarterfinals",
            "Quarterfinal",
            "Semifinals", 
            "Semifinal",
            "Final",
            "Bronze Medal Game",
            "Gold Medal Game",
            "Playoff"
        ]
        
        for round_name in expected_rounds:
            assert round_name in PLAYOFF_ROUNDS, f"Playoff-Runde '{round_name}' fehlt"
            
    def test_prelim_rounds_contain_expected_values(self):
        """Überprüfe, dass alle erwarteten Vorrunden enthalten sind"""
        expected_rounds = [
            "Preliminary Round",
            "Group Stage",
            "Round Robin"
        ]
        
        for round_name in expected_rounds:
            assert round_name in PRELIM_ROUNDS, f"Vorrunde '{round_name}' fehlt"


class TestTimeCalculationBackwardCompatibility:
    """Tests für die Rückwärtskompatibilität der Zeit-Berechnungen"""
    
    def test_time_conversion_produces_same_results(self):
        """Überprüfe, dass die Zeit-Konvertierung die gleichen Ergebnisse liefert"""
        # Teste mit Werten, die im ursprünglichen Code verwendet wurden
        test_cases = [
            ("12:34", 754),   # 12 * 60 + 34
            ("00:00", 0),
            ("20:00", 1200),  # 20 * 60
            ("59:59", 3599),  # 59 * 60 + 59
            ("60:00", 3600),  # 60 * 60
        ]
        
        for time_str, expected_seconds in test_cases:
            result = convert_time_to_seconds(time_str)
            assert result == expected_seconds, f"Konvertierung von '{time_str}' hat sich geändert"
            
    def test_invalid_time_still_returns_zero(self):
        """Überprüfe, dass ungültige Zeiten noch 0 zurückgeben"""
        invalid_times = [
            "",
            None,
            "invalid",
            "12-34",
            "12:34:56",
            ":30",
            "30:",
        ]
        
        for invalid_time in invalid_times:
            result = convert_time_to_seconds(invalid_time)
            assert result == 0, f"Ungültige Zeit '{invalid_time}' sollte 0 zurückgeben"


class TestIntegrationBackwardCompatibility:
    """Integrationstests für Rückwärtskompatibilität"""
    
    @patch('utils.standings._calculate_basic_prelim_standings')
    @patch('utils.playoff_mapping._build_playoff_team_map_for_year')
    def test_playoff_resolver_integration(self, mock_build_map, mock_calc_standings):
        """Teste die Integration des PlayoffResolvers mit anderen Komponenten"""
        # Mock-Daten vorbereiten
        year_obj = Mock()
        year_obj.id = 2023
        year_obj.fixture_path = None
        
        games = []
        # Vorrundenspiel
        prelim_game = Mock()
        prelim_game.round = "Preliminary Round"
        prelim_game.team1_code = "GER"
        prelim_game.team2_code = "CAN"
        prelim_game.team1_score = 3
        prelim_game.team2_score = 2
        prelim_game.game_number = 1
        prelim_game.group = "A"
        games.append(prelim_game)
        
        # Playoff-Spiel
        playoff_game = Mock()
        playoff_game.round = "Quarterfinals"
        playoff_game.team1_code = "A1"
        playoff_game.team2_code = "B4"
        playoff_game.team1_score = None
        playoff_game.team2_score = None
        playoff_game.game_number = 57
        playoff_game.group = None
        games.append(playoff_game)
        
        # Mocks konfigurieren
        mock_calc_standings.return_value = {
            "GER": Mock(group="A", rank_in_group=1),
            "CAN": Mock(group="A", rank_in_group=2),
        }
        
        mock_build_map.return_value = {
            "A1": "GER",
            "B4": "USA",
        }
        
        # PlayoffResolver verwenden
        resolver = PlayoffResolver(year_obj, games)
        
        # Teste Auflösung
        assert resolver.get_resolved_code("A1") == "GER"
        assert resolver.get_resolved_code("B4") == "USA"
        assert resolver.get_resolved_code("GER") == "GER"  # Bereits aufgelöst
        
        # Überprüfe, dass die richtigen Funktionen aufgerufen wurden
        mock_calc_standings.assert_called_once()
        mock_build_map.assert_called_once()
        
    def test_constants_used_in_filtering(self):
        """Teste, dass die Konstanten korrekt für Filterung verwendet werden"""
        # Mock-Spiele erstellen
        games = []
        
        # Verschiedene Rundentypen
        for round_name in PRELIM_ROUNDS:
            game = Mock()
            game.round = round_name
            games.append(game)
            
        for round_name in PLAYOFF_ROUNDS[:3]:  # Nur einige Playoff-Runden
            game = Mock() 
            game.round = round_name
            games.append(game)
            
        # Filtern mit Konstanten (wie im echten Code)
        prelim_games = [g for g in games if g.round in PRELIM_ROUNDS]
        playoff_games = [g for g in games if g.round in PLAYOFF_ROUNDS]
        
        assert len(prelim_games) == len(PRELIM_ROUNDS)
        assert len(playoff_games) == 3
        
        # Sicherstellen, dass die Filterung korrekt funktioniert
        for game in prelim_games:
            assert game.round not in PLAYOFF_ROUNDS
            
        for game in playoff_games:
            assert game.round not in PRELIM_ROUNDS