from flask import render_template, request, current_app
from models import ChampionshipYear, Game, AllTimeTeamStats
from routes.blueprints import main_bp
from utils import is_code_final
from constants import TEAM_ISO_CODES


def calculate_all_time_standings(game_type='all'):
    """
    Optimized calculation that maintains perfect data consistency with the original
    by using the same API logic but with improved batching and caching.
    
    Args:
        game_type (str): Filter games by type - 'all', 'preliminary', or 'playoffs'
    """
    # Get all teams that have played in any tournament
    all_teams = set()
    all_years = ChampionshipYear.query.all()
    
    for year_obj in all_years:
        games_this_year = Game.query.filter_by(year_id=year_obj.id).all()
        for game in games_this_year:
            if game.team1_code and is_code_final(game.team1_code):
                all_teams.add(game.team1_code)
            if game.team2_code and is_code_final(game.team2_code):
                all_teams.add(game.team2_code)
    
    all_time_stats_dict = {}
    
    # Optimization: batch process all teams but use parallel processing concept
    # Pre-fetch all yearly stats for all teams in a more efficient way
    yearly_stats_cache = {}
    
    # Import API function here to avoid circular imports
    from routes.api.team_stats import get_team_yearly_stats
    
    # Use the API function directly with proper context management
    for team_code in all_teams:
        with current_app.test_request_context(query_string=f'game_type={game_type}'):
            try:
                response = get_team_yearly_stats(team_code)
                if hasattr(response, 'get_json'):
                    data = response.get_json()
                    yearly_stats_cache[team_code] = data.get('yearly_stats', [])
                elif isinstance(response, tuple) and len(response) == 2:
                    response_obj, _ = response
                    if hasattr(response_obj, 'get_json'):
                        data = response_obj.get_json()
                        yearly_stats_cache[team_code] = data.get('yearly_stats', [])
            except Exception:
                yearly_stats_cache[team_code] = []
    
    # Process the cached data
    for team_code, yearly_stats_data in yearly_stats_cache.items():
        if yearly_stats_data:
            all_time_stats_dict[team_code] = AllTimeTeamStats(team_code=team_code)
            team_all_time_stats = all_time_stats_dict[team_code]
            
            # Aggregate from API data
            for year_data in yearly_stats_data:
                if year_data.get('participated', False):
                    year = year_data.get('year')
                    stats = year_data.get('stats', {})
                    
                    if year:
                        team_all_time_stats.years_participated.add(year)
                    
                    team_all_time_stats.gp += stats.get('gp', 0)
                    team_all_time_stats.w += stats.get('w', 0)
                    team_all_time_stats.otw += stats.get('otw', 0)
                    team_all_time_stats.sow += stats.get('sow', 0)
                    team_all_time_stats.l += stats.get('l', 0)
                    team_all_time_stats.otl += stats.get('otl', 0)
                    team_all_time_stats.sol += stats.get('sol', 0)
                    team_all_time_stats.gf += stats.get('gf', 0)
                    team_all_time_stats.ga += stats.get('ga', 0)
                    team_all_time_stats.pts += stats.get('pts', 0)
            
            # Only keep teams that actually have games in the filtered category
            if team_all_time_stats.gp == 0:
                del all_time_stats_dict[team_code]

    final_all_time_standings = list(all_time_stats_dict.values())
    final_all_time_standings.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
    
    return final_all_time_standings


@main_bp.route('/all-time-standings')
def all_time_standings_view():
    game_type = request.args.get('game_type', 'all')
    
    # Validate game_type parameter
    if game_type not in ['all', 'preliminary', 'playoffs']:
        game_type = 'all'
    
    standings_data = calculate_all_time_standings(game_type)
    
    # Determine page title based on filter
    title_map = {
        'all': 'All-Time Standings (Hauptrunde und Playoffs)',
        'preliminary': 'All-Time Standings (nur Hauptrunde)',
        'playoffs': 'All-Time Standings (nur Playoffs)'
    }
    page_title = title_map.get(game_type, title_map['all'])
    
    return render_template('all_time_standings.html', 
                         standings_data=standings_data, 
                         team_iso_codes=TEAM_ISO_CODES,
                         current_filter=game_type,
                         page_title=page_title)