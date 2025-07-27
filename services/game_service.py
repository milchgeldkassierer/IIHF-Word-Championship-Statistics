"""
Game Service for IIHF World Championship Statistics
Handles all business logic related to games, scores, and game statistics
"""

from typing import Dict, List, Optional, Tuple, Any
from models import Game, ChampionshipYear, TeamStats, ShotsOnGoal, GameOverrule, Goal, Penalty, Player, db
from services.base import BaseService
from services.exceptions import ServiceError, ValidationError, NotFoundError, BusinessRuleError
from app.repositories.core.game_repository import GameRepository
from utils.playoff_resolver import PlayoffResolver
from utils import check_game_data_consistency, is_code_final, convert_time_to_seconds
from constants import PIM_MAP, POWERPLAY_PENALTY_TYPES, TEAM_ISO_CODES, GOAL_TYPE_DISPLAY_MAP, PERIOD_1_END, PERIOD_2_END, PERIOD_3_END
import logging

logger = logging.getLogger(__name__)


class GameService(BaseService[Game]):
    """
    Service for game-related business logic
    Manages games, scores, shots on goal, and game statistics
    """
    
    def __init__(self):
        super().__init__(Game)
        self.repository = GameRepository()  # Repository für Datenbankzugriff
        self._playoff_resolver_cache = {}
    
    def update_game_score(self, game_id: int, team1_score: Optional[int], 
                         team2_score: Optional[int], result_type: Optional[str]) -> Game:
        """
        Update game score with proper validation and point calculation
        
        Args:
            game_id: The game ID to update
            team1_score: Score for team 1 (can be None)
            team2_score: Score for team 2 (can be None)
            result_type: Type of result (REG, OT, SO)
            
        Returns:
            Updated game object
            
        Raises:
            NotFoundError: If game not found
            ValidationError: If scores are invalid
            ServiceError: If update fails
        """
        game = self.repository.find_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        try:
            # Validate scores
            if team1_score is not None and team1_score < 0:
                raise ValidationError("Team 1 score cannot be negative", "team1_score")
            if team2_score is not None and team2_score < 0:
                raise ValidationError("Team 2 score cannot be negative", "team2_score")
            
            # Validate result type for completed games
            if team1_score is not None and team2_score is not None:
                if result_type not in ['REG', 'OT', 'SO']:
                    raise ValidationError(f"Invalid result type: {result_type}", "result_type")
                
                # Business rule: OT/SO games must have 1-goal difference
                if result_type in ['OT', 'SO'] and abs(team1_score - team2_score) != 1:
                    raise BusinessRuleError(
                        f"{result_type} games must have exactly 1 goal difference",
                        "overtime_goal_difference"
                    )
            
            # Update scores
            game.team1_score = team1_score
            game.team2_score = team2_score
            
            # Calculate points based on result type
            if team1_score is None or team2_score is None:
                game.result_type = None
                game.team1_points = 0
                game.team2_points = 0
            else:
                game.result_type = result_type
                game.team1_points, game.team2_points = self._calculate_points(
                    team1_score, team2_score, result_type
                )
            
            self.commit()
            logger.info(f"Updated game {game_id} score: {team1_score}-{team2_score} ({result_type})")
            return game
            
        except (ValidationError, BusinessRuleError):
            self.rollback()
            raise
        except Exception as e:
            self.rollback()
            logger.error(f"Error updating game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to update game: {str(e)}")
    
    def _calculate_points(self, team1_score: int, team2_score: int, 
                         result_type: str) -> Tuple[int, int]:
        """
        Calculate points based on score and result type
        
        IIHF Point System:
        - Regular win: 3 points
        - OT/SO win: 2 points
        - OT/SO loss: 1 point
        - Regular loss: 0 points
        """
        if result_type == 'REG':
            if team1_score > team2_score:
                return 3, 0
            elif team2_score > team1_score:
                return 0, 3
            else:
                # Draw in regulation (rare in IIHF)
                return 1, 1
        elif result_type in ['OT', 'SO']:
            if team1_score > team2_score:
                return 2, 1
            else:
                return 1, 2
        else:
            raise ValidationError(f"Invalid result type: {result_type}")
    
    def add_shots_on_goal(self, game_id: int, sog_data: Dict[str, Dict[int, int]]) -> Dict:
        """
        Add or update shots on goal for a game
        
        Args:
            game_id: The game ID
            sog_data: Dictionary with team codes as keys and period shots as values
                     Example: {'CAN': {1: 10, 2: 12, 3: 8, 4: 0}, 'USA': {...}}
                     
        Returns:
            Current SOG data after update
            
        Raises:
            NotFoundError: If game not found
            ServiceError: If update fails
        """
        game = self.repository.find_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        try:
            made_changes = False
            
            # Resolve team codes first
            team1_resolved, team2_resolved = self.resolve_team_names(game.year_id, game_id)
            valid_teams = [team1_resolved, team2_resolved]
            
            for team_code, periods in sog_data.items():
                # Skip placeholder teams
                if self._is_placeholder_team(team_code):
                    continue
                
                # Validate team is playing in this game
                if team_code not in valid_teams:
                    logger.warning(f"Team {team_code} not playing in game {game_id}")
                    continue
                
                for period, shots in periods.items():
                    # Validate period
                    if period not in [1, 2, 3, 4]:
                        logger.warning(f"Invalid period {period} for SOG")
                        continue
                    
                    # Validate shots
                    if shots < 0:
                        raise ValidationError(f"Shots cannot be negative", f"period_{period}_shots")
                    
                    existing_sog = ShotsOnGoal.query.filter_by(
                        game_id=game_id, 
                        team_code=team_code, 
                        period=period
                    ).first()
                    
                    if existing_sog:
                        if existing_sog.shots != shots:
                            existing_sog.shots = shots
                            made_changes = True
                    elif shots != 0:  # Only create record for non-zero shots
                        new_sog = ShotsOnGoal(
                            game_id=game_id,
                            team_code=team_code,
                            period=period,
                            shots=shots
                        )
                        self.db.session.add(new_sog)
                        made_changes = True
            
            if made_changes:
                self.commit()
                logger.info(f"Updated SOG for game {game_id}")
            
            # Return current SOG data
            current_sog = self._get_current_sog_data(game_id)
            
            # Check data consistency
            consistency_result = check_game_data_consistency(game, current_sog)
            
            return {
                'sog_data': current_sog,
                'made_changes': made_changes,
                'consistency': consistency_result
            }
            
        except ValidationError:
            self.rollback()
            raise
        except Exception as e:
            self.rollback()
            logger.error(f"Error adding SOG for game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to add shots on goal: {str(e)}")
    
    def _is_placeholder_team(self, team_code: str) -> bool:
        """Check if team code is a placeholder"""
        if not team_code:
            return True
        placeholders = ['A', 'B', 'W', 'L', 'Q', 'S']
        return (team_code[0] in placeholders and 
                len(team_code) > 1 and 
                team_code[1:].isdigit())
    
    def _get_current_sog_data(self, game_id: int) -> Dict[str, Dict[int, int]]:
        """Get current SOG data for a game"""
        sog_entries = self.repository.get_shots_on_goal(game_id)
        sog_data = {}
        
        for entry in sog_entries:
            if entry.team_code not in sog_data:
                sog_data[entry.team_code] = {1: 0, 2: 0, 3: 0, 4: 0}
            sog_data[entry.team_code][entry.period] = entry.shots
        
        return sog_data
    
    def resolve_team_names(self, year_id: int, game_id: int) -> Tuple[str, str]:
        """
        Resolve placeholder team names to actual team codes
        
        Args:
            year_id: Championship year ID
            game_id: Game ID
            
        Returns:
            Tuple of (team1_resolved, team2_resolved)
            
        Raises:
            NotFoundError: If year or game not found
        """
        year_obj = ChampionshipYear.query.get(year_id)
        if not year_obj:
            raise NotFoundError("Championship year", year_id)
        
        game = self.repository.find_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        # Get or create playoff resolver
        if year_id not in self._playoff_resolver_cache:
            games_raw = self.repository.find_by_year(year_id)
            self._playoff_resolver_cache[year_id] = PlayoffResolver(year_obj, games_raw)
        
        resolver = self._playoff_resolver_cache[year_id]
        
        # Use centralized resolver
        team1_resolved = resolver.get_resolved_code(game.team1_code)
        team2_resolved = resolver.get_resolved_code(game.team2_code)
        
        return team1_resolved, team2_resolved
    
    def get_game_with_stats(self, game_id: int) -> Dict[str, Any]:
        """
        Get comprehensive game information with all statistics
        
        Args:
            game_id: The game ID
            
        Returns:
            Dictionary with game data, statistics, and related information
            
        Raises:
            NotFoundError: If game not found
        """
        game = self.repository.find_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        # Resolve team names
        team1_name, team2_name = self.resolve_team_names(game.year_id, game_id)
        
        # Get SOG data
        sog_data = self._get_current_sog_data(game_id)
        
        # Calculate SOG totals
        sog_totals = {}
        for team_code, periods in sog_data.items():
            sog_totals[team_code] = sum(periods.values())
        
        # Get goals
        goals = self.repository.get_goals(game_id)
        
        # Get penalties
        penalties = self.repository.get_penalties(game_id)
        
        # Calculate PIM totals
        pim_totals = {team1_name: 0, team2_name: 0}
        for penalty in penalties:
            if penalty.team_code == team1_name:
                pim_totals[team1_name] += PIM_MAP.get(penalty.penalty_type, 0)
            elif penalty.team_code == team2_name:
                pim_totals[team2_name] += PIM_MAP.get(penalty.penalty_type, 0)
        
        # Calculate powerplay opportunities
        pp_opportunities = self._calculate_powerplay_opportunities(
            penalties, team1_name, team2_name
        )
        
        # Calculate powerplay goals
        pp_goals = {team1_name: 0, team2_name: 0}
        for goal in goals:
            if goal.goal_type == "PP":
                if goal.team_code == team1_name:
                    pp_goals[team1_name] += 1
                elif goal.team_code == team2_name:
                    pp_goals[team2_name] += 1
        
        # Get overrule if exists
        overrule = self.repository.get_overrule(game_id)
        
        return {
            'game': game,
            'team1_resolved': team1_name,
            'team2_resolved': team2_name,
            'team1_iso': TEAM_ISO_CODES.get(team1_name.upper(), ""),
            'team2_iso': TEAM_ISO_CODES.get(team2_name.upper(), ""),
            'sog_data': sog_data,
            'sog_totals': sog_totals,
            'goals': goals,
            'penalties': penalties,
            'pim_totals': pim_totals,
            'pp_opportunities': pp_opportunities,
            'pp_goals': pp_goals,
            'overrule': overrule
        }
    
    def _calculate_powerplay_opportunities(self, penalties: List[Penalty], 
                                         team1: str, team2: str) -> Dict[str, int]:
        """Calculate powerplay opportunities from penalties"""
        potential_pp_slots = []
        
        for penalty in penalties:
            if penalty.penalty_type in POWERPLAY_PENALTY_TYPES:
                # Each penalty gives exactly one powerplay opportunity
                beneficiary = None
                if penalty.team_code == team1:
                    beneficiary = team2
                elif penalty.team_code == team2:
                    beneficiary = team1
                
                if beneficiary:
                    potential_pp_slots.append({
                        'time': penalty.minute_of_game,
                        'beneficiary': beneficiary
                    })
        
        # Group by time to handle coincidental penalties
        grouped_slots = {}
        for slot in potential_pp_slots:
            time = slot['time']
            if time not in grouped_slots:
                grouped_slots[time] = []
            grouped_slots[time].append(slot)
        
        # Calculate final opportunities
        pp_opportunities = {team1: 0, team2: 0}
        for time, slots in grouped_slots.items():
            opp_team1 = sum(1 for s in slots if s['beneficiary'] == team1)
            opp_team2 = sum(1 for s in slots if s['beneficiary'] == team2)
            
            # Cancel out coincidental penalties
            cancelled = min(opp_team1, opp_team2)
            pp_opportunities[team1] += (opp_team1 - cancelled)
            pp_opportunities[team2] += (opp_team2 - cancelled)
        
        return pp_opportunities
    
    def add_overrule(self, game_id: int, reason: str) -> GameOverrule:
        """
        Add or update an overrule for a game
        
        Args:
            game_id: The game ID
            reason: Reason for the overrule
            
        Returns:
            The created or updated overrule
            
        Raises:
            NotFoundError: If game not found
            ValidationError: If reason is empty
        """
        game = self.repository.find_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        if not reason or not reason.strip():
            raise ValidationError("Overrule reason cannot be empty", "reason")
        
        try:
            # Check if overrule already exists
            existing_overrule = GameOverrule.query.filter_by(game_id=game_id).first()
            
            if existing_overrule:
                # Update existing
                existing_overrule.reason = reason.strip()
                existing_overrule.created_at = db.func.current_timestamp()
                self.commit()
                logger.info(f"Updated overrule for game {game_id}")
                return existing_overrule
            else:
                # Create new
                new_overrule = GameOverrule(
                    game_id=game_id,
                    reason=reason.strip()
                )
                self.db.session.add(new_overrule)
                self.commit()
                logger.info(f"Added overrule for game {game_id}")
                return new_overrule
                
        except Exception as e:
            self.rollback()
            logger.error(f"Error adding overrule for game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to add overrule: {str(e)}")
    
    def remove_overrule(self, game_id: int) -> bool:
        """
        Remove an overrule for a game
        
        Args:
            game_id: The game ID
            
        Returns:
            True if removed, False if not found
            
        Raises:
            NotFoundError: If game not found
        """
        game = self.repository.find_by_id(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        try:
            existing_overrule = GameOverrule.query.filter_by(game_id=game_id).first()
            
            if not existing_overrule:
                return False
            
            self.db.session.delete(existing_overrule)
            self.commit()
            logger.info(f"Removed overrule for game {game_id}")
            return True
            
        except Exception as e:
            self.rollback()
            logger.error(f"Error removing overrule for game {game_id}: {str(e)}")
            raise ServiceError(f"Failed to remove overrule: {str(e)}")
    
    def get_games_by_year(self, year_id: int, include_stats: bool = False) -> List[Dict[str, Any]]:
        """
        Get all games for a championship year
        
        Args:
            year_id: Championship year ID
            include_stats: Whether to include detailed statistics
            
        Returns:
            List of games with optional statistics
        """
        games = self.repository.find_by_year(year_id)
        
        if not include_stats:
            return games
        
        # Include detailed stats for each game
        games_with_stats = []
        for game in games:
            try:
                game_stats = self.get_game_with_stats(game.id)
                games_with_stats.append(game_stats)
            except Exception as e:
                logger.error(f"Error getting stats for game {game.id}: {str(e)}")
                games_with_stats.append({'game': game, 'error': str(e)})
        
        return games_with_stats
    
    def get_game_stats_for_view(self, year_id: int, game_id: int) -> Dict[str, Any]:
        """
        Get comprehensive game statistics for the game stats view
        Includes all playoff resolution logic and team name resolution
        
        Args:
            year_id: Championship year ID
            game_id: Game ID
            
        Returns:
            Dictionary with all necessary data for game stats view
            
        Raises:
            NotFoundError: If year or game not found
        """
        # Validiere Jahr und Spiel
        year_obj = ChampionshipYear.query.get(year_id)
        if not year_obj:
            raise NotFoundError("Championship year", year_id)
        
        game = self.repository.find_by_id(game_id)
        if not game or game.year_id != year_id:
            raise NotFoundError("Game", game_id)
        
        # Hole alle Spiele für Playoff-Resolution
        games_raw = self.repository.find_by_year(year_id)
        
        # Nutze PlayoffResolver für Team-Resolution
        if year_id not in self._playoff_resolver_cache:
            self._playoff_resolver_cache[year_id] = PlayoffResolver(year_obj, games_raw)
        
        resolver = self._playoff_resolver_cache[year_id]
        
        # Hole aufgelöste Teamnamen
        team1_resolved, team2_resolved = self.resolve_team_names(year_id, game_id)
        
        # Hole Spielstatistiken
        game_stats = self.get_game_with_stats(game_id)
        
        # Füge aufgelöste Namen zum Spielobjekt hinzu
        game.team1_display_name = team1_resolved
        game.team2_display_name = team2_resolved
        
        # Hole SOG-Daten mit aufgelösten Namen
        sog_data = game_stats['sog_data']
        sog_totals = game_stats['sog_totals']
        
        # Stelle sicher, dass beide Teams in den SOG-Daten vorhanden sind
        for team_name in [team1_resolved, team2_resolved]:
            if team_name not in sog_data:
                sog_data[team_name] = {1: 0, 2: 0, 3: 0, 4: 0}
            if team_name not in sog_totals:
                sog_totals[team_name] = 0
        
        # Berechne Scores nach Periode
        team1_scores_by_period = {1: 0, 2: 0, 3: 0, 4: 0}
        team2_scores_by_period = {1: 0, 2: 0, 3: 0, 4: 0}
        
        for goal in game_stats['goals']:
            time_sec = convert_time_to_seconds(goal.minute)
            period = 4
            if time_sec <= PERIOD_1_END:
                period = 1
            elif time_sec <= PERIOD_2_END:
                period = 2
            elif time_sec <= PERIOD_3_END:
                period = 3
            
            if goal.team_code == team1_resolved:
                team1_scores_by_period[period] += 1
            elif goal.team_code == team2_resolved:
                team2_scores_by_period[period] += 1
        
        # Erstelle Game Events für Template
        game_events = []
        player_cache = {p.id: p for p in Player.query.all()}
        
        def get_player_name(pid):
            p = player_cache.get(pid)
            return f"{p.first_name} {p.last_name}" if p else "N/A"
        
        for goal in game_stats['goals']:
            time_sec = convert_time_to_seconds(goal.minute)
            period_disp = "OT"
            if time_sec <= PERIOD_1_END:
                period_disp = "1st Period"
            elif time_sec <= PERIOD_2_END:
                period_disp = "2nd Period"
            elif time_sec <= PERIOD_3_END:
                period_disp = "3rd Period"
            
            game_events.append({
                'type': 'goal',
                'time_str': goal.minute,
                'time_for_sort': time_sec,
                'period_display': period_disp,
                'team_code': goal.team_code,
                'team_iso': TEAM_ISO_CODES.get(goal.team_code.upper() if goal.team_code else ""),
                'goal_type_display': GOAL_TYPE_DISPLAY_MAP.get(goal.goal_type, goal.goal_type),
                'is_empty_net': goal.is_empty_net,
                'scorer': get_player_name(goal.scorer_id),
                'assist1': get_player_name(goal.assist1_id) if goal.assist1_id else None,
                'assist2': get_player_name(goal.assist2_id) if goal.assist2_id else None,
                'scorer_obj': player_cache.get(goal.scorer_id),
                'assist1_obj': player_cache.get(goal.assist1_id) if goal.assist1_id else None,
                'assist2_obj': player_cache.get(goal.assist2_id) if goal.assist2_id else None,
            })
        
        game_events.sort(key=lambda x: x['time_for_sort'])
        
        # Berechne Powerplay-Prozentsatz
        pp_percentage = {team1_resolved: 0.0, team2_resolved: 0.0}
        for team_name in [team1_resolved, team2_resolved]:
            pp_opps = game_stats['pp_opportunities'].get(team_name, 0)
            pp_goals = game_stats['pp_goals'].get(team_name, 0)
            if pp_opps > 0:
                pp_percentage[team_name] = round((pp_goals / pp_opps) * 100, 1)
        
        return {
            'year': year_obj,
            'game': game,
            'team1_resolved': team1_resolved,
            'team2_resolved': team2_resolved,
            'sog_data': sog_data,
            'sog_totals': sog_totals,
            'pim_totals': game_stats['pim_totals'],
            'pp_goals_scored': game_stats['pp_goals'],
            'pp_opportunities': game_stats['pp_opportunities'],
            'pp_percentage': pp_percentage,
            'game_events': game_events,
            'team1_scores_by_period': team1_scores_by_period,
            'team2_scores_by_period': team2_scores_by_period
        }