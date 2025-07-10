import re
import os
from typing import Dict, List, Tuple, Set, Optional

from models import Game, ChampionshipYear
from constants import PLAYOFF_ROUNDS


def is_code_final(team_code: Optional[str]) -> bool:
    """Checks if a team code is a definitive 3-letter country code."""
    if not team_code:
        return False
    # Standard IIHF codes are 3 letters, all uppercase.
    return len(team_code) == 3 and team_code.isalpha() and team_code.isupper()


def get_resolved_team_code(
    placeholder_code: str,
    playoff_team_map: Dict[str, str],
    all_games_for_year_map: Dict[int, Game]
) -> str:
    """
    Resolves a team placeholder (e.g., 'A1', 'W(57)') to an actual team code.
    Iteratively resolves until a final 3-letter code is found or no more resolution is possible.
    Returns the resolved team code (or the original placeholder if unresolvable).
    """
    if not placeholder_code: # Handle empty or None placeholder
        return "" 
    if is_code_final(placeholder_code):
        return placeholder_code

    current_code = placeholder_code
    visited_codes: Set[str] = {current_code} # For cycle detection during this resolution attempt

    for _ in range(10): # Max resolution depth for a single call
        if is_code_final(current_code):
            return current_code

        # Attempt 1: Direct lookup in the playoff_team_map
        # This covers A1, B2, and potentially already resolved W(X), L(X)
        resolved_from_map = playoff_team_map.get(current_code)
        
        if resolved_from_map is not None:
            if is_code_final(resolved_from_map): # Successfully resolved via map
                return resolved_from_map
            
            # If map points to itself (e.g. W(X) -> W(X) and W(X) is not yet resolved)
            # or to another placeholder, update current_code and continue loop.
            if resolved_from_map == current_code and not re.match(r"^[WL]\((\d+)\)$", current_code):
                 # If it's a simple placeholder like "A1" mapping to "A1", it's unresolvable by map.
                 # If it's W(X) mapping to W(X), we might try game lookup next.
                break # Stuck on a simple placeholder, exit loop for this path

            current_code = resolved_from_map # Follow the chain in the map
        
        # Attempt 2: If current_code is W(X) or L(X) (either original or from map), try game result
        # This is only tried if direct map lookup didn't yield a *final* code.
        elif re.match(r"^[WL]\((\d+)\)$", current_code): # current_code could be like "W(57)"
            match = re.match(r"^[WL]\((\d+)\)$", current_code)
            prefix = match.group(0)[0] # W or L
            game_num = int(match.group(1))

            game = all_games_for_year_map.get(game_num)
            if game and game.team1_score is not None and game.team2_score is not None:
                
                # Critical: Avoid immediate re-resolution of the exact same W(X)/L(X) placeholder 
                # if it's one of the game's *original* team codes.
                # This is to prevent simple infinite recursion if W(57) is team1_code of game 57.
                # The _build_playoff_team_map_for_year handles iterative building of the map.
                if game.team1_code == current_code or game.team2_code == current_code:
                    break # Cannot resolve W/L of a game using itself directly in this call

                team1_resolved_participant = get_resolved_team_code(game.team1_code, playoff_team_map, all_games_for_year_map)
                team2_resolved_participant = get_resolved_team_code(game.team2_code, playoff_team_map, all_games_for_year_map)

                if is_code_final(team1_resolved_participant) and is_code_final(team2_resolved_participant):
                    winner_code = team1_resolved_participant if game.team1_score > game.team2_score else team2_resolved_participant
                    loser_code = team2_resolved_participant if game.team1_score > game.team2_score else team1_resolved_participant
                    
                    # This is the potential resolution from game outcome
                    current_code = winner_code if prefix == 'W' else loser_code
                    # Do NOT update playoff_team_map here. This function is for resolution, not map building.
                    # If current_code became final, next loop iteration will return it.
                else:
                    # Participants of the game are not yet fully resolved to final codes.
                    # Cannot determine W/L of this game definitively yet through this path.
                    break # Exit loop, return current (likely placeholder) state of current_code
            else:
                # Game not found, or no score, cannot resolve W/L from game.
                break # Exit loop
        else:
            # Not in map (resolved_from_map is None), and not W/L pattern.
            # This means it's an unresolvable placeholder (e.g. "A5" if group only has 4 teams) or unknown format.
            break # Exit loop, current_code is the placeholder itself

        # Cycle detection for the current resolution path
        if current_code in visited_codes:
            return placeholder_code # Return original to break cycle
        visited_codes.add(current_code)

    # If loop finishes (e.g. max iterations or break), return current_code if final, else original placeholder
    return current_code if is_code_final(current_code) else placeholder_code


def resolve_game_participants(
    game_to_resolve: Game, 
    year_obj: ChampionshipYear, 
    all_games_in_year: List[Game]
) -> Tuple[str, str]:
    """
    Main public function to resolve team codes for a given game.
    Returns a tuple of (resolved_team1_code, resolved_team2_code).
    """
    from .standings import _calculate_basic_prelim_standings
    from .playoff_mapping import _build_playoff_team_map_for_year
    from constants import PRELIM_ROUNDS
    
    # 1. Filter preliminary games for the year that have final team codes and scores.
    # _calculate_basic_prelim_standings itself filters by PRELIM_ROUNDS and scores,
    # and also by is_code_final for participants.
    prelim_games_for_standings_calc = [
        g for g in all_games_in_year
        if g.round in PRELIM_ROUNDS and \
           is_code_final(g.team1_code) and \
           is_code_final(g.team2_code) and \
           g.team1_score is not None and g.team2_score is not None
    ]

    # 2. Calculate basic preliminary standings (team_code -> TeamStats obj)
    prelim_standings_map = _calculate_basic_prelim_standings(prelim_games_for_standings_calc)

    # 3. Group these standings by group name for _build_playoff_team_map_for_year
    # The list of TeamStats for each group should be sorted by rank_in_group.
    prelim_standings_by_group: Dict[str, List] = {}
    for ts_obj in prelim_standings_map.values(): # ts_obj is TeamStats
        group_key = ts_obj.group if ts_obj.group else "UnknownGroup" 
        if group_key not in prelim_standings_by_group:
            prelim_standings_by_group[group_key] = []
        prelim_standings_by_group[group_key].append(ts_obj)
    
    # Sort teams within each group by rank_in_group (which was calculated by _calculate_basic_prelim_standings)
    for group_name in prelim_standings_by_group:
        prelim_standings_by_group[group_name].sort(key=lambda x: x.rank_in_group)

    # 4. Build the playoff team map (placeholder -> actual team code)
    # _build_playoff_team_map_for_year needs all games to resolve W(X), L(X) from playoff results
    playoff_team_map = _build_playoff_team_map_for_year(
        year_obj,
        all_games_in_year, 
        prelim_standings_by_group # This is Dict[group_name, List_of_TeamStats_sorted_by_rank]
    )

    # 5. Create a map of game_number to Game object for quick lookups by get_resolved_team_code
    all_games_for_year_map: Dict[int, Game] = {
        g.game_number: g for g in all_games_in_year if g.game_number is not None
    }

    # 6. Resolve participants for the game_to_resolve
    # Handle cases where original codes might be None (though not typical for team codes in DB)
    team1_to_resolve = game_to_resolve.team1_code if game_to_resolve.team1_code is not None else ""
    team2_to_resolve = game_to_resolve.team2_code if game_to_resolve.team2_code is not None else ""

    resolved_team1 = get_resolved_team_code(
        team1_to_resolve,
        playoff_team_map,
        all_games_for_year_map
    )
    resolved_team2 = get_resolved_team_code(
        team2_to_resolve,
        playoff_team_map,
        all_games_for_year_map
    )

    return resolved_team1, resolved_team2


def resolve_fixture_path_local(relative_path, current_app):
    """
    Local version of resolve_fixture_path to avoid circular imports.
    Converts a relative fixture path to an absolute path.
    """
    if not relative_path:
        return None
    
    if relative_path.startswith('fixtures/'):
        # Remove 'fixtures/' prefix and look in BASE_DIR/fixtures/
        filename = relative_path[9:]  # Remove 'fixtures/' prefix
        absolute_path = os.path.join(current_app.config['BASE_DIR'], 'fixtures', filename)
    else:
        # Look in upload folder
        absolute_path = os.path.join(current_app.config['UPLOAD_FOLDER'], relative_path)
    
    return absolute_path