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
    
    # Collect all player performances
    all_performances = []
    
    for year_id, players in player_points_by_tournament.items():
        year = db.session.query(ChampionshipYear).filter_by(id=year_id).first()
        for player_id, points in players.items():
            player = db.session.query(Player).filter_by(id=player_id).first()
            all_performances.append({
                'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                'team': player.team_code if player else 'Unknown',
                'points': points,
                'tournament': year.name,
                'year': year.year
            })
    
    # Sort by points descending and return top 3
    all_performances.sort(key=lambda x: x['points'], reverse=True)
    return all_performances[:3]


def get_most_goals_player_tournament():
    """Meiste Tore eines Spielers in einem Turnier"""
    player_goals_by_tournament = defaultdict(lambda: defaultdict(int))
    
    years = db.session.query(ChampionshipYear).all()
    for year in years:
        goals = db.session.query(Goal).join(Game).filter(Game.year_id == year.id).all()
        
        for goal in goals:
            player_goals_by_tournament[year.id][goal.scorer_id] += 1
    
    # Collect all player performances
    all_performances = []
    
    for year_id, players in player_goals_by_tournament.items():
        year = db.session.query(ChampionshipYear).filter_by(id=year_id).first()
        for player_id, goals in players.items():
            player = db.session.query(Player).filter_by(id=player_id).first()
            all_performances.append({
                'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                'team': player.team_code if player else 'Unknown',
                'goals': goals,
                'tournament': year.name,
                'year': year.year
            })
    
    # Sort by goals descending and return top 3
    all_performances.sort(key=lambda x: x['goals'], reverse=True)
    return all_performances[:3]


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
    
    # Collect all player performances
    all_performances = []
    
    for year_id, players in player_assists_by_tournament.items():
        year = db.session.query(ChampionshipYear).filter_by(id=year_id).first()
        for player_id, assists in players.items():
            player = db.session.query(Player).filter_by(id=player_id).first()
            all_performances.append({
                'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                'team': player.team_code if player else 'Unknown',
                'assists': assists,
                'tournament': year.name,
                'year': year.year
            })
    
    # Sort by assists descending and return top 3
    all_performances.sort(key=lambda x: x['assists'], reverse=True)
    return all_performances[:3]


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
    
    # Collect all player performances
    all_performances = []
    
    for year_id, players in player_pim_by_tournament.items():
        year = db.session.query(ChampionshipYear).filter_by(id=year_id).first()
        for player_id, pim in players.items():
            player = db.session.query(Player).filter_by(id=player_id).first()
            all_performances.append({
                'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                'team': player.team_code if player else 'Unknown',
                'pim': pim,
                'tournament': year.name,
                'year': year.year
            })
    
    # Sort by penalty minutes descending and return top 3
    all_performances.sort(key=lambda x: x['pim'], reverse=True)
    return all_performances[:3]