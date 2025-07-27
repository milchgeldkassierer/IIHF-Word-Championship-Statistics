from flask import render_template, request, jsonify, current_app
from routes.blueprints import main_bp
from constants import TEAM_ISO_CODES

# Import Service Layer
from app.services.core.player_service import PlayerService
from app.services.core.team_service import TeamService
from app.exceptions import ServiceError


def get_all_player_stats(team_filter=None):
    """
    Get all player statistics using the service layer.
    This function now uses PlayerService.get_comprehensive_player_stats() instead of direct DB queries.
    """
    try:
        player_service = PlayerService()
        return player_service.get_comprehensive_player_stats(team_filter=team_filter)
    except ServiceError as e:
        current_app.logger.error(f"Service error in get_all_player_stats: {str(e)}")
        return []
    except Exception as e:
        current_app.logger.error(f"Unexpected error in get_all_player_stats: {str(e)}")
        return []


@main_bp.route('/player-stats')
def player_stats_view():
    team_filter = request.args.get('team_filter', '').strip()
    if not team_filter:
        team_filter = None
    
    player_stats_data = get_all_player_stats(team_filter=team_filter)
    return render_template('player_stats.html', player_stats=player_stats_data, team_iso_codes=TEAM_ISO_CODES)


@main_bp.route('/player-stats/data')
def player_stats_data():
    team_filter = request.args.get('team_filter', '').strip()
    if not team_filter:
        team_filter = None
    
    player_stats_data = get_all_player_stats(team_filter=team_filter)
    
    formatted_data = {
        'scoring_players': [player for player in player_stats_data if player['scorer_points'] > 0],
        'goal_players': [player for player in player_stats_data if player['goals'] > 0],
        'assist_players': [player for player in player_stats_data if player['assists'] > 0],
        'pim_players': [player for player in player_stats_data if player['pims'] > 0],
        'team_iso_codes': TEAM_ISO_CODES
    }
    
    return jsonify(formatted_data)