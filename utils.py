import re
import os
import json
from typing import Dict, List, Tuple, Set, Optional

# Assuming models.py and constants.py are accessible in the Python path
from models import Game, ChampionshipYear, TeamStats
from constants import PRELIM_ROUNDS, PLAYOFF_ROUNDS, QF_GAME_NUMBERS_BY_YEAR, SF_GAME_NUMBERS_BY_YEAR, FINAL_BRONZE_GAME_NUMBERS_BY_YEAR

# Helper to check if a team code is a final, resolved code (e.g., "USA", "SWE")
def is_code_final(team_code: Optional[str]) -> bool:
    """Checks if a team code is a definitive 3-letter country code."""
    if not team_code:
        return False
    # Standard IIHF codes are 3 letters, all uppercase.
    return len(team_code) == 3 and team_code.isalpha() and team_code.isupper()

# --- Placeholder for _calculate_basic_prelim_standings ---
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
    
    # Calculate rank_in_group
    grouped_standings_for_ranking: Dict[str, List[TeamStats]] = {}
    for ts_code, ts_obj in standings.items():
        # Ensure all objects have a group; default if necessary
        group_key = ts_obj.group if ts_obj.group else "UnknownGroup" 
        if group_key not in grouped_standings_for_ranking:
            grouped_standings_for_ranking[group_key] = []
        grouped_standings_for_ranking[group_key].append(ts_obj)

    for group_name, group_list in grouped_standings_for_ranking.items():
        # Sort by pts (desc), gd (desc), gf (desc)
        # TeamStats has a gd @property
        group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        for i, ts_in_group in enumerate(group_list):
            ts_in_group.rank_in_group = i + 1
            # The original standings dict values are the same objects, so rank is updated.

    return standings

# --- Placeholder for _build_playoff_team_map_for_year ---
def _build_playoff_team_map_for_year(
    year_obj: ChampionshipYear,
    all_games_for_year: List[Game],
    prelim_standings_by_group: Dict[str, List[TeamStats]] # Grouped and ranked
) -> Dict[str, str]:
    """
    Builds a map from playoff placeholders (e.g., 'A1', 'W(57)') to actual team codes.
    Returns the fully populated playoff_team_map for the year.
    """
    playoff_team_map: Dict[str, str] = {}
    all_games_map_by_number: Dict[int, Game] = {g.game_number: g for g in all_games_for_year if g.game_number is not None}

    qf_game_numbers: List[int] = []
    sf_game_numbers: List[int] = []
    # final_bronze_game_numbers: List[int] = [] # Not directly used for map construction from W/L
    host_team_codes: List[str] = []

    if year_obj.fixture_path and os.path.exists(year_obj.fixture_path):
        try:
            with open(year_obj.fixture_path, 'r', encoding='utf-8') as f:
                fixture_data = json.load(f)
            # Use .get for game numbers list, falling back to constants if key missing or empty
            qf_game_numbers = fixture_data.get("qf_game_numbers") or QF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])
            sf_game_numbers = fixture_data.get("sf_game_numbers") or SF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])
            host_team_codes = fixture_data.get("host_teams", []) 
        except (json.JSONDecodeError, OSError) as e:
            # print(f"Warning: Could not load or parse fixture {year_obj.fixture_path}: {e}") # Consider logging
            qf_game_numbers = QF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])
            sf_game_numbers = SF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])
    else:
        qf_game_numbers = QF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])
        sf_game_numbers = SF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])

    # 1. Initial population from prelim standings (A1, B2, etc.)
    # prelim_standings_by_group is Dict[str (group_name), List[TeamStats (sorted by rank)]
    for group_name, group_teams_stats_list in prelim_standings_by_group.items():
        for team_stat in group_teams_stats_list: # Assumes list is sorted by rank_in_group from _calculate_basic_prelim_standings
            # rank_in_group is 1-indexed
            placeholder = f"{team_stat.group}{team_stat.rank_in_group}" 
            playoff_team_map[placeholder] = team_stat.name
            
            if host_team_codes and team_stat.name in host_team_codes:
                # This assumes host placeholders like "H1", "H2" might be used in game data.
                # The rank is specific to its group. If overall host rank needed, it's different.
                host_placeholder_group_rank = f"H{team_stat.rank_in_group}" 
                playoff_team_map[host_placeholder_group_rank] = team_stat.name


    # 2. Iteratively resolve W(game_num) and L(game_num)
    max_passes = 10 
    passes = 0
    changed_in_pass = True

    while changed_in_pass and passes < max_passes:
        changed_in_pass = False
        passes += 1

        # First, try to resolve existing non-final values in the map
        for placeholder_key, mapped_code in list(playoff_team_map.items()):
            if not is_code_final(mapped_code):
                # get_resolved_team_code is still a placeholder itself, this won't do much yet
                resolved_code = get_resolved_team_code(mapped_code, playoff_team_map, all_games_map_by_number)
                if resolved_code != mapped_code and is_code_final(resolved_code):
                    playoff_team_map[placeholder_key] = resolved_code
                    changed_in_pass = True
        
        # Then, determine W/L for playoff games and update map
        for game in all_games_for_year:
            if game.round in PLAYOFF_ROUNDS and game.game_number is not None and \
               game.team1_score is not None and game.team2_score is not None:
                
                # Resolve game participants first. Critical for W(QF1) vs W(QF2) type games.
                # Again, this relies on get_resolved_team_code.
                r_team1 = get_resolved_team_code(game.team1_code, playoff_team_map, all_games_map_by_number)
                r_team2 = get_resolved_team_code(game.team2_code, playoff_team_map, all_games_map_by_number)

                if not is_code_final(r_team1) or not is_code_final(r_team2):
                    # If participants of this game aren't resolved yet, can't determine W/L for map.
                    continue 

                winner_actual_code = r_team1 if game.team1_score > game.team2_score else r_team2
                loser_actual_code = r_team2 if game.team1_score > game.team2_score else r_team1
                
                w_placeholder = f"W({game.game_number})"
                l_placeholder = f"L({game.game_number})"

                if playoff_team_map.get(w_placeholder) != winner_actual_code:
                    playoff_team_map[w_placeholder] = winner_actual_code
                    changed_in_pass = True
                
                if playoff_team_map.get(l_placeholder) != loser_actual_code:
                    playoff_team_map[l_placeholder] = loser_actual_code
                    changed_in_pass = True
    
    # 3. SF Seeding Logic (Post-QF resolution)
    # This part is for specific reseeding rules if they exist beyond fixed W(X) paths.
    # Example: if SF games are "SF_HI_vs_LOW" and "SF_MID1_vs_MID2"
    if qf_game_numbers and sf_game_numbers: 
        qf_winners_details = []
        
        # Flatten all prelim teams and get their overall rank
        all_prelim_teams_flat: List[TeamStats] = []
        for group_list in prelim_standings_by_group.values():
            all_prelim_teams_flat.extend(group_list)
        
        # Sort by pts, gd, gf for overall ranking
        all_prelim_teams_flat.sort(key=lambda ts: (ts.pts, ts.gd, ts.gf), reverse=True)
        
        overall_prelim_rank_map: Dict[str, int] = {
            ts.name: rank + 1 for rank, ts in enumerate(all_prelim_teams_flat)
        }

        for qf_game_num in qf_game_numbers:
            w_qf_placeholder = f"W({qf_game_num})"
            qf_winner_team_code = playoff_team_map.get(w_qf_placeholder)
            
            if qf_winner_team_code and is_code_final(qf_winner_team_code):
                original_rank = overall_prelim_rank_map.get(qf_winner_team_code, 99) # Default to low rank
                qf_winners_details.append({"code": qf_winner_team_code, "rank": original_rank, "qf_game_num": qf_game_num})
        
        qf_winners_details.sort(key=lambda x: x["rank"]) # Sort QF winners by original overall prelim rank

        # This is where specific SF placeholder mapping based on qf_winners_details would go.
        # E.g., if fixture has SF games with placeholders like "SF_R1_vs_R4_T1", "SF_R1_vs_R4_T2"
        # if len(qf_winners_details) == 4:
        #     playoff_team_map["SF_R1_TEAM"] = qf_winners_details[0]["code"]
        #     playoff_team_map["SF_R4_TEAM"] = qf_winners_details[3]["code"]
        #     playoff_team_map["SF_R2_TEAM"] = qf_winners_details[1]["code"]
        #     playoff_team_map["SF_R3_TEAM"] = qf_winners_details[2]["code"]
        # This is highly dependent on game data placeholders. The W(X) system is more common.
        # Also, host team adjustments for SF pairings would be applied here.

    # Final cleanup pass
    final_passes = 3 
    for _ in range(final_passes):
        map_changed_in_final_pass = False
        for placeholder_key, mapped_code in list(playoff_team_map.items()):
            if not is_code_final(mapped_code):
                resolved_code = get_resolved_team_code(mapped_code, playoff_team_map, all_games_map_by_number)
                if resolved_code != mapped_code and is_code_final(resolved_code):
                    playoff_team_map[placeholder_key] = resolved_code
                    map_changed_in_final_pass = True
        if not map_changed_in_final_pass:
            break
            
    return playoff_team_map

# --- Placeholder for get_resolved_team_code ---
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
            # print(f"Cycle detected resolving {placeholder_code}. Path: {visited_codes} -> {current_code}")
            return placeholder_code # Return original to break cycle
        visited_codes.add(current_code)

    # If loop finishes (e.g. max iterations or break), return current_code if final, else original placeholder
    return current_code if is_code_final(current_code) else placeholder_code

# --- Placeholder for resolve_game_participants ---
def resolve_game_participants(
    game_to_resolve: Game, 
    year_obj: ChampionshipYear, 
    all_games_in_year: List[Game]
) -> Tuple[str, str]:
    """
    Main public function to resolve team codes for a given game.
    Returns a tuple of (resolved_team1_code, resolved_team2_code).
    """
    # TODO: Implementation in next step (This is the implementation)
    # This will call the above helper functions.

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
    prelim_standings_by_group: Dict[str, List[TeamStats]] = {}
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

def convert_time_to_seconds(time_str: str) -> int:
    """
    Converts a time string in format "MM:SS" to total seconds.
    
    Args:
        time_str: Time string in format "MM:SS" (e.g., "12:34")
        
    Returns:
        Total seconds as integer
        
    Example:
        convert_time_to_seconds("12:34") returns 754
    """
    if not time_str or ':' not in time_str:
        return 0
    
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            return 0
        
        minutes = int(parts[0])
        seconds = int(parts[1])
        
        return minutes * 60 + seconds
    except (ValueError, IndexError):
        return 0

def check_game_data_consistency(game_display, sog_data=None):
    """
    Checks a game display object for data consistency issues.
    
    Args:
        game_display: GameDisplay object to check
        sog_data: Optional shots on goal data dictionary
        
    Returns:
        Dictionary with consistency check results
    """
    warnings = []
    scores_fully_match_data = True
    
    # Check if scores are set but result_type is missing
    if game_display.team1_score is not None and game_display.team2_score is not None:
        if not game_display.result_type:
            warnings.append(f"Game {game_display.id}: Scores are set but result_type is missing")
            scores_fully_match_data = False
        
        # Check if scores match result_type logic
        if game_display.result_type == 'REG' and game_display.team1_score == game_display.team2_score:
            warnings.append(f"Game {game_display.id}: Regular time result but scores are tied")
            scores_fully_match_data = False
        
        if game_display.result_type in ['OT', 'SO'] and abs(game_display.team1_score - game_display.team2_score) != 1:
            warnings.append(f"Game {game_display.id}: Overtime/Shootout result but score difference is not 1")
            scores_fully_match_data = False
    
    # Check if result_type is set but scores are missing
    if game_display.result_type and (game_display.team1_score is None or game_display.team2_score is None):
        warnings.append(f"Game {game_display.id}: Result type is set but scores are missing")
        scores_fully_match_data = False
    
    # Check team codes
    if not game_display.team1_code or not game_display.team2_code:
        warnings.append(f"Game {game_display.id}: Missing team code(s)")
        scores_fully_match_data = False
    
    if game_display.team1_code == game_display.team2_code:
        warnings.append(f"Game {game_display.id}: Team playing against itself")
        scores_fully_match_data = False
    
    # Check points consistency
    if game_display.team1_score is not None and game_display.team2_score is not None and game_display.result_type:
        expected_points = calculate_expected_points(game_display.team1_score, game_display.team2_score, game_display.result_type)
        if hasattr(game_display, 'team1_points') and hasattr(game_display, 'team2_points'):
            if (game_display.team1_points, game_display.team2_points) != expected_points:
                warnings.append(f"Game {game_display.id}: Points don't match expected values for result")
                scores_fully_match_data = False
    
    return {
        'warnings': warnings,
        'scores_fully_match_data': scores_fully_match_data
    }

def calculate_expected_points(team1_score: int, team2_score: int, result_type: str) -> Tuple[int, int]:
    """
    Calculates expected points for both teams based on scores and result type.
    
    Returns:
        Tuple of (team1_points, team2_points)
    """
    if result_type == 'REG':
        if team1_score > team2_score:
            return (3, 0)
        elif team2_score > team1_score:
            return (0, 3)
        else:
            return (1, 1)  # Tie in regulation (rare in hockey)
    elif result_type in ['OT', 'SO']:
        if team1_score > team2_score:
            return (2, 1)
        else:
            return (1, 2)
    else:
        return (0, 0)  # Unknown result type