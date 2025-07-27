"""
Tournament Service with Repository Pattern
Handles all business logic related to tournaments, standings, and tournament statistics
"""

from typing import Dict, List, Optional, Tuple, Any
from models import ChampionshipYear, Game, db
from app.services.base import BaseService
from app.services.utils.cache_manager import CacheableService, cached
from app.repositories.core.tournament_repository import TournamentRepository
from app.exceptions import ServiceError, ValidationError, NotFoundError, BusinessRuleError
from utils.playoff_resolver import PlayoffResolver
from constants import TEAM_ISO_CODES
import logging
from datetime import datetime
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)


class TournamentService(CacheableService, BaseService[ChampionshipYear]):
    """
    Service for tournament-related business logic using repository pattern
    Manages tournaments, standings, schedules, and tournament statistics
    """
    
    def __init__(self, repository: Optional[TournamentRepository] = None):
        """
        Initialize service with repository and cache
        
        Args:
            repository: TournamentRepository instance (optional, will create if not provided)
        """
        if repository is None:
            repository = TournamentRepository()
        # Initialisiere beide Elternklassen
        # Use proper MRO initialization
        super().__init__(repository)
    
    def create_tournament(self, name: str, year: int, fixture_path: Optional[str] = None) -> ChampionshipYear:
        """
        Create a new tournament with validation
        
        Args:
            name: Tournament name
            year: Tournament year
            fixture_path: Optional path to fixture file
            
        Returns:
            Created tournament object
            
        Raises:
            ValidationError: If validation fails
            BusinessRuleError: If tournament already exists for the year
        """
        # Validate inputs
        if not name or not name.strip():
            raise ValidationError("Tournament name cannot be empty", "name")
        
        if year < 1920 or year > datetime.now().year + 10:
            raise ValidationError(f"Invalid year: {year}", "year")
        
        # Check if tournament already exists for this year
        existing = self.repository.get_by_year(year)
        if existing:
            raise BusinessRuleError(
                f"Tournament already exists for year {year}",
                "duplicate_tournament"
            )
        
        try:
            # Create tournament
            tournament = self.create(
                name=name.strip(),
                year=year,
                fixture_path=fixture_path
            )
            
            logger.info(f"Created tournament: {name} ({year})")
            return tournament
            
        except Exception as e:
            self.rollback()
            logger.error(f"Error creating tournament: {str(e)}")
            raise ServiceError(f"Failed to create tournament: {str(e)}")
    
    def update_tournament(self, tournament_id: int, name: Optional[str] = None,
                         fixture_path: Optional[str] = None) -> ChampionshipYear:
        """
        Update tournament information
        
        Args:
            tournament_id: Tournament ID to update
            name: New tournament name (optional)
            fixture_path: New fixture path (optional)
            
        Returns:
            Updated tournament object
            
        Raises:
            NotFoundError: If tournament not found
            ValidationError: If validation fails
        """
        tournament = self.get_by_id(tournament_id)
        if not tournament:
            raise NotFoundError("Tournament", tournament_id)
        
        update_data = {}
        
        if name is not None:
            if not name.strip():
                raise ValidationError("Tournament name cannot be empty", "name")
            update_data['name'] = name.strip()
        
        if fixture_path is not None:
            update_data['fixture_path'] = fixture_path
        
        if not update_data:
            return tournament  # Nothing to update
        
        try:
            updated = self.update(tournament_id, **update_data)
            logger.info(f"Updated tournament {tournament_id}")
            return updated
            
        except Exception as e:
            self.rollback()
            logger.error(f"Error updating tournament {tournament_id}: {str(e)}")
            raise ServiceError(f"Failed to update tournament: {str(e)}")
    
    def get_tournament_by_year(self, year: int) -> Optional[ChampionshipYear]:
        """
        Get tournament by year
        
        Args:
            year: Tournament year
            
        Returns:
            Tournament if found, None otherwise
        """
        return self.repository.get_by_year(year)
    
    def get_recent_tournaments(self, limit: int = 10) -> List[ChampionshipYear]:
        """
        Get most recent tournaments
        
        Args:
            limit: Number of tournaments to return (default: 10)
            
        Returns:
            List of recent tournaments
        """
        return self.repository.get_recent_tournaments(limit)
    
    @cached(ttl=600, key_prefix="tournament:statistics")
    def get_tournament_statistics(self, tournament_id: int) -> Dict[str, Any]:
        """
        Get comprehensive tournament statistics
        
        Args:
            tournament_id: Tournament ID
            
        Returns:
            Dictionary with tournament statistics
            
        Raises:
            NotFoundError: If tournament not found
        """
        stats = self.repository.get_tournament_with_stats(tournament_id)
        if not stats or not stats.get('tournament'):
            raise NotFoundError("Tournament", tournament_id)
        
        tournament = stats['tournament']
        
        # Calculate additional statistics
        completion_rate = 0
        if stats['total_games'] > 0:
            completion_rate = (stats['completed_games'] / stats['total_games']) * 100
        
        # Get medal winners if tournament is complete
        medal_winners = self._get_medal_winners(tournament_id) if completion_rate == 100 else None
        
        # Get top scorers
        top_scorers = self._get_top_scorers(tournament_id, limit=10)
        
        # Get tournament records
        records = self._get_tournament_records(tournament_id)
        
        return {
            'tournament': tournament,
            'total_games': stats['total_games'],
            'completed_games': stats['completed_games'],
            'completion_rate': round(completion_rate, 2),
            'rounds': stats['rounds'],
            'participating_teams': stats['participating_teams'],
            'venues': stats['venues'],
            'medal_winners': medal_winners,
            'top_scorers': top_scorers,
            'records': records
        }
    
    @cached(ttl=300, key_prefix="tournament:standings")
    def get_tournament_standings(self, tournament_id: int, group: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tournament standings with additional context
        
        Args:
            tournament_id: Tournament ID
            group: Optional group filter
            
        Returns:
            Dictionary with standings and metadata
            
        Raises:
            NotFoundError: If tournament not found
        """
        tournament = self.get_by_id(tournament_id)
        if not tournament:
            raise NotFoundError("Tournament", tournament_id)
        
        standings = self.repository.get_tournament_standings(tournament_id, group)
        
        # Add position numbers if not already set
        for i, team in enumerate(standings, 1):
            if 'position' not in team or team['position'] is None:
                team['position'] = i
            
            # Add ISO codes
            team['iso_code'] = TEAM_ISO_CODES.get(team['team_code'].upper(), '')
        
        # Get current round information
        current_round = self._get_current_round(tournament_id)
        
        return {
            'tournament': tournament,
            'group': group,
            'standings': standings,
            'current_round': current_round,
            'last_updated': datetime.now().isoformat()
        }
    
    @cached(ttl=300, key_prefix="tournament:schedule")
    def get_tournament_schedule(self, tournament_id: int, round: Optional[str] = None,
                               include_results: bool = False) -> Dict[str, Any]:
        """
        Get tournament game schedule with optional results
        
        Args:
            tournament_id: Tournament ID
            round: Optional round filter
            include_results: Whether to separate completed games
            
        Returns:
            Dictionary with schedule information
            
        Raises:
            NotFoundError: If tournament not found
        """
        tournament = self.get_by_id(tournament_id)
        if not tournament:
            raise NotFoundError("Tournament", tournament_id)
        
        all_games = self.repository.get_tournament_schedule(tournament_id, round)
        
        if include_results:
            upcoming = []
            completed = []
            
            for game in all_games:
                if game.team1_score is None or game.team2_score is None:
                    upcoming.append(self._format_game_info(game))
                else:
                    completed.append(self._format_game_info(game))
            
            return {
                'tournament': tournament,
                'round': round,
                'upcoming_games': upcoming,
                'completed_games': completed,
                'total_games': len(all_games)
            }
        else:
            games = [self._format_game_info(game) for game in all_games]
            return {
                'tournament': tournament,
                'round': round,
                'games': games,
                'total_games': len(games)
            }
    
    @cached(ttl=600, key_prefix="tournament:team_performance")
    def get_team_tournament_performance(self, tournament_id: int, team_code: str) -> Dict[str, Any]:
        """
        Get detailed team performance in a tournament
        
        Args:
            tournament_id: Tournament ID
            team_code: Team code
            
        Returns:
            Dictionary with team performance data
            
        Raises:
            NotFoundError: If tournament or team not found
        """
        tournament = self.get_by_id(tournament_id)
        if not tournament:
            raise NotFoundError("Tournament", tournament_id)
        
        performance = self.repository.get_tournament_team_performance(tournament_id, team_code)
        
        if not performance.get('games'):
            raise NotFoundError(f"Team {team_code} in tournament", tournament_id)
        
        # Add additional analysis
        performance['tournament'] = tournament
        performance['team_iso'] = TEAM_ISO_CODES.get(team_code.upper(), '')
        
        # Calculate form (last 5 games)
        completed_games = [g for g in performance['games'] 
                          if g.team1_score is not None and g.team2_score is not None]
        last_5_games = completed_games[-5:] if len(completed_games) >= 5 else completed_games
        
        form = []
        for game in last_5_games:
            if game.team1_code == team_code:
                form.append('W' if game.team1_score > game.team2_score else 'L')
            else:
                form.append('W' if game.team2_score > game.team1_score else 'L')
        
        performance['recent_form'] = ''.join(form)
        
        # Calculate average goals per game
        games_played = len(completed_games)
        if games_played > 0:
            performance['avg_goals_for'] = round(performance['total_goals_scored'] / games_played, 2)
            performance['avg_goals_against'] = round(performance['total_goals_conceded'] / games_played, 2)
        else:
            performance['avg_goals_for'] = 0
            performance['avg_goals_against'] = 0
        
        return performance
    
    def get_head_to_head_in_tournament(self, tournament_id: int, team1_code: str, 
                                      team2_code: str) -> Dict[str, Any]:
        """
        Get head-to-head record between two teams in a tournament
        
        Args:
            tournament_id: Tournament ID
            team1_code: First team code
            team2_code: Second team code
            
        Returns:
            Dictionary with head-to-head data
            
        Raises:
            NotFoundError: If tournament not found
        """
        tournament = self.get_by_id(tournament_id)
        if not tournament:
            raise NotFoundError("Tournament", tournament_id)
        
        # Get games between the teams
        games = Game.query.filter(
            and_(
                Game.year_id == tournament_id,
                or_(
                    and_(Game.team1_code == team1_code, Game.team2_code == team2_code),
                    and_(Game.team1_code == team2_code, Game.team2_code == team1_code)
                )
            )
        ).order_by(Game.game_number).all()
        
        # Calculate statistics
        team1_wins = 0
        team2_wins = 0
        team1_goals = 0
        team2_goals = 0
        meetings = []
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                meetings.append({
                    'game': game,
                    'completed': False
                })
                continue
            
            game_info = self._format_game_info(game)
            
            if game.team1_code == team1_code:
                team1_goals += game.team1_score
                team2_goals += game.team2_score
                if game.team1_score > game.team2_score:
                    team1_wins += 1
                    game_info['winner'] = team1_code
                else:
                    team2_wins += 1
                    game_info['winner'] = team2_code
            else:
                team1_goals += game.team2_score
                team2_goals += game.team1_score
                if game.team2_score > game.team1_score:
                    team1_wins += 1
                    game_info['winner'] = team1_code
                else:
                    team2_wins += 1
                    game_info['winner'] = team2_code
            
            meetings.append({
                'game': game_info,
                'completed': True
            })
        
        return {
            'tournament': tournament,
            'team1': {
                'code': team1_code,
                'iso': TEAM_ISO_CODES.get(team1_code.upper(), ''),
                'wins': team1_wins,
                'goals': team1_goals
            },
            'team2': {
                'code': team2_code,
                'iso': TEAM_ISO_CODES.get(team2_code.upper(), ''),
                'wins': team2_wins,
                'goals': team2_goals
            },
            'total_meetings': len(games),
            'completed_meetings': team1_wins + team2_wins,
            'meetings': meetings
        }
    
    def search_tournaments(self, criteria: Dict[str, Any]) -> List[ChampionshipYear]:
        """
        Search tournaments with advanced criteria
        
        Args:
            criteria: Search criteria dictionary
            
        Returns:
            List of matching tournaments
        """
        return self.repository.search_tournaments(criteria)
    
    def delete_tournament(self, tournament_id: int) -> bool:
        """
        Delete a tournament (cascade deletes all related data)
        
        Args:
            tournament_id: Tournament ID to delete
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            BusinessRuleError: If tournament has games
        """
        tournament = self.get_by_id(tournament_id)
        if not tournament:
            return False
        
        # Check if tournament has games
        game_count = Game.query.filter_by(year_id=tournament_id).count()
        if game_count > 0:
            raise BusinessRuleError(
                f"Cannot delete tournament with {game_count} games. Delete games first.",
                "tournament_has_games"
            )
        
        try:
            result = self.delete(tournament_id)
            logger.info(f"Deleted tournament {tournament_id}")
            return result
            
        except Exception as e:
            self.rollback()
            logger.error(f"Error deleting tournament {tournament_id}: {str(e)}")
            raise ServiceError(f"Failed to delete tournament: {str(e)}")
    
    # Helper methods
    
    def _format_game_info(self, game: Game) -> Dict[str, Any]:
        """Format game information for display"""
        return {
            'id': game.id,
            'game_number': game.game_number,
            'date': game.date,
            'start_time': game.start_time,
            'round': game.round,
            'group': game.group,
            'team1_code': game.team1_code,
            'team2_code': game.team2_code,
            'team1_iso': TEAM_ISO_CODES.get(game.team1_code.upper(), ''),
            'team2_iso': TEAM_ISO_CODES.get(game.team2_code.upper(), ''),
            'venue': game.venue,
            'location': game.location,
            'team1_score': game.team1_score,
            'team2_score': game.team2_score,
            'result_type': game.result_type,
            'completed': game.team1_score is not None and game.team2_score is not None
        }
    
    def _get_current_round(self, tournament_id: int) -> Optional[str]:
        """Get the current round being played"""
        # Get the latest game with a score
        latest_completed = Game.query.filter(
            and_(
                Game.year_id == tournament_id,
                Game.team1_score.isnot(None),
                Game.team2_score.isnot(None)
            )
        ).order_by(Game.game_number.desc()).first()
        
        if latest_completed:
            # Check if there are incomplete games in the same round
            incomplete_same_round = Game.query.filter(
                and_(
                    Game.year_id == tournament_id,
                    Game.round == latest_completed.round,
                    Game.team1_score.is_(None)
                )
            ).count()
            
            if incomplete_same_round > 0:
                return latest_completed.round
            
            # Otherwise, find the next round
            next_game = Game.query.filter(
                and_(
                    Game.year_id == tournament_id,
                    Game.game_number > latest_completed.game_number,
                    Game.team1_score.is_(None)
                )
            ).order_by(Game.game_number).first()
            
            if next_game:
                return next_game.round
        else:
            # No completed games, get first game's round
            first_game = Game.query.filter(
                Game.year_id == tournament_id
            ).order_by(Game.game_number).first()
            
            if first_game:
                return first_game.round
        
        return None
    
    def _get_medal_winners(self, tournament_id: int) -> Optional[Dict[str, str]]:
        """Get medal winners for completed tournament"""
        # Get final games
        final = Game.query.filter(
            and_(
                Game.year_id == tournament_id,
                Game.round == 'Final'
            )
        ).first()
        
        bronze = Game.query.filter(
            and_(
                Game.year_id == tournament_id,
                Game.round == 'Bronze Medal Game'
            )
        ).first()
        
        if not final or final.team1_score is None:
            return None
        
        medals = {}
        
        # Gold and Silver from Final
        if final.team1_score > final.team2_score:
            medals['gold'] = final.team1_code
            medals['silver'] = final.team2_code
        else:
            medals['gold'] = final.team2_code
            medals['silver'] = final.team1_code
        
        # Bronze from Bronze Medal Game
        if bronze and bronze.team1_score is not None:
            if bronze.team1_score > bronze.team2_score:
                medals['bronze'] = bronze.team1_code
            else:
                medals['bronze'] = bronze.team2_code
        
        return medals
    
    def _get_top_scorers(self, tournament_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top scorers for tournament (placeholder - would need Goal model integration)"""
        # This would require integration with Goal/Player models
        # For now, return empty list
        return []
    
    def _get_tournament_records(self, tournament_id: int) -> Dict[str, Any]:
        """Get tournament records (highest scoring game, biggest win, etc.)"""
        games = Game.query.filter(
            and_(
                Game.year_id == tournament_id,
                Game.team1_score.isnot(None),
                Game.team2_score.isnot(None)
            )
        ).all()
        
        if not games:
            return {}
        
        records = {
            'highest_scoring_game': None,
            'biggest_win': None,
            'most_goals_team': None,
            'most_goals_game': 0,
            'biggest_margin': 0
        }
        
        team_goals = {}
        
        for game in games:
            total_goals = game.team1_score + game.team2_score
            margin = abs(game.team1_score - game.team2_score)
            
            # Track highest scoring game
            if total_goals > records['most_goals_game']:
                records['most_goals_game'] = total_goals
                records['highest_scoring_game'] = self._format_game_info(game)
            
            # Track biggest win
            if margin > records['biggest_margin']:
                records['biggest_margin'] = margin
                records['biggest_win'] = self._format_game_info(game)
            
            # Track team goals
            if game.team1_code not in team_goals:
                team_goals[game.team1_code] = 0
            if game.team2_code not in team_goals:
                team_goals[game.team2_code] = 0
            
            team_goals[game.team1_code] += game.team1_score
            team_goals[game.team2_code] += game.team2_score
        
        # Find team with most goals
        if team_goals:
            max_team = max(team_goals.items(), key=lambda x: x[1])
            records['most_goals_team'] = {
                'team_code': max_team[0],
                'goals': max_team[1]
            }
        
        return records