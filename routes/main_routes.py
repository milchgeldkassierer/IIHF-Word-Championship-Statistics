import os
import json
import re # Added for regex in playoff map building
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import db, ChampionshipYear, Game, AllTimeTeamStats, TeamStats # Added TeamStats
from constants import TEAM_ISO_CODES, PRELIM_ROUNDS, PLAYOFF_ROUNDS, QF_GAME_NUMBERS_BY_YEAR, SF_GAME_NUMBERS_BY_YEAR # Added more constants
from utils import get_resolved_team_code, is_code_final # Added utils imports
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
                with open(year_obj.fixture_path, 'r', encoding='utf-8') as f: fixture_data = json.load(f)
                qf_gns = fixture_data.get("qf_game_numbers") or QF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])
                sf_gns = fixture_data.get("sf_game_numbers") or SF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])
                h_tcs = fixture_data.get("host_teams", [])
            except (json.JSONDecodeError, OSError): 
                qf_gns = QF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, []); sf_gns = SF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])
        else: 
            qf_gns = QF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, []); sf_gns = SF_GAME_NUMBERS_BY_YEAR.get(year_obj.year, [])

        for grp_name_iter, grp_teams_stats_list in prelim_standings_by_group_this_year.items(): # Renamed grp_name
            for team_s in grp_teams_stats_list:
                current_year_playoff_map[f"{team_s.group}{team_s.rank_in_group}"] = team_s.name
                if h_tcs and team_s.name in h_tcs: current_year_playoff_map[f"H{team_s.rank_in_group}"] = team_s.name # Placeholder for host rank
        
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

        resolved_team1_code = get_resolved_team_code(game.team1_code, current_year_playoff_map, current_year_games_map_by_number)
        resolved_team2_code = get_resolved_team_code(game.team2_code, current_year_playoff_map, current_year_games_map_by_number)

        if not (is_code_final(resolved_team1_code) and is_code_final(resolved_team2_code)):
            current_app.logger.warning(
                f"Game ID {game.id} (Original: '{game.team1_code}' vs '{game.team2_code}') resolved to "
                f"('{resolved_team1_code}' vs '{resolved_team2_code}'). "
                f"Skipping for all-time stats due to non-final team codes."
            )
            continue # Skip this game if participants can't be resolved to final codes
            
        year_of_game = game.championship_year.year if game.championship_year else None # Should always have year

        # Initialize/get AllTimeTeamStats for resolved final team codes
        if resolved_team1_code not in all_time_stats_dict:
            all_time_stats_dict[resolved_team1_code] = AllTimeTeamStats(team_code=resolved_team1_code)
        team1_stats = all_time_stats_dict[resolved_team1_code]
        
        if resolved_team2_code not in all_time_stats_dict:
            all_time_stats_dict[resolved_team2_code] = AllTimeTeamStats(team_code=resolved_team2_code)
        team2_stats = all_time_stats_dict[resolved_team2_code]

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