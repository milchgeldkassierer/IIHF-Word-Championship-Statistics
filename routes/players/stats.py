from flask import render_template, request, jsonify, current_app
from models import db, Player, Goal, Penalty
from routes.blueprints import main_bp
from constants import TEAM_ISO_CODES, PIM_MAP
from sqlalchemy import func, case


def get_all_player_stats(team_filter=None):
    goals_sq = db.session.query(
        Goal.scorer_id.label("player_id"),
        func.count(Goal.id).label("num_goals")
    ).filter(Goal.scorer_id.isnot(None)) \
    .group_by(Goal.scorer_id).subquery()

    assists1_sq = db.session.query(
        Goal.assist1_id.label("player_id"),
        func.count(Goal.id).label("num_assists1")
    ).filter(Goal.assist1_id.isnot(None)) \
    .group_by(Goal.assist1_id).subquery()

    assists2_sq = db.session.query(
        Goal.assist2_id.label("player_id"),
        func.count(Goal.id).label("num_assists2")
    ).filter(Goal.assist2_id.isnot(None)) \
    .group_by(Goal.assist2_id).subquery()

    pim_when_clauses = []
    for penalty_type_key, minutes in PIM_MAP.items():
        pim_when_clauses.append((Penalty.penalty_type == penalty_type_key, minutes))
    
    pim_case_statement = case(
        *pim_when_clauses,
        else_=0
    )

    pims_sq = db.session.query(
        Penalty.player_id.label("player_id"),
        func.sum(pim_case_statement).label("total_pims")
    ).filter(Penalty.player_id.isnot(None)) \
    .group_by(Penalty.player_id).subquery()

    player_stats_query = db.session.query(
        Player.id,
        Player.first_name,
        Player.last_name,
        Player.team_code,
        func.coalesce(goals_sq.c.num_goals, 0).label("goals"),
        func.coalesce(assists1_sq.c.num_assists1, 0).label("assists1_count"),
        func.coalesce(assists2_sq.c.num_assists2, 0).label("assists2_count"),
        func.coalesce(pims_sq.c.total_pims, 0).label("pims")
    ).select_from(Player) \
    .outerjoin(goals_sq, Player.id == goals_sq.c.player_id) \
    .outerjoin(assists1_sq, Player.id == assists1_sq.c.player_id) \
    .outerjoin(assists2_sq, Player.id == assists2_sq.c.player_id) \
    .outerjoin(pims_sq, Player.id == pims_sq.c.player_id)

    if team_filter:
        player_stats_query = player_stats_query.filter(Player.team_code == team_filter)

    distinct_db_penalty_types = db.session.query(Penalty.penalty_type).distinct().all()
    unmapped_types = [pt[0] for pt in distinct_db_penalty_types if pt[0] not in PIM_MAP and pt[0] is not None]
    if unmapped_types:
        current_app.logger.warning(f"PlayerStats: Unmapped penalty types found in database, defaulted to 0 PIMs: {unmapped_types}")

    results = []
    for row in player_stats_query.all():
        assists = row.assists1_count + row.assists2_count
        scorer_points = row.goals + assists
        results.append({
            'first_name': row.first_name,
            'last_name': row.last_name,
            'team_code': row.team_code,
            'goals': row.goals,
            'assists': assists,
            'scorer_points': scorer_points,
            'pims': row.pims
        })

    results.sort(key=lambda x: (x['scorer_points'], x['goals']), reverse=True)
    
    return results


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