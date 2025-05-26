import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import db, ChampionshipYear, Game # Add other models if needed by this blueprint
import traceback

main_bp = Blueprint('main_bp', __name__)

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