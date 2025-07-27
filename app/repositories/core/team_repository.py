"""
Team Repository for IIHF World Championship Statistics
Handles team-specific data access patterns and aggregations
"""

from typing import List, Optional, Dict, Any, Set
from sqlalchemy import and_, or_, func, distinct
from models import Game, Player, Goal, Penalty, ShotsOnGoal, TeamStats, AllTimeTeamStats, db
from app.repositories.base import BaseRepository
from constants import TEAM_ISO_CODES, PIM_MAP, POWERPLAY_PENALTY_TYPES
import logging

logger = logging.getLogger(__name__)


class TeamRepository(BaseRepository[Game]):
    """
    Repository for team-specific queries and data access
    Note: Teams don't have a dedicated model, they are derived from Game data
    """
    
    def __init__(self):
        # We use Game as the base model since teams are derived from games
        super().__init__(Game)
    
    def get_all_teams(self, year_id: Optional[int] = None) -> List[str]:
        """
        Get all unique team codes
        
        Args:
            year_id: Optional year filter
            
        Returns:
            List of unique team codes
        """
        query = self.db.session.query(Game.team1_code).distinct()
        if year_id:
            query = query.filter(Game.year_id == year_id)
        
        team1_codes = [code[0] for code in query.all()]
        
        query = self.db.session.query(Game.team2_code).distinct()
        if year_id:
            query = query.filter(Game.year_id == year_id)
        
        team2_codes = [code[0] for code in query.all()]
        
        # Combine and get unique codes, filtering out placeholders
        all_codes = set(team1_codes + team2_codes)
        
        # Filter out placeholder teams
        valid_teams = []
        for code in all_codes:
            if code and not self._is_placeholder_team(code):
                valid_teams.append(code)
        
        return sorted(valid_teams)
    
    def get_teams_by_year(self, year_id: int) -> List[str]:
        """
        Get all teams that participated in a specific year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            List of team codes
        """
        return self.get_all_teams(year_id)
    
    def get_team_games(self, team_code: str, year_id: Optional[int] = None) -> List[Game]:
        """
        Get all games for a specific team
        
        Args:
            team_code: Team code (e.g., 'CAN')
            year_id: Optional year filter
            
        Returns:
            List of games involving the team
        """
        query = self.get_query().filter(
            or_(
                Game.team1_code == team_code,
                Game.team2_code == team_code
            )
        )
        
        if year_id:
            query = query.filter(Game.year_id == year_id)
        
        return query.order_by(Game.game_number).all()
    
    def get_team_players(self, team_code: str, year_id: Optional[int] = None) -> List[Player]:
        """
        Get all players for a team
        
        Args:
            team_code: Team code
            year_id: Optional year filter (to get players who scored/assisted in that year)
            
        Returns:
            List of players
        """
        if year_id:
            # Get players who participated in goals during this year
            game_ids = self.db.session.query(Game.id).filter(
                and_(
                    Game.year_id == year_id,
                    or_(
                        Game.team1_code == team_code,
                        Game.team2_code == team_code
                    )
                )
            ).subquery()
            
            # Get unique player IDs from goals
            player_ids = self.db.session.query(
                distinct(Goal.scorer_id)
            ).filter(
                and_(
                    Goal.game_id.in_(game_ids),
                    Goal.team_code == team_code
                )
            ).union(
                self.db.session.query(distinct(Goal.assist1_id)).filter(
                    and_(
                        Goal.game_id.in_(game_ids),
                        Goal.team_code == team_code,
                        Goal.assist1_id.isnot(None)
                    )
                )
            ).union(
                self.db.session.query(distinct(Goal.assist2_id)).filter(
                    and_(
                        Goal.game_id.in_(game_ids),
                        Goal.team_code == team_code,
                        Goal.assist2_id.isnot(None)
                    )
                )
            )
            
            player_id_list = [pid[0] for pid in player_ids.all()]
            
            return Player.query.filter(
                and_(
                    Player.team_code == team_code,
                    Player.id.in_(player_id_list)
                )
            ).all()
        else:
            # Get all players for the team
            return Player.query.filter_by(team_code=team_code).all()
    
    def get_team_stats(self, team_code: str, year_id: int, 
                      round_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a team
        
        Args:
            team_code: Team code
            year_id: Championship year ID
            round_filter: Optional round filter
            
        Returns:
            Dictionary with team statistics
        """
        # Get games
        games = self.get_team_games(team_code, year_id)
        
        if round_filter:
            games = [g for g in games if g.round == round_filter]
        
        # Initialize stats
        stats = {
            'team_code': team_code,
            'team_iso': TEAM_ISO_CODES.get(team_code, ""),
            'games_played': 0,
            'wins': 0,
            'ot_wins': 0,
            'so_wins': 0,
            'losses': 0,
            'ot_losses': 0,
            'so_losses': 0,
            'goals_for': 0,
            'goals_against': 0,
            'points': 0,
            'shots_for': 0,
            'shots_against': 0,
            'powerplay_goals': 0,
            'powerplay_opportunities': 0,
            'penalty_minutes': 0,
            'empty_net_goals': 0,
            'shutouts': 0
        }
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            stats['games_played'] += 1
            
            # Determine if team is team1 or team2
            is_team1 = game.team1_code == team_code
            
            if is_team1:
                team_score = game.team1_score
                opponent_score = game.team2_score
                team_points = game.team1_points
            else:
                team_score = game.team2_score
                opponent_score = game.team1_score
                team_points = game.team2_points
            
            # Update goal stats
            stats['goals_for'] += team_score
            stats['goals_against'] += opponent_score
            stats['points'] += team_points
            
            # Win/loss tracking
            if team_score > opponent_score:
                if game.result_type == 'REG':
                    stats['wins'] += 1
                elif game.result_type == 'OT':
                    stats['ot_wins'] += 1
                elif game.result_type == 'SO':
                    stats['so_wins'] += 1
            else:
                if game.result_type == 'REG':
                    stats['losses'] += 1
                elif game.result_type == 'OT':
                    stats['ot_losses'] += 1
                elif game.result_type == 'SO':
                    stats['so_losses'] += 1
            
            # Check for shutouts
            if opponent_score == 0:
                stats['shutouts'] += 1
            
            # Get additional stats for this game
            game_stats = self._get_game_team_stats(game.id, team_code)
            stats['shots_for'] += game_stats['shots_for']
            stats['shots_against'] += game_stats['shots_against']
            stats['powerplay_goals'] += game_stats['pp_goals']
            stats['powerplay_opportunities'] += game_stats['pp_opportunities']
            stats['penalty_minutes'] += game_stats['pim']
            stats['empty_net_goals'] += game_stats['eng']
        
        # Calculate derived stats
        stats['goal_differential'] = stats['goals_for'] - stats['goals_against']
        
        if stats['powerplay_opportunities'] > 0:
            stats['powerplay_percentage'] = (
                stats['powerplay_goals'] / stats['powerplay_opportunities'] * 100
            )
        else:
            stats['powerplay_percentage'] = 0.0
        
        return stats
    
    def _get_game_team_stats(self, game_id: int, team_code: str) -> Dict[str, Any]:
        """
        Get team-specific stats for a single game
        """
        stats = {
            'shots_for': 0,
            'shots_against': 0,
            'pp_goals': 0,
            'pp_opportunities': 0,
            'pim': 0,
            'eng': 0
        }
        
        # Get game to determine opponent
        game = Game.query.get(game_id)
        if not game:
            return stats
        
        opponent_code = game.team2_code if game.team1_code == team_code else game.team1_code
        
        # Shots on goal
        sog_entries = ShotsOnGoal.query.filter_by(game_id=game_id).all()
        for sog in sog_entries:
            if sog.team_code == team_code:
                stats['shots_for'] += sog.shots
            elif sog.team_code == opponent_code:
                stats['shots_against'] += sog.shots
        
        # Goals
        goals = Goal.query.filter_by(game_id=game_id).all()
        for goal in goals:
            if goal.team_code == team_code:
                if goal.goal_type == "PP":
                    stats['pp_goals'] += 1
                if goal.is_empty_net:
                    stats['eng'] += 1
        
        # Penalties
        penalties = Penalty.query.filter_by(game_id=game_id).all()
        for penalty in penalties:
            if penalty.team_code == team_code:
                stats['pim'] += PIM_MAP.get(penalty.penalty_type, 0)
            elif penalty.team_code == opponent_code and penalty.penalty_type in POWERPLAY_PENALTY_TYPES:
                # Opponent penalty gives us a powerplay opportunity
                stats['pp_opportunities'] += 1
        
        return stats
    
    def get_team_standings(self, year_id: int, group: Optional[str] = None) -> List[TeamStats]:
        """
        Get team standings for a year, optionally filtered by group
        
        Args:
            year_id: Championship year ID
            group: Optional group filter
            
        Returns:
            List of TeamStats objects sorted by ranking
        """
        # Get all teams
        teams = self.get_teams_by_year(year_id)
        standings = []
        
        for team_code in teams:
            # Get team's games
            games = self.get_team_games(team_code, year_id)
            
            # Filter by group if specified
            if group:
                games = [g for g in games if g.group == group and g.round == 'Preliminary Round']
            else:
                games = [g for g in games if g.round == 'Preliminary Round']
            
            # Skip if no games in this group
            if not games:
                continue
            
            # Create TeamStats object
            team_stats = TeamStats(
                name=team_code,
                group=games[0].group if games and games[0].group else ""
            )
            
            # Calculate stats from games
            for game in games:
                if game.team1_score is None or game.team2_score is None:
                    continue
                
                team_stats.gp += 1
                
                is_team1 = game.team1_code == team_code
                if is_team1:
                    team_score = game.team1_score
                    opponent_score = game.team2_score
                    points = game.team1_points
                else:
                    team_score = game.team2_score
                    opponent_score = game.team1_score
                    points = game.team2_points
                
                team_stats.gf += team_score
                team_stats.ga += opponent_score
                team_stats.pts += points
                
                # Win/loss tracking
                if team_score > opponent_score:
                    if game.result_type == 'REG':
                        team_stats.w += 1
                    elif game.result_type == 'OT':
                        team_stats.otw += 1
                    elif game.result_type == 'SO':
                        team_stats.sow += 1
                else:
                    if game.result_type == 'REG':
                        team_stats.l += 1
                    elif game.result_type == 'OT':
                        team_stats.otl += 1
                    elif game.result_type == 'SO':
                        team_stats.sol += 1
            
            standings.append(team_stats)
        
        # Sort standings
        standings.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        
        # Assign ranks
        for i, team in enumerate(standings):
            team.rank_in_group = i + 1
        
        return standings
    
    def get_all_time_stats(self, team_code: str) -> AllTimeTeamStats:
        """
        Get all-time statistics for a team across all years
        
        Args:
            team_code: Team code
            
        Returns:
            AllTimeTeamStats object
        """
        stats = AllTimeTeamStats(team_code=team_code)
        
        # Get all games for this team
        games = self.get_team_games(team_code)
        
        # Track years
        years = set()
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            years.add(game.year_id)
            stats.gp += 1
            
            is_team1 = game.team1_code == team_code
            if is_team1:
                team_score = game.team1_score
                opponent_score = game.team2_score
                points = game.team1_points
            else:
                team_score = game.team2_score
                opponent_score = game.team1_score
                points = game.team2_points
            
            stats.gf += team_score
            stats.ga += opponent_score
            stats.pts += points
            
            # Win/loss tracking
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
        
        # Get actual years from ChampionshipYear model
        from models import ChampionshipYear
        year_objs = ChampionshipYear.query.filter(
            ChampionshipYear.id.in_(years)
        ).all()
        
        stats.years_participated = {y.year for y in year_objs}
        
        return stats
    
    def get_head_to_head_record(self, team1_code: str, team2_code: str,
                               year_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get head-to-head record between two teams
        
        Args:
            team1_code: First team code
            team2_code: Second team code
            year_id: Optional year filter
            
        Returns:
            Dictionary with head-to-head statistics
        """
        query = self.get_query().filter(
            or_(
                and_(Game.team1_code == team1_code, Game.team2_code == team2_code),
                and_(Game.team1_code == team2_code, Game.team2_code == team1_code)
            )
        )
        
        if year_id:
            query = query.filter(Game.year_id == year_id)
        
        games = query.all()
        
        # Calculate statistics
        team1_wins = 0
        team2_wins = 0
        team1_goals = 0
        team2_goals = 0
        games_played = 0
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            games_played += 1
            
            # Determine which team is which in this game
            if game.team1_code == team1_code:
                team1_goals += game.team1_score
                team2_goals += game.team2_score
                if game.team1_score > game.team2_score:
                    team1_wins += 1
                else:
                    team2_wins += 1
            else:
                team1_goals += game.team2_score
                team2_goals += game.team1_score
                if game.team2_score > game.team1_score:
                    team1_wins += 1
                else:
                    team2_wins += 1
        
        return {
            'games': games,
            'games_played': games_played,
            f'{team1_code}_wins': team1_wins,
            f'{team2_code}_wins': team2_wins,
            f'{team1_code}_goals': team1_goals,
            f'{team2_code}_goals': team2_goals,
            'goal_differential': team1_goals - team2_goals
        }
    
    def count_teams_by_year(self, year_id: int) -> int:
        """
        Count number of teams in a year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            Number of teams
        """
        return len(self.get_teams_by_year(year_id))
    
    def get_team_performance_by_round(self, team_code: str, year_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Get team performance broken down by round
        
        Args:
            team_code: Team code
            year_id: Championship year ID
            
        Returns:
            Dictionary mapping round names to performance stats
        """
        games = self.get_team_games(team_code, year_id)
        
        performance = {}
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            round_name = game.round
            if round_name not in performance:
                performance[round_name] = {
                    'games': 0,
                    'wins': 0,
                    'losses': 0,
                    'goals_for': 0,
                    'goals_against': 0,
                    'points': 0
                }
            
            performance[round_name]['games'] += 1
            
            is_team1 = game.team1_code == team_code
            if is_team1:
                team_score = game.team1_score
                opponent_score = game.team2_score
                points = game.team1_points
            else:
                team_score = game.team2_score
                opponent_score = game.team1_score
                points = game.team2_points
            
            performance[round_name]['goals_for'] += team_score
            performance[round_name]['goals_against'] += opponent_score
            performance[round_name]['points'] += points
            
            if team_score > opponent_score:
                performance[round_name]['wins'] += 1
            else:
                performance[round_name]['losses'] += 1
        
        return performance
    
    def _is_placeholder_team(self, team_code: str) -> bool:
        """Check if team code is a placeholder"""
        if not team_code:
            return True
        placeholders = ['A', 'B', 'W', 'L', 'Q', 'S']
        return (team_code[0] in placeholders and 
                len(team_code) > 1 and 
                team_code[1:].isdigit())