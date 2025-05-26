from models import Goal, ShotsOnGoal

def convert_time_to_seconds(time_str):
    if not time_str or ':' not in time_str:
        return float('inf')
    try:
        minutes, seconds = map(int, time_str.split(':'))
        return minutes * 60 + seconds
    except ValueError:
        return float('inf')

def check_game_data_consistency(game_obj, sog_data_for_game_id):
    """
    Checks if the game's score matches the counted goals and if SOG data is sufficient.
    sog_data_for_game_id should be a dict like: {team_code: {period: shots}}
    Example: sog_by_game_flat.get(game_id, {})
    """
    goals_match = False
    if game_obj.team1_score is not None and game_obj.team2_score is not None:
        actual_goals_team1_db = Goal.query.filter_by(game_id=game_obj.id, team_code=game_obj.team1_code).count()
        actual_goals_team2_db = Goal.query.filter_by(game_id=game_obj.id, team_code=game_obj.team2_code).count()
        
        expected_db_goals_team1 = game_obj.team1_score
        expected_db_goals_team2 = game_obj.team2_score

        if game_obj.result_type == 'SO':
            if game_obj.team1_score > game_obj.team2_score: expected_db_goals_team1 -= 1
            elif game_obj.team2_score > game_obj.team1_score: expected_db_goals_team2 -= 1
        goals_match = (actual_goals_team1_db == expected_db_goals_team1) and (actual_goals_team2_db == expected_db_goals_team2)
    elif game_obj.team1_score is None and game_obj.team2_score is None: # If no score entered, expect no goals
        actual_goals_team1_db = Goal.query.filter_by(game_id=game_obj.id, team_code=game_obj.team1_code).count()
        actual_goals_team2_db = Goal.query.filter_by(game_id=game_obj.id, team_code=game_obj.team2_code).count()
        goals_match = (actual_goals_team1_db == 0) and (actual_goals_team2_db == 0)
    else: # One score entered but not the other, or other inconsistent states
        goals_match = False

    sog_criteria_met = False
    if game_obj.team1_score is not None and game_obj.team2_score is not None:
        team1_sog_periods = sog_data_for_game_id.get(game_obj.team1_code, {})
        team2_sog_periods = sog_data_for_game_id.get(game_obj.team2_code, {})

        # Check SOG for P1, P2, P3 - must be > 0 for both teams if score is entered
        sog_p1_ok = team1_sog_periods.get(1, 0) > 0 and team2_sog_periods.get(1, 0) > 0
        sog_p2_ok = team1_sog_periods.get(2, 0) > 0 and team2_sog_periods.get(2, 0) > 0
        sog_p3_ok = team1_sog_periods.get(3, 0) > 0 and team2_sog_periods.get(3, 0) > 0
        
        sog_ot_ok = True # Assume OT SOG is okay if game not in OT/SO
        if game_obj.result_type in ['OT', 'SO']:
            # For OT/SO games, SOG must be > 0 for period 4 for both teams
            sog_ot_ok = team1_sog_periods.get(4, 0) > 0 and team2_sog_periods.get(4, 0) > 0
        
        sog_criteria_met = sog_p1_ok and sog_p2_ok and sog_p3_ok and sog_ot_ok
    elif game_obj.team1_score is None and game_obj.team2_score is None: # If no score entered, SOG criteria are met by default
        sog_criteria_met = True
    else: # One score entered but not other - SOG criteria not met
        sog_criteria_met = False
        
    return {
        'goals_match_score': goals_match,
        'sog_criteria_met': sog_criteria_met,
        'scores_fully_match_data': goals_match and sog_criteria_met
    } 