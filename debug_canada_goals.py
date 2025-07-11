#!/usr/bin/env python3
import sqlite3
import sys
sys.path.append('.')

from routes.records.team_tournament_records import get_most_goals_team_tournament
from routes.records.utils import get_all_resolved_games
from utils import is_code_final

def debug_most_goals_calculation():
    """Debug the most goals team tournament calculation specifically for Canada"""
    print("="*60)
    print("DEBUGGING MOST GOALS TEAM TOURNAMENT CALCULATION")
    print("="*60)
    
    # Get the current record
    most_goals_records = get_most_goals_team_tournament()
    print("Current most goals team tournament records:")
    for record in most_goals_records:
        print(f"  {record['team']}: {record['goals']} goals in {record['tournament']} ({record['year']})")
    
    print("\n" + "="*60)
    print("DETAILED CALCULATION FOR CANADA")
    print("="*60)
    
    # Replicate the calculation logic for Canada specifically
    resolved_games = get_all_resolved_games()
    
    canada_by_year = {}
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        # Check if Canada is involved
        if (team1_code == 'CAN' or team2_code == 'CAN') and year and is_code_final(team1_code) and is_code_final(team2_code):
            if year not in canada_by_year:
                canada_by_year[year] = {'goals': 0, 'games': []}
            
            can_goals = game.team1_score if team1_code == 'CAN' else game.team2_score
            canada_by_year[year]['goals'] += can_goals
            
            opp_team = team2_code if team1_code == 'CAN' else team1_code
            canada_by_year[year]['games'].append({
                'opponent': opp_team,
                'can_goals': can_goals,
                'opp_goals': game.team2_score if team1_code == 'CAN' else game.team1_score,
                'round': game.round,
                'date': game.date
            })
    
    print("Canada's goal totals by year (from records calculation):")
    for year in sorted(canada_by_year.keys(), reverse=True):
        data = canada_by_year[year]
        print(f"{year}: {data['goals']} goals in {len(data['games'])} games")
        
        # Show game breakdown for high-scoring years
        if data['goals'] >= 35:
            print(f"  Game breakdown for {year}:")
            for game in data['games']:
                print(f"    vs {game['opponent']}: {game['can_goals']} goals ({game['round']}) on {game['date']}")
    
    return canada_by_year

def main():
    # First debug the records calculation
    canada_data = debug_most_goals_calculation()
    
    print("\n" + "="*60)
    print("DIRECT DATABASE QUERY COMPARISON")
    print("="*60)
    
    # Compare with direct database query
    conn = sqlite3.connect('data/iihf_data.db')
    cursor = conn.cursor()
    
    # Check Canada total goals including playoffs for recent years
    for year in [2025, 2024, 2023, 2022]:
        # Get all goals (preliminary + playoff)
        query = """SELECT g.team1_code, g.team2_code, g.team1_score, g.team2_score, g.round 
                   FROM game g 
                   JOIN championship_year cy ON g.year_id = cy.id 
                   WHERE (g.team1_code = 'CAN' OR g.team2_code = 'CAN') 
                   AND cy.year = ? AND g.team1_score IS NOT NULL AND g.team2_score IS NOT NULL"""
        
        cursor.execute(query, (year,))
        all_games = cursor.fetchall()
        
        total_goals = 0
        game_details = []
        for game in all_games:
            team1, team2, score1, score2, round_type = game
            can_score = score1 if team1 == 'CAN' else score2
            opp_team = team2 if team1 == 'CAN' else team1
            total_goals += can_score
            game_details.append(f'{can_score} vs {opp_team} ({round_type})')
        
        records_goals = canada_data.get(year, {}).get('goals', 0)
        print(f'{year}: DB={total_goals} goals, Records={records_goals} goals')
        
        if total_goals != records_goals:
            print(f'  *** DISCREPANCY FOUND FOR {year} ***')
            print(f'  Database shows: {total_goals} goals')
            print(f'  Records calculation shows: {records_goals} goals')
            if len(game_details) <= 10:  # Only show details for reasonable number of games
                print(f'  Game breakdown: {" + ".join(game_details)}')

    conn.close()

if __name__ == '__main__':
    main()