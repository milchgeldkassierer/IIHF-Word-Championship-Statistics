from flask import request, jsonify, redirect, url_for, flash, current_app
from models import db, Game, Goal, Player, ShotsOnGoal
from constants import TEAM_ISO_CODES
from utils import convert_time_to_seconds, check_game_data_consistency
from app.services.core.game_service import GameService
from app.services.core.player_service import PlayerService
from app.exceptions import NotFoundError, ValidationError, ServiceError

# Import the blueprint from the parent package
from . import year_bp

@year_bp.route('/<int:year_id>/game/<int:game_id>/add_goal', methods=['POST'])
def add_goal(year_id, game_id):
    # Service-Layer verwenden
    game_service = GameService()
    try:
        game = game_service.get_by_id(game_id)
        if not game or game.year_id != year_id:
            return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404
    except NotFoundError:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404
    try:
        data = request.form
        new_goal = Goal(
            game_id=game_id, team_code=data.get('team_code_goal'), minute=data.get('minute'), goal_type=data.get('goal_type'),
            scorer_id=int(data.get('scorer_id')),
            assist1_id=int(data.get('assist1_id')) if data.get('assist1_id') and data.get('assist1_id').isdigit() else None,
            assist2_id=int(data.get('assist2_id')) if data.get('assist2_id') and data.get('assist2_id').isdigit() else None,
            is_empty_net=data.get('is_empty_net') == 'on'
        )
        if not all([new_goal.team_code, new_goal.minute, new_goal.goal_type, new_goal.scorer_id]):
            return jsonify({'success': False, 'message': 'Fehlende Daten für Toreingabe.'}), 400
        db.session.add(new_goal)
        db.session.commit()

        # Service für Player verwenden
        player_service = PlayerService()
        all_players = player_service.get_all()
        player_cache = {p.id: p for p in all_players} 
        def get_pname_local(pid):
            p = player_cache.get(pid)
            return f"{p.first_name} {p.last_name}" if p else "N/A"
        
        sog_entries_for_game = ShotsOnGoal.query.filter_by(game_id=game_id).all()
        sog_data_for_check = {}
        for sog_e in sog_entries_for_game:
            sog_data_for_check.setdefault(sog_e.team_code, {})[sog_e.period] = sog_e.shots
        if game.team1_code not in sog_data_for_check:
            sog_data_for_check[game.team1_code] = {}
        if game.team2_code not in sog_data_for_check:
            sog_data_for_check[game.team2_code] = {}
        for team_code_key in [game.team1_code, game.team2_code]:
            for p_key in range(1, 5):
                sog_data_for_check[team_code_key].setdefault(p_key, 0)

        consistency_result = check_game_data_consistency(game, sog_data_for_check)
        scores_match = consistency_result['scores_fully_match_data']

        goal_data_for_js = {
            'id': new_goal.id, 'team_code': new_goal.team_code, 'minute': new_goal.minute,
            'goal_type_display': new_goal.goal_type, 'is_empty_net': new_goal.is_empty_net,
            'scorer': get_pname_local(new_goal.scorer_id),
            'assist1': get_pname_local(new_goal.assist1_id) if new_goal.assist1_id else None,
            'assist2': get_pname_local(new_goal.assist2_id) if new_goal.assist2_id else None,
            'team_iso': TEAM_ISO_CODES.get(new_goal.team_code.upper()),
            'time_for_sort': convert_time_to_seconds(new_goal.minute),
            'scores_fully_match_goals': scores_match
        }
        return jsonify({'success': True, 'message': 'Tor erfolgreich hinzugefügt!', 'goal': goal_data_for_js, 'game_id': game_id})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding goal: {str(e)}")
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500

@year_bp.route('/<int:year_id>/goal/<int:goal_id>/delete', methods=['POST'])
def delete_goal(year_id, goal_id):
    # TODO: GoalService implementieren - vorerst direkte DB-Abfrage
    goal = db.session.get(Goal, goal_id)
    if not goal: 
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Goal not found.'}), 404
        flash('Goal not found.', 'warning')
        return redirect(url_for('year_bp.year_view', year_id=year_id))

    # Service-Layer verwenden
    game_service = GameService()
    try:
        game = game_service.get_by_id(goal.game_id)
        if not game or game.year_id != year_id:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Invalid association.'}), 400
            flash('Invalid goal for year.', 'danger')
            return redirect(url_for('year_bp.year_view', year_id=year_id))
    except NotFoundError:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid association.'}), 400
        flash('Invalid goal for year.', 'danger')
        return redirect(url_for('year_bp.year_view', year_id=year_id))
    
    game_id_resp = game.id
    db.session.delete(goal)
    db.session.commit()

    sog_entries_for_game = ShotsOnGoal.query.filter_by(game_id=game_id_resp).all()
    sog_data_for_check = {}
    for sog_e in sog_entries_for_game:
        sog_data_for_check.setdefault(sog_e.team_code, {})[sog_e.period] = sog_e.shots
    if game.team1_code not in sog_data_for_check:
        sog_data_for_check[game.team1_code] = {}
    if game.team2_code not in sog_data_for_check:
        sog_data_for_check[game.team2_code] = {}
    for team_code_key in [game.team1_code, game.team2_code]:
        for p_key in range(1, 5):
            sog_data_for_check[team_code_key].setdefault(p_key, 0)

    consistency_result = check_game_data_consistency(game, sog_data_for_check)
    scores_match = consistency_result['scores_fully_match_data']

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Goal deleted.', 'goal_id': goal_id, 'game_id': game_id_resp, 'scores_fully_match_goals': scores_match})
    flash('Goal deleted.', 'success')
    return redirect(url_for('year_bp.year_view', year_id=year_id, _anchor=f"game-details-{game_id_resp}"))