"""
Standings Service for IIHF World Championship Statistics
Handles all business logic related to team standings, rankings, and tiebreakers
"""

from typing import Dict, List, Optional, Tuple, Any
from models import Game, ChampionshipYear, TeamStats, db
from services.base import BaseService
from services.exceptions import ServiceError, ValidationError, NotFoundError
from app.repositories.core.standings_repository import StandingsRepository
import logging

logger = logging.getLogger(__name__)


class StandingsService(BaseService[Game]):
    """
    Service for standings-related business logic
    Manages group standings, overall standings, tiebreakers, and qualification scenarios
    """
    
    def __init__(self):
        super().__init__(Game)  # Standings are derived from games
        # self.repository = StandingsRepository()  # Repository für Datenbankzugriff
        self.repository = None  # Placeholder für Repository
    
    def get_group_standings(self, year_id: int, group: str) -> List[TeamStats]:
        """
        Get standings for a specific group with proper IIHF ranking
        
        Args:
            year_id: The championship year ID
            group: The group identifier (e.g., 'A', 'B')
            
        Returns:
            List of TeamStats objects sorted by IIHF ranking rules
            
        Raises:
            NotFoundError: If championship year not found
            ValidationError: If group doesn't exist
        """
        # Validate championship exists
        championship = ChampionshipYear.query.get(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        # Get group games
        group_games = self.repository.get_group_games(year_id, group)
        
        if not group_games:
            raise ValidationError(f"Group {group} not found in championship", "group")
        
        # Calculate standings
        standings = self._calculate_group_standings(group_games, group)
        
        # Apply IIHF tiebreaker rules
        standings = self._apply_iihf_tiebreakers(standings, group_games)
        
        return standings
    
    def get_all_groups_standings(self, year_id: int) -> Dict[str, List[TeamStats]]:
        """
        Get standings for all groups in a championship
        
        Args:
            year_id: The championship year ID
            
        Returns:
            Dictionary with group as key and standings as value
            
        Raises:
            NotFoundError: If championship year not found
        """
        # Validate championship exists
        championship = ChampionshipYear.query.get(year_id)
        if not championship:
            raise NotFoundError("Championship year", year_id)
        
        # Get all groups
        groups = self.repository.get_all_groups(year_id)
        
        all_standings = {}
        for group in groups:
            try:
                standings = self.get_group_standings(year_id, group)
                all_standings[group] = standings
            except Exception as e:
                logger.error(f"Error calculating standings for group {group}: {str(e)}")
                all_standings[group] = []
        
        return all_standings
    
    def _calculate_group_standings(self, games: List[Game], group: str) -> List[TeamStats]:
        """Calculate standings from group games"""
        # Extract teams
        teams = set()
        for game in games:
            if not self._is_placeholder_team(game.team1_code):
                teams.add(game.team1_code)
            if not self._is_placeholder_team(game.team2_code):
                teams.add(game.team2_code)
        
        # Calculate stats for each team
        standings = []
        for team_code in teams:
            team_games = [g for g in games if 
                         g.team1_code == team_code or g.team2_code == team_code]
            stats = self._calculate_team_stats(team_games, team_code, group)
            standings.append(stats)
        
        return standings
    
    def _calculate_team_stats(self, games: List[Game], team_code: str, group: str) -> TeamStats:
        """Calculate team statistics from games"""
        stats = TeamStats(name=team_code, group=group)
        
        for game in games:
            # Skip incomplete games
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
            
            # Update wins/losses by type
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
    
    def _apply_iihf_tiebreakers(self, standings: List[TeamStats], games: List[Game]) -> List[TeamStats]:
        """
        Apply IIHF tiebreaker rules to standings
        
        IIHF Tiebreaker Rules (in order):
        1. Points
        2. Head-to-head points
        3. Head-to-head goal difference
        4. Head-to-head goals scored
        5. Overall goal difference
        6. Overall goals scored
        7. Seeding coming into the tournament
        """
        # First sort by basic criteria
        standings.sort(key=lambda x: (
            -x.pts,      # Points (descending)
            -x.gd,       # Goal difference (descending)
            -x.gf        # Goals for (descending)
        ))
        
        # Handle ties by checking teams with same points
        i = 0
        while i < len(standings):
            # Find teams with same points
            tied_teams = [standings[i]]
            j = i + 1
            while j < len(standings) and standings[j].pts == standings[i].pts:
                tied_teams.append(standings[j])
                j += 1
            
            # If there are ties, apply head-to-head tiebreakers
            if len(tied_teams) > 1:
                tied_teams = self._apply_head_to_head_tiebreakers(tied_teams, games)
                # Replace in standings
                for k, team in enumerate(tied_teams):
                    standings[i + k] = team
            
            i = j
        
        # Assign final rankings
        for i, team_stats in enumerate(standings):
            team_stats.rank_in_group = i + 1
        
        return standings
    
    def _apply_head_to_head_tiebreakers(self, tied_teams: List[TeamStats], games: List[Game]) -> List[TeamStats]:
        """Apply head-to-head tiebreakers for tied teams"""
        # Calculate head-to-head records
        h2h_records = {}
        
        for team in tied_teams:
            h2h_records[team.name] = {
                'team': team,
                'h2h_points': 0,
                'h2h_gf': 0,
                'h2h_ga': 0,
                'h2h_games': 0
            }
        
        # Get head-to-head games
        team_codes = [t.name for t in tied_teams]
        for game in games:
            if (game.team1_code in team_codes and game.team2_code in team_codes and
                game.team1_score is not None and game.team2_score is not None):
                
                # Update h2h records
                h2h_records[game.team1_code]['h2h_games'] += 1
                h2h_records[game.team2_code]['h2h_games'] += 1
                
                h2h_records[game.team1_code]['h2h_gf'] += game.team1_score
                h2h_records[game.team1_code]['h2h_ga'] += game.team2_score
                h2h_records[game.team1_code]['h2h_points'] += game.team1_points
                
                h2h_records[game.team2_code]['h2h_gf'] += game.team2_score
                h2h_records[game.team2_code]['h2h_ga'] += game.team1_score
                h2h_records[game.team2_code]['h2h_points'] += game.team2_points
        
        # Sort by head-to-head criteria
        sorted_records = sorted(h2h_records.values(), key=lambda x: (
            -x['h2h_points'],                    # H2H points
            -(x['h2h_gf'] - x['h2h_ga']),       # H2H goal difference
            -x['h2h_gf'],                        # H2H goals for
            -x['team'].gd,                       # Overall goal difference
            -x['team'].gf                        # Overall goals for
        ))
        
        return [record['team'] for record in sorted_records]
    
    def _is_placeholder_team(self, team_code: str) -> bool:
        """Check if team code is a placeholder"""
        if not team_code:
            return True
        placeholders = ['A', 'B', 'W', 'L', 'Q', 'S']
        return (team_code[0] in placeholders and 
                len(team_code) > 1 and 
                team_code[1:].isdigit())
    
    def get_overall_standings(self, year_id: int) -> List[TeamStats]:
        """
        Get overall tournament standings (all teams combined)
        
        Args:
            year_id: The championship year ID
            
        Returns:
            List of all teams sorted by overall performance
        """
        # Get all groups standings
        all_groups = self.get_all_groups_standings(year_id)
        
        # Combine all teams
        all_teams = []
        for group, standings in all_groups.items():
            all_teams.extend(standings)
        
        # Sort by overall criteria
        all_teams.sort(key=lambda x: (
            -x.pts,              # Points
            -x.gd,               # Goal difference
            -x.gf,               # Goals for
            x.rank_in_group      # Better group ranking
        ))
        
        return all_teams
    
    def get_playoff_qualifiers(self, year_id: int) -> Dict[str, List[TeamStats]]:
        """
        Determine playoff qualifiers based on standings
        
        Args:
            year_id: The championship year ID
            
        Returns:
            Dictionary with qualification status
        """
        # Get all group standings
        all_groups = self.get_all_groups_standings(year_id)
        
        qualifiers = {
            'direct_qualifiers': [],      # Top 2 from each group
            'best_third_places': [],      # Best 3rd place teams (if applicable)
            'eliminated': []              # Teams not qualifying
        }
        
        third_place_teams = []
        
        for group, standings in all_groups.items():
            if len(standings) >= 2:
                # Top 2 qualify directly
                qualifiers['direct_qualifiers'].extend(standings[:2])
                
                # Collect 3rd place teams
                if len(standings) >= 3:
                    third_place_teams.append(standings[2])
                
                # Rest are eliminated
                if len(standings) > 3:
                    qualifiers['eliminated'].extend(standings[3:])
        
        # Determine best 3rd place teams (typically top 2 of 3rd place teams qualify)
        third_place_teams.sort(key=lambda x: (-x.pts, -x.gd, -x.gf))
        
        # Assuming top 2 third-place teams qualify (adjust based on tournament format)
        if len(third_place_teams) >= 2:
            qualifiers['best_third_places'] = third_place_teams[:2]
            qualifiers['eliminated'].extend(third_place_teams[2:])
        else:
            qualifiers['best_third_places'] = third_place_teams
        
        return qualifiers
    
    def calculate_scenarios(self, year_id: int, team_code: str) -> Dict[str, Any]:
        """
        Calculate qualification scenarios for a team
        
        Args:
            year_id: The championship year ID
            team_code: The team to calculate scenarios for
            
        Returns:
            Dictionary with qualification scenarios
        """
        # Get current standings
        all_groups = self.get_all_groups_standings(year_id)
        
        # Find team's group and position
        team_group = None
        team_position = None
        team_stats = None
        
        for group, standings in all_groups.items():
            for i, stats in enumerate(standings):
                if stats.name == team_code:
                    team_group = group
                    team_position = i + 1
                    team_stats = stats
                    break
        
        if not team_stats:
            raise NotFoundError(f"Team {team_code}", None)
        
        # Get remaining games
        remaining_games = self.repository.get_team_remaining_games(year_id, team_code)
        
        scenarios = {
            'team': team_code,
            'current_position': team_position,
            'current_points': team_stats.pts,
            'remaining_games': len(remaining_games),
            'max_possible_points': team_stats.pts + (len(remaining_games) * 3),
            'scenarios': []
        }
        
        # Calculate different scenarios
        if team_position <= 2:
            scenarios['scenarios'].append({
                'type': 'maintain_direct_qualification',
                'description': 'Team is currently in direct qualification position',
                'requirements': self._calculate_maintain_position_requirements(
                    team_stats, all_groups[team_group], remaining_games
                )
            })
        elif team_position == 3:
            scenarios['scenarios'].append({
                'type': 'improve_to_direct_qualification',
                'description': 'Team needs to move up to top 2',
                'requirements': self._calculate_improvement_requirements(
                    team_stats, all_groups[team_group], remaining_games, 2
                )
            })
            scenarios['scenarios'].append({
                'type': 'best_third_place',
                'description': 'Qualify as best 3rd place team',
                'requirements': self._calculate_best_third_requirements(
                    team_stats, all_groups, remaining_games
                )
            })
        else:
            scenarios['scenarios'].append({
                'type': 'reach_playoffs',
                'description': 'Team needs significant improvement to reach playoffs',
                'requirements': self._calculate_improvement_requirements(
                    team_stats, all_groups[team_group], remaining_games, 3
                )
            })
        
        return scenarios
    
    def _calculate_maintain_position_requirements(self, team_stats: TeamStats, 
                                                 group_standings: List[TeamStats],
                                                 remaining_games: List[Game]) -> Dict[str, Any]:
        """Calculate requirements to maintain current position"""
        # Find teams that could overtake
        threats = []
        for stats in group_standings:
            if stats.rank_in_group > team_stats.rank_in_group:
                max_points = stats.pts + (self._count_team_remaining_games(stats.name, remaining_games) * 3)
                if max_points >= team_stats.pts:
                    threats.append({
                        'team': stats.name,
                        'current_points': stats.pts,
                        'max_points': max_points,
                        'games_remaining': self._count_team_remaining_games(stats.name, remaining_games)
                    })
        
        return {
            'min_points_needed': team_stats.pts,
            'threats': threats,
            'safe_with': f"Current points may be enough if threats don't win all games"
        }
    
    def _calculate_improvement_requirements(self, team_stats: TeamStats,
                                          group_standings: List[TeamStats],
                                          remaining_games: List[Game],
                                          target_position: int) -> Dict[str, Any]:
        """Calculate requirements to improve to target position"""
        # Find teams to overtake
        teams_to_overtake = [s for s in group_standings if s.rank_in_group <= target_position]
        
        requirements = []
        for target in teams_to_overtake:
            points_gap = target.pts - team_stats.pts
            their_remaining = self._count_team_remaining_games(target.name, remaining_games)
            
            requirements.append({
                'overtake': target.name,
                'current_gap': points_gap,
                'their_max_points': target.pts + (their_remaining * 3),
                'scenario': self._calculate_overtake_scenario(team_stats, target, remaining_games)
            })
        
        return {
            'target_position': target_position,
            'teams_to_overtake': requirements
        }
    
    def _calculate_best_third_requirements(self, team_stats: TeamStats,
                                          all_groups: Dict[str, List[TeamStats]],
                                          remaining_games: List[Game]) -> Dict[str, Any]:
        """Calculate requirements to qualify as best 3rd place"""
        # Get all 3rd place teams
        third_place_teams = []
        for group, standings in all_groups.items():
            if len(standings) >= 3:
                third_place_teams.append(standings[2])
        
        # Sort by points
        third_place_teams.sort(key=lambda x: (-x.pts, -x.gd, -x.gf))
        
        # Calculate position among 3rd place teams
        current_3rd_rank = None
        for i, team in enumerate(third_place_teams):
            if team.name == team_stats.name:
                current_3rd_rank = i + 1
                break
        
        return {
            'current_3rd_place_rank': current_3rd_rank,
            'total_3rd_place_teams': len(third_place_teams),
            'qualifying_positions': 2,  # Usually top 2 3rd place teams qualify
            'current_points': team_stats.pts,
            'points_of_2nd_best_3rd': third_place_teams[1].pts if len(third_place_teams) > 1 else 0
        }
    
    def _count_team_remaining_games(self, team_code: str, games: List[Game]) -> int:
        """Count remaining games for a team"""
        count = 0
        for game in games:
            if ((game.team1_code == team_code or game.team2_code == team_code) and
                game.team1_score is None):
                count += 1
        return count
    
    def _calculate_overtake_scenario(self, team_stats: TeamStats, target: TeamStats,
                                   remaining_games: List[Game]) -> str:
        """Calculate specific scenario to overtake another team"""
        points_gap = target.pts - team_stats.pts
        our_remaining = self._count_team_remaining_games(team_stats.name, remaining_games)
        
        if points_gap <= 0:
            return "Already ahead on points"
        elif points_gap <= 3:
            return "Need to win 1 more game than opponent"
        elif points_gap <= our_remaining * 3:
            wins_needed = (points_gap + 2) // 3  # Round up
            return f"Need to win at least {wins_needed} games"
        else:
            return "Mathematically impossible even with all wins"
    
    def get_live_standings(self, year_id: int) -> Dict[str, Any]:
        """
        Get live standings with current game states
        
        Args:
            year_id: The championship year ID
            
        Returns:
            Dictionary with live standings and ongoing games
        """
        # Get regular standings
        all_groups = self.get_all_groups_standings(year_id)
        
        # Get ongoing games
        ongoing_games = self.repository.get_ongoing_games(year_id)
        
        return {
            'standings': all_groups,
            'ongoing_games': ongoing_games,
            'last_updated': self.repository.get_last_update_time(year_id)
        }