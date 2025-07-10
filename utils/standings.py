from typing import Dict, List
from collections import defaultdict

from models import Game, TeamStats
from constants import PRELIM_ROUNDS, MAX_PRELIM_GAMES_PER_TEAM
from .team_resolution import is_code_final


def _calculate_basic_prelim_standings(prelim_games_for_year: List[Game]) -> Dict[str, TeamStats]:
    """
    Calculates simplified standings for preliminary round games of a single year.
    Focuses on points, goal difference, goals for, and rank_in_group for ranking.
    Returns a dictionary mapping team codes to their TeamStats objects.
    """
    standings: Dict[str, TeamStats] = {}

    for game in prelim_games_for_year:
        if game.round not in PRELIM_ROUNDS or game.team1_score is None or game.team2_score is None:
            continue

        # Ensure teams are initialized with their group
        # Only process games where both participants are final team codes
        if not is_code_final(game.team1_code) or not is_code_final(game.team2_code):
            continue # Should not happen for prelim games used for standings
            
        current_game_group = game.group # Assuming game object has group info for prelims

        if game.team1_code not in standings:
            # Ensure group is a string, default if None for safety, though expected from fixture
            standings[game.team1_code] = TeamStats(name=game.team1_code, group=current_game_group or "N/A")
        # Update group if it was N/A and now we have one
        elif standings[game.team1_code].group == "N/A" and current_game_group is not None:
             standings[game.team1_code].group = current_game_group


        if game.team2_code not in standings:
            standings[game.team2_code] = TeamStats(name=game.team2_code, group=current_game_group or "N/A")
        elif standings[game.team2_code].group == "N/A" and current_game_group is not None:
            standings[game.team2_code].group = current_game_group


        team1_stats = standings[game.team1_code]
        team2_stats = standings[game.team2_code]

        team1_stats.gp += 1
        team2_stats.gp += 1
        team1_stats.gf += game.team1_score
        team1_stats.ga += game.team2_score
        team2_stats.gf += game.team2_score
        team2_stats.ga += game.team1_score

        if game.result_type == 'REG':
            if game.team1_score > game.team2_score:
                team1_stats.w += 1; team1_stats.pts += 3
                team2_stats.l += 1
            else:
                team2_stats.w += 1; team2_stats.pts += 3
                team1_stats.l += 1
        elif game.result_type == 'OT':
            if game.team1_score > game.team2_score:
                team1_stats.otw += 1; team1_stats.pts += 2
                team2_stats.otl += 1; team2_stats.pts += 1
            else:
                team2_stats.otw += 1; team2_stats.pts += 2
                team1_stats.otl += 1; team1_stats.pts += 1
        elif game.result_type == 'SO': # Shootout
            if game.team1_score > game.team2_score:
                team1_stats.sow += 1; team1_stats.pts += 2
                team2_stats.sol += 1; team2_stats.pts += 1
            else:
                team2_stats.sow += 1; team2_stats.pts += 2
                team1_stats.sol += 1; team1_stats.pts += 1
    
    # Calculate rank_in_group with head-to-head comparison
    grouped_standings_for_ranking: Dict[str, List[TeamStats]] = {}
    for ts_code, ts_obj in standings.items():
        # Ensure all objects have a group; default if necessary
        group_key = ts_obj.group if ts_obj.group else "UnknownGroup" 
        if group_key not in grouped_standings_for_ranking:
            grouped_standings_for_ranking[group_key] = []
        grouped_standings_for_ranking[group_key].append(ts_obj)

    for group_name, group_list in grouped_standings_for_ranking.items():
        # Sort by pts (desc), head-to-head comparison, gd (desc), gf (desc)
        group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        
        # Apply head-to-head tiebreaker for teams with equal points
        group_list = _apply_head_to_head_tiebreaker(group_list, prelim_games_for_year)
        
        for i, ts_in_group in enumerate(group_list):
            ts_in_group.rank_in_group = i + 1
            # The original standings dict values are the same objects, so rank is updated.

    return standings


def _apply_head_to_head_tiebreaker(teams_list: List[TeamStats], all_games: List[Game]) -> List[TeamStats]:
    """
    Apply head-to-head tiebreaker for teams with equal points.
    Returns the sorted list with head-to-head results considered.
    """
    if len(teams_list) <= 1:
        return teams_list
    
    # Group teams by points
    teams_by_points = {}
    for team in teams_list:
        points = team.pts
        if points not in teams_by_points:
            teams_by_points[points] = []
        teams_by_points[points].append(team)
    
    result = []
    
    # Process each point group separately
    for points in sorted(teams_by_points.keys(), reverse=True):
        point_group = teams_by_points[points]
        
        if len(point_group) == 1:
            result.extend(point_group)
        else:
            # Apply head-to-head tiebreaker within this point group
            sorted_group = _sort_teams_by_head_to_head(point_group, all_games)
            result.extend(sorted_group)
    
    return result


def _sort_teams_by_head_to_head(tied_teams: List[TeamStats], all_games: List[Game]) -> List[TeamStats]:
    """
    Sort teams that are tied on points by head-to-head results following updated IIHF rules.
    
    Updated Tie-breaking procedure:
    - For 2 teams: Direct game between them is decisive ONLY if it has been played
      If direct game not played: Use overall goal difference and goals for
    - For 3+ teams tied: 
      Head-to-head tiebreaker ONLY applies if ALL teams have played ALL their 7 preliminary games
      If not all games played: Use overall goal difference and goals for
    """
    if len(tied_teams) <= 1:
        return tied_teams
    
    # Check if we have exactly 2 teams or more than 2 teams
    if len(tied_teams) == 2:
        return _sort_two_teams_by_head_to_head(tied_teams, all_games)
    else:
        return _sort_multiple_teams_by_head_to_head(tied_teams, all_games)


def _sort_two_teams_by_head_to_head(tied_teams: List[TeamStats], all_games: List[Game]) -> List[TeamStats]:
    """
    Sort exactly 2 teams that are tied on points.
    Uses head-to-head if the direct game has been played, otherwise overall stats.
    """
    team1, team2 = tied_teams[0], tied_teams[1]
    
    # Find head-to-head games between these two teams
    head_to_head_games = []
    for game in all_games:
        if (game.team1_code == team1.name and game.team2_code == team2.name) or \
           (game.team1_code == team2.name and game.team2_code == team1.name):
            if (game.team1_score is not None and game.team2_score is not None and
                game.round in PRELIM_ROUNDS):
                head_to_head_games.append(game)
    
    # If direct game has been played, use head-to-head result
    if head_to_head_games:
        # Calculate head-to-head stats
        h2h_stats = {
            team1.name: {'points': 0, 'gf': 0, 'ga': 0},
            team2.name: {'points': 0, 'gf': 0, 'ga': 0}
        }
        
        for game in head_to_head_games:
            team1_h2h = h2h_stats[game.team1_code] if game.team1_code in h2h_stats else h2h_stats[game.team2_code]
            team2_h2h = h2h_stats[game.team2_code] if game.team2_code in h2h_stats else h2h_stats[game.team1_code]
            
            # Determine which team is which in the game
            if game.team1_code == team1.name:
                t1_score, t2_score = game.team1_score, game.team2_score
                t1_h2h, t2_h2h = h2h_stats[team1.name], h2h_stats[team2.name]
            else:
                t1_score, t2_score = game.team2_score, game.team1_score
                t1_h2h, t2_h2h = h2h_stats[team1.name], h2h_stats[team2.name]
            
            t1_h2h['gf'] += t1_score
            t1_h2h['ga'] += t2_score
            t2_h2h['gf'] += t2_score
            t2_h2h['ga'] += t1_score
            
            # Award points based on result
            if game.result_type == 'REG':
                if t1_score > t2_score:
                    t1_h2h['points'] += 3
                else:
                    t2_h2h['points'] += 3
            elif game.result_type in ['OT', 'SO']:
                if t1_score > t2_score:
                    t1_h2h['points'] += 2
                    t2_h2h['points'] += 1
                else:
                    t2_h2h['points'] += 2
                    t1_h2h['points'] += 1
        
        # Sort by head-to-head results
        team_list = [(team1, h2h_stats[team1.name]), (team2, h2h_stats[team2.name])]
        team_list.sort(key=lambda x: (
            x[1]['points'],                    # H2H points
            x[1]['gf'] - x[1]['ga'],          # H2H goal difference
            x[1]['gf'],                       # H2H goals for
            x[0].gd,                          # Overall goal difference
            x[0].gf                           # Overall goals for
        ), reverse=True)
        
        return [team_obj for team_obj, _ in team_list]
    
    # No direct game played, use overall stats
    return sorted(tied_teams, key=lambda x: (x.gd, x.gf), reverse=True)


def _sort_multiple_teams_by_head_to_head(tied_teams: List[TeamStats], all_games: List[Game]) -> List[TeamStats]:
    """
    Sort 3+ teams that are tied on points.
    Uses head-to-head only if ALL teams have played ALL their 7 preliminary games.
    """
    # Check if all teams have played all their preliminary games
    all_games_completed = all(team.gp >= MAX_PRELIM_GAMES_PER_TEAM for team in tied_teams)
    
    if not all_games_completed:
        # Not all games played, use overall stats
        return sorted(tied_teams, key=lambda x: (x.gd, x.gf), reverse=True)
    
    # All games completed, use head-to-head tiebreaker
    team_names = {team.name for team in tied_teams}
    head_to_head_games = []
    
    for game in all_games:
        if (game.team1_code in team_names and game.team2_code in team_names and 
            game.team1_score is not None and game.team2_score is not None and
            game.round in PRELIM_ROUNDS):
            head_to_head_games.append(game)
    
    # Calculate head-to-head records
    h2h_stats = {}
    for team in tied_teams:
        h2h_stats[team.name] = {
            'points': 0,
            'gf': 0,
            'ga': 0,
            'team_obj': team
        }
    
    for game in head_to_head_games:
        team1_h2h = h2h_stats[game.team1_code]
        team2_h2h = h2h_stats[game.team2_code]
        
        team1_h2h['gf'] += game.team1_score
        team1_h2h['ga'] += game.team2_score
        team2_h2h['gf'] += game.team2_score
        team2_h2h['ga'] += game.team1_score
        
        # Award points based on result (IIHF 3-point system)
        if game.result_type == 'REG':
            if game.team1_score > game.team2_score:
                team1_h2h['points'] += 3
            else:
                team2_h2h['points'] += 3
        elif game.result_type in ['OT', 'SO']:
            if game.team1_score > game.team2_score:
                team1_h2h['points'] += 2
                team2_h2h['points'] += 1
            else:
                team2_h2h['points'] += 2
                team1_h2h['points'] += 1
    
    # Sort by head-to-head criteria
    h2h_list = list(h2h_stats.values())
    h2h_list.sort(key=lambda x: (
        x['points'],                # Head-to-head points
        x['gf'] - x['ga'],         # Head-to-head goal difference
        x['gf'],                   # Head-to-head goals for
        x['team_obj'].gd,          # Overall goal difference
        x['team_obj'].gf           # Overall goals for
    ), reverse=True)
    
    return [h2h['team_obj'] for h2h in h2h_list]