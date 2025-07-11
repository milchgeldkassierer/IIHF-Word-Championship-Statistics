#!/usr/bin/env python3
import sys
sys.path.append('.')
import os
os.environ['FLASK_ENV'] = 'development'

from app import app

def debug_canada_46_goals():
    with app.app_context():
        from routes.records.utils import get_all_resolved_games
        from utils import is_code_final
        
        print("="*60)
        print("DEBUGGING CANADA'S 46 GOALS DISCREPANCY (2025)")
        print("="*60)
        
        # Get all resolved games
        resolved_games = get_all_resolved_games()
        
        # Filter for Canada games in 2025
        canada_2025_games = []
        for resolved_game in resolved_games:
            if (resolved_game['year'] == 2025 and 
                (resolved_game['team1_code'] == 'CAN' or resolved_game['team2_code'] == 'CAN') and
                is_code_final(resolved_game['team1_code']) and is_code_final(resolved_game['team2_code'])):
                canada_2025_games.append(resolved_game)
        
        print(f"Found {len(canada_2025_games)} resolved Canada games in 2025:")
        print()
        
        total_goals_records = 0
        for i, resolved_game in enumerate(canada_2025_games, 1):
            game = resolved_game['game']
            team1_code = resolved_game['team1_code']
            team2_code = resolved_game['team2_code']
            
            can_goals = game.team1_score if team1_code == 'CAN' else game.team2_score
            total_goals_records += can_goals
            
            opp_team = team2_code if team1_code == 'CAN' else team1_code
            opp_goals = game.team2_score if team1_code == 'CAN' else game.team1_score
            
            print(f"{i:2d}. vs {opp_team}: CAN {can_goals}-{opp_goals} ({game.round}) - Game #{game.game_number} on {game.date}")
            
            # Show detailed game info
            print(f"     Database: {game.team1_code} vs {game.team2_code} = {game.team1_score}-{game.team2_score}")
            print(f"     Resolved: {team1_code} vs {team2_code}")
            if game.team1_code != team1_code or game.team2_code != team2_code:
                print(f"     *** TEAM CODE RESOLUTION OCCURRED ***")
        
        print(f"\nTotal goals from records calculation: {total_goals_records}")
        
        # Check if Canada played semifinals
        canada_semifinals = [g for g in canada_2025_games if g['game'].round == 'Semifinals']
        if canada_semifinals:
            print(f"\nCanada semifinals games found in records:")
            for sem_game in canada_semifinals:
                game = sem_game['game']
                team1_code = sem_game['team1_code']
                team2_code = sem_game['team2_code']
                can_goals = game.team1_score if team1_code == 'CAN' else game.team2_score
                opp_team = team2_code if team1_code == 'CAN' else team1_code
                opp_goals = game.team2_score if team1_code == 'CAN' else game.team1_score
                print(f"  vs {opp_team}: CAN {can_goals}-{opp_goals} - Game #{game.game_number}")
        else:
            print(f"\nNo semifinals games found for Canada in records calculation")
        
        print()
        
        # Now compare with direct database query
        print("="*60)
        print("DIRECT DATABASE COMPARISON")
        print("="*60)
        
        import sqlite3
        conn = sqlite3.connect('data/iihf_data.db')
        cursor = conn.cursor()
        
        # Get all Canada games in 2025 directly from database
        query = """SELECT g.game_number, g.date, g.team1_code, g.team2_code, g.team1_score, g.team2_score, g.round 
                   FROM game g 
                   JOIN championship_year cy ON g.year_id = cy.id 
                   WHERE (g.team1_code = 'CAN' OR g.team2_code = 'CAN') 
                   AND cy.year = 2025 AND g.team1_score IS NOT NULL AND g.team2_score IS NOT NULL
                   ORDER BY g.game_number"""
        
        cursor.execute(query)
        db_games = cursor.fetchall()
        
        print(f"Found {len(db_games)} Canada games in database for 2025:")
        print()
        
        total_goals_db = 0
        for i, game in enumerate(db_games, 1):
            game_num, date, team1, team2, score1, score2, round_type = game
            can_goals = score1 if team1 == 'CAN' else score2
            total_goals_db += can_goals
            opp_team = team2 if team1 == 'CAN' else team1
            opp_goals = score2 if team1 == 'CAN' else score1
            
            print(f"{i:2d}. vs {opp_team}: CAN {can_goals}-{opp_goals} ({round_type}) - Game #{game_num} on {date}")
        
        print(f"\nTotal goals from direct database: {total_goals_db}")
        print(f"Records calculation shows: {total_goals_records}")
        print(f"Discrepancy: {total_goals_records - total_goals_db} goals")
        
        if total_goals_records != total_goals_db:
            print("\n*** DISCREPANCY FOUND! ***")
            print(f"The records calculation is counting {total_goals_records - total_goals_db} extra goals!")
            
            # Find which games are in records but not in database
            db_game_numbers = {game[0] for game in db_games}
            records_game_numbers = {game['game'].game_number for game in canada_2025_games}
            
            extra_in_records = records_game_numbers - db_game_numbers
            extra_in_db = db_game_numbers - records_game_numbers
            
            if extra_in_records:
                print(f"Games in records but not in DB: {extra_in_records}")
            if extra_in_db:
                print(f"Games in DB but not in records: {extra_in_db}")
                
            # Check for duplicate counting
            records_game_list = [game['game'].game_number for game in canada_2025_games]
            if len(records_game_list) != len(set(records_game_list)):
                print("*** DUPLICATE GAMES FOUND IN RECORDS CALCULATION! ***")
                from collections import Counter
                duplicates = Counter(records_game_list)
                for game_num, count in duplicates.items():
                    if count > 1:
                        print(f"Game #{game_num} appears {count} times in records")
        
        conn.close()

if __name__ == '__main__':
    debug_canada_46_goals()