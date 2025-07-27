"""
Team Service for IIHF World Championship Statistics
Handles all business logic related to teams, team statistics, and team performance
"""

from typing import Dict, List, Optional, Tuple, Any, Set
from models import Game, ChampionshipYear, TeamStats, TeamOverallStats, AllTimeTeamStats, Player, db
from services.base import BaseService
from services.exceptions import ServiceError, ValidationError, NotFoundError
from app.repositories.core.team_repository import TeamRepository
from constants import TEAM_ISO_CODES, TEAM_NAMES
import logging

logger = logging.getLogger(__name__)


class TeamService(BaseService[Game]):  # Note: We use Game as base since teams are not stored as separate entities
    """
    Service for team-related business logic
    Manages team statistics, standings, head-to-head records, and performance tracking
    """
    
    def __init__(self):
        super().__init__(Game)  # Teams are derived from games
        self.repository = TeamRepository()  # Repository für Datenbankzugriff
    
    def get_team_stats(self, year_id: int, team_code: str) -> TeamStats:
        """
        Get team statistics for a specific championship year
        
        Args:
            year_id: The championship year ID
            team_code: The team code
            
        Returns:
            TeamStats object with complete statistics
            
        Raises:
            NotFoundError: If year not found
            ValidationError: If team code is invalid
        """
        # Validate year exists
        year = ChampionshipYear.query.get(year_id)
        if not year:
            raise NotFoundError("Championship year", year_id)
        
        # Validate team code
        if not team_code or len(team_code) != 3:
            raise ValidationError("Team code must be exactly 3 characters", "team_code")
        
        # Get all games for the team
        games = self.repository.get_team_games(year_id, team_code.upper())
        
        # Calculate statistics
        stats = self._calculate_team_stats(games, team_code.upper())
        
        return stats
    
    def get_all_teams_stats(self, year_id: int) -> List[TeamStats]:
        """
        Get statistics for all teams in a championship year
        
        Args:
            year_id: The championship year ID
            
        Returns:
            List of TeamStats objects
            
        Raises:
            NotFoundError: If year not found
        """
        # Validate year exists
        year = ChampionshipYear.query.get(year_id)
        if not year:
            raise NotFoundError("Championship year", year_id)
        
        # Get all games for the year
        all_games = self.repository.get_all_games(year_id)
        
        # Extract unique team codes
        team_codes = self._extract_team_codes(all_games)
        
        # Calculate stats for each team
        team_stats = []
        for team_code in team_codes:
            team_games = [g for g in all_games if 
                         g.team1_code == team_code or g.team2_code == team_code]
            stats = self._calculate_team_stats(team_games, team_code)
            team_stats.append(stats)
        
        return team_stats
    
    def _calculate_team_stats(self, games: List[Game], team_code: str) -> TeamStats:
        """Calculate team statistics from games"""
        stats = TeamStats(
            name=team_code,
            group=self._determine_team_group(games, team_code)
        )
        
        for game in games:
            # Skip games without results
            if game.team1_score is None or game.team2_score is None:
                continue
            
            stats.gp += 1
            
            # Determine if team is team1 or team2
            if game.team1_code == team_code:
                team_score = game.team1_score
                opponent_score = game.team2_score
                team_points = game.team1_points
            else:
                team_score = game.team2_score
                opponent_score = game.team1_score
                team_points = game.team2_points
            
            # Update goals
            stats.gf += team_score
            stats.ga += opponent_score
            
            # Update wins/losses based on result type
            if team_score > opponent_score:
                if game.result_type == 'REG':
                    stats.w += 1
                elif game.result_type == 'OT':
                    stats.otw += 1
                elif game.result_type == 'SO':
                    stats.sow += 1
            else:
                if game.result_type == 'REG':
                    stats.l += 1
                elif game.result_type == 'OT':
                    stats.otl += 1
                elif game.result_type == 'SO':
                    stats.sol += 1
            
            # Update points
            stats.pts += team_points
        
        return stats
    
    def _determine_team_group(self, games: List[Game], team_code: str) -> str:
        """Determine team's group from their games"""
        for game in games:
            if (game.team1_code == team_code or game.team2_code == team_code) and game.group:
                return game.group
        return ""
    
    def _extract_team_codes(self, games: List[Game]) -> Set[str]:
        """Extract unique team codes from games"""
        team_codes = set()
        for game in games:
            if not self._is_placeholder_team(game.team1_code):
                team_codes.add(game.team1_code)
            if not self._is_placeholder_team(game.team2_code):
                team_codes.add(game.team2_code)
        return team_codes
    
    def _is_placeholder_team(self, team_code: str) -> bool:
        """Check if team code is a placeholder"""
        if not team_code:
            return True
        placeholders = ['A', 'B', 'W', 'L', 'Q', 'S']
        return (team_code[0] in placeholders and 
                len(team_code) > 1 and 
                team_code[1:].isdigit())
    
    def get_team_overall_stats(self, year_id: int, team_code: str) -> TeamOverallStats:
        """
        Get comprehensive team statistics including special teams
        
        Args:
            year_id: The championship year ID
            team_code: The team code
            
        Returns:
            TeamOverallStats object with detailed statistics
        """
        # Get basic stats first
        basic_stats = self.get_team_stats(year_id, team_code)
        
        # Get detailed game statistics
        detailed_stats = self.repository.get_team_detailed_stats(year_id, team_code)
        
        overall_stats = TeamOverallStats(
            team_name=team_code,
            team_iso_code=TEAM_ISO_CODES.get(team_code.upper(), None),
            gp=basic_stats.gp,
            gf=basic_stats.gf,
            ga=basic_stats.ga,
            eng=detailed_stats.get('empty_net_goals', 0),
            sog=detailed_stats.get('shots_on_goal', 0),
            soga=detailed_stats.get('shots_on_goal_against', 0),
            so=detailed_stats.get('shutouts', 0),
            ppgf=detailed_stats.get('powerplay_goals_for', 0),
            ppga=detailed_stats.get('powerplay_goals_against', 0),
            ppf=detailed_stats.get('powerplay_opportunities_for', 0),
            ppa=detailed_stats.get('powerplay_opportunities_against', 0),
            pim=detailed_stats.get('penalty_minutes', 0)
        )
        
        return overall_stats
    
    def get_head_to_head(self, year_id: int, team1_code: str, team2_code: str) -> Dict[str, Any]:
        """
        Get head-to-head record between two teams
        
        Args:
            year_id: The championship year ID (None for all-time)
            team1_code: First team code
            team2_code: Second team code
            
        Returns:
            Dictionary with head-to-head statistics
        """
        games = self.repository.get_head_to_head_games(year_id, team1_code, team2_code)
        
        # Calculate H2H stats
        team1_wins = 0
        team1_ot_wins = 0
        team1_so_wins = 0
        team2_wins = 0
        team2_ot_wins = 0
        team2_so_wins = 0
        team1_goals = 0
        team2_goals = 0
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            # Normalize team positions
            if game.team1_code == team1_code:
                t1_score = game.team1_score
                t2_score = game.team2_score
            else:
                t1_score = game.team2_score
                t2_score = game.team1_score
            
            team1_goals += t1_score
            team2_goals += t2_score
            
            # Count wins by type
            if t1_score > t2_score:
                if game.result_type == 'REG':
                    team1_wins += 1
                elif game.result_type == 'OT':
                    team1_ot_wins += 1
                elif game.result_type == 'SO':
                    team1_so_wins += 1
            else:
                if game.result_type == 'REG':
                    team2_wins += 1
                elif game.result_type == 'OT':
                    team2_ot_wins += 1
                elif game.result_type == 'SO':
                    team2_so_wins += 1
        
        return {
            'games_played': len(games),
            'team1': {
                'code': team1_code,
                'name': TEAM_NAMES.get(team1_code, team1_code),
                'wins': team1_wins,
                'ot_wins': team1_ot_wins,
                'so_wins': team1_so_wins,
                'total_wins': team1_wins + team1_ot_wins + team1_so_wins,
                'goals_for': team1_goals,
                'goals_against': team2_goals
            },
            'team2': {
                'code': team2_code,
                'name': TEAM_NAMES.get(team2_code, team2_code),
                'wins': team2_wins,
                'ot_wins': team2_ot_wins,
                'so_wins': team2_so_wins,
                'total_wins': team2_wins + team2_ot_wins + team2_so_wins,
                'goals_for': team2_goals,
                'goals_against': team1_goals
            },
            'games': games
        }
    
    def get_all_time_team_stats(self, team_code: str) -> AllTimeTeamStats:
        """
        Get all-time statistics for a team across all championships
        
        Args:
            team_code: The team code
            
        Returns:
            AllTimeTeamStats object
        """
        # Get all games for the team across all years
        all_games = self.repository.get_all_time_team_games(team_code)
        
        stats = AllTimeTeamStats(team_code=team_code)
        years = set()
        
        for game in all_games:
            # Skip incomplete games
            if game.team1_score is None or game.team2_score is None:
                continue
            
            stats.gp += 1
            years.add(game.championship_year.year)
            
            # Determine team position and scores
            if game.team1_code == team_code:
                team_score = game.team1_score
                opponent_score = game.team2_score
                team_points = game.team1_points
            else:
                team_score = game.team2_score
                opponent_score = game.team1_score
                team_points = game.team2_points
            
            # Update goals
            stats.gf += team_score
            stats.ga += opponent_score
            
            # Update wins/losses
            if team_score > opponent_score:
                if game.result_type == 'REG':
                    stats.w += 1
                elif game.result_type == 'OT':
                    stats.otw += 1
                elif game.result_type == 'SO':
                    stats.sow += 1
            else:
                if game.result_type == 'REG':
                    stats.l += 1
                elif game.result_type == 'OT':
                    stats.otl += 1
                elif game.result_type == 'SO':
                    stats.sol += 1
            
            # Update points
            stats.pts += team_points
        
        stats.years_participated = years
        
        return stats
    
    def get_team_roster(self, team_code: str, year_id: Optional[int] = None) -> List[Player]:
        """
        Get team roster
        
        Args:
            team_code: The team code
            year_id: Optional championship year ID
            
        Returns:
            List of players on the team
        """
        return self.repository.get_team_players(team_code, year_id)
    
    def get_team_performance_trends(self, team_code: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get team performance trends over recent years
        
        Args:
            team_code: The team code
            limit: Number of recent years to include
            
        Returns:
            List of yearly performance data
        """
        recent_years = self.repository.get_recent_championship_years(limit)
        
        trends = []
        for year in recent_years:
            try:
                stats = self.get_team_stats(year.id, team_code)
                trends.append({
                    'year': year.year,
                    'year_name': year.name,
                    'statistics': stats,
                    'win_percentage': self._calculate_win_percentage(stats)
                })
            except Exception as e:
                logger.warning(f"No data for {team_code} in year {year.year}: {str(e)}")
                continue
        
        return trends
    
    def _calculate_win_percentage(self, stats: TeamStats) -> float:
        """Calculate win percentage from team stats"""
        if stats.gp == 0:
            return 0.0
        
        # Count all wins (regulation + OT + SO)
        total_wins = stats.w + stats.otw + stats.sow
        return (total_wins / stats.gp) * 100
    
    def get_team_records(self, team_code: str) -> Dict[str, Any]:
        """
        Get team records (biggest wins, worst losses, etc.)
        
        Args:
            team_code: The team code
            
        Returns:
            Dictionary with various team records
        """
        all_games = self.repository.get_all_time_team_games(team_code)
        
        biggest_win = None
        worst_loss = None
        highest_scoring_game = None
        most_goals_scored = 0
        most_goals_conceded = 0
        
        for game in all_games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            # Determine team position
            if game.team1_code == team_code:
                team_score = game.team1_score
                opponent_score = game.team2_score
                opponent_code = game.team2_code
            else:
                team_score = game.team2_score
                opponent_score = game.team1_score
                opponent_code = game.team1_code
            
            # Track records
            goal_diff = team_score - opponent_score
            total_goals = team_score + opponent_score
            
            # Biggest win
            if goal_diff > 0 and (biggest_win is None or goal_diff > biggest_win['goal_difference']):
                biggest_win = {
                    'game': game,
                    'score': f"{team_score}-{opponent_score}",
                    'opponent': opponent_code,
                    'goal_difference': goal_diff,
                    'year': game.championship_year.year
                }
            
            # Worst loss
            if goal_diff < 0 and (worst_loss is None or goal_diff < worst_loss['goal_difference']):
                worst_loss = {
                    'game': game,
                    'score': f"{team_score}-{opponent_score}",
                    'opponent': opponent_code,
                    'goal_difference': goal_diff,
                    'year': game.championship_year.year
                }
            
            # Highest scoring game
            if highest_scoring_game is None or total_goals > highest_scoring_game['total_goals']:
                highest_scoring_game = {
                    'game': game,
                    'score': f"{team_score}-{opponent_score}",
                    'opponent': opponent_code,
                    'total_goals': total_goals,
                    'year': game.championship_year.year
                }
            
            # Most goals in a game
            if team_score > most_goals_scored:
                most_goals_scored = team_score
            
            if opponent_score > most_goals_conceded:
                most_goals_conceded = opponent_score
        
        return {
            'biggest_win': biggest_win,
            'worst_loss': worst_loss,
            'highest_scoring_game': highest_scoring_game,
            'most_goals_scored_game': most_goals_scored,
            'most_goals_conceded_game': most_goals_conceded
        }