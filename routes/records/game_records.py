from models import db, ChampionshipYear
from collections import defaultdict
from utils import is_code_final
from .utils import get_all_resolved_games
from app.services.core.records_service import RecordsService


def get_highest_victory(records_data=None):
    """Findet die TOP 3 höchsten Siege (größte Tordifferenzen)"""
    # Service Layer verwenden
    records_service = RecordsService()
    
    try:
        # Hole Team-Rekorde über Service
        team_records = records_service.get_team_records(limit=3)
        biggest_wins = team_records.get('biggest_wins', [])
        
        # Formatiere für Anzeige mit Rang
        top_3_results = []
        current_rank = 1
        last_diff = None
        
        for idx, win in enumerate(biggest_wins[:3]):
            if last_diff is None or win['goal_diff'] != last_diff:
                current_rank = idx + 1
                last_diff = win['goal_diff']
            
            top_3_results.append({
                'winner': win['winner'],
                'winner_score': win['winner_score'],
                'loser': win['loser'],
                'loser_score': win['loser_score'],
                'difference': win['goal_diff'],
                'year': win['year'],
                'tournament': win['tournament'],
                'rank': current_rank
            })
        
        return top_3_results
    except Exception as e:
        # Fallback auf alte Implementierung bei Fehler
        if records_data is None:
            resolved_games = get_all_resolved_games()
        else:
            resolved_games = records_data['resolved_games']
        
        if not resolved_games:
            return []
        
        game_diffs = []
        for resolved_game in resolved_games:
            game = resolved_game['game']
            team1_code = resolved_game['team1_code']
            team2_code = resolved_game['team2_code']
            year = resolved_game['year']
            
            diff = abs(game.team1_score - game.team2_score)
            
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
            game_diffs.append({
                'winner': winner,
                'winner_score': winner_score,
                'loser': loser,
                'loser_score': loser_score,
                'difference': diff,
                'year': year or 'Unknown',
                'tournament': year_obj.name if year_obj else 'Unknown',
                'rank': 0
            })
        
        game_diffs.sort(key=lambda x: x['difference'], reverse=True)
        
        if not game_diffs:
            return []
        
        top_3_results = []
        current_rank = 1
        last_diff = None
        
        for game_diff in game_diffs:
            if last_diff is None or game_diff['difference'] != last_diff:
                if len(top_3_results) >= 3:
                    break
                if current_rank > 3:
                    break
                game_diff['rank'] = current_rank
                last_diff = game_diff['difference']
                current_rank += 1
            else:
                game_diff['rank'] = current_rank - 1
            
            if game_diff['rank'] <= 3:
                top_3_results.append(game_diff)
        
        return top_3_results


def get_most_goals_game(records_data=None):
    """Findet die TOP 3 Spiele mit den meisten Toren"""
    # Service Layer verwenden
    records_service = RecordsService()
    
    try:
        # Hole Spiel-Rekorde über Service
        game_records = records_service.get_game_records(limit=3)
        most_goals = game_records.get('most_goals_combined', [])
        
        # Formatiere für Anzeige mit Rang
        top_3_results = []
        current_rank = 1
        last_goals = None
        
        for idx, game in enumerate(most_goals[:3]):
            if last_goals is None or game['total_goals'] != last_goals:
                current_rank = idx + 1
                last_goals = game['total_goals']
            
            # Parse Teams aus dem Format "TEAM1 vs TEAM2"
            teams = game['teams'].split(' vs ')
            team1 = teams[0] if len(teams) > 0 else 'Unknown'
            team2 = teams[1] if len(teams) > 1 else 'Unknown'
            
            # Parse Scores aus dem Format "X:Y"
            scores = game['score'].split(':')
            team1_score = int(scores[0]) if len(scores) > 0 else 0
            team2_score = int(scores[1]) if len(scores) > 1 else 0
            
            top_3_results.append({
                'team1': team1,
                'team1_score': team1_score,
                'team2': team2,
                'team2_score': team2_score,
                'total_goals': game['total_goals'],
                'year': game['year'],
                'tournament': game['tournament'],
                'rank': current_rank
            })
        
        return top_3_results
    except Exception as e:
        # Fallback auf alte Implementierung bei Fehler
        if records_data is None:
            resolved_games = get_all_resolved_games()
        else:
            resolved_games = records_data['resolved_games']
        
        if not resolved_games:
            return []
        
        game_totals = []
        for resolved_game in resolved_games:
            game = resolved_game['game']
            team1_code = resolved_game['team1_code']
            team2_code = resolved_game['team2_code']
            year = resolved_game['year']
            
            total_goals = game.team1_score + game.team2_score
            year_obj = db.session.query(ChampionshipYear).filter_by(id=game.year_id).first()
            
            game_totals.append({
                'team1': team1_code,
                'team1_score': game.team1_score,
                'team2': team2_code,
                'team2_score': game.team2_score,
                'total_goals': total_goals,
                'year': year or 'Unknown',
                'tournament': year_obj.name if year_obj else 'Unknown',
                'rank': 0
            })
        
        game_totals.sort(key=lambda x: x['total_goals'], reverse=True)
        
        if not game_totals:
            return []
        
        top_3_results = []
        current_rank = 1
        last_goals = None
        
        for game_total in game_totals:
            if last_goals is None or game_total['total_goals'] != last_goals:
                if len(top_3_results) >= 3:
                    break
                if current_rank > 3:
                    break
                game_total['rank'] = current_rank
                last_goals = game_total['total_goals']
                current_rank += 1
            else:
                game_total['rank'] = current_rank - 1
            
            if game_total['rank'] <= 3:
                top_3_results.append(game_total)
        
        return top_3_results


def get_most_frequent_matchup(records_data=None):
    """Findet die TOP 3 häufigsten Duelle über alle Turniere"""
    if records_data is None:
        resolved_games = get_all_resolved_games()
    else:
        resolved_games = records_data['resolved_games']
    
    if not resolved_games:
        return []
    
    matchup_counts = defaultdict(int)
    matchup_examples = defaultdict(list)
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        # Nur finale Team-Codes verwenden
        if is_code_final(team1_code) and is_code_final(team2_code) and team1_code != team2_code:
            # Teams alphabetisch sortieren um sicherzustellen dass A vs B und B vs A als dasselbe Duell gezählt werden
            teams = sorted([team1_code, team2_code])
            matchup_key = f"{teams[0]} vs {teams[1]}"
            
            matchup_counts[matchup_key] += 1
            
            # Sammle alle Jahre für Zeitspanne
            matchup_examples[matchup_key].append(year if year else 0)
    
    if not matchup_counts:
        return []
    
    # Sortiere nach Häufigkeit
    sorted_matchups = sorted(matchup_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Zeige alle Duelle derselben Häufigkeit, bis mindestens 3 Duelle erreicht sind
    top_3_results = []
    current_rank = 1
    last_count = None
    
    for matchup, count in sorted_matchups:
        # Wenn wir schon mindestens 3 haben und eine neue (niedrigere) Häufigkeit beginnt, stoppe
        if len(top_3_results) >= 3 and count != last_count:
            break
            
        # Bestimme den Rang
        if last_count is None or count != last_count:
            rank = len(top_3_results) + 1
            last_count = count
        else:
            # Gleiche Häufigkeit - finde den Rang des ersten Elements mit dieser Häufigkeit
            rank = next(r['rank'] for r in top_3_results if r['count'] == count)
        
        # Füge das Duell hinzu
        teams = matchup.split(' vs ')
        
        # Berechne Zeitspanne
        years = [y for y in matchup_examples[matchup] if y > 0]
        if years:
            years.sort()
            timespan = f"{years[0]} - {years[-1]}" if len(years) > 1 and years[0] != years[-1] else str(years[0])
        else:
            timespan = "Unbekannt"
        
        result = {
            'team1': teams[0],
            'team2': teams[1],
            'count': count,
            'timespan': timespan,
            'rank': rank
        }
        top_3_results.append(result)
    
    return top_3_results