from collections import defaultdict
from models import db, Goal, Player, ChampionshipYear, Game, Penalty
from constants import PIM_MAP, TOP_3_DISPLAY
from app.services.core.records_service import RecordsService
from app.services.core.tournament_service import TournamentService
from app.services.core.game_service import GameService
from app.services.core.player_service import PlayerService
from app.exceptions import ServiceError, NotFoundError


def get_most_scorers_tournament():
    """Meiste Scorer (Tore + Assists) eines Spielers in einem Turnier"""
    # Service Layer verwenden
    records_service = RecordsService()
    
    try:
        # Hole Turnier-Rekorde über Service für Punkte
        tournament_records = records_service.get_tournament_records(record_types=['points'])
        point_leaders = tournament_records.get('point_leaders', [])
        
        # Formatiere für Anzeige - nur Top 3
        all_performances = []
        for leader in point_leaders[:TOP_3_DISPLAY]:
            all_performances.append({
                'player': leader['player_name'],
                'team': leader['team'],
                'points': leader['points'],
                'tournament': leader['tournament'],
                'year': leader['year']
            })
        
        return all_performances
    except Exception as e:
        # Fallback auf alte Implementierung bei Fehler
        try:
            tournament_service = TournamentService()
            game_service = GameService()
            player_points_by_tournament = defaultdict(lambda: defaultdict(int))
            
            years = tournament_service.get_all()
            for year in years:
                goals = game_service.get_goals_by_year(year.id)
            
            for goal in goals:
                player_points_by_tournament[year.id][goal.scorer_id] += 1
                
                if goal.assist1_id:
                    player_points_by_tournament[year.id][goal.assist1_id] += 1
                if goal.assist2_id:
                    player_points_by_tournament[year.id][goal.assist2_id] += 1
        
            # Collect all player performances
            all_performances = []
            
            for year_id, players in player_points_by_tournament.items():
                try:
                    year = tournament_service.get_by_id(year_id)
                    player_service = PlayerService()
                    for player_id, points in players.items():
                        try:
                            player = player_service.get_by_id(player_id)
                            all_performances.append({
                                'player': f"{player.first_name} {player.last_name}",
                                'team': player.team_code,
                                'points': points,
                                'tournament': year.name,
                                'year': year.year
                            })
                        except (NotFoundError, ServiceError):
                            continue
                except (NotFoundError, ServiceError):
                    continue
            
            # Sort by points descending and return top 3
            all_performances.sort(key=lambda x: x['points'], reverse=True)
            return all_performances[:TOP_3_DISPLAY]
        except Exception:
            # Final fallback - return empty list
            return []


def get_most_goals_player_tournament():
    """Meiste Tore eines Spielers in einem Turnier"""
    # Service Layer verwenden
    records_service = RecordsService()
    
    try:
        # Hole Turnier-Rekorde über Service für Tore
        tournament_records = records_service.get_tournament_records(record_types=['goals'])
        goal_leaders = tournament_records.get('goal_leaders', [])
        
        # Formatiere für Anzeige - nur Top 3
        all_performances = []
        for leader in goal_leaders[:TOP_3_DISPLAY]:
            all_performances.append({
                'player': leader['player_name'],
                'team': leader['team'],
                'goals': leader['goals'],
                'tournament': leader['tournament'],
                'year': leader['year']
            })
        
        return all_performances
    except Exception as e:
        # Fallback auf alte Implementierung bei Fehler
        try:
            tournament_service = TournamentService()
            game_service = GameService()
            player_goals_by_tournament = defaultdict(lambda: defaultdict(int))
            
            years = tournament_service.get_all()
            for year in years:
                goals = game_service.get_goals_by_year(year.id)
            
            for goal in goals:
                player_goals_by_tournament[year.id][goal.scorer_id] += 1
        
            # Collect all player performances
            all_performances = []
            
            for year_id, players in player_goals_by_tournament.items():
                try:
                    year = tournament_service.get_by_id(year_id)
                    player_service = PlayerService()
                    for player_id, goals in players.items():
                        try:
                            player = player_service.get_by_id(player_id)
                            all_performances.append({
                                'player': f"{player.first_name} {player.last_name}",
                                'team': player.team_code,
                                'goals': goals,
                                'tournament': year.name,
                                'year': year.year
                            })
                        except (NotFoundError, ServiceError):
                            continue
                except (NotFoundError, ServiceError):
                    continue
            
            # Sort by goals descending and return top 3
            all_performances.sort(key=lambda x: x['goals'], reverse=True)
            return all_performances[:TOP_3_DISPLAY]
        except Exception:
            # Final fallback - return empty list
            return []


def get_most_assists_player_tournament():
    """Meiste Assists eines Spielers in einem Turnier"""
    # Service Layer verwenden
    records_service = RecordsService()
    
    try:
        # Hole Turnier-Rekorde über Service für Assists
        tournament_records = records_service.get_tournament_records(record_types=['assists'])
        assist_leaders = tournament_records.get('assist_leaders', [])
        
        # Formatiere für Anzeige - nur Top 3
        all_performances = []
        for leader in assist_leaders[:TOP_3_DISPLAY]:
            all_performances.append({
                'player': leader['player_name'],
                'team': leader['team'],
                'assists': leader['assists'],
                'tournament': leader['tournament'],
                'year': leader['year']
            })
        
        return all_performances
    except Exception as e:
        # Fallback auf alte Implementierung bei Fehler
        try:
            tournament_service = TournamentService()
            game_service = GameService()
            player_assists_by_tournament = defaultdict(lambda: defaultdict(int))
            
            years = tournament_service.get_all()
            for year in years:
                goals = game_service.get_goals_by_year(year.id)
            
            for goal in goals:
                if goal.assist1_id:
                    player_assists_by_tournament[year.id][goal.assist1_id] += 1
                if goal.assist2_id:
                    player_assists_by_tournament[year.id][goal.assist2_id] += 1
        
            # Collect all player performances
            all_performances = []
            
            for year_id, players in player_assists_by_tournament.items():
                try:
                    year = tournament_service.get_by_id(year_id)
                    player_service = PlayerService()
                    for player_id, assists in players.items():
                        try:
                            player = player_service.get_by_id(player_id)
                            all_performances.append({
                                'player': f"{player.first_name} {player.last_name}",
                                'team': player.team_code,
                                'assists': assists,
                                'tournament': year.name,
                                'year': year.year
                            })
                        except (NotFoundError, ServiceError):
                            continue
                except (NotFoundError, ServiceError):
                    continue
            
            # Sort by assists descending and return top 3
            all_performances.sort(key=lambda x: x['assists'], reverse=True)
            return all_performances[:TOP_3_DISPLAY]
        except Exception:
            # Final fallback - return empty list
            return []


def get_most_penalty_minutes_tournament():
    """Meiste Strafminuten eines Spielers in einem Turnier"""
    # Service Layer verwenden
    records_service = RecordsService()
    
    try:
        # Hole Turnier-Rekorde über Service für Strafen
        tournament_records = records_service.get_tournament_records(record_types=['penalties'])
        penalty_leaders = tournament_records.get('penalty_leaders', [])
        
        # Formatiere für Anzeige - nur Top 3
        all_performances = []
        for leader in penalty_leaders[:TOP_3_DISPLAY]:
            all_performances.append({
                'player': leader['player_name'],
                'team': leader['team'],
                'pim': leader['penalty_minutes'],
                'tournament': leader['tournament'],
                'year': leader['year']
            })
        
        return all_performances
    except Exception as e:
        # Fallback auf alte Implementierung bei Fehler
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
        return all_performances[:TOP_3_DISPLAY]