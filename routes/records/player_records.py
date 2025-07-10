from collections import defaultdict
from models import db, Goal, Player, ChampionshipYear, Game, Penalty
from constants import PIM_MAP


def get_most_scorers_tournament():
    """Meiste Scorer (Tore + Assists) eines Spielers in einem Turnier"""
    player_points_by_tournament = defaultdict(lambda: defaultdict(int))
    
    years = db.session.query(ChampionshipYear).all()
    for year in years:
        goals = db.session.query(Goal).join(Game).filter(Game.year_id == year.id).all()
        
        for goal in goals:
            player_points_by_tournament[year.id][goal.scorer_id] += 1
            
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
    player_pim_by_tournament = defaultdict(lambda: defaultdict(int))
    
    years = db.session.query(ChampionshipYear).all()
    for year in years:
        penalties = db.session.query(Penalty).join(Game).filter(Game.year_id == year.id).all()
        
        for penalty in penalties:
            if penalty.player_id:
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