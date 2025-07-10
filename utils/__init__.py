# Main utils package - provides backwards compatibility with original utils.py

# Import all functions from submodules for backwards compatibility
from .team_resolution import (
    is_code_final,
    get_resolved_team_code,
    resolve_game_participants,
    resolve_fixture_path_local
)

from .standings import (
    _calculate_basic_prelim_standings,
    _apply_head_to_head_tiebreaker,
    _sort_teams_by_head_to_head,
    _sort_two_teams_by_head_to_head,
    _sort_multiple_teams_by_head_to_head
)

from .playoff_mapping import (
    _build_playoff_team_map_for_year,
)

from .data_validation import (
    check_game_data_consistency,
    check_powerplay_penalty_consistency,
    get_penalty_duration_minutes,
    analyze_powerplay_situation,
    get_expected_goal_types,
    describe_powerplay_situation,
    calculate_expected_points
)

from .time_helpers import (
    convert_time_to_seconds,
)

# Special handling for the team_vs_team_view function which has different imports
# We'll keep this in the main utils for now since it has complex dependencies
import re
import os
import json
from typing import Dict, List, Tuple, Set, Optional

def team_vs_team_view(team1, team2):
    try:
        team1 = team1.upper()
        team2 = team2.upper()
    except AttributeError:
        return {"error": "Ungültige Team-Namen"}

    # Import main_routes functions for correct team resolution
    from routes.main_routes import calculate_complete_final_ranking, get_medal_tally_data

    # Get medal tally data with correct team resolution
    medal_data = get_medal_tally_data()
    
    # Create medal games lookup by year for correctly resolved teams
    medal_games_by_year = {}
    for medal_entry in medal_data:
        year = medal_entry.year_obj.year
        if medal_entry.gold and medal_entry.silver:
            # Final game
            medal_games_by_year.setdefault(year, []).append({
                'round': 'Finale',
                'team1': medal_entry.gold,
                'team2': medal_entry.silver,
                'result': '4-1',  # Default, will be updated from actual game
                'game_type': 'Gold Medal Game'
            })
        if medal_entry.bronze and medal_entry.fourth:
            # Bronze game  
            medal_games_by_year.setdefault(year, []).append({
                'round': 'Spiel um Platz 3',
                'team1': medal_entry.bronze,
                'team2': medal_entry.fourth,
                'result': '4-2',  # Default, will be updated from actual game
                'game_type': 'Bronze Medal Game'
            })

    # Get all regular games from database
    from models import Year, Game
    from flask import url_for
    
    # Define GameDisplay class locally since it's used here
    class GameDisplay:
        def __init__(self, year, date, round, location, team1_score, team2_score, result, typ, stats_link):
            self.year = year
            self.date = date
            self.round = round
            self.location = location
            self.team1_score = team1_score
            self.team2_score = team2_score
            self.result = result
            self.typ = typ
            self.stats_link = stats_link
    
    all_years = Year.query.all()
    all_games = Game.query.all()
    
    games_data = []
    
    # Process all years to get correct game results
    for year_obj in all_years:
        year = year_obj.year
        games_this_year = [g for g in all_games if g.year_id == year_obj.id]
        
        # Get medal games for this year with correct scores
        medal_games = [g for g in games_this_year if g.round in ['Gold Medal Game', 'Bronze Medal Game']]
        
        for medal_game in medal_games:
            if (medal_game.team1_score is not None and medal_game.team2_score is not None):
                # Use calculate_complete_final_ranking to get correctly resolved teams
                final_ranking = calculate_complete_final_ranking(year_obj, games_this_year, {}, year_obj)
                
                # Map the resolved teams to the medal game
                if medal_game.round == 'Gold Medal Game':
                    resolved_team1 = final_ranking.get(1)  # Gold
                    resolved_team2 = final_ranking.get(2)  # Silver
                    round_name = 'Finale'
                elif medal_game.round == 'Bronze Medal Game':
                    resolved_team1 = final_ranking.get(3)  # Bronze
                    resolved_team2 = final_ranking.get(4)  # Fourth
                    round_name = 'Spiel um Platz 3'
                else:
                    continue
                
                # Check if this game involves our target teams
                if ((resolved_team1 == team1 and resolved_team2 == team2) or 
                    (resolved_team1 == team2 and resolved_team2 == team1)):
                    
                    # Determine which team is team1 and team2 based on resolved order
                    if resolved_team1 == team1:
                        team1_score = medal_game.team1_score
                        team2_score = medal_game.team2_score
                        typ = medal_game.result_type or 'Regular'
                    else:
                        team1_score = medal_game.team2_score 
                        team2_score = medal_game.team1_score
                        typ = medal_game.result_type or 'Regular'
                    
                    games_data.append(GameDisplay(
                        year=year,
                        date=medal_game.date,
                        round=round_name,
                        location=medal_game.location,
                        team1_score=team1_score,
                        team2_score=team2_score,
                        result=f"{team1_score}:{team2_score}",
                        typ=typ,
                        stats_link=None
                    ))
        
        # Process regular games
        for game in games_this_year:
            if game.round not in ['Gold Medal Game', 'Bronze Medal Game']:
                if ((game.team1_code == team1 and game.team2_code == team2) or 
                    (game.team1_code == team2 and game.team2_code == team1)):
                    
                    if game.team1_code == team1:
                        team1_score = game.team1_score
                        team2_score = game.team2_score
                    else:
                        team1_score = game.team2_score 
                        team2_score = game.team1_score
                    
                    if team1_score is not None and team2_score is not None:
                        result = f"{team1_score}:{team2_score}"
                        typ = game.result_type or 'Regular'
                        
                        stats_link = None
                        if game.game_number:
                            stats_link = url_for('main.game_stats', 
                                                year=year, 
                                                game_number=game.game_number)
                        
                        games_data.append(GameDisplay(
                            year=year,
                            date=game.date,
                            round=game.round,
                            location=game.location,
                            team1_score=team1_score,
                            team2_score=team2_score,
                            result=result,
                            typ=typ,
                            stats_link=stats_link
                        ))

    # Sort by year (newest first)
    games_data.sort(key=lambda x: x.year, reverse=True)
    
    # Calculate statistics
    team1_wins = len([g for g in games_data if g.team1_score > g.team2_score])
    team2_wins = len([g for g in games_data if g.team2_score > g.team1_score])
    total_games = len(games_data)
    
    statistics = {
        'total_games': total_games,
        f'{team1}_wins': team1_wins,
        f'{team2}_wins': team2_wins,
        'series_record': f"{team1_wins}-{team2_wins}"
    }
    
    return {
        'team1': team1,
        'team2': team2,
        'games': games_data,
        'statistics': statistics
    }

# Export all for backwards compatibility
__all__ = [
    # Team resolution
    'is_code_final',
    'get_resolved_team_code', 
    'resolve_game_participants',
    'resolve_fixture_path_local',
    
    # Standings
    '_calculate_basic_prelim_standings',
    '_apply_head_to_head_tiebreaker', 
    '_sort_teams_by_head_to_head',
    '_sort_two_teams_by_head_to_head',
    '_sort_multiple_teams_by_head_to_head',
    
    # Playoff mapping
    '_build_playoff_team_map_for_year',
    
    # Data validation
    'check_game_data_consistency',
    'check_powerplay_penalty_consistency',
    'get_penalty_duration_minutes',
    'analyze_powerplay_situation',
    'get_expected_goal_types',
    'describe_powerplay_situation', 
    'calculate_expected_points',
    
    # Time helpers
    'convert_time_to_seconds',
    
    # Special functions
    'team_vs_team_view'
]