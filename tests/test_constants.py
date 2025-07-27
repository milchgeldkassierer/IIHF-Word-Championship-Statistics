"""
Tests für die Konstanten-Definitionen

Diese Tests überprüfen, dass alle Konstanten korrekt definiert sind
und die erwarteten Werte haben nach der Magic Number Refaktorierung.
"""

import pytest
from constants import (
    TEAM_ISO_CODES,
    PRELIM_ROUNDS,
    PLAYOFF_ROUNDS,
    MAX_PRELIM_GAMES_PER_TEAM,
    PENALTY_TYPES_CHOICES,
    PENALTY_REASONS_CHOICES,
    PIM_MAP,
    POWERPLAY_PENALTY_TYPES,
    GOAL_TYPE_DISPLAY_MAP
)


class TestTeamConstants:
    """Tests für Team-bezogene Konstanten"""
    
    def test_team_iso_codes_structure(self):
        """Überprüfe die Struktur der Team ISO Codes"""
        # Überprüfe, dass es ein Dictionary ist
        assert isinstance(TEAM_ISO_CODES, dict)
        
        # Überprüfe bekannte Teams
        assert TEAM_ISO_CODES["GER"] == "de"
        assert TEAM_ISO_CODES["CAN"] == "ca"
        assert TEAM_ISO_CODES["USA"] == "us"
        assert TEAM_ISO_CODES["SWE"] == "se"
        assert TEAM_ISO_CODES["FIN"] == "fi"
        
        # Überprüfe spezielle Playoff-Codes
        assert TEAM_ISO_CODES["QF"] is None
        assert TEAM_ISO_CODES["SF"] is None
        assert TEAM_ISO_CODES["L(SF)"] is None
        assert TEAM_ISO_CODES["W(SF)"] is None
        
    def test_team_iso_codes_format(self):
        """Überprüfe das Format der Team Codes"""
        for team_code, iso_code in TEAM_ISO_CODES.items():
            # Team codes sollten 3 Buchstaben sein (außer spezielle Codes)
            if iso_code is not None:
                assert len(team_code) == 3, f"Team code {team_code} ist nicht 3 Zeichen lang"
                assert team_code.isupper(), f"Team code {team_code} ist nicht in Großbuchstaben"
                # ISO codes sollten 2 Kleinbuchstaben sein
                assert len(iso_code) == 2, f"ISO code {iso_code} für {team_code} ist nicht 2 Zeichen lang"
                assert iso_code.islower(), f"ISO code {iso_code} für {team_code} ist nicht in Kleinbuchstaben"


class TestRoundConstants:
    """Tests für Runden-Konstanten"""
    
    def test_prelim_rounds_definition(self):
        """Überprüfe die Hauptrunden-Definition"""
        assert isinstance(PRELIM_ROUNDS, list)
        assert len(PRELIM_ROUNDS) == 3
        assert "Preliminary Round" in PRELIM_ROUNDS
        assert "Group Stage" in PRELIM_ROUNDS
        assert "Round Robin" in PRELIM_ROUNDS
        
    def test_playoff_rounds_definition(self):
        """Überprüfe die Playoff-Runden-Definition"""
        assert isinstance(PLAYOFF_ROUNDS, list)
        assert len(PLAYOFF_ROUNDS) == 8
        assert "Quarterfinals" in PLAYOFF_ROUNDS
        assert "Quarterfinal" in PLAYOFF_ROUNDS
        assert "Semifinals" in PLAYOFF_ROUNDS
        assert "Semifinal" in PLAYOFF_ROUNDS
        assert "Final" in PLAYOFF_ROUNDS
        assert "Bronze Medal Game" in PLAYOFF_ROUNDS
        assert "Gold Medal Game" in PLAYOFF_ROUNDS
        assert "Playoff" in PLAYOFF_ROUNDS
        
    def test_no_overlap_between_rounds(self):
        """Stelle sicher, dass es keine Überschneidungen zwischen Runden gibt"""
        prelim_set = set(PRELIM_ROUNDS)
        playoff_set = set(PLAYOFF_ROUNDS)
        assert len(prelim_set & playoff_set) == 0, "Es gibt Überschneidungen zwischen Haupt- und Playoff-Runden"


class TestGameConstants:
    """Tests für Spiel-bezogene Konstanten"""
    
    def test_max_prelim_games_per_team(self):
        """Überprüfe die maximale Anzahl der Hauptrundenspiele"""
        assert MAX_PRELIM_GAMES_PER_TEAM == 7
        assert isinstance(MAX_PRELIM_GAMES_PER_TEAM, int)
        assert MAX_PRELIM_GAMES_PER_TEAM > 0


class TestPenaltyConstants:
    """Tests für Strafen-Konstanten"""
    
    def test_penalty_types_choices(self):
        """Überprüfe die Straftypen"""
        assert isinstance(PENALTY_TYPES_CHOICES, list)
        assert len(PENALTY_TYPES_CHOICES) == 5
        
        expected_types = [
            "2 Min",
            "2+2 Min", 
            "5 Min Disziplinar",
            "5 Min + Spieldauer",
            "10 Min Disziplinar"
        ]
        
        for penalty_type in expected_types:
            assert penalty_type in PENALTY_TYPES_CHOICES
            
    def test_penalty_reasons_choices(self):
        """Überprüfe die Strafgründe"""
        assert isinstance(PENALTY_REASONS_CHOICES, list)
        assert len(PENALTY_REASONS_CHOICES) == 18
        
        # Überprüfe einige wichtige Strafgründe
        important_reasons = [
            "Bandencheck",
            "Behinderung",
            "Cross Checking",
            "Haken",
            "Hoher Stock",
            "unsportliches Verhalten",
            "zu viele Spieler auf dem Eis"
        ]
        
        for reason in important_reasons:
            assert reason in PENALTY_REASONS_CHOICES
            
    def test_pim_map(self):
        """Überprüfe die Strafminuten-Zuordnung"""
        assert isinstance(PIM_MAP, dict)
        assert len(PIM_MAP) == 5
        
        # Überprüfe die korrekten Zuordnungen
        assert PIM_MAP["2 Min"] == 2
        assert PIM_MAP["2+2 Min"] == 4
        assert PIM_MAP["5 Min Disziplinar"] == 5
        assert PIM_MAP["5 Min + Spieldauer"] == 5
        assert PIM_MAP["10 Min Disziplinar"] == 10
        
    def test_powerplay_penalty_types(self):
        """Überprüfe welche Strafen zu Powerplay führen"""
        assert isinstance(POWERPLAY_PENALTY_TYPES, list)
        assert len(POWERPLAY_PENALTY_TYPES) == 3
        
        # Diese Strafen sollten zu Powerplay führen
        assert "2 Min" in POWERPLAY_PENALTY_TYPES
        assert "2+2 Min" in POWERPLAY_PENALTY_TYPES
        assert "5 Min + Spieldauer" in POWERPLAY_PENALTY_TYPES
        
        # Diese Strafen sollten NICHT zu Powerplay führen
        assert "5 Min Disziplinar" not in POWERPLAY_PENALTY_TYPES
        assert "10 Min Disziplinar" not in POWERPLAY_PENALTY_TYPES
        
    def test_penalty_consistency(self):
        """Überprüfe die Konsistenz zwischen verschiedenen Strafen-Konstanten"""
        # Alle Straftypen im PIM_MAP sollten auch in PENALTY_TYPES_CHOICES sein
        for penalty_type in PIM_MAP.keys():
            assert penalty_type in PENALTY_TYPES_CHOICES, f"{penalty_type} ist im PIM_MAP aber nicht in PENALTY_TYPES_CHOICES"
            
        # Alle Powerplay-Strafen sollten in PENALTY_TYPES_CHOICES sein
        for pp_type in POWERPLAY_PENALTY_TYPES:
            assert pp_type in PENALTY_TYPES_CHOICES, f"{pp_type} ist in POWERPLAY_PENALTY_TYPES aber nicht in PENALTY_TYPES_CHOICES"


class TestGoalConstants:
    """Tests für Tor-bezogene Konstanten"""
    
    def test_goal_type_display_map(self):
        """Überprüfe die Tor-Typ Anzeige-Zuordnung"""
        assert isinstance(GOAL_TYPE_DISPLAY_MAP, dict)
        assert len(GOAL_TYPE_DISPLAY_MAP) == 4
        
        # Überprüfe die korrekten Zuordnungen
        assert GOAL_TYPE_DISPLAY_MAP["REG"] == "EQ"  # Regular/Equal strength
        assert GOAL_TYPE_DISPLAY_MAP["PP"] == "PP"   # Powerplay
        assert GOAL_TYPE_DISPLAY_MAP["SH"] == "SH"   # Shorthanded
        assert GOAL_TYPE_DISPLAY_MAP["PS"] == "PS"   # Penalty shot
        
    def test_goal_type_keys_are_uppercase(self):
        """Stelle sicher, dass alle Tor-Typ Schlüssel in Großbuchstaben sind"""
        for key in GOAL_TYPE_DISPLAY_MAP.keys():
            assert key.isupper(), f"Goal type key {key} ist nicht in Großbuchstaben"
            

class TestConstantCompleteness:
    """Tests um sicherzustellen, dass alle notwendigen Konstanten definiert sind"""
    
    def test_all_penalty_types_have_pim_mapping(self):
        """Überprüfe, dass alle Straftypen eine Minuten-Zuordnung haben"""
        for penalty_type in PENALTY_TYPES_CHOICES:
            assert penalty_type in PIM_MAP, f"Straftyp '{penalty_type}' hat keine Minuten-Zuordnung im PIM_MAP"
            
    def test_constants_are_immutable_types(self):
        """Überprüfe, dass Konstanten unveränderliche Typen verwenden"""
        # Listen und Dictionaries sind technisch veränderbar, aber wir können
        # zumindest sicherstellen, dass die Werte korrekte Typen haben
        
        # PIM_MAP sollte nur Integer-Werte haben
        for penalty, minutes in PIM_MAP.items():
            assert isinstance(minutes, int), f"PIM_MAP['{penalty}'] sollte ein Integer sein"
            
        # TEAM_ISO_CODES sollte nur String oder None Werte haben
        for team, iso in TEAM_ISO_CODES.items():
            assert iso is None or isinstance(iso, str), f"TEAM_ISO_CODES['{team}'] sollte String oder None sein"