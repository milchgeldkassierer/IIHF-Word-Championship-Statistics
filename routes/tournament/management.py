import os
import json
import traceback
from flask import render_template, request, redirect, url_for, flash, current_app
from models import db, ChampionshipYear, Game, Penalty
from utils.fixture_helpers import resolve_fixture_path
from .summary import calculate_overall_tournament_summary
from utils import resolve_game_participants
from constants import TEAM_ISO_CODES, PIM_MAP
from sqlalchemy import func, case
from routes.blueprints import main_bp
from routes.records.utils import get_tournament_statistics
# Service Layer imports
from app.services.core.tournament_service import TournamentService
from app.exceptions import NotFoundError, ValidationError, BusinessRuleError
# Import locally to avoid circular imports


@main_bp.route('/', methods=['GET', 'POST'])
def index():
    # Service Layer initialisieren
    tournament_service = TournamentService()
    
    if request.method == 'POST':
        if 'delete_year' in request.form:
            year_id_to_delete = request.form.get('year_id_to_delete')
            try:
                # Service Layer nutzen für Tournament-Abruf
                year_obj_del = tournament_service.get_by_id(year_id_to_delete)
                if year_obj_del:
                    # Fixture-Datei löschen falls vorhanden
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
                    
                    # Löschung direkt durchführen (Service hat keine delete Methode)
                    db.session.delete(year_obj_del)
                    db.session.commit()
                    flash(f'Tournament "{year_obj_del.name} ({year_obj_del.year})" deleted.', 'success')
                else:
                    flash('Tournament to delete not found.', 'warning')
            except BusinessRuleError as e:
                flash(str(e), 'danger')
            except Exception as e:
                flash(f'Error deleting tournament: {str(e)}', 'danger')
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

        # Service Layer nutzen für Tournament-Suche
        existing_tournament = ChampionshipYear.query.filter_by(year=year_int).first()
        target_year_obj = existing_tournament

        if not target_year_obj:
            try:
                # Service Layer nutzen für Tournament-Erstellung
                target_year_obj = tournament_service.create_tournament(name_str, year_int)
                flash(f'Tournament "{target_year_obj.name} ({target_year_obj.year})" created.', 'success')
            except ValidationError as e:
                flash(f'Validation error: {str(e)}', 'danger')
                return redirect(url_for('main_bp.index'))
            except BusinessRuleError as e:
                flash(f'Business rule error: {str(e)}', 'danger')
                return redirect(url_for('main_bp.index'))
            except Exception as e:
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
                # Fixture-Loading bleibt direkt, da es komplexe Datenverarbeitung ist
                # Service Layer für Spielverwaltung nutzen
                game_service = GameService()
                
                # Zuerst alle bestehenden Spiele für dieses Turnier löschen
                existing_games = game_service.get_by_tournament(target_year_obj.id)
                for game in existing_games:
                    game_service.delete(game.id)
                try:
                    # Tournament-Update direkt (Service hat keine update Methode)
                    target_year_obj.fixture_path = relative_fixture_path
                    
                    with open(fixture_path_to_load, 'r', encoding='utf-8') as f:
                        fixture_data = json.load(f)
                    
                    games_from_json = fixture_data.get("schedule", [])
                    games_data_list = []
                    
                    for game_data_item in games_from_json:
                        mapped_game_data = {
                            'year_id': target_year_obj.id,
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
                        games_data_list.append(mapped_game_data)
                    
                    # Bulk create Spiele über Service
                    if games_data_list:
                        game_service.bulk_create(games_data_list)
                    flash(f'Fixture "{os.path.basename(fixture_path_to_load)}" loaded and games updated for "{target_year_obj.name} ({target_year_obj.year})".', 'success')
                except Exception as e:
                    game_service.rollback()
                    flash(f'Error processing fixture file "{os.path.basename(fixture_path_to_load if fixture_path_to_load else potential_fixture_filename)}": {str(e)} - {traceback.format_exc()}', 'danger')
            else:
                if not existing_tournament:
                    flash(f'Tournament "{target_year_obj.name} ({target_year_obj.year})" created, but no fixture file like "{year_str}.json" found. Please add it and try again.', 'warning')
                else:
                    flash(f'No fixture file like "{year_str}.json" found for "{target_year_obj.name} ({target_year_obj.year})". Existing games remain.', 'info')

    # Direkte Datenbankabfrage für Tournament-Liste
    all_years_db = ChampionshipYear.query.order_by(ChampionshipYear.year.asc(), ChampionshipYear.name).all()
    
    # Statistiken für jedes Tournament hinzufügen
    for year in all_years_db:
        year.stats = get_tournament_statistics(year)
    
    # Verfügbare Fixture-Dateien finden
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
    
    sorted_fixture_years = sorted(list(all_found_years))

    # Import locally to avoid circular imports
    from routes.standings.medals import get_medal_tally_data
    medal_data = get_medal_tally_data()
    medal_data_by_year = {medal_entry['year_obj'].year: medal_entry for medal_entry in medal_data}
    
    # Gesamtstatistiken berechnen
    overall_summary = calculate_overall_tournament_summary()

    return render_template('index.html', all_years=all_years_db, available_fixture_years=sorted_fixture_years, team_iso_codes=TEAM_ISO_CODES, medal_data_by_year=medal_data_by_year, overall_summary=overall_summary)