from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from markupsafe import escape
from models import db, Player
from routes.blueprints import main_bp
from constants import TEAM_ISO_CODES
from sqlalchemy import func
import re
import html

# Import Service Layer
from app.services.core.player_service import PlayerService
from app.services.core.team_service import TeamService
from app.exceptions import NotFoundError, ValidationError, ServiceError


@main_bp.route('/edit-players', methods=['GET', 'POST'])
def edit_players():
    # Initialize Services
    player_service = PlayerService()
    team_service = TeamService()
    
    if request.method == 'POST':
        # Sanitize and validate input data to prevent XSS
        player_id = _sanitize_input(request.form.get('player_id'))
        first_name = _sanitize_input(request.form.get('first_name'))
        last_name = _sanitize_input(request.form.get('last_name'))
        jersey_number_str = _sanitize_input(request.form.get('jersey_number'))
        
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Validate required fields and format
        if not player_id or not first_name or not last_name:
            error_msg = 'Spieler-ID, Vorname und Nachname sind erforderlich.'
            if is_ajax:
                return jsonify({'success': False, 'message': error_msg}), 400
            flash(error_msg, 'danger')
        elif not _validate_player_name(first_name) or not _validate_player_name(last_name):
            error_msg = 'Ungültiges Format für Spielernamen. Nur Buchstaben, Leerzeichen, Bindestriche und Apostrophe sind erlaubt.'
            if is_ajax:
                return jsonify({'success': False, 'message': error_msg}), 400
            flash(error_msg, 'danger')
        else:
            try:
                # Validate jersey number
                jersey_number = None
                if jersey_number_str and jersey_number_str.strip():
                    try:
                        jersey_number = int(jersey_number_str.strip())
                    except ValueError:
                        error_msg = 'Ungültige Trikotnummer.'
                        if is_ajax:
                            return jsonify({'success': False, 'message': error_msg}), 400
                        flash(error_msg, 'warning')
                        return redirect(url_for('main_bp.edit_players'))
                
                # Update player via service
                updated_player = player_service.update_player(
                    int(player_id),
                    first_name=first_name.strip(),
                    last_name=last_name.strip(),
                    jersey_number=jersey_number
                )
                
                success_msg = f'Spieler {first_name} {last_name} erfolgreich aktualisiert!'
                
                if is_ajax:
                    return jsonify({
                        'success': True, 
                        'message': success_msg,
                        'player': {
                            'id': updated_player.id,
                            'first_name': updated_player.first_name,
                            'last_name': updated_player.last_name,
                            'jersey_number': updated_player.jersey_number,
                            'team_code': updated_player.team_code
                        }
                    })
                flash(success_msg, 'success')
                
            except NotFoundError:
                error_msg = 'Spieler nicht gefunden.'
                if is_ajax:
                    return jsonify({'success': False, 'message': error_msg}), 404
                flash(error_msg, 'danger')
            except ValidationError as e:
                error_msg = f'Validierungsfehler: {str(e)}'
                if is_ajax:
                    return jsonify({'success': False, 'message': error_msg}), 400
                flash(error_msg, 'warning')
            except ServiceError as e:
                current_app.logger.error(f"Service error updating player: {str(e)}")
                error_msg = f'Fehler beim Aktualisieren des Spielers: {str(e)}'
                if is_ajax:
                    return jsonify({'success': False, 'message': error_msg}), 500
                flash(error_msg, 'danger')
        
        if not is_ajax:
            selected_country = request.args.get('country')
            if selected_country:
                return redirect(url_for('main_bp.edit_players', country=selected_country))
            return redirect(url_for('main_bp.edit_players'))
    
    # Get countries with players via service
    try:
        countries_stats = team_service.get_countries_with_players()
        countries_data = {}
        total_players = 0
        
        for stat in countries_stats:
            country_code = stat['team_code']
            player_count = stat['player_count']
            if country_code in TEAM_ISO_CODES and TEAM_ISO_CODES[country_code] is not None:
                countries_data[country_code] = player_count
                total_players += player_count
        
        countries = list(countries_data.keys())
        selected_country = request.args.get('country', countries[0] if countries else None)
        
        # Get players for selected country via service
        players = []
        if selected_country:
            players = player_service.get_players_by_team(selected_country)
            
    except ServiceError as e:
        current_app.logger.error(f"Service error in edit_players: {str(e)}")
        flash(f'Fehler beim Laden der Spielerdaten: {str(e)}', 'danger')
        countries_data = {}
        total_players = 0
        countries = []
        selected_country = None
        players = []
    
    return render_template('edit_players.html', 
                         countries=countries, 
                         countries_data=countries_data,
                         total_players=total_players,
                         selected_country=selected_country, 
                         players=players,
                         team_iso_codes=TEAM_ISO_CODES)


@main_bp.route('/add-player-global', methods=['POST'])
def add_player_global():
    # Initialize Service
    player_service = PlayerService()
    
    # Sanitize and validate input data to prevent XSS
    team_code = _sanitize_input(request.form.get('team_code'))
    first_name = _sanitize_input(request.form.get('first_name'))
    last_name = _sanitize_input(request.form.get('last_name'))
    jersey_number_str = _sanitize_input(request.form.get('jersey_number'))
    
    # Validate required fields and format
    if not team_code or not first_name or not last_name:
        flash('Team, Vorname und Nachname sind erforderlich.', 'danger')
        return redirect(url_for('main_bp.edit_players'))
    
    if not _validate_player_name(first_name) or not _validate_player_name(last_name):
        flash('Ungültiges Format für Spielernamen. Nur Buchstaben, Leerzeichen, Bindestriche und Apostrophe sind erlaubt.', 'danger')
        return redirect(url_for('main_bp.edit_players'))
    
    try:
        # Validate jersey number
        jersey_number = None
        if jersey_number_str and jersey_number_str.strip():
            try:
                jersey_number = int(jersey_number_str.strip())
            except ValueError:
                flash('Ungültige Trikotnummer.', 'warning')
                return redirect(url_for('main_bp.edit_players'))
        
        # Create player via service
        new_player = player_service.create_player(
            team_code=team_code,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            jersey_number=jersey_number
        )
        
        flash(f'Spieler {first_name} {last_name} erfolgreich hinzugefügt!', 'success')
        
    except ValidationError as e:
        if 'bereits' in str(e).lower() or 'exists' in str(e).lower():
            flash(f'Spieler {first_name} {last_name} ({team_code}) existiert bereits.', 'warning')
        else:
            flash(f'Validierungsfehler: {str(e)}', 'warning')
    except ServiceError as e:
        current_app.logger.error(f"Service error adding player: {str(e)}")
        flash(f'Fehler beim Hinzufügen des Spielers: {str(e)}', 'danger')
    
    return redirect(url_for('main_bp.edit_players', country=team_code))


def _sanitize_input(value: str) -> str:
    """
    Sanitize user input to prevent XSS attacks
    
    Args:
        value: Input string to sanitize
        
    Returns:
        Sanitized string safe for processing
    """
    if not value:
        return value
    
    # Strip whitespace
    value = value.strip()
    
    # Remove potentially dangerous characters and scripts
    # Block script tags and javascript protocols
    value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)
    value = re.sub(r'on\w+\s*=', '', value, flags=re.IGNORECASE)
    
    # Remove HTML tags except for basic safe ones
    value = re.sub(r'<(?!/?[bi]>)[^>]*>', '', value)
    
    # Limit length to prevent DoS
    if len(value) > 100:
        value = value[:100]
    
    return value


def _validate_player_name(name: str) -> bool:
    """
    Validate player name format
    
    Args:
        name: Player name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not name or len(name.strip()) < 2:
        return False
    
    # Only allow letters, spaces, hyphens, and apostrophes
    pattern = r'^[a-zA-ZäöüßÄÖÜ\s\-\']+$'
    return bool(re.match(pattern, name.strip()))