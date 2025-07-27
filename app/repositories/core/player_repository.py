"""
Player Repository for IIHF World Championship Statistics
Handles player-specific data access patterns
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import and_, or_, func
from models import Player, Goal, Penalty, db
from app.repositories.base import BaseRepository
import logging

logger = logging.getLogger(__name__)


class PlayerRepository(BaseRepository[Player]):
    """
    Repository for player-specific queries and data access
    """
    
    def __init__(self):
        super().__init__(Player)
    
    def get_players_by_team(self, team_code: str) -> List[Player]:
        """
        Get all players for a specific team, ordered by last name, first name
        
        Args:
            team_code: Team code (e.g., 'CAN', 'USA')
            
        Returns:
            List of players
        """
        return self.get_query().filter(
            Player.team_code == team_code
        ).order_by(Player.last_name, Player.first_name).all()
    
    def get_player_by_jersey(self, team_code: str, jersey_number: int) -> Optional[Player]:
        """
        Get player by team and jersey number
        
        Args:
            team_code: Team code
            jersey_number: Jersey number
            
        Returns:
            Player if found, None otherwise
        """
        return self.find_one(team_code=team_code, jersey_number=jersey_number)
    
    def get_player_by_name(self, first_name: str, last_name: str, 
                          team_code: Optional[str] = None) -> Optional[Player]:
        """
        Get player by name, optionally filtered by team
        
        Args:
            first_name: Player's first name
            last_name: Player's last name
            team_code: Optional team code filter
            
        Returns:
            Player if found, None otherwise
        """
        query = self.get_query().filter(
            and_(
                Player.first_name == first_name,
                Player.last_name == last_name
            )
        )
        
        if team_code:
            query = query.filter(Player.team_code == team_code)
        
        return query.first()
    
    def search_players(self, search_term: str, team_code: Optional[str] = None) -> List[Player]:
        """
        Search players by name (partial match)
        
        Args:
            search_term: Search term for first or last name
            team_code: Optional team filter
            
        Returns:
            List of matching players
        """
        query = self.get_query().filter(
            or_(
                Player.first_name.ilike(f"%{search_term}%"),
                Player.last_name.ilike(f"%{search_term}%")
            )
        )
        
        if team_code:
            query = query.filter(Player.team_code == team_code)
        
        return query.all()
    
    def get_player_statistics(self, player_id: int) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a player
        
        Args:
            player_id: Player ID
            
        Returns:
            Dictionary with goals, assists, penalty minutes, etc.
        """
        # Get goal statistics
        goals_scored = self.db.session.query(func.count(Goal.id)).filter(
            Goal.scorer_id == player_id
        ).scalar() or 0
        
        # Get assist statistics
        assists_1 = self.db.session.query(func.count(Goal.id)).filter(
            Goal.assist1_id == player_id
        ).scalar() or 0
        
        assists_2 = self.db.session.query(func.count(Goal.id)).filter(
            Goal.assist2_id == player_id
        ).scalar() or 0
        
        total_assists = assists_1 + assists_2
        
        # Get penalty minutes
        # Assuming penalty minutes are stored or calculated
        # For now, counting penalties
        penalty_count = self.db.session.query(func.count(Penalty.id)).filter(
            Penalty.player_id == player_id
        ).scalar() or 0
        
        return {
            'goals': goals_scored,
            'assists': total_assists,
            'penalty_minutes': penalty_count * 2,  # Assuming 2 minutes per penalty by default
            'points': goals_scored + total_assists
        }
    
    def get_players_with_stats(self, team_code: str) -> List[Dict[str, Any]]:
        """
        Get all players for a team with their basic statistics
        
        Args:
            team_code: Team code
            
        Returns:
            List of player dictionaries with stats
        """
        players = self.get_players_by_team(team_code)
        result = []
        
        for player in players:
            stats = self.get_player_statistics(player.id)
            result.append({
                'id': player.id,
                'first_name': player.first_name,
                'last_name': player.last_name,
                'jersey_number': player.jersey_number,
                'goals': stats['goals'],
                'assists': stats['assists'],
                'points': stats['points']
            })
        
        return result
    
    def get_goal_types_for_player(self, player_id: int) -> Dict[str, int]:
        """
        Get breakdown of goal types for a player
        
        Args:
            player_id: Player ID
            
        Returns:
            Dictionary with goal type counts
        """
        goal_types = self.db.session.query(
            Goal.goal_type,
            func.count(Goal.id)
        ).filter(
            Goal.scorer_id == player_id
        ).group_by(Goal.goal_type).all()
        
        return {goal_type: count for goal_type, count in goal_types}
    
    def get_penalty_breakdown_for_player(self, player_id: int) -> Dict[str, int]:
        """
        Get breakdown of penalty types for a player
        
        Args:
            player_id: Player ID
            
        Returns:
            Dictionary with penalty type counts
        """
        penalty_types = self.db.session.query(
            Penalty.penalty_type,
            func.count(Penalty.id)
        ).filter(
            Penalty.player_id == player_id
        ).group_by(Penalty.penalty_type).all()
        
        return {penalty_type: count for penalty_type, count in penalty_types}
    
    def get_team_roster(self, team_code: str) -> Dict[str, Any]:
        """
        Get complete roster information for a team
        
        Args:
            team_code: Team code
            
        Returns:
            Dictionary with roster information
        """
        players = self.get_players_by_team(team_code)
        
        return {
            'team_code': team_code,
            'players': players,
            'total_players': len(players),
            'by_position': {
                'forwards': [p for p in players if p.jersey_number and p.jersey_number < 30],
                'defensemen': [p for p in players if p.jersey_number and 30 <= p.jersey_number < 70],
                'goalies': [p for p in players if p.jersey_number and p.jersey_number >= 70]
            }
        }
    
    def get_years_played(self, player_id: int) -> List[Dict[str, Any]]:
        """
        Get list of years a player has participated
        
        Args:
            player_id: Player ID
            
        Returns:
            List of years with year_id and year
        """
        # This would need to be implemented with proper year tracking
        # For now returning empty list
        return []
    
    def find_duplicates(self, team_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find potential duplicate players
        
        Args:
            team_code: Optional team filter
            
        Returns:
            List of potential duplicates
        """
        query = self.db.session.query(
            Player.first_name,
            Player.last_name,
            Player.team_code,
            func.count(Player.id).label('count')
        ).group_by(
            Player.first_name,
            Player.last_name,
            Player.team_code
        ).having(func.count(Player.id) > 1)
        
        if team_code:
            query = query.filter(Player.team_code == team_code)
        
        duplicates = query.all()
        
        results = []
        for first_name, last_name, team, count in duplicates:
            players = self.get_query().filter(
                and_(
                    Player.first_name == first_name,
                    Player.last_name == last_name,
                    Player.team_code == team
                )
            ).all()
            
            results.append({
                'name': f"{first_name} {last_name}",
                'team_code': team,
                'count': count,
                'players': players
            })
        
        return results
    
    def get_inactive_players(self, years_since_last_game: int = 3) -> List[Player]:
        """
        Get players who haven't played in recent years
        
        Args:
            years_since_last_game: Number of years to consider inactive
            
        Returns:
            List of inactive players
        """
        # This would need proper implementation
        # For now returning empty list
        return []
    
    def get_player_streaks(self, player_id: int) -> Dict[str, Any]:
        """
        Get scoring streaks for a player
        
        Args:
            player_id: Player ID
            
        Returns:
            Dictionary with streak information
        """
        # This would need game-by-game tracking
        # For now returning empty dict
        return {
            'current_goal_streak': 0,
            'current_point_streak': 0,
            'longest_goal_streak': 0,
            'longest_point_streak': 0
        }
    
    def bulk_update_team(self, old_team_code: str, new_team_code: str) -> int:
        """
        Update all players from one team to another
        
        Args:
            old_team_code: Current team code
            new_team_code: New team code
            
        Returns:
            Number of players updated
        """
        count = self.db.session.query(Player).filter(
            Player.team_code == old_team_code
        ).update({'team_code': new_team_code})
        
        self.db.session.commit()
        return count
    
    def get_player_by_id_with_stats(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player with their statistics
        
        Args:
            player_id: Player ID
            
        Returns:
            Player dictionary with stats or None
        """
        player = self.get_by_id(player_id)
        if not player:
            return None
        
        stats = self.get_player_statistics(player_id)
        
        return {
            'player': player,
            'statistics': stats
        }
    
    def get_players_by_jersey_range(self, team_code: str, 
                                   min_jersey: int, 
                                   max_jersey: int) -> List[Player]:
        """
        Get players by jersey number range
        
        Args:
            team_code: Team code
            min_jersey: Minimum jersey number
            max_jersey: Maximum jersey number
            
        Returns:
            List of players
        """
        return self.get_query().filter(
            and_(
                Player.team_code == team_code,
                Player.jersey_number >= min_jersey,
                Player.jersey_number <= max_jersey
            )
        ).order_by(Player.jersey_number).all()
    
    def get_team_captains(self, team_code: str) -> List[Player]:
        """
        Get team captains (placeholder - would need captain field)
        
        Args:
            team_code: Team code
            
        Returns:
            List of captains
        """
        # This would need a captain field in the model
        # For now returning empty list
        return []
    
    def get_player_count_by_country(self) -> List[Tuple[str, int]]:
        """
        Get player count grouped by country/team
        
        Returns:
            List of tuples (team_code, count)
        """
        return self.db.session.query(
            Player.team_code,
            func.count(Player.id)
        ).group_by(
            Player.team_code
        ).having(func.count(Player.id) > 1).all()
    
    def get_player_game_log(self, player_id: int) -> List[Dict[str, Any]]:
        """
        Get game-by-game log for a player
        
        Args:
            player_id: Player ID
            
        Returns:
            List of game statistics
        """
        # Get all goals where player was involved
        goals_scored = self.db.session.query(Goal).filter_by(scorer_id=player_id).all()
        assists_1 = self.db.session.query(Goal).filter_by(assist1_id=player_id).all()
        assists_2 = self.db.session.query(Goal).filter_by(assist2_id=player_id).all()
        penalties = self.db.session.query(Penalty).filter_by(player_id=player_id).all()
        
        # Group by game_id
        game_stats = {}
        
        for goal in goals_scored:
            if goal.game_id not in game_stats:
                game_stats[goal.game_id] = {'goals': 0, 'assists': 0, 'penalties': 0}
            game_stats[goal.game_id]['goals'] += 1
        
        for assist in assists_1 + assists_2:
            if assist.game_id not in game_stats:
                game_stats[assist.game_id] = {'goals': 0, 'assists': 0, 'penalties': 0}
            game_stats[assist.game_id]['assists'] += 1
        
        for penalty in penalties:
            if penalty.game_id not in game_stats:
                game_stats[penalty.game_id] = {'goals': 0, 'assists': 0, 'penalties': 0}
            game_stats[penalty.game_id]['penalties'] += 1
        
        # Convert to list
        result = []
        for game_id, stats in game_stats.items():
            result.append({
                'game_id': game_id,
                'goals': stats['goals'],
                'assists': stats['assists'],
                'points': stats['goals'] + stats['assists'],
                'penalties': stats['penalties']
            })
        
        return result
    
    def get_player_count_by_team(self) -> List[Tuple[str, int]]:
        """
        Get player count grouped by team
        
        Returns:
            List of tuples (team_code, count)
        """
        return self.db.session.query(
            Player.team_code, 
            func.count(Player.id).label('player_count')
        ).group_by(Player.team_code).order_by(Player.team_code).all()