from collections import defaultdict
from .utils import get_all_resolved_games


def get_longest_win_streak(records_data=None):
    """Berechnet die längste Siegesserie über alle Turniere"""
    if records_data is None:
        resolved_games = get_all_resolved_games()
    else:
        resolved_games = records_data['resolved_games']
    resolved_games.sort(key=lambda x: (
        x['year'] or 0, 
        x['game'].date or '1900-01-01', 
        x['game'].game_number or 0
    ))
    
    team_streaks = defaultdict(int)
    team_streak_start = defaultdict(lambda: None)
    team_streak_end = defaultdict(lambda: None)
    max_streaks = []
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        
        winner = None
        loser = None
        
        if game.team1_score > game.team2_score:
            winner = team1_code
            loser = team2_code
        elif game.team2_score > game.team1_score:
            winner = team2_code
            loser = team1_code
        
        if winner:
            if team_streaks[winner] == 0:
                team_streak_start[winner] = game.date
            team_streaks[winner] += 1
            team_streak_end[winner] = game.date
            
            team_streaks[loser] = 0
            team_streak_start[loser] = None
            team_streak_end[loser] = None
            
            # Sammle alle Streaks für spätere Top 3 Auswertung
            current_record = {
                'team': winner, 
                'streak': team_streaks[winner],
                'start_date': team_streak_start[winner],
                'end_date': team_streak_end[winner],
                'rank': 0
            }
            
            # Prüfe ob bereits eine Serie für dieses Team und Startdatum existiert
            record_exists = False
            for i, existing in enumerate(max_streaks):
                if (existing['team'] == winner and 
                    existing['start_date'] == team_streak_start[winner]):
                    # Ersetze mit längerer Serie
                    if team_streaks[winner] > existing['streak']:
                        max_streaks[i] = current_record
                    record_exists = True
                    break
            
            if not record_exists:
                max_streaks.append(current_record)
    
    # Sortiere nach Streak-Länge und bestimme Top 3
    max_streaks.sort(key=lambda x: x['streak'], reverse=True)
    
    top_3_results = []
    current_rank = 1
    last_streak = None
    
    for streak_record in max_streaks:
        if last_streak is None or streak_record['streak'] != last_streak:
            if len(top_3_results) >= 3:
                break
            if current_rank > 3:
                break
            streak_record['rank'] = current_rank
            last_streak = streak_record['streak']
            current_rank += 1
        else:
            streak_record['rank'] = current_rank - 1
        
        if streak_record['rank'] <= 3:
            top_3_results.append(streak_record)
    
    return top_3_results


def get_longest_loss_streak(records_data=None):
    """Berechnet die längste Niederlagenserie über alle Turniere"""
    if records_data is None:
        resolved_games = get_all_resolved_games()
    else:
        resolved_games = records_data['resolved_games']
    resolved_games.sort(key=lambda x: (
        x['year'] or 0, 
        x['game'].date or '1900-01-01', 
        x['game'].game_number or 0
    ))
    
    team_streaks = defaultdict(int)
    team_streak_start = defaultdict(lambda: None)
    team_streak_end = defaultdict(lambda: None)
    max_streaks = []
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        
        winner = None
        loser = None
        
        if game.team1_score > game.team2_score:
            winner = team1_code
            loser = team2_code
        elif game.team2_score > game.team1_score:
            winner = team2_code
            loser = team1_code
        
        if winner and loser:
            if team_streaks[loser] == 0:
                team_streak_start[loser] = game.date
            team_streaks[loser] += 1
            team_streak_end[loser] = game.date
            
            team_streaks[winner] = 0
            team_streak_start[winner] = None
            team_streak_end[winner] = None
            
            # Sammle alle Streaks für spätere Top 3 Auswertung
            current_record = {
                'team': loser, 
                'streak': team_streaks[loser],
                'start_date': team_streak_start[loser],
                'end_date': team_streak_end[loser],
                'rank': 0
            }
            
            # Prüfe ob bereits eine Serie für dieses Team und Startdatum existiert
            record_exists = False
            for i, existing in enumerate(max_streaks):
                if (existing['team'] == loser and 
                    existing['start_date'] == team_streak_start[loser]):
                    # Ersetze mit längerer Serie
                    if team_streaks[loser] > existing['streak']:
                        max_streaks[i] = current_record
                    record_exists = True
                    break
            
            if not record_exists:
                max_streaks.append(current_record)
    
    # Sortiere nach Streak-Länge und bestimme Top 3
    max_streaks.sort(key=lambda x: x['streak'], reverse=True)
    
    top_3_results = []
    current_rank = 1
    last_streak = None
    
    for streak_record in max_streaks:
        if last_streak is None or streak_record['streak'] != last_streak:
            if len(top_3_results) >= 3:
                break
            if current_rank > 3:
                break
            streak_record['rank'] = current_rank
            last_streak = streak_record['streak']
            current_rank += 1
        else:
            streak_record['rank'] = current_rank - 1
        
        if streak_record['rank'] <= 3:
            top_3_results.append(streak_record)
    
    return top_3_results


def get_longest_scoring_streak(records_data=None):
    """Berechnet die längste Serie mit mindestens 1 Tor"""
    if records_data is None:
        resolved_games = get_all_resolved_games()
    else:
        resolved_games = records_data['resolved_games']
    resolved_games.sort(key=lambda x: (
        x['year'] or 0, 
        x['game'].date or '1900-01-01', 
        x['game'].game_number or 0
    ))
    
    team_streaks = defaultdict(int)
    team_streak_start = defaultdict(lambda: None)
    team_streak_end = defaultdict(lambda: None)
    max_streaks = []
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        
        if game.team1_score > 0:
            if team_streaks[team1_code] == 0:
                team_streak_start[team1_code] = game.date
            team_streaks[team1_code] += 1
            team_streak_end[team1_code] = game.date
        else:
            team_streaks[team1_code] = 0
            team_streak_start[team1_code] = None
            team_streak_end[team1_code] = None
            
        if game.team2_score > 0:
            if team_streaks[team2_code] == 0:
                team_streak_start[team2_code] = game.date
            team_streaks[team2_code] += 1
            team_streak_end[team2_code] = game.date
        else:
            team_streaks[team2_code] = 0
            team_streak_start[team2_code] = None
            team_streak_end[team2_code] = None
        
        for team in [team1_code, team2_code]:
            if team_streaks[team] > 0:
                # Sammle alle Streaks für spätere Top 3 Auswertung
                current_record = {
                    'team': team, 
                    'streak': team_streaks[team],
                    'start_date': team_streak_start[team],
                    'end_date': team_streak_end[team],
                    'rank': 0
                }
                
                # Prüfe ob bereits eine Serie für dieses Team und Startdatum existiert
                record_exists = False
                for i, existing in enumerate(max_streaks):
                    if (existing['team'] == team and 
                        existing['start_date'] == team_streak_start[team]):
                        # Ersetze mit längerer Serie
                        if team_streaks[team] > existing['streak']:
                            max_streaks[i] = current_record
                        record_exists = True
                        break
                
                if not record_exists:
                    max_streaks.append(current_record)
    
    # Sortiere nach Streak-Länge und bestimme Top 3
    max_streaks.sort(key=lambda x: x['streak'], reverse=True)
    
    top_3_results = []
    current_rank = 1
    last_streak = None
    
    for streak_record in max_streaks:
        if last_streak is None or streak_record['streak'] != last_streak:
            if len(top_3_results) >= 3:
                break
            if current_rank > 3:
                break
            streak_record['rank'] = current_rank
            last_streak = streak_record['streak']
            current_rank += 1
        else:
            streak_record['rank'] = current_rank - 1
        
        if streak_record['rank'] <= 3:
            top_3_results.append(streak_record)
    
    return top_3_results


def get_longest_shutout_streak(records_data=None):
    """Berechnet die längste Serie ohne Gegentor"""
    if records_data is None:
        resolved_games = get_all_resolved_games()
    else:
        resolved_games = records_data['resolved_games']
    resolved_games.sort(key=lambda x: (
        x['year'] or 0, 
        x['game'].date or '1900-01-01', 
        x['game'].game_number or 0
    ))
    
    team_streaks = defaultdict(int)
    team_streak_start = defaultdict(lambda: None)
    team_streak_end = defaultdict(lambda: None)
    max_streaks = []
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        
        if game.team2_score == 0:
            if team_streaks[team1_code] == 0:
                team_streak_start[team1_code] = game.date
            team_streaks[team1_code] += 1
            team_streak_end[team1_code] = game.date
        else:
            team_streaks[team1_code] = 0
            team_streak_start[team1_code] = None
            team_streak_end[team1_code] = None
            
        if game.team1_score == 0:
            if team_streaks[team2_code] == 0:
                team_streak_start[team2_code] = game.date
            team_streaks[team2_code] += 1
            team_streak_end[team2_code] = game.date
        else:
            team_streaks[team2_code] = 0
            team_streak_start[team2_code] = None
            team_streak_end[team2_code] = None
        
        for team in [team1_code, team2_code]:
            if team_streaks[team] > 0:
                # Sammle alle Streaks für spätere Top 3 Auswertung
                current_record = {
                    'team': team, 
                    'streak': team_streaks[team],
                    'start_date': team_streak_start[team],
                    'end_date': team_streak_end[team],
                    'rank': 0
                }
                
                # Prüfe ob bereits eine Serie für dieses Team und Startdatum existiert
                record_exists = False
                for i, existing in enumerate(max_streaks):
                    if (existing['team'] == team and 
                        existing['start_date'] == team_streak_start[team]):
                        # Ersetze mit längerer Serie
                        if team_streaks[team] > existing['streak']:
                            max_streaks[i] = current_record
                        record_exists = True
                        break
                
                if not record_exists:
                    max_streaks.append(current_record)
    
    # Sortiere nach Streak-Länge und bestimme Top 3
    max_streaks.sort(key=lambda x: x['streak'], reverse=True)
    
    top_3_results = []
    current_rank = 1
    last_streak = None
    
    for streak_record in max_streaks:
        if last_streak is None or streak_record['streak'] != last_streak:
            if len(top_3_results) >= 3:
                break
            if current_rank > 3:
                break
            streak_record['rank'] = current_rank
            last_streak = streak_record['streak']
            current_rank += 1
        else:
            streak_record['rank'] = current_rank - 1
        
        if streak_record['rank'] <= 3:
            top_3_results.append(streak_record)
    
    return top_3_results


def get_longest_goalless_streak(records_data=None):
    """Berechnet die längste Serie ohne eigenes Tor"""
    if records_data is None:
        resolved_games = get_all_resolved_games()
    else:
        resolved_games = records_data['resolved_games']
    resolved_games.sort(key=lambda x: (
        x['year'] or 0, 
        x['game'].date or '1900-01-01', 
        x['game'].game_number or 0
    ))
    
    team_streaks = defaultdict(int)
    team_streak_start = defaultdict(lambda: None)
    team_streak_end = defaultdict(lambda: None)
    max_streaks = []
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        
        if game.team1_score == 0:
            if team_streaks[team1_code] == 0:
                team_streak_start[team1_code] = game.date
            team_streaks[team1_code] += 1
            team_streak_end[team1_code] = game.date
        else:
            team_streaks[team1_code] = 0
            team_streak_start[team1_code] = None
            team_streak_end[team1_code] = None
            
        if game.team2_score == 0:
            if team_streaks[team2_code] == 0:
                team_streak_start[team2_code] = game.date
            team_streaks[team2_code] += 1
            team_streak_end[team2_code] = game.date
        else:
            team_streaks[team2_code] = 0
            team_streak_start[team2_code] = None
            team_streak_end[team2_code] = None
        
        for team in [team1_code, team2_code]:
            if team_streaks[team] > 0:
                # Sammle alle Streaks für spätere Top 3 Auswertung
                current_record = {
                    'team': team, 
                    'streak': team_streaks[team],
                    'start_date': team_streak_start[team],
                    'end_date': team_streak_end[team],
                    'rank': 0
                }
                
                # Prüfe ob bereits eine Serie für dieses Team und Startdatum existiert
                record_exists = False
                for i, existing in enumerate(max_streaks):
                    if (existing['team'] == team and 
                        existing['start_date'] == team_streak_start[team]):
                        # Ersetze mit längerer Serie
                        if team_streaks[team] > existing['streak']:
                            max_streaks[i] = current_record
                        record_exists = True
                        break
                
                if not record_exists:
                    max_streaks.append(current_record)
    
    # Sortiere nach Streak-Länge und bestimme Top 3
    max_streaks.sort(key=lambda x: x['streak'], reverse=True)
    
    top_3_results = []
    current_rank = 1
    last_streak = None
    
    for streak_record in max_streaks:
        if last_streak is None or streak_record['streak'] != last_streak:
            if len(top_3_results) >= 3:
                break
            if current_rank > 3:
                break
            streak_record['rank'] = current_rank
            last_streak = streak_record['streak']
            current_rank += 1
        else:
            streak_record['rank'] = current_rank - 1
        
        if streak_record['rank'] <= 3:
            top_3_results.append(streak_record)
    
    return top_3_results