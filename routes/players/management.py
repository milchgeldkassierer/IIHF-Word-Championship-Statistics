from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from models import db, Player
from routes.main_routes import main_bp
from constants import TEAM_ISO_CODES
from sqlalchemy import func


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