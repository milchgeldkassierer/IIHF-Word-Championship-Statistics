from flask import render_template, request, jsonify, current_app
from models import db, Player, Goal, Penalty, Game, ChampionshipYear
from routes.blueprints import main_bp
from constants import TEAM_ISO_CODES, PIM_MAP
from sqlalchemy import func, case, or_


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

    # Subqueries for year ranges
    goal_years_sq = db.session.query(
        Goal.scorer_id.label("player_id"),
        func.min(ChampionshipYear.year).label("first_goal_year"),
        func.max(ChampionshipYear.year).label("last_goal_year")
    ).join(Game, Goal.game_id == Game.id) \
    .join(ChampionshipYear, Game.year_id == ChampionshipYear.id) \
    .filter(Goal.scorer_id.isnot(None)) \
    .group_by(Goal.scorer_id).subquery()

    assist_years_sq = db.session.query(
        Player.id.label("player_id"),
        func.min(ChampionshipYear.year).label("first_assist_year"),
        func.max(ChampionshipYear.year).label("last_assist_year")
    ).select_from(Goal) \
    .join(Game, Goal.game_id == Game.id) \
    .join(ChampionshipYear, Game.year_id == ChampionshipYear.id) \
    .join(Player, or_(Goal.assist1_id == Player.id, Goal.assist2_id == Player.id)) \
    .group_by(Player.id).subquery()

    pim_years_sq = db.session.query(
        Penalty.player_id.label("player_id"),
        func.min(ChampionshipYear.year).label("first_pim_year"),
        func.max(ChampionshipYear.year).label("last_pim_year")
    ).join(Game, Penalty.game_id == Game.id) \
    .join(ChampionshipYear, Game.year_id == ChampionshipYear.id) \
    .filter(Penalty.player_id.isnot(None)) \
    .group_by(Penalty.player_id).subquery()

    player_stats_query = db.session.query(
        Player.id,
        Player.first_name,
        Player.last_name,
        Player.team_code,
        func.coalesce(goals_sq.c.num_goals, 0).label("goals"),
        func.coalesce(assists1_sq.c.num_assists1, 0).label("assists1_count"),
        func.coalesce(assists2_sq.c.num_assists2, 0).label("assists2_count"),
        func.coalesce(pims_sq.c.total_pims, 0).label("pims"),
        goal_years_sq.c.first_goal_year,
        goal_years_sq.c.last_goal_year,
        assist_years_sq.c.first_assist_year,
        assist_years_sq.c.last_assist_year,
        pim_years_sq.c.first_pim_year,
        pim_years_sq.c.last_pim_year
    ).select_from(Player) \
    .outerjoin(goals_sq, Player.id == goals_sq.c.player_id) \
    .outerjoin(assists1_sq, Player.id == assists1_sq.c.player_id) \
    .outerjoin(assists2_sq, Player.id == assists2_sq.c.player_id) \
    .outerjoin(pims_sq, Player.id == pims_sq.c.player_id) \
    .outerjoin(goal_years_sq, Player.id == goal_years_sq.c.player_id) \
    .outerjoin(assist_years_sq, Player.id == assist_years_sq.c.player_id) \
    .outerjoin(pim_years_sq, Player.id == pim_years_sq.c.player_id)

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
        
        # Format year ranges
        goal_year_range = None
        if row.first_goal_year and row.last_goal_year:
            if row.first_goal_year == row.last_goal_year:
                goal_year_range = f"({row.first_goal_year})"
            else:
                goal_year_range = f"({row.first_goal_year}-{row.last_goal_year})"
        
        assist_year_range = None
        if row.first_assist_year and row.last_assist_year:
            if row.first_assist_year == row.last_assist_year:
                assist_year_range = f"({row.first_assist_year})"
            else:
                assist_year_range = f"({row.first_assist_year}-{row.last_assist_year})"
        
        pim_year_range = None
        if row.first_pim_year and row.last_pim_year:
            if row.first_pim_year == row.last_pim_year:
                pim_year_range = f"({row.first_pim_year})"
            else:
                pim_year_range = f"({row.first_pim_year}-{row.last_pim_year})"
        
        # For overall scoring, use the earliest and latest years from any stat
        overall_first_year = None
        overall_last_year = None
        
        all_first_years = [y for y in [row.first_goal_year, row.first_assist_year, row.first_pim_year] if y is not None]
        all_last_years = [y for y in [row.last_goal_year, row.last_assist_year, row.last_pim_year] if y is not None]
        
        if all_first_years:
            overall_first_year = min(all_first_years)
        if all_last_years:
            overall_last_year = max(all_last_years)
        
        overall_year_range = None
        if overall_first_year and overall_last_year:
            if overall_first_year == overall_last_year:
                overall_year_range = f"({overall_first_year})"
            else:
                overall_year_range = f"({overall_first_year}-{overall_last_year})"
        
        results.append({
            'first_name': row.first_name,
            'last_name': row.last_name,
            'team_code': row.team_code,
            'goals': row.goals,
            'assists': assists,
            'scorer_points': scorer_points,
            'pims': row.pims,
            'goal_year_range': goal_year_range,
            'assist_year_range': assist_year_range,
            'pim_year_range': pim_year_range,
            'overall_year_range': overall_year_range
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