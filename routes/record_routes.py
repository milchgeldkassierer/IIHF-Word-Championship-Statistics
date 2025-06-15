from flask import Blueprint, render_template
from models import db, Game, Goal, Player, ChampionshipYear, Penalty
from sqlalchemy import func, case, desc, asc, and_, or_
from collections import defaultdict, Counter
from datetime import datetime
import re
from constants import TEAM_ISO_CODES, PIM_MAP, PRELIM_ROUNDS, PLAYOFF_ROUNDS
from utils import resolve_game_participants, get_resolved_team_code, is_code_final, _apply_head_to_head_tiebreaker

record_bp = Blueprint('record_bp', __name__)

def get_all_resolved_games():
    """
    Holt alle Spiele und löst Platzhalter auf, basierend auf der bewährten Logik aus year_routes.py
    """
    # Nutze die bereits funktionierende Team-Auflösungslogik aus year_routes.py
    from models import TeamStats
    import re, os, json
    
    all_resolved_games = []
    
    # Hole alle Jahre
    years = ChampionshipYear.query.all()
    
    for year_obj in years:
        try:
            # Simuliere year_view Logik für dieses Jahr um aufgelöste Teams zu bekommen
            games_raw = Game.query.filter_by(year_id=year_obj.id).order_by(Game.date, Game.start_time, Game.game_number).all()
            
            if not games_raw:
                continue
                
            # Nutze dieselbe Team-Auflösungslogik wie in year_routes.py
            # Erstelle Preliminary Round Statistics
            teams_stats = {}
            prelim_games = [g for g in games_raw if g.round == 'Preliminary Round' and g.group]
            
            unique_teams_in_prelim_groups = set()
            for g in prelim_games:
                if g.team1_code and g.group: 
                    unique_teams_in_prelim_groups.add((g.team1_code, g.group))
                if g.team2_code and g.group: 
                    unique_teams_in_prelim_groups.add((g.team2_code, g.group))

            for team_code, group_name in unique_teams_in_prelim_groups:
                if team_code not in teams_stats: 
                    teams_stats[team_code] = TeamStats(name=team_code, group=group_name)

            for g in [pg for pg in prelim_games if pg.team1_score is not None]: 
                for code, grp, gf, ga, pts, res, is_t1 in [(g.team1_code, g.group, g.team1_score, g.team2_score, g.team1_points, g.result_type, True),
                                                           (g.team2_code, g.group, g.team2_score, g.team1_score, g.team2_points, g.result_type, False)]:
                    stats = teams_stats.setdefault(code, TeamStats(name=code, group=grp))
                    
                    if stats.group == grp: 
                         stats.gp+=1; stats.gf+=gf; stats.ga+=ga; stats.pts+=pts
                         if res=='REG': stats.w+=1 if gf>ga else 0; stats.l+=1 if ga>gf else 0 
                         elif res=='OT': stats.otw+=1 if gf>ga else 0; stats.otl+=1 if ga>gf else 0
                         elif res=='SO': stats.sow+=1 if gf>ga else 0; stats.sol+=1 if ga>gf else 0
            
            standings_by_group = {}
            if teams_stats:
                group_full_names = sorted(list(set(s.group for s in teams_stats.values() if s.group))) 
                for full_group_name_key in group_full_names: 
                    current_group_teams = sorted(
                        [s for s in teams_stats.values() if s.group == full_group_name_key],
                        key=lambda x: (x.pts, x.gd, x.gf),
                        reverse=True
                    )
                    current_group_teams = _apply_head_to_head_tiebreaker(current_group_teams, prelim_games)
                    for i, team_stat_obj in enumerate(current_group_teams):
                        team_stat_obj.rank_in_group = i + 1 
                    
                    standings_by_group[full_group_name_key] = current_group_teams

            # Erstelle playoff_team_map exakt wie in year_routes.py
            playoff_team_map = {}
            for group_display_name, group_standings_list in standings_by_group.items():
                group_letter_match = re.match(r"Group ([A-D])", group_display_name) 
                if group_letter_match:
                    group_letter = group_letter_match.group(1)
                    for i, s_team_obj in enumerate(group_standings_list): 
                        playoff_team_map[f'{group_letter}{i+1}'] = s_team_obj.name 

            games_dict_by_num = {g.game_number: g for g in games_raw}
            
            # Lade fixture data wie in year_routes.py
            qf_game_numbers = []
            sf_game_numbers = []
            bronze_game_number = None
            gold_game_number = None
            tournament_hosts = []

            fixture_path_exists = False
            if year_obj.fixture_path:
                try:
                    from routes.main_routes import resolve_fixture_path
                    absolute_fixture_path = resolve_fixture_path(year_obj.fixture_path)
                    fixture_path_exists = absolute_fixture_path and os.path.exists(absolute_fixture_path)
                except:
                    fixture_path_exists = False

            if year_obj.fixture_path and fixture_path_exists:
                try:
                    with open(absolute_fixture_path, 'r', encoding='utf-8') as f:
                        loaded_fixture_data = json.load(f)
                    tournament_hosts = loaded_fixture_data.get("hosts", [])
                    
                    schedule_data = loaded_fixture_data.get("schedule", [])
                    for i, game_data in enumerate(schedule_data):
                        round_name = game_data.get("round", "").lower()
                        game_num = game_data.get("gameNumber")
                        
                        if "quarterfinal" in round_name: 
                            qf_game_numbers.append(game_num)
                        elif "semifinal" in round_name: 
                            sf_game_numbers.append(game_num)
                        elif "bronze medal game" in round_name or "bronze" in round_name or "3rd place" in round_name:
                            bronze_game_number = game_num
                        elif "gold medal game" in round_name or "final" in round_name or "gold" in round_name:
                            gold_game_number = game_num
                    sf_game_numbers.sort()
                except Exception as e: 
                    if year_obj.year == 2025: 
                        qf_game_numbers = [57, 58, 59, 60]
                        sf_game_numbers = [61, 62]
                        bronze_game_number = 63
                        gold_game_number = 64
                        tournament_hosts = ["SWE", "DEN"]

            if sf_game_numbers and len(sf_game_numbers) >= 2 and all(isinstance(item, int) for item in sf_game_numbers):
                playoff_team_map['SF1'] = str(sf_game_numbers[0])
                playoff_team_map['SF2'] = str(sf_game_numbers[1])

            # Verwende dieselbe get_resolved_code Funktion wie in year_routes.py
            def get_resolved_code(placeholder_code, current_map):
                max_depth = 5 
                current_code = placeholder_code
                for _ in range(max_depth):
                    if current_code in current_map:
                        next_code = current_map[current_code]
                        if next_code == current_code: return current_code 
                        current_code = next_code
                    elif (current_code.startswith('W(') or current_code.startswith('L(')) and current_code.endswith(')'):
                        match = re.search(r'\(([^()]+)\)', current_code) 
                        if match:
                            inner_placeholder = match.group(1)
                            if inner_placeholder.isdigit():
                                game_num = int(inner_placeholder)
                                game = games_dict_by_num.get(game_num)
                                if game and game.team1_score is not None:
                                    raw_winner = game.team1_code if game.team1_score > game.team2_score else game.team2_code
                                    raw_loser = game.team2_code if game.team1_score > game.team2_score else game.team1_code
                                    outcome_based_code = raw_winner if current_code.startswith('W(') else raw_loser
                                    next_code = current_map.get(outcome_based_code, outcome_based_code)
                                    if next_code == current_code: return next_code 
                                    current_code = next_code 
                                else: return current_code 
                            else: 
                                resolved_inner = current_map.get(inner_placeholder, inner_placeholder)
                                if resolved_inner == inner_placeholder: return current_code 
                                if resolved_inner.isdigit():
                                     current_code = f"{'W' if current_code.startswith('W(') else 'L'}({resolved_inner})"
                                else: 
                                     return resolved_inner 
                        else: return current_code 
                    else: 
                        return current_code
                return current_code

            # Führe die Auflösung direkt auf games_raw durch
            for _pass_num in range(max(3, len(games_raw) // 2)): 
                changes_in_pass = 0
                for game in games_raw:
                    if game.team1_score is None or game.team2_score is None:
                        continue
                    
                    # Löse Team-Codes auf
                    resolved_t1 = get_resolved_code(game.team1_code, playoff_team_map)
                    resolved_t2 = get_resolved_code(game.team2_code, playoff_team_map)
                    
                    # Aktualisiere playoff_team_map mit Gewinnern/Verlierern
                    if game.round != 'Preliminary Round':
                        if is_code_final(resolved_t1) and is_code_final(resolved_t2):
                            actual_winner = resolved_t1 if game.team1_score > game.team2_score else resolved_t2
                            actual_loser = resolved_t2 if game.team1_score > game.team2_score else resolved_t1
                            
                            win_key = f'W({game.game_number})'
                            lose_key = f'L({game.game_number})'
                            if playoff_team_map.get(win_key) != actual_winner: 
                                playoff_team_map[win_key] = actual_winner
                                changes_in_pass += 1
                            if playoff_team_map.get(lose_key) != actual_loser: 
                                playoff_team_map[lose_key] = actual_loser
                                changes_in_pass += 1
                
                if changes_in_pass == 0 and _pass_num > 0: 
                    break 

            # Führe dieselbe Semifinal-Logik durch wie in year_routes.py
            if qf_game_numbers and sf_game_numbers and len(sf_game_numbers) == 2:
                qf_winners_teams = []
                all_qf_winners_resolved = True
                for qf_game_num in qf_game_numbers:
                    winner_placeholder = f'W({qf_game_num})'
                    resolved_qf_winner = get_resolved_code(winner_placeholder, playoff_team_map)

                    if is_code_final(resolved_qf_winner):
                        qf_winners_teams.append(resolved_qf_winner)
                    else:
                        all_qf_winners_resolved = False; break
                
                if all_qf_winners_resolved and len(qf_winners_teams) == 4:
                    qf_winners_stats = []
                    for team_name in qf_winners_teams:
                        if team_name in teams_stats: 
                            qf_winners_stats.append(teams_stats[team_name])
                        else: 
                            all_qf_winners_resolved = False; break 
                    
                    if all_qf_winners_resolved and len(qf_winners_stats) == 4:
                        qf_winners_stats.sort(key=lambda ts: (ts.rank_in_group, -ts.pts, -ts.gd, -ts.gf))
                        R1, R2, R3, R4 = [ts.name for ts in qf_winners_stats] 

                        matchup1 = (R1, R4); matchup2 = (R2, R3)
                        sf_game1_teams = None; sf_game2_teams = None
                        primary_host_plays_sf1 = False

                        if tournament_hosts:
                            if tournament_hosts[0] in [R1,R2,R3,R4]: 
                                 primary_host_plays_sf1 = True
                                 if R1 == tournament_hosts[0] or R4 == tournament_hosts[0]: sf_game1_teams = matchup1; sf_game2_teams = matchup2
                                 else: sf_game1_teams = matchup2; sf_game2_teams = matchup1
                            elif len(tournament_hosts) > 1 and tournament_hosts[1] in [R1,R2,R3,R4]: 
                                 primary_host_plays_sf1 = True 
                                 if R1 == tournament_hosts[1] or R4 == tournament_hosts[1]: sf_game1_teams = matchup1; sf_game2_teams = matchup2
                                 else: sf_game1_teams = matchup2; sf_game2_teams = matchup1
                        
                        if not primary_host_plays_sf1: 
                            sf_game1_teams = matchup1; sf_game2_teams = matchup2

                        sf_game_obj_1 = games_dict_by_num.get(sf_game_numbers[0])
                        sf_game_obj_2 = games_dict_by_num.get(sf_game_numbers[1])

                        if sf_game_obj_1 and sf_game_obj_2 and sf_game1_teams and sf_game2_teams:
                            if playoff_team_map.get(sf_game_obj_1.team1_code) != sf_game1_teams[0]:
                                playoff_team_map[sf_game_obj_1.team1_code] = sf_game1_teams[0]
                            if playoff_team_map.get(sf_game_obj_1.team2_code) != sf_game1_teams[1]:
                                playoff_team_map[sf_game_obj_1.team2_code] = sf_game1_teams[1]
                            if playoff_team_map.get(sf_game_obj_2.team1_code) != sf_game2_teams[0]:
                                playoff_team_map[sf_game_obj_2.team1_code] = sf_game2_teams[0]
                            if playoff_team_map.get(sf_game_obj_2.team2_code) != sf_game2_teams[1]:
                                playoff_team_map[sf_game_obj_2.team2_code] = sf_game2_teams[1]
                            
                            playoff_team_map['Q1'] = sf_game1_teams[0]
                            playoff_team_map['Q2'] = sf_game1_teams[1]
                            playoff_team_map['Q3'] = sf_game2_teams[0]
                            playoff_team_map['Q4'] = sf_game2_teams[1]

            # Sammle alle aufgelösten Spiele
            for game in games_raw:
                if game.team1_score is not None and game.team2_score is not None:
                    resolved_team1_code = get_resolved_code(game.team1_code, playoff_team_map)
                    resolved_team2_code = get_resolved_code(game.team2_code, playoff_team_map)
                    
                    all_resolved_games.append({
                        'game': game,
                        'team1_code': resolved_team1_code,
                        'team2_code': resolved_team2_code,
                        'year': year_obj.year
                    })
                        
        except Exception as e:
            # Fallback: Verwende nur Spiele mit finalen Team-Codes
            for game in Game.query.filter_by(year_id=year_obj.id).all():
                if (game.team1_score is not None and game.team2_score is not None and
                    is_code_final(game.team1_code) and is_code_final(game.team2_code)):
                    all_resolved_games.append({
                        'game': game,
                        'team1_code': game.team1_code,
                        'team2_code': game.team2_code,
                        'year': year_obj.year
                    })

    return all_resolved_games

def get_resolved_team_info(team_code, game=None):
    """
    Hilfsfunktion um Team-Codes zu bereinigen und ISO-Codes zu holen
    """
    if not team_code:
        return team_code, None
    
    # Versuche Team-Code zu bereinigen falls es ein Platzhalter ist
    if game and game.year_id:
        try:
            year_obj = db.session.query(ChampionshipYear).filter_by(id=game.year_id).first()
            if year_obj:
                all_games = db.session.query(Game).filter_by(year_id=game.year_id).all()
                resolved_team1, resolved_team2 = resolve_game_participants(game, year_obj, all_games)
                
                # Bestimme welcher der beiden Teams der gewünschte ist
                if game.team1_code == team_code:
                    team_code = resolved_team1
                elif game.team2_code == team_code:
                    team_code = resolved_team2
        except:
            # Fallback auf ursprünglichen Code wenn Auflösung fehlschlägt
            pass
    
    # Hole ISO-Code für Flagge
    iso_code = TEAM_ISO_CODES.get(team_code)
    
    return team_code, iso_code

@record_bp.route('/records')
def records_view():
    """Rekorde-Seite mit verschiedenen Rekordkategorien"""
    
    # Alle Zeit Rekorde
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
    
    # Pro Turnier Rekorde - Allgemein
    tournament_most_goals = get_tournament_with_most_goals()
    tournament_least_goals = get_tournament_with_least_goals()
    
    # Pro Turnier Rekorde - Team
    most_goals_team_tournament = get_most_goals_team_tournament()
    fewest_goals_against_tournament = get_fewest_goals_against_tournament()
    most_shutouts_tournament = get_most_shutouts_tournament()
    
    # Pro Turnier Rekorde - Spieler
    most_scorers_tournament = get_most_scorers_tournament()
    most_goals_player_tournament = get_most_goals_player_tournament()
    most_assists_player_tournament = get_most_assists_player_tournament()
    most_penalty_minutes_tournament = get_most_penalty_minutes_tournament()
    
    return render_template('records.html',
                           # Alle Zeit Rekorde
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
                           # Pro Turnier - Allgemein
                           tournament_most_goals=tournament_most_goals,
                           tournament_least_goals=tournament_least_goals,
                           # Pro Turnier - Team
                           most_goals_team_tournament=most_goals_team_tournament,
                           fewest_goals_against_tournament=fewest_goals_against_tournament,
                           most_shutouts_tournament=most_shutouts_tournament,
                           # Pro Turnier - Spieler
                           most_scorers_tournament=most_scorers_tournament,
                           most_goals_player_tournament=most_goals_player_tournament,
                           most_assists_player_tournament=most_assists_player_tournament,
                           most_penalty_minutes_tournament=most_penalty_minutes_tournament,
                           # Team ISO codes für Flaggen
                           team_iso_codes=TEAM_ISO_CODES)

def get_longest_win_streak():
    """Berechnet die längste Siegesserie über alle Turniere"""
    resolved_games = get_all_resolved_games()
    # Sortiere nach Jahr, Datum und Spiel-Nummer für korrekte chronologische Reihenfolge
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
            if team_streaks[winner] == 0:  # Neue Serie beginnt
                team_streak_start[winner] = game.date
            team_streaks[winner] += 1
            team_streak_end[winner] = game.date
            
            team_streaks[loser] = 0
            team_streak_start[loser] = None
            team_streak_end[loser] = None
            
            # Prüfe ob das ein neuer Rekord ist
            if not max_streaks or team_streaks[winner] > max_streaks[0]['streak']:
                max_streaks = [{
                    'team': winner, 
                    'streak': team_streaks[winner],
                    'start_date': team_streak_start[winner],
                    'end_date': team_streak_end[winner]
                }]
            elif team_streaks[winner] == max_streaks[0]['streak']:
                new_record = {
                    'team': winner, 
                    'streak': team_streaks[winner],
                    'start_date': team_streak_start[winner],
                    'end_date': team_streak_end[winner]
                }
                if new_record not in max_streaks:
                    max_streaks.append(new_record)
    
    return max_streaks

def get_longest_loss_streak():
    """Berechnet die längste Niederlagenserie über alle Turniere"""
    resolved_games = get_all_resolved_games()
    # Sortiere nach Jahr, Datum und Spiel-Nummer für korrekte chronologische Reihenfolge
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
            if team_streaks[loser] == 0:  # Neue Serie beginnt
                team_streak_start[loser] = game.date
            team_streaks[loser] += 1
            team_streak_end[loser] = game.date
            
            team_streaks[winner] = 0
            team_streak_start[winner] = None
            team_streak_end[winner] = None
            
            # Prüfe ob das ein neuer Rekord ist
            if not max_streaks or team_streaks[loser] > max_streaks[0]['streak']:
                max_streaks = [{
                    'team': loser, 
                    'streak': team_streaks[loser],
                    'start_date': team_streak_start[loser],
                    'end_date': team_streak_end[loser]
                }]
            elif team_streaks[loser] == max_streaks[0]['streak']:
                new_record = {
                    'team': loser, 
                    'streak': team_streaks[loser],
                    'start_date': team_streak_start[loser],
                    'end_date': team_streak_end[loser]
                }
                if new_record not in max_streaks:
                    max_streaks.append(new_record)
    
    return max_streaks

def get_longest_scoring_streak():
    """Berechnet die längste Serie mit mindestens 1 Tor"""
    resolved_games = get_all_resolved_games()
    # Sortiere nach Jahr, Datum und Spiel-Nummer für korrekte chronologische Reihenfolge
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
        
        # Team1 hat mindestens 1 Tor geschossen
        if game.team1_score > 0:
            if team_streaks[team1_code] == 0:  # Neue Serie beginnt
                team_streak_start[team1_code] = game.date
            team_streaks[team1_code] += 1
            team_streak_end[team1_code] = game.date
        else:
            team_streaks[team1_code] = 0
            team_streak_start[team1_code] = None
            team_streak_end[team1_code] = None
            
        # Team2 hat mindestens 1 Tor geschossen
        if game.team2_score > 0:
            if team_streaks[team2_code] == 0:  # Neue Serie beginnt
                team_streak_start[team2_code] = game.date
            team_streaks[team2_code] += 1
            team_streak_end[team2_code] = game.date
        else:
            team_streaks[team2_code] = 0
            team_streak_start[team2_code] = None
            team_streak_end[team2_code] = None
        
        # Prüfe beide Teams für neue Rekorde
        for team in [team1_code, team2_code]:
            if not max_streaks or team_streaks[team] > max_streaks[0]['streak']:
                max_streaks = [{
                    'team': team, 
                    'streak': team_streaks[team],
                    'start_date': team_streak_start[team],
                    'end_date': team_streak_end[team]
                }]
            elif team_streaks[team] == max_streaks[0]['streak'] and team_streaks[team] > 0:
                new_record = {
                    'team': team, 
                    'streak': team_streaks[team],
                    'start_date': team_streak_start[team],
                    'end_date': team_streak_end[team]
                }
                if new_record not in max_streaks:
                    max_streaks.append(new_record)
    
    return max_streaks

def get_longest_shutout_streak():
    """Berechnet die längste Serie ohne Gegentor"""
    resolved_games = get_all_resolved_games()
    # Sortiere nach Jahr, Datum und Spiel-Nummer für korrekte chronologische Reihenfolge
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
        
        # Team1 bekommt kein Gegentor
        if game.team2_score == 0:
            if team_streaks[team1_code] == 0:  # Neue Serie beginnt
                team_streak_start[team1_code] = game.date
            team_streaks[team1_code] += 1
            team_streak_end[team1_code] = game.date
        else:
            team_streaks[team1_code] = 0
            team_streak_start[team1_code] = None
            team_streak_end[team1_code] = None
            
        # Team2 bekommt kein Gegentor
        if game.team1_score == 0:
            if team_streaks[team2_code] == 0:  # Neue Serie beginnt
                team_streak_start[team2_code] = game.date
            team_streaks[team2_code] += 1
            team_streak_end[team2_code] = game.date
        else:
            team_streaks[team2_code] = 0
            team_streak_start[team2_code] = None
            team_streak_end[team2_code] = None
        
        # Prüfe beide Teams für neue Rekorde
        for team in [team1_code, team2_code]:
            if not max_streaks or team_streaks[team] > max_streaks[0]['streak']:
                max_streaks = [{
                    'team': team, 
                    'streak': team_streaks[team],
                    'start_date': team_streak_start[team],
                    'end_date': team_streak_end[team]
                }]
            elif team_streaks[team] == max_streaks[0]['streak'] and team_streaks[team] > 0:
                new_record = {
                    'team': team, 
                    'streak': team_streaks[team],
                    'start_date': team_streak_start[team],
                    'end_date': team_streak_end[team]
                }
                if new_record not in max_streaks:
                    max_streaks.append(new_record)
    
    return max_streaks

def get_longest_goalless_streak():
    """Berechnet die längste Serie ohne eigenes Tor"""
    resolved_games = get_all_resolved_games()
    # Sortiere nach Jahr, Datum und Spiel-Nummer für korrekte chronologische Reihenfolge
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
        
        # Team1 schießt kein Tor
        if game.team1_score == 0:
            if team_streaks[team1_code] == 0:  # Neue Serie beginnt
                team_streak_start[team1_code] = game.date
            team_streaks[team1_code] += 1
            team_streak_end[team1_code] = game.date
        else:
            team_streaks[team1_code] = 0
            team_streak_start[team1_code] = None
            team_streak_end[team1_code] = None
            
        # Team2 schießt kein Tor
        if game.team2_score == 0:
            if team_streaks[team2_code] == 0:  # Neue Serie beginnt
                team_streak_start[team2_code] = game.date
            team_streaks[team2_code] += 1
            team_streak_end[team2_code] = game.date
        else:
            team_streaks[team2_code] = 0
            team_streak_start[team2_code] = None
            team_streak_end[team2_code] = None
        
        # Prüfe beide Teams für neue Rekorde
        for team in [team1_code, team2_code]:
            if not max_streaks or team_streaks[team] > max_streaks[0]['streak']:
                max_streaks = [{
                    'team': team, 
                    'streak': team_streaks[team],
                    'start_date': team_streak_start[team],
                    'end_date': team_streak_end[team]
                }]
            elif team_streaks[team] == max_streaks[0]['streak'] and team_streaks[team] > 0:
                new_record = {
                    'team': team, 
                    'streak': team_streaks[team],
                    'start_date': team_streak_start[team],
                    'end_date': team_streak_end[team]
                }
                if new_record not in max_streaks:
                    max_streaks.append(new_record)
    
    return max_streaks

def get_highest_victory():
    """Findet den höchsten Sieg (größte Tordifferenz)"""
    resolved_games = get_all_resolved_games()
    
    if not resolved_games:
        return []
    
    # Berechne Tordifferenzen
    game_diffs = []
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        diff = abs(game.team1_score - game.team2_score)
        game_diffs.append({
            'game': game,
            'team1_code': team1_code,
            'team2_code': team2_code,
            'year': year,
            'difference': diff
        })
    
    # Sortiere nach Differenz
    game_diffs.sort(key=lambda x: x['difference'], reverse=True)
    
    if not game_diffs:
        return []
    
    max_diff = game_diffs[0]['difference']
    results = []
    
    for game_diff in game_diffs:
        if game_diff['difference'] == max_diff:
            game = game_diff['game']
            team1_code = game_diff['team1_code']
            team2_code = game_diff['team2_code']
            year = game_diff['year']
            
            if game.team1_score > game.team2_score:
                winner = team1_code
                winner_score = game.team1_score
                loser = team2_code
                loser_score = game.team2_score
            else:
                winner = team2_code
                winner_score = game.team2_score
                loser = team1_code
                loser_score = game.team1_score
            
            year_obj = db.session.query(ChampionshipYear).filter_by(id=game.year_id).first()
            results.append({
                'winner': winner,
                'winner_score': winner_score,
                'loser': loser,
                'loser_score': loser_score,
                'difference': game_diff['difference'],
                'year': year or 'Unknown',
                'tournament': year_obj.name if year_obj else 'Unknown'
            })
        else:
            break
    
    return results

def get_most_goals_game():
    """Findet das Spiel mit den meisten Toren"""
    resolved_games = get_all_resolved_games()
    
    if not resolved_games:
        return []
    
    # Berechne Gesamttore
    game_totals = []
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        total_goals = game.team1_score + game.team2_score
        game_totals.append({
            'game': game,
            'team1_code': team1_code,
            'team2_code': team2_code,
            'year': year,
            'total_goals': total_goals
        })
    
    # Sortiere nach Gesamttoren
    game_totals.sort(key=lambda x: x['total_goals'], reverse=True)
    
    if not game_totals:
        return []
    
    max_goals = game_totals[0]['total_goals']
    results = []
    
    for game_total in game_totals:
        if game_total['total_goals'] == max_goals:
            game = game_total['game']
            team1_code = game_total['team1_code']
            team2_code = game_total['team2_code']
            year = game_total['year']
            
            year_obj = db.session.query(ChampionshipYear).filter_by(id=game.year_id).first()
            results.append({
                'team1': team1_code,
                'team1_score': game.team1_score,
                'team2': team2_code,
                'team2_score': game.team2_score,
                'total_goals': game_total['total_goals'],
                'year': year or 'Unknown',
                'tournament': year_obj.name if year_obj else 'Unknown'
            })
        else:
            break
    
    return results

def get_fastest_goal():
    """Findet die TOP 3 schnellsten Tore (basierend auf Minute)"""
    def parse_minute(minute_str):
        if not minute_str:
            return 999
        # Extrahiere Zahlen aus Strings wie "1:23", "12:34", "0:45"
        match = re.match(r'(\d+):(\d+)', minute_str)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            return minutes * 60 + seconds
        # Falls nur Minuten angegeben sind
        try:
            return int(minute_str) * 60
        except:
            return 999
    
    goals = db.session.query(Goal).join(Player, Goal.scorer_id == Player.id).all()
    
    # Erstelle Liste mit allen Toren und deren Zeiten
    goal_times = []
    for goal in goals:
        time_seconds = parse_minute(goal.minute)
        game = db.session.query(Game).filter_by(id=goal.game_id).first()
        year = db.session.query(ChampionshipYear).filter_by(id=game.year_id).first() if game else None
        
        goal_times.append({
            'player': f"{goal.scorer.first_name} {goal.scorer.last_name}",
            'team': goal.team_code,
            'minute': goal.minute,
            'time_seconds': time_seconds,
            'year': year.year if year else 'Unknown',
            'tournament': year.name if year else 'Unknown',
            'vs_team': game.team2_code if game and game.team1_code == goal.team_code else (game.team1_code if game else 'Unknown'),
            'rank': 0
        })
    
    # Sortiere nach Zeit
    goal_times.sort(key=lambda x: x['time_seconds'])
    
    # Bestimme TOP 3 einzigartige Zeiten
    top_3_results = []
    current_rank = 1
    last_time = None
    
    for goal_time in goal_times:
        if last_time is None or goal_time['time_seconds'] != last_time:
            if current_rank > 3:
                break
            goal_time['rank'] = current_rank
            last_time = goal_time['time_seconds']
            current_rank += 1
        else:
            goal_time['rank'] = current_rank - 1  # Gleiche Zeit = gleicher Rang
        
        if goal_time['rank'] <= 3:
            top_3_results.append(goal_time)
    
    return top_3_results

def get_fastest_hattrick():
    """Findet die TOP 3 schnellsten Hattricks"""
    # Gruppiere Tore nach Spieler und Spiel
    goals = db.session.query(Goal).join(Player, Goal.scorer_id == Player.id).order_by(Goal.game_id, Goal.scorer_id, Goal.minute).all()
    
    player_game_goals = defaultdict(list)
    for goal in goals:
        key = (goal.scorer_id, goal.game_id)
        player_game_goals[key].append(goal)
    
    all_hattricks = []
    
    def parse_minute(minute_str):
        if not minute_str:
            return 999
        match = re.match(r'(\d+):(\d+)', minute_str)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            return minutes * 60 + seconds
        try:
            return int(minute_str) * 60
        except:
            return 999
    
    def format_duration(duration_seconds):
        """Konvertiert Sekunden in Minuten:Sekunden Format"""
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    for (player_id, game_id), game_goals in player_game_goals.items():
        if len(game_goals) >= 3:  # Mindestens Hattrick
            # Sortiere nach Zeit
            game_goals.sort(key=lambda g: parse_minute(g.minute))
            
            # Berechne Dauer des Hattricks (1. bis 3. Tor)
            first_goal_time = parse_minute(game_goals[0].minute)
            third_goal_time = parse_minute(game_goals[2].minute)
            duration = third_goal_time - first_goal_time
            
            player = db.session.query(Player).filter_by(id=player_id).first()
            game = db.session.query(Game).filter_by(id=game_id).first()
            year = db.session.query(ChampionshipYear).filter_by(id=game.year_id).first() if game else None
            
            all_hattricks.append({
                'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                'team': game_goals[0].team_code,
                'first_goal': game_goals[0].minute,
                'second_goal': game_goals[1].minute,
                'third_goal': game_goals[2].minute,
                'duration_seconds': duration,
                'duration_formatted': format_duration(duration),
                'year': year.year if year else 'Unknown',
                'tournament': year.name if year else 'Unknown',
                'vs_team': game.team2_code if game and game.team1_code == game_goals[0].team_code else (game.team1_code if game else 'Unknown'),
                'rank': 0
            })
    
    # Sortiere nach Dauer
    all_hattricks.sort(key=lambda x: x['duration_seconds'])
    
    # Bestimme TOP 3 einzigartige Dauern
    top_3_results = []
    current_rank = 1
    last_duration = None
    
    for hattrick in all_hattricks:
        if last_duration is None or hattrick['duration_seconds'] != last_duration:
            if current_rank > 3:
                break
            hattrick['rank'] = current_rank
            last_duration = hattrick['duration_seconds']
            current_rank += 1
        else:
            hattrick['rank'] = current_rank - 1  # Gleiche Dauer = gleicher Rang
        
        if hattrick['rank'] <= 3:
            top_3_results.append(hattrick)
    
    return top_3_results

def get_most_consecutive_tournament_wins():
    """Findet die meisten Turniersiege in Folge basierend auf Gold Medal Game Gewinnern"""
    resolved_games = get_all_resolved_games()
    
    # Sammle alle Gold Medal Game Gewinner chronologisch
    tournament_winners = []
    year_winners = {}
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        # Prüfe ob es ein Final ist (Gold Medal Game)
        if (game.round and 
            game.round == 'Gold Medal Game' and
            game.team1_score is not None and 
            game.team2_score is not None):
            
            # Nur zählen wenn beide Teams finale Team-Codes haben
            if (is_code_final(team1_code) and is_code_final(team2_code) and
                team1_code != team2_code and year):
                
                # Bestimme den Gewinner
                if game.team1_score > game.team2_score:
                    winner = team1_code
                elif game.team2_score > game.team1_score:
                    winner = team2_code
                else:
                    continue  # Unentschieden ignorieren
                
                year_winners[year] = winner
    
    # Sortiere nach Jahren
    sorted_years = sorted(year_winners.keys())
    
    # Berechne aufeinanderfolgende Siege
    team_current_streak = defaultdict(int)
    team_current_years = defaultdict(list)
    team_max_streak = defaultdict(int)
    team_max_streak_years = defaultdict(list)
    
    for year in sorted_years:
        winner = year_winners[year]
        
        # Setze alle anderen Teams zurück
        for team in team_current_streak:
            if team != winner:
                team_current_streak[team] = 0
                team_current_years[team] = []
        
        # Erhöhe Streak für aktuellen Gewinner
        team_current_streak[winner] += 1
        team_current_years[winner].append(year)
        
        # Prüfe ob neuer Rekord
        if team_current_streak[winner] > team_max_streak[winner]:
            team_max_streak[winner] = team_current_streak[winner]
            team_max_streak_years[winner] = team_current_years[winner][:]
    
    if not team_max_streak:
        return []
    
    # Finde das Maximum
    max_streak = max(team_max_streak.values())
    results = []
    
    for team, streak in team_max_streak.items():
        if streak == max_streak:
            years = team_max_streak_years[team]
            results.append({
                'team': team, 
                'streak': streak,
                'years': years
            })
    
    return results

def get_most_final_appearances():
    """Berechnet die meisten Finalteilnahmen basierend auf echten Gold Medal Games"""
    resolved_games = get_all_resolved_games()
    team_final_appearances = defaultdict(int)
    team_final_years = defaultdict(list)
    
    # Suche nach Gold Medal Games (Finals) in allen aufgelösten Spielen
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        # Prüfe ob es ein Final ist (Gold Medal Game)
        if (game.round and 
            game.round == 'Gold Medal Game' and
            game.team1_score is not None and 
            game.team2_score is not None):
            
            # Nur zählen wenn beide Teams finale Team-Codes haben (nicht Platzhalter)
            # und das Spiel tatsächlich gespielt wurde
            if (is_code_final(team1_code) and is_code_final(team2_code) and
                team1_code != team2_code):  # Verhindere Duplikate
                
                team_final_appearances[team1_code] += 1
                team_final_appearances[team2_code] += 1
                
                if year:
                    team_final_years[team1_code].append(year)
                    team_final_years[team2_code].append(year)
    
    if not team_final_appearances:
        return []
    
    max_appearances = max(team_final_appearances.values())
    results = []
    
    for team, appearances in team_final_appearances.items():
        if appearances == max_appearances:
            years = sorted(list(set(team_final_years[team]))) if team in team_final_years else []
            results.append({
                'team': team, 
                'appearances': appearances,
                'years': years
            })
    
    return results

def get_record_champion():
    """Berechnet das Team mit den meisten Turniersiegen (Gold Medal Game Gewinner)"""
    resolved_games = get_all_resolved_games()
    team_championships = defaultdict(int)
    team_championship_years = defaultdict(list)
    
    # Suche nach Gold Medal Games (Finals) in allen aufgelösten Spielen
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        # Prüfe ob es ein Final ist (Gold Medal Game)
        if (game.round and 
            game.round == 'Gold Medal Game' and
            game.team1_score is not None and 
            game.team2_score is not None):
            
            # Nur zählen wenn beide Teams finale Team-Codes haben (nicht Platzhalter)
            # und das Spiel tatsächlich gespielt wurde
            if (is_code_final(team1_code) and is_code_final(team2_code) and
                team1_code != team2_code):  # Verhindere Duplikate
                
                # Bestimme den Gewinner
                if game.team1_score > game.team2_score:
                    winner = team1_code
                elif game.team2_score > game.team1_score:
                    winner = team2_code
                else:
                    continue  # Unentschieden ignorieren (sollte in Finals nicht vorkommen)
                
                team_championships[winner] += 1
                if year:
                    team_championship_years[winner].append(year)
    
    if not team_championships:
        return []
    
    max_championships = max(team_championships.values())
    results = []
    
    for team, championships in team_championships.items():
        if championships == max_championships:
            years = sorted(team_championship_years[team]) if team in team_championship_years else []
            results.append({
                'team': team, 
                'championships': championships,
                'years': years
            })
    
    return results

def get_tournament_with_most_goals():
    """Turnier mit den meisten Toren - nur beendete Turniere"""
    from routes.main_routes import get_tournament_statistics
    
    # Zuerst nur beendete Turniere ermitteln
    all_years = db.session.query(ChampionshipYear).all()
    completed_years = []
    
    for year_obj in all_years:
        tournament_stats = get_tournament_statistics(year_obj)
        is_completed = (tournament_stats['total_games'] > 0 and 
                       tournament_stats['completed_games'] == tournament_stats['total_games'])
        if is_completed:
            completed_years.append(year_obj)
    
    if not completed_years:
        return []
    
    # Berechne Tore nur für beendete Turniere
    tournament_goals = db.session.query(
        ChampionshipYear,
        func.sum(Game.team1_score + Game.team2_score).label('total_goals'),
        func.count(Game.id).label('games_count')
    ).join(Game, ChampionshipYear.id == Game.year_id).filter(
        Game.team1_score.isnot(None),
        Game.team2_score.isnot(None),
        ChampionshipYear.id.in_([year.id for year in completed_years])
    ).group_by(ChampionshipYear.id).order_by(desc('total_goals')).all()
    
    if not tournament_goals:
        return []
    
    max_goals = tournament_goals[0].total_goals
    results = []
    
    for year, total_goals, games in tournament_goals:
        if total_goals == max_goals:
            results.append({
                'tournament': year.name,
                'year': year.year,
                'total_goals': total_goals,
                'games': games,
                'goals_per_game': round(total_goals / games, 2) if games > 0 else 0
            })
        else:
            break
    
    return results

def get_tournament_with_least_goals():
    """Turnier mit den wenigsten Toren - nur beendete Turniere"""
    from routes.main_routes import get_tournament_statistics
    
    # Zuerst nur beendete Turniere ermitteln
    all_years = db.session.query(ChampionshipYear).all()
    completed_years = []
    
    for year_obj in all_years:
        tournament_stats = get_tournament_statistics(year_obj)
        is_completed = (tournament_stats['total_games'] > 0 and 
                       tournament_stats['completed_games'] == tournament_stats['total_games'])
        if is_completed:
            completed_years.append(year_obj)
    
    if not completed_years:
        return []
    
    # Berechne Tore nur für beendete Turniere
    tournament_goals = db.session.query(
        ChampionshipYear,
        func.sum(Game.team1_score + Game.team2_score).label('total_goals'),
        func.count(Game.id).label('games_count')
    ).join(Game, ChampionshipYear.id == Game.year_id).filter(
        Game.team1_score.isnot(None),
        Game.team2_score.isnot(None),
        ChampionshipYear.id.in_([year.id for year in completed_years])
    ).group_by(ChampionshipYear.id).order_by(asc('total_goals')).all()
    
    if not tournament_goals:
        return []
    
    min_goals = tournament_goals[0].total_goals
    results = []
    
    for year, total_goals, games in tournament_goals:
        if total_goals == min_goals:
            results.append({
                'tournament': year.name,
                'year': year.year,
                'total_goals': total_goals,
                'games': games,
                'goals_per_game': round(total_goals / games, 2) if games > 0 else 0
            })
        else:
            break
    
    return results

def get_most_goals_team_tournament():
    """Meiste Tore eines Teams in einem Turnier"""
    resolved_games = get_all_resolved_games()
    
    # Berechnung mit aufgelösten Team-Codes und Jahr-Objekten für echte Turniernamen
    team_goals_by_tournament = defaultdict(lambda: defaultdict(int))
    year_objects = {year.year: year for year in ChampionshipYear.query.all()}
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        if year and is_code_final(team1_code) and is_code_final(team2_code):
            year_key = f"{year}"
            team_goals_by_tournament[year_key][team1_code] += game.team1_score
            team_goals_by_tournament[year_key][team2_code] += game.team2_score
    
    max_goals = 0
    results = []
    
    for year_key, teams in team_goals_by_tournament.items():
        year_int = int(year_key) if year_key.isdigit() else None
        year_obj = year_objects.get(year_int) if year_int else None
        tournament_name = year_obj.name if year_obj else f"IIHF {year_key}"
        
        for team, goals in teams.items():
            if goals > max_goals:
                max_goals = goals
                results = [{
                    'team': team,
                    'goals': goals,
                    'tournament': tournament_name,
                    'year': year_int or year_key
                }]
            elif goals == max_goals:
                results.append({
                    'team': team,
                    'goals': goals,
                    'tournament': tournament_name,
                    'year': year_int or year_key
                })
    
    return results

def get_fewest_goals_against_tournament():
    """Wenigste Gegentore eines Teams in einem Turnier - nur beendete Turniere"""
    from routes.main_routes import get_tournament_statistics
    
    # Zuerst nur beendete Turniere ermitteln
    all_years = db.session.query(ChampionshipYear).all()
    completed_years = []
    
    for year_obj in all_years:
        tournament_stats = get_tournament_statistics(year_obj)
        is_completed = (tournament_stats['total_games'] > 0 and 
                       tournament_stats['completed_games'] == tournament_stats['total_games'])
        if is_completed:
            completed_years.append(year_obj)
    
    if not completed_years:
        return []
    
    team_goals_against_by_tournament = defaultdict(lambda: defaultdict(int))
    
    # Verwende aufgelöste Spiele statt ursprüngliche Team-Codes
    resolved_games = get_all_resolved_games()
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        # Nur beendete Turniere berücksichtigen
        year_obj = next((y for y in completed_years if y.year == year), None)
        if year_obj and is_code_final(team1_code) and is_code_final(team2_code):
            team_goals_against_by_tournament[year_obj.id][team1_code] += game.team2_score
            team_goals_against_by_tournament[year_obj.id][team2_code] += game.team1_score
    
    min_goals_against = None
    results = []
    
    for year_id, teams in team_goals_against_by_tournament.items():
        year = db.session.query(ChampionshipYear).filter_by(id=year_id).first()
        for team, goals_against in teams.items():
            if min_goals_against is None or goals_against < min_goals_against:
                min_goals_against = goals_against
                results = [{
                    'team': team,
                    'goals_against': goals_against,
                    'tournament': year.name,
                    'year': year.year
                }]
            elif goals_against == min_goals_against:
                results.append({
                    'team': team,
                    'goals_against': goals_against,
                    'tournament': year.name,
                    'year': year.year
                })
    
    return results

def get_most_shutouts_tournament():
    """Meiste Shutouts eines Teams in einem Turnier"""
    resolved_games = get_all_resolved_games()
    
    team_shutouts_by_tournament = defaultdict(lambda: defaultdict(int))
    year_objects = {year.year: year for year in ChampionshipYear.query.all()}
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        if year and is_code_final(team1_code) and is_code_final(team2_code):
            year_key = f"{year}"
            if game.team2_score == 0:  # Team1 hat Shutout
                team_shutouts_by_tournament[year_key][team1_code] += 1
            if game.team1_score == 0:  # Team2 hat Shutout
                team_shutouts_by_tournament[year_key][team2_code] += 1
    
    max_shutouts = 0
    results = []
    
    for year_key, teams in team_shutouts_by_tournament.items():
        year_int = int(year_key) if year_key.isdigit() else None
        year_obj = year_objects.get(year_int) if year_int else None
        tournament_name = year_obj.name if year_obj else f"IIHF {year_key}"
        
        for team, shutouts in teams.items():
            if shutouts > max_shutouts:
                max_shutouts = shutouts
                results = [{
                    'team': team,
                    'shutouts': shutouts,
                    'tournament': tournament_name,
                    'year': year_int or year_key
                }]
            elif shutouts == max_shutouts:
                results.append({
                    'team': team,
                    'shutouts': shutouts,
                    'tournament': tournament_name,
                    'year': year_int or year_key
                })
    
    return results

def get_most_scorers_tournament():
    """Meiste Scorer (Tore + Assists) eines Spielers in einem Turnier"""
    player_points_by_tournament = defaultdict(lambda: defaultdict(int))
    
    years = db.session.query(ChampionshipYear).all()
    for year in years:
        goals = db.session.query(Goal).join(Game).filter(Game.year_id == year.id).all()
        
        for goal in goals:
            # Tor = 1 Punkt
            player_points_by_tournament[year.id][goal.scorer_id] += 1
            
            # Assists = 1 Punkt jeweils
            if goal.assist1_id:
                player_points_by_tournament[year.id][goal.assist1_id] += 1
            if goal.assist2_id:
                player_points_by_tournament[year.id][goal.assist2_id] += 1
    
    max_points = 0
    results = []
    
    for year_id, players in player_points_by_tournament.items():
        year = db.session.query(ChampionshipYear).filter_by(id=year_id).first()
        for player_id, points in players.items():
            player = db.session.query(Player).filter_by(id=player_id).first()
            if points > max_points:
                max_points = points
                results = [{
                    'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                    'team': player.team_code if player else 'Unknown',
                    'points': points,
                    'tournament': year.name,
                    'year': year.year
                }]
            elif points == max_points:
                results.append({
                    'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                    'team': player.team_code if player else 'Unknown',
                    'points': points,
                    'tournament': year.name,
                    'year': year.year
                })
    
    return results

def get_most_goals_player_tournament():
    """Meiste Tore eines Spielers in einem Turnier"""
    player_goals_by_tournament = defaultdict(lambda: defaultdict(int))
    
    years = db.session.query(ChampionshipYear).all()
    for year in years:
        goals = db.session.query(Goal).join(Game).filter(Game.year_id == year.id).all()
        
        for goal in goals:
            player_goals_by_tournament[year.id][goal.scorer_id] += 1
    
    max_goals = 0
    results = []
    
    for year_id, players in player_goals_by_tournament.items():
        year = db.session.query(ChampionshipYear).filter_by(id=year_id).first()
        for player_id, goals in players.items():
            player = db.session.query(Player).filter_by(id=player_id).first()
            if goals > max_goals:
                max_goals = goals
                results = [{
                    'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                    'team': player.team_code if player else 'Unknown',
                    'goals': goals,
                    'tournament': year.name,
                    'year': year.year
                }]
            elif goals == max_goals:
                results.append({
                    'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                    'team': player.team_code if player else 'Unknown',
                    'goals': goals,
                    'tournament': year.name,
                    'year': year.year
                })
    
    return results

def get_most_assists_player_tournament():
    """Meiste Assists eines Spielers in einem Turnier"""
    player_assists_by_tournament = defaultdict(lambda: defaultdict(int))
    
    years = db.session.query(ChampionshipYear).all()
    for year in years:
        goals = db.session.query(Goal).join(Game).filter(Game.year_id == year.id).all()
        
        for goal in goals:
            if goal.assist1_id:
                player_assists_by_tournament[year.id][goal.assist1_id] += 1
            if goal.assist2_id:
                player_assists_by_tournament[year.id][goal.assist2_id] += 1
    
    max_assists = 0
    results = []
    
    for year_id, players in player_assists_by_tournament.items():
        year = db.session.query(ChampionshipYear).filter_by(id=year_id).first()
        for player_id, assists in players.items():
            player = db.session.query(Player).filter_by(id=player_id).first()
            if assists > max_assists:
                max_assists = assists
                results = [{
                    'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                    'team': player.team_code if player else 'Unknown',
                    'assists': assists,
                    'tournament': year.name,
                    'year': year.year
                }]
            elif assists == max_assists:
                results.append({
                    'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                    'team': player.team_code if player else 'Unknown',
                    'assists': assists,
                    'tournament': year.name,
                    'year': year.year
                })
    
    return results

def get_most_penalty_minutes_tournament():
    """Meiste Strafminuten eines Spielers in einem Turnier"""
    from constants import PIM_MAP
    
    player_pim_by_tournament = defaultdict(lambda: defaultdict(int))
    
    years = db.session.query(ChampionshipYear).all()
    for year in years:
        penalties = db.session.query(Penalty).join(Game).filter(Game.year_id == year.id).all()
        
        for penalty in penalties:
            if penalty.player_id:
                # Verwende die korrekte PIM_MAP aus constants.py
                minutes = PIM_MAP.get(penalty.penalty_type, 0)
                player_pim_by_tournament[year.id][penalty.player_id] += minutes
    
    max_pim = 0
    results = []
    
    for year_id, players in player_pim_by_tournament.items():
        year = db.session.query(ChampionshipYear).filter_by(id=year_id).first()
        for player_id, pim in players.items():
            player = db.session.query(Player).filter_by(id=player_id).first()
            if pim > max_pim:
                max_pim = pim
                results = [{
                    'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                    'team': player.team_code if player else 'Unknown',
                    'pim': pim,
                    'tournament': year.name,
                    'year': year.year
                }]
            elif pim == max_pim:
                results.append({
                    'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                    'team': player.team_code if player else 'Unknown',
                    'pim': pim,
                    'tournament': year.name,
                    'year': year.year
                })
    
    return results