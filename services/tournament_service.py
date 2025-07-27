"""
Tournament Service for IIHF World Championship Statistics
Handles all business logic related to tournament structure, scheduling, and progression
"""

from typing import Dict, List, Optional, Tuple, Any, Set
from models import ChampionshipYear, Game, TeamStats, db
from services.base import BaseService
from services.exceptions import ServiceError, ValidationError, NotFoundError, BusinessRuleError
# Repository will be injected or created internally
from utils.playoff_resolver import PlayoffResolver
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TournamentRepository:
    """Mock repository for testing - will be replaced with actual implementation"""
    def find_by_id(self, id): return None
    def find_by_year(self, year): return None
    def get_all_games(self, year_id): return []
    def get_group_games(self, year_id, group): return []
    def get_round_games(self, year_id, round_name): return []
    def get_upcoming_playoff_games(self, year_id): return []
    def get_filtered_games(self, year_id, round_name, date_from, date_to): return []
    def get_tournament_statistics(self, year_id): return {}
    def get_game_shots_on_goal(self, game_id): return []


class TournamentService(BaseService[ChampionshipYear]):
    """
    Service for tournament-related business logic
    Manages tournament structure, rounds, groups, playoffs, and championship progression
    """
    
    def __init__(self):
        super().__init__(ChampionshipYear)
        self.repository = TournamentRepository()  # Repository für Datenbankzugriff
        self._playoff_resolver_cache = {}
    
    def create_championship_year(self, name: str, year: int, 
                                fixture_path: Optional[str] = None) -> ChampionshipYear:
        """
        Create a new championship year
        
        Args:
            name: Championship name (e.g., "IIHF World Championship 2024")
            year: The year of the championship
            fixture_path: Optional path to fixture file
            
        Returns:
            Created championship year object
            
        Raises:
            ValidationError: If input data is invalid
            DuplicateError: If championship year already exists
            ServiceError: If creation fails
        """
        # Validate year
        current_year = datetime.now().year
        if year < 1920 or year > current_year + 5:
            raise ValidationError(f"Invalid year: {year}", "year")
        
        # Validate name
        if not name or not name.strip():
            raise ValidationError("Championship name cannot be empty", "name")
        
        try:
            # Check for duplicate
            existing = self.repository.find_by_year(year)
            if existing:
                raise ValidationError(f"Championship for year {year} already exists", "year")
            
            # Create championship
            championship = ChampionshipYear(
                name=name.strip(),
                year=year,
                fixture_path=fixture_path
            )
            
            self.db.session.add(championship)
            self.commit()
            
            logger.info(f"Created championship: {name} ({year})")
            return championship
            
        except ValidationError:
            self.rollback()
            raise
        except Exception as e:
            self.rollback()
            logger.error(f"Error creating championship: {str(e)}")
            raise ServiceError(f"Failed to create championship: {str(e)}")
    
    def get_tournament_structure(self, year_id: int) -> Dict[str, Any]:
        """
        Get complete tournament structure including groups and rounds
        
        Args:
            year_id: The championship year ID
            
        Returns:
            Dictionary with tournament structure
            
        Raises:
            NotFoundError: If championship year not found
        """
        championship = self.repository.find_by_id(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        # Get all games
        all_games = self.repository.get_all_games(year_id)
        
        # Extract tournament structure
        structure = {
            'championship': championship,
            'groups': self._extract_groups(all_games),
            'rounds': self._extract_rounds(all_games),
            'teams': self._extract_participating_teams(all_games),
            'total_games': len(all_games),
            'completed_games': sum(1 for g in all_games if g.team1_score is not None),
            'upcoming_games': sum(1 for g in all_games if g.team1_score is None)
        }
        
        return structure
    
    def _extract_groups(self, games: List[Game]) -> Dict[str, List[str]]:
        """Extract groups and their teams from games"""
        groups = {}
        
        for game in games:
            if game.group:
                if game.group not in groups:
                    groups[game.group] = set()
                
                # Add teams to group if not placeholders
                if not self._is_placeholder_team(game.team1_code):
                    groups[game.group].add(game.team1_code)
                if not self._is_placeholder_team(game.team2_code):
                    groups[game.group].add(game.team2_code)
        
        # Convert sets to sorted lists
        return {group: sorted(list(teams)) for group, teams in groups.items()}
    
    def _extract_rounds(self, games: List[Game]) -> List[Dict[str, Any]]:
        """Extract rounds and their details from games"""
        rounds_dict = {}
        
        for game in games:
            if game.round not in rounds_dict:
                rounds_dict[game.round] = {
                    'name': game.round,
                    'games': [],
                    'start_date': None,
                    'end_date': None
                }
            
            rounds_dict[game.round]['games'].append(game)
            
            # Update date range
            if game.date:
                game_date = game.date
                if not rounds_dict[game.round]['start_date'] or game_date < rounds_dict[game.round]['start_date']:
                    rounds_dict[game.round]['start_date'] = game_date
                if not rounds_dict[game.round]['end_date'] or game_date > rounds_dict[game.round]['end_date']:
                    rounds_dict[game.round]['end_date'] = game_date
        
        # Sort rounds by typical tournament order
        round_order = ['Group Stage', 'Quarterfinals', 'Semifinals', 'Bronze Medal Game', 'Gold Medal Game']
        
        sorted_rounds = []
        for round_name in round_order:
            if round_name in rounds_dict:
                sorted_rounds.append(rounds_dict[round_name])
        
        # Add any other rounds not in the standard order
        for round_name, round_data in rounds_dict.items():
            if round_name not in round_order:
                sorted_rounds.append(round_data)
        
        return sorted_rounds
    
    def _extract_participating_teams(self, games: List[Game]) -> List[str]:
        """Extract all participating teams"""
        teams = set()
        
        for game in games:
            if not self._is_placeholder_team(game.team1_code):
                teams.add(game.team1_code)
            if not self._is_placeholder_team(game.team2_code):
                teams.add(game.team2_code)
        
        return sorted(list(teams))
    
    def _is_placeholder_team(self, team_code: str) -> bool:
        """Check if team code is a placeholder"""
        if not team_code:
            return True
        placeholders = ['A', 'B', 'W', 'L', 'Q', 'S']
        return (team_code[0] in placeholders and 
                len(team_code) > 1 and 
                team_code[1:].isdigit())
    
    def get_group_standings(self, year_id: int, group: str) -> List[TeamStats]:
        """
        Get standings for a specific group
        
        Args:
            year_id: The championship year ID
            group: The group identifier (e.g., 'A', 'B')
            
        Returns:
            List of TeamStats objects sorted by ranking
            
        Raises:
            NotFoundError: If championship year not found
            ValidationError: If group doesn't exist
        """
        championship = self.repository.find_by_id(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        # Get group games
        group_games = self.repository.get_group_games(year_id, group)
        
        if not group_games:
            raise ValidationError(f"Group {group} not found in championship", "group")
        
        # Extract teams in group
        teams = set()
        for game in group_games:
            if not self._is_placeholder_team(game.team1_code):
                teams.add(game.team1_code)
            if not self._is_placeholder_team(game.team2_code):
                teams.add(game.team2_code)
        
        # Calculate standings
        standings = []
        for team_code in teams:
            team_games = [g for g in group_games if 
                         g.team1_code == team_code or g.team2_code == team_code]
            stats = self._calculate_team_stats_for_games(team_games, team_code, group)
            standings.append(stats)
        
        # Sort by IIHF ranking rules
        standings.sort(key=lambda x: (
            -x.pts,      # Points (descending)
            -x.gd,       # Goal difference (descending)
            -x.gf        # Goals for (descending)
        ))
        
        # Assign rankings
        for i, team_stats in enumerate(standings):
            team_stats.rank_in_group = i + 1
        
        return standings
    
    def _calculate_team_stats_for_games(self, games: List[Game], team_code: str, group: str) -> TeamStats:
        """Calculate team statistics from a set of games"""
        stats = TeamStats(name=team_code, group=group)
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            stats.gp += 1
            
            # Determine team position
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
            
            stats.pts += team_points
        
        return stats
    
    def get_playoff_bracket(self, year_id: int) -> Dict[str, Any]:
        """
        Get playoff bracket with resolved team names
        
        Args:
            year_id: The championship year ID
            
        Returns:
            Dictionary with playoff bracket structure
            
        Raises:
            NotFoundError: If championship year not found
        """
        championship = self.repository.find_by_id(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        # Get or create playoff resolver
        if year_id not in self._playoff_resolver_cache:
            all_games = self.repository.get_all_games(year_id)
            self._playoff_resolver_cache[year_id] = PlayoffResolver(championship, all_games)
        
        resolver = self._playoff_resolver_cache[year_id]
        
        # Get playoff games
        playoff_rounds = ['Quarterfinals', 'Semifinals', 'Bronze Medal Game', 'Gold Medal Game']
        bracket = {}
        
        for round_name in playoff_rounds:
            round_games = self.repository.get_round_games(year_id, round_name)
            
            bracket[round_name] = []
            for game in round_games:
                # Resolve team names
                team1_resolved = resolver.get_resolved_code(game.team1_code)
                team2_resolved = resolver.get_resolved_code(game.team2_code)
                
                bracket[round_name].append({
                    'game': game,
                    'team1_original': game.team1_code,
                    'team1_resolved': team1_resolved,
                    'team2_original': game.team2_code,
                    'team2_resolved': team2_resolved,
                    'completed': game.team1_score is not None and game.team2_score is not None
                })
        
        return bracket
    
    def update_playoff_progression(self, year_id: int, game_id: int) -> Dict[str, Any]:
        """
        Update playoff progression after a game result
        
        Args:
            year_id: The championship year ID
            game_id: The completed game ID
            
        Returns:
            Dictionary with updated playoff games
            
        Raises:
            NotFoundError: If championship or game not found
            BusinessRuleError: If game is not complete
        """
        championship = self.repository.find_by_id(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        game = Game.query.get(game_id)
        if not game:
            raise NotFoundError("Game", game_id)
        
        if game.team1_score is None or game.team2_score is None:
            raise BusinessRuleError("Game must be completed to update playoff progression", "incomplete_game")
        
        # Refresh playoff resolver
        all_games = self.repository.get_all_games(year_id)
        resolver = PlayoffResolver(championship, all_games)
        self._playoff_resolver_cache[year_id] = resolver
        
        # Get affected playoff games
        affected_games = []
        
        # Determine winner and loser
        if game.team1_score > game.team2_score:
            winner = game.team1_code
            loser = game.team2_code
        else:
            winner = game.team2_code
            loser = game.team1_code
        
        # Find games that might be affected by this result
        upcoming_games = self.repository.get_upcoming_playoff_games(year_id)
        
        for upcoming_game in upcoming_games:
            updated = False
            
            # Check if team1 placeholder can be resolved
            if self._is_placeholder_team(upcoming_game.team1_code):
                resolved = resolver.get_resolved_code(upcoming_game.team1_code)
                if resolved != upcoming_game.team1_code:
                    upcoming_game.team1_code = resolved
                    updated = True
            
            # Check if team2 placeholder can be resolved
            if self._is_placeholder_team(upcoming_game.team2_code):
                resolved = resolver.get_resolved_code(upcoming_game.team2_code)
                if resolved != upcoming_game.team2_code:
                    upcoming_game.team2_code = resolved
                    updated = True
            
            if updated:
                affected_games.append(upcoming_game)
        
        # Commit changes
        if affected_games:
            self.commit()
            logger.info(f"Updated {len(affected_games)} playoff games after game {game_id}")
        
        return {
            'completed_game': game,
            'winner': winner,
            'loser': loser,
            'affected_games': affected_games
        }
    
    def get_tournament_schedule(self, year_id: int, round_name: Optional[str] = None,
                               date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Game]:
        """
        Get tournament schedule with optional filters
        
        Args:
            year_id: The championship year ID
            round_name: Optional round filter
            date_from: Optional start date filter
            date_to: Optional end date filter
            
        Returns:
            List of games matching criteria
        """
        championship = self.repository.find_by_id(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        games = self.repository.get_filtered_games(year_id, round_name, date_from, date_to)
        
        # Sort by date and game number
        games.sort(key=lambda g: (g.date or '', g.game_number or 0))
        
        return games
    
    def get_tournament_statistics(self, year_id: int) -> Dict[str, Any]:
        """
        Get comprehensive tournament statistics
        
        Args:
            year_id: The championship year ID
            
        Returns:
            Dictionary with tournament statistics
        """
        championship = self.repository.find_by_id(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        stats = self.repository.get_tournament_statistics(year_id)
        
        return {
            'championship': championship,
            'total_games': stats['total_games'],
            'completed_games': stats['completed_games'],
            'goals_scored': stats['total_goals'],
            'average_goals_per_game': stats['total_goals'] / stats['completed_games'] if stats['completed_games'] > 0 else 0,
            'regulation_wins': stats['regulation_wins'],
            'overtime_games': stats['overtime_games'],
            'shootout_games': stats['shootout_games'],
            'participating_teams': stats['team_count'],
            'total_players': stats['player_count'],
            'penalty_minutes': stats['total_penalty_minutes'],
            'powerplay_goals': stats['powerplay_goals'],
            'empty_net_goals': stats['empty_net_goals']
        }
    
    def validate_tournament_integrity(self, year_id: int) -> Dict[str, List[str]]:
        """
        Validate tournament data integrity
        
        Args:
            year_id: The championship year ID
            
        Returns:
            Dictionary with validation issues by category
        """
        championship = self.repository.find_by_id(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        issues = {
            'missing_results': [],
            'invalid_scores': [],
            'missing_statistics': [],
            'playoff_issues': [],
            'data_inconsistencies': []
        }
        
        all_games = self.repository.get_all_games(year_id)
        
        for game in all_games:
            # Check for games without results
            if game.team1_score is None or game.team2_score is None:
                if game.date and game.date < datetime.now().strftime('%Y-%m-%d'):
                    issues['missing_results'].append(
                        f"Game {game.game_number}: {game.team1_code} vs {game.team2_code} ({game.date})"
                    )
            
            # Check for invalid scores
            if game.team1_score is not None and game.team2_score is not None:
                if game.team1_score < 0 or game.team2_score < 0:
                    issues['invalid_scores'].append(
                        f"Game {game.game_number}: Negative score detected"
                    )
                
                # Check result type consistency
                if game.result_type in ['OT', 'SO']:
                    if abs(game.team1_score - game.team2_score) != 1:
                        issues['data_inconsistencies'].append(
                            f"Game {game.game_number}: {game.result_type} game should have 1-goal difference"
                        )
            
            # Check for missing SOG data
            sog_data = self.repository.get_game_shots_on_goal(game.id)
            if game.team1_score is not None and not sog_data:
                issues['missing_statistics'].append(
                    f"Game {game.game_number}: Missing shots on goal data"
                )
        
        # Validate playoff progression
        playoff_games = [g for g in all_games if g.round in 
                        ['Quarterfinals', 'Semifinals', 'Bronze Medal Game', 'Gold Medal Game']]
        
        for game in playoff_games:
            if self._is_placeholder_team(game.team1_code) or self._is_placeholder_team(game.team2_code):
                # Check if placeholders should have been resolved
                if game.round == 'Semifinals':
                    qf_complete = all(g.team1_score is not None for g in all_games 
                                    if g.round == 'Quarterfinals')
                    if qf_complete:
                        issues['playoff_issues'].append(
                            f"Game {game.game_number}: Unresolved playoff teams in {game.round}"
                        )
        
        return issues