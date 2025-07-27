"""
Test that the StandingsCalculator refactoring maintains identical behavior
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Game, TeamStats
from services.standings_calculator_adapter import StandingsCalculator


def test_standings_calculator_matches_original_logic():
    """Test that StandingsCalculator produces same results as original logic"""
    
    # Create test games
    test_games = [
        # Regular wins
        Game(team1_code='USA', team2_code='CAN', team1_score=3, team2_score=2, 
             result_type='REG', group='Group A'),
        Game(team1_code='FIN', team2_code='SWE', team1_score=4, team2_score=1, 
             result_type='REG', group='Group B'),
        
        # Overtime games
        Game(team1_code='USA', team2_code='FIN', team1_score=3, team2_score=2, 
             result_type='OT', group='Group A'),
        Game(team1_code='CAN', team2_code='SWE', team1_score=2, team2_score=3, 
             result_type='OT', group='Group B'),
        
        # Shootout games
        Game(team1_code='USA', team2_code='SWE', team1_score=1, team2_score=2, 
             result_type='SO', group='Group A'),
        Game(team1_code='CAN', team2_code='FIN', team1_score=2, team2_score=1, 
             result_type='SO', group='Group B'),
    ]
    
    # Calculate standings using new calculator
    calculator = StandingsCalculator()
    standings = calculator.calculate_standings_from_games(test_games)
    
    # Verify USA stats (1 REG win, 1 OT win, 1 SO loss)
    usa = standings['USA']
    assert usa.gp == 3
    assert usa.w == 1
    assert usa.otw == 1
    assert usa.sow == 0
    assert usa.l == 0
    assert usa.otl == 0
    assert usa.sol == 1
    assert usa.pts == 6  # 3 + 2 + 1
    assert usa.gf == 7   # 3 + 3 + 1
    assert usa.ga == 6   # 2 + 2 + 2
    
    # Verify CAN stats (1 REG loss, 1 OT loss, 1 SO win)
    can = standings['CAN']
    assert can.gp == 3
    assert can.w == 0
    assert can.otw == 0
    assert can.sow == 1
    assert can.l == 1
    assert can.otl == 1
    assert can.sol == 0
    assert can.pts == 3  # 0 + 1 + 2
    assert can.gf == 6   # 2 + 2 + 2
    assert can.ga == 7   # 3 + 3 + 1
    
    # Verify FIN stats (1 REG loss, 1 OT loss, 1 SO loss)
    fin = standings['FIN']
    assert fin.gp == 3
    assert fin.w == 0
    assert fin.otw == 0
    assert fin.sow == 0
    assert fin.l == 1
    assert fin.otl == 1
    assert fin.sol == 1
    assert fin.pts == 2  # 0 + 1 + 1
    assert fin.gf == 4   # 1 + 2 + 1
    assert fin.ga == 9   # 4 + 3 + 2
    
    # Verify SWE stats (1 REG loss, 1 OT win, 1 SO win)
    swe = standings['SWE']
    assert swe.gp == 3
    assert swe.w == 0
    assert swe.otw == 1
    assert swe.sow == 1
    assert swe.l == 1
    assert swe.otl == 0
    assert swe.sol == 0
    assert swe.pts == 4  # 0 + 2 + 2
    assert swe.gf == 6   # 1 + 3 + 2
    assert swe.ga == 6   # 4 + 2 + 1
    
    print("✅ All tests passed! StandingsCalculator maintains identical behavior.")


if __name__ == '__main__':
    test_standings_calculator_matches_original_logic()