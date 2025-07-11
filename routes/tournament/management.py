import os
import json
import traceback
from flask import render_template, request, redirect, url_for, flash, current_app
from models import db, ChampionshipYear, Game, Penalty
from utils.fixture_helpers import resolve_fixture_path
from tournament_summary import calculate_overall_tournament_summary
from utils import resolve_game_participants
from constants import TEAM_ISO_CODES, PIM_MAP
from sqlalchemy import func, case
from routes.main_routes import main_bp
# Import locally to avoid circular imports


def get_tournament_statistics(year_obj):
    """
    Calculate tournament statistics: games completed, total games, goals, penalties and winner
    Returns dict with: total_games, completed_games, goals, penalties, avg_goals_per_game, avg_penalties_per_game, winner
    """
    if not year_obj:
        return {
            'total_games': 0, 
            'completed_games': 0, 
            'goals': 0, 
            'penalties': 0, 
            'avg_goals_per_game': 0.0,
            'avg_penalties_per_game': 0.0,
            'winner': None
        }
    
    all_games = Game.query.filter_by(year_id=year_obj.id).all()
    total_games = len(all_games)
    
    completed_games_list = [game for game in all_games if game.team1_score is not None and game.team2_score is not None]
    completed_games = len(completed_games_list)
    
    # Calculate goals and penalties for completed games only
    goals_count = 0
    penalties_count = 0
    
    if completed_games > 0:
        # Calculate goals from game scores (same method as records.html)
        goals_count = sum(game.team1_score + game.team2_score for game in completed_games_list)
        
        # Calculate PIM from penalty types (same method as records.html)
        penalties_count = db.session.query(
            func.sum(
                case(
                    *[(Penalty.penalty_type == penalty_type, pim_value) for penalty_type, pim_value in PIM_MAP.items()],
                    else_=2  # Default for unknown penalty types
                )
            )
        ).join(Game, Penalty.game_id == Game.id).filter(
            Game.year_id == year_obj.id,
            Game.team1_score.isnot(None),
            Game.team2_score.isnot(None)
        ).scalar() or 0
    
    # Calculate averages
    avg_goals_per_game = round(goals_count / completed_games, 2) if completed_games > 0 else 0.0
    avg_penalties_per_game = round(penalties_count / completed_games, 2) if completed_games > 0 else 0.0
    
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
        'goals': goals_count,
        'penalties': penalties_count,
        'avg_goals_per_game': avg_goals_per_game,
        'avg_penalties_per_game': avg_penalties_per_game,
        'winner': winner
    }


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

    # Import locally to avoid circular imports
    from routes.standings.medals import get_medal_tally_data
    medal_data = get_medal_tally_data()
    medal_data_by_year = {medal_entry['year_obj'].year: medal_entry for medal_entry in medal_data}
    
    # Gesamtstatistiken berechnen
    overall_summary = calculate_overall_tournament_summary()

    return render_template('index.html', all_years=all_years_db, available_fixture_years=sorted_fixture_years, team_iso_codes=TEAM_ISO_CODES, medal_data_by_year=medal_data_by_year, overall_summary=overall_summary)