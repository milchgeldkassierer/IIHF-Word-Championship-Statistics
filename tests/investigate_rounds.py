#!/usr/bin/env python3
"""
Investigate all unique round names in the database.
"""

import sqlite3

def main():
    conn = sqlite3.connect('data/iihf_data.db')
    cursor = conn.cursor()
    
    print("\n" + "="*80)
    print("DATABASE ROUND INVESTIGATION")
    print("="*80)
    
    # 1. Get all unique rounds
    print("\n1. All unique round names in database:")
    cursor.execute("SELECT DISTINCT round FROM game WHERE round IS NOT NULL ORDER BY round")
    rounds = cursor.fetchall()
    for round_name in rounds:
        print(f"  - '{round_name[0]}'")
    
    # 2. Count games per round
    print("\n2. Game count per round:")
    cursor.execute("""
        SELECT round, COUNT(*) as count 
        FROM game 
        WHERE round IS NOT NULL 
        GROUP BY round 
        ORDER BY count DESC
    """)
    for round_name, count in cursor.fetchall():
        print(f"  - {round_name}: {count} games")
    
    # 3. Check years in database
    print("\n3. Years in database:")
    cursor.execute("""
        SELECT cy.year, COUNT(*) as games
        FROM game g
        JOIN championship_year cy ON g.year_id = cy.id
        GROUP BY cy.year
        ORDER BY cy.year DESC
    """)
    for year, count in cursor.fetchall():
        print(f"  - {year}: {count} games")
    
    # 4. Check if any games have high game numbers (playoff indicator)
    print("\n4. Games with high game numbers (typically playoffs are 57-64):")
    cursor.execute("""
        SELECT cy.year, g.game_number, g.team1_code, g.team2_code, g.round
        FROM game g
        JOIN championship_year cy ON g.year_id = cy.id
        WHERE g.game_number >= 57
        ORDER BY cy.year DESC, g.game_number
        LIMIT 20
    """)
    games = cursor.fetchall()
    if games:
        for year, game_num, team1, team2, round_name in games:
            print(f"  - {year} Game #{game_num}: {team1} vs {team2} ({round_name})")
    else:
        print("  No games found with game number >= 57")
    
    # 5. Sample games to see data patterns
    print("\n5. Sample of latest games:")
    cursor.execute("""
        SELECT cy.year, g.date, g.team1_code, g.team2_code, 
               g.team1_score, g.team2_score, g.round, g.game_number
        FROM game g
        JOIN championship_year cy ON g.year_id = cy.id
        ORDER BY cy.year DESC, g.date DESC
        LIMIT 10
    """)
    for game in cursor.fetchall():
        year, date, t1, t2, s1, s2, round_name, game_num = game
        print(f"  {year} {date}: {t1} {s1}-{s2} {t2} - {round_name} (Game #{game_num})")
    
    # 6. Check if USA is in the database at all
    print("\n6. USA game summary:")
    cursor.execute("""
        SELECT cy.year, COUNT(*) as games
        FROM game g
        JOIN championship_year cy ON g.year_id = cy.id
        WHERE g.team1_code = 'USA' OR g.team2_code = 'USA'
        GROUP BY cy.year
        ORDER BY cy.year DESC
    """)
    usa_years = cursor.fetchall()
    if usa_years:
        print(f"  USA games found in {len(usa_years)} years:")
        for year, count in usa_years[:5]:
            print(f"    - {year}: {count} games")
    
    conn.close()

if __name__ == "__main__":
    main()