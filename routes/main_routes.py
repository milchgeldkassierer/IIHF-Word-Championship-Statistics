import os
import json
from typing import Dict, List
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from models import db, ChampionshipYear, Game, AllTimeTeamStats, TeamStats, Player, Goal, Penalty
from constants import TEAM_ISO_CODES, PRELIM_ROUNDS, PLAYOFF_ROUNDS, PIM_MAP
from utils import get_resolved_team_code, is_code_final, resolve_game_participants, _apply_head_to_head_tiebreaker
from sqlalchemy import func, case
import traceback

main_bp = Blueprint('main_bp', __name__)

def resolve_fixture_path(relative_path):
    """
    Converts a relative fixture path to an absolute path.
    For files starting with 'fixtures/', looks in BASE_DIR/fixtures/
    For other files, looks in UPLOAD_FOLDER/
    """
    if not relative_path:
        return None
    
    if relative_path.startswith('fixtures/'):
        filename = relative_path[9:]
        absolute_path = os.path.join(current_app.config['BASE_DIR'], 'fixtures', filename)
    else:
        absolute_path = os.path.join(current_app.config['UPLOAD_FOLDER'], relative_path)
    
    return absolute_path

def get_tournament_statistics(year_obj):
    """
    Calculate tournament statistics: games completed, total games, and winner
    Returns dict with: total_games, completed_games, winner
    """
    if not year_obj:
        return {'total_games': 0, 'completed_games': 0, 'winner': None}
    
    all_games = Game.query.filter_by(year_id=year_obj.id).all()
    total_games = len(all_games)
    
    completed_games = sum(1 for game in all_games if game.team1_score is not None and game.team2_score is not None)
    
    winner = None
    if completed_games == total_games and total_games > 0:
        final_game = None
        
        for game in all_games:
            if game.round and ('final' in game.round.lower() or 'gold medal' in game.round.lower() or 'gold' in game.round.lower()):
                final_game = game
                break
        
        if not final_game and all_games:
            max_game_number = max(game.game_number for game in all_games if game.game_number is not None)
            for game in all_games:
                if game.game_number == max_game_number:
                    final_game = game
                    break
                    
        if final_game and final_game.team1_score is not None and final_game.team2_score is not None:
            try:
                resolved_team1, resolved_team2 = resolve_game_participants(final_game, year_obj, all_games)
                
                if final_game.team1_score > final_game.team2_score:
                    winner = resolved_team1
                elif final_game.team2_score > final_game.team1_score:
                    winner = resolved_team2
            except Exception:
                if final_game.team1_score > final_game.team2_score:
                    winner = final_game.team1_code
                elif final_game.team2_score > final_game.team1_score:
                    winner = final_game.team2_code
    
    return {
        'total_games': total_games,
        'completed_games': completed_games,
        'winner': winner
    }

def calculate_all_time_standings():
    """
    Calculates all-time standings for all teams based on game results.
    This version precomputes playoff maps for each year.
    """
    all_games = Game.query.options(db.joinedload(Game.championship_year)).all()
    year_objects_map = {year.id: year for year in ChampionshipYear.query.all()}

    games_by_year_id = {}
    for game_obj in all_games:
        games_by_year_id.setdefault(game_obj.year_id, []).append(game_obj)

    resolved_playoff_maps_by_year_id = {}

    for year_id, games_in_this_year in games_by_year_id.items():
        year_obj = year_objects_map.get(year_id)
        if not year_obj:
            current_app.logger.warning(f"Year object not found for year_id {year_id}. Skipping playoff map generation for this year.")
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
                if game_prelim.team1_score > game_prelim.team2_score: 
                    (t1_stats.w, t1_stats.pts, t2_stats.l) = (t1_stats.w+1, t1_stats.pts+3, t2_stats.l+1)
                else: 
                    (t2_stats.w, t2_stats.pts, t1_stats.l) = (t2_stats.w+1, t2_stats.pts+3, t1_stats.l+1)
            elif game_prelim.result_type == 'OT':
                if game_prelim.team1_score > game_prelim.team2_score: 
                    (t1_stats.otw, t1_stats.pts, t2_stats.otl, t2_stats.pts) = (t1_stats.otw+1, t1_stats.pts+2, t2_stats.otl+1, t2_stats.pts+1)
                else: 
                    (t2_stats.otw, t2_stats.pts, t1_stats.otl, t1_stats.pts) = (t2_stats.otw+1, t2_stats.pts+2, t1_stats.otl+1, t1_stats.pts+1)
            elif game_prelim.result_type == 'SO':
                if game_prelim.team1_score > game_prelim.team2_score: 
                    (t1_stats.sow, t1_stats.pts, t2_stats.sol, t2_stats.pts) = (t1_stats.sow+1, t1_stats.pts+2, t2_stats.sol+1, t2_stats.pts+1)
                else: 
                    (t2_stats.sow, t2_stats.pts, t1_stats.sol, t1_stats.pts) = (t2_stats.sow+1, t2_stats.pts+2, t1_stats.sol+1, t1_stats.pts+1)

        prelim_standings_by_group_this_year: Dict[str, List[TeamStats]] = {}
        for ts_obj in prelim_stats_map_this_year.values():
            group_key = ts_obj.group if ts_obj.group else "UnknownGroup"
            prelim_standings_by_group_this_year.setdefault(group_key, []).append(ts_obj)
        
        for group_list in prelim_standings_by_group_this_year.values():
            group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
            group_list = _apply_head_to_head_tiebreaker(group_list, prelim_games_for_standings_calc)
            for i, ts_in_group in enumerate(group_list):
                ts_in_group.rank_in_group = i + 1
        
        current_year_playoff_map: Dict[str, str] = {}
        all_games_this_year_map_by_number: Dict[int, Game] = {g.game_number: g for g in games_in_this_year if g.game_number is not None}

        qf_gns, sf_gns, h_tcs = [], [], []
        fixture_absolute_path = resolve_fixture_path(year_obj.fixture_path)
        if year_obj.fixture_path and fixture_absolute_path and os.path.exists(fixture_absolute_path):
            try:
                with open(fixture_absolute_path, 'r', encoding='utf-8') as f: 
                    fixture_data = json.load(f)
                qf_gns = fixture_data.get("qf_game_numbers") or [57, 58, 59, 60]
                sf_gns = fixture_data.get("sf_game_numbers") or [61, 62]
                h_tcs = fixture_data.get("host_teams", [])
            except (json.JSONDecodeError, OSError): 
                qf_gns = [57, 58, 59, 60]; sf_gns = [61, 62]
        else: 
            qf_gns = [57, 58, 59, 60]; sf_gns = [61, 62]

        for grp_name_iter, grp_teams_stats_list in prelim_standings_by_group_this_year.items():
            for team_s in grp_teams_stats_list:
                group_letter = team_s.group
                if group_letter and group_letter.startswith("Group "):
                    group_letter = group_letter.replace("Group ", "")
                current_year_playoff_map[f"{group_letter}{team_s.rank_in_group}"] = team_s.name
                if h_tcs and team_s.name in h_tcs: 
                    current_year_playoff_map[f"H{team_s.rank_in_group}"] = team_s.name
        
        if qf_gns and len(qf_gns) >= 4:
            for i, qf_game_num in enumerate(qf_gns[:4]):
                qf_winner_placeholder = f"Q{i+1}"
                game_winner_placeholder = f"W({qf_game_num})"
                current_year_playoff_map[qf_winner_placeholder] = game_winner_placeholder

        max_iter_passes, current_pass, map_changed_this_iter = 10, 0, True
        while map_changed_this_iter and current_pass < max_iter_passes:
            map_changed_this_iter = False; current_pass += 1
            for pk, mc in list(current_year_playoff_map.items()):
                if not is_code_final(mc):
                    rc = get_resolved_team_code(mc, current_year_playoff_map, all_games_this_year_map_by_number)
                    if rc != mc and is_code_final(rc): 
                        current_year_playoff_map[pk] = rc; map_changed_this_iter = True
            
            for g_playoff in games_in_this_year:
                if g_playoff.round in PLAYOFF_ROUNDS and g_playoff.game_number and \
                   g_playoff.team1_score is not None and g_playoff.team2_score is not None:
                    rt1 = get_resolved_team_code(g_playoff.team1_code, current_year_playoff_map, all_games_this_year_map_by_number)
                    rt2 = get_resolved_team_code(g_playoff.team2_code, current_year_playoff_map, all_games_this_year_map_by_number)
                    if not is_code_final(rt1) or not is_code_final(rt2): 
                        continue
                    
                    wac = rt1 if g_playoff.team1_score > g_playoff.team2_score else rt2
                    lac = rt2 if g_playoff.team1_score > g_playoff.team2_score else rt1
                    wp, lp = f"W({g_playoff.game_number})", f"L({g_playoff.game_number})"
                    if current_year_playoff_map.get(wp) != wac: 
                        current_year_playoff_map[wp] = wac; map_changed_this_iter = True
                    if current_year_playoff_map.get(lp) != lac: 
                        current_year_playoff_map[lp] = lac; map_changed_this_iter = True
                    
                    if sf_gns and g_playoff.game_number in sf_gns:
                        sf_index = sf_gns.index(g_playoff.game_number) + 1
                        sf_winner_placeholder = f"W(SF{sf_index})"
                        sf_loser_placeholder = f"L(SF{sf_index})"
                        if current_year_playoff_map.get(sf_winner_placeholder) != wac: 
                            current_year_playoff_map[sf_winner_placeholder] = wac; map_changed_this_iter = True
                        if current_year_playoff_map.get(sf_loser_placeholder) != lac: 
                            current_year_playoff_map[sf_loser_placeholder] = lac; map_changed_this_iter = True
            
            if sf_gns and len(sf_gns) >= 2:
                sf_game_1 = all_games_this_year_map_by_number.get(sf_gns[0])
                sf_game_2 = all_games_this_year_map_by_number.get(sf_gns[1])
                
                if sf_game_1 and sf_game_2:
                    q1_team = current_year_playoff_map.get('Q1')
                    q2_team = current_year_playoff_map.get('Q2') 
                    q3_team = current_year_playoff_map.get('Q3')
                    q4_team = current_year_playoff_map.get('Q4')
                    
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
                    
        resolved_playoff_maps_by_year_id[year_id] = current_year_playoff_map

    all_time_stats_dict = {}
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
            current_year_playoff_map = {}

        current_year_games_list = games_by_year_id.get(year_id, [])
        current_year_games_map_by_number = {g.game_number: g for g in current_year_games_list if g.game_number is not None}

        resolved_team1_code = get_resolved_team_code(game.team1_code, current_year_playoff_map, current_year_games_map_by_number)
        resolved_team2_code = get_resolved_team_code(game.team2_code, current_year_playoff_map, current_year_games_map_by_number)
        
        if game.round in ['SF', 'F'] or game.game_number in [61, 62, 63, 64]:
            pass

        has_final_resolved_codes = is_code_final(resolved_team1_code) and is_code_final(resolved_team2_code)
        has_final_original_codes = is_code_final(game.team1_code) and is_code_final(game.team2_code)
        
        if not (has_final_resolved_codes or has_final_original_codes):
            skipped_games_count = getattr(calculate_all_time_standings, '_skipped_count', 0) + 1
            calculate_all_time_standings._skipped_count = skipped_games_count
            continue
            
        if has_final_resolved_codes:
            final_team1_code = resolved_team1_code
            final_team2_code = resolved_team2_code
        else:
            final_team1_code = game.team1_code
            final_team2_code = game.team2_code
            
        year_of_game = game.championship_year.year if game.championship_year else None

        if final_team1_code not in all_time_stats_dict:
            all_time_stats_dict[final_team1_code] = AllTimeTeamStats(team_code=final_team1_code)
        team1_stats = all_time_stats_dict[final_team1_code]
        
        if final_team2_code not in all_time_stats_dict:
            all_time_stats_dict[final_team2_code] = AllTimeTeamStats(team_code=final_team2_code)
        team2_stats = all_time_stats_dict[final_team2_code]

        if year_of_game:
            team1_stats.years_participated.add(year_of_game)
            team2_stats.years_participated.add(year_of_game)

        team1_stats.gp += 1
        team2_stats.gp += 1
        team1_stats.gf += game.team1_score
        team1_stats.ga += game.team2_score
        team2_stats.gf += game.team2_score
        team2_stats.ga += game.team1_score
        
        if game.team1_score > game.team2_score:
            winner_stats, loser_stats = team1_stats, team2_stats
        else:
            winner_stats, loser_stats = team2_stats, team1_stats
        
        if game.result_type == 'REG':
            winner_stats.w += 1; winner_stats.pts += 3
            loser_stats.l += 1
        elif game.result_type == 'OT':
            winner_stats.otw += 1; winner_stats.pts += 2
            loser_stats.otl += 1; loser_stats.pts += 1
        elif game.result_type == 'SO':
            winner_stats.sow += 1; winner_stats.pts += 2
            loser_stats.sol += 1; loser_stats.pts += 1
        elif game.result_type:
             current_app.logger.warning(f"Game ID {game.id} has unhandled result_type: '{game.result_type}'. Points not assigned for this type.")

    final_all_time_standings = list(all_time_stats_dict.values())
    final_all_time_standings.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
    
    skipped_count = getattr(calculate_all_time_standings, '_skipped_count', 0)
    if skipped_count > 0:
        current_app.logger.info(f"All-time standings calculated. Skipped {skipped_count} games with non-final team codes (placeholder/unresolved teams).")
        calculate_all_time_standings._skipped_count = 0
    
    return final_all_time_standings

@main_bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'delete_year' in request.form:
            year_id_to_delete = request.form.get('year_id_to_delete')
            year_obj_del = db.session.get(ChampionshipYear, year_id_to_delete)
            if year_obj_del:
                if year_obj_del.fixture_path:
                    absolute_fixture_path = resolve_fixture_path(year_obj_del.fixture_path)
                    if absolute_fixture_path and os.path.exists(absolute_fixture_path):
                        try:
                            abs_fixture_path = os.path.abspath(absolute_fixture_path)
                            abs_upload_folder = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
                            if abs_fixture_path.startswith(abs_upload_folder):
                                 os.remove(absolute_fixture_path)
                                 flash(f'Associated fixture file "{os.path.basename(absolute_fixture_path)}" from data directory deleted.', 'info')
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
            flash('Name and Year are required.', 'danger')
            return redirect(url_for('main_bp.index'))
            
        try: 
            year_int = int(year_str)
        except ValueError: 
            flash('Year must be a number.', 'danger')
            return redirect(url_for('main_bp.index'))

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
            relative_fixture_path = None

            path_in_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], potential_fixture_filename)
            if os.path.exists(path_in_upload_folder):
                fixture_path_to_load = path_in_upload_folder
                relative_fixture_path = potential_fixture_filename
            else:
                path_in_root_fixtures = os.path.join(current_app.config['BASE_DIR'], 'fixtures', potential_fixture_filename)
                if os.path.exists(path_in_root_fixtures):
                    fixture_path_to_load = path_in_root_fixtures
                    relative_fixture_path = f"fixtures/{potential_fixture_filename}"
            
            if not fixture_path_to_load and target_year_obj.id:
                 potential_id_fixture_filename = f"{target_year_obj.id}_{year_str}.json"
                 path_id_in_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], potential_id_fixture_filename)
                 if os.path.exists(path_id_in_upload_folder):
                      fixture_path_to_load = path_id_in_upload_folder
                      relative_fixture_path = potential_id_fixture_filename

            if fixture_path_to_load:
                Game.query.filter_by(year_id=target_year_obj.id).delete()
                try:
                    target_year_obj.fixture_path = relative_fixture_path
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
    
    for year in all_years_db:
        year.stats = get_tournament_statistics(year)
    
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

    medal_data = get_medal_tally_data()
    medal_data_by_year = {medal_entry['year_obj'].year: medal_entry for medal_entry in medal_data}

    return render_template('index.html', all_years=all_years_db, available_fixture_years=sorted_fixture_years, team_iso_codes=TEAM_ISO_CODES, medal_data_by_year=medal_data_by_year)

@main_bp.route('/all-time-standings')
def all_time_standings_view():
    standings_data = calculate_all_time_standings()
    return render_template('all_time_standings.html', standings_data=standings_data, team_iso_codes=TEAM_ISO_CODES)

@main_bp.route('/medal-tally')
def medal_tally_view():
    current_app.logger.info("Accessing medal tally page.")
    medal_data = get_medal_tally_data()
    return render_template('medal_tally.html', medal_data=medal_data, team_iso_codes=TEAM_ISO_CODES)

def calculate_complete_final_ranking(year_obj, games_this_year, playoff_map, year_obj_for_map):
    final_ranking = {}
    
    def trace_team_from_medal_games():
        sf_games = [g for g in games_this_year if g.round == "Semifinals" and g.team1_score is not None and g.team2_score is not None]
        
        sf_results = {}
        for sf_game in sf_games:
            winner = sf_game.team1_code if sf_game.team1_score > sf_game.team2_score else sf_game.team2_code
            loser = sf_game.team2_code if sf_game.team1_score > sf_game.team2_score else sf_game.team1_code
            
            if sf_game.game_number == 61:  # SF1
                sf_results["W(SF1)"] = winner
                sf_results["L(SF1)"] = loser
            elif sf_game.game_number == 62:  # SF2  
                sf_results["W(SF2)"] = winner
                sf_results["L(SF2)"] = loser
        
        team_map = {}
        prelim_games = [g for g in games_this_year if g.round in PRELIM_ROUNDS and is_code_final(g.team1_code) and is_code_final(g.team2_code)]
        
        group_standings = {}
        for game in prelim_games:
            if game.team1_score is None or game.team2_score is None:
                continue
                
            group = game.group
            if not group:
                continue
                
            if group not in group_standings:
                group_standings[group] = {}
                
            for team in [game.team1_code, game.team2_code]:
                if team not in group_standings[group]:
                    group_standings[group][team] = {'pts': 0, 'gf': 0, 'ga': 0}
            
            t1_score, t2_score = game.team1_score, game.team2_score
            group_standings[group][game.team1_code]['gf'] += t1_score
            group_standings[group][game.team1_code]['ga'] += t2_score
            group_standings[group][game.team2_code]['gf'] += t2_score  
            group_standings[group][game.team2_code]['ga'] += t1_score
            
            if game.result_type == 'REG':
                if t1_score > t2_score:
                    group_standings[group][game.team1_code]['pts'] += 3
                else:
                    group_standings[group][game.team2_code]['pts'] += 3
            elif game.result_type in ['OT', 'SO']:
                if t1_score > t2_score:
                    group_standings[group][game.team1_code]['pts'] += 2
                    group_standings[group][game.team2_code]['pts'] += 1
                else:
                    group_standings[group][game.team2_code]['pts'] += 2
                    group_standings[group][game.team1_code]['pts'] += 1
        
        for group, teams in group_standings.items():
            team_stats_list = []
            for team_name, stats in teams.items():
                ts = TeamStats(name=team_name, group=group)
                ts.pts = stats['pts']
                ts.gf = stats['gf'] 
                ts.ga = stats['ga']
                team_stats_list.append(ts)
            
            team_stats_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
            team_stats_list = _apply_head_to_head_tiebreaker(team_stats_list, prelim_games)
            
            group_letter = group.replace("Group ", "") if group.startswith("Group ") else group
            for i, team_stat in enumerate(team_stats_list, 1):
                team_map[f"{group_letter}{i}"] = team_stat.name
        
        qf_games = [g for g in games_this_year if g.round == "Quarterfinals" and g.team1_score is not None and g.team2_score is not None]
        qf_games.sort(key=lambda x: x.game_number or 0)
        
        qf_winners = []
        for qf_game in qf_games:
            winner_code = qf_game.team1_code if qf_game.team1_score > qf_game.team2_score else qf_game.team2_code
            if winner_code in team_map:
                actual_team = team_map[winner_code]
                qf_winners.append(actual_team)
            else:
                qf_winners.append(winner_code)
        
        qf_winner_stats = []
        for actual_team in qf_winners:
            team_rank_in_group = None
            team_group = None
            team_stats = None
            
            for placeholder, mapped_team in team_map.items():
                if mapped_team == actual_team:
                    if len(placeholder) >= 2:
                        team_group = placeholder[0]
                        try:
                            team_rank_in_group = int(placeholder[1:])
                        except ValueError:
                            continue
                    break
            
            for group, teams in group_standings.items():
                group_letter = group.replace("Group ", "") if group.startswith("Group ") else group
                if group_letter == team_group and actual_team in teams:
                    team_stats = teams[actual_team]
                    break
            
            if team_rank_in_group and team_stats:
                qf_winner_stats.append({
                    'team': actual_team,
                    'group': team_group,
                    'rank_in_group': team_rank_in_group,
                    'pts': team_stats['pts'],
                    'gd': team_stats['gf'] - team_stats['ga'],
                    'gf': team_stats['gf']
                })
        
        qf_winner_stats.sort(key=lambda x: (x['rank_in_group'], -x['pts'], -x['gd'], -x['gf']))
        
        qf_results = {}
        if len(qf_winner_stats) >= 4:
            qf_results["Q1"] = qf_winner_stats[0]['team']
            qf_results["Q2"] = qf_winner_stats[3]['team']
            qf_results["Q3"] = qf_winner_stats[1]['team']
            qf_results["Q4"] = qf_winner_stats[2]['team']
        
        def resolve_code(code):
            if is_code_final(code):
                return code
            if code in team_map:
                return team_map[code]
            if code in qf_results:
                return resolve_code(qf_results[code])
            if code in sf_results:
                return resolve_code(sf_results[code])
            return code
        
        return resolve_code
    
    resolve_team = trace_team_from_medal_games()
    
    games_map = {g.game_number: g for g in games_this_year if g.game_number is not None}
    
    bronze_game = None
    for game in games_this_year:
        if game.round == "Bronze Medal Game" and game.team1_score is not None and game.team2_score is not None:
            bronze_game = game
            break
    
    final_game = None
    for game in games_this_year:
        if game.round == "Gold Medal Game" and game.team1_score is not None and game.team2_score is not None:
            final_game = game
            break
    
    if bronze_game:
        team1_resolved = resolve_team(bronze_game.team1_code)
        team2_resolved = resolve_team(bronze_game.team2_code)
        
        if bronze_game.team1_score > bronze_game.team2_score:
            final_ranking[3] = team1_resolved
            final_ranking[4] = team2_resolved
        else:
            final_ranking[3] = team2_resolved
            final_ranking[4] = team1_resolved
    
    if final_game:
        team1_resolved = resolve_team(final_game.team1_code)
        team2_resolved = resolve_team(final_game.team2_code)
        
        if final_game.team1_score > final_game.team2_score:
            final_ranking[1] = team1_resolved
            final_ranking[2] = team2_resolved
        else:
            final_ranking[1] = team2_resolved
            final_ranking[2] = team1_resolved

    prelim_stats_map = {}
    prelim_games = [
        g for g in games_this_year
        if g.round in PRELIM_ROUNDS and \
           is_code_final(g.team1_code) and \
           is_code_final(g.team2_code) and \
           g.team1_score is not None and g.team2_score is not None
    ]
    
    for game in prelim_games:
        current_game_group = game.group or "N/A"
        for team_code in [game.team1_code, game.team2_code]:
            if team_code not in prelim_stats_map:
                prelim_stats_map[team_code] = TeamStats(name=team_code, group=current_game_group)
            elif prelim_stats_map[team_code].group == "N/A" and current_game_group != "N/A":
                prelim_stats_map[team_code].group = current_game_group
        
        t1_stats = prelim_stats_map[game.team1_code]
        t2_stats = prelim_stats_map[game.team2_code]
        
        t1_stats.gp += 1; t2_stats.gp += 1
        t1_stats.gf += game.team1_score; t1_stats.ga += game.team2_score
        t2_stats.gf += game.team2_score; t2_stats.ga += game.team1_score
        
        if game.result_type == 'REG':
            if game.team1_score > game.team2_score: 
                t1_stats.w += 1; t1_stats.pts += 3; t2_stats.l += 1
            else: 
                t2_stats.w += 1; t2_stats.pts += 3; t1_stats.l += 1
        elif game.result_type == 'OT':
            if game.team1_score > game.team2_score: 
                t1_stats.otw += 1; t1_stats.pts += 2; t2_stats.otl += 1; t2_stats.pts += 1
            else: 
                t2_stats.otw += 1; t2_stats.pts += 2; t1_stats.otl += 1; t1_stats.pts += 1
        elif game.result_type == 'SO':
            if game.team1_score > game.team2_score: 
                t1_stats.sow += 1; t1_stats.pts += 2; t2_stats.sol += 1; t2_stats.pts += 1
            else: 
                t2_stats.sow += 1; t2_stats.pts += 2; t1_stats.sol += 1; t1_stats.pts += 1
    
    standings_by_group = {}
    for ts in prelim_stats_map.values():
        group_key = ts.group if ts.group else "UnknownGroup"
        standings_by_group.setdefault(group_key, []).append(ts)
    
    for group_list in standings_by_group.values():
        group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        group_list = _apply_head_to_head_tiebreaker(group_list, prelim_games)
        for i, ts in enumerate(group_list):
            ts.rank_in_group = i + 1
    
    qf_losers = []
    qf_games = [g for g in games_this_year if g.round == "Quarterfinals" and g.team1_score is not None and g.team2_score is not None]
    
    for qf_game in qf_games:
        loser_code = qf_game.team2_code if qf_game.team1_score > qf_game.team2_score else qf_game.team1_code
        loser_resolved = resolve_team(loser_code)
        if is_code_final(loser_resolved):
            qf_losers.append(loser_resolved)
    
    qf_losers_stats = [prelim_stats_map.get(team) for team in qf_losers if team in prelim_stats_map]
    qf_losers_stats = [ts for ts in qf_losers_stats if ts is not None]
    qf_losers_stats.sort(key=lambda x: (x.rank_in_group, -x.pts, -x.gd, -x.gf))
    
    for i, ts in enumerate(qf_losers_stats):
        if 5 + i <= 8:
            final_ranking[5 + i] = ts.name
    
    all_playoff_teams = set(final_ranking.values())
    remaining_teams = []
    
    for ts in prelim_stats_map.values():
        if ts.name not in all_playoff_teams:
            remaining_teams.append(ts)
    
    remaining_teams.sort(key=lambda x: (x.rank_in_group, -x.pts, -x.gd, -x.gf))
    
    current_position = 9
    for ts in remaining_teams:
        if current_position <= 16:
            final_ranking[current_position] = ts.name
            current_position += 1

    return final_ranking

def get_medal_tally_data():
    current_app.logger.info("Starting medal tally calculation.")
    medal_tally_results = []

    all_games = Game.query.options(db.joinedload(Game.championship_year)).all()
    all_years = ChampionshipYear.query.order_by(ChampionshipYear.year.desc()).all()
    year_objects_map = {year.id: year for year in all_years}

    completed_years = []
    for year_obj in all_years:
        tournament_stats = get_tournament_statistics(year_obj)
        is_completed = (tournament_stats['total_games'] > 0 and 
                       tournament_stats['completed_games'] == tournament_stats['total_games'])
        if is_completed:
            completed_years.append(year_obj)
            current_app.logger.info(f"Including completed tournament: {year_obj.year} ({tournament_stats['completed_games']}/{tournament_stats['total_games']} games)")
        else:
            current_app.logger.info(f"Excluding incomplete tournament: {year_obj.year} ({tournament_stats['completed_games']}/{tournament_stats['total_games']} games)")

    games_by_year_id = {}
    for game_obj in all_games:
        games_by_year_id.setdefault(game_obj.year_id, []).append(game_obj)

    resolved_playoff_maps_by_year_id = {}

    for year_obj_for_map in completed_years:
        year_id_iter = year_obj_for_map.id
        games_in_this_year = games_by_year_id.get(year_id_iter, [])
        
        if not games_in_this_year:
            current_app.logger.warning(f"MedalTally: No games found for completed year_id {year_id_iter}. Skipping.")
            continue

        prelim_stats_map_this_year = {}
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

        prelim_standings_by_group_this_year = {}
        for ts_obj in prelim_stats_map_this_year.values():
            group_key = ts_obj.group if ts_obj.group else "UnknownGroup"
            prelim_standings_by_group_this_year.setdefault(group_key, []).append(ts_obj)
        
        for group_list in prelim_standings_by_group_this_year.values():
            group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
            group_list = _apply_head_to_head_tiebreaker(group_list, prelim_games_for_standings_calc)
            for i, ts_in_group in enumerate(group_list):
                ts_in_group.rank_in_group = i + 1
        
        current_year_playoff_map = {}
        all_games_this_year_map_by_number_local = {g.game_number: g for g in games_in_this_year if g.game_number is not None}

        qf_gns, sf_gns, h_tcs = [], [], []
        fixture_absolute_path = resolve_fixture_path(year_obj_for_map.fixture_path)
        if year_obj_for_map.fixture_path and fixture_absolute_path and os.path.exists(fixture_absolute_path):
            try:
                with open(fixture_absolute_path, 'r', encoding='utf-8') as f: 
                    fixture_data = json.load(f)
                qf_gns = fixture_data.get("qf_game_numbers") or [57, 58, 59, 60]
                sf_gns = fixture_data.get("sf_game_numbers") or [61, 62]
                h_tcs = fixture_data.get("host_teams", [])
            except (json.JSONDecodeError, OSError): 
                qf_gns = [57, 58, 59, 60]; sf_gns = [61, 62]
        else: 
            qf_gns = [57, 58, 59, 60]; sf_gns = [61, 62]

        for grp_name_iter, grp_teams_stats_list in prelim_standings_by_group_this_year.items():
            for team_s in grp_teams_stats_list:
                group_letter = team_s.group
                if group_letter and group_letter.startswith("Group "):
                    group_letter = group_letter.replace("Group ", "")
                current_year_playoff_map[f"{group_letter}{team_s.rank_in_group}"] = team_s.name
                if h_tcs and team_s.name in h_tcs: 
                    current_year_playoff_map[f"H{team_s.rank_in_group}"] = team_s.name

        if qf_gns and len(qf_gns) >= 4:
            for i, qf_game_num in enumerate(qf_gns[:4]):
                current_year_playoff_map[f"Q{i+1}"] = f"W({qf_game_num})"
        
        max_iter_passes, current_pass, map_changed_this_iter = 10, 0, True
        while map_changed_this_iter and current_pass < max_iter_passes:
            map_changed_this_iter = False; current_pass += 1
            for pk, mc in list(current_year_playoff_map.items()):
                if not is_code_final(mc):
                    rc = get_resolved_team_code(mc, current_year_playoff_map, all_games_this_year_map_by_number_local)
                    if rc != mc and is_code_final(rc): 
                        current_year_playoff_map[pk] = rc; map_changed_this_iter = True
            
            for g_playoff in games_in_this_year:
                if g_playoff.round in PLAYOFF_ROUNDS and g_playoff.game_number and \
                   g_playoff.team1_score is not None and g_playoff.team2_score is not None:
                    rt1 = get_resolved_team_code(g_playoff.team1_code, current_year_playoff_map, all_games_this_year_map_by_number_local)
                    rt2 = get_resolved_team_code(g_playoff.team2_code, current_year_playoff_map, all_games_this_year_map_by_number_local)
                    if not is_code_final(rt1) or not is_code_final(rt2): 
                        continue
                    
                    wac = rt1 if g_playoff.team1_score > g_playoff.team2_score else rt2
                    lac = rt2 if g_playoff.team1_score > g_playoff.team2_score else rt1
                    wp, lp = f"W({g_playoff.game_number})", f"L({g_playoff.game_number})"
                    if current_year_playoff_map.get(wp) != wac: 
                        current_year_playoff_map[wp] = wac; map_changed_this_iter = True
                    if current_year_playoff_map.get(lp) != lac: 
                        current_year_playoff_map[lp] = lac; map_changed_this_iter = True
                    
                    if sf_gns and g_playoff.game_number in sf_gns:
                        sf_index = sf_gns.index(g_playoff.game_number) + 1
                        sf_winner_placeholder = f"W(SF{sf_index})"
                        sf_loser_placeholder = f"L(SF{sf_index})"
                        if current_year_playoff_map.get(sf_winner_placeholder) != wac: 
                            current_year_playoff_map[sf_winner_placeholder] = wac; map_changed_this_iter = True
                        if current_year_playoff_map.get(sf_loser_placeholder) != lac: 
                            current_year_playoff_map[sf_loser_placeholder] = lac; map_changed_this_iter = True
            
            if sf_gns and len(sf_gns) >= 2:
                sf_game_1_obj = all_games_this_year_map_by_number_local.get(sf_gns[0])
                sf_game_2_obj = all_games_this_year_map_by_number_local.get(sf_gns[1])
                
                if sf_game_1_obj and sf_game_2_obj:
                    q1_team = current_year_playoff_map.get('Q1')
                    q2_team = current_year_playoff_map.get('Q2') 
                    q3_team = current_year_playoff_map.get('Q3')
                    q4_team = current_year_playoff_map.get('Q4')
                    
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

                    if q1_team and is_code_final(q1_team) and q2_team and is_code_final(q2_team):
                        if sf_game_1_obj.team1_code == 'Q1' and sf_game_1_obj.team2_code == 'Q2':
                            current_year_playoff_map['Q1'] = q1_team
                            current_year_playoff_map['Q2'] = q2_team
                            map_changed_this_iter = True

                    if q3_team and is_code_final(q3_team) and q4_team and is_code_final(q4_team):
                        if sf_game_2_obj.team1_code == 'Q3' and sf_game_2_obj.team2_code == 'Q4':
                            current_year_playoff_map['Q3'] = q3_team
                            current_year_playoff_map['Q4'] = q4_team
                            map_changed_this_iter = True
                    
        resolved_playoff_maps_by_year_id[year_id_iter] = current_year_playoff_map

    for year_obj_medal_calc in completed_years:
        year_id_current = year_obj_medal_calc.id
        current_playoff_map = resolved_playoff_maps_by_year_id.get(year_id_current, {})
        final_ranking = calculate_complete_final_ranking(year_obj_medal_calc, games_by_year_id.get(year_id_current, []), current_playoff_map, year_obj_medal_calc)
        
        gold = final_ranking.get(1)
        silver = final_ranking.get(2)
        bronze = final_ranking.get(3)
        fourth = final_ranking.get(4)
            
        medal_tally_results.append({
            'year_obj': year_obj_medal_calc,
            'final_ranking': final_ranking,
            'gold': gold,
            'silver': silver,
            'bronze': bronze,
            'fourth': fourth
        })

    medal_tally_results.sort(key=lambda x: x['year_obj'].year, reverse=True)
    
    current_app.logger.info(f"Finished medal tally calculation. Processed {len(completed_years)} completed tournaments.")
    return medal_tally_results

def get_all_player_stats(team_filter=None):
    current_app.logger.info(f"Starting player statistics calculation. Team filter: {team_filter}")

    goals_sq = db.session.query(
        Goal.scorer_id.label("player_id"),
        func.count(Goal.id).label("num_goals")
    ).filter(Goal.scorer_id.isnot(None)) \
    .group_by(Goal.scorer_id).subquery()

    assists1_sq = db.session.query(
        Goal.assist1_id.label("player_id"),
        func.count(Goal.id).label("num_assists1")
    ).filter(Goal.assist1_id.isnot(None)) \
    .group_by(Goal.assist1_id).subquery()

    assists2_sq = db.session.query(
        Goal.assist2_id.label("player_id"),
        func.count(Goal.id).label("num_assists2")
    ).filter(Goal.assist2_id.isnot(None)) \
    .group_by(Goal.assist2_id).subquery()

    pim_when_clauses = []
    for penalty_type_key, minutes in PIM_MAP.items():
        pim_when_clauses.append((Penalty.penalty_type == penalty_type_key, minutes))
    
    pim_case_statement = case(
        *pim_when_clauses,
        else_=0
    )

    pims_sq = db.session.query(
        Penalty.player_id.label("player_id"),
        func.sum(pim_case_statement).label("total_pims")
    ).filter(Penalty.player_id.isnot(None)) \
    .group_by(Penalty.player_id).subquery()

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

    if team_filter:
        player_stats_query = player_stats_query.filter(Player.team_code == team_filter)

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

    results.sort(key=lambda x: (x['scorer_points'], x['goals']), reverse=True)
    
    current_app.logger.info(f"Finished player statistics calculation. Found {len(results)} players.")
    return results

@main_bp.route('/player-stats')
def player_stats_view():
    team_filter = request.args.get('team_filter', '').strip()
    if not team_filter:
        team_filter = None
    
    current_app.logger.info(f"Accessing player statistics page. Team filter: {team_filter}")
    player_stats_data = get_all_player_stats(team_filter=team_filter)
    return render_template('player_stats.html', player_stats=player_stats_data, team_iso_codes=TEAM_ISO_CODES)

@main_bp.route('/player-stats/data')
def player_stats_data():
    team_filter = request.args.get('team_filter', '').strip()
    if not team_filter:
        team_filter = None
    
    current_app.logger.info(f"Accessing player statistics JSON data. Team filter: {team_filter}")
    player_stats_data = get_all_player_stats(team_filter=team_filter)
    
    formatted_data = {
        'scoring_players': [player for player in player_stats_data if player['scorer_points'] > 0],
        'goal_players': [player for player in player_stats_data if player['goals'] > 0],
        'assist_players': [player for player in player_stats_data if player['assists'] > 0],
        'pim_players': [player for player in player_stats_data if player['pims'] > 0],
        'team_iso_codes': TEAM_ISO_CODES
    }
    
    return jsonify(formatted_data)

@main_bp.route('/edit-players', methods=['GET', 'POST'])
def edit_players():
    if request.method == 'POST':
        player_id = request.form.get('player_id')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        jersey_number_str = request.form.get('jersey_number')
        
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not player_id or not first_name or not last_name:
            error_msg = 'Spieler-ID, Vorname und Nachname sind erforderlich.'
            if is_ajax:
                return jsonify({'success': False, 'message': error_msg}), 400
            flash(error_msg, 'danger')
        else:
            try:
                player = db.session.get(Player, int(player_id))
                if not player:
                    error_msg = 'Spieler nicht gefunden.'
                    if is_ajax:
                        return jsonify({'success': False, 'message': error_msg}), 404
                    flash(error_msg, 'danger')
                else:
                    player.first_name = first_name.strip()
                    player.last_name = last_name.strip()
                    
                    if jersey_number_str and jersey_number_str.strip():
                        try:
                            player.jersey_number = int(jersey_number_str.strip())
                        except ValueError:
                            error_msg = 'Ungültige Trikotnummer.'
                            if is_ajax:
                                return jsonify({'success': False, 'message': error_msg}), 400
                            flash(error_msg, 'warning')
                            return redirect(url_for('main_bp.edit_players'))
                    else:
                        player.jersey_number = None
                    
                    db.session.commit()
                    success_msg = f'Spieler {first_name} {last_name} erfolgreich aktualisiert!'
                    
                    if is_ajax:
                        return jsonify({
                            'success': True, 
                            'message': success_msg,
                            'player': {
                                'id': player.id,
                                'first_name': player.first_name,
                                'last_name': player.last_name,
                                'jersey_number': player.jersey_number,
                                'team_code': player.team_code
                            }
                        })
                    flash(success_msg, 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error updating player: {str(e)}")
                error_msg = f'Fehler beim Aktualisieren des Spielers: {str(e)}'
                if is_ajax:
                    return jsonify({'success': False, 'message': error_msg}), 500
                flash(error_msg, 'danger')
        
        if not is_ajax:
            selected_country = request.args.get('country')
            if selected_country:
                return redirect(url_for('main_bp.edit_players', country=selected_country))
            return redirect(url_for('main_bp.edit_players'))
    
    countries_with_players_query = db.session.query(
        Player.team_code, 
        func.count(Player.id).label('player_count')
    ).group_by(Player.team_code).order_by(Player.team_code).all()
    
    countries_data = {}
    total_players = 0
    for country_code, player_count in countries_with_players_query:
        if country_code in TEAM_ISO_CODES and TEAM_ISO_CODES[country_code] is not None:
            countries_data[country_code] = player_count
            total_players += player_count
    
    countries = list(countries_data.keys())
    
    selected_country = request.args.get('country', countries[0] if countries else None)
    
    players = []
    if selected_country:
        players = Player.query.filter_by(team_code=selected_country).order_by(Player.last_name, Player.first_name).all()
    
    return render_template('edit_players.html', 
                         countries=countries, 
                         countries_data=countries_data,
                         total_players=total_players,
                         selected_country=selected_country, 
                         players=players,
                         team_iso_codes=TEAM_ISO_CODES)

@main_bp.route('/add-player-global', methods=['POST'])
def add_player_global():
    team_code = request.form.get('team_code')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    jersey_number_str = request.form.get('jersey_number')
    
    if not team_code or not first_name or not last_name:
        flash('Team, Vorname und Nachname sind erforderlich.', 'danger')
        return redirect(url_for('main_bp.edit_players'))
    
    try:
        jersey_number = None
        if jersey_number_str and jersey_number_str.strip():
            try:
                jersey_number = int(jersey_number_str.strip())
            except ValueError:
                flash('Ungültige Trikotnummer.', 'warning')
                return redirect(url_for('main_bp.edit_players'))
        
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