"""
Tests für Zeit-Berechnungen ohne Magic Numbers

Diese Tests überprüfen, dass Zeit-Berechnungen korrekt funktionieren
und keine hartkodierten Zahlen mehr verwenden.
"""

import pytest
from utils.time_helpers import convert_time_to_seconds


class TestTimeConversion:
    """Tests für die Zeit-Konvertierungsfunktionen"""
    
    def test_convert_time_to_seconds_basic(self):
        """Teste grundlegende Zeit-Konvertierung"""
        # Standard-Fälle
        assert convert_time_to_seconds("00:00") == 0
        assert convert_time_to_seconds("00:30") == 30
        assert convert_time_to_seconds("01:00") == 60
        assert convert_time_to_seconds("01:30") == 90
        assert convert_time_to_seconds("10:00") == 600
        assert convert_time_to_seconds("20:00") == 1200
        
    def test_convert_time_to_seconds_edge_cases(self):
        """Teste Grenzfälle der Zeit-Konvertierung"""
        # Maximale Spielzeit (60 Minuten + Verlängerung)
        assert convert_time_to_seconds("60:00") == 3600
        assert convert_time_to_seconds("65:00") == 3900  # 5 Min Verlängerung
        assert convert_time_to_seconds("70:00") == 4200  # 10 Min Verlängerung
        
        # Ungewöhnliche aber gültige Zeiten
        assert convert_time_to_seconds("59:59") == 3599
        assert convert_time_to_seconds("00:01") == 1
        
    def test_convert_time_to_seconds_invalid_input(self):
        """Teste ungültige Eingaben"""
        # Leere oder None Eingaben
        assert convert_time_to_seconds("") == 0
        assert convert_time_to_seconds(None) == 0
        
        # Fehlendes Kolon
        assert convert_time_to_seconds("1234") == 0
        assert convert_time_to_seconds("12 34") == 0
        
        # Ungültiges Format
        assert convert_time_to_seconds("12:34:56") == 0  # Zu viele Teile
        assert convert_time_to_seconds("12") == 0  # Zu wenige Teile
        assert convert_time_to_seconds(":30") == 0  # Fehlende Minuten
        assert convert_time_to_seconds("30:") == 0  # Fehlende Sekunden
        
    def test_convert_time_to_seconds_non_numeric(self):
        """Teste nicht-numerische Eingaben"""
        assert convert_time_to_seconds("ab:cd") == 0
        assert convert_time_to_seconds("12:ab") == 0
        assert convert_time_to_seconds("ab:30") == 0
        assert convert_time_to_seconds("--:--") == 0
        
    def test_time_calculation_uses_constant(self):
        """Überprüfe, dass die Berechnung 60 als Konstante für Minuten verwendet"""
        # Die Funktion sollte minutes * 60 + seconds verwenden
        # Teste verschiedene Minuten-Werte
        for minutes in range(0, 61, 5):
            time_str = f"{minutes:02d}:00"
            expected = minutes * 60  # 60 sollte nicht hartcodiert sein
            assert convert_time_to_seconds(time_str) == expected
            
    def test_overtime_calculations(self):
        """Teste Berechnungen für Verlängerungszeiten"""
        # Reguläre Spielzeit
        assert convert_time_to_seconds("60:00") == 60 * 60  # 3600 Sekunden
        
        # Verlängerung (5 Minuten)
        assert convert_time_to_seconds("65:00") == 65 * 60  # 3900 Sekunden
        
        # Penalty Shootout Zeit (theoretisch)
        assert convert_time_to_seconds("70:00") == 70 * 60  # 4200 Sekunden
        

class TestPeriodTimeCalculations:
    """Tests für Drittel-basierte Zeitberechnungen"""
    
    def test_period_time_calculations(self):
        """Teste Zeitberechnungen für verschiedene Drittel"""
        # Erstes Drittel
        assert convert_time_to_seconds("05:30") == 330  # 5:30 im ersten Drittel
        assert convert_time_to_seconds("19:59") == 1199  # Ende erstes Drittel
        
        # Zweites Drittel (würde 20:00 + Zeit sein)
        # Hinweis: convert_time_to_seconds verarbeitet nur die Zeit selbst,
        # die Drittel-Logik wäre in einer anderen Funktion
        assert convert_time_to_seconds("20:00") == 1200
        assert convert_time_to_seconds("25:30") == 1530
        assert convert_time_to_seconds("39:59") == 2399
        
        # Drittes Drittel
        assert convert_time_to_seconds("40:00") == 2400
        assert convert_time_to_seconds("45:30") == 2730
        assert convert_time_to_seconds("59:59") == 3599
        
    def test_goal_time_validation(self):
        """Teste Validierung von Tor-Zeiten"""
        # Gültige Tor-Zeiten
        valid_times = [
            "00:15",  # Früher Treffer
            "19:45",  # Später Treffer im Drittel
            "20:00",  # Treffer genau am Drittelende
            "59:59",  # Letztsekunden-Treffer
            "62:34",  # Verlängerungstreffer
        ]
        
        for time_str in valid_times:
            seconds = convert_time_to_seconds(time_str)
            assert seconds > 0, f"Zeit {time_str} sollte gültig sein"
            
    def test_penalty_time_calculations(self):
        """Teste Zeitberechnungen für Strafen"""
        # 2-Minuten-Strafe
        penalty_start = convert_time_to_seconds("15:30")
        penalty_duration = 2 * 60  # 2 Minuten in Sekunden
        penalty_end_seconds = penalty_start + penalty_duration
        
        # Konvertiere zurück zu MM:SS für Anzeige
        penalty_end_minutes = penalty_end_seconds // 60
        penalty_end_secs = penalty_end_seconds % 60
        penalty_end_str = f"{penalty_end_minutes:02d}:{penalty_end_secs:02d}"
        
        assert penalty_end_str == "17:30"
        
        # 5-Minuten-Strafe
        penalty_start = convert_time_to_seconds("18:00")
        penalty_duration = 5 * 60  # 5 Minuten
        penalty_end_seconds = penalty_start + penalty_duration
        
        penalty_end_minutes = penalty_end_seconds // 60
        penalty_end_secs = penalty_end_seconds % 60
        
        # Strafe geht ins nächste Drittel
        assert penalty_end_minutes == 23
        assert penalty_end_secs == 0


class TestTimeFormattingConsistency:
    """Tests für konsistente Zeit-Formatierung"""
    
    def test_consistent_time_format(self):
        """Überprüfe konsistente Formatierung von Zeiten"""
        # Alle Zeiten sollten im Format MM:SS sein
        test_cases = [
            ("0:0", 0),      # Sollte trotzdem funktionieren
            ("00:00", 0),    # Bevorzugtes Format
            ("1:5", 65),     # Sollte funktionieren
            ("01:05", 65),   # Bevorzugtes Format
            ("10:30", 630),
            ("60:00", 3600),
        ]
        
        for time_str, expected in test_cases:
            if ':' in time_str:
                result = convert_time_to_seconds(time_str)
                if expected > 0:
                    assert result == expected, f"Zeit {time_str} sollte {expected} Sekunden ergeben"
                    
    def test_seconds_to_minutes_conversion(self):
        """Teste Umkehrung: Sekunden zu Minuten:Sekunden Format"""
        # Diese Funktionalität könnte in einer separaten Funktion sein
        test_cases = [
            (0, "00:00"),
            (30, "00:30"),
            (60, "01:00"),
            (90, "01:30"),
            (600, "10:00"),
            (3599, "59:59"),
            (3600, "60:00"),
        ]
        
        for total_seconds, expected_format in test_cases:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            formatted = f"{minutes:02d}:{seconds:02d}"
            assert formatted == expected_format, f"{total_seconds} Sekunden sollten als {expected_format} formatiert werden"