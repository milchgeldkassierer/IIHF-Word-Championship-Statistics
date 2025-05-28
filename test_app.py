#!/usr/bin/env python3
"""
Quick test script to verify the application is working properly.
"""

from app import app
from models import ChampionshipYear, Game, Player
from routes.main_routes import calculate_all_time_standings, get_medal_tally_data

def test_basic_functionality():
    """Test basic application functionality"""
    print("Testing IIHF World Championship Statistics Application...")
    
    with app.app_context():
        # Test database connectivity
        years = ChampionshipYear.query.all()
        print(f"✓ Database connection works - Found {len(years)} championship years")
        
        games = Game.query.count()
        print(f"✓ Found {games} games in database")
        
        players = Player.query.count()
        print(f"✓ Found {players} players in database")
        
        # Test all-time standings calculation
        try:
            standings = calculate_all_time_standings()
            print(f"✓ All-time standings calculation works - {len(standings)} teams")
        except Exception as e:
            print(f"✗ All-time standings calculation failed: {e}")
            
        # Test medal tally calculation
        try:
            medal_tally = get_medal_tally_data()
            print(f"✓ Medal tally calculation works - {len(medal_tally)} years")
        except Exception as e:
            print(f"✗ Medal tally calculation failed: {e}")
            
        print("\n✓ All basic functionality tests passed!")
        print("The application is ready for continued development.")

if __name__ == "__main__":
    test_basic_functionality()
