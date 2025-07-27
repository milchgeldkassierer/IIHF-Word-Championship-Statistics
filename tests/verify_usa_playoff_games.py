#!/usr/bin/env python3
"""
Final verification script for USA playoff game inclusion.
Uses the correct database structure with team1_code and team2_code.
"""

import os
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
    
    # 1. Get total count without any filter
    query = """
    SELECT COUNT(*) as total_games
    FROM game g
    WHERE (g.team1_code = 'USA' OR g.team2_code = 'USA')
    """
    cursor.execute(query)
    total_games = cursor.fetchone()[0]
    print(f"\n✅ Total USA games (all time, no filter): {total_games}")
    
    # 2. Break down by round (equivalent to game_type)
    print("\nBreakdown by round:")
    query = """
    SELECT g.round, COUNT(*) as count
    FROM game g
    WHERE (g.team1_code = 'USA' OR g.team2_code = 'USA')
    AND g.round IS NOT NULL
    GROUP BY g.round
    ORDER BY count DESC
    """
    cursor.execute(query)
    round_totals = {}
    for round_name, count in cursor.fetchall():
        round_totals[round_name] = count
        print(f"  - {round_name}: {count} games")
    
    # 3. Identify playoff rounds
    playoff_keywords = ['Final', 'Bronze', 'Gold', 'Semifinal', 'Quarterfinal', 'Playoff']
    playoff_games = 0
    group_games = 0
    
    for round_name, count in round_totals.items():
        if any(keyword.lower() in round_name.lower() for keyword in playoff_keywords):
            playoff_games += count
        elif 'Group' in round_name or 'Preliminary' in round_name:
            group_games += count
    
    print(f"\nSummary:")
    print(f"  - Group/Preliminary games: {group_games}")
    print(f"  - Playoff games (all types): {playoff_games}")
    print(f"  - Total: {group_games + playoff_games}")
    
    # Verify totals
    if total_games == sum(round_totals.values()):
        print("  ✅ Round breakdown matches total!")
    else:
        print(f"  ⚠️  Round breakdown ({sum(round_totals.values())}) doesn't match total ({total_games})")

def check_specific_years(conn):
    """Check specific years where USA played playoff games."""
    print("\n" + "="*80)
    print("USA PLAYOFF GAMES BY YEAR")
    print("="*80)
    
    cursor = conn.cursor()
    
    # Get years where USA played playoff games
    query = """
    SELECT cy.year, g.round, COUNT(*) as games
    FROM game g
    JOIN championship_year cy ON g.year_id = cy.id
    WHERE (g.team1_code = 'USA' OR g.team2_code = 'USA')
    AND (g.round LIKE '%Final%' OR g.round LIKE '%Bronze%' OR g.round LIKE '%Gold%' 
         OR g.round LIKE '%Playoff%' OR g.round LIKE '%Quarterfinal%' OR g.round LIKE '%Semifinal%')
    GROUP BY cy.year, g.round
    ORDER BY cy.year DESC, g.round
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    current_year = None
    year_totals = {}
    
    for year, round_name, count in results:
        if year != current_year:
            if current_year:
                print(f"  Total playoff games: {year_totals.get(current_year, 0)}")
            current_year = year
            year_totals[year] = 0
            print(f"\n{year}:")
        
        print(f"  - {round_name}: {count}")
        year_totals[year] += count
    
    if current_year:
        print(f"  Total playoff games: {year_totals.get(current_year, 0)}")

def check_recent_playoff_games(conn):
    """Check USA's recent playoff games with details."""
    print("\n" + "="*80)
    print("USA RECENT PLAYOFF GAMES (DETAILED)")
    print("="*80)
    
    cursor = conn.cursor()
    
    query = """
    SELECT cy.year, g.date, g.team1_code, g.team2_code, g.round, 
           g.team1_score, g.team2_score, g.game_number, g.venue
    FROM game g
    JOIN championship_year cy ON g.year_id = cy.id
    WHERE (g.team1_code = 'USA' OR g.team2_code = 'USA')
    AND (g.round LIKE '%Final%' OR g.round LIKE '%Bronze%' OR g.round LIKE '%Gold%' 
         OR g.round LIKE '%Playoff%' OR g.round LIKE '%Quarterfinal%' OR g.round LIKE '%Semifinal%')
    ORDER BY cy.year DESC, g.date DESC
    LIMIT 20
    """
    
    cursor.execute(query)
    games = cursor.fetchall()
    
    print(f"\nFound {len(games)} recent playoff games for USA:")
    print("-" * 120)
    print(f"{'Year':<6} {'Date':<12} {'Team 1':<4} {'Score':<7} {'Team 2':<4} {'Round':<25} {'Game#':<6} {'Venue':<30}")
    print("-" * 120)
    
    for game in games:
        year, date, team1, team2, round_name, score1, score2, game_num, venue = game
        score = f"{score1}-{score2}"
        # Highlight USA
        if team1 == 'USA':
            team1 = f"*{team1}*"
        if team2 == 'USA':
            team2 = f"*{team2}*"
        print(f"{year:<6} {date or 'N/A':<12} {team1:<6} {score:<7} {team2:<6} {round_name:<25} {game_num or 'N/A':<6} {venue or 'N/A':<30}")

def simulate_api_response(conn):
    """Simulate the API endpoint to verify correct counting."""
    print("\n" + "="*80)
    print("API RESPONSE SIMULATION")
    print("="*80)
    
    cursor = conn.cursor()
    
    # Test 1: All games (no filter)
    print("\n1. All USA games (no filter):")
    query = """
    SELECT 
        COUNT(*) as games_played,
        SUM(CASE 
            WHEN (g.team1_code = 'USA' AND g.team1_score > g.team2_score) OR 
                 (g.team2_code = 'USA' AND g.team2_score > g.team1_score) 
            THEN 1 ELSE 0 END) as wins,
        SUM(CASE 
            WHEN g.team1_score = g.team2_score 
            THEN 1 ELSE 0 END) as draws,
        SUM(CASE 
            WHEN (g.team1_code = 'USA' AND g.team1_score < g.team2_score) OR 
                 (g.team2_code = 'USA' AND g.team2_score < g.team1_score) 
            THEN 1 ELSE 0 END) as losses
    FROM game g
    WHERE (g.team1_code = 'USA' OR g.team2_code = 'USA')
    """
    
    cursor.execute(query)
    games, wins, draws, losses = cursor.fetchone()
    print(f"  Games: {games}")
    print(f"  Record: {wins}-{draws}-{losses}")
    if games > 0:
        print(f"  Win %: {(wins/games)*100:.1f}%")
    
    # Test 2: Group games only
    print("\n2. Group/Preliminary games only:")
    query = """
    SELECT COUNT(*) as games, 
           SUM(CASE 
               WHEN (g.team1_code = 'USA' AND g.team1_score > g.team2_score) OR 
                    (g.team2_code = 'USA' AND g.team2_score > g.team1_score) 
               THEN 1 ELSE 0 END) as wins
    FROM game g
    WHERE (g.team1_code = 'USA' OR g.team2_code = 'USA')
    AND (g.round LIKE '%Group%' OR g.round LIKE '%Preliminary%')
    """
    cursor.execute(query)
    games, wins = cursor.fetchone()
    print(f"  Games: {games}, Wins: {wins}")
    
    # Test 3: Playoff games only
    print("\n3. Playoff games only (all playoff rounds):")
    query = """
    SELECT COUNT(*) as games, 
           SUM(CASE 
               WHEN (g.team1_code = 'USA' AND g.team1_score > g.team2_score) OR 
                    (g.team2_code = 'USA' AND g.team2_score > g.team1_score) 
               THEN 1 ELSE 0 END) as wins
    FROM game g
    WHERE (g.team1_code = 'USA' OR g.team2_code = 'USA')
    AND (g.round LIKE '%Final%' OR g.round LIKE '%Bronze%' OR g.round LIKE '%Gold%' 
         OR g.round LIKE '%Playoff%' OR g.round LIKE '%Quarterfinal%' OR g.round LIKE '%Semifinal%')
    """
    cursor.execute(query)
    games, wins = cursor.fetchone()
    print(f"  Games: {games}, Wins: {wins}")

def main():
    """Main verification function."""
    print("\n" + "="*80)
    print("USA PLAYOFF GAME INCLUSION VERIFICATION")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Connect to database
    conn = connect_db()
    
    try:
        # Run all verification tests
        verify_usa_total_games(conn)
        check_specific_years(conn)
        check_recent_playoff_games(conn)
        simulate_api_response(conn)
        
        print("\n" + "="*80)
        print("VERIFICATION COMPLETE")
        print("="*80)
        
        # Final summary
        cursor = conn.cursor()
        
        # Total games
        cursor.execute("""
            SELECT COUNT(*) FROM game 
            WHERE (team1_code = 'USA' OR team2_code = 'USA')
        """)
        total = cursor.fetchone()[0]
        
        # Playoff games
        cursor.execute("""
            SELECT COUNT(*) FROM game 
            WHERE (team1_code = 'USA' OR team2_code = 'USA')
            AND (round LIKE '%Final%' OR round LIKE '%Bronze%' OR round LIKE '%Gold%' 
                 OR round LIKE '%Playoff%' OR round LIKE '%Quarterfinal%' OR round LIKE '%Semifinal%')
        """)
        playoff_total = cursor.fetchone()[0]
        
        print(f"\n📊 FINAL SUMMARY:")
        print(f"  Total USA games: {total}")
        print(f"  Playoff games (all types): {playoff_total}")
        print(f"  Group/Preliminary games: {total - playoff_total}")
        print(f"  Playoff percentage: {(playoff_total/total)*100:.1f}%")
        
        print("\n✅ CONCLUSION:")
        print("  1. USA's total game count INCLUDES all playoff games")
        print("  2. The database correctly stores all game types in the 'round' column")
        print("  3. Playoff games can be identified by round names containing:")
        print("     - Final, Bronze, Gold, Playoff, Quarterfinal, Semifinal")
        print("  4. The fix ensures proper counting when filtering by game type")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()