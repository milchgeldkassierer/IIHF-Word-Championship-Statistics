"""
Tournament Repository for IIHF World Championship Statistics
Handles tournament-specific data access patterns
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import and_, or_, func, desc
from models import ChampionshipYear, Game, db
from app.repositories.base import BaseRepository
import logging

logger = logging.getLogger(__name__)


class TournamentRepository(BaseRepository[ChampionshipYear]):
    """
    Repository for tournament-specific queries and data access
    """
    
    def __init__(self):
        super().__init__(ChampionshipYear)
    
    def get_by_year(self, year: int) -> Optional[ChampionshipYear]:
        """
        Get tournament by year
        
        Args:
            year: The year of the tournament
            
        Returns:
            Tournament if found, None otherwise
        """
        return self.find_one(year=year)
    
    def get_recent_tournaments(self, limit: int = 10) -> List[ChampionshipYear]:
        """
        Get most recent tournaments
        
        Args:
            limit: Number of tournaments to return
            
        Returns:
            List of recent tournaments ordered by year descending
        """
        return self.get_query().order_by(desc(ChampionshipYear.year)).limit(limit).all()
    
    def get_tournaments_by_range(self, start_year: int, end_year: int) -> List[ChampionshipYear]:
        """
        Get tournaments within a year range
        
        Args:
            start_year: Starting year (inclusive)
            end_year: Ending year (inclusive)
            
        Returns:
            List of tournaments in the range
        """
        return self.get_query().filter(
            and_(
                ChampionshipYear.year >= start_year,
                ChampionshipYear.year <= end_year
            )
        ).order_by(ChampionshipYear.year).all()
    
    def get_tournament_with_stats(self, tournament_id: int) -> Dict[str, Any]:
        """
        Get tournament with comprehensive statistics
        
        Args:
            tournament_id: Tournament ID
            
        Returns:
            Dictionary with tournament data and statistics
        """
        tournament = self.get_by_id(tournament_id)
        if not tournament:
            return {}
        
        # Count games by round
        round_counts = self.db.session.query(
            Game.round,
            func.count(Game.id)
        ).filter(
            Game.year_id == tournament_id
        ).group_by(Game.round).all()
        
        # Count total games
        total_games = self.db.session.query(func.count(Game.id)).filter(
            Game.year_id == tournament_id
        ).scalar() or 0
        
        # Count completed games
        completed_games = self.db.session.query(func.count(Game.id)).filter(
            and_(
                Game.year_id == tournament_id,
                Game.team1_score.isnot(None),
                Game.team2_score.isnot(None)
            )
        ).scalar() or 0
        
        # Get participating teams
        team1_codes = self.db.session.query(Game.team1_code).filter(
            Game.year_id == tournament_id
        ).distinct()
        team2_codes = self.db.session.query(Game.team2_code).filter(
            Game.year_id == tournament_id
        ).distinct()
        
        all_teams = set()
        for code in team1_codes:
            if code[0] and not self._is_placeholder_team(code[0]):
                all_teams.add(code[0])
        for code in team2_codes:
            if code[0] and not self._is_placeholder_team(code[0]):
                all_teams.add(code[0])
        
        # Get venue information
        venues = self.db.session.query(
            Game.venue,
            func.count(Game.id)
        ).filter(
            Game.year_id == tournament_id
        ).group_by(Game.venue).all()
        
        return {
            'tournament': tournament,
            'total_games': total_games,
            'completed_games': completed_games,
            'rounds': {round: count for round, count in round_counts},
            'participating_teams': sorted(list(all_teams)),
            'venues': {venue: count for venue, count in venues if venue}
        }
    
    def get_tournament_standings(self, tournament_id: int, group: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get tournament standings with team statistics
        
        Args:
            tournament_id: Tournament ID
            group: Optional group filter (e.g., 'A', 'B')
            
        Returns:
            List of team standings ordered by points, goal difference
        """
        # Get all games for the tournament
        query = self.db.session.query(Game).filter(
            Game.year_id == tournament_id
        )
        
        if group:
            query = query.filter(Game.group == group)
        
        games = query.all()
        
        # Calculate standings from games
        team_stats = {}
        
        for game in games:
            # Skip games without scores
            if game.team1_score is None or game.team2_score is None:
                continue
            
            # Initialize team entries if not exists
            for team_code in [game.team1_code, game.team2_code]:
                if self._is_placeholder_team(team_code):
                    continue
                    
                if team_code not in team_stats:
                    team_stats[team_code] = {
                        'team_code': team_code,
                        'group': game.group,
                        'games_played': 0,
                        'wins': 0,
                        'draws': 0,
                        'losses': 0,
                        'ot_wins': 0,
                        'ot_losses': 0,
                        'goals_for': 0,
                        'goals_against': 0,
                        'points': 0
                    }
            
            # Update statistics for team1
            if not self._is_placeholder_team(game.team1_code):
                stats1 = team_stats[game.team1_code]
                stats1['games_played'] += 1
                stats1['goals_for'] += game.team1_score
                stats1['goals_against'] += game.team2_score
                stats1['points'] += game.team1_points
                
                # Determine win/loss type
                if game.team1_score > game.team2_score:
                    if game.result_type == 'REG':
                        stats1['wins'] += 1
                    else:
                        stats1['ot_wins'] += 1
                elif game.team1_score < game.team2_score:
                    if game.result_type == 'REG':
                        stats1['losses'] += 1
                    else:
                        stats1['ot_losses'] += 1
                else:
                    stats1['draws'] += 1
            
            # Update statistics for team2
            if not self._is_placeholder_team(game.team2_code):
                stats2 = team_stats[game.team2_code]
                stats2['games_played'] += 1
                stats2['goals_for'] += game.team2_score
                stats2['goals_against'] += game.team1_score
                stats2['points'] += game.team2_points
                
                # Determine win/loss type
                if game.team2_score > game.team1_score:
                    if game.result_type == 'REG':
                        stats2['wins'] += 1
                    else:
                        stats2['ot_wins'] += 1
                elif game.team2_score < game.team1_score:
                    if game.result_type == 'REG':
                        stats2['losses'] += 1
                    else:
                        stats2['ot_losses'] += 1
                else:
                    stats2['draws'] += 1
        
        # Convert to list and calculate goal difference
        standings = []
        for team_code, stats in team_stats.items():
            stats['goal_difference'] = stats['goals_for'] - stats['goals_against']
            standings.append(stats)
        
        # Sort by points (desc), goal difference (desc), goals for (desc)
        standings.sort(key=lambda x: (
            -x['points'],
            -x['goal_difference'],
            -x['goals_for']
        ))
        
        # Add position numbers
        for i, team in enumerate(standings, 1):
            team['position'] = i
        
        return standings
    
    def get_tournament_schedule(self, tournament_id: int, round: Optional[str] = None) -> List[Game]:
        """
        Get tournament game schedule
        
        Args:
            tournament_id: Tournament ID
            round: Optional round filter
            
        Returns:
            List of games ordered by game number
        """
        query = self.db.session.query(Game).filter(
            Game.year_id == tournament_id
        )
        
        if round:
            query = query.filter(Game.round == round)
        
        return query.order_by(Game.game_number).all()
    
    def get_tournament_results(self, tournament_id: int, 
                              round: Optional[str] = None,
                              team_code: Optional[str] = None) -> List[Game]:
        """
        Get completed games (results) for a tournament
        
        Args:
            tournament_id: Tournament ID
            round: Optional round filter
            team_code: Optional team filter
            
        Returns:
            List of completed games
        """
        query = self.db.session.query(Game).filter(
            and_(
                Game.year_id == tournament_id,
                Game.team1_score.isnot(None),
                Game.team2_score.isnot(None)
            )
        )
        
        if round:
            query = query.filter(Game.round == round)
        
        if team_code:
            query = query.filter(
                or_(
                    Game.team1_code == team_code,
                    Game.team2_code == team_code
                )
            )
        
        return query.order_by(Game.game_number).all()
    
    def count_tournaments(self) -> int:
        """
        Count total number of tournaments
        
        Returns:
            Total tournament count
        """
        return self.count()
    
    def get_tournament_team_performance(self, tournament_id: int, team_code: str) -> Dict[str, Any]:
        """
        Get detailed team performance in a tournament
        
        Args:
            tournament_id: Tournament ID
            team_code: Team code
            
        Returns:
            Dictionary with team performance metrics
        """
        # Get all games for the team
        games = self.db.session.query(Game).filter(
            and_(
                Game.year_id == tournament_id,
                or_(
                    Game.team1_code == team_code,
                    Game.team2_code == team_code
                )
            )
        ).order_by(Game.game_number).all()
        
        # Calculate metrics
        games_played = 0
        wins_reg = 0
        wins_ot = 0
        losses_reg = 0
        losses_ot = 0
        draws = 0
        goals_scored = 0
        goals_conceded = 0
        points = 0
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            games_played += 1
            
            if game.team1_code == team_code:
                goals_scored += game.team1_score
                goals_conceded += game.team2_score
                points += game.team1_points
                
                if game.team1_score > game.team2_score:
                    if game.result_type == 'REG':
                        wins_reg += 1
                    else:
                        wins_ot += 1
                elif game.team1_score < game.team2_score:
                    if game.result_type == 'REG':
                        losses_reg += 1
                    else:
                        losses_ot += 1
                else:
                    draws += 1
            else:
                goals_scored += game.team2_score
                goals_conceded += game.team1_score
                points += game.team2_points
                
                if game.team2_score > game.team1_score:
                    if game.result_type == 'REG':
                        wins_reg += 1
                    else:
                        wins_ot += 1
                elif game.team2_score < game.team1_score:
                    if game.result_type == 'REG':
                        losses_reg += 1
                    else:
                        losses_ot += 1
                else:
                    draws += 1
        
        # Create team stats summary
        team_stats = {
            'team_code': team_code,
            'games_played': games_played,
            'wins': wins_reg,
            'ot_wins': wins_ot,
            'losses': losses_reg,
            'ot_losses': losses_ot,
            'draws': draws,
            'goals_for': goals_scored,
            'goals_against': goals_conceded,
            'goal_difference': goals_scored - goals_conceded,
            'points': points
        }
        
        return {
            'team_stats': team_stats,
            'games': games,
            'wins_regulation': wins_reg,
            'wins_overtime': wins_ot,
            'losses_regulation': losses_reg,
            'losses_overtime': losses_ot,
            'total_goals_scored': goals_scored,
            'total_goals_conceded': goals_conceded,
            'goal_differential': goals_scored - goals_conceded
        }
    
    def search_tournaments(self, criteria: Dict[str, Any]) -> List[ChampionshipYear]:
        """
        Search tournaments with multiple criteria
        
        Args:
            criteria: Search criteria dictionary
            
        Returns:
            List of matching tournaments
        """
        query = self.get_query()
        
        # Year range filter
        if 'start_year' in criteria:
            query = query.filter(ChampionshipYear.year >= criteria['start_year'])
        
        if 'end_year' in criteria:
            query = query.filter(ChampionshipYear.year <= criteria['end_year'])
        
        # Name filter (partial match)
        if 'name' in criteria:
            query = query.filter(
                ChampionshipYear.name.like(f"%{criteria['name']}%")
            )
        
        # Has fixture filter
        if 'has_fixture' in criteria:
            if criteria['has_fixture']:
                query = query.filter(ChampionshipYear.fixture_path.isnot(None))
            else:
                query = query.filter(ChampionshipYear.fixture_path.is_(None))
        
        # Order by year descending by default
        query = query.order_by(desc(ChampionshipYear.year))
        
        return query.all()
    
    def _is_placeholder_team(self, team_code: str) -> bool:
        """Check if team code is a placeholder"""
        if not team_code:
            return True
        placeholders = ['A', 'B', 'W', 'L', 'Q', 'S']
        return (team_code[0] in placeholders and 
                len(team_code) > 1 and 
                team_code[1:].isdigit())