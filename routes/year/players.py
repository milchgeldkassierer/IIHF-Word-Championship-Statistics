from flask import request, redirect, url_for, flash, jsonify, current_app
from models import db, Player
from app.services.core.player_service import PlayerService
from app.exceptions import NotFoundError, ValidationError, ServiceError

# Import the blueprint from the parent package
from . import year_bp

@year_bp.route('/add_player_global', methods=['POST'])
def add_player():
    team_code = request.form.get('team_code')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    jersey_number_str = request.form.get('jersey_number')
    year_id_redirect = request.form.get('year_id_redirect') 
    game_id_anchor = request.form.get('game_id_anchor') 

    if not team_code or not first_name or not last_name:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Team, First Name, and Last Name are required.'}), 400
        flash('Team, First Name, and Last Name are required to add a player.', 'danger')
    else:
        try:
            jersey_number = int(jersey_number_str) if jersey_number_str and jersey_number_str.isdigit() else None
        except ValueError: 
            jersey_number = None
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Invalid Jersey Number format.'}), 400
            flash('Invalid Jersey Number format.', 'danger')
            anchor_to_use = f"game-details-{game_id_anchor}" if game_id_anchor and game_id_anchor != 'None' else "addPlayerForm-global"
            if year_id_redirect and year_id_redirect != 'None':
                return redirect(url_for('year_bp.year_view', year_id=int(year_id_redirect), _anchor=anchor_to_use))
            return redirect(url_for('main_bp.index'))

        # Service-Layer verwenden
        player_service = PlayerService()
        existing_player = player_service.find_by_name_and_team(first_name, last_name, team_code)
        if existing_player:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': f'Player {first_name} {last_name} ({team_code}) already exists.'}), 400
            flash(f'Player {first_name} {last_name} ({team_code}) already exists.', 'warning')
        else:
            try:
                # Service-Layer für Player-Erstellung verwenden
                new_player = player_service.create_player(
                    team_code=team_code,
                    first_name=first_name,
                    last_name=last_name,
                    jersey_number=jersey_number
                )
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True, 'message': f'Player {first_name} {last_name} added!',
                        'player': {'id': new_player.id, 'first_name': new_player.first_name, 'last_name': new_player.last_name, 'team_code': new_player.team_code, 'jersey_number': new_player.jersey_number, 'full_name': f"{new_player.last_name.upper()}, {new_player.first_name}"}
                    })
                flash(f'Player {first_name} {last_name} added!', 'success')
            except Exception as e:
                # Rollback wird vom Service gehandhabt
                current_app.logger.error(f"Error adding player: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': f'Error adding player: {str(e)}'}), 500
                flash(f'Error adding player: {str(e)}', 'danger')
    
    anchor_to_use = f"game-details-{game_id_anchor}" if game_id_anchor and game_id_anchor != 'None' else "addPlayerForm-global"
    if year_id_redirect and year_id_redirect != 'None':
        return redirect(url_for('year_bp.year_view', year_id=int(year_id_redirect), _anchor=anchor_to_use))
    return redirect(url_for('main_bp.index'))