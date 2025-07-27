"""
Team Service with Repository Pattern
Handles all business logic related to teams, players, and team statistics
"""

from typing import Dict, List, Optional, Any, Set
from models import TeamStats, TeamOverallStats, AllTimeTeamStats, ChampionshipYear, db, Game, Goal, Penalty, ShotsOnGoal
from app.services.base import BaseService
from app.services.utils.cache_manager import CacheableService, cached
from app.repositories.core import TeamRepository
from app.exceptions import ServiceError, ValidationError, NotFoundError, BusinessRuleError
from constants import TEAM_ISO_CODES, PRELIM_ROUNDS, PLAYOFF_ROUNDS, PIM_MAP, POWERPLAY_PENALTY_TYPES
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)


class TeamService(CacheableService, BaseService[None]):
    """
    Service for team-related business logic using repository pattern
    Manages teams, rosters, standings, and team statistics
    Note: Teams don't have a dedicated model, they are derived from game data
    """
    
    def __init__(self, repository: Optional[TeamRepository] = None):
        """
        Initialize service with repository and cache
        
        Args:
            repository: TeamRepository instance (optional, will create if not provided)
        """
        if repository is None:
            repository = TeamRepository()
        # Initialisiere beide Elternklassen
        # Use proper MRO initialization
        super().__init__(repository)
        self.repository: TeamRepository = repository  # Type hint for IDE support
    
    def get_all_teams(self, year_id: Optional[int] = None, 
                     include_placeholders: bool = False) -> List[Dict[str, Any]]:
        """
        Get all teams with basic information
        
        Args:
            year_id: Optional year filter
            include_placeholders: Whether to include placeholder teams
            
        Returns:
            List of team dictionaries with code and ISO
        """
        try:
            team_codes = self.repository.get_all_teams(year_id)
            
            teams = []
            for code in team_codes:
                # Skip placeholders if not requested
                if not include_placeholders and self._is_placeholder_team(code):
                    continue
                
                team = {
                    'code': code,
                    'iso_code': TEAM_ISO_CODES.get(code, ""),
                    'name': self._get_team_full_name(code)
                }
                teams.append(team)
            
            logger.info(f"Retrieved {len(teams)} teams")
            return sorted(teams, key=lambda x: x['code'])
            
        except Exception as e:
            logger.error(f"Error getting teams: {str(e)}")
            raise ServiceError(f"Failed to retrieve teams: {str(e)}")
    
    def get_teams_by_year(self, year_id: int) -> List[Dict[str, Any]]:
        """
        Get all teams that participated in a specific year
        
        Args:
            year_id: Championship year ID
            
        Returns:
            List of team dictionaries
            
        Raises:
            NotFoundError: If year not found
        """
        # Validate year exists
        year = ChampionshipYear.query.get(year_id)
        if not year:
            raise NotFoundError("Championship year", year_id)
        
        try:
            team_codes = self.repository.get_teams_by_year(year_id)
            
            teams = []
            for code in team_codes:
                team = {
                    'code': code,
                    'iso_code': TEAM_ISO_CODES.get(code, ""),
                    'name': self._get_team_full_name(code),
                    'year': year.year
                }
                teams.append(team)
            
            logger.info(f"Retrieved {len(teams)} teams for year {year.year}")
            return sorted(teams, key=lambda x: x['code'])
            
        except Exception as e:
            logger.error(f"Error getting teams for year {year_id}: {str(e)}")
            raise ServiceError(f"Failed to retrieve teams: {str(e)}")
    
    @cached(ttl=300, key_prefix="team:stats")
    def get_team_stats(self, team_code: str, year_id: int,
                      round_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a team
        
        Args:
            team_code: Team code (e.g., 'CAN')
            year_id: Championship year ID
            round_filter: Optional round filter
            
        Returns:
            Dictionary with team statistics
            
        Raises:
            NotFoundError: If team or year not found
            ValidationError: If team code is invalid
        """
        # Validate inputs
        if not team_code or len(team_code) != 3:
            raise ValidationError("Invalid team code format", "team_code")
        
        year = ChampionshipYear.query.get(year_id)
        if not year:
            raise NotFoundError("Championship year", year_id)
        
        # Check if team participated in this year
        teams_in_year = self.repository.get_teams_by_year(year_id)
        if team_code not in teams_in_year:
            raise NotFoundError(f"Team {team_code} in year {year.year}", team_code)
        
        try:
            stats = self.repository.get_team_stats(team_code, year_id, round_filter)
            
            # Add additional information
            stats['team_name'] = self._get_team_full_name(team_code)
            stats['year'] = year.year
            stats['round_filter'] = round_filter
            
            logger.info(f"Retrieved stats for team {team_code} in year {year.year}")
            return stats
            
        except Exception as e:
            logger.error(f"Error getting team stats: {str(e)}")
            raise ServiceError(f"Failed to retrieve team statistics: {str(e)}")
    
    def get_team_overall_stats(self, team_code: str, year_id: int) -> TeamOverallStats:
        """
        Get overall statistics for a team in TeamOverallStats format
        
        Args:
            team_code: Team code
            year_id: Championship year ID
            
        Returns:
            TeamOverallStats object
        """
        stats = self.get_team_stats(team_code, year_id)
        
        overall = TeamOverallStats(
            team_name=team_code,
            team_iso_code=stats['team_iso'],
            gp=stats['games_played'],
            gf=stats['goals_for'],
            ga=stats['goals_against'],
            eng=stats['empty_net_goals'],
            sog=stats['shots_for'],
            soga=stats['shots_against'],
            so=stats['shutouts'],
            ppgf=stats['powerplay_goals'],
            ppga=0,  # Would need opponent PP goals data
            ppf=stats['powerplay_opportunities'],
            ppa=0,  # Would need times shorthanded data
            pim=stats['penalty_minutes']
        )
        
        return overall
    
    def get_team_standings(self, year_id: int, group: Optional[str] = None) -> List[TeamStats]:
        """
        Get team standings for preliminary round
        
        Args:
            year_id: Championship year ID
            group: Optional group filter ('A' or 'B')
            
        Returns:
            List of TeamStats objects sorted by ranking
            
        Raises:
            NotFoundError: If year not found
            ValidationError: If group is invalid
        """
        # Validate year
        year = ChampionshipYear.query.get(year_id)
        if not year:
            raise NotFoundError("Championship year", year_id)
        
        # Validate group if provided
        if group and group not in ['A', 'B']:
            raise ValidationError("Group must be 'A' or 'B'", "group")
        
        try:
            standings = self.repository.get_team_standings(year_id, group)
            
            logger.info(f"Retrieved standings for year {year.year}" + 
                       (f" group {group}" if group else ""))
            return standings
            
        except Exception as e:
            logger.error(f"Error getting standings: {str(e)}")
            raise ServiceError(f"Failed to retrieve standings: {str(e)}")
    
    def get_team_roster(self, team_code: str, year_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get team roster (players)
        
        Args:
            team_code: Team code
            year_id: Optional year filter
            
        Returns:
            List of player dictionaries
            
        Raises:
            ValidationError: If team code is invalid
        """
        if not team_code or len(team_code) != 3:
            raise ValidationError("Invalid team code format", "team_code")
        
        try:
            players = self.repository.get_team_players(team_code, year_id)
            
            roster = []
            for player in players:
                roster.append({
                    'id': player.id,
                    'first_name': player.first_name,
                    'last_name': player.last_name,
                    'jersey_number': player.jersey_number,
                    'team_code': player.team_code,
                    'full_name': f"{player.first_name} {player.last_name}"
                })
            
            # Sort by jersey number
            roster.sort(key=lambda x: x['jersey_number'] or 999)
            
            logger.info(f"Retrieved {len(roster)} players for team {team_code}")
            return roster
            
        except Exception as e:
            logger.error(f"Error getting team roster: {str(e)}")
            raise ServiceError(f"Failed to retrieve roster: {str(e)}")
    
    @cached(ttl=900, key_prefix="team:all_time_stats")
    def get_all_time_stats(self, team_code: str) -> AllTimeTeamStats:
        """
        Get all-time statistics for a team
        
        Args:
            team_code: Team code
            
        Returns:
            AllTimeTeamStats object
            
        Raises:
            ValidationError: If team code is invalid
        """
        if not team_code or len(team_code) != 3:
            raise ValidationError("Invalid team code format", "team_code")
        
        try:
            stats = self.repository.get_all_time_stats(team_code)
            
            logger.info(f"Retrieved all-time stats for team {team_code}")
            return stats
            
        except Exception as e:
            logger.error(f"Error getting all-time stats: {str(e)}")
            raise ServiceError(f"Failed to retrieve all-time statistics: {str(e)}")
    
    @cached(ttl=600, key_prefix="team:head_to_head")
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
            
        Raises:
            ValidationError: If team codes are invalid or same
        """
        # Validate inputs
        if not team1_code or len(team1_code) != 3:
            raise ValidationError("Invalid team 1 code format", "team1_code")
        if not team2_code or len(team2_code) != 3:
            raise ValidationError("Invalid team 2 code format", "team2_code")
        if team1_code == team2_code:
            raise ValidationError("Teams cannot be the same", "team_codes")
        
        try:
            record = self.repository.get_head_to_head_record(team1_code, team2_code, year_id)
            
            # Add team names
            record['team1_name'] = self._get_team_full_name(team1_code)
            record['team2_name'] = self._get_team_full_name(team2_code)
            
            logger.info(f"Retrieved head-to-head record: {team1_code} vs {team2_code}")
            return record
            
        except Exception as e:
            logger.error(f"Error getting head-to-head record: {str(e)}")
            raise ServiceError(f"Failed to retrieve head-to-head record: {str(e)}")
    
    def get_team_performance_by_round(self, team_code: str, year_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Get team performance broken down by tournament round
        
        Args:
            team_code: Team code
            year_id: Championship year ID
            
        Returns:
            Dictionary mapping round names to performance stats
            
        Raises:
            NotFoundError: If team didn't participate in year
        """
        # Validate team participated
        teams_in_year = self.repository.get_teams_by_year(year_id)
        if team_code not in teams_in_year:
            year = ChampionshipYear.query.get(year_id)
            year_str = year.year if year else year_id
            raise NotFoundError(f"Team {team_code} in year {year_str}", team_code)
        
        try:
            performance = self.repository.get_team_performance_by_round(team_code, year_id)
            
            # Add round type classification
            for round_name, stats in performance.items():
                stats['round_type'] = 'preliminary' if round_name in PRELIM_ROUNDS else 'playoff'
                stats['win_percentage'] = (
                    stats['wins'] / stats['games'] * 100 if stats['games'] > 0 else 0
                )
            
            logger.info(f"Retrieved round performance for team {team_code} in year {year_id}")
            return performance
            
        except Exception as e:
            logger.error(f"Error getting round performance: {str(e)}")
            raise ServiceError(f"Failed to retrieve round performance: {str(e)}")
    
    @cached(ttl=1200, key_prefix="team:achievements")
    def get_team_achievements(self, team_code: str) -> Dict[str, Any]:
        """
        Get team achievements (medals, tournament wins, etc.)
        
        Args:
            team_code: Team code
            
        Returns:
            Dictionary with achievement statistics
        """
        try:
            all_time_stats = self.get_all_time_stats(team_code)
            
            achievements = {
                'team_code': team_code,
                'team_name': self._get_team_full_name(team_code),
                'total_participations': all_time_stats.num_years_participated,
                'years_participated': sorted(all_time_stats.years_participated),
                'total_games': all_time_stats.gp,
                'total_wins': all_time_stats.w + all_time_stats.otw + all_time_stats.sow,
                'total_losses': all_time_stats.l + all_time_stats.otl + all_time_stats.sol,
                'all_time_goal_differential': all_time_stats.gd,
                'medals': self._calculate_medals(team_code)
            }
            
            logger.info(f"Retrieved achievements for team {team_code}")
            return achievements
            
        except Exception as e:
            logger.error(f"Error getting team achievements: {str(e)}")
            raise ServiceError(f"Failed to retrieve achievements: {str(e)}")
    
    def _calculate_medals(self, team_code: str) -> Dict[str, int]:
        """
        Calculate medals won by a team
        This would need to analyze final standings/games
        """
        # TODO: Implement medal calculation based on final games
        # For now, return placeholder
        return {
            'gold': 0,
            'silver': 0,
            'bronze': 0
        }
    
    def _get_team_full_name(self, team_code: str) -> str:
        """
        Get full team name from code
        """
        # TODO: Add proper team name mapping
        team_names = {
            'CAN': 'Canada',
            'USA': 'United States',
            'RUS': 'Russia',
            'FIN': 'Finland',
            'SWE': 'Sweden',
            'CZE': 'Czech Republic',
            'SVK': 'Slovakia',
            'SUI': 'Switzerland',
            'GER': 'Germany',
            'LAT': 'Latvia',
            'NOR': 'Norway',
            'DEN': 'Denmark',
            'FRA': 'France',
            'AUT': 'Austria',
            'ITA': 'Italy',
            'KAZ': 'Kazakhstan',
            'BLR': 'Belarus',
            'SLO': 'Slovenia',
            'GBR': 'Great Britain',
            'HUN': 'Hungary',
            'POL': 'Poland',
            'KOR': 'South Korea',
            'JAP': 'Japan',
            'UKR': 'Ukraine',
            'ROM': 'Romania',
            'EST': 'Estonia',
            'CHN': 'China'
        }
        return team_names.get(team_code, team_code)
    
    def _is_placeholder_team(self, team_code: str) -> bool:
        """Check if team code is a placeholder"""
        if not team_code:
            return True
        placeholders = ['A', 'B', 'W', 'L', 'Q', 'S']
        return (team_code[0] in placeholders and 
                len(team_code) > 1 and 
                team_code[1:].isdigit())
    
    def get_team_games(self, team_code: str, year_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all games for a team
        
        Args:
            team_code: Team code
            year_id: Optional year filter
            
        Returns:
            List of game dictionaries
        """
        if not team_code or len(team_code) != 3:
            raise ValidationError("Invalid team code format", "team_code")
        
        try:
            games = self.repository.get_team_games(team_code, year_id)
            
            game_list = []
            for game in games:
                game_dict = {
                    'id': game.id,
                    'year_id': game.year_id,
                    'game_number': game.game_number,
                    'round': game.round,
                    'group': game.group,
                    'date': game.date,
                    'team1_code': game.team1_code,
                    'team2_code': game.team2_code,
                    'team1_score': game.team1_score,
                    'team2_score': game.team2_score,
                    'result_type': game.result_type,
                    'venue': game.venue,
                    'is_home': game.team1_code == team_code,
                    'opponent': game.team2_code if game.team1_code == team_code else game.team1_code
                }
                
                # Add result from team perspective
                if game.team1_score is not None and game.team2_score is not None:
                    if game.team1_code == team_code:
                        game_dict['result'] = 'W' if game.team1_score > game.team2_score else 'L'
                        game_dict['goals_for'] = game.team1_score
                        game_dict['goals_against'] = game.team2_score
                    else:
                        game_dict['result'] = 'W' if game.team2_score > game.team1_score else 'L'
                        game_dict['goals_for'] = game.team2_score
                        game_dict['goals_against'] = game.team1_score
                
                game_list.append(game_dict)
            
            logger.info(f"Retrieved {len(game_list)} games for team {team_code}")
            return game_list
            
        except Exception as e:
            logger.error(f"Error getting team games: {str(e)}")
            raise ServiceError(f"Failed to retrieve team games: {str(e)}")
    
    def validate_team_exists(self, team_code: str, year_id: Optional[int] = None) -> bool:
        """
        Validate if a team exists (and optionally in a specific year)
        
        Args:
            team_code: Team code to validate
            year_id: Optional year to check participation
            
        Returns:
            True if team exists, False otherwise
        """
        try:
            teams = self.repository.get_all_teams(year_id)
            return team_code in teams
        except:
            return False
    
    def get_countries_with_players(self) -> List[Dict[str, Any]]:
        """
        Get all countries/teams that have players registered
        
        Returns:
            List of dictionaries with team_code and player_count
            Format: [{'team_code': 'CAN', 'player_count': 25}, ...]
            
        Raises:
            ServiceError: If database query fails
        """
        try:
            # Get player count by team using repository pattern
            from models import Player
            
            # Query to get player count by team_code
            player_counts = self.repository.db.session.query(
                Player.team_code,
                func.count(Player.id).label('player_count')
            ).group_by(Player.team_code).all()
            
            # Convert to expected format
            countries_stats = []
            for team_code, count in player_counts:
                # Filter out invalid team codes and placeholders
                if team_code and not self._is_placeholder_team(team_code):
                    countries_stats.append({
                        'team_code': team_code,
                        'player_count': count
                    })
            
            # Sort by team code for consistency
            countries_stats.sort(key=lambda x: x['team_code'])
            
            logger.info(f"Retrieved {len(countries_stats)} countries with players")
            return countries_stats
            
        except Exception as e:
            logger.error(f"Error getting countries with players: {str(e)}")
            raise ServiceError(f"Failed to retrieve countries with players: {str(e)}")
    
    def calculate_team_stats_for_year(self, year_id: int, team_codes: List[str],
                                     games_processed: List[Any], games_raw_map: Dict[int, Game]) -> List[TeamOverallStats]:
        """
        Calculate comprehensive team statistics for a year
        
        Args:
            year_id: Championship year ID
            team_codes: List of team codes to calculate stats for
            games_processed: List of processed games (with resolved team codes)
            games_raw_map: Map of game ID to raw game objects
            
        Returns:
            List of TeamOverallStats objects
        """
        # Hole alle notwendigen Daten auf einmal (vermeidet N+1 Queries)
        all_games_for_year = Game.query.filter_by(year_id=year_id).all()
        all_goals_for_year = Goal.query.join(Game).filter(Game.year_id == year_id).all()
        all_penalties_for_year = Penalty.query.join(Game).filter(Game.year_id == year_id).all()
        all_sog_for_year = ShotsOnGoal.query.join(Game).filter(Game.year_id == year_id).all()
        
        # SOG by game and team
        sog_by_game_team = {}
        for sog_entry in all_sog_for_year:
            game_sog = sog_by_game_team.setdefault(sog_entry.game_id, {})
            team_total_sog = game_sog.get(sog_entry.team_code, 0)
            game_sog[sog_entry.team_code] = team_total_sog + sog_entry.shots
        
        # Map für aufgelöste Spiele
        games_processed_map = {g.id: g for g in games_processed}
        
        # Hole alle Spieler für Team-Code-Auflösung
        from models import Player
        all_players_list = Player.query.all()
        
        team_stats_data_list = []
        
        for team_code_upper in team_codes:
            # Finde den tatsächlichen Team-Code (case-sensitive)
            actual_team_code_from_games = None
            for g_disp_for_code in games_processed:
                if g_disp_for_code.team1_code.upper() == team_code_upper:
                    actual_team_code_from_games = g_disp_for_code.team1_code
                    break
                if g_disp_for_code.team2_code.upper() == team_code_upper:
                    actual_team_code_from_games = g_disp_for_code.team2_code
                    break
            
            if not actual_team_code_from_games:
                found_in_players = any(p.team_code.upper() == team_code_upper for p in all_players_list)
                if found_in_players:
                    player_team_match = next((p.team_code for p in all_players_list if p.team_code.upper() == team_code_upper), team_code_upper)
                    actual_team_code_from_games = player_team_match
                else: 
                    for g_raw_for_code_obj in games_raw_map.values():
                        if g_raw_for_code_obj.team1_code.upper() == team_code_upper:
                            actual_team_code_from_games = g_raw_for_code_obj.team1_code
                            break
                        if g_raw_for_code_obj.team2_code.upper() == team_code_upper:
                            actual_team_code_from_games = g_raw_for_code_obj.team2_code
                            break
                if not actual_team_code_from_games:
                    actual_team_code_from_games = team_code_upper 

            current_team_code = actual_team_code_from_games
            stats = TeamOverallStats(team_name=current_team_code, team_iso_code=TEAM_ISO_CODES.get(current_team_code.upper()))

            # Berechne Spiel-Statistiken
            for game_id, resolved_game_this_iter in games_processed_map.items():
                raw_game_obj_this_iter = games_raw_map.get(game_id)
                if not raw_game_obj_this_iter:
                    continue

                is_current_team_t1_in_raw_game = False

                if resolved_game_this_iter.team1_code == current_team_code:
                    is_current_team_t1_in_raw_game = True
                elif resolved_game_this_iter.team2_code == current_team_code:
                    is_current_team_t1_in_raw_game = False 
                else:
                    continue

                if raw_game_obj_this_iter.team1_score is not None and raw_game_obj_this_iter.team2_score is not None: 
                    stats.gp += 1
                    current_team_score = raw_game_obj_this_iter.team1_score if is_current_team_t1_in_raw_game else raw_game_obj_this_iter.team2_score
                    opponent_score = raw_game_obj_this_iter.team2_score if is_current_team_t1_in_raw_game else raw_game_obj_this_iter.team1_score
                    stats.gf += current_team_score
                    stats.ga += opponent_score
                    if opponent_score == 0 and current_team_score > 0:
                        stats.so += 1
                
                game_sog_info = sog_by_game_team.get(raw_game_obj_this_iter.id, {})
                if resolved_game_this_iter.team1_code == current_team_code:
                    stats.sog += game_sog_info.get(current_team_code, 0)
                    stats.soga += game_sog_info.get(resolved_game_this_iter.team2_code, 0)
                elif resolved_game_this_iter.team2_code == current_team_code:
                    stats.sog += game_sog_info.get(current_team_code, 0)
                    stats.soga += game_sog_info.get(resolved_game_this_iter.team1_code, 0)
            
            # Berechne Tor-Statistiken
            for goal_event in all_goals_for_year:
                if goal_event.game_id not in games_processed_map:
                    continue
                
                resolved_game_of_goal = games_processed_map.get(goal_event.game_id)
                if not resolved_game_of_goal:
                    continue

                if goal_event.team_code == current_team_code:
                    if goal_event.is_empty_net:
                        stats.eng += 1
                    if goal_event.goal_type == 'PP':
                        stats.ppgf += 1
                elif (resolved_game_of_goal.team1_code == current_team_code and goal_event.team_code == resolved_game_of_goal.team2_code) or \
                     (resolved_game_of_goal.team2_code == current_team_code and goal_event.team_code == resolved_game_of_goal.team1_code):
                    if goal_event.goal_type == 'PP':
                        stats.ppga += 1

            # Berechne Straf-Statistiken
            for penalty_event in all_penalties_for_year:
                if penalty_event.game_id not in games_processed_map:
                    continue

                resolved_game_of_penalty = games_processed_map.get(penalty_event.game_id)
                if not resolved_game_of_penalty:
                    continue
                
                if penalty_event.team_code == current_team_code:
                    stats.pim += PIM_MAP.get(penalty_event.penalty_type, 0)
                    if penalty_event.penalty_type in POWERPLAY_PENALTY_TYPES:
                        stats.ppa += 1 
                elif (resolved_game_of_penalty.team1_code == current_team_code and penalty_event.team_code == resolved_game_of_penalty.team2_code) or \
                     (resolved_game_of_penalty.team2_code == current_team_code and penalty_event.team_code == resolved_game_of_penalty.team1_code):
                    if penalty_event.penalty_type in POWERPLAY_PENALTY_TYPES:
                        stats.ppf += 1
                        
            team_stats_data_list.append(stats)
        
        return team_stats_data_list