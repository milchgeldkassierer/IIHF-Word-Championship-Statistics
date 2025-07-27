"""
Records Service for IIHF World Championship Statistics
Handles all business logic related to tournament records, milestones, and historical achievements
"""

from typing import Dict, List, Optional, Tuple, Any
from models import Game, ChampionshipYear, Player, Goal, Penalty, ShotsOnGoal, db
from services.base import BaseService
from services.exceptions import ServiceError, NotFoundError
from app.repositories.core.records_repository import RecordsRepository
from constants import PIM_MAP
import logging

logger = logging.getLogger(__name__)


class RecordsService(BaseService[Game]):
    """
    Service for records-related business logic
    Manages tournament records, player achievements, team records, and historical statistics
    """
    
    def __init__(self):
        super().__init__(Game)  # Records are derived from games
        # self.repository = RecordsRepository()  # TODO: Create RecordsRepository
    
    def get_tournament_records(self, year_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get comprehensive tournament records
        
        Args:
            year_id: Optional championship year ID (None for all-time records)
            
        Returns:
            Dictionary with various tournament records
        """
        records = {
            'scoring': self._get_scoring_records(year_id),
            'team': self._get_team_records(year_id),
            'game': self._get_game_records(year_id),
            'penalty': self._get_penalty_records(year_id),
            'goaltending': self._get_goaltending_records(year_id),
            'streaks': self._get_streak_records(year_id),
            'milestones': self._get_milestone_records(year_id)
        }
        
        return records
    
    def _get_scoring_records(self, year_id: Optional[int]) -> Dict[str, Any]:
        """Get scoring-related records"""
        return {
            'most_goals_tournament': self.repository.get_most_goals_in_tournament(year_id),
            'most_assists_tournament': self.repository.get_most_assists_in_tournament(year_id),
            'most_points_tournament': self.repository.get_most_points_in_tournament(year_id),
            'most_goals_game': self.repository.get_most_goals_in_game(year_id),
            'most_points_game': self.repository.get_most_points_in_game(year_id),
            'fastest_goal': self.repository.get_fastest_goal(year_id),
            'most_powerplay_goals': self.repository.get_most_powerplay_goals(year_id),
            'most_shorthanded_goals': self.repository.get_most_shorthanded_goals(year_id),
            'most_game_winning_goals': self.repository.get_most_game_winning_goals(year_id),
            'most_empty_net_goals': self.repository.get_most_empty_net_goals(year_id)
        }
    
    def _get_team_records(self, year_id: Optional[int]) -> Dict[str, Any]:
        """Get team-related records"""
        return {
            'highest_scoring_team': self.repository.get_highest_scoring_team(year_id),
            'best_defensive_team': self.repository.get_best_defensive_team(year_id),
            'best_powerplay': self.repository.get_best_powerplay_team(year_id),
            'best_penalty_kill': self.repository.get_best_penalty_kill_team(year_id),
            'most_wins': self.repository.get_most_wins_team(year_id),
            'best_goal_differential': self.repository.get_best_goal_differential(year_id),
            'most_shots_on_goal': self.repository.get_most_shots_team(year_id),
            'most_penalties': self.repository.get_most_penalized_team(year_id)
        }
    
    def _get_game_records(self, year_id: Optional[int]) -> Dict[str, Any]:
        """Get game-related records"""
        return {
            'highest_scoring_game': self.repository.get_highest_scoring_game(year_id),
            'biggest_win_margin': self.repository.get_biggest_win_margin(year_id),
            'most_goals_by_team': self.repository.get_most_goals_by_team_game(year_id),
            'most_penalties_game': self.repository.get_most_penalties_game(year_id),
            'longest_game': self.repository.get_longest_overtime_game(year_id),
            'most_shots_game': self.repository.get_most_shots_game(year_id)
        }
    
    def _get_penalty_records(self, year_id: Optional[int]) -> Dict[str, Any]:
        """Get penalty-related records"""
        return {
            'most_pim_player': self.repository.get_most_pim_player(year_id),
            'most_pim_team': self.repository.get_most_pim_team(year_id),
            'most_penalties_player': self.repository.get_most_penalties_player(year_id),
            'longest_suspension': self.repository.get_longest_suspension(year_id)
        }
    
    def _get_goaltending_records(self, year_id: Optional[int]) -> Dict[str, Any]:
        """Get goaltending-related records (derived from team stats)"""
        return {
            'most_shutouts': self.repository.get_most_shutouts(year_id),
            'best_goals_against': self.repository.get_best_goals_against_average(year_id),
            'most_saves_game': self.repository.get_most_saves_game(year_id)
        }
    
    def _get_streak_records(self, year_id: Optional[int]) -> Dict[str, Any]:
        """Get streak-related records"""
        return {
            'longest_win_streak': self.repository.get_longest_win_streak(year_id),
            'longest_point_streak': self.repository.get_longest_point_streak(year_id),
            'longest_goal_streak': self.repository.get_longest_goal_streak(year_id),
            'most_consecutive_wins_tournament': self.repository.get_most_consecutive_wins(year_id)
        }
    
    def _get_milestone_records(self, year_id: Optional[int]) -> Dict[str, Any]:
        """Get milestone achievements"""
        return {
            '100_goals': self.repository.get_players_with_100_goals(),
            '200_points': self.repository.get_players_with_200_points(),
            '10_tournaments': self.repository.get_players_with_10_tournaments(),
            'gold_medals': self.repository.get_most_gold_medals()
        }
    
    def get_player_records(self, player_id: int) -> Dict[str, Any]:
        """
        Get all records for a specific player
        
        Args:
            player_id: The player ID
            
        Returns:
            Dictionary with player's records and achievements
            
        Raises:
            NotFoundError: If player not found
        """
        player = Player.query.get(player_id)
        if not player:
            raise NotFoundError("Player", player_id)
        
        records = {
            'player': player,
            'career_totals': self.repository.get_player_career_totals(player_id),
            'single_tournament_bests': self.repository.get_player_single_tournament_bests(player_id),
            'single_game_bests': self.repository.get_player_single_game_bests(player_id),
            'achievements': self._get_player_achievements(player_id),
            'tournament_history': self.repository.get_player_tournament_history(player_id)
        }
        
        return records
    
    def _get_player_achievements(self, player_id: int) -> List[Dict[str, Any]]:
        """Get player achievements and milestones"""
        achievements = []
        career_totals = self.repository.get_player_career_totals(player_id)
        
        # Goal milestones
        goal_milestones = [10, 25, 50, 100]
        for milestone in goal_milestones:
            if career_totals.get('goals', 0) >= milestone:
                achievements.append({
                    'type': 'scoring',
                    'achievement': f'{milestone} Career Goals',
                    'date_achieved': self.repository.get_milestone_date(player_id, 'goals', milestone)
                })
        
        # Point milestones
        point_milestones = [25, 50, 100, 200]
        for milestone in point_milestones:
            if career_totals.get('points', 0) >= milestone:
                achievements.append({
                    'type': 'scoring',
                    'achievement': f'{milestone} Career Points',
                    'date_achieved': self.repository.get_milestone_date(player_id, 'points', milestone)
                })
        
        # Tournament participation
        tournaments = career_totals.get('tournaments', 0)
        if tournaments >= 10:
            achievements.append({
                'type': 'longevity',
                'achievement': f'{tournaments} Tournament Appearances',
                'date_achieved': None
            })
        
        # Special achievements
        if career_totals.get('gold_medals', 0) > 0:
            achievements.append({
                'type': 'team',
                'achievement': f"{career_totals['gold_medals']} Gold Medal(s)",
                'date_achieved': None
            })
        
        return achievements
    
    def get_team_records(self, team_code: str) -> Dict[str, Any]:
        """
        Get all records for a specific team
        
        Args:
            team_code: The team code
            
        Returns:
            Dictionary with team's records and achievements
        """
        records = {
            'team': team_code,
            'all_time_record': self.repository.get_team_all_time_record(team_code),
            'tournament_wins': self.repository.get_team_tournament_wins(team_code),
            'best_tournament': self.repository.get_team_best_tournament(team_code),
            'worst_tournament': self.repository.get_team_worst_tournament(team_code),
            'biggest_win': self.repository.get_team_biggest_win(team_code),
            'worst_loss': self.repository.get_team_worst_loss(team_code),
            'highest_scoring_game': self.repository.get_team_highest_scoring_game(team_code),
            'player_records': self.repository.get_team_player_records(team_code),
            'head_to_head_records': self._get_team_head_to_head_records(team_code)
        }
        
        return records
    
    def _get_team_head_to_head_records(self, team_code: str) -> List[Dict[str, Any]]:
        """Get head-to-head records against all opponents"""
        opponents = self.repository.get_team_all_opponents(team_code)
        h2h_records = []
        
        for opponent in opponents:
            record = self.repository.get_team_vs_opponent_record(team_code, opponent)
            if record['games_played'] > 0:
                h2h_records.append(record)
        
        # Sort by games played
        h2h_records.sort(key=lambda x: -x['games_played'])
        
        return h2h_records
    
    def get_championship_records(self, year_id: int) -> Dict[str, Any]:
        """
        Get records specific to a championship year
        
        Args:
            year_id: The championship year ID
            
        Returns:
            Dictionary with championship-specific records
            
        Raises:
            NotFoundError: If championship not found
        """
        championship = ChampionshipYear.query.get(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        records = {
            'championship': championship,
            'tournament_mvp': self.repository.get_tournament_mvp(year_id),
            'all_star_team': self.repository.get_all_star_team(year_id),
            'scoring_leader': self.repository.get_scoring_leader(year_id),
            'best_goaltender': self.repository.get_best_goaltender(year_id),
            'fair_play_award': self.repository.get_fair_play_team(year_id),
            'championship_game': self.repository.get_championship_game(year_id),
            'tournament_summary': self._get_tournament_summary(year_id)
        }
        
        return records
    
    def _get_tournament_summary(self, year_id: int) -> Dict[str, Any]:
        """Get tournament summary statistics"""
        return {
            'total_goals': self.repository.get_tournament_total_goals(year_id),
            'games_played': self.repository.get_tournament_games_played(year_id),
            'participating_teams': self.repository.get_tournament_team_count(year_id),
            'total_players': self.repository.get_tournament_player_count(year_id),
            'overtime_games': self.repository.get_tournament_overtime_games(year_id),
            'shutouts': self.repository.get_tournament_shutouts(year_id),
            'hat_tricks': self.repository.get_tournament_hat_tricks(year_id),
            'penalty_minutes': self.repository.get_tournament_penalty_minutes(year_id),
            'attendance': self.repository.get_tournament_attendance(year_id)
        }
    
    def search_records(self, search_type: str, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search for specific records based on criteria
        
        Args:
            search_type: Type of record to search ('player', 'team', 'game')
            criteria: Search criteria
            
        Returns:
            List of matching records
        """
        if search_type == 'player':
            return self._search_player_records(criteria)
        elif search_type == 'team':
            return self._search_team_records(criteria)
        elif search_type == 'game':
            return self._search_game_records(criteria)
        else:
            raise ValueError(f"Invalid search type: {search_type}")
    
    def _search_player_records(self, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search player records based on criteria"""
        results = []
        
        # Search by minimum goals
        if 'min_goals' in criteria:
            players = self.repository.get_players_with_min_goals(
                criteria['min_goals'],
                criteria.get('year_id')
            )
            results.extend(players)
        
        # Search by minimum points
        if 'min_points' in criteria:
            players = self.repository.get_players_with_min_points(
                criteria['min_points'],
                criteria.get('year_id')
            )
            results.extend(players)
        
        # Remove duplicates
        seen = set()
        unique_results = []
        for result in results:
            player_id = result.get('player_id')
            if player_id not in seen:
                seen.add(player_id)
                unique_results.append(result)
        
        return unique_results
    
    def _search_team_records(self, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search team records based on criteria"""
        results = []
        
        # Search by minimum wins
        if 'min_wins' in criteria:
            teams = self.repository.get_teams_with_min_wins(
                criteria['min_wins'],
                criteria.get('year_id')
            )
            results.extend(teams)
        
        # Search by goal differential
        if 'min_goal_diff' in criteria:
            teams = self.repository.get_teams_with_min_goal_diff(
                criteria['min_goal_diff'],
                criteria.get('year_id')
            )
            results.extend(teams)
        
        return results
    
    def _search_game_records(self, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search game records based on criteria"""
        results = []
        
        # Search by minimum total goals
        if 'min_total_goals' in criteria:
            games = self.repository.get_games_with_min_goals(
                criteria['min_total_goals'],
                criteria.get('year_id')
            )
            results.extend(games)
        
        # Search by result type
        if 'result_type' in criteria:
            games = self.repository.get_games_by_result_type(
                criteria['result_type'],
                criteria.get('year_id')
            )
            results.extend(games)
        
        return results
    
    def get_record_progression(self, record_type: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get historical progression of a specific record
        
        Args:
            record_type: Type of record (e.g., 'most_goals_tournament')
            limit: Number of historical entries to return
            
        Returns:
            List showing how the record has progressed over time
        """
        return self.repository.get_record_progression(record_type, limit)
    
    def compare_records(self, entity1: str, entity2: str, 
                       entity_type: str = 'player') -> Dict[str, Any]:
        """
        Compare records between two entities
        
        Args:
            entity1: First entity ID or code
            entity2: Second entity ID or code
            entity_type: Type of entity ('player' or 'team')
            
        Returns:
            Dictionary with side-by-side comparison
        """
        if entity_type == 'player':
            return self._compare_player_records(int(entity1), int(entity2))
        elif entity_type == 'team':
            return self._compare_team_records(entity1, entity2)
        else:
            raise ValueError(f"Invalid entity type: {entity_type}")
    
    def _compare_player_records(self, player1_id: int, player2_id: int) -> Dict[str, Any]:
        """Compare records between two players"""
        player1_records = self.get_player_records(player1_id)
        player2_records = self.get_player_records(player2_id)
        
        return {
            'player1': player1_records,
            'player2': player2_records,
            'comparison': {
                'goals': {
                    'player1': player1_records['career_totals'].get('goals', 0),
                    'player2': player2_records['career_totals'].get('goals', 0),
                    'difference': player1_records['career_totals'].get('goals', 0) - 
                                 player2_records['career_totals'].get('goals', 0)
                },
                'points': {
                    'player1': player1_records['career_totals'].get('points', 0),
                    'player2': player2_records['career_totals'].get('points', 0),
                    'difference': player1_records['career_totals'].get('points', 0) - 
                                 player2_records['career_totals'].get('points', 0)
                },
                'tournaments': {
                    'player1': player1_records['career_totals'].get('tournaments', 0),
                    'player2': player2_records['career_totals'].get('tournaments', 0),
                    'difference': player1_records['career_totals'].get('tournaments', 0) - 
                                 player2_records['career_totals'].get('tournaments', 0)
                }
            }
        }
    
    def _compare_team_records(self, team1_code: str, team2_code: str) -> Dict[str, Any]:
        """Compare records between two teams"""
        team1_records = self.get_team_records(team1_code)
        team2_records = self.get_team_records(team2_code)
        
        # Get head-to-head record
        h2h = self.repository.get_team_vs_opponent_record(team1_code, team2_code)
        
        return {
            'team1': team1_records,
            'team2': team2_records,
            'head_to_head': h2h,
            'comparison': {
                'all_time_wins': {
                    'team1': team1_records['all_time_record'].get('wins', 0),
                    'team2': team2_records['all_time_record'].get('wins', 0)
                },
                'championships': {
                    'team1': len(team1_records['tournament_wins']),
                    'team2': len(team2_records['tournament_wins'])
                },
                'goal_differential': {
                    'team1': team1_records['all_time_record'].get('goal_differential', 0),
                    'team2': team2_records['all_time_record'].get('goal_differential', 0)
                }
            }
        }