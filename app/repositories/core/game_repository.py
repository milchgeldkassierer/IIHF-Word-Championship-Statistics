"""
Game Repository for IIHF World Championship Statistics
Handles game-specific data access patterns
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import and_, or_, func
from models import Game, ChampionshipYear, ShotsOnGoal, GameOverrule
from app.repositories.base import BaseRepository
import logging

logger = logging.getLogger(__name__)


class GameRepository(BaseRepository[Game]):
    """
    Repository for game-specific queries and data access
    """
    
    def __init__(self):
        super().__init__(Game)
    
    def get_games_by_year(self, year_id: int) -> List[Game]:
        """
        Get all games for a specific year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            List of games
        """
        return self.find_all(year_id=year_id)
    
    def get_games_by_round(self, year_id: int, round: str) -> List[Game]:
        """
        Get all games for a specific round in a year
        
        Args:
            year_id: Championship year ID
            round: Round name (e.g., 'Preliminary Round', 'Quarter-finals')
            
        Returns:
            List of games
        """
        return self.find_all(year_id=year_id, round=round)
    
    def get_preliminary_games(self, year_id: int, group: Optional[str] = None) -> List[Game]:
        """
        Get preliminary round games, optionally filtered by group
        
        Args:
            year_id: Championship year ID
            group: Optional group filter (e.g., 'A', 'B')
            
        Returns:
            List of preliminary round games
        """
        query = self.get_query().filter(
            and_(
                Game.year_id == year_id,
                Game.round == 'Preliminary Round'
            )
        )
        
        if group:
            query = query.filter(Game.group == group)
        
        return query.all()
    
    def get_playoff_games(self, year_id: int) -> List[Game]:
        """
        Get all playoff games (non-preliminary) for a year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            List of playoff games
        """
        return self.get_query().filter(
            and_(
                Game.year_id == year_id,
                Game.round != 'Preliminary Round'
            )
        ).all()
    
    def get_games_by_team(self, year_id: int, team_code: str, 
                          round: Optional[str] = None) -> List[Game]:
        """
        Get all games for a specific team
        
        Args:
            year_id: Championship year ID
            team_code: Team code (e.g., 'CAN', 'USA')
            round: Optional round filter
            
        Returns:
            List of games involving the team
        """
        query = self.get_query().filter(
            and_(
                Game.year_id == year_id,
                or_(
                    Game.team1_code == team_code,
                    Game.team2_code == team_code
                )
            )
        )
        
        if round:
            query = query.filter(Game.round == round)
        
        return query.all()
    
    def get_head_to_head_games(self, team1_code: str, team2_code: str,
                               year_id: Optional[int] = None) -> List[Game]:
        """
        Get all games between two teams
        
        Args:
            team1_code: First team code
            team2_code: Second team code
            year_id: Optional year filter
            
        Returns:
            List of games between the teams
        """
        query = self.get_query().filter(
            or_(
                and_(Game.team1_code == team1_code, Game.team2_code == team2_code),
                and_(Game.team1_code == team2_code, Game.team2_code == team1_code)
            )
        )
        
        if year_id:
            query = query.filter(Game.year_id == year_id)
        
        return query.all()
    
    def get_completed_games(self, year_id: int) -> List[Game]:
        """
        Get all completed games (with scores) for a year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            List of completed games
        """
        return self.get_query().filter(
            and_(
                Game.year_id == year_id,
                Game.team1_score.isnot(None),
                Game.team2_score.isnot(None)
            )
        ).all()
    
    def get_games_by_date(self, year_id: int, date: str) -> List[Game]:
        """
        Get all games on a specific date
        
        Args:
            year_id: Championship year ID
            date: Date string (format depends on data)
            
        Returns:
            List of games on that date
        """
        return self.find_all(year_id=year_id, date=date)
    
    def get_games_by_venue(self, year_id: int, venue: str) -> List[Game]:
        """
        Get all games at a specific venue
        
        Args:
            year_id: Championship year ID
            venue: Venue name
            
        Returns:
            List of games at that venue
        """
        return self.find_all(year_id=year_id, venue=venue)
    
    def get_games_with_overrules(self, year_id: int) -> List[Tuple[Game, GameOverrule]]:
        """
        Get all games that have overrules
        
        Args:
            year_id: Championship year ID
            
        Returns:
            List of tuples (game, overrule)
        """
        return self.db.session.query(Game, GameOverrule).join(
            GameOverrule, Game.id == GameOverrule.game_id
        ).filter(Game.year_id == year_id).all()
    
    def get_game_statistics(self, game_id: int) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a game
        
        Args:
            game_id: Game ID
            
        Returns:
            Dictionary with game statistics
        """
        game = self.get_by_id(game_id)
        if not game:
            return {}
        
        # Get SOG data
        sog_data = self.db.session.query(ShotsOnGoal).filter_by(game_id=game_id).all()
        
        # Get overrule if exists
        overrule = self.db.session.query(GameOverrule).filter_by(game_id=game_id).first()
        
        return {
            'game': game,
            'shots_on_goal': sog_data,
            'overrule': overrule
        }
    
    def count_games_by_round(self, year_id: int) -> Dict[str, int]:
        """
        Count games by round for a year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            Dictionary mapping round names to game counts
        """
        results = self.db.session.query(
            Game.round,
            func.count(Game.id)
        ).filter(
            Game.year_id == year_id
        ).group_by(Game.round).all()
        
        return {round: count for round, count in results}
    
    def get_games_by_result_type(self, year_id: int, result_type: str) -> List[Game]:
        """
        Get games by result type (REG, OT, SO)
        
        Args:
            year_id: Championship year ID
            result_type: Result type
            
        Returns:
            List of games
        """
        return self.find_all(year_id=year_id, result_type=result_type)
    
    def search_games(self, criteria: Dict[str, Any]) -> List[Game]:
        """
        Advanced game search with multiple criteria
        
        Args:
            criteria: Search criteria dictionary
            
        Returns:
            List of matching games
        """
        query = self.get_query()
        
        # Year filter
        if 'year_id' in criteria:
            query = query.filter(Game.year_id == criteria['year_id'])
        
        # Round filter
        if 'round' in criteria:
            query = query.filter(Game.round == criteria['round'])
        
        # Group filter
        if 'group' in criteria:
            query = query.filter(Game.group == criteria['group'])
        
        # Team filter
        if 'team' in criteria:
            team = criteria['team']
            query = query.filter(
                or_(Game.team1_code == team, Game.team2_code == team)
            )
        
        # Score filter (high-scoring games)
        if 'min_total_score' in criteria:
            min_score = criteria['min_total_score']
            query = query.filter(
                and_(
                    Game.team1_score.isnot(None),
                    Game.team2_score.isnot(None),
                    (Game.team1_score + Game.team2_score) >= min_score
                )
            )
        
        # Result type filter
        if 'result_type' in criteria:
            query = query.filter(Game.result_type == criteria['result_type'])
        
        # Date range filter
        if 'start_date' in criteria:
            query = query.filter(Game.date >= criteria['start_date'])
        
        if 'end_date' in criteria:
            query = query.filter(Game.date <= criteria['end_date'])
        
        # Venue filter
        if 'venue' in criteria:
            query = query.filter(Game.venue == criteria['venue'])
        
        # Order by game number by default
        query = query.order_by(Game.game_number)
        
        return query.all()
    
    def get_latest_game_number(self, year_id: int) -> int:
        """
        Get the highest game number for a year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            Latest game number or 0 if no games
        """
        result = self.db.session.query(
            func.max(Game.game_number)
        ).filter(Game.year_id == year_id).scalar()
        
        return result or 0