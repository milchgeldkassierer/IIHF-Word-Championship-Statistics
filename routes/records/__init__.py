from flask import Blueprint, render_template
from constants import TEAM_ISO_CODES

# Import all record functions from submodules
from .streaks import (
    get_longest_win_streak,
    get_longest_loss_streak,
    get_longest_scoring_streak,
    get_longest_shutout_streak,
    get_longest_goalless_streak
)

from .game_records import (
    get_highest_victory,
    get_most_goals_game,
    get_most_frequent_matchup
)

from .goal_records import (
    get_fastest_goal,
    get_fastest_hattrick
)

from .tournament_records import (
    get_most_consecutive_tournament_wins,
    get_most_final_appearances,
    get_record_champion,
    get_tournament_with_most_goals,
    get_tournament_with_least_goals,
    get_tournament_with_most_penalty_minutes
)

from .team_tournament_records import (
    get_most_goals_team_tournament,
    get_fewest_goals_against_tournament,
    get_most_shutouts_tournament
)

from .player_records import (
    get_most_scorers_tournament,
    get_most_goals_player_tournament,
    get_most_assists_player_tournament,
    get_most_penalty_minutes_tournament
)

# Import utilities for external access
from .utils import get_all_resolved_games, get_resolved_team_info

# Create the blueprint
record_bp = Blueprint('record_bp', __name__)


@record_bp.route('/records')
def records_view():
    """Rekorde-Seite mit verschiedenen Rekordkategorien"""
    
    longest_win_streak = get_longest_win_streak()
    longest_loss_streak = get_longest_loss_streak()
    longest_scoring_streak = get_longest_scoring_streak()
    longest_shutout_streak = get_longest_shutout_streak()
    longest_goalless_streak = get_longest_goalless_streak()
    
    highest_victory = get_highest_victory()
    most_goals_game = get_most_goals_game()
    
    fastest_goal = get_fastest_goal()
    fastest_hattrick = get_fastest_hattrick()
    
    most_consecutive_tournament_wins = get_most_consecutive_tournament_wins()
    most_final_appearances = get_most_final_appearances()
    record_champion = get_record_champion()
    
    tournament_most_goals = get_tournament_with_most_goals()
    tournament_least_goals = get_tournament_with_least_goals()
    tournament_most_penalty_minutes = get_tournament_with_most_penalty_minutes()
    
    most_goals_team_tournament = get_most_goals_team_tournament()
    fewest_goals_against_tournament = get_fewest_goals_against_tournament()
    most_shutouts_tournament = get_most_shutouts_tournament()
    
    most_scorers_tournament = get_most_scorers_tournament()
    most_goals_player_tournament = get_most_goals_player_tournament()
    most_assists_player_tournament = get_most_assists_player_tournament()
    most_penalty_minutes_tournament = get_most_penalty_minutes_tournament()
    
    most_frequent_matchup = get_most_frequent_matchup()
    
    return render_template('records.html',
                           longest_win_streak=longest_win_streak,
                           longest_loss_streak=longest_loss_streak,
                           longest_scoring_streak=longest_scoring_streak,
                           longest_shutout_streak=longest_shutout_streak,
                           longest_goalless_streak=longest_goalless_streak,
                           highest_victory=highest_victory,
                           most_goals_game=most_goals_game,
                           fastest_goal=fastest_goal,
                           fastest_hattrick=fastest_hattrick,
                           most_consecutive_tournament_wins=most_consecutive_tournament_wins,
                           most_final_appearances=most_final_appearances,
                           record_champion=record_champion,
                           tournament_most_goals=tournament_most_goals,
                           tournament_least_goals=tournament_least_goals,
                           tournament_most_penalty_minutes=tournament_most_penalty_minutes,
                           most_goals_team_tournament=most_goals_team_tournament,
                           fewest_goals_against_tournament=fewest_goals_against_tournament,
                           most_shutouts_tournament=most_shutouts_tournament,
                           most_scorers_tournament=most_scorers_tournament,
                           most_goals_player_tournament=most_goals_player_tournament,
                           most_assists_player_tournament=most_assists_player_tournament,
                           most_penalty_minutes_tournament=most_penalty_minutes_tournament,
                           team_iso_codes=TEAM_ISO_CODES,
                           most_frequent_matchup=most_frequent_matchup)

# Export all functions for backwards compatibility
__all__ = [
    'record_bp',
    
    # Streaks
    'get_longest_win_streak',
    'get_longest_loss_streak', 
    'get_longest_scoring_streak',
    'get_longest_shutout_streak',
    'get_longest_goalless_streak',
    
    # Game records
    'get_highest_victory',
    'get_most_goals_game',
    'get_most_frequent_matchup',
    
    # Goal records
    'get_fastest_goal',
    'get_fastest_hattrick',
    
    # Tournament records
    'get_most_consecutive_tournament_wins',
    'get_most_final_appearances',
    'get_record_champion',
    'get_tournament_with_most_goals',
    'get_tournament_with_least_goals',
    'get_tournament_with_most_penalty_minutes',
    
    # Team tournament records
    'get_most_goals_team_tournament',
    'get_fewest_goals_against_tournament',
    'get_most_shutouts_tournament',
    
    # Player records
    'get_most_scorers_tournament',
    'get_most_goals_player_tournament',
    'get_most_assists_player_tournament',
    'get_most_penalty_minutes_tournament',
    
    # Utilities
    'get_all_resolved_games',
    'get_resolved_team_info'
]