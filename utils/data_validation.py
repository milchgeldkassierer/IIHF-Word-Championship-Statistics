from typing import Tuple
from constants import PIM_MAP, GOAL_TYPE_DISPLAY_MAP
from .time_helpers import convert_time_to_seconds


def check_game_data_consistency(game_display, sog_data=None):
    """
    Checks a game display object for data consistency issues.
    
    Args:
        game_display: GameDisplay object to check
        sog_data: Optional shots on goal data dictionary
        
    Returns:
        Dictionary with consistency check results
    """
    warnings = []
    scores_fully_match_data = True
    
    # Check if scores are set but result_type is missing
    if game_display.team1_score is not None and game_display.team2_score is not None:
        if not game_display.result_type:
            warnings.append(f"Game {game_display.id}: Scores are set but result_type is missing")
            scores_fully_match_data = False
        
        # Check if scores match result_type logic
        if game_display.result_type == 'REG' and game_display.team1_score == game_display.team2_score:
            warnings.append(f"Game {game_display.id}: Regular time result but scores are tied")
            scores_fully_match_data = False
        
        if game_display.result_type in ['OT', 'SO'] and abs(game_display.team1_score - game_display.team2_score) != 1:
            warnings.append(f"Game {game_display.id}: Overtime/Shootout result but score difference is not 1")
            scores_fully_match_data = False
    
    # Check if result_type is set but scores are missing
    if game_display.result_type and (game_display.team1_score is None or game_display.team2_score is None):
        warnings.append(f"Game {game_display.id}: Result type is set but scores are missing")
        scores_fully_match_data = False
    
    # Check team codes
    if not game_display.team1_code or not game_display.team2_code:
        warnings.append(f"Game {game_display.id}: Missing team code(s)")
        scores_fully_match_data = False
    
    if game_display.team1_code == game_display.team2_code:
        warnings.append(f"Game {game_display.id}: Team playing against itself")
        scores_fully_match_data = False
    
    # Check points consistency
    if game_display.team1_score is not None and game_display.team2_score is not None and game_display.result_type:
        expected_points = calculate_expected_points(game_display.team1_score, game_display.team2_score, game_display.result_type)
        if hasattr(game_display, 'team1_points') and hasattr(game_display, 'team2_points'):
            if (game_display.team1_points, game_display.team2_points) != expected_points:
                warnings.append(f"Game {game_display.id}: Points don't match expected values for result")
                scores_fully_match_data = False
    
    # NEW: Check if goals match scores (with special rule for SO/penalty shootout)
    if (game_display.team1_score is not None and game_display.team2_score is not None and 
        hasattr(game_display, 'sorted_events') and game_display.sorted_events):
        
        # Count goals for each team from sorted_events
        team1_goals = 0
        team2_goals = 0
        overtime_goals = []  # Track goals scored in overtime
        
        for event in game_display.sorted_events:
            if event.get('type') == 'goal':
                goal_data = event.get('data', {})
                goal_team = goal_data.get('team_code')
                goal_time = goal_data.get('minute', '')
                
                # Check if goal was scored after 60:00 (overtime)
                goal_seconds = convert_time_to_seconds(goal_time)
                if goal_seconds > 3600:  # 60 minutes = 3600 seconds
                    overtime_goals.append({
                        'team': goal_team,
                        'time': goal_time,
                        'seconds': goal_seconds
                    })
                
                if goal_team == game_display.team1_code:
                    team1_goals += 1
                elif goal_team == game_display.team2_code:
                    team2_goals += 1
        
        # NEW: Check overtime goal rules
        if overtime_goals:
            # If there are overtime goals, the result_type must be OT
            if game_display.result_type != 'OT':
                warnings.append(f"Game {game_display.id}: Goal(s) scored after 60:00 but result type is not 'OT' (n.V.)")
                scores_fully_match_data = False
            
            # The team that scored the overtime goal must have exactly 1 more goal than the other team
            score_diff = abs(game_display.team1_score - game_display.team2_score)
            if score_diff != 1:
                warnings.append(f"Game {game_display.id}: Overtime goal(s) present but score difference is not 1")
                scores_fully_match_data = False
            
            # Verify that the winning team actually scored the overtime goal
            winning_team = game_display.team1_code if game_display.team1_score > game_display.team2_score else game_display.team2_code
            overtime_scoring_teams = [goal['team'] for goal in overtime_goals]
            if winning_team not in overtime_scoring_teams:
                warnings.append(f"Game {game_display.id}: Overtime goal(s) not scored by the winning team")
                scores_fully_match_data = False
        
        # Check if goals match scores
        goals_match_scores = False
        if game_display.result_type == 'SO':
            # For penalty shootout: the winning team should have 1 LESS recorded goal than their final score
            # (because the penalty shootout winning goal is not recorded as a regular goal event)
            if game_display.team1_score > game_display.team2_score:
                # Team 1 won in SO, so team1_goals should be 1 less than team1_score
                goals_match_scores = (team1_goals == game_display.team1_score - 1) and \
                                   (team2_goals == game_display.team2_score)
            else:
                # Team 2 won in SO, so team2_goals should be 1 less than team2_score
                goals_match_scores = (team2_goals == game_display.team2_score - 1) and \
                                   (team1_goals == game_display.team1_score)
        else:
            # For all other result types: goals must match scores exactly
            goals_match_scores = (team1_goals == game_display.team1_score and 
                                team2_goals == game_display.team2_score)
        
        if not goals_match_scores:
            warnings.append(f"Game {game_display.id}: Recorded goals ({team1_goals}-{team2_goals}) don't match scores ({game_display.team1_score}-{game_display.team2_score})")
            scores_fully_match_data = False
    
    # NEW: Check if SOG data is complete for all periods (P1, P2, P3)
    if sog_data and game_display.team1_code and game_display.team2_code:
        team1_sog = sog_data.get(game_display.team1_code, {})
        team2_sog = sog_data.get(game_display.team2_code, {})
        
        # Check if all three periods (1, 2, 3) have SOG data for both teams
        required_periods = [1, 2, 3]
        missing_sog_periods = []
        
        for period in required_periods:
            team1_has_sog = period in team1_sog and team1_sog[period] is not None and team1_sog[period] >= 0
            team2_has_sog = period in team2_sog and team2_sog[period] is not None and team2_sog[period] >= 0
            
            if not (team1_has_sog and team2_has_sog):
                missing_sog_periods.append(period)
        
        if missing_sog_periods:
            warnings.append(f"Game {game_display.id}: Missing SOG data for period(s): {missing_sog_periods}")
            scores_fully_match_data = False

    # NEW: Check PowerPlay/Penalty consistency
    if hasattr(game_display, 'sorted_events') and game_display.sorted_events:
        pp_penalty_warnings = check_powerplay_penalty_consistency(game_display)
        warnings.extend(pp_penalty_warnings)
        if pp_penalty_warnings:
            scores_fully_match_data = False
    
    return {
        'warnings': warnings,
        'scores_fully_match_data': scores_fully_match_data
    }


def check_powerplay_penalty_consistency(game_display):
    """
    Überprüft die Konsistenz von Powerplay-/Penalty-Situationen in einem Spiel.
    
    Regeln:
    - Wenn eine Strafe aktiv ist und ein Tor innerhalb von 2 Minuten fällt, muss es PP oder SH sein
    - Bei einem SH-Tor läuft die Strafe weiter
    - Bei einem PP-Tor endet die Strafe (außer bei Major Penalties ≥ 5 Minuten)
    - Bei 5 Min + Spieldauer: PP-Tor beendet die Strafe NICHT (Major Penalty Regel)
    - Bei 2+2 Min: PP-Tor in den ersten 2 Minuten reduziert die Strafe auf 2 Min
    - Bei gleichzeitigen Strafen beider Teams ist es kein Powerplay (4-on-4)
    
    Args:
        game_display: GameDisplay Objekt mit sorted_events
        
    Returns:
        List von Warnungen als Strings
    """
    warnings = []
    
    # Sammle alle Tore und Strafen mit Zeiten in Sekunden
    goals = []
    penalties = []
    
    for event in game_display.sorted_events:
        if event.get('type') == 'goal':
            goal_data = event.get('data', {})
            goals.append({
                'time_seconds': event.get('time_for_sort', 0),
                'time_str': goal_data.get('minute', ''),
                'team': goal_data.get('team_code', ''),
                'goal_type': goal_data.get('goal_type_display', ''),
                'scorer': goal_data.get('scorer', ''),
                'id': goal_data.get('id', 0)
            })
        elif event.get('type') == 'penalty':
            penalty_data = event.get('data', {})
            penalty_duration = get_penalty_duration_minutes(penalty_data.get('penalty_type', ''))
            penalties.append({
                'time_seconds': event.get('time_for_sort', 0),
                'time_str': penalty_data.get('minute_of_game', ''),
                'team': penalty_data.get('team_code', ''),
                'penalty_type': penalty_data.get('penalty_type', ''),
                'duration_minutes': penalty_duration,
                'original_duration_minutes': penalty_duration,  # Originale Dauer für 2+2 Strafen
                'player': penalty_data.get('player_name', ''),
                'id': penalty_data.get('id', 0),
                'is_active': True  # Wird bei PP-Toren modifiziert
            })
    
    # Sortiere nach Zeit
    goals.sort(key=lambda x: x['time_seconds'])
    penalties.sort(key=lambda x: x['time_seconds'])
    
    # Überprüfe jedes Tor auf Powerplay-Konsistenz
    # WICHTIG: Sequenzielle Verarbeitung um PP-Tor-Regeln korrekt zu handhaben
    for goal in goals:
        goal_time = goal['time_seconds']
        goal_team = goal['team']
        goal_type = goal['goal_type']
        
        # Finde aktive Strafen zum Zeitpunkt des Tors
        # Berücksichtige die Regel: Max 2 Spieler gleichzeitig in der Strafbank
        active_penalties_at_goal = []
        
        # Gruppiere Strafen nach Teams
        penalties_by_team = {}
        for penalty in penalties:
            if not penalty['is_active']:
                continue
            team = penalty['team']
            if team not in penalties_by_team:
                penalties_by_team[team] = []
            penalties_by_team[team].append(penalty)
        
        # Berechne für jedes Team die effektiven Strafzeiten
        for team, team_penalties in penalties_by_team.items():
            # Sortiere Strafen nach Startzeit
            team_penalties.sort(key=lambda x: x['time_seconds'])
            
            # Verfolge die aktiven Strafen für dieses Team
            active_team_penalties = []
            
            for penalty in team_penalties:
                penalty_start = penalty['time_seconds']
                penalty_duration = penalty['duration_minutes'] * 60
                
                # Finde die effektive Startzeit dieser Strafe
                effective_start = penalty_start
                
                # Wenn bereits 2 Strafen aktiv sind, muss diese Strafe warten
                if len(active_team_penalties) >= 2:
                    # Finde die früheste Endzeit der aktiven Strafen
                    earliest_end = min(p['effective_end'] for p in active_team_penalties)
                    if penalty_start < earliest_end:
                        effective_start = earliest_end
                
                effective_end = effective_start + penalty_duration
                
                # Prüfe, ob diese Strafe zum Zeitpunkt des Tors aktiv ist
                if effective_start <= goal_time <= effective_end:
                    penalty_copy = penalty.copy()
                    penalty_copy['effective_start'] = effective_start
                    penalty_copy['effective_end'] = effective_end
                    active_penalties_at_goal.append(penalty_copy)
                
                # Aktualisiere die Liste der aktiven Strafen
                # Entferne abgelaufene Strafen
                active_team_penalties = [p for p in active_team_penalties if p['effective_end'] > effective_start]
                
                # Füge die neue Strafe hinzu
                active_team_penalties.append({
                    'effective_start': effective_start,
                    'effective_end': effective_end,
                    'penalty': penalty
                })
                
                # Beschränke auf max 2 gleichzeitige Strafen
                if len(active_team_penalties) > 2:
                    active_team_penalties = active_team_penalties[:2]
        
        # Analysiere die Powerplay-Situation
        pp_situation = analyze_powerplay_situation(active_penalties_at_goal, goal_team, game_display.team1_code, game_display.team2_code)
        
        # Überprüfe, ob der Tortyp zur Situation passt
        expected_goal_types = get_expected_goal_types(pp_situation)
        
        # Convert display type back to database type for comparison
        goal_type_for_validation = goal_type
        for db_type, display_type in GOAL_TYPE_DISPLAY_MAP.items():
            if goal_type == display_type:
                goal_type_for_validation = db_type
                break
        
        if expected_goal_types and goal_type_for_validation not in expected_goal_types:
            situation_desc = describe_powerplay_situation(pp_situation, active_penalties_at_goal)
            warnings.append(f"Spiel {game_display.id}: Tor von {goal_team} um {goal['time_str']} ist als '{goal_type}' markiert, aber bei {situation_desc} sollte es '{'/'.join(expected_goal_types)}' sein")
        
        # KRITISCH: Spezielle Behandlung von Strafen bei PP-Toren
        # Diese Änderungen müssen PERSISTENT sein für nachfolgende Tore!
        if goal_type == 'PP':
            for penalty in penalties:  # Verwende die ursprüngliche penalties Liste
                if not penalty['is_active']:
                    continue
                if penalty['team'] != goal_team:  # Strafe des Gegners
                    penalty_type = penalty['penalty_type']
                    penalty_start = penalty['time_seconds']
                    penalty_duration = penalty['duration_minutes'] * 60
                    penalty_end = penalty_start + penalty_duration
                    
                    # Prüfe, ob diese Strafe zum Zeitpunkt des PP-Tors aktiv war
                    if penalty_start <= goal_time <= penalty_end:
                        if penalty_type == '5 Min + Spieldauer':
                            # Bei 5+Spieldauer: PP-Tor beendet die Strafe NICHT (Major Penalty)
                            # Die Strafe läuft weiter
                            pass
                        elif penalty_type == '2+2 Min':
                            # Bei 2+2 Min: PP-Tor in den ersten 2 Minuten reduziert auf 2 Min
                            time_since_penalty_start = goal_time - penalty_start
                            if time_since_penalty_start <= 120:  # Ersten 2 Minuten (120 Sekunden)
                                # Strafe wird auf 2 Minuten reduziert
                                penalty['duration_minutes'] = 2
                            else:
                                # Nach den ersten 2 Minuten: Strafe endet normal
                                penalty['is_active'] = False
                        elif penalty['duration_minutes'] < 5:
                            # Minor Penalties (< 5 Min): Strafe endet bei PP-Tor
                            penalty['is_active'] = False
                        # Major Penalties (>= 5 Min aber nicht 5+Spieldauer): Strafe läuft weiter
    
    return warnings


def get_penalty_duration_minutes(penalty_type):
    """Gibt die Dauer einer Strafe in Minuten zurück."""
    # Hauptmapping aus constants.py
    if penalty_type in PIM_MAP:
        return PIM_MAP[penalty_type]
    
    # Fallback für andere mögliche Formate
    duration_map = {
        '2 min': 2,
        '2+2 min': 4,
        '2+10 min': 12,
        '4 min': 4,
        '5 min': 5,
        '5+10 min': 15,
        '10 min': 10,
        '20 min': 20,
        'Match penalty': 20,
        'Game misconduct': 10,
        'Misconduct': 10
    }
    return duration_map.get(penalty_type.lower(), 2)  # Default 2 Minuten


def analyze_powerplay_situation(active_penalties, goal_team, team1_code, team2_code):
    """
    Analysiert die Powerplay-Situation basierend auf aktiven Strafen.
    
    WICHTIG: Die aktiven Strafen wurden bereits korrekt gefiltert unter Berücksichtigung der Regel,
    dass ein Team maximal 2 Spieler gleichzeitig in der Strafbank haben kann.
    
    Returns:
        dict mit 'type' ('pp', 'sh', '4on4', 'even') und Details
    """
    # Zähle Strafen pro Team (bereits korrekt gefiltert)
    team1_penalties = [p for p in active_penalties if p['team'] == team1_code]
    team2_penalties = [p for p in active_penalties if p['team'] == team2_code]
    
    team1_penalty_count = len(team1_penalties)
    team2_penalty_count = len(team2_penalties)
    
    # Bestimme welches Team das Tor geschossen hat
    goal_team_penalties = team1_penalties if goal_team == team1_code else team2_penalties
    opponent_penalties = team2_penalties if goal_team == team1_code else team1_penalties
    
    goal_team_penalty_count = len(goal_team_penalties)
    opponent_penalty_count = len(opponent_penalties)
    
    if goal_team_penalty_count == 0 and opponent_penalty_count == 0:
        return {'type': 'even'}
    elif goal_team_penalty_count > 0 and opponent_penalty_count == 0:
        return {'type': 'sh', 'goal_team_penalties': goal_team_penalty_count}
    elif goal_team_penalty_count == 0 and opponent_penalty_count > 0:
        return {'type': 'pp', 'opponent_penalties': opponent_penalty_count}
    elif goal_team_penalty_count > 0 and opponent_penalty_count > 0:
        # Beide Teams haben Strafen - normalerweise 4-on-4
        return {'type': '4on4', 'goal_team_penalties': goal_team_penalty_count, 'opponent_penalties': opponent_penalty_count}
    else:
        return {'type': 'unknown'}


def get_expected_goal_types(pp_situation):
    """Gibt die erwarteten Tortypen für eine gegebene Powerplay-Situation zurück."""
    situation_type = pp_situation.get('type')
    
    if situation_type == 'pp':
        return ['PP']
    elif situation_type == 'sh':
        return ['SH']
    elif situation_type == '4on4':
        return ['REG']  # 4-on-4 gilt als regulär
    elif situation_type == 'even':
        return ['REG']
    else:
        return []


def describe_powerplay_situation(pp_situation, active_penalties):
    """Beschreibt die Powerplay-Situation für Fehlermeldungen."""
    situation_type = pp_situation.get('type')
    
    if situation_type == 'pp':
        penalty_count = pp_situation.get('opponent_penalties', 1)
        return f"aktiver Strafe des Gegners (Powerplay, {penalty_count} Strafe{'n' if penalty_count > 1 else ''})"
    elif situation_type == 'sh':
        penalty_count = pp_situation.get('goal_team_penalties', 1)
        return f"eigener Strafe (Unterzahl, {penalty_count} Strafe{'n' if penalty_count > 1 else ''})"
    elif situation_type == '4on4':
        return "gleichzeitigen Strafen beider Teams (4-gegen-4)"
    elif situation_type == 'even':
        return "gleichstarker Besetzung"
    else:
        return "unklarer Strafsituation"


def calculate_expected_points(team1_score: int, team2_score: int, result_type: str) -> Tuple[int, int]:
    """
    Calculates expected points for both teams based on scores and result type.
    
    Returns:
        Tuple of (team1_points, team2_points)
    """
    if result_type == 'REG':
        if team1_score > team2_score:
            return (3, 0)
        elif team2_score > team1_score:
            return (0, 3)
        else:
            return (1, 1)  # Tie in regulation (rare in hockey)
    elif result_type in ['OT', 'SO']:
        if team1_score > team2_score:
            return (2, 1)
        else:
            return (1, 2)
    else:
        return (0, 0)  # Unknown result type