"""
Player Service for IIHF World Championship Statistics
Handles all business logic related to players, player statistics, and performance tracking
"""

from typing import Dict, List, Optional, Tuple, Any
from models import Player, Goal, Penalty, Game, ChampionshipYear, db
from services.base import BaseService
from services.exceptions import ServiceError, ValidationError, NotFoundError, DuplicateError, BusinessRuleError
from app.repositories.core.player_repository import PlayerRepository
from sqlalchemy import func, case, or_
from constants import PIM_MAP
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class PlayerService(BaseService[Player]):
    """
    Service for player-related business logic
    Manages players, player statistics, goals, assists, and penalties
    """
    
    def __init__(self):
        super().__init__(Player)
        self.repository = PlayerRepository()  # Repository für Datenbankzugriff
    
    def create_player(self, team_code: str, first_name: str, last_name: str, 
                     jersey_number: Optional[int] = None) -> Player:
        """
        Create a new player with validation
        
        Args:
            team_code: The team code (3 letters)
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
        # Validate team code
        if not team_code or len(team_code) != 3:
            raise ValidationError("Team code must be exactly 3 characters", "team_code")
        
        # Validate names
        if not first_name or not first_name.strip():
            raise ValidationError("First name cannot be empty", "first_name")
        if not last_name or not last_name.strip():
            raise ValidationError("Last name cannot be empty", "last_name")
        
        # Validate jersey number
        if jersey_number is not None:
            if jersey_number < 0 or jersey_number > 99:
                raise ValidationError("Jersey number must be between 0 and 99", "jersey_number")
        
        try:
            # Check for duplicate
            existing = self.repository.find_by_name_and_team(
                first_name.strip(), 
                last_name.strip(), 
                team_code.upper()
            )
            if existing:
                raise DuplicateError(
                    "Player", 
                    "name", 
                    f"{first_name} {last_name} ({team_code})"
                )
            
            # Create player
            player = Player(
                team_code=team_code.upper(),
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                jersey_number=jersey_number
            )
            
            self.repository.save(player)
            self.commit()
            
            logger.info(f"Created player: {player.first_name} {player.last_name} #{jersey_number} ({team_code})")
            return player
            
        except (ValidationError, DuplicateError):
            self.rollback()
            raise
        except Exception as e:
            self.rollback()
            logger.error(f"Error creating player: {str(e)}")
            raise ServiceError(f"Failed to create player: {str(e)}")
    
    def update_player(self, player_id: int, first_name: Optional[str] = None,
                     last_name: Optional[str] = None, jersey_number: Optional[int] = None) -> Player:
        """
        Update player information
        
        Args:
            player_id: The player ID
            first_name: New first name (optional)
            last_name: New last name (optional)
            jersey_number: New jersey number (optional)
            
        Returns:
            Updated player object
            
        Raises:
            NotFoundError: If player not found
            ValidationError: If input data is invalid
            ServiceError: If update fails
        """
        player = self.repository.find_by_id(player_id)
        if not player:
            raise NotFoundError("Player", player_id)
        
        try:
            # Validate and update fields
            if first_name is not None:
                if not first_name.strip():
                    raise ValidationError("First name cannot be empty", "first_name")
                player.first_name = first_name.strip()
            
            if last_name is not None:
                if not last_name.strip():
                    raise ValidationError("Last name cannot be empty", "last_name")
                player.last_name = last_name.strip()
            
            if jersey_number is not None:
                if jersey_number < 0 or jersey_number > 99:
                    raise ValidationError("Jersey number must be between 0 and 99", "jersey_number")
                player.jersey_number = jersey_number
            
            self.commit()
            logger.info(f"Updated player {player_id}")
            return player
            
        except ValidationError:
            self.rollback()
            raise
        except Exception as e:
            self.rollback()
            logger.error(f"Error updating player {player_id}: {str(e)}")
            raise ServiceError(f"Failed to update player: {str(e)}")
    
    def get_player_statistics(self, player_id: int, year_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get comprehensive player statistics
        
        Args:
            player_id: The player ID
            year_id: Optional championship year ID (None for all-time stats)
            
        Returns:
            Dictionary with player data and statistics
            
        Raises:
            NotFoundError: If player not found
        """
        player = self.repository.find_by_id(player_id)
        if not player:
            raise NotFoundError("Player", player_id)
        
        # Get goals scored
        goals = self.repository.get_player_goals(player_id, year_id)
        
        # Get assists
        assists = self.repository.get_player_assists(player_id, year_id)
        
        # Get penalties
        penalties = self.repository.get_player_penalties(player_id, year_id)
        
        # Calculate statistics
        stats = self._calculate_player_stats(goals, assists, penalties)
        
        # Get games played
        games_played = self.repository.get_games_played(player_id, year_id)
        
        return {
            'player': player,
            'statistics': {
                'games_played': len(games_played),
                'goals': stats['goals'],
                'assists': stats['assists'],
                'points': stats['points'],
                'power_play_goals': stats['pp_goals'],
                'penalty_minutes': stats['pim'],
                'plus_minus': stats.get('plus_minus', 0)  # If tracked
            },
            'goals_detail': goals,
            'assists_detail': assists,
            'penalties_detail': penalties,
            'year_id': year_id
        }
    
    def _calculate_player_stats(self, goals: List[Goal], assists: List[Goal], 
                               penalties: List[Penalty]) -> Dict[str, int]:
        """Calculate player statistics from raw data"""
        from constants import PIM_MAP
        
        # Count goals by type
        total_goals = len(goals)
        pp_goals = sum(1 for g in goals if g.goal_type == 'PP')
        sh_goals = sum(1 for g in goals if g.goal_type == 'SH')
        en_goals = sum(1 for g in goals if g.is_empty_net)
        
        # Count assists
        total_assists = len(assists)
        
        # Calculate penalty minutes
        total_pim = sum(PIM_MAP.get(p.penalty_type, 0) for p in penalties)
        
        return {
            'goals': total_goals,
            'pp_goals': pp_goals,
            'sh_goals': sh_goals,
            'en_goals': en_goals,
            'assists': total_assists,
            'points': total_goals + total_assists,
            'pim': total_pim,
            'penalties': len(penalties)
        }
    
    def get_team_players(self, team_code: str, year_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all players for a team with their statistics
        
        Args:
            team_code: The team code
            year_id: Optional championship year ID
            
        Returns:
            List of players with statistics
        """
        players = self.repository.find_by_team(team_code)
        
        players_with_stats = []
        for player in players:
            try:
                stats = self.get_player_statistics(player.id, year_id)
                players_with_stats.append(stats)
            except Exception as e:
                logger.error(f"Error getting stats for player {player.id}: {str(e)}")
                players_with_stats.append({
                    'player': player,
                    'error': str(e)
                })
        
        # Sort by points (goals + assists) descending
        players_with_stats.sort(
            key=lambda x: x.get('statistics', {}).get('points', 0), 
            reverse=True
        )
        
        return players_with_stats
    
    def get_top_scorers(self, year_id: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top scorers (by points)
        
        Args:
            year_id: Optional championship year ID (None for all-time)
            limit: Number of players to return
            
        Returns:
            List of top scorers with statistics
        """
        # Get all players with their scoring statistics
        scorers = self.repository.get_top_scorers(year_id, limit)
        
        result = []
        for scorer_data in scorers:
            player = self.repository.find_by_id(scorer_data['player_id'])
            if player:
                result.append({
                    'player': player,
                    'statistics': {
                        'goals': scorer_data['goals'],
                        'assists': scorer_data['assists'],
                        'points': scorer_data['points'],
                        'games_played': scorer_data.get('games_played', 0)
                    }
                })
        
        return result
    
    def get_penalty_leaders(self, year_id: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get players with most penalty minutes
        
        Args:
            year_id: Optional championship year ID
            limit: Number of players to return
            
        Returns:
            List of penalty leaders
        """
        penalty_leaders = self.repository.get_penalty_leaders(year_id, limit)
        
        result = []
        for leader_data in penalty_leaders:
            player = self.repository.find_by_id(leader_data['player_id'])
            if player:
                result.append({
                    'player': player,
                    'statistics': {
                        'penalty_minutes': leader_data['total_pim'],
                        'penalties': leader_data['penalty_count'],
                        'games_played': leader_data.get('games_played', 0)
                    }
                })
        
        return result
    
    def transfer_player(self, player_id: int, new_team_code: str) -> Player:
        """
        Transfer player to a new team
        
        Args:
            player_id: The player ID
            new_team_code: The new team code
            
        Returns:
            Updated player object
            
        Raises:
            NotFoundError: If player not found
            ValidationError: If team code is invalid
            BusinessRuleError: If transfer violates business rules
        """
        player = self.repository.find_by_id(player_id)
        if not player:
            raise NotFoundError("Player", player_id)
        
        # Validate team code
        if not new_team_code or len(new_team_code) != 3:
            raise ValidationError("Team code must be exactly 3 characters", "team_code")
        
        if player.team_code == new_team_code.upper():
            raise BusinessRuleError(
                "Player is already on this team",
                "same_team_transfer"
            )
        
        try:
            old_team = player.team_code
            player.team_code = new_team_code.upper()
            
            self.commit()
            logger.info(f"Transferred player {player_id} from {old_team} to {new_team_code}")
            return player
            
        except Exception as e:
            self.rollback()
            logger.error(f"Error transferring player {player_id}: {str(e)}")
            raise ServiceError(f"Failed to transfer player: {str(e)}")
    
    def merge_duplicate_players(self, primary_id: int, duplicate_id: int) -> Player:
        """
        Merge duplicate player records
        
        Args:
            primary_id: The primary player ID to keep
            duplicate_id: The duplicate player ID to merge and delete
            
        Returns:
            The merged player record
            
        Raises:
            NotFoundError: If either player not found
            BusinessRuleError: If players are not duplicates
        """
        primary = self.repository.find_by_id(primary_id)
        duplicate = self.repository.find_by_id(duplicate_id)
        
        if not primary:
            raise NotFoundError("Primary player", primary_id)
        if not duplicate:
            raise NotFoundError("Duplicate player", duplicate_id)
        
        # Validate they are actually duplicates (same name, possibly different teams)
        if (primary.first_name.lower() != duplicate.first_name.lower() or
            primary.last_name.lower() != duplicate.last_name.lower()):
            raise BusinessRuleError(
                "Players do not have matching names",
                "not_duplicates"
            )
        
        try:
            # Merge statistics by updating foreign keys
            self.repository.merge_player_records(primary_id, duplicate_id)
            
            # Delete duplicate
            self.repository.delete(duplicate)
            
            self.commit()
            logger.info(f"Merged player {duplicate_id} into {primary_id}")
            return primary
            
        except Exception as e:
            self.rollback()
            logger.error(f"Error merging players: {str(e)}")
            raise ServiceError(f"Failed to merge players: {str(e)}")
    
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