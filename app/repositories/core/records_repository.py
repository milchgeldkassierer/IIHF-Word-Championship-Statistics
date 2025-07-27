"""
Records Repository für IIHF World Championship Statistics
Verwaltet Datenzugriff für Rekord-bezogene Operationen
"""

from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session, joinedload

from models import Game, Player, Goal, Penalty, ShotsOnGoal, ChampionshipYear
from app.repositories.base import BaseRepository


class RecordsRepository(BaseRepository[Player]):
    """Repository für Rekord-Management und -Abfragen"""
    
    def __init__(self):
        super().__init__(Player)
    
    # Turnier-Rekorde
    def get_tournament_goal_records(self, year: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die meisten Tore in einem Turnier"""
        query = self.db.query(
            Player.id,
            Player.first_name,
            Player.last_name,
            Player.team,
            Goal.year,
            func.count(Goal.id).label('goals')
        ).join(Goal, Player.id == Goal.player_id)
        
        if year:
            query = query.filter(Goal.year == year)
        
        query = query.group_by(Player.id, Player.first_name, Player.last_name, Player.team, Goal.year)
        query = query.order_by(desc('goals'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'player_id': r.id,
                'player_name': f"{r.first_name} {r.last_name}",
                'team': r.team,
                'year': r.year,
                'goals': r.goals
            }
            for r in results
        ]
    
    def get_tournament_assist_records(self, year: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die meisten Assists in einem Turnier"""
        query = self.db.query(
            Player.id,
            Player.first_name,
            Player.last_name,
            Player.team,
            Goal.year,
            func.count(Goal.id).label('assists')
        ).join(Goal, or_(Player.id == Goal.assist1_id, Player.id == Goal.assist2_id))
        
        if year:
            query = query.filter(Goal.year == year)
        
        query = query.group_by(Player.id, Player.first_name, Player.last_name, Player.team, Goal.year)
        query = query.order_by(desc('assists'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'player_id': r.id,
                'player_name': f"{r.first_name} {r.last_name}",
                'team': r.team,
                'year': r.year,
                'assists': r.assists
            }
            for r in results
        ]
    
    def get_tournament_point_records(self, year: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die meisten Punkte (Tore + Assists) in einem Turnier"""
        # Subquery für Tore
        goals_subq = self.db.query(
            Goal.player_id,
            Goal.year,
            func.count(Goal.id).label('goals')
        ).group_by(Goal.player_id, Goal.year).subquery()
        
        # Subquery für Assists
        assists_subq = self.db.query(
            Player.id.label('player_id'),
            Goal.year,
            func.count(Goal.id).label('assists')
        ).join(Goal, or_(Player.id == Goal.assist1_id, Player.id == Goal.assist2_id))\
         .group_by(Player.id, Goal.year).subquery()
        
        # Hauptabfrage
        query = self.db.query(
            Player.id,
            Player.first_name,
            Player.last_name,
            Player.team,
            func.coalesce(goals_subq.c.year, assists_subq.c.year).label('year'),
            func.coalesce(goals_subq.c.goals, 0).label('goals'),
            func.coalesce(assists_subq.c.assists, 0).label('assists'),
            (func.coalesce(goals_subq.c.goals, 0) + func.coalesce(assists_subq.c.assists, 0)).label('points')
        ).outerjoin(goals_subq, Player.id == goals_subq.c.player_id)\
         .outerjoin(assists_subq, Player.id == assists_subq.c.player_id)
        
        if year:
            query = query.filter(or_(goals_subq.c.year == year, assists_subq.c.year == year))
        
        query = query.filter(or_(goals_subq.c.goals > 0, assists_subq.c.assists > 0))
        query = query.order_by(desc('points'), desc('goals'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'player_id': r.id,
                'player_name': f"{r.first_name} {r.last_name}",
                'team': r.team,
                'year': r.year,
                'goals': r.goals,
                'assists': r.assists,
                'points': r.points
            }
            for r in results
        ]
    
    def get_tournament_penalty_records(self, year: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die meisten Strafminuten in einem Turnier"""
        query = self.db.query(
            Player.id,
            Player.first_name,
            Player.last_name,
            Player.team,
            Penalty.year,
            func.sum(Penalty.duration).label('penalty_minutes')
        ).join(Penalty, Player.id == Penalty.player_id)
        
        if year:
            query = query.filter(Penalty.year == year)
        
        query = query.group_by(Player.id, Player.first_name, Player.last_name, Player.team, Penalty.year)
        query = query.order_by(desc('penalty_minutes'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'player_id': r.id,
                'player_name': f"{r.first_name} {r.last_name}",
                'team': r.team,
                'year': r.year,
                'penalty_minutes': r.penalty_minutes
            }
            for r in results
        ]
    
    # Karriere-Rekorde
    def get_career_goal_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die Spieler mit den meisten Karriere-Toren"""
        query = self.db.query(
            Player.id,
            Player.first_name,
            Player.last_name,
            Player.team,
            func.count(Goal.id).label('total_goals'),
            func.count(func.distinct(Goal.year)).label('tournaments')
        ).join(Goal, Player.id == Goal.player_id)
        
        query = query.group_by(Player.id, Player.first_name, Player.last_name, Player.team)
        query = query.order_by(desc('total_goals'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'player_id': r.id,
                'player_name': f"{r.first_name} {r.last_name}",
                'team': r.team,
                'total_goals': r.total_goals,
                'tournaments': r.tournaments
            }
            for r in results
        ]
    
    def get_career_assist_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die Spieler mit den meisten Karriere-Assists"""
        query = self.db.query(
            Player.id,
            Player.first_name,
            Player.last_name,
            Player.team,
            func.count(Goal.id).label('total_assists'),
            func.count(func.distinct(Goal.year)).label('tournaments')
        ).join(Goal, or_(Player.id == Goal.assist1_id, Player.id == Goal.assist2_id))
        
        query = query.group_by(Player.id, Player.first_name, Player.last_name, Player.team)
        query = query.order_by(desc('total_assists'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'player_id': r.id,
                'player_name': f"{r.first_name} {r.last_name}",
                'team': r.team,
                'total_assists': r.total_assists,
                'tournaments': r.tournaments
            }
            for r in results
        ]
    
    def get_career_point_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die Spieler mit den meisten Karriere-Punkten"""
        # Ähnlich wie tournament_point_records aber ohne year Gruppierung
        goals_subq = self.db.query(
            Goal.player_id,
            func.count(Goal.id).label('goals')
        ).group_by(Goal.player_id).subquery()
        
        assists_subq = self.db.query(
            Player.id.label('player_id'),
            func.count(Goal.id).label('assists')
        ).join(Goal, or_(Player.id == Goal.assist1_id, Player.id == Goal.assist2_id))\
         .group_by(Player.id).subquery()
        
        query = self.db.query(
            Player.id,
            Player.first_name,
            Player.last_name,
            Player.team,
            func.coalesce(goals_subq.c.goals, 0).label('goals'),
            func.coalesce(assists_subq.c.assists, 0).label('assists'),
            (func.coalesce(goals_subq.c.goals, 0) + func.coalesce(assists_subq.c.assists, 0)).label('points')
        ).outerjoin(goals_subq, Player.id == goals_subq.c.player_id)\
         .outerjoin(assists_subq, Player.id == assists_subq.c.player_id)
        
        query = query.filter(or_(goals_subq.c.goals > 0, assists_subq.c.assists > 0))
        query = query.order_by(desc('points'), desc('goals'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'player_id': r.id,
                'player_name': f"{r.first_name} {r.last_name}",
                'team': r.team,
                'goals': r.goals,
                'assists': r.assists,
                'points': r.points
            }
            for r in results
        ]
    
    # Team-Rekorde
    def get_team_highest_scoring_games(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die Spiele mit den meisten Toren eines Teams"""
        query = self.db.query(
            Game.id,
            Game.year,
            Game.round,
            Game.team1,
            Game.team2,
            Game.team1_score,
            Game.team2_score,
            func.greatest(Game.team1_score, Game.team2_score).label('max_goals')
        ).filter(
            and_(Game.team1_score.isnot(None), Game.team2_score.isnot(None))
        )
        
        query = query.order_by(desc('max_goals'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'game_id': r.id,
                'year': r.year,
                'round': r.round,
                'teams': f"{r.team1} vs {r.team2}",
                'score': f"{r.team1_score}:{r.team2_score}",
                'winning_team': r.team1 if r.team1_score > r.team2_score else r.team2,
                'max_goals': r.max_goals
            }
            for r in results
        ]
    
    def get_team_biggest_wins(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die größten Siege (Tordifferenz)"""
        query = self.db.query(
            Game.id,
            Game.year,
            Game.round,
            Game.team1,
            Game.team2,
            Game.team1_score,
            Game.team2_score,
            func.abs(Game.team1_score - Game.team2_score).label('goal_diff')
        ).filter(
            and_(Game.team1_score.isnot(None), Game.team2_score.isnot(None))
        )
        
        query = query.order_by(desc('goal_diff'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'game_id': r.id,
                'year': r.year,
                'round': r.round,
                'winner': r.team1 if r.team1_score > r.team2_score else r.team2,
                'loser': r.team2 if r.team1_score > r.team2_score else r.team1,
                'score': f"{max(r.team1_score, r.team2_score)}:{min(r.team1_score, r.team2_score)}",
                'goal_diff': r.goal_diff
            }
            for r in results
        ]
    
    # Spiel-Rekorde
    def get_game_most_goals_combined(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die Spiele mit den meisten kombinierten Toren"""
        query = self.db.query(
            Game.id,
            Game.year,
            Game.round,
            Game.team1,
            Game.team2,
            Game.team1_score,
            Game.team2_score,
            (Game.team1_score + Game.team2_score).label('total_goals')
        ).filter(
            and_(Game.team1_score.isnot(None), Game.team2_score.isnot(None))
        )
        
        query = query.order_by(desc('total_goals'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'game_id': r.id,
                'year': r.year,
                'round': r.round,
                'teams': f"{r.team1} vs {r.team2}",
                'score': f"{r.team1_score}:{r.team2_score}",
                'total_goals': r.total_goals
            }
            for r in results
        ]
    
    def get_game_most_penalties(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Holt die Spiele mit den meisten Strafminuten"""
        query = self.db.query(
            Game.id,
            Game.year,
            Game.round,
            Game.team1,
            Game.team2,
            func.sum(Penalty.duration).label('total_penalties')
        ).join(Penalty, Game.id == Penalty.game_id)
        
        query = query.group_by(Game.id, Game.year, Game.round, Game.team1, Game.team2)
        query = query.order_by(desc('total_penalties'))
        query = query.limit(limit)
        
        results = query.all()
        
        return [
            {
                'game_id': r.id,
                'year': r.year,
                'round': r.round,
                'teams': f"{r.team1} vs {r.team2}",
                'total_penalties': r.total_penalties
            }
            for r in results
        ]
    
    # Historische Entwicklung
    def get_record_progression(self, record_type: str, player_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Zeigt die Entwicklung eines bestimmten Rekords über die Zeit"""
        if record_type == 'tournament_goals':
            query = self.db.query(
                Goal.year,
                Player.id,
                Player.first_name,
                Player.last_name,
                func.count(Goal.id).label('value')
            ).join(Player, Goal.player_id == Player.id)
            
            if player_id:
                query = query.filter(Player.id == player_id)
            
            query = query.group_by(Goal.year, Player.id, Player.first_name, Player.last_name)
            query = query.order_by(Goal.year, desc('value'))
            
            # Get top record for each year
            results = []
            for year_data in query.all():
                year_results = [r for r in query.all() if r.year == year_data.year]
                if year_results:
                    top = year_results[0]
                    results.append({
                        'year': top.year,
                        'player_id': top.id,
                        'player_name': f"{top.first_name} {top.last_name}",
                        'value': top.value
                    })
            
            return results
        
        # Weitere Rekordtypen können hier hinzugefügt werden
        return []
    
    def search_records(self, search_term: str, record_category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Sucht nach Rekorden basierend auf Spielernamen oder Teams"""
        results = []
        
        # Spieler-basierte Suche
        players = self.db.query(Player).filter(
            or_(
                Player.first_name.ilike(f'%{search_term}%'),
                Player.last_name.ilike(f'%{search_term}%'),
                Player.team.ilike(f'%{search_term}%')
            )
        ).all()
        
        for player in players:
            # Turnier-Rekorde für den Spieler
            goals = self.db.query(
                Goal.year,
                func.count(Goal.id).label('goals')
            ).filter(Goal.player_id == player.id)\
             .group_by(Goal.year).all()
            
            for g in goals:
                results.append({
                    'type': 'tournament_goals',
                    'player_name': f"{player.first_name} {player.last_name}",
                    'team': player.team,
                    'year': g.year,
                    'value': g.goals,
                    'description': f"{g.goals} goals in {g.year}"
                })
        
        return results