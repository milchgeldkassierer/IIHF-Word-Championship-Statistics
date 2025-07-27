"""
StandingsCalculator Adapter - Adapts the IIHF codebase models to work with StandingsCalculator
This provides a clean interface for standings calculation logic
"""

from typing import Dict
from models import TeamStats, Game
from services.standings_calculator import StandingsCalculator as BaseCalculator


class StandingsCalculator:
    """
    Adapter for StandingsCalculator that works with IIHF codebase models
    """
    
    def __init__(self):
        """Initialize the adapter"""
        # We'll use composition instead of inheritance for clarity
        pass
    
    def update_team_stats(self, team_stats: Dict[str, TeamStats], game: Game) -> None:
        """
        Update team statistics based on a game result
        
        Args:
            team_stats: Dictionary mapping team codes to TeamStats objects
            game: Game object with the match result
        """
        if game.team1_score is None or game.team2_score is None:
            return
        
        # Ensure teams exist in stats dictionary
        if game.team1_code not in team_stats:
            team_stats[game.team1_code] = TeamStats(name=game.team1_code, group=game.group or "N/A")
        if game.team2_code not in team_stats:
            team_stats[game.team2_code] = TeamStats(name=game.team2_code, group=game.group or "N/A")
        
        # Update group if it was N/A and now we have one
        if team_stats[game.team1_code].group == "N/A" and game.group:
            team_stats[game.team1_code].group = game.group
        if team_stats[game.team2_code].group == "N/A" and game.group:
            team_stats[game.team2_code].group = game.group
        
        # Get team stats objects
        team1_stats = team_stats[game.team1_code]
        team2_stats = team_stats[game.team2_code]
        
        # Update games played
        team1_stats.gp += 1
        team2_stats.gp += 1
        
        # Update goals for/against
        team1_stats.gf += game.team1_score
        team1_stats.ga += game.team2_score
        team2_stats.gf += game.team2_score
        team2_stats.ga += game.team1_score
        
        # Determine winner and update points/records
        if game.result_type == 'REG':
            if game.team1_score > game.team2_score:
                team1_stats.w += 1
                team1_stats.pts += 3
                team2_stats.l += 1
            else:
                team2_stats.w += 1
                team2_stats.pts += 3
                team1_stats.l += 1
        elif game.result_type == 'OT':
            if game.team1_score > game.team2_score:
                team1_stats.otw += 1
                team1_stats.pts += 2
                team2_stats.otl += 1
                team2_stats.pts += 1
            else:
                team2_stats.otw += 1
                team2_stats.pts += 2
                team1_stats.otl += 1
                team1_stats.pts += 1
        elif game.result_type == 'SO':
            if game.team1_score > game.team2_score:
                team1_stats.sow += 1
                team1_stats.pts += 2
                team2_stats.sol += 1
                team2_stats.pts += 1
            else:
                team2_stats.sow += 1
                team2_stats.pts += 2
                team1_stats.sol += 1
                team1_stats.pts += 1
    
    def calculate_standings_from_games(self, games: list[Game], group_filter: str = None) -> Dict[str, TeamStats]:
        """
        Calculate complete standings from a list of games
        
        Args:
            games: List of Game objects
            group_filter: Optional group to filter by
            
        Returns:
            Dictionary mapping team codes to TeamStats objects
        """
        standings = {}
        
        for game in games:
            # Skip games without scores
            if game.team1_score is None or game.team2_score is None:
                continue
            
            # Apply group filter if specified
            if group_filter and game.group != group_filter:
                continue
            
            # Update stats for this game
            self.update_team_stats(standings, game)
        
        return standings