import re
import os
import json
from typing import Dict, List

from models import Game, ChampionshipYear, TeamStats
from constants import PLAYOFF_ROUNDS, QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4, SEMIFINAL_1, SEMIFINAL_2
from .team_resolution import is_code_final, get_resolved_team_code, resolve_fixture_path_local


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

    if year_obj.fixture_path:
        from flask import current_app
        absolute_fixture_path = resolve_fixture_path_local(year_obj.fixture_path, current_app)
        if absolute_fixture_path and os.path.exists(absolute_fixture_path):
            try:
                with open(absolute_fixture_path, 'r', encoding='utf-8') as f:
                    fixture_data = json.load(f)
                # Use .get for game numbers list, falling back to constants if key missing or empty
                qf_game_numbers = fixture_data.get("qf_game_numbers") or [QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4]
                sf_game_numbers = fixture_data.get("sf_game_numbers") or [SEMIFINAL_1, SEMIFINAL_2]
                host_team_codes = fixture_data.get("host_teams", []) 
            except (json.JSONDecodeError, OSError) as e:
                qf_game_numbers = [QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4]
                sf_game_numbers = [SEMIFINAL_1, SEMIFINAL_2]
    else:
        qf_game_numbers = [QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4]
        sf_game_numbers = [SEMIFINAL_1, SEMIFINAL_2]

    # 1. Initial population from prelim standings (A1, B2, etc.)
    # prelim_standings_by_group is Dict[str (group_name), List[TeamStats (sorted by rank)]]
    for group_name, group_teams_stats_list in prelim_standings_by_group.items():
        for team_stat in group_teams_stats_list: # Assumes list is sorted by rank_in_group from _calculate_basic_prelim_standings
            # rank_in_group is 1-indexed
            # Extract just the letter part from group names like "Group A" -> "A"
            group_letter = team_stat.group
            if group_letter and group_letter.startswith("Group "):
                group_letter = group_letter.replace("Group ", "")
            placeholder = f"{group_letter}{team_stat.rank_in_group}" 
            playoff_team_map[placeholder] = team_stat.name
            
            if host_team_codes and team_stat.name in host_team_codes:
                # This assumes host placeholders like "H1", "H2" might be used in game data.
                # The rank is specific to its group. If overall host rank needed, it's different.
                host_placeholder_group_rank = f"H{team_stat.rank_in_group}" 
                playoff_team_map[host_placeholder_group_rank] = team_stat.name

    # Check for custom QF seeding and apply if exists
    try:
        from routes.year.seeding import get_custom_qf_seeding_from_db
        custom_qf_seeding = get_custom_qf_seeding_from_db(year_obj.id)
        if custom_qf_seeding:
            # Override standard group position mappings with custom seeding
            for position, team_name in custom_qf_seeding.items():
                playoff_team_map[position] = team_name
    except ImportError:
        # In case of circular import or missing function, continue with standard seeding
        pass


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
    
    # 2.5 SF Mapping für Medal Games
    # Die Bronze/Gold Medal Games verwenden L(SF1), L(SF2), W(SF1), W(SF2) Platzhalter
    # Diese müssen zu den Spielnummern 61 und 62 gemappt werden
    if sf_game_numbers and len(sf_game_numbers) >= 2:
        playoff_team_map['SF1'] = str(sf_game_numbers[0])  # Normalerweise 61
        playoff_team_map['SF2'] = str(sf_game_numbers[1])  # Normalerweise 62
    
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