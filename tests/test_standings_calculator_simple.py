"""
Einfacher Test für StandingsCalculator ohne Flask-Abhängigkeiten
Demonstriert die korrekte Funktionsweise der Geschäftslogik
"""

# Temporäre Model-Klassen für Tests ohne SQLAlchemy
class Team:
    def __init__(self, team_id, name, abbr, year, group_name, 
                 gp=0, w=0, otw=0, sow=0, l=0, otl=0, sol=0, 
                 pts=0, gf=0, ga=0, gd=0):
        self.team_id = team_id
        self.name = name
        self.abbr = abbr
        self.year = year
        self.group_name = group_name
        self.gp = gp
        self.w = w
        self.otw = otw
        self.sow = sow
        self.l = l
        self.otl = otl
        self.sol = sol
        self.pts = pts
        self.gf = gf
        self.ga = ga
        self.gd = gd

class Game:
    def __init__(self, game_id, year, round_name, home_team_id, away_team_id,
                 home_score, away_score, game_type):
        self.game_id = game_id
        self.year = year
        self.round_name = round_name
        self.home_team_id = home_team_id
        self.away_team_id = away_team_id
        self.home_score = home_score
        self.away_score = away_score
        self.game_type = game_type

# GameType enum Ersatz
class GameType:
    REG = "REG"
    OT = "OT"
    SO = "SO"

# Import der zu testenden Klasse mit temporärem sys.path Hack
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Temporär die Models durch unsere Dummy-Klassen ersetzen
import services.standings_calculator
services.standings_calculator.Team = Team
services.standings_calculator.Game = Game
services.standings_calculator.GameType = GameType

from services.standings_calculator import StandingsCalculator


def test_business_rules():
    """Test der Geschäftsregeln für Punkteberechnung"""
    print("=== StandingsCalculator Business Rules Test ===\n")
    
    calculator = StandingsCalculator()
    
    # Test 1: Regulärer Sieg (3 Punkte)
    print("Test 1: Regulärer Sieg")
    team1 = Team(1, "Canada", "CAN", 2024, "A")
    game1 = Game(1, 2024, "Preliminary", 1, 2, 5, 2, GameType.REG)
    calculator.update_team_stats(team1, game1, is_home=True)
    print(f"  GP={team1.gp}, W={team1.w}, L={team1.l}, PTS={team1.pts}")
    print(f"  GF={team1.gf}, GA={team1.ga}, GD={team1.gd}")
    assert team1.pts == 3, "Regulärer Sieg sollte 3 Punkte geben"
    assert team1.w == 1, "Regulärer Sieg sollte W erhöhen"
    print("  ✓ Bestanden\n")
    
    # Test 2: OT-Sieg (2 Punkte)
    print("Test 2: Overtime-Sieg")
    team2 = Team(2, "USA", "USA", 2024, "A")
    game2 = Game(2, 2024, "Preliminary", 2, 3, 4, 3, GameType.OT)
    calculator.update_team_stats(team2, game2, is_home=True)
    print(f"  GP={team2.gp}, OTW={team2.otw}, PTS={team2.pts}")
    assert team2.pts == 2, "OT-Sieg sollte 2 Punkte geben"
    assert team2.otw == 1, "OT-Sieg sollte OTW erhöhen"
    print("  ✓ Bestanden\n")
    
    # Test 3: SO-Sieg (2 Punkte)
    print("Test 3: Shootout-Sieg")
    team3 = Team(3, "Sweden", "SWE", 2024, "B")
    game3 = Game(3, 2024, "Preliminary", 3, 4, 3, 2, GameType.SO)
    calculator.update_team_stats(team3, game3, is_home=True)
    print(f"  GP={team3.gp}, SOW={team3.sow}, PTS={team3.pts}")
    assert team3.pts == 2, "SO-Sieg sollte 2 Punkte geben"
    assert team3.sow == 1, "SO-Sieg sollte SOW erhöhen"
    print("  ✓ Bestanden\n")
    
    # Test 4: Reguläre Niederlage (0 Punkte)
    print("Test 4: Reguläre Niederlage")
    team4 = Team(4, "Finland", "FIN", 2024, "B")
    game4 = Game(4, 2024, "Preliminary", 5, 4, 3, 1, GameType.REG)
    calculator.update_team_stats(team4, game4, is_home=False)
    print(f"  GP={team4.gp}, L={team4.l}, PTS={team4.pts}")
    assert team4.pts == 0, "Reguläre Niederlage sollte 0 Punkte geben"
    assert team4.l == 1, "Reguläre Niederlage sollte L erhöhen"
    print("  ✓ Bestanden\n")
    
    # Test 5: OT-Niederlage (1 Punkt)
    print("Test 5: Overtime-Niederlage")
    team5 = Team(5, "Russia", "RUS", 2024, "A")
    game5 = Game(5, 2024, "Preliminary", 6, 5, 3, 2, GameType.OT)
    calculator.update_team_stats(team5, game5, is_home=False)
    print(f"  GP={team5.gp}, OTL={team5.otl}, PTS={team5.pts}")
    assert team5.pts == 1, "OT-Niederlage sollte 1 Punkt geben"
    assert team5.otl == 1, "OT-Niederlage sollte OTL erhöhen"
    print("  ✓ Bestanden\n")
    
    # Test 6: SO-Niederlage (1 Punkt)
    print("Test 6: Shootout-Niederlage")
    team6 = Team(6, "Czech", "CZE", 2024, "B")
    game6 = Game(6, 2024, "Preliminary", 7, 6, 2, 1, GameType.SO)
    calculator.update_team_stats(team6, game6, is_home=False)
    print(f"  GP={team6.gp}, SOL={team6.sol}, PTS={team6.pts}")
    assert team6.pts == 1, "SO-Niederlage sollte 1 Punkt geben"
    assert team6.sol == 1, "SO-Niederlage sollte SOL erhöhen"
    print("  ✓ Bestanden\n")
    
    # Test 7: Akkumulierte Statistiken
    print("Test 7: Mehrere Spiele")
    team7 = Team(7, "Germany", "GER", 2024, "A")
    
    # Spiel 1: Regulärer Sieg
    game7_1 = Game(7, 2024, "Preliminary", 7, 8, 4, 1, GameType.REG)
    calculator.update_team_stats(team7, game7_1, is_home=True)
    
    # Spiel 2: OT-Niederlage
    game7_2 = Game(8, 2024, "Preliminary", 9, 7, 3, 2, GameType.OT)
    calculator.update_team_stats(team7, game7_2, is_home=False)
    
    # Spiel 3: SO-Sieg
    game7_3 = Game(9, 2024, "Preliminary", 7, 10, 2, 1, GameType.SO)
    calculator.update_team_stats(team7, game7_3, is_home=True)
    
    print(f"  Nach 3 Spielen:")
    print(f"  GP={team7.gp}, W={team7.w}, OTW={team7.otw}, SOW={team7.sow}")
    print(f"  L={team7.l}, OTL={team7.otl}, SOL={team7.sol}")
    print(f"  PTS={team7.pts} (3+1+2=6)")
    print(f"  GF={team7.gf}, GA={team7.ga}, GD={team7.gd}")
    
    assert team7.gp == 3, "Sollte 3 Spiele haben"
    assert team7.pts == 6, "Sollte 6 Punkte haben (3+1+2)"
    assert team7.gf == 8, "Sollte 8 Tore erzielt haben"
    assert team7.ga == 5, "Sollte 5 Gegentore haben"
    assert team7.gd == 3, "Tordifferenz sollte +3 sein"
    print("  ✓ Bestanden\n")
    
    # Test 8: Hilfsfunktionen
    print("Test 8: Hilfsfunktionen")
    print(f"  Team-Rekord: {calculator.get_team_record(team7)}")
    print(f"  Siegquote: {calculator.calculate_win_percentage(team7):.3f}")
    print(f"  Punktequote: {calculator.calculate_points_percentage(team7):.3f}")
    wins = calculator.get_detailed_wins(team7)
    losses = calculator.get_detailed_losses(team7)
    print(f"  Siege (W-OTW-SOW): {wins}")
    print(f"  Niederlagen (L-OTL-SOL): {losses}")
    print("  ✓ Bestanden\n")
    
    print("=== Alle Tests erfolgreich! ===")
    print("\nZusammenfassung der Geschäftsregeln:")
    print("- Regulärer Sieg: 3 Punkte, W+1")
    print("- OT/SO Sieg: 2 Punkte, OTW/SOW+1")
    print("- Reguläre Niederlage: 0 Punkte, L+1")
    print("- OT/SO Niederlage: 1 Punkt, OTL/SOL+1")
    print("- Torstatistiken werden immer aktualisiert (GF, GA, GD)")


if __name__ == "__main__":
    test_business_rules()