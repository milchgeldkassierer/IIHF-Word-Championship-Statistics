from flask import request, jsonify, redirect, url_for, flash, current_app
from models import db, Game, Player, Penalty
from constants import TEAM_ISO_CODES
from utils import convert_time_to_seconds

# Import the blueprint from the parent package
from . import year_bp

@year_bp.route('/<int:year_id>/game/<int:game_id>/add_penalty', methods=['POST'])
def add_penalty(year_id, game_id):
    game = db.session.get(Game, game_id)
    if not game or game.year_id != year_id:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404
    try:
        data = request.form
        pid_str = data.get('player_id_penalty')
        new_penalty = Penalty(
            game_id=game_id, team_code=data.get('team_code_penalty'),
            player_id=int(pid_str) if pid_str and pid_str != '-1' and pid_str.isdigit() else None,
            minute_of_game=data.get('minute_of_game'), penalty_type=data.get('penalty_type'), reason=data.get('reason')
        )
        if not all([new_penalty.team_code, new_penalty.minute_of_game, new_penalty.penalty_type, new_penalty.reason]):
            return jsonify({'success': False, 'message': 'Fehlende Daten für Strafeneingabe.'}), 400
        db.session.add(new_penalty)
        db.session.commit()
        
        player_cache = {p.id: p for p in Player.query.all()}
        def get_pname_local(pid): 
            if pid is None:
                return "Teamstrafe"
            p = player_cache.get(pid)
            return f"{p.first_name} {p.last_name}" if p else "Bankstrafe"

        penalty_data_for_js = {
            'id': new_penalty.id, 'team_code': new_penalty.team_code,
            'player_name': get_pname_local(new_penalty.player_id),
            'minute_of_game': new_penalty.minute_of_game,
            'penalty_type': new_penalty.penalty_type, 'reason': new_penalty.reason,
            'team_iso': TEAM_ISO_CODES.get(new_penalty.team_code.upper()),
            'time_for_sort': convert_time_to_seconds(new_penalty.minute_of_game)
        }
        return jsonify({'success': True, 'message': 'Strafe erfolgreich hinzugefügt!', 'penalty': penalty_data_for_js, 'game_id': game_id})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding penalty: {str(e)}")
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500

@year_bp.route('/<int:year_id>/penalty/<int:penalty_id>/delete', methods=['POST'])
def delete_penalty(year_id, penalty_id):
    penalty = db.session.get(Penalty, penalty_id)
    if not penalty:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Penalty not found.'}), 404
        flash('Penalty not found.', 'warning')
        return redirect(url_for('year_bp.year_view', year_id=year_id))

    game = db.session.get(Game, penalty.game_id)
    if not game or game.year_id != year_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid association.'}), 400
        flash('Invalid penalty for year.', 'danger')
        return redirect(url_for('year_bp.year_view', year_id=year_id))
    
    game_id_resp = game.id
    db.session.delete(penalty)
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Penalty deleted.', 'penalty_id': penalty_id, 'game_id': game_id_resp})
    flash('Penalty deleted.', 'success')
    return redirect(url_for('year_bp.year_view', year_id=year_id, _anchor=f"game-details-{game_id_resp}"))