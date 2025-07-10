from collections import defaultdict
from models import db, ChampionshipYear
from utils import is_code_final
from .utils import get_all_resolved_games


def get_most_goals_team_tournament():
    """Meiste Tore eines Teams in einem Turnier"""
    resolved_games = get_all_resolved_games()
    
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
    
    resolved_games = get_all_resolved_games()
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
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
            if game.team2_score == 0:
                team_shutouts_by_tournament[year_key][team1_code] += 1
            if game.team1_score == 0:
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