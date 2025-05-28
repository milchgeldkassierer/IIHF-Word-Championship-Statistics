import os
import json
import re # Added for regex in playoff map building
from typing import Dict, List # Added typing imports
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import db, ChampionshipYear, Game, AllTimeTeamStats, TeamStats, Player, Goal, Penalty # Added Player, Goal, Penalty
from constants import TEAM_ISO_CODES, PRELIM_ROUNDS, PLAYOFF_ROUNDS, QF_GAME_NUMBERS_BY_YEAR, SF_GAME_NUMBERS_BY_YEAR, FINAL_BRONZE_GAME_NUMBERS_BY_YEAR, PIM_MAP # Added more constants, PIM_MAP
from utils import get_resolved_team_code, is_code_final # Added utils imports
from sqlalchemy import func, case # Added func, case for SQLAlchemy
import traceback

main_bp = Blueprint('main_bp', __name__)

def calculate_all_time_standings():
    """
    Calculates all-time standings for all teams based on game results.
    This version precomputes playoff maps for each year.
    """
    # --- Start of new precomputation logic ---
    all_games = Game.query.options(db.joinedload(Game.championship_year)).all()
    year_objects_map = {year.id: year for year in ChampionshipYear.query.all()}

    games_by_year_id = {}
    for game_obj in all_games: # Renamed game to game_obj to avoid conflict later
        games_by_year_id.setdefault(game_obj.year_id, []).append(game_obj)

    resolved_playoff_maps_by_year_id = {}

    for year_id, games_in_this_year in games_by_year_id.items():
        year_obj = year_objects_map.get(year_id)
        if not year_obj:
            current_app.logger.warning(f"Year object not found for year_id {year_id}. Skipping playoff map generation for this year.")
            continue

        # a. Calculate Prelim Standings for this year
        prelim_stats_map_this_year: Dict[str, TeamStats] = {}
        prelim_games_for_standings_calc = [
            g for g in games_in_this_year
            if g.round in PRELIM_ROUNDS and \
               is_code_final(g.team1_code) and \
               is_code_final(g.team2_code) and \
               g.team1_score is not None and g.team2_score is not None
        ]

        for game_prelim in prelim_games_for_standings_calc:
            current_game_group = game_prelim.group or "N/A"
            # Ensure both teams are initialized in prelim_stats_map_this_year
            # Using a loop for brevity, though direct access is also fine.
            for team_code_val in [game_prelim.team1_code, game_prelim.team2_code]:
                if team_code_val not in prelim_stats_map_this_year:
                    prelim_stats_map_this_year[team_code_val] = TeamStats(name=team_code_val, group=current_game_group)
                # If team was seen before with N/A group (unlikely if data is good), update with actual group.
                elif prelim_stats_map_this_year[team_code_val].group == "N/A" and current_game_group != "N/A":
                    prelim_stats_map_this_year[team_code_val].group = current_game_group
            
            t1_stats = prelim_stats_map_this_year[game_prelim.team1_code]
            t2_stats = prelim_stats_map_this_year[game_prelim.team2_code]

            t1_stats.gp += 1; t2_stats.gp += 1
            t1_stats.gf += game_prelim.team1_score; t1_stats.ga += game_prelim.team2_score
            t2_stats.gf += game_prelim.team2_score; t2_stats.ga += game_prelim.team1_score

            if game_prelim.result_type == 'REG':
                if game_prelim.team1_score > game_prelim.team2_score: (t1_stats.w, t1_stats.pts, t2_stats.l) = (t1_stats.w+1, t1_stats.pts+3, t2_stats.l+1)
                else: (t2_stats.w, t2_stats.pts, t1_stats.l) = (t2_stats.w+1, t2_stats.pts+3, t1_stats.l+1)
            elif game_prelim.result_type == 'OT':
                if game_prelim.team1_score > game_prelim.team2_score: (t1_stats.otw, t1_stats.pts, t2_stats.otl, t2_stats.pts) = (t1_stats.otw+1, t1_stats.pts+2, t2_stats.otl+1, t2_stats.pts+1)
                else: (t2_stats.otw, t2_stats.pts, t1_stats.otl, t1_stats.pts) = (t2_stats.otw+1, t2_stats.pts+2, t1_stats.otl+1, t1_stats.pts+1)
            elif game_prelim.result_type == 'SO':
                if game_prelim.team1_score > game_prelim.team2_score: (t1_stats.sow, t1_stats.pts, t2_stats.sol, t2_stats.pts) = (t1_stats.sow+1, t1_stats.pts+2, t2_stats.sol+1, t2_stats.pts+1)
                else: (t2_stats.sow, t2_stats.pts, t1_stats.sol, t1_stats.pts) = (t2_stats.sow+1, t2_stats.pts+2, t1_stats.sol+1, t1_stats.pts+1)

        prelim_standings_by_group_this_year: Dict[str, List[TeamStats]] = {}
        for ts_obj in prelim_stats_map_this_year.values():
            group_key = ts_obj.group if ts_obj.group else "UnknownGroup"
            prelim_standings_by_group_this_year.setdefault(group_key, []).append(ts_obj)
        
        for group_list in prelim_standings_by_group_this_year.values():
            group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
            for i, ts_in_group in enumerate(group_list):
                ts_in_group.rank_in_group = i + 1
        
        # b. Build Playoff Team Map for this year
        current_year_playoff_map: Dict[str, str] = {}
        all_games_this_year_map_by_number: Dict[int, Game] = {g.game_number: g for g in games_in_this_year if g.game_number is not None}

        qf_gns, sf_gns, h_tcs = [], [], []
        if year_obj.fixture_path and os.path.exists(year_obj.fixture_path):
            try:
                with open(year_obj.fixture_path, 'r', encoding='utf-8') as f: 
                    fixture_data = json.load(f)
                qf_gns = fixture_data.get("qf_game_numbers") or QF_GAME_NUMBERS_BY_YEAR.get(year_id, [])
                sf_gns = fixture_data.get("sf_game_numbers") or SF_GAME_NUMBERS_BY_YEAR.get(year_id, [])
                h_tcs = fixture_data.get("host_teams", [])
            except (json.JSONDecodeError, OSError): 
                qf_gns = QF_GAME_NUMBERS_BY_YEAR.get(year_id, []); sf_gns = SF_GAME_NUMBERS_BY_YEAR.get(year_id, [])
        else: 
            qf_gns = QF_GAME_NUMBERS_BY_YEAR.get(year_id, []); sf_gns = SF_GAME_NUMBERS_BY_YEAR.get(year_id, [])

        for grp_name_iter, grp_teams_stats_list in prelim_standings_by_group_this_year.items(): # Renamed grp_name
            for team_s in grp_teams_stats_list:
                # Extract just the letter part from group names like "Group A" -> "A"
                group_letter = team_s.group
                if group_letter and group_letter.startswith("Group "):
                    group_letter = group_letter.replace("Group ", "")
                current_year_playoff_map[f"{group_letter}{team_s.rank_in_group}"] = team_s.name
                if h_tcs and team_s.name in h_tcs: current_year_playoff_map[f"H{team_s.rank_in_group}"] = team_s.name # Placeholder for host rank
        
        # Add quarterfinal winner mappings (Q1, Q2, Q3, Q4)
        # Assuming QF games are in order: 57, 58, 59, 60
        if qf_gns and len(qf_gns) >= 4:
            for i, qf_game_num in enumerate(qf_gns[:4]):
                qf_winner_placeholder = f"Q{i+1}"
                game_winner_placeholder = f"W({qf_game_num})"
                # Q1 = W(57), Q2 = W(58), Q3 = W(59), Q4 = W(60)
                current_year_playoff_map[qf_winner_placeholder] = game_winner_placeholder


        max_iter_passes, current_pass, map_changed_this_iter = 10, 0, True
        while map_changed_this_iter and current_pass < max_iter_passes:
            map_changed_this_iter = False; current_pass += 1
            for pk, mc in list(current_year_playoff_map.items()): # pk: placeholder_key, mc: mapped_code
                if not is_code_final(mc):
                    rc = get_resolved_team_code(mc, current_year_playoff_map, all_games_this_year_map_by_number) # rc: resolved_code
                    if rc != mc and is_code_final(rc): current_year_playoff_map[pk] = rc; map_changed_this_iter = True
            
            for g_playoff in games_in_this_year:
                if g_playoff.round in PLAYOFF_ROUNDS and g_playoff.game_number and \
                   g_playoff.team1_score is not None and g_playoff.team2_score is not None:
                    rt1 = get_resolved_team_code(g_playoff.team1_code, current_year_playoff_map, all_games_this_year_map_by_number)
                    rt2 = get_resolved_team_code(g_playoff.team2_code, current_year_playoff_map, all_games_this_year_map_by_number)
                    if not is_code_final(rt1) or not is_code_final(rt2): continue
                    
                    wac = rt1 if g_playoff.team1_score > g_playoff.team2_score else rt2 # winner_actual_code
                    lac = rt2 if g_playoff.team1_score > g_playoff.team2_score else rt1 # loser_actual_code
                    wp, lp = f"W({g_playoff.game_number})", f"L({g_playoff.game_number})" # winner_placeholder, loser_placeholder
                    if current_year_playoff_map.get(wp) != wac: current_year_playoff_map[wp] = wac; map_changed_this_iter = True
                    if current_year_playoff_map.get(lp) != lac: current_year_playoff_map[lp] = lac; map_changed_this_iter = True
                    
                    # Add semifinal mappings (SF1, SF2) based on semifinal games
                    if sf_gns and g_playoff.game_number in sf_gns:
                        sf_index = sf_gns.index(g_playoff.game_number) + 1
                        sf_winner_placeholder = f"W(SF{sf_index})"
                        sf_loser_placeholder = f"L(SF{sf_index})"
                        if current_year_playoff_map.get(sf_winner_placeholder) != wac: 
                            current_year_playoff_map[sf_winner_placeholder] = wac; map_changed_this_iter = True
                        if current_year_playoff_map.get(sf_loser_placeholder) != lac: 
                            current_year_playoff_map[sf_loser_placeholder] = lac; map_changed_this_iter = True
            
            # SIMPLIFIED: Direct semifinal mapping after QF winners are resolved
            if sf_gns and len(sf_gns) >= 2:
                # Get the semifinal games
                sf_game_1 = all_games_this_year_map_by_number.get(sf_gns[0])
                sf_game_2 = all_games_this_year_map_by_number.get(sf_gns[1])
                
                if sf_game_1 and sf_game_2:

                    
                    # Try to resolve Q1, Q2, Q3, Q4 to actual teams
                    q1_team = current_year_playoff_map.get('Q1')
                    q2_team = current_year_playoff_map.get('Q2') 
                    q3_team = current_year_playoff_map.get('Q3')
                    q4_team = current_year_playoff_map.get('Q4')
                    

                    
                    # If Q1-Q4 are mapped to W(X) placeholders, resolve them
                    if q1_team and q1_team.startswith('W('):
                        q1_resolved = current_year_playoff_map.get(q1_team)
                        if q1_resolved and is_code_final(q1_resolved):
                            current_year_playoff_map['Q1'] = q1_resolved
                            q1_team = q1_resolved
                            map_changed_this_iter = True

                    
                    if q2_team and q2_team.startswith('W('):
                        q2_resolved = current_year_playoff_map.get(q2_team)
                        if q2_resolved and is_code_final(q2_resolved):
                            current_year_playoff_map['Q2'] = q2_resolved
                            q2_team = q2_resolved
                            map_changed_this_iter = True

                    
                    if q3_team and q3_team.startswith('W('):
                        q3_resolved = current_year_playoff_map.get(q3_team)
                        if q3_resolved and is_code_final(q3_resolved):
                            current_year_playoff_map['Q3'] = q3_resolved
                            q3_team = q3_resolved
                            map_changed_this_iter = True

                    
                    if q4_team and q4_team.startswith('W('):
                        q4_resolved = current_year_playoff_map.get(q4_team)
                        if q4_resolved and is_code_final(q4_resolved):
                            current_year_playoff_map['Q4'] = q4_resolved
                            q4_team = q4_resolved
                            map_changed_this_iter = True

                    
                    # Now map the semifinal games directly
                    if q1_team and is_code_final(q1_team) and q2_team and is_code_final(q2_team):
                        if sf_game_1.team1_code == 'Q1' and sf_game_1.team2_code == 'Q2':
                            current_year_playoff_map['Q1'] = q1_team
                            current_year_playoff_map['Q2'] = q2_team
                            map_changed_this_iter = True

                    
                    if q3_team and is_code_final(q3_team) and q4_team and is_code_final(q4_team):
                        if sf_game_2.team1_code == 'Q3' and sf_game_2.team2_code == 'Q4':
                            current_year_playoff_map['Q3'] = q3_team
                            current_year_playoff_map['Q4'] = q4_team
                            map_changed_this_iter = True

            
            # Add complex semifinal pairing logic INSIDE the loop (ported from year_routes.py) - DISABLED FOR NOW
            if False and qf_gns and sf_gns and len(qf_gns) >= 4 and len(sf_gns) >= 2:

                # Get QF winners
                qf_winners_teams = []
                all_qf_winners_resolved = True
                for qf_game_num in qf_gns[:4]:  # Only take first 4 QF games
                    winner_placeholder = f'W({qf_game_num})'
                    resolved_qf_winner = current_year_playoff_map.get(winner_placeholder)

                    if resolved_qf_winner and is_code_final(resolved_qf_winner):
                        qf_winners_teams.append(resolved_qf_winner)
                    else:
                        all_qf_winners_resolved = False

                        break
                
                if all_qf_winners_resolved and len(qf_winners_teams) == 4:
                    # Get preliminary stats for QF winners to determine rankings
                    qf_winners_stats = []
                    for team_name in qf_winners_teams:
                        # Find this team in the preliminary standings
                        team_found = False
                        for group_standings in prelim_standings_by_group_this_year.values():
                            for team_stat in group_standings:
                                if team_stat.name == team_name:
                                    qf_winners_stats.append(team_stat)
                                    team_found = True
                                    break
                            if team_found:
                                break
                        if not team_found:
                            all_qf_winners_resolved = False
                            break
                    
                    if all_qf_winners_resolved and len(qf_winners_stats) == 4:
                        # Sort by preliminary standings (same logic as year_routes.py)
                        qf_winners_stats.sort(key=lambda ts: (ts.rank_in_group, -ts.pts, -ts.gd, -ts.gf))
                        R1, R2, R3, R4 = [ts.name for ts in qf_winners_stats]

                        
                        # Create matchups: R1 vs R4, R2 vs R3
                        matchup1 = (R1, R4)
                        matchup2 = (R2, R3)
                        sf_game1_teams = None
                        sf_game2_teams = None
                        primary_host_plays_sf1 = False
                        
                        # Check for host country preferences (same logic as year_routes.py)
                        if h_tcs:  # h_tcs = host teams
                            if h_tcs[0] in [R1, R2, R3, R4]:
                                primary_host_plays_sf1 = True
                                if R1 == h_tcs[0] or R4 == h_tcs[0]:
                                    sf_game1_teams = matchup1
                                    sf_game2_teams = matchup2
                                else:
                                    sf_game1_teams = matchup2
                                    sf_game2_teams = matchup1
                            elif len(h_tcs) > 1 and h_tcs[1] in [R1, R2, R3, R4]:
                                primary_host_plays_sf1 = True
                                if R1 == h_tcs[1] or R4 == h_tcs[1]:
                                    sf_game1_teams = matchup1
                                    sf_game2_teams = matchup2
                                else:
                                    sf_game1_teams = matchup2
                                    sf_game2_teams = matchup1
                        
                        if not primary_host_plays_sf1:
                            sf_game1_teams = matchup1
                            sf_game2_teams = matchup2
                        
                        # Map semifinal games to actual teams
                        if sf_game1_teams and sf_game2_teams and len(sf_gns) >= 2:
                            sf_game_obj_1 = all_games_this_year_map_by_number.get(sf_gns[0])
                            sf_game_obj_2 = all_games_this_year_map_by_number.get(sf_gns[1])
                            
                            if sf_game_obj_1 and sf_game_obj_2:

                                # Map SF game 1 teams
                                if current_year_playoff_map.get(sf_game_obj_1.team1_code) != sf_game1_teams[0]:

                                    current_year_playoff_map[sf_game_obj_1.team1_code] = sf_game1_teams[0]
                                    map_changed_this_iter = True
                                if current_year_playoff_map.get(sf_game_obj_1.team2_code) != sf_game1_teams[1]:

                                    current_year_playoff_map[sf_game_obj_1.team2_code] = sf_game1_teams[1]
                                    map_changed_this_iter = True
                                
                                # Map SF game 2 teams
                                if current_year_playoff_map.get(sf_game_obj_2.team1_code) != sf_game2_teams[0]:

                                    current_year_playoff_map[sf_game_obj_2.team1_code] = sf_game2_teams[0]
                                    map_changed_this_iter = True
                                if current_year_playoff_map.get(sf_game_obj_2.team2_code) != sf_game2_teams[1]:

                                    current_year_playoff_map[sf_game_obj_2.team2_code] = sf_game2_teams[1]
                                    map_changed_this_iter = True
        
        resolved_playoff_maps_by_year_id[year_id] = current_year_playoff_map

        



    # --- End of new precomputation logic ---
    
    all_time_stats_dict = {}
    # Iterate all_games, using precomputed maps to resolve team codes.
    for game in all_games:
        if game.team1_score is None or game.team2_score is None:
            continue

        year_id = game.year_id
        current_year_playoff_map = resolved_playoff_maps_by_year_id.get(year_id)
        if current_year_playoff_map is None:
            current_app.logger.warning(
                f"Playoff map not found for year_id {year_id} when processing game GID:{game.id}. "
                f"Original team codes ('{game.team1_code}', '{game.team2_code}') will be used for resolution attempt."
            )
            current_year_playoff_map = {} # Use empty map; get_resolved_team_code will likely return original codes

        current_year_games_list = games_by_year_id.get(year_id, [])
        current_year_games_map_by_number = {g.game_number: g for g in current_year_games_list if g.game_number is not None}


        # Always try to resolve team codes, but only include games with scores in all-time stats
        resolved_team1_code = get_resolved_team_code(game.team1_code, current_year_playoff_map, current_year_games_map_by_number)
        resolved_team2_code = get_resolved_team_code(game.team2_code, current_year_playoff_map, current_year_games_map_by_number)
        
        # Debug logging for semifinal games specifically
        if game.round in ['SF', 'F'] or game.game_number in [61, 62, 63, 64]:
            pass
        



        # Include games that resolve to final team codes OR games that have actual team codes in the database
        # This handles both placeholder games that resolve correctly and manually updated games
        has_final_resolved_codes = is_code_final(resolved_team1_code) and is_code_final(resolved_team2_code)
        has_final_original_codes = is_code_final(game.team1_code) and is_code_final(game.team2_code)
        
        if not (has_final_resolved_codes or has_final_original_codes):
            # Skip games where participants can't be resolved to final codes
            skipped_games_count = getattr(calculate_all_time_standings, '_skipped_count', 0) + 1
            calculate_all_time_standings._skipped_count = skipped_games_count
            continue # Skip this game if participants can't be resolved to final codes
            
        # Use the best available team codes (prefer resolved if final, otherwise use original if final)
        if has_final_resolved_codes:
            final_team1_code = resolved_team1_code
            final_team2_code = resolved_team2_code
        else:
            final_team1_code = game.team1_code
            final_team2_code = game.team2_code
            
        year_of_game = game.championship_year.year if game.championship_year else None # Should always have year

        # Initialize/get AllTimeTeamStats for final team codes
        if final_team1_code not in all_time_stats_dict:
            all_time_stats_dict[final_team1_code] = AllTimeTeamStats(team_code=final_team1_code)
        team1_stats = all_time_stats_dict[final_team1_code]
        
        if final_team2_code not in all_time_stats_dict:
            all_time_stats_dict[final_team2_code] = AllTimeTeamStats(team_code=final_team2_code)
        team2_stats = all_time_stats_dict[final_team2_code]

        # Update participation years and game stats
        if year_of_game: # Should always be true if game.championship_year is loaded
            team1_stats.years_participated.add(year_of_game)
            team2_stats.years_participated.add(year_of_game)

        team1_stats.gp += 1
        team2_stats.gp += 1
        team1_stats.gf += game.team1_score
        team1_stats.ga += game.team2_score
        team2_stats.gf += game.team2_score
        team2_stats.ga += game.team1_score
        
        # Determine winner and loser stats objects
        if game.team1_score > game.team2_score:
            winner_stats, loser_stats = team1_stats, team2_stats
        else: # team2_score > team1_score (draws not expected with these result types)
            winner_stats, loser_stats = team2_stats, team1_stats
        
        # Assign points and W/L type based on game.result_type
        if game.result_type == 'REG':
            winner_stats.w += 1; winner_stats.pts += 3
            loser_stats.l += 1
        elif game.result_type == 'OT':
            winner_stats.otw += 1; winner_stats.pts += 2
            loser_stats.otl += 1; loser_stats.pts += 1
        elif game.result_type == 'SO': # Shootout
            winner_stats.sow += 1; winner_stats.pts += 2
            loser_stats.sol += 1; loser_stats.pts += 1
        elif game.result_type: # Only log if result_type is present but not recognized
             current_app.logger.warning(f"Game ID {game.id} has unhandled result_type: '{game.result_type}'. Points not assigned for this type.")
        # If game.result_type is None or empty, points are not assigned, no specific warning here unless desired.

    # Convert dictionary values to list (all_time_stats_dict now only contains final codes)
    final_all_time_standings = list(all_time_stats_dict.values())
    final_all_time_standings.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
    
    # Log summary of skipped games if any
    skipped_count = getattr(calculate_all_time_standings, '_skipped_count', 0)
    if skipped_count > 0:
        current_app.logger.info(f"All-time standings calculated. Skipped {skipped_count} games with non-final team codes (placeholder/unresolved teams).")
        # Reset counter for next calculation
        calculate_all_time_standings._skipped_count = 0
    
    return final_all_time_standings

@main_bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'delete_year' in request.form:
            year_id_to_delete = request.form.get('year_id_to_delete')
            year_obj_del = db.session.get(ChampionshipYear, year_id_to_delete)
            if year_obj_del:
                if year_obj_del.fixture_path and os.path.exists(year_obj_del.fixture_path):
                    try:
                        abs_fixture_path = os.path.abspath(year_obj_del.fixture_path)
                        abs_upload_folder = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
                        if abs_fixture_path.startswith(abs_upload_folder):
                             os.remove(year_obj_del.fixture_path)
                             flash(f'Associated fixture file "{os.path.basename(year_obj_del.fixture_path)}" from data directory deleted.', 'info')
                    except OSError as e:
                        flash(f"Error deleting managed fixture file: {e}", "danger")
                
                db.session.delete(year_obj_del)
                db.session.commit()
                flash(f'Tournament "{year_obj_del.name} ({year_obj_del.year})" deleted.', 'success')
            else:
                flash('Tournament to delete not found.', 'warning')
            return redirect(url_for('main_bp.index'))

        name_str = request.form.get('tournament_name')
        year_str = request.form.get('year')

        if not name_str or not year_str:
            flash('Name and Year are required.', 'danger'); return redirect(url_for('main_bp.index'))
        try: year_int = int(year_str)
        except ValueError: flash('Year must be a number.', 'danger'); return redirect(url_for('main_bp.index'))

        existing_tournament = ChampionshipYear.query.filter_by(name=name_str, year=year_int).first()
        target_year_obj = existing_tournament

        if not target_year_obj:
            new_tournament = ChampionshipYear(name=name_str, year=year_int)
            db.session.add(new_tournament)
            try:
                db.session.commit()
                target_year_obj = new_tournament
                flash(f'Tournament "{target_year_obj.name} ({target_year_obj.year})" created.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating tournament: {str(e)}', 'danger')
                return redirect(url_for('main_bp.index'))
        else:
            flash(f'Tournament "{name_str} ({year_int})" already exists. Updating fixture based on selected year.', 'info')

        if target_year_obj:
            potential_fixture_filename = f"{year_str}.json"
            fixture_path_to_load = None

            path_in_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], potential_fixture_filename)
            if os.path.exists(path_in_upload_folder):
                fixture_path_to_load = path_in_upload_folder
            else:
                path_in_root_fixtures = os.path.join(current_app.config['BASE_DIR'], 'fixtures', potential_fixture_filename)
                if os.path.exists(path_in_root_fixtures):
                    fixture_path_to_load = path_in_root_fixtures
            
            if not fixture_path_to_load and target_year_obj.id:
                 potential_id_fixture_filename = f"{target_year_obj.id}_{year_str}.json"
                 path_id_in_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], potential_id_fixture_filename)
                 if os.path.exists(path_id_in_upload_folder):
                      fixture_path_to_load = path_id_in_upload_folder

            if fixture_path_to_load:
                Game.query.filter_by(year_id=target_year_obj.id).delete()
                try:
                    target_year_obj.fixture_path = fixture_path_to_load
                    with open(fixture_path_to_load, 'r', encoding='utf-8') as f:
                        fixture_data = json.load(f)
                    
                    games_from_json = fixture_data.get("schedule", [])
                    for game_data_item in games_from_json:
                        mapped_game_data = {
                            'date': game_data_item.get('date'),
                            'start_time': game_data_item.get('startTime'),
                            'round': game_data_item.get('round'),
                            'group': game_data_item.get('group'),
                            'game_number': game_data_item.get('gameNumber'),
                            'team1_code': game_data_item.get('team1'),
                            'team2_code': game_data_item.get('team2'),
                            'location': game_data_item.get('location'),
                            'venue': game_data_item.get('venue')
                        }
                        new_game = Game(year_id=target_year_obj.id, **mapped_game_data)
                        db.session.add(new_game)
                    
                    db.session.commit()
                    flash(f'Fixture "{os.path.basename(fixture_path_to_load)}" loaded and games updated for "{target_year_obj.name} ({target_year_obj.year})".', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error processing fixture file "{os.path.basename(fixture_path_to_load if fixture_path_to_load else potential_fixture_filename)}": {str(e)} - {traceback.format_exc()}', 'danger')
            else:
                if not existing_tournament:
                    flash(f'Tournament "{target_year_obj.name} ({target_year_obj.year})" created, but no fixture file like "{year_str}.json" found. Please add it and try again.', 'warning')
                else:
                    flash(f'No fixture file like "{year_str}.json" found for "{target_year_obj.name} ({target_year_obj.year})". Existing games remain.', 'info')

    all_years_db = ChampionshipYear.query.order_by(ChampionshipYear.year.desc(), ChampionshipYear.name).all()
    
    # Example of how you might call it in a route (for testing, not part of this function's definition)
    # all_time_table = calculate_all_time_standings()
    # for team_stat in all_time_table:
    #     print(f"Team: {team_stat.team_code}, Pts: {team_stat.pts}, GD: {team_stat.gd}")

    all_found_years = set()
    upload_folder_path = current_app.config['UPLOAD_FOLDER']
    if os.path.exists(upload_folder_path):
        for f_name in os.listdir(upload_folder_path):
            if f_name.endswith('.json'):
                year_part = f_name[:-5]
                if '_' in year_part:
                    potential_year = year_part.split('_')[-1]
                    if potential_year.isdigit():
                        all_found_years.add(potential_year)
                elif year_part.isdigit():
                    all_found_years.add(year_part)

    root_fixtures_path = os.path.join(current_app.config['BASE_DIR'], 'fixtures') 
    if os.path.exists(root_fixtures_path):
        for f_name in os.listdir(root_fixtures_path):
            if f_name.endswith('.json'):
                year_part = f_name[:-5]
                if year_part.isdigit():
                    all_found_years.add(year_part)
    
    sorted_fixture_years = sorted(list(all_found_years), reverse=True)

    return render_template('index.html', all_years=all_years_db, available_fixture_years=sorted_fixture_years)

@main_bp.route('/all-time-standings')
def all_time_standings_view():
    """
    Displays the all-time standings page.
    """
    standings_data = calculate_all_time_standings()
    return render_template('all_time_standings.html', standings_data=standings_data, team_iso_codes=TEAM_ISO_CODES)

@main_bp.route('/medal-tally')
def medal_tally_view():
    """
    Displays the medal tally page.
    """
    current_app.logger.info("Accessing medal tally page.")
    medal_data = get_medal_tally_data() # This function is already defined in this file
    # TEAM_ISO_CODES is already imported in this file
    return render_template('medal_tally.html', medal_data=medal_data, team_iso_codes=TEAM_ISO_CODES)

def get_medal_tally_data():
    """
    Calculates the medal tally (Gold, Silver, Bronze, 4th) for each championship year.
    """
    current_app.logger.info("Starting medal tally calculation.")
    medal_tally_results = []

    # --- Start of precomputation logic (adapted from calculate_all_time_standings) ---
    all_games = Game.query.options(db.joinedload(Game.championship_year)).all()
    all_years = ChampionshipYear.query.order_by(ChampionshipYear.year.desc()).all() # Fetch all years, sort later
    year_objects_map = {year.id: year for year in all_years}

    games_by_year_id: Dict[int, List[Game]] = {}
    for game_obj in all_games:
        games_by_year_id.setdefault(game_obj.year_id, []).append(game_obj)

    resolved_playoff_maps_by_year_id: Dict[int, Dict[str, str]] = {}

    for year_id_iter, games_in_this_year in games_by_year_id.items(): # Renamed year_id to avoid conflict
        year_obj_for_map = year_objects_map.get(year_id_iter)
        if not year_obj_for_map:
            current_app.logger.warning(f"MedalTally: Year object not found for year_id {year_id_iter}. Skipping playoff map generation.")
            continue

        prelim_stats_map_this_year: Dict[str, TeamStats] = {}
        prelim_games_for_standings_calc = [
            g for g in games_in_this_year
            if g.round in PRELIM_ROUNDS and \
               is_code_final(g.team1_code) and \
               is_code_final(g.team2_code) and \
               g.team1_score is not None and g.team2_score is not None
        ]

        for game_prelim in prelim_games_for_standings_calc:
            current_game_group = game_prelim.group or "N/A"
            for team_code_val in [game_prelim.team1_code, game_prelim.team2_code]:
                if team_code_val not in prelim_stats_map_this_year:
                    prelim_stats_map_this_year[team_code_val] = TeamStats(name=team_code_val, group=current_game_group)
                elif prelim_stats_map_this_year[team_code_val].group == "N/A" and current_game_group != "N/A":
                    prelim_stats_map_this_year[team_code_val].group = current_game_group
            
            t1_stats = prelim_stats_map_this_year[game_prelim.team1_code]
            t2_stats = prelim_stats_map_this_year[game_prelim.team2_code]

            t1_stats.gp += 1; t2_stats.gp += 1
            t1_stats.gf += game_prelim.team1_score; t1_stats.ga += game_prelim.team2_score
            t2_stats.gf += game_prelim.team2_score; t2_stats.ga += game_prelim.team1_score

            if game_prelim.result_type == 'REG':
                if game_prelim.team1_score > game_prelim.team2_score: (t1_stats.w, t1_stats.pts, t2_stats.l) = (t1_stats.w+1, t1_stats.pts+3, t2_stats.l+1)
                else: (t2_stats.w, t2_stats.pts, t1_stats.l) = (t2_stats.w+1, t2_stats.pts+3, t1_stats.l+1)
            elif game_prelim.result_type == 'OT':
                if game_prelim.team1_score > game_prelim.team2_score: (t1_stats.otw, t1_stats.pts, t2_stats.otl, t2_stats.pts) = (t1_stats.otw+1, t1_stats.pts+2, t2_stats.otl+1, t2_stats.pts+1)
                else: (t2_stats.otw, t2_stats.pts, t1_stats.otl, t1_stats.pts) = (t2_stats.otw+1, t2_stats.pts+2, t1_stats.otl+1, t1_stats.pts+1)
            elif game_prelim.result_type == 'SO':
                if game_prelim.team1_score > game_prelim.team2_score: (t1_stats.sow, t1_stats.pts, t2_stats.sol, t2_stats.pts) = (t1_stats.sow+1, t1_stats.pts+2, t2_stats.sol+1, t2_stats.pts+1)
                else: (t2_stats.sow, t2_stats.pts, t1_stats.sol, t1_stats.pts) = (t2_stats.sow+1, t2_stats.pts+2, t1_stats.sol+1, t1_stats.pts+1)

        prelim_standings_by_group_this_year: Dict[str, List[TeamStats]] = {}
        for ts_obj in prelim_stats_map_this_year.values():
            group_key = ts_obj.group if ts_obj.group else "UnknownGroup"
            prelim_standings_by_group_this_year.setdefault(group_key, []).append(ts_obj)
        
        for group_list in prelim_standings_by_group_this_year.values():
            group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
            for i, ts_in_group in enumerate(group_list):
                ts_in_group.rank_in_group = i + 1
        
        current_year_playoff_map: Dict[str, str] = {}
        all_games_this_year_map_by_number_local: Dict[int, Game] = {g.game_number: g for g in games_in_this_year if g.game_number is not None} # Renamed to avoid conflict

        qf_gns, sf_gns, h_tcs = [], [], []
        if year_obj_for_map.fixture_path and os.path.exists(year_obj_for_map.fixture_path):
            try:
                with open(year_obj_for_map.fixture_path, 'r', encoding='utf-8') as f: fixture_data = json.load(f)
                qf_gns = fixture_data.get("qf_game_numbers") or QF_GAME_NUMBERS_BY_YEAR.get(year_id_iter, [])
                sf_gns = fixture_data.get("sf_game_numbers") or SF_GAME_NUMBERS_BY_YEAR.get(year_id_iter, [])
                h_tcs = fixture_data.get("host_teams", [])
            except (json.JSONDecodeError, OSError): 
                qf_gns = QF_GAME_NUMBERS_BY_YEAR.get(year_id_iter, []); sf_gns = SF_GAME_NUMBERS_BY_YEAR.get(year_id_iter, [])
        else: 
            qf_gns = QF_GAME_NUMBERS_BY_YEAR.get(year_id_iter, []); sf_gns = SF_GAME_NUMBERS_BY_YEAR.get(year_id_iter, [])

        for grp_name_iter, grp_teams_stats_list in prelim_standings_by_group_this_year.items():
            for team_s in grp_teams_stats_list:
                group_letter = team_s.group
                if group_letter and group_letter.startswith("Group "): group_letter = group_letter.replace("Group ", "")
                current_year_playoff_map[f"{group_letter}{team_s.rank_in_group}"] = team_s.name
                if h_tcs and team_s.name in h_tcs: current_year_playoff_map[f"H{team_s.rank_in_group}"] = team_s.name

        if qf_gns and len(qf_gns) >= 4:
            for i, qf_game_num in enumerate(qf_gns[:4]):
                current_year_playoff_map[f"Q{i+1}"] = f"W({qf_game_num})"
        
        max_iter_passes, current_pass, map_changed_this_iter = 10, 0, True
        while map_changed_this_iter and current_pass < max_iter_passes:
            map_changed_this_iter = False; current_pass += 1
            for pk, mc in list(current_year_playoff_map.items()):
                if not is_code_final(mc):
                    rc = get_resolved_team_code(mc, current_year_playoff_map, all_games_this_year_map_by_number_local)
                    if rc != mc and is_code_final(rc): current_year_playoff_map[pk] = rc; map_changed_this_iter = True
            
            for g_playoff in games_in_this_year:
                if g_playoff.round in PLAYOFF_ROUNDS and g_playoff.game_number and \
                   g_playoff.team1_score is not None and g_playoff.team2_score is not None:
                    rt1 = get_resolved_team_code(g_playoff.team1_code, current_year_playoff_map, all_games_this_year_map_by_number_local)
                    rt2 = get_resolved_team_code(g_playoff.team2_code, current_year_playoff_map, all_games_this_year_map_by_number_local)
                    if not is_code_final(rt1) or not is_code_final(rt2): continue
                    
                    wac = rt1 if g_playoff.team1_score > g_playoff.team2_score else rt2
                    lac = rt2 if g_playoff.team1_score > g_playoff.team2_score else rt1
                    wp, lp = f"W({g_playoff.game_number})", f"L({g_playoff.game_number})"
                    if current_year_playoff_map.get(wp) != wac: current_year_playoff_map[wp] = wac; map_changed_this_iter = True
                    if current_year_playoff_map.get(lp) != lac: current_year_playoff_map[lp] = lac; map_changed_this_iter = True
                    
                    if sf_gns and g_playoff.game_number in sf_gns:
                        sf_index = sf_gns.index(g_playoff.game_number) + 1
                        sf_winner_placeholder = f"W(SF{sf_index})"
                        sf_loser_placeholder = f"L(SF{sf_index})"
                        if current_year_playoff_map.get(sf_winner_placeholder) != wac: current_year_playoff_map[sf_winner_placeholder] = wac; map_changed_this_iter = True
                        if current_year_playoff_map.get(sf_loser_placeholder) != lac: current_year_playoff_map[sf_loser_placeholder] = lac; map_changed_this_iter = True
            
            # Simplified SF mapping (copied from calculate_all_time_standings)
            if sf_gns and len(sf_gns) >= 2:
                sf_game_1_obj = all_games_this_year_map_by_number_local.get(sf_gns[0]) # Renamed to avoid conflict
                sf_game_2_obj = all_games_this_year_map_by_number_local.get(sf_gns[1]) # Renamed to avoid conflict
                if sf_game_1_obj and sf_game_2_obj:
                    q1_team = current_year_playoff_map.get('Q1')
                    q2_team = current_year_playoff_map.get('Q2') 
                    q3_team = current_year_playoff_map.get('Q3')
                    q4_team = current_year_playoff_map.get('Q4')
                    if q1_team and q1_team.startswith('W('):
                        q1_resolved = current_year_playoff_map.get(q1_team)
                        if q1_resolved and is_code_final(q1_resolved): current_year_playoff_map['Q1'] = q1_resolved; q1_team = q1_resolved; map_changed_this_iter = True
                    if q2_team and q2_team.startswith('W('):
                        q2_resolved = current_year_playoff_map.get(q2_team)
                        if q2_resolved and is_code_final(q2_resolved): current_year_playoff_map['Q2'] = q2_resolved; q2_team = q2_resolved; map_changed_this_iter = True
                    if q3_team and q3_team.startswith('W('):
                        q3_resolved = current_year_playoff_map.get(q3_team)
                        if q3_resolved and is_code_final(q3_resolved): current_year_playoff_map['Q3'] = q3_resolved; q3_team = q3_resolved; map_changed_this_iter = True
                    if q4_team and q4_team.startswith('W('):
                        q4_resolved = current_year_playoff_map.get(q4_team)
                        if q4_resolved and is_code_final(q4_resolved): current_year_playoff_map['Q4'] = q4_resolved; q4_team = q4_resolved; map_changed_this_iter = True
                    if q1_team and is_code_final(q1_team) and q2_team and is_code_final(q2_team):
                        if sf_game_1_obj.team1_code == 'Q1' and sf_game_1_obj.team2_code == 'Q2':
                            current_year_playoff_map['Q1'] = q1_team; current_year_playoff_map['Q2'] = q2_team; map_changed_this_iter = True
                    if q3_team and is_code_final(q3_team) and q4_team and is_code_final(q4_team):
                        if sf_game_2_obj.team1_code == 'Q3' and sf_game_2_obj.team2_code == 'Q4':
                            current_year_playoff_map['Q3'] = q3_team; current_year_playoff_map['Q4'] = q4_team; map_changed_this_iter = True
        
        resolved_playoff_maps_by_year_id[year_id_iter] = current_year_playoff_map

    # --- End of precomputation logic ---

    for year_obj_medal_calc in all_years: # Iterating through sorted all_years
        year_id_current = year_obj_medal_calc.id # Renamed for clarity


        gold, silver, bronze, fourth = None, None, None, None
        
        # Get the precomputed playoff map and games list for the current year
        current_playoff_map = resolved_playoff_maps_by_year_id.get(year_id_current, {})
        games_this_year = games_by_year_id.get(year_id_current, [])
        games_this_year_map_by_number = {g.game_number: g for g in games_this_year if g.game_number is not None}

        # Get bronze and final game numbers for the year
        # FINAL_BRONZE_GAME_NUMBERS_BY_YEAR = { year_id: (bronze_game_num, final_game_num), ... }
        # Default to (63, 64) if not specified for the year_id
        game_numbers = FINAL_BRONZE_GAME_NUMBERS_BY_YEAR.get(year_id_current, (63, 64)) 
        bronze_game_num, final_game_num = game_numbers[0], game_numbers[1]



        # Bronze Medal Game
        bronze_game = games_this_year_map_by_number.get(bronze_game_num)
        if bronze_game:

            if bronze_game.team1_score is not None and bronze_game.team2_score is not None:
                b_team1 = get_resolved_team_code(bronze_game.team1_code, current_playoff_map, games_this_year_map_by_number)
                b_team2 = get_resolved_team_code(bronze_game.team2_code, current_playoff_map, games_this_year_map_by_number)


                if is_code_final(b_team1) and is_code_final(b_team2):
                    if bronze_game.team1_score > bronze_game.team2_score:
                        bronze = b_team1
                        fourth = b_team2
                    else:
                        bronze = b_team2
                        fourth = b_team1
                    current_app.logger.info(f"MedalTally: Year {year_obj_medal_calc.year} - Bronze: {bronze}, Fourth: {fourth}")
                else:
                    current_app.logger.warning(f"MedalTally: Bronze game for {year_obj_medal_calc.year} (G#{bronze_game_num}) has non-final team codes: {b_team1} or {b_team2}. Medals might be incorrect.")
            else:
                current_app.logger.warning(f"MedalTally: Bronze game for {year_obj_medal_calc.year} (G#{bronze_game_num}) is missing scores. Cannot determine bronze/fourth.")
        else:
            current_app.logger.warning(f"MedalTally: Bronze game (expected G#{bronze_game_num}) not found for year {year_obj_medal_calc.year}.")

        # Final/Gold Medal Game
        final_game = games_this_year_map_by_number.get(final_game_num)
        if final_game:

            if final_game.team1_score is not None and final_game.team2_score is not None:
                f_team1 = get_resolved_team_code(final_game.team1_code, current_playoff_map, games_this_year_map_by_number)
                f_team2 = get_resolved_team_code(final_game.team2_code, current_playoff_map, games_this_year_map_by_number)


                if is_code_final(f_team1) and is_code_final(f_team2):
                    if final_game.team1_score > final_game.team2_score:
                        gold = f_team1
                        silver = f_team2
                    else:
                        gold = f_team2
                        silver = f_team1
                    current_app.logger.info(f"MedalTally: Year {year_obj_medal_calc.year} - Gold: {gold}, Silver: {silver}")
                else:
                    current_app.logger.warning(f"MedalTally: Final game for {year_obj_medal_calc.year} (G#{final_game_num}) has non-final team codes: {f_team1} or {f_team2}. Medals might be incorrect.")
            else:
                current_app.logger.warning(f"MedalTally: Final game for {year_obj_medal_calc.year} (G#{final_game_num}) is missing scores. Cannot determine gold/silver.")
        else:
            current_app.logger.warning(f"MedalTally: Final game (expected G#{final_game_num}) not found for year {year_obj_medal_calc.year}.")
            
        medal_tally_results.append({
            'year_obj': year_obj_medal_calc,
            'gold': gold,
            'silver': silver,
            'bronze': bronze,
            'fourth': fourth
        })

    # Already sorted by year desc by `all_years` query, but explicit sort here is fine.
    medal_tally_results.sort(key=lambda x: x['year_obj'].year, reverse=True)
    
    current_app.logger.info("Finished medal tally calculation.")
    return medal_tally_results

def get_all_player_stats(team_filter=None):
    """
    Calculates aggregated statistics (goals, assists, PIMs) for all players.
    
    Args:
        team_filter (str, optional): If provided, only return stats for players from this team.
    """
    current_app.logger.info(f"Starting player statistics calculation. Team filter: {team_filter}")

    # Subquery for Goals
    goals_sq = db.session.query(
        Goal.scorer_id.label("player_id"),
        func.count(Goal.id).label("num_goals")
    ).filter(Goal.scorer_id.isnot(None)) \
    .group_by(Goal.scorer_id).subquery()

    # Subquery for Primary Assists
    assists1_sq = db.session.query(
        Goal.assist1_id.label("player_id"),
        func.count(Goal.id).label("num_assists1")
    ).filter(Goal.assist1_id.isnot(None)) \
    .group_by(Goal.assist1_id).subquery()

    # Subquery for Secondary Assists
    assists2_sq = db.session.query(
        Goal.assist2_id.label("player_id"),
        func.count(Goal.id).label("num_assists2")
    ).filter(Goal.assist2_id.isnot(None)) \
    .group_by(Goal.assist2_id).subquery()

    # Subquery for PIMs
    # Create a list of WHEN clauses for the CASE statement from PIM_MAP
    pim_when_clauses = []
    for penalty_type_key, minutes in PIM_MAP.items():
        pim_when_clauses.append((Penalty.penalty_type == penalty_type_key, minutes))
    
    # Fallback for penalty types not in PIM_MAP - log them later if encountered
    # The `else_=0` in the case statement handles this for summing, but we need to identify them.
    # For now, we assume PIM_MAP is comprehensive or unmapped types default to 0.
    # To explicitly log unmapped types, a more complex query or post-processing might be needed.
    # Here, we rely on the else_=0 and can add a separate check later if required.
    
    pim_case_statement = case(
        *pim_when_clauses, # Unpack the list of tuples
        else_=0 # Default PIM value for unmapped types
    )

    pims_sq = db.session.query(
        Penalty.player_id.label("player_id"),
        func.sum(pim_case_statement).label("total_pims")
    ).filter(Penalty.player_id.isnot(None)) \
    .group_by(Penalty.player_id).subquery()

    # Main query to fetch players and join with aggregated stats
    player_stats_query = db.session.query(
        Player.id,
        Player.first_name,
        Player.last_name,
        Player.team_code,
        func.coalesce(goals_sq.c.num_goals, 0).label("goals"),
        func.coalesce(assists1_sq.c.num_assists1, 0).label("assists1_count"),
        func.coalesce(assists2_sq.c.num_assists2, 0).label("assists2_count"),
        func.coalesce(pims_sq.c.total_pims, 0).label("pims")
    ).select_from(Player) \
    .outerjoin(goals_sq, Player.id == goals_sq.c.player_id) \
    .outerjoin(assists1_sq, Player.id == assists1_sq.c.player_id) \
    .outerjoin(assists2_sq, Player.id == assists2_sq.c.player_id) \
    .outerjoin(pims_sq, Player.id == pims_sq.c.player_id)

    # Apply team filter if provided
    if team_filter:
        player_stats_query = player_stats_query.filter(Player.team_code == team_filter)

    # Log distinct penalty types from DB not in PIM_MAP
    # This is a separate query for logging purposes, run once.
    # It does not affect the main stats calculation which defaults unmapped types to 0 PIM.
    distinct_db_penalty_types = db.session.query(Penalty.penalty_type).distinct().all()
    unmapped_types = [pt[0] for pt in distinct_db_penalty_types if pt[0] not in PIM_MAP and pt[0] is not None]
    if unmapped_types:
        current_app.logger.warning(f"PlayerStats: Unmapped penalty types found in database, defaulted to 0 PIMs: {unmapped_types}")


    results = []
    for row in player_stats_query.all():
        assists = row.assists1_count + row.assists2_count
        scorer_points = row.goals + assists
        results.append({
            'first_name': row.first_name,
            'last_name': row.last_name,
            'team_code': row.team_code,
            'goals': row.goals,
            'assists': assists,
            'scorer_points': scorer_points,
            'pims': row.pims
        })

    # Sort results
    # Primary sort: scorer_points (descending), Secondary sort: goals (descending)
    results.sort(key=lambda x: (x['scorer_points'], x['goals']), reverse=True)
    
    current_app.logger.info(f"Finished player statistics calculation. Found {len(results)} players.")
    return results

@main_bp.route('/player-stats')
def player_stats_view():
    """
    Displays the player statistics page.
    Supports team filtering via 'team_filter' query parameter.
    """
    team_filter = request.args.get('team_filter', '').strip()
    if not team_filter:
        team_filter = None
    
    current_app.logger.info(f"Accessing player statistics page. Team filter: {team_filter}")
    player_stats_data = get_all_player_stats(team_filter=team_filter)
    # TEAM_ISO_CODES is already imported in this file
    return render_template('player_stats.html', player_stats=player_stats_data, team_iso_codes=TEAM_ISO_CODES)

@main_bp.route('/edit-players', methods=['GET', 'POST'])
def edit_players():
    """
    Route to edit player information (first name, last name, jersey number).
    Shows countries on the left and players for selected country on the right.
    """
    if request.method == 'POST':
        # Handle player updates
        player_id = request.form.get('player_id')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        jersey_number_str = request.form.get('jersey_number')
        
        if not player_id or not first_name or not last_name:
            flash('Spieler-ID, Vorname und Nachname sind erforderlich.', 'danger')
        else:
            try:
                player = db.session.get(Player, int(player_id))
                if not player:
                    flash('Spieler nicht gefunden.', 'danger')
                else:
                    # Update player information
                    player.first_name = first_name.strip()
                    player.last_name = last_name.strip()
                    
                    # Handle jersey number
                    if jersey_number_str and jersey_number_str.strip():
                        try:
                            player.jersey_number = int(jersey_number_str.strip())
                        except ValueError:
                            flash('Ungültige Trikotnummer.', 'warning')
                            return redirect(url_for('main_bp.edit_players'))
                    else:
                        player.jersey_number = None
                    
                    db.session.commit()
                    flash(f'Spieler {first_name} {last_name} erfolgreich aktualisiert!', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error updating player: {str(e)}")
                flash(f'Fehler beim Aktualisieren des Spielers: {str(e)}', 'danger')
        
        return redirect(url_for('main_bp.edit_players'))
    
    # GET request - show the edit page
    # Get all countries/teams that have players
    countries_with_players = db.session.query(Player.team_code).distinct().order_by(Player.team_code).all()
    countries = [country[0] for country in countries_with_players if country[0] in TEAM_ISO_CODES and TEAM_ISO_CODES[country[0]] is not None]
    
    # Get selected country from query parameter
    selected_country = request.args.get('country', countries[0] if countries else None)
    
    # Get players for selected country
    players = []
    if selected_country:
        players = Player.query.filter_by(team_code=selected_country).order_by(Player.last_name, Player.first_name).all()
    
    return render_template('edit_players.html', 
                         countries=countries, 
                         selected_country=selected_country, 
                         players=players,
                         team_iso_codes=TEAM_ISO_CODES)

@main_bp.route('/add-player-global', methods=['POST'])
def add_player_global():
    """
    Route to add a new player globally (not tied to a specific game/year).
    """
    team_code = request.form.get('team_code')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    jersey_number_str = request.form.get('jersey_number')
    
    if not team_code or not first_name or not last_name:
        flash('Team, Vorname und Nachname sind erforderlich.', 'danger')
        return redirect(url_for('main_bp.edit_players'))
    
    try:
        # Handle jersey number
        jersey_number = None
        if jersey_number_str and jersey_number_str.strip():
            try:
                jersey_number = int(jersey_number_str.strip())
            except ValueError:
                flash('Ungültige Trikotnummer.', 'warning')
                return redirect(url_for('main_bp.edit_players'))
        
        # Check if player already exists
        existing_player = Player.query.filter_by(
            team_code=team_code, 
            first_name=first_name.strip(), 
            last_name=last_name.strip()
        ).first()
        
        if existing_player:
            flash(f'Spieler {first_name} {last_name} ({team_code}) existiert bereits.', 'warning')
        else:
            new_player = Player(
                team_code=team_code,
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                jersey_number=jersey_number
            )
            db.session.add(new_player)
            db.session.commit()
            flash(f'Spieler {first_name} {last_name} erfolgreich hinzugefügt!', 'success')
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding player: {str(e)}")
        flash(f'Fehler beim Hinzufügen des Spielers: {str(e)}', 'danger')
    
    return redirect(url_for('main_bp.edit_players', country=team_code))