"""
Player Service with Repository Pattern
Handles all business logic related to players and player statistics
"""

from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy import or_, func, case
from models import Player, Goal, Penalty, Game, ChampionshipYear, db
from app.services.base import BaseService
from app.services.utils.cache_manager import CacheableService, cached
from app.repositories.core import PlayerRepository
from services.exceptions import ServiceError, ValidationError, NotFoundError, DuplicateError
from constants import PIM_MAP, POWERPLAY_PENALTY_TYPES
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class PlayerService(CacheableService, BaseService[Player]):
    """
    Service for player-related business logic using repository pattern
    Manages players, player statistics, and tournament/team associations
    """
    
    def __init__(self, repository: Optional[PlayerRepository] = None):
        """
        Initialize service with repository and cache
        
        Args:
            repository: PlayerRepository instance (optional, will create if not provided)
        """
        if repository is None:
            repository = PlayerRepository()
        # Use proper MRO initialization
        super().__init__(repository)
    
    def create_player(self, team_code: str, first_name: str, last_name: str,
                     jersey_number: Optional[int] = None) -> Player:
        """
        Create a new player with validation
        
        Args:
            team_code: Team code (e.g., 'CAN', 'USA')
            first_name: Player's first name
            last_name: Player's last name
            jersey_number: Optional jersey number
            
        Returns:
            Created player object
            
        Raises:
            ValidationError: If input data is invalid
            DuplicateError: If player already exists
            ServiceError: If creation fails
        """
        try:
            # Validate input
            if not team_code or len(team_code) != 3:
                raise ValidationError("Team code must be 3 characters", "team_code")
            
            if not first_name or not first_name.strip():
                raise ValidationError("First name cannot be empty", "first_name")
            
            if not last_name or not last_name.strip():
                raise ValidationError("Last name cannot be empty", "last_name")
            
            if jersey_number is not None:
                if jersey_number < 1 or jersey_number > 99:
                    raise ValidationError("Jersey number must be between 1 and 99", "jersey_number")
                
                # Check for duplicate jersey number on same team
                existing = self.repository.get_player_by_jersey(team_code, jersey_number)
                if existing:
                    raise DuplicateError(
                        "Player",
                        "jersey_number",
                        f"{jersey_number} on team {team_code}"
                    )
            
            # Check for duplicate player (same name on same team)
            existing = self.repository.get_player_by_name(
                first_name.strip(),
                last_name.strip(),
                team_code
            )
            if existing:
                raise DuplicateError(
                    "Player",
                    "name",
                    f"{first_name} {last_name} on team {team_code}"
                )
            
            # Create player
            player = self.repository.create(
                team_code=team_code.upper(),
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                jersey_number=jersey_number
            )
            
            # Invalidate team cache
            self.invalidate_cache(f"team_roster_{team_code}")
            
            return player
            
        except (ValidationError, DuplicateError):
            raise
        except Exception as e:
            logger.error(f"Error creating player: {e}")
            raise ServiceError(f"Failed to create player: {e}")
    
    def get_player_statistics(self, player_id: int, year_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a player
        
        Args:
            player_id: Player ID
            year_id: Optional year filter
            
        Returns:
            Dictionary with player statistics
            
        Raises:
            NotFoundError: If player not found
            ServiceError: If retrieval fails
        """
        try:
            player = self.get_by_id(player_id)
            
            # Build cache key
            cache_key = f"player_stats_{player_id}"
            if year_id:
                cache_key += f"_year_{year_id}"
            
            # Check cache
            cached_stats = self.get_from_cache(cache_key)
            if cached_stats is not None:
                return cached_stats
            
            # Get goals, assists, and penalty minutes
            stats = self.repository.get_player_statistics(player_id, year_id)
            
            # Calculate additional statistics
            stats['points'] = stats['goals'] + stats['assists']
            stats['player'] = player
            
            # Get goal types breakdown
            goal_breakdown = self.repository.get_goal_types_for_player(player_id, year_id)
            stats['powerplay_goals'] = goal_breakdown.get('PP', 0)
            stats['shorthanded_goals'] = goal_breakdown.get('SH', 0)
            stats['even_strength_goals'] = stats['goals'] - stats['powerplay_goals'] - stats['shorthanded_goals']
            
            # Get penalty breakdown
            penalty_breakdown = self.repository.get_penalty_breakdown_for_player(player_id, year_id)
            stats['penalty_breakdown'] = penalty_breakdown
            
            # Calculate powerplay penalties
            pp_penalties = sum(
                count for penalty_type, count in penalty_breakdown.items()
                if penalty_type in POWERPLAY_PENALTY_TYPES
            )
            stats['powerplay_penalties'] = pp_penalties
            
            # Store in cache
            self.store_in_cache(cache_key, stats, ttl=300)
            
            return stats
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting player statistics: {e}")
            raise ServiceError(f"Failed to get player statistics: {e}")
    
    def manage_roster(self, team_code: str, add_players: Optional[List[int]] = None,
                     remove_players: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Manage team roster by adding or removing players
        
        Args:
            team_code: Team code to manage
            add_players: List of player IDs to add to team
            remove_players: List of player IDs to remove from team
            
        Returns:
            Updated roster information
            
        Raises:
            ValidationError: If invalid operations requested
            ServiceError: If operation fails
        """
        try:
            if not team_code or len(team_code) != 3:
                raise ValidationError("Invalid team code", "team_code")
            
            result = {
                'team_code': team_code,
                'added': [],
                'removed': [],
                'errors': []
            }
            
            # Process removals first
            if remove_players:
                for player_id in remove_players:
                    try:
                        player = self.get_by_id(player_id)
                        if player.team_code == team_code:
                            player.team_code = None
                            self.repository.update(player)
                            result['removed'].append({
                                'id': player.id,
                                'name': f"{player.first_name} {player.last_name}"
                            })
                        else:
                            result['errors'].append(f"Player {player_id} not on team {team_code}")
                    except NotFoundError:
                        result['errors'].append(f"Player {player_id} not found")
            
            # Process additions
            if add_players:
                for player_id in add_players:
                    try:
                        player = self.get_by_id(player_id)
                        if player.team_code != team_code:
                            player.team_code = team_code
                            self.repository.update(player)
                            result['added'].append({
                                'id': player.id,
                                'name': f"{player.first_name} {player.last_name}"
                            })
                        else:
                            result['errors'].append(f"Player {player_id} already on team {team_code}")
                    except NotFoundError:
                        result['errors'].append(f"Player {player_id} not found")
            
            # Invalidate team cache
            self.invalidate_cache(f"team_roster_{team_code}")
            self.invalidate_cache(f"team_stats_{team_code}")
            
            return result
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error managing roster: {e}")
            raise ServiceError(f"Failed to manage roster: {e}")
    
    def get_team_roster(self, team_code: str, include_stats: bool = False) -> Dict[str, Any]:
        """
        Get complete roster for a team
        
        Args:
            team_code: Team code
            include_stats: Whether to include player statistics
            
        Returns:
            Dictionary with team roster information
            
        Raises:
            ValidationError: If team code invalid
            ServiceError: If retrieval fails
        """
        if not team_code or len(team_code) != 3:
            raise ValidationError("Invalid team code", "team_code")
        
        if include_stats:
            # Get players with basic statistics
            players_with_stats = self.repository.get_players_with_stats(team_code.upper())
            
            return {
                'team_code': team_code.upper(),
                'players': players_with_stats,
                'total_players': len(players_with_stats),
                'total_goals': sum(p['goals'] for p in players_with_stats),
                'total_assists': sum(p['assists'] for p in players_with_stats),
                'total_points': sum(p['points'] for p in players_with_stats)
            }
        else:
            # Get basic roster
            return self.repository.get_team_roster(team_code.upper())
    
    def search_players(self, search_term: str, team_code: Optional[str] = None) -> List[Player]:
        """
        Search for players by name
        
        Args:
            search_term: Search term for player name
            team_code: Optional team filter
            
        Returns:
            List of matching players
        """
        if not search_term or len(search_term) < 2:
            raise ValidationError("Search term must be at least 2 characters", "search_term")
        
        return self.repository.search_players(search_term, team_code)
    
    @cached(ttl=600, key_prefix="player:tournament_leaders")
    def get_tournament_scoring_leaders(self, year_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get tournament scoring leaders
        
        Args:
            year_id: Championship year ID
            limit: Number of players to return
            
        Returns:
            List of top scorers with statistics
        """
        # This would need to be implemented with proper year association
        # For now, returning empty list
        # TODO: Implement with proper year association
        return []
    
    def get_penalties_by_type(self, player_id: int, year_id: Optional[int] = None) -> Dict[str, int]:
        """
        Get penalty breakdown by type for a player
        
        Args:
            player_id: Player ID
            year_id: Optional year filter
            
        Returns:
            Dictionary with penalty types and counts
        """
        try:
            return self.repository.get_penalty_breakdown_for_player(player_id, year_id)
        except Exception as e:
            logger.error(f"Error getting penalty breakdown: {e}")
            raise ServiceError(f"Failed to get penalty breakdown: {e}")
    
    def merge_players(self, keep_player_id: int, merge_player_id: int) -> Player:
        """
        Merge two player records (e.g., for duplicate cleanup)
        
        Args:
            keep_player_id: ID of player to keep
            merge_player_id: ID of player to merge and delete
            
        Returns:
            The kept player with merged statistics
            
        Raises:
            NotFoundError: If either player not found
            ValidationError: If players are on different teams
            ServiceError: If merge fails
        """
        try:
            keep_player = self.get_by_id(keep_player_id)
            merge_player = self.get_by_id(merge_player_id)
            
            # Validate same team
            if keep_player.team_code != merge_player.team_code:
                raise ValidationError(
                    f"Cannot merge players from different teams: {keep_player.team_code} != {merge_player.team_code}",
                    "team_code"
                )
            
            # Merge in transaction
            with self.repository.db.session.begin_nested():
                # Update all goals
                Goal.query.filter_by(scorer_id=merge_player_id).update({'scorer_id': keep_player_id})
                Goal.query.filter_by(assist1_id=merge_player_id).update({'assist1_id': keep_player_id})
                Goal.query.filter_by(assist2_id=merge_player_id).update({'assist2_id': keep_player_id})
                
                # Update all penalties
                Penalty.query.filter_by(player_id=merge_player_id).update({'player_id': keep_player_id})
                
                # Delete merged player
                self.repository.delete(merge_player_id)
            
            # Invalidate all caches
            self.invalidate_cache(f"player_{keep_player_id}")
            self.invalidate_cache(f"player_{merge_player_id}")
            self.invalidate_cache(f"team_roster_{keep_player.team_code}")
            
            return keep_player
            
        except (NotFoundError, ValidationError):
            raise
        except Exception as e:
            logger.error(f"Error merging players: {e}")
            raise ServiceError(f"Failed to merge players: {e}")
    
    def get_players_for_year(self, year_id: int) -> List[Dict[str, Any]]:
        """
        Get all players who participated in a specific year with statistics
        
        Args:
            year_id: Championship year ID
            
        Returns:
            List of players with their statistics for that year
        """
        try:
            # Get unique players from goals and penalties for the year
            players_from_goals = self.repository.db.session.query(Player).join(
                Goal, or_(
                    Goal.scorer_id == Player.id,
                    Goal.assist1_id == Player.id,
                    Goal.assist2_id == Player.id
                )
            ).join(Game).filter(Game.year_id == year_id).distinct().all()
            
            players_from_penalties = self.repository.db.session.query(Player).join(
                Penalty
            ).join(Game).filter(Game.year_id == year_id).distinct().all()
            
            # Combine and deduplicate
            all_players = list(set(players_from_goals + players_from_penalties))
            
            # Get statistics for each player
            result = []
            for player in all_players:
                stats = self.get_player_statistics(player.id, year_id)
                result.append({
                    'player': player,
                    'statistics': stats
                })
            
            # Sort by points, then goals
            result.sort(key=lambda x: (x['statistics']['points'], x['statistics']['goals']), reverse=True)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting players for year: {e}")
            raise ServiceError(f"Failed to get players for year: {e}")
    
    def get_inactive_players(self, years_inactive: int = 3) -> List[Dict[str, Any]]:
        """
        Get players who haven't played in recent years
        
        Args:
            years_inactive: Number of years to consider as inactive
            
        Returns:
            List of inactive players with last activity
        """
        try:
            # This would need proper implementation with year tracking
            # TODO: Implement inactive player tracking
            return []
            
        except Exception as e:
            logger.error(f"Error getting inactive players: {e}")
            raise ServiceError(f"Failed to get inactive players: {e}")
    
    @cached(ttl=600, key_prefix="player:career_totals")
    def get_career_totals(self, player_id: int) -> Dict[str, Any]:
        """
        Get career totals for a player across all years
        
        Args:
            player_id: Player ID
            
        Returns:
            Dictionary with career statistics and year breakdown
        """
        try:
            player = self.get_by_id(player_id)
            
            # Get all-time statistics
            career_stats = self.get_player_statistics(player_id)
            
            # Get year-by-year breakdown
            years_played = self.repository.get_years_played(player_id)
            yearly_stats = []
            
            for year in years_played:
                year_stats = self.get_player_statistics(player_id, year['year_id'])
                yearly_stats.append({
                    'year': year['year'],
                    'year_id': year['year_id'],
                    'statistics': year_stats
                })
            
            return {
                'player': player,
                'career_totals': career_stats,
                'years_played': len(years_played),
                'yearly_breakdown': yearly_stats
            }
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting career totals: {e}")
            raise ServiceError(f"Failed to get career totals: {e}")
    
    def get_milestone_achievements(self, player_id: int) -> List[Dict[str, Any]]:
        """
        Get milestone achievements for a player (100 goals, 200 points, etc.)
        
        Args:
            player_id: Player ID
            
        Returns:
            List of achieved milestones
        """
        try:
            stats = self.get_player_statistics(player_id)
            milestones = []
            
            # Goal milestones
            goal_milestones = [100, 200, 300, 400, 500]
            for milestone in goal_milestones:
                if stats['goals'] >= milestone:
                    milestones.append({
                        'type': 'goals',
                        'value': milestone,
                        'achieved': True,
                        'current': stats['goals']
                    })
            
            # Point milestones
            point_milestones = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
            for milestone in point_milestones:
                if stats['points'] >= milestone:
                    milestones.append({
                        'type': 'points',
                        'value': milestone,
                        'achieved': True,
                        'current': stats['points']
                    })
            
            # Assist milestones
            assist_milestones = [100, 200, 300, 400, 500]
            for milestone in assist_milestones:
                if stats['assists'] >= milestone:
                    milestones.append({
                        'type': 'assists',
                        'value': milestone,
                        'achieved': True,
                        'current': stats['assists']
                    })
            
            return milestones
            
        except Exception as e:
            logger.error(f"Error getting milestone achievements: {e}")
            raise ServiceError(f"Failed to get milestone achievements: {e}")
    
    def compare_players(self, player_ids: List[int], year_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Compare statistics for multiple players
        
        Args:
            player_ids: List of player IDs to compare
            year_id: Optional year filter
            
        Returns:
            List of player statistics for comparison
        """
        try:
            if len(player_ids) < 2:
                raise ValidationError("Need at least 2 players to compare", "player_ids")
            
            if len(player_ids) > 10:
                raise ValidationError("Can compare maximum 10 players", "player_ids")
            
            comparisons = []
            for player_id in player_ids:
                try:
                    player = self.get_by_id(player_id)
                    stats = self.get_player_statistics(player_id, year_id)
                    comparisons.append({
                        'player': player,
                        'statistics': stats
                    })
                except NotFoundError:
                    logger.warning(f"Player {player_id} not found for comparison")
            
            # Sort by points for easy comparison
            comparisons.sort(key=lambda x: x['statistics']['points'], reverse=True)
            
            return comparisons
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error comparing players: {e}")
            raise ServiceError(f"Failed to compare players: {e}")
    
    @cached(ttl=1800, key_prefix="player:all_time_leaders")
    def get_all_time_leaders(self, category: str = 'points', limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all-time statistical leaders
        
        Args:
            category: Statistical category ('points', 'goals', 'assists', 'penalty_minutes')
            limit: Number of players to return
            
        Returns:
            List of top players in the category
        """
        try:
            valid_categories = ['points', 'goals', 'assists', 'penalty_minutes']
            if category not in valid_categories:
                raise ValidationError(f"Invalid category. Must be one of: {valid_categories}", "category")
            
            # Get all players with statistics
            all_players = self.repository.get_all()
            player_stats = []
            
            for player in all_players:
                stats = self.get_player_statistics(player.id)
                if stats[category] > 0:  # Only include players with non-zero stats
                    player_stats.append({
                        'player': player,
                        'value': stats[category],
                        'statistics': stats
                    })
            
            # Sort by category value
            player_stats.sort(key=lambda x: x['value'], reverse=True)
            
            # Return top N
            return player_stats[:limit]
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error getting all-time leaders: {e}")
            raise ServiceError(f"Failed to get all-time leaders: {e}")
    
    def get_player_teams(self, player_id: int) -> List[Dict[str, Any]]:
        """
        Get all teams a player has played for
        
        Args:
            player_id: Player ID
            
        Returns:
            List of teams with years played
        """
        try:
            # This would need implementation tracking team changes
            # For now, return current team
            player = self.get_by_id(player_id)
            
            return [{
                'team_code': player.team_code,
                'current': True,
                'years': self.repository.get_years_played(player_id)
            }]
            
        except Exception as e:
            logger.error(f"Error getting player teams: {e}")
            raise ServiceError(f"Failed to get player teams: {e}")
    
    @cached(ttl=600, key_prefix="player:team_statistics")
    def get_team_statistics(self, team_code: str) -> Dict[str, Any]:
        """
        Get aggregated statistics for a team
        
        Args:
            team_code: Team code
            
        Returns:
            Dictionary with team statistics
        """
        if not team_code or len(team_code) != 3:
            raise ValidationError("Invalid team code", "team_code")
        
        players = self.repository.get_players_by_team(team_code.upper())
        
        # Calculate team totals
        total_goals = 0
        total_assists = 0
        total_pim = 0
        total_pp_goals = 0
        total_sh_goals = 0
        
        for player in players:
            stats = self.get_player_statistics(player.id)
            total_goals += stats['goals']
            total_assists += stats['assists']
            total_pim += stats['penalty_minutes']
            total_pp_goals += stats['powerplay_goals']
            total_sh_goals += stats['shorthanded_goals']
        
        return {
            'team_code': team_code.upper(),
            'total_players': len(players),
            'total_goals': total_goals,
            'total_assists': total_assists,
            'total_points': total_goals + total_assists,
            'total_penalty_minutes': total_pim,
            'powerplay_goals': total_pp_goals,
            'shorthanded_goals': total_sh_goals,
            'players': players
        }
    
    def find_by_name_and_team(self, first_name: str, last_name: str, team_code: str) -> Optional[Player]:
        """
        Find a player by name and team
        
        Args:
            first_name: Player's first name
            last_name: Player's last name
            team_code: Team code
            
        Returns:
            Player if found, None otherwise
        """
        try:
            return self.repository.get_player_by_name(first_name, last_name, team_code)
        except Exception as e:
            logger.error(f"Error finding player: {e}")
            return None
    
    def get_players_by_team(self, team_code: str) -> List[Player]:
        """
        Get all players for a specific team, ordered by last name, first name
        
        Args:
            team_code: Team code
            
        Returns:
            List of players
        """
        try:
            return self.repository.get_players_by_team(team_code)
        except Exception as e:
            logger.error(f"Error getting players by team: {e}")
            raise ServiceError(f"Failed to get players by team: {e}")
    
    def get_player_count_by_team(self) -> List[Tuple[str, int]]:
        """
        Get player count grouped by team
        
        Returns:
            List of tuples (team_code, count)
        """
        try:
            return self.repository.get_player_count_by_team()
        except Exception as e:
            logger.error(f"Error getting player count by team: {e}")
            raise ServiceError(f"Failed to get player count by team: {e}")
    
    def get_player_stats_for_year(self, year_id: int, team_filter: Optional[str] = None, 
                                 game_ids: Optional[List[int]] = None) -> Dict[int, Dict[str, Any]]:
        """
        Get player statistics for a specific year with optional filtering
        
        Args:
            year_id: Championship year ID
            team_filter: Optional team code filter
            game_ids: Optional list of specific game IDs to include
            
        Returns:
            Dictionary with player_id as key and stats dict as value
            Format: {player_id: {'g': goals, 'a': assists, 'p': points, 'obj': player_object}}
            
        Raises:
            ServiceError: If database query fails
        """
        try:
            from models import Goal, Game
            
            # Build base query for goals
            goals_query = Goal.query.join(Game).filter(Game.year_id == year_id)
            
            # Apply game filter if provided
            if game_ids:
                goals_query = goals_query.filter(Goal.game_id.in_(game_ids))
            
            goals = goals_query.all()
            
            # Collect all player IDs and initialize stats
            player_stats = {}
            player_objects = {}
            
            # Process goals for scoring statistics
            for goal in goals:
                # Apply team filter if specified
                if team_filter:
                    # Check if any involved player is from the filtered team
                    players_to_check = [
                        goal.scorer_id,
                        goal.assist1_id, 
                        goal.assist2_id
                    ]
                    
                    team_match = False
                    for pid in players_to_check:
                        if pid:
                            player = Player.query.get(pid)
                            if player and player.team_code == team_filter:
                                team_match = True
                                break
                    
                    if not team_match:
                        continue
                
                # Track scorer
                if goal.scorer_id:
                    if goal.scorer_id not in player_stats:
                        player_stats[goal.scorer_id] = {'g': 0, 'a': 0, 'p': 0}
                        player_objects[goal.scorer_id] = Player.query.get(goal.scorer_id)
                    player_stats[goal.scorer_id]['g'] += 1
                    player_stats[goal.scorer_id]['p'] += 1
                
                # Track assists
                for assist_id in [goal.assist1_id, goal.assist2_id]:
                    if assist_id:
                        if assist_id not in player_stats:
                            player_stats[assist_id] = {'g': 0, 'a': 0, 'p': 0}
                            player_objects[assist_id] = Player.query.get(assist_id)
                        player_stats[assist_id]['a'] += 1
                        player_stats[assist_id]['p'] += 1
            
            # Add player objects to stats
            result = {}
            for player_id, stats in player_stats.items():
                result[player_id] = {
                    'g': stats['g'],
                    'a': stats['a'], 
                    'p': stats['p'],
                    'obj': player_objects[player_id]
                }
            
            logger.info(f"Retrieved stats for {len(result)} players in year {year_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting player stats for year: {str(e)}")
            raise ServiceError(f"Failed to retrieve player stats for year: {str(e)}")
    
    def get_player_penalty_stats_for_year(self, year_id: int, team_filter: Optional[str] = None) -> Dict[int, Dict[str, Any]]:
        """
        Get player penalty statistics for a specific year
        
        Args:
            year_id: Championship year ID
            team_filter: Optional team code filter
            
        Returns:
            Dictionary with player_id as key and penalty stats dict as value
            Format: {player_id: {'pim': penalty_minutes, 'obj': player_object}}
            
        Raises:
            ServiceError: If database query fails
        """
        try:
            from models import Penalty, Game
            
            # Build base query for penalties
            penalties_query = Penalty.query.join(Game).filter(Game.year_id == year_id)
            penalties = penalties_query.all()
            
            # Collect player penalty statistics
            player_penalties = {}
            player_objects = {}
            
            for penalty in penalties:
                if penalty.player_id:
                    # Get player object
                    if penalty.player_id not in player_objects:
                        player_objects[penalty.player_id] = Player.query.get(penalty.player_id)
                    
                    player = player_objects[penalty.player_id]
                    
                    # Apply team filter if specified
                    if team_filter and player and player.team_code != team_filter:
                        continue
                    
                    # Initialize player stats
                    if penalty.player_id not in player_penalties:
                        player_penalties[penalty.player_id] = {'pim': 0}
                    
                    # Add penalty minutes
                    penalty_minutes = PIM_MAP.get(penalty.penalty_type, 0)
                    player_penalties[penalty.player_id]['pim'] += penalty_minutes
            
            # Build final result with player objects
            result = {}
            for player_id, stats in player_penalties.items():
                result[player_id] = {
                    'pim': stats['pim'],
                    'obj': player_objects[player_id]
                }
            
            logger.info(f"Retrieved penalty stats for {len(result)} players in year {year_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting player penalty stats for year: {str(e)}")
            raise ServiceError(f"Failed to retrieve player penalty stats for year: {str(e)}")
    
    def get_all_players(self, order_by: Optional[List[str]] = None) -> List[Player]:
        """
        Get all players with optional ordering
        
        Args:
            order_by: List of field names to order by (e.g., ['team_code', 'last_name'])
            
        Returns:
            List of all players ordered as specified
            
        Raises:
            ServiceError: If database query fails
        """
        try:
            query = Player.query
            
            # Apply ordering if specified
            if order_by:
                order_clauses = []
                for field in order_by:
                    if hasattr(Player, field):
                        order_clauses.append(getattr(Player, field))
                    else:
                        logger.warning(f"Invalid order field: {field}")
                
                if order_clauses:
                    query = query.order_by(*order_clauses)
            
            players = query.all()
            logger.info(f"Retrieved {len(players)} players with ordering: {order_by}")
            return players
            
        except Exception as e:
            logger.error(f"Error getting all players: {str(e)}")
            raise ServiceError(f"Failed to retrieve all players: {str(e)}")
    
    def update_player(self, player_id: int, first_name: str, last_name: str, jersey_number: Optional[int] = None) -> Player:
        """
        Update player information
        
        Args:
            player_id: Player ID
            first_name: New first name
            last_name: New last name
            jersey_number: New jersey number (optional)
            
        Returns:
            Updated player
            
        Raises:
            NotFoundError: If player not found
            ValidationError: If data is invalid
        """
        try:
            player = self.get_by_id(player_id)
            
            # Validate input
            if not first_name or not first_name.strip():
                raise ValidationError("First name cannot be empty", "first_name")
            
            if not last_name or not last_name.strip():
                raise ValidationError("Last name cannot be empty", "last_name")
            
            if jersey_number is not None:
                if jersey_number < 1 or jersey_number > 99:
                    raise ValidationError("Jersey number must be between 1 and 99", "jersey_number")
                
                # Check for duplicate jersey number on same team (excluding current player)
                existing = self.repository.get_player_by_jersey(player.team_code, jersey_number)
                if existing and existing.id != player_id:
                    raise ValidationError(
                        f"Jersey number {jersey_number} already taken on team {player.team_code}",
                        "jersey_number"
                    )
            
            # Update player
            player.first_name = first_name.strip()
            player.last_name = last_name.strip()
            player.jersey_number = jersey_number
            
            self.repository.update(player)
            
            # Invalidate cache
            self.invalidate_cache(f"player_{player_id}")
            self.invalidate_cache(f"team_players_{player.team_code}")
            
            return player
            
        except NotFoundError:
            raise
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error updating player: {e}")
            raise ServiceError(f"Failed to update player: {e}")
    
    def get_comprehensive_player_stats(self, team_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get comprehensive player statistics for all players with year ranges and detailed metrics.
        This replaces the direct database queries in routes/players/stats.py
        
        Args:
            team_filter: Optional team code filter
            
        Returns:
            List of player statistics with goals, assists, PIMs, and year ranges
        """
        try:
            # Build subqueries for goals scored
            goals_sq = db.session.query(
                Goal.scorer_id.label("player_id"),
                func.count(Goal.id).label("num_goals")
            ).filter(Goal.scorer_id.isnot(None)) \
            .group_by(Goal.scorer_id).subquery()

            # Build subqueries for first assists
            assists1_sq = db.session.query(
                Goal.assist1_id.label("player_id"),
                func.count(Goal.id).label("num_assists1")
            ).filter(Goal.assist1_id.isnot(None)) \
            .group_by(Goal.assist1_id).subquery()

            # Build subqueries for second assists
            assists2_sq = db.session.query(
                Goal.assist2_id.label("player_id"),
                func.count(Goal.id).label("num_assists2")
            ).filter(Goal.assist2_id.isnot(None)) \
            .group_by(Goal.assist2_id).subquery()

            # Build penalty minutes case statement
            pim_when_clauses = []
            for penalty_type_key, minutes in PIM_MAP.items():
                pim_when_clauses.append((Penalty.penalty_type == penalty_type_key, minutes))
            
            pim_case_statement = case(
                *pim_when_clauses,
                else_=0
            )

            # Build subqueries for penalty minutes
            pims_sq = db.session.query(
                Penalty.player_id.label("player_id"),
                func.sum(pim_case_statement).label("total_pims")
            ).filter(Penalty.player_id.isnot(None)) \
            .group_by(Penalty.player_id).subquery()

            # Build subqueries for goal year ranges
            goal_years_sq = db.session.query(
                Goal.scorer_id.label("player_id"),
                func.min(ChampionshipYear.year).label("first_goal_year"),
                func.max(ChampionshipYear.year).label("last_goal_year")
            ).join(Game, Goal.game_id == Game.id) \
            .join(ChampionshipYear, Game.year_id == ChampionshipYear.id) \
            .filter(Goal.scorer_id.isnot(None)) \
            .group_by(Goal.scorer_id).subquery()

            # Build subqueries for assist year ranges
            assist_years_sq = db.session.query(
                Player.id.label("player_id"),
                func.min(ChampionshipYear.year).label("first_assist_year"),
                func.max(ChampionshipYear.year).label("last_assist_year")
            ).select_from(Goal) \
            .join(Game, Goal.game_id == Game.id) \
            .join(ChampionshipYear, Game.year_id == ChampionshipYear.id) \
            .join(Player, or_(Goal.assist1_id == Player.id, Goal.assist2_id == Player.id)) \
            .group_by(Player.id).subquery()

            # Build subqueries for penalty year ranges
            pim_years_sq = db.session.query(
                Penalty.player_id.label("player_id"),
                func.min(ChampionshipYear.year).label("first_pim_year"),
                func.max(ChampionshipYear.year).label("last_pim_year")
            ).join(Game, Penalty.game_id == Game.id) \
            .join(ChampionshipYear, Game.year_id == ChampionshipYear.id) \
            .filter(Penalty.player_id.isnot(None)) \
            .group_by(Penalty.player_id).subquery()

            # Build main query with all joins
            player_stats_query = db.session.query(
                Player.id,
                Player.first_name,
                Player.last_name,
                Player.team_code,
                func.coalesce(goals_sq.c.num_goals, 0).label("goals"),
                func.coalesce(assists1_sq.c.num_assists1, 0).label("assists1_count"),
                func.coalesce(assists2_sq.c.num_assists2, 0).label("assists2_count"),
                func.coalesce(pims_sq.c.total_pims, 0).label("pims"),
                goal_years_sq.c.first_goal_year,
                goal_years_sq.c.last_goal_year,
                assist_years_sq.c.first_assist_year,
                assist_years_sq.c.last_assist_year,
                pim_years_sq.c.first_pim_year,
                pim_years_sq.c.last_pim_year
            ).select_from(Player) \
            .outerjoin(goals_sq, Player.id == goals_sq.c.player_id) \
            .outerjoin(assists1_sq, Player.id == assists1_sq.c.player_id) \
            .outerjoin(assists2_sq, Player.id == assists2_sq.c.player_id) \
            .outerjoin(pims_sq, Player.id == pims_sq.c.player_id) \
            .outerjoin(goal_years_sq, Player.id == goal_years_sq.c.player_id) \
            .outerjoin(assist_years_sq, Player.id == assist_years_sq.c.player_id) \
            .outerjoin(pim_years_sq, Player.id == pim_years_sq.c.player_id)

            # Apply team filter if provided
            if team_filter:
                player_stats_query = player_stats_query.filter(Player.team_code == team_filter)

            # Check for unmapped penalty types
            distinct_db_penalty_types = db.session.query(Penalty.penalty_type).distinct().all()
            unmapped_types = [pt[0] for pt in distinct_db_penalty_types if pt[0] not in PIM_MAP and pt[0] is not None]
            if unmapped_types:
                current_app.logger.warning(f"PlayerStats: Unmapped penalty types found in database, defaulted to 0 PIMs: {unmapped_types}")

            # Process results and calculate derived values
            results = []
            for row in player_stats_query.all():
                assists = row.assists1_count + row.assists2_count
                scorer_points = row.goals + assists
                
                # Format year ranges
                goal_year_range = self._format_year_range(row.first_goal_year, row.last_goal_year)
                assist_year_range = self._format_year_range(row.first_assist_year, row.last_assist_year)
                pim_year_range = self._format_year_range(row.first_pim_year, row.last_pim_year)
                
                # Calculate overall year range
                overall_year_range = self._calculate_overall_year_range(
                    row.first_goal_year, row.last_goal_year,
                    row.first_assist_year, row.last_assist_year,
                    row.first_pim_year, row.last_pim_year
                )
                
                results.append({
                    'first_name': row.first_name,
                    'last_name': row.last_name,
                    'team_code': row.team_code,
                    'goals': row.goals,
                    'assists': assists,
                    'scorer_points': scorer_points,
                    'pims': row.pims,
                    'goal_year_range': goal_year_range,
                    'assist_year_range': assist_year_range,
                    'pim_year_range': pim_year_range,
                    'overall_year_range': overall_year_range
                })

            # Sort by points (goals + assists) descending, then by goals descending
            results.sort(key=lambda x: (x['scorer_points'], x['goals']), reverse=True)
            
            logger.info(f"Retrieved comprehensive player stats for {len(results)} players")
            return results
            
        except Exception as e:
            logger.error(f"Error getting comprehensive player stats: {str(e)}")
            raise ServiceError(f"Failed to get comprehensive player stats: {str(e)}")
    
    def _format_year_range(self, first_year: Optional[int], last_year: Optional[int]) -> Optional[str]:
        """Format year range for display"""
        if first_year and last_year:
            if first_year == last_year:
                return f"({first_year})"
            else:
                return f"({first_year}-{last_year})"
        return None
    
    def _calculate_overall_year_range(self, first_goal_year: Optional[int], last_goal_year: Optional[int],
                                    first_assist_year: Optional[int], last_assist_year: Optional[int],
                                    first_pim_year: Optional[int], last_pim_year: Optional[int]) -> Optional[str]:
        """Calculate overall year range from all stat categories"""
        all_first_years = [y for y in [first_goal_year, first_assist_year, first_pim_year] if y is not None]
        all_last_years = [y for y in [last_goal_year, last_assist_year, last_pim_year] if y is not None]
        
        overall_first_year = min(all_first_years) if all_first_years else None
        overall_last_year = max(all_last_years) if all_last_years else None
        
        return self._format_year_range(overall_first_year, overall_last_year)