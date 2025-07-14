from collections import defaultdict
from models import db, Game, ChampionshipYear, Penalty
from sqlalchemy import func, case, desc, asc
from utils import is_code_final
from utils.data_validation import calculate_tournament_penalty_minutes
from .utils import get_all_resolved_games


def get_most_consecutive_tournament_wins():
    """Findet die meisten Turniersiege in Folge basierend auf Gold Medal Game Gewinnern"""
    resolved_games = get_all_resolved_games()
    
    tournament_winners = []
    year_winners = {}
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        if (game.round and game.round == 'Gold Medal Game' and
            game.team1_score is not None and game.team2_score is not None):
            
            if (is_code_final(team1_code) and is_code_final(team2_code) and
                team1_code != team2_code and year):
                
                if game.team1_score > game.team2_score:
                    winner = team1_code
                elif game.team2_score > game.team1_score:
                    winner = team2_code
                else:
                    continue
                
                year_winners[year] = winner
    
    sorted_years = sorted(year_winners.keys())
    
    team_current_streak = defaultdict(int)
    team_current_years = defaultdict(list)
    team_max_streak = defaultdict(int)
    team_max_streak_years = defaultdict(list)
    
    for year in sorted_years:
        winner = year_winners[year]
        
        for team in team_current_streak:
            if team != winner:
                team_current_streak[team] = 0
                team_current_years[team] = []
        
        team_current_streak[winner] += 1
        team_current_years[winner].append(year)
        
        if team_current_streak[winner] > team_max_streak[winner]:
            team_max_streak[winner] = team_current_streak[winner]
            team_max_streak_years[winner] = team_current_years[winner][:]
    
    if not team_max_streak:
        return []
    
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
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        if (game.round and game.round == 'Gold Medal Game' and
            game.team1_score is not None and game.team2_score is not None):
            
            if (is_code_final(team1_code) and is_code_final(team2_code) and
                team1_code != team2_code):
                
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
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        if (game.round and game.round == 'Gold Medal Game' and
            game.team1_score is not None and game.team2_score is not None):
            
            if (is_code_final(team1_code) and is_code_final(team2_code) and
                team1_code != team2_code):
                
                if game.team1_score > game.team2_score:
                    winner = team1_code
                elif game.team2_score > game.team1_score:
                    winner = team2_code
                else:
                    continue
                
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
    from .utils import get_tournament_statistics
    
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
    from .utils import get_tournament_statistics
    
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


def get_tournament_with_most_penalty_minutes():
    """Turnier mit den meisten Strafminuten - nur beendete Turniere"""
    from .utils import get_tournament_statistics
    
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
    
    # Berechne Strafminuten pro Turnier
    tournament_pim_data = []
    
    for year_obj in completed_years:
        # Berechne Strafminuten mit zentraler Funktion
        total_pim = calculate_tournament_penalty_minutes(year_obj.id, completed_games_only=True)
        
        # Anzahl der gespielten Spiele
        games_count = db.session.query(func.count(Game.id)).filter(
            Game.year_id == year_obj.id,
            Game.team1_score.isnot(None),
            Game.team2_score.isnot(None)
        ).scalar() or 0
        
        if games_count > 0:
            tournament_pim_data.append({
                'tournament': year_obj.name,
                'year': year_obj.year,
                'total_pim': total_pim,
                'games': games_count,
                'pim_per_game': round(total_pim / games_count, 2) if games_count > 0 else 0
            })
    
    if not tournament_pim_data:
        return []
    
    # Sortiere nach meisten Strafminuten
    tournament_pim_data.sort(key=lambda x: x['total_pim'], reverse=True)
    max_pim = tournament_pim_data[0]['total_pim']
    
    # Gib alle Turniere mit den meisten Strafminuten zurück
    results = []
    for data in tournament_pim_data:
        if data['total_pim'] == max_pim:
            results.append(data)
        else:
            break
    
    return results


def get_tournament_with_least_penalty_minutes():
    """Turnier mit den wenigsten Strafminuten - nur beendete Turniere"""
    from .utils import get_tournament_statistics
    
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
    
    # Berechne Strafminuten pro Turnier
    tournament_pim_data = []
    
    for year_obj in completed_years:
        # Berechne Strafminuten mit zentraler Funktion
        total_pim = calculate_tournament_penalty_minutes(year_obj.id, completed_games_only=True)
        
        # Anzahl der gespielten Spiele
        games_count = db.session.query(func.count(Game.id)).filter(
            Game.year_id == year_obj.id,
            Game.team1_score.isnot(None),
            Game.team2_score.isnot(None)
        ).scalar() or 0
        
        if games_count > 0:
            tournament_pim_data.append({
                'tournament': year_obj.name,
                'year': year_obj.year,
                'total_pim': total_pim,
                'games': games_count,
                'pim_per_game': round(total_pim / games_count, 2) if games_count > 0 else 0
            })
    
    if not tournament_pim_data:
        return []
    
    # Sortiere nach wenigsten Strafminuten
    tournament_pim_data.sort(key=lambda x: x['total_pim'])
    min_pim = tournament_pim_data[0]['total_pim']
    
    # Gib alle Turniere mit den wenigsten Strafminuten zurück
    results = []
    for data in tournament_pim_data:
        if data['total_pim'] == min_pim:
            results.append(data)
        else:
            break
    
    return results