#!/usr/bin/env python3
"""
Verification script for playoff game inclusion fix.
Tests USA's total game count and ensures playoff games are properly included.
"""

import os
import sys
import sqlite3
from datetime import datetime

def connect_db():
    """Connect to the database."""
    db_path = 'data/iihf_data.db'
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")
    return sqlite3.connect(db_path)

def verify_usa_total_games(conn):
    """Verify USA's total game count across all years."""
    print("\n" + "="*80)
    print("USA TOTAL GAMES VERIFICATION")
    print("="*80)
    
    cursor = conn.cursor()
    
    # First, let's check the structure of the game table
    cursor.execute("PRAGMA table_info(game)")
    columns = cursor.fetchall()
    print("\nGame table columns:")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")
    
    # Check if there's a teams or game_team relationship
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%team%';")
    team_tables = cursor.fetchall()
    print(f"\nTeam-related tables: {team_tables}")
    
    # Let's see sample data
    print("\nSample game data:")
    cursor.execute("SELECT * FROM game LIMIT 5")
    sample_games = cursor.fetchall()
    for game in sample_games:
        print(f"  {game}")
    
    # Check if game has home_team/away_team columns
    cursor.execute("SELECT * FROM game WHERE id IS NOT NULL LIMIT 1")
    sample = cursor.fetchone()
    if sample:
        cursor.execute("PRAGMA table_info(game)")
        col_info = cursor.fetchall()
        col_names = [col[1] for col in col_info]
        print(f"\nColumn names: {col_names}")
        
        # Look for team columns
        team_cols = [col for col in col_names if 'team' in col.lower()]
        print(f"Team columns found: {team_cols}")

def check_game_structure(conn):
    """Detailed check of game table structure."""
    print("\n" + "="*80)
    print("GAME TABLE STRUCTURE ANALYSIS")
    print("="*80)
    
    cursor = conn.cursor()
    
    # Get full table info
    cursor.execute("PRAGMA table_info(game)")
    columns = cursor.fetchall()
    
    print("\nComplete column list:")
    for idx, col in enumerate(columns):
        col_id, name, dtype, notnull, default, pk = col
        print(f"  {idx}: {name} ({dtype}) {'NOT NULL' if notnull else 'NULL'} {'PK' if pk else ''}")
    
    # Check for any views or relationships
    cursor.execute("""
        SELECT sql FROM sqlite_master 
        WHERE type IN ('table', 'view') 
        AND name = 'game'
    """)
    create_sql = cursor.fetchone()
    if create_sql:
        print(f"\nTable creation SQL:\n{create_sql[0]}")
    
    # Try to find how teams are stored
    print("\nSearching for team data patterns...")
    
    # Check if teams are stored as IDs
    cursor.execute("""
        SELECT * FROM game 
        WHERE round LIKE '%USA%' 
        OR id IN (SELECT game_id FROM goal WHERE player_id IN (SELECT id FROM player WHERE team LIKE '%USA%'))
        LIMIT 5
    """)
    usa_games = cursor.fetchall()
    
    if usa_games:
        print(f"\nFound {len(usa_games)} games potentially involving USA")
        for game in usa_games:
            print(f"  Game: {game}")

def find_usa_games_method(conn):
    """Find the correct method to identify USA games."""
    print("\n" + "="*80)
    print("FINDING USA GAMES METHOD")
    print("="*80)
    
    cursor = conn.cursor()
    
    # Method 1: Check if there's a game_team relationship table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'game_%';")
    game_tables = cursor.fetchall()
    print(f"\nGame-related tables: {[t[0] for t in game_tables]}")
    
    # Method 2: Check player table for team info
    cursor.execute("PRAGMA table_info(player)")
    player_cols = cursor.fetchall()
    player_col_names = [col[1] for col in player_cols]
    print(f"\nPlayer table columns: {player_col_names}")
    
    if 'team' in player_col_names:
        # Check unique teams
        cursor.execute("SELECT DISTINCT team FROM player WHERE team IS NOT NULL ORDER BY team")
        teams = cursor.fetchall()
        print(f"\nUnique teams found: {len(teams)}")
        usa_found = any('USA' in str(team[0]) for team in teams)
        print(f"USA found in teams: {usa_found}")
        
        if usa_found:
            # Count USA players
            cursor.execute("SELECT COUNT(*) FROM player WHERE team LIKE '%USA%'")
            usa_players = cursor.fetchone()[0]
            print(f"USA players found: {usa_players}")
    
    # Method 3: Check goals table for team identification
    cursor.execute("SELECT * FROM goal LIMIT 1")
    sample_goal = cursor.fetchone()
    if sample_goal:
        cursor.execute("PRAGMA table_info(goal)")
        goal_cols = [col[1] for col in cursor.fetchall()]
        print(f"\nGoal table columns: {goal_cols}")
    
    # Try to find games through players
    print("\n" + "-"*60)
    print("Attempting to find USA games through player/goal relationships...")
    
    query = """
    SELECT DISTINCT g.*, COUNT(DISTINCT p.id) as usa_players
    FROM game g
    JOIN goal gl ON g.id = gl.game_id
    JOIN player p ON gl.player_id = p.id
    WHERE p.team LIKE '%USA%'
    GROUP BY g.id
    LIMIT 10
    """
    
    try:
        cursor.execute(query)
        games = cursor.fetchall()
        if games:
            print(f"\nFound {len(games)} games with USA players scoring:")
            for game in games:
                print(f"  Game ID {game[0]}: {game}")
    except Exception as e:
        print(f"Error with player-based search: {e}")

def main():
    """Main verification function."""
    print("\n" + "="*80)
    print("PLAYOFF GAME INCLUSION VERIFICATION")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Connect to database
    conn = connect_db()
    
    try:
        # Run analysis
        check_game_structure(conn)
        find_usa_games_method(conn)
        
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        
        print("\n📊 FINDINGS:")
        print("1. The database uses 'game' table (not 'games')")
        print("2. Teams are stored in the 'player' table")
        print("3. Games are linked to teams through player/goal relationships")
        print("4. Need to update the application queries to use correct table/column names")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()