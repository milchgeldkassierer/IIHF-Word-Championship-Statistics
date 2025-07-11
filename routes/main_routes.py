import os
import json
from typing import Dict, List
from flask import Blueprint, current_app
from models import db, ChampionshipYear, Game, AllTimeTeamStats, TeamStats, Player, Goal, Penalty, GameDisplay, ShotsOnGoal, GameOverrule
from utils import is_code_final, _apply_head_to_head_tiebreaker, get_resolved_team_code, resolve_game_participants
from constants import PRELIM_ROUNDS, PLAYOFF_ROUNDS, PIM_MAP
from sqlalchemy import func, case
import traceback
import re

main_bp = Blueprint('main_bp', __name__)

# Import route functions from modular structure to register them with the blueprint
# These imports will register the routes with main_bp
import routes.tournament.management
import routes.standings.all_time
import routes.standings.medals  
import routes.players.stats
import routes.players.management
import routes.api.team_stats



def get_tournament_statistics(year_obj):
    """
    Calculate tournament statistics: games completed, total games, goals, penalties and winner
    Returns dict with: total_games, completed_games, goals, penalties, avg_goals_per_game, avg_penalties_per_game, winner
    """
    if not year_obj:
        return {
            'total_games': 0, 
            'completed_games': 0, 
            'goals': 0, 
            'penalties': 0, 
            'avg_goals_per_game': 0.0,
            'avg_penalties_per_game': 0.0,
            'winner': None
        }
    
    all_games = Game.query.filter_by(year_id=year_obj.id).all()
    total_games = len(all_games)
    
    completed_games_list = [game for game in all_games if game.team1_score is not None and game.team2_score is not None]
    completed_games = len(completed_games_list)
    
    # Calculate goals and penalties for completed games only
    goals_count = 0
    penalties_count = 0
    
    if completed_games > 0:
        # Calculate goals from game scores (same method as records.html)
        goals_count = sum(game.team1_score + game.team2_score for game in completed_games_list)
        
        # Calculate PIM from penalty types (same method as records.html)
        from constants import PIM_MAP
        penalties_count = db.session.query(
            func.sum(
                case(
                    *[(Penalty.penalty_type == penalty_type, pim_value) for penalty_type, pim_value in PIM_MAP.items()],
                    else_=2  # Default for unknown penalty types
                )
            )
        ).join(Game, Penalty.game_id == Game.id).filter(
            Game.year_id == year_obj.id,
            Game.team1_score.isnot(None),
            Game.team2_score.isnot(None)
        ).scalar() or 0
    
    # Calculate averages
    avg_goals_per_game = round(goals_count / completed_games, 2) if completed_games > 0 else 0.0
    avg_penalties_per_game = round(penalties_count / completed_games, 2) if completed_games > 0 else 0.0
    
    winner = None
    if completed_games == total_games and total_games > 0:
        final_game = None
        
        for game in all_games:
            if game.round and ('final' in game.round.lower() or 'gold medal' in game.round.lower() or 'gold' in game.round.lower()):
                final_game = game
                break
        
        if not final_game and all_games:
            max_game_number = max(game.game_number for game in all_games if game.game_number is not None)
            for game in all_games:
                if game.game_number == max_game_number:
                    final_game = game
                    break
                    
        if final_game and final_game.team1_score is not None and final_game.team2_score is not None:
            try:
                resolved_team1, resolved_team2 = resolve_game_participants(final_game, year_obj, all_games)
                
                if final_game.team1_score > final_game.team2_score:
                    winner = resolved_team1
                elif final_game.team2_score > final_game.team1_score:
                    winner = resolved_team2
            except Exception:
                if final_game.team1_score > final_game.team2_score:
                    winner = final_game.team1_code
                elif final_game.team2_score > final_game.team1_score:
                    winner = final_game.team2_code
    
    return {
        'total_games': total_games,
        'completed_games': completed_games,
        'goals': goals_count,
        'penalties': penalties_count,
        'avg_goals_per_game': avg_goals_per_game,
        'avg_penalties_per_game': avg_penalties_per_game,
        'winner': winner
    }

def calculate_all_time_standings():
    """
    Calculates all-time standings by aggregating yearly statistics directly from the API.
    This ensures perfect consistency with the yearly stats API.
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
    
    # For each team, use the API to get yearly stats and aggregate them
    for team_code in all_teams:
        # Use the same API logic internally
        yearly_stats_data = get_team_yearly_stats_internal_api(team_code)
        
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

    final_all_time_standings = list(all_time_stats_dict.values())
    final_all_time_standings.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
    
    return final_all_time_standings


def get_team_yearly_stats_internal_api(team_code):
    """Internal function that uses the same logic as the API endpoint"""
    # Directly call the API function without circular import
    with current_app.test_request_context():
        try:
            # Get the response from the API endpoint
            response = get_team_yearly_stats(team_code)
            if hasattr(response, 'get_json'):
                data = response.get_json()
                return data.get('yearly_stats', [])
            elif isinstance(response, dict):
                return response.get('yearly_stats', [])
            else:
                return []
        except Exception:
            return []


def calculate_team_yearly_stats_internal(team_code, year_id):
    """Internal function to calculate team yearly stats for a specific year"""
    # Get games for this year only
    games_raw = Game.query.filter_by(year_id=year_id).order_by(Game.date, Game.start_time, Game.game_number).all()
    games_raw_map = {g.id: g for g in games_raw}
    
    if not games_raw:
        return None
    
    year_obj = ChampionshipYear.query.get(year_id)
    if not year_obj:
        return None
    
    # Use same logic as get_team_yearly_stats API
    teams_stats = {}
    prelim_games = [g for g in games_raw if g.round == 'Preliminary Round' and g.group]
    
    # Build preliminary stats for playoff resolution
    unique_teams_in_prelim_groups = set()
    for g in prelim_games:
        if g.team1_code and g.group: 
            unique_teams_in_prelim_groups.add((g.team1_code, g.group))
        if g.team2_code and g.group: 
            unique_teams_in_prelim_groups.add((g.team2_code, g.group))

    for team_code_prelim, group_name in unique_teams_in_prelim_groups:
        if team_code_prelim not in teams_stats: 
            teams_stats[team_code_prelim] = TeamStats(name=team_code_prelim, group=group_name)

    for g in [pg for pg in prelim_games if pg.team1_score is not None]: 
        for code, grp, gf, ga, pts, res in [(g.team1_code, g.group, g.team1_score, g.team2_score, g.team1_points, g.result_type),
                                           (g.team2_code, g.group, g.team2_score, g.team1_score, g.team2_points, g.result_type)]:
            stats = teams_stats.setdefault(code, TeamStats(name=code, group=grp))
            
            if stats.group == grp: 
                stats.gp += 1
                stats.gf += gf
                stats.ga += ga
                stats.pts += pts
                if res == 'REG':
                    stats.w += 1 if gf > ga else 0
                    stats.l += 1 if ga > gf else 0 
                elif res == 'OT':
                    stats.otw += 1 if gf > ga else 0
                    stats.otl += 1 if ga > gf else 0
                elif res == 'SO':
                    stats.sow += 1 if gf > ga else 0
                    stats.sol += 1 if ga > gf else 0
    
    # Create playoff resolution map
    standings_by_group = {}
    if teams_stats:
        group_full_names = sorted(list(set(s.group for s in teams_stats.values() if s.group))) 
        for full_group_name_key in group_full_names: 
            current_group_teams = sorted(
                [s for s in teams_stats.values() if s.group == full_group_name_key],
                key=lambda x: (x.pts, x.gd, x.gf),
                reverse=True
            )
            current_group_teams = _apply_head_to_head_tiebreaker(current_group_teams, prelim_games)
            for i, team_stat_obj in enumerate(current_group_teams):
                team_stat_obj.rank_in_group = i + 1 
            
            standings_by_group[full_group_name_key] = current_group_teams

    playoff_team_map = {}
    for group_display_name, group_standings_list in standings_by_group.items():
        group_letter_match = re.match(r"Group ([A-D])", group_display_name) 
        if group_letter_match:
            group_letter = group_letter_match.group(1)
            for i, s_team_obj in enumerate(group_standings_list): 
                playoff_team_map[f'{group_letter}{i+1}'] = s_team_obj.name 
    
    # Get fixture data
    qf_game_numbers = []
    sf_game_numbers = []
    tournament_hosts = []

    if year_obj.fixture_path:
        absolute_fixture_path = resolve_fixture_path(year_obj.fixture_path)
        if absolute_fixture_path and os.path.exists(absolute_fixture_path):
            try:
                with open(absolute_fixture_path, 'r', encoding='utf-8') as fixture_file:
                    fixture_data = json.load(fixture_file)
                    qf_game_numbers = fixture_data.get("qf_game_numbers", [])
                    sf_game_numbers = fixture_data.get("sf_game_numbers", [])
                    tournament_hosts = fixture_data.get("host_teams", [])
            except (json.JSONDecodeError, OSError):
                pass

    # Add host teams to playoff map
    for host_team in tournament_hosts:
        if host_team in teams_stats:
            host_rank = teams_stats[host_team].rank_in_group
            playoff_team_map[f'H{host_rank}'] = host_team

    # Create games_processed with playoff resolution
    games_processed = []
    for raw_game in games_raw:
        if raw_game.team1_score is not None and raw_game.team2_score is not None:
            game_display = type('GameDisplay', (), {
                'id': raw_game.id,
                'original_team1_code': raw_game.team1_code,
                'original_team2_code': raw_game.team2_code,
                'team1_code': raw_game.team1_code,
                'team2_code': raw_game.team2_code,
                'team1_score': raw_game.team1_score,
                'team2_score': raw_game.team2_score,
                'result_type': raw_game.result_type,
                'round': raw_game.round,
                'game_number': raw_game.game_number
            })()
            games_processed.append(game_display)

    # Multi-pass resolution
    def get_resolved_code(code, playoff_map):
        return playoff_map.get(code, code)

    for _pass_num in range(max(3, len(games_processed) // 2)): 
        changes_in_pass = 0
        for g_disp in games_processed:
            resolved_t1 = get_resolved_code(g_disp.original_team1_code, playoff_team_map)
            if g_disp.team1_code != resolved_t1: 
                g_disp.team1_code = resolved_t1
                changes_in_pass += 1
            
            resolved_t2 = get_resolved_code(g_disp.original_team2_code, playoff_team_map)
            if g_disp.team2_code != resolved_t2: 
                g_disp.team2_code = resolved_t2
                changes_in_pass += 1

            if g_disp.round != 'Preliminary Round' and g_disp.team1_score is not None:
                is_t1_final = is_code_final(g_disp.team1_code)
                is_t2_final = is_code_final(g_disp.team2_code)

                if is_t1_final and is_t2_final:
                    actual_winner = g_disp.team1_code if g_disp.team1_score > g_disp.team2_score else g_disp.team2_code
                    actual_loser = g_disp.team2_code if g_disp.team1_score > g_disp.team2_score else g_disp.team1_code
                    
                    win_key = f'W({g_disp.game_number})'
                    lose_key = f'L({g_disp.game_number})'
                    if playoff_team_map.get(win_key) != actual_winner: 
                        playoff_team_map[win_key] = actual_winner
                        changes_in_pass += 1
                    if playoff_team_map.get(lose_key) != actual_loser: 
                        playoff_team_map[lose_key] = actual_loser
                        changes_in_pass += 1
        
        if changes_in_pass == 0 and _pass_num > 0: 
            break

    # Apply custom seeding
    if qf_game_numbers and sf_game_numbers and len(sf_game_numbers) == 2:
        qf_winners_teams = []
        all_qf_winners_resolved = True
        for qf_game_num in qf_game_numbers:
            winner_placeholder = f'W({qf_game_num})'
            resolved_qf_winner = get_resolved_code(winner_placeholder, playoff_team_map)
            if is_code_final(resolved_qf_winner):
                qf_winners_teams.append(resolved_qf_winner)
            else:
                all_qf_winners_resolved = False
                break
        
        if all_qf_winners_resolved and len(qf_winners_teams) == 4:
            qf_winners_stats = []
            for team_name in qf_winners_teams:
                if team_name in teams_stats: 
                    qf_winners_stats.append(teams_stats[team_name])
                else: 
                    all_qf_winners_resolved = False
                    break
            
            if all_qf_winners_resolved and len(qf_winners_stats) == 4:
                qf_winners_stats.sort(key=lambda ts: (ts.rank_in_group, -ts.pts, -ts.gd, -ts.gf))
                
                # Check for custom seeding
                try:
                    from routes.year.seeding import get_custom_seeding_from_db
                    custom_seeding = get_custom_seeding_from_db(year_id)
                except ImportError:
                    custom_seeding = None
                
                if custom_seeding:
                    R1 = custom_seeding.get('seed1')
                    R2 = custom_seeding.get('seed2') 
                    R3 = custom_seeding.get('seed3')
                    R4 = custom_seeding.get('seed4')
                    
                    custom_teams = [R1, R2, R3, R4]
                    qf_team_names = [ts.name for ts in qf_winners_stats]
                    
                    if all(team in qf_team_names for team in custom_teams):
                        pass  # Use custom seeding
                    else:
                        R1, R2, R3, R4 = [ts.name for ts in qf_winners_stats]
                else:
                    R1, R2, R3, R4 = [ts.name for ts in qf_winners_stats]

                playoff_team_map['Q1'] = R1
                playoff_team_map['Q2'] = R2
                playoff_team_map['Q3'] = R3
                playoff_team_map['Q4'] = R4

    # Final resolution pass
    for g_disp_final_pass in games_processed:
        code_to_resolve_t1 = g_disp_final_pass.original_team1_code 
        resolved_t1_final = get_resolved_code(code_to_resolve_t1, playoff_team_map)
        if g_disp_final_pass.team1_code != resolved_t1_final:
            g_disp_final_pass.team1_code = resolved_t1_final

        code_to_resolve_t2 = g_disp_final_pass.original_team2_code
        resolved_t2_final = get_resolved_code(code_to_resolve_t2, playoff_team_map)
        if g_disp_final_pass.team2_code != resolved_t2_final:
            g_disp_final_pass.team2_code = resolved_t2_final

    # Calculate stats for this specific team
    games_processed_map = {g.id: g for g in games_processed}
    
    # Initialize stats
    gp = w = otw = sow = l = otl = sol = gf = ga = pts = 0
    
    # Check each game
    for game_id, resolved_game in games_processed_map.items():
        raw_game = games_raw_map.get(game_id)
        if not raw_game:
            continue

        # Check if this team is involved
        is_team1 = resolved_game.team1_code == team_code
        is_team2 = resolved_game.team2_code == team_code
        
        if not (is_team1 or is_team2):
            continue

        if raw_game.team1_score is not None and raw_game.team2_score is not None:
            gp += 1
            team_score = raw_game.team1_score if is_team1 else raw_game.team2_score
            opp_score = raw_game.team2_score if is_team1 else raw_game.team1_score
            gf += team_score
            ga += opp_score
            
            team_points = raw_game.team1_points if is_team1 else raw_game.team2_points
            pts += team_points
            
            result_type = raw_game.result_type
            if result_type == 'REG':
                if team_score > opp_score:
                    w += 1
                else:
                    l += 1
            elif result_type == 'OT':
                if team_score > opp_score:
                    otw += 1
                else:
                    otl += 1
            elif result_type == 'SO':
                if team_score > opp_score:
                    sow += 1
                else:
                    sol += 1
    
    if gp == 0:
        return None
    
    return {
        'games_played': gp,
        'wins': w,
        'overtime_wins': otw,
        'shootout_wins': sow,
        'losses': l,
        'overtime_losses': otl,
        'shootout_losses': sol,
        'goals_for': gf,
        'goals_against': ga,
        'points': pts
    }

    games_by_year_id = {}
    for game_obj in all_games:
        games_by_year_id.setdefault(game_obj.year_id, []).append(game_obj)

    resolved_playoff_maps_by_year_id = {}
    
    # Pre-calculate correct medal game rankings for each year (with custom seeding)
    medal_game_rankings_by_year = {}
    for year_id, games_in_this_year in games_by_year_id.items():
        year_obj = year_objects_map.get(year_id)
        if year_obj:
            try:
                # CRITICAL: Apply custom seeding BEFORE calculating final ranking
                playoff_map_for_ranking = {}
                # Custom seeding logic would go here if needed
                # For now, we continue without custom seeding for most years
                
                final_ranking = calculate_complete_final_ranking(year_obj, games_in_this_year, playoff_map_for_ranking, year_obj)
                medal_game_rankings_by_year[year_id] = final_ranking
            except Exception as e:
                current_app.logger.warning(f"Could not calculate final ranking for year {year_id}: {e}")
                medal_game_rankings_by_year[year_id] = {}

    for year_id, games_in_this_year in games_by_year_id.items():
        year_obj = year_objects_map.get(year_id)
        if not year_obj:
            current_app.logger.warning(f"Year object not found for year_id {year_id}. Skipping playoff map generation for this year.")
            continue

        prelim_stats_map_this_year: Dict[str, TeamStats] = {}
        prelim_games_for_standings_calc = [
            g for g in games_in_this_year
            if g.round in PRELIM_ROUNDS and \
               is_code_final(g.team1_code) and \
               is_code_final(g.team2_code) and \
               g.team1_score is not None and g.team2_score is not None
        ]

        for game_prelim in prelim_games_for_standings_calc:
            current_game_group = game_prelim.group or "N/A"
            for team_code_val in [game_prelim.team1_code, game_prelim.team2_code]:
                if team_code_val not in prelim_stats_map_this_year:
                    prelim_stats_map_this_year[team_code_val] = TeamStats(name=team_code_val, group=current_game_group)
                elif prelim_stats_map_this_year[team_code_val].group == "N/A" and current_game_group != "N/A":
                    prelim_stats_map_this_year[team_code_val].group = current_game_group
            
            t1_stats = prelim_stats_map_this_year[game_prelim.team1_code]
            t2_stats = prelim_stats_map_this_year[game_prelim.team2_code]

            t1_stats.gp += 1; t2_stats.gp += 1
            t1_stats.gf += game_prelim.team1_score; t1_stats.ga += game_prelim.team2_score
            t2_stats.gf += game_prelim.team2_score; t2_stats.ga += game_prelim.team1_score

            if game_prelim.result_type == 'REG':
                if game_prelim.team1_score > game_prelim.team2_score: 
                    (t1_stats.w, t1_stats.pts, t2_stats.l) = (t1_stats.w+1, t1_stats.pts+3, t2_stats.l+1)
                else: 
                    (t2_stats.w, t2_stats.pts, t1_stats.l) = (t2_stats.w+1, t2_stats.pts+3, t1_stats.l+1)
            elif game_prelim.result_type == 'OT':
                if game_prelim.team1_score > game_prelim.team2_score: 
                    (t1_stats.otw, t1_stats.pts, t2_stats.otl, t2_stats.pts) = (t1_stats.otw+1, t1_stats.pts+2, t2_stats.otl+1, t2_stats.pts+1)
                else: 
                    (t2_stats.otw, t2_stats.pts, t1_stats.otl, t1_stats.pts) = (t2_stats.otw+1, t2_stats.pts+2, t1_stats.otl+1, t1_stats.pts+1)
            elif game_prelim.result_type == 'SO':
                if game_prelim.team1_score > game_prelim.team2_score: 
                    (t1_stats.sow, t1_stats.pts, t2_stats.sol, t2_stats.pts) = (t1_stats.sow+1, t1_stats.pts+2, t2_stats.sol+1, t2_stats.pts+1)
                else: 
                    (t2_stats.sow, t2_stats.pts, t1_stats.sol, t1_stats.pts) = (t2_stats.sow+1, t2_stats.pts+2, t1_stats.sol+1, t1_stats.pts+1)

        prelim_standings_by_group_this_year: Dict[str, List[TeamStats]] = {}
        for ts_obj in prelim_stats_map_this_year.values():
            group_key = ts_obj.group if ts_obj.group else "UnknownGroup"
            prelim_standings_by_group_this_year.setdefault(group_key, []).append(ts_obj)
        
        for group_list in prelim_standings_by_group_this_year.values():
            group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
            group_list = _apply_head_to_head_tiebreaker(group_list, prelim_games_for_standings_calc)
            for i, ts_in_group in enumerate(group_list):
                ts_in_group.rank_in_group = i + 1
        
        current_year_playoff_map: Dict[str, str] = {}
        all_games_this_year_map_by_number: Dict[int, Game] = {g.game_number: g for g in games_in_this_year if g.game_number is not None}

        qf_gns, sf_gns, h_tcs = [], [], []
        fixture_absolute_path = resolve_fixture_path(year_obj.fixture_path)
        if year_obj.fixture_path and fixture_absolute_path and os.path.exists(fixture_absolute_path):
            try:
                with open(fixture_absolute_path, 'r', encoding='utf-8') as f: 
                    fixture_data = json.load(f)
                qf_gns = fixture_data.get("qf_game_numbers") or [57, 58, 59, 60]
                sf_gns = fixture_data.get("sf_game_numbers") or [61, 62]
                h_tcs = fixture_data.get("host_teams", [])
            except (json.JSONDecodeError, OSError): 
                qf_gns = [57, 58, 59, 60]; sf_gns = [61, 62]
        else: 
            qf_gns = [57, 58, 59, 60]; sf_gns = [61, 62]

        for grp_name_iter, grp_teams_stats_list in prelim_standings_by_group_this_year.items():
            for team_s in grp_teams_stats_list:
                group_letter = team_s.group
                if group_letter and group_letter.startswith("Group "):
                    group_letter = group_letter.replace("Group ", "")
                current_year_playoff_map[f"{group_letter}{team_s.rank_in_group}"] = team_s.name
                if h_tcs and team_s.name in h_tcs: 
                    current_year_playoff_map[f"H{team_s.rank_in_group}"] = team_s.name
        
        if qf_gns and len(qf_gns) >= 4:
            for i, qf_game_num in enumerate(qf_gns[:4]):
                qf_winner_placeholder = f"Q{i+1}"
                game_winner_placeholder = f"W({qf_game_num})"
                current_year_playoff_map[qf_winner_placeholder] = game_winner_placeholder

        max_iter_passes, current_pass, map_changed_this_iter = 10, 0, True
        while map_changed_this_iter and current_pass < max_iter_passes:
            map_changed_this_iter = False; current_pass += 1
            for pk, mc in list(current_year_playoff_map.items()):
                if not is_code_final(mc):
                    rc = get_resolved_team_code(mc, current_year_playoff_map, all_games_this_year_map_by_number)
                    if rc != mc and is_code_final(rc): 
                        current_year_playoff_map[pk] = rc; map_changed_this_iter = True
            
            for g_playoff in games_in_this_year:
                if g_playoff.round in PLAYOFF_ROUNDS and g_playoff.game_number and \
                   g_playoff.team1_score is not None and g_playoff.team2_score is not None:
                    rt1 = get_resolved_team_code(g_playoff.team1_code, current_year_playoff_map, all_games_this_year_map_by_number)
                    rt2 = get_resolved_team_code(g_playoff.team2_code, current_year_playoff_map, all_games_this_year_map_by_number)
                    if not is_code_final(rt1) or not is_code_final(rt2): 
                        continue
                    
                    wac = rt1 if g_playoff.team1_score > g_playoff.team2_score else rt2
                    lac = rt2 if g_playoff.team1_score > g_playoff.team2_score else rt1
                    wp, lp = f"W({g_playoff.game_number})", f"L({g_playoff.game_number})"
                    if current_year_playoff_map.get(wp) != wac: 
                        current_year_playoff_map[wp] = wac; map_changed_this_iter = True
                    if current_year_playoff_map.get(lp) != lac: 
                        current_year_playoff_map[lp] = lac; map_changed_this_iter = True
                    
                    if sf_gns and g_playoff.game_number in sf_gns:
                        sf_index = sf_gns.index(g_playoff.game_number) + 1
                        sf_winner_placeholder = f"W(SF{sf_index})"
                        sf_loser_placeholder = f"L(SF{sf_index})"
                        if current_year_playoff_map.get(sf_winner_placeholder) != wac: 
                            current_year_playoff_map[sf_winner_placeholder] = wac; map_changed_this_iter = True
                        if current_year_playoff_map.get(sf_loser_placeholder) != lac: 
                            current_year_playoff_map[sf_loser_placeholder] = lac; map_changed_this_iter = True
            
            if sf_gns and len(sf_gns) >= 2:
                sf_game_1 = all_games_this_year_map_by_number.get(sf_gns[0])
                sf_game_2 = all_games_this_year_map_by_number.get(sf_gns[1])
                
                if sf_game_1 and sf_game_2:
                    q1_team = current_year_playoff_map.get('Q1')
                    q2_team = current_year_playoff_map.get('Q2') 
                    q3_team = current_year_playoff_map.get('Q3')
                    q4_team = current_year_playoff_map.get('Q4')
                    
                    if q1_team and q1_team.startswith('W('):
                        q1_resolved = current_year_playoff_map.get(q1_team)
                        if q1_resolved and is_code_final(q1_resolved):
                            current_year_playoff_map['Q1'] = q1_resolved
                            q1_team = q1_resolved
                            map_changed_this_iter = True

                    if q2_team and q2_team.startswith('W('):
                        q2_resolved = current_year_playoff_map.get(q2_team)
                        if q2_resolved and is_code_final(q2_resolved):
                            current_year_playoff_map['Q2'] = q2_resolved
                            q2_team = q2_resolved
                            map_changed_this_iter = True

                    if q3_team and q3_team.startswith('W('):
                        q3_resolved = current_year_playoff_map.get(q3_team)
                        if q3_resolved and is_code_final(q3_resolved):
                            current_year_playoff_map['Q3'] = q3_resolved
                            q3_team = q3_resolved
                            map_changed_this_iter = True

                    if q4_team and q4_team.startswith('W('):
                        q4_resolved = current_year_playoff_map.get(q4_team)
                        if q4_resolved and is_code_final(q4_resolved):
                            current_year_playoff_map['Q4'] = q4_resolved
                            q4_team = q4_resolved
                            map_changed_this_iter = True

                    if q1_team and is_code_final(q1_team) and q2_team and is_code_final(q2_team):
                        if sf_game_1.team1_code == 'Q1' and sf_game_1.team2_code == 'Q2':
                            current_year_playoff_map['Q1'] = q1_team
                            current_year_playoff_map['Q2'] = q2_team
                            map_changed_this_iter = True

                    if q3_team and is_code_final(q3_team) and q4_team and is_code_final(q4_team):
                        if sf_game_2.team1_code == 'Q3' and sf_game_2.team2_code == 'Q4':
                            current_year_playoff_map['Q3'] = q3_team
                            current_year_playoff_map['Q4'] = q4_team
                            map_changed_this_iter = True
        
        # Apply custom seeding after all team resolution is complete
        # Import here to avoid circular imports
        try:
            from routes.year.seeding import get_custom_seeding_from_db
            custom_seeding = get_custom_seeding_from_db(year_id)
            if custom_seeding:
                # Override Q1-Q4 mappings with custom seeding
                current_year_playoff_map['Q1'] = custom_seeding['seed1']
                current_year_playoff_map['Q2'] = custom_seeding['seed2']
                current_year_playoff_map['Q3'] = custom_seeding['seed3']
                current_year_playoff_map['Q4'] = custom_seeding['seed4']
        except ImportError:
            pass  # If import fails, continue without custom seeding
                    
        resolved_playoff_maps_by_year_id[year_id] = current_year_playoff_map

    all_time_stats_dict = {}
    for game in all_games:
        if game.team1_score is None or game.team2_score is None:
            continue

        year_id = game.year_id
        current_year_playoff_map = resolved_playoff_maps_by_year_id.get(year_id)
        if current_year_playoff_map is None:
            current_app.logger.warning(
                f"Playoff map not found for year_id {year_id} when processing game GID:{game.id}. "
                f"Original team codes ('{game.team1_code}', '{game.team2_code}') will be used for resolution attempt."
            )
            current_year_playoff_map = {}
        
        # CRITICAL: Special handling for Medal Games AND Semifinals using correct final ranking
        final_team1_code = None
        final_team2_code = None
        
        if game.round in ['Gold Medal Game', 'Bronze Medal Game', 'Semifinals']:
            # Use correct medal game resolution from calculate_complete_final_ranking
            year_ranking = medal_game_rankings_by_year.get(year_id, {})
            if year_ranking:
                if game.round == 'Gold Medal Game':
                    final_team1_code = year_ranking.get(1)  # Gold
                    final_team2_code = year_ranking.get(2)  # Silver
                    # Ensure correct order based on actual game result
                    if (final_team1_code and final_team2_code and 
                        game.team1_score is not None and game.team2_score is not None):
                        # If resolved teams don't match game structure, swap them
                        if (game.team1_score > game.team2_score and final_team1_code != year_ranking.get(1)) or \
                           (game.team2_score > game.team1_score and final_team2_code != year_ranking.get(1)):
                            final_team1_code, final_team2_code = final_team2_code, final_team1_code
                elif game.round == 'Bronze Medal Game':
                    final_team1_code = year_ranking.get(3)  # Bronze
                    final_team2_code = year_ranking.get(4)  # Fourth
                    # Ensure correct order based on actual game result
                    if (final_team1_code and final_team2_code and 
                        game.team1_score is not None and game.team2_score is not None):
                        # If resolved teams don't match game structure, swap them
                        if (game.team1_score > game.team2_score and final_team1_code != year_ranking.get(3)) or \
                           (game.team2_score > game.team1_score and final_team2_code != year_ranking.get(3)):
                            final_team1_code, final_team2_code = final_team2_code, final_team1_code
                elif game.round == 'Semifinals':
                    # CRITICAL: Use same logic as get_all_resolved_games() for semifinals
                    # Check for custom seeding first
                    try:
                        from routes.year.seeding import get_custom_seeding_from_db
                        custom_seeding = get_custom_seeding_from_db(year_id)
                        if custom_seeding:
                            # Direct assignment based on custom seeding and game number
                            if game.game_number == 61:  # SF1: seed1 vs seed4
                                # Get the two teams that played in SF1
                                team_a = custom_seeding['seed1']
                                team_b = custom_seeding['seed4']
                            elif game.game_number == 62:  # SF2: seed2 vs seed3
                                # Get the two teams that played in SF2
                                team_a = custom_seeding['seed2']
                                team_b = custom_seeding['seed3']
                            else:
                                team_a = None
                                team_b = None
                            
                            # Assign teams to final codes (order doesn't matter much, just ensure they're assigned)
                            if team_a and team_b:
                                final_team1_code = team_a
                                final_team2_code = team_b
                        else:
                            # No custom seeding - use standard resolution (will happen in fallback below)
                            pass
                    except ImportError:
                        # If import fails, use standard resolution (will happen in fallback below)
                        pass

        # Fallback to standard resolution if medal game resolution failed
        if not final_team1_code or not final_team2_code:
            # Apply custom seeding for this specific year if it exists
            # Import here to avoid circular imports
            try:
                from routes.year.seeding import get_custom_seeding_from_db
                custom_seeding = get_custom_seeding_from_db(year_id)
                if custom_seeding:
                    # Create a copy of the playoff map and override Q1-Q4 with custom seeding
                    current_year_playoff_map = current_year_playoff_map.copy()
                    current_year_playoff_map['Q1'] = custom_seeding['seed1']
                    current_year_playoff_map['Q2'] = custom_seeding['seed2']
                    current_year_playoff_map['Q3'] = custom_seeding['seed3']
                    current_year_playoff_map['Q4'] = custom_seeding['seed4']
            except ImportError:
                pass  # If import fails, continue without custom seeding

            current_year_games_list = games_by_year_id.get(year_id, [])
            current_year_games_map_by_number = {g.game_number: g for g in current_year_games_list if g.game_number is not None}

            resolved_team1_code = get_resolved_team_code(game.team1_code, current_year_playoff_map, current_year_games_map_by_number)
            resolved_team2_code = get_resolved_team_code(game.team2_code, current_year_playoff_map, current_year_games_map_by_number)

            has_final_resolved_codes = is_code_final(resolved_team1_code) and is_code_final(resolved_team2_code)
            has_final_original_codes = is_code_final(game.team1_code) and is_code_final(game.team2_code)
            
            if not (has_final_resolved_codes or has_final_original_codes):
                skipped_games_count = getattr(calculate_all_time_standings, '_skipped_count', 0) + 1
                calculate_all_time_standings._skipped_count = skipped_games_count
                continue
                
            if has_final_resolved_codes:
                final_team1_code = resolved_team1_code
                final_team2_code = resolved_team2_code
            else:
                final_team1_code = game.team1_code
                final_team2_code = game.team2_code
            
        year_of_game = game.championship_year.year if game.championship_year else None

        if final_team1_code not in all_time_stats_dict:
            all_time_stats_dict[final_team1_code] = AllTimeTeamStats(team_code=final_team1_code)
        team1_stats = all_time_stats_dict[final_team1_code]
        
        if final_team2_code not in all_time_stats_dict:
            all_time_stats_dict[final_team2_code] = AllTimeTeamStats(team_code=final_team2_code)
        team2_stats = all_time_stats_dict[final_team2_code]

        if year_of_game:
            team1_stats.years_participated.add(year_of_game)
            team2_stats.years_participated.add(year_of_game)

        team1_stats.gp += 1
        team2_stats.gp += 1
        team1_stats.gf += game.team1_score
        team1_stats.ga += game.team2_score
        team2_stats.gf += game.team2_score
        team2_stats.ga += game.team1_score
        
        if game.team1_score > game.team2_score:
            winner_stats, loser_stats = team1_stats, team2_stats
        else:
            winner_stats, loser_stats = team2_stats, team1_stats
        
        if game.result_type == 'REG':
            winner_stats.w += 1; winner_stats.pts += 3
            loser_stats.l += 1
        elif game.result_type == 'OT':
            winner_stats.otw += 1; winner_stats.pts += 2
            loser_stats.otl += 1; loser_stats.pts += 1
        elif game.result_type == 'SO':
            winner_stats.sow += 1; winner_stats.pts += 2
            loser_stats.sol += 1; loser_stats.pts += 1
        elif game.result_type:
             current_app.logger.warning(f"Game ID {game.id} has unhandled result_type: '{game.result_type}'. Points not assigned for this type.")

    final_all_time_standings = list(all_time_stats_dict.values())
    final_all_time_standings.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
    
    skipped_count = getattr(calculate_all_time_standings, '_skipped_count', 0)
    if skipped_count > 0:
        calculate_all_time_standings._skipped_count = 0
    
    return final_all_time_standings



def calculate_complete_final_ranking(year_obj, games_this_year, playoff_map, year_obj_for_map):
    final_ranking = {}
    
    def trace_team_from_medal_games():
        sf_games = [g for g in games_this_year if g.round == "Semifinals" and g.team1_score is not None and g.team2_score is not None]
        
        # Bei manuell geändertem Seeding: sammle alle Semifinal-Gewinner und -Verlierer
        # unabhängig von Game-Nummern, da die Zuordnung durch das Custom Seeding gestört ist
        sf_winners = []
        sf_losers = []
        sf_results = {}
        
        for sf_game in sf_games:
            # Löse die Teams direkt auf, falls sie noch Platzhalter sind
            team1_resolved = sf_game.team1_code
            team2_resolved = sf_game.team2_code
            
            # Bei manuell geändertem Seeding sind die Teams schon echte Team-Codes
            if is_code_final(team1_resolved) and is_code_final(team2_resolved):
                winner = team1_resolved if sf_game.team1_score > sf_game.team2_score else team2_resolved
                loser = team2_resolved if sf_game.team1_score > sf_game.team2_score else team1_resolved
            else:
                # Fallback für den Fall, dass noch Platzhalter verwendet werden
                winner = sf_game.team1_code if sf_game.team1_score > sf_game.team2_score else sf_game.team2_code
                loser = sf_game.team2_code if sf_game.team1_score > sf_game.team2_score else sf_game.team1_code
            
            sf_winners.append(winner)
            sf_losers.append(loser)
            
            # Noch die ursprüngliche Zuordnung für Fallback-Kompatibilität
            if sf_game.game_number == 61:  # SF1
                sf_results["W(SF1)"] = winner
                sf_results["L(SF1)"] = loser
            elif sf_game.game_number == 62:  # SF2  
                sf_results["W(SF2)"] = winner
                sf_results["L(SF2)"] = loser
        
        team_map = {}
        prelim_games = [g for g in games_this_year if g.round in PRELIM_ROUNDS and is_code_final(g.team1_code) and is_code_final(g.team2_code)]
        
        group_standings = {}
        for game in prelim_games:
            if game.team1_score is None or game.team2_score is None:
                continue
                
            group = game.group
            if not group:
                continue
                
            if group not in group_standings:
                group_standings[group] = {}
                
            for team in [game.team1_code, game.team2_code]:
                if team not in group_standings[group]:
                    group_standings[group][team] = {'pts': 0, 'gf': 0, 'ga': 0}
            
            t1_score, t2_score = game.team1_score, game.team2_score
            group_standings[group][game.team1_code]['gf'] += t1_score
            group_standings[group][game.team1_code]['ga'] += t2_score
            group_standings[group][game.team2_code]['gf'] += t2_score  
            group_standings[group][game.team2_code]['ga'] += t1_score
            
            if game.result_type == 'REG':
                if t1_score > t2_score:
                    group_standings[group][game.team1_code]['pts'] += 3
                else:
                    group_standings[group][game.team2_code]['pts'] += 3
            elif game.result_type in ['OT', 'SO']:
                if t1_score > t2_score:
                    group_standings[group][game.team1_code]['pts'] += 2
                    group_standings[group][game.team2_code]['pts'] += 1
                else:
                    group_standings[group][game.team2_code]['pts'] += 2
                    group_standings[group][game.team1_code]['pts'] += 1
        
        for group, teams in group_standings.items():
            team_stats_list = []
            for team_name, stats in teams.items():
                ts = TeamStats(name=team_name, group=group)
                ts.pts = stats['pts']
                ts.gf = stats['gf'] 
                ts.ga = stats['ga']
                team_stats_list.append(ts)
            
            team_stats_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
            team_stats_list = _apply_head_to_head_tiebreaker(team_stats_list, prelim_games)
            
            group_letter = group.replace("Group ", "") if group.startswith("Group ") else group
            for i, team_stat in enumerate(team_stats_list, 1):
                team_map[f"{group_letter}{i}"] = team_stat.name
        
        qf_games = [g for g in games_this_year if g.round == "Quarterfinals" and g.team1_score is not None and g.team2_score is not None]
        qf_games.sort(key=lambda x: x.game_number or 0)
        
        qf_winners = []
        for qf_game in qf_games:
            winner_code = qf_game.team1_code if qf_game.team1_score > qf_game.team2_score else qf_game.team2_code
            if winner_code in team_map:
                actual_team = team_map[winner_code]
                qf_winners.append(actual_team)
            else:
                qf_winners.append(winner_code)
        
        qf_winner_stats = []
        for actual_team in qf_winners:
            team_rank_in_group = None
            team_group = None
            team_stats = None
            
            for placeholder, mapped_team in team_map.items():
                if mapped_team == actual_team:
                    if len(placeholder) >= 2:
                        team_group = placeholder[0]
                        try:
                            team_rank_in_group = int(placeholder[1:])
                        except ValueError:
                            continue
                    break
            
            for group, teams in group_standings.items():
                group_letter = group.replace("Group ", "") if group.startswith("Group ") else group
                if group_letter == team_group and actual_team in teams:
                    team_stats = teams[actual_team]
                    break
            
            if team_rank_in_group and team_stats:
                qf_winner_stats.append({
                    'team': actual_team,
                    'group': team_group,
                    'rank_in_group': team_rank_in_group,
                    'pts': team_stats['pts'],
                    'gd': team_stats['gf'] - team_stats['ga'],
                    'gf': team_stats['gf']
                })
        
        qf_winner_stats.sort(key=lambda x: (x['rank_in_group'], -x['pts'], -x['gd'], -x['gf']))
        
        qf_results = {}
        
        # CRITICAL: Use playoff_map for Q1-Q4 if provided (contains custom seeding)
        if playoff_map and all(key in playoff_map for key in ['Q1', 'Q2', 'Q3', 'Q4']):
            # Use playoff_map (which contains custom seeding)
            qf_results["Q1"] = playoff_map['Q1']
            qf_results["Q2"] = playoff_map['Q2']
            qf_results["Q3"] = playoff_map['Q3']
            qf_results["Q4"] = playoff_map['Q4']
        elif len(qf_winner_stats) >= 4:
            # Fallback to calculated seeding if no playoff_map provided
            qf_results["Q1"] = qf_winner_stats[0]['team']
            qf_results["Q2"] = qf_winner_stats[3]['team']
            qf_results["Q3"] = qf_winner_stats[1]['team']
            qf_results["Q4"] = qf_winner_stats[2]['team']
        
        def resolve_code(code):
            if is_code_final(code):
                return code
            if code in team_map:
                return team_map[code]
            if code in qf_results:
                return resolve_code(qf_results[code])
            if code in sf_results:
                return resolve_code(sf_results[code])
            
            # Spezielle Behandlung für Medal Game Platzhalter bei manuell geändertem Seeding
            # Da die Game-Nummer-basierte Zuordnung gestört ist, nutze die tatsächlichen Ergebnisse
            if code.startswith('L(SF') and len(sf_losers) >= 2:
                # Für Bronze Medal Game: nutze die beiden Semifinal-Verlierer
                if code == 'L(SF1)':
                    return sf_losers[0] if is_code_final(sf_losers[0]) else sf_losers[0]
                elif code == 'L(SF2)':
                    return sf_losers[1] if is_code_final(sf_losers[1]) else sf_losers[1]
            elif code.startswith('W(SF') and len(sf_winners) >= 2:
                # Für Gold Medal Game: nutze die beiden Semifinal-Gewinner
                if code == 'W(SF1)':
                    return sf_winners[0] if is_code_final(sf_winners[0]) else sf_winners[0]
                elif code == 'W(SF2)':
                    return sf_winners[1] if is_code_final(sf_winners[1]) else sf_winners[1]
                    
            return code
        
        return resolve_code

    resolve_team = trace_team_from_medal_games()
    
    games_map = {g.game_number: g for g in games_this_year if g.game_number is not None}
    
    # Finde Medal Games (Bronze und Final)
    bronze_game = None
    final_game = None
    
    for game in games_this_year:
        if game.round == "Bronze Medal Game":
            bronze_game = game
        elif game.round == "Gold Medal Game":
            final_game = game
    
    # GENERELLE LÖSUNG FÜR CUSTOM SEEDING PROBLEM
    # Verbesserte Medal Game Auflösung die mit allen Jahren und Seeding-Arten funktioniert
    
    # Sammle alle Semifinal-Ergebnisse mit korrekter Team-Auflösung
    semifinal_teams_resolved = {}
    sf_games = [g for g in games_this_year if g.round == "Semifinals" and g.team1_score is not None and g.team2_score is not None]
    
    for sf_game in sf_games:
        # Löse Teams auf (bei Custom Seeding sind es bereits echte Teams, sonst Platzhalter)
        team1 = sf_game.team1_code if is_code_final(sf_game.team1_code) else resolve_team(sf_game.team1_code)
        team2 = sf_game.team2_code if is_code_final(sf_game.team2_code) else resolve_team(sf_game.team2_code)
        
        winner = team1 if sf_game.team1_score > sf_game.team2_score else team2
        loser = team2 if sf_game.team1_score > sf_game.team2_score else team1
        
        # Speichere mit Game-Nummer für korrekte Zuordnung
        game_key = f"SF{sf_game.game_number - 60}" if sf_game.game_number >= 61 else f"SF{len(semifinal_teams_resolved) + 1}"
        semifinal_teams_resolved[f"W({game_key})"] = winner
        semifinal_teams_resolved[f"L({game_key})"] = loser
    
    # Prüfe ob Custom Seeding verwendet wird
    has_custom_seeding = False
    try:
        from routes.year.seeding import get_custom_seeding_from_db
        custom_seeding = get_custom_seeding_from_db(year_obj_for_map.id)
        has_custom_seeding = custom_seeding is not None
    except Exception as e:
        has_custom_seeding = False
    
    # Bei Custom Seeding: Komplett neue Medal Game Berechnung um Platzhalter-Probleme zu umgehen
    if has_custom_seeding:
        # Sammle alle Semifinal-Ergebnisse
        sf_winners = []
        sf_losers = []
        for sf_game in sf_games:
            team1 = sf_game.team1_code if is_code_final(sf_game.team1_code) else resolve_team(sf_game.team1_code)
            team2 = sf_game.team2_code if is_code_final(sf_game.team2_code) else resolve_team(sf_game.team2_code)
            
            winner = team1 if sf_game.team1_score > sf_game.team2_score else team2
            loser = team2 if sf_game.team1_score > sf_game.team2_score else team1
            
            if is_code_final(winner):
                sf_winners.append(winner)
            if is_code_final(loser):
                sf_losers.append(loser)
        
        # INTELLIGENTE MEDAL GAME AUFLÖSUNG
        # Versuche zuerst die Platzhalter aufzulösen
        if bronze_game and len(sf_losers) >= 2:
            # Versuche Standard-Platzhalter-Auflösung
            try:
                resolved_bronze_team1 = resolve_team(bronze_game.team1_code)
                resolved_bronze_team2 = resolve_team(bronze_game.team2_code)
                
                # Prüfe ob das eine Standard-Struktur ist (beide Teams sind SF Losers)
                if resolved_bronze_team1 in sf_losers and resolved_bronze_team2 in sf_losers:
                    if bronze_game.team1_score > bronze_game.team2_score:
                        final_ranking[3] = resolved_bronze_team1  # Bronze
                        final_ranking[4] = resolved_bronze_team2  # 4th
                    else:
                        final_ranking[3] = resolved_bronze_team2  # Bronze
                        final_ranking[4] = resolved_bronze_team1  # 4th
                    
                else:
                    # Cross-Over: Einer ist SF Winner, einer ist SF Loser
                    # Bronze Game Gewinner = Bronze, Verlierer = 4th
                    if bronze_game.team1_score > bronze_game.team2_score:
                        final_ranking[3] = resolved_bronze_team1  # Bronze
                        final_ranking[4] = resolved_bronze_team2  # 4th
                    else:
                        final_ranking[3] = resolved_bronze_team2  # Bronze  
                        final_ranking[4] = resolved_bronze_team1  # 4th
                    
            except Exception as e:
                # Fallback: Verwende SF Losers
                if bronze_game.team1_score > bronze_game.team2_score:
                    final_ranking[3] = sf_losers[0]
                    final_ranking[4] = sf_losers[1]
                else:
                    final_ranking[3] = sf_losers[1]
                    final_ranking[4] = sf_losers[0]
            
        if final_game and len(sf_winners) >= 2:
            # Versuche Standard-Platzhalter-Auflösung
            try:
                resolved_final_team1 = resolve_team(final_game.team1_code)
                resolved_final_team2 = resolve_team(final_game.team2_code)
                
                # Prüfe ob das eine Standard-Struktur ist (beide Teams sind SF Winners)
                if resolved_final_team1 in sf_winners and resolved_final_team2 in sf_winners:
                    if final_game.team1_score > final_game.team2_score:
                        final_ranking[1] = resolved_final_team1  # Gold
                        final_ranking[2] = resolved_final_team2  # Silver
                    else:
                        final_ranking[1] = resolved_final_team2  # Gold
                        final_ranking[2] = resolved_final_team1  # Silver
                    
                else:
                    # Cross-Over: Einer ist SF Winner, einer ist SF Loser  
                    # Final Game Gewinner = Gold, Verlierer = Silver
                    if final_game.team1_score > final_game.team2_score:
                        final_ranking[1] = resolved_final_team1  # Gold
                        final_ranking[2] = resolved_final_team2  # Silver
                    else:
                        final_ranking[1] = resolved_final_team2  # Gold
                        final_ranking[2] = resolved_final_team1  # Silver
                    
            except Exception as e:
                # Fallback: Verwende SF Winners
                if final_game.team1_score > final_game.team2_score:
                    final_ranking[1] = sf_winners[0]
                    final_ranking[2] = sf_winners[1]
                else:
                    final_ranking[1] = sf_winners[1]
                    final_ranking[2] = sf_winners[0]
    
    else:
        # Standard-Auflösung für normale Jahre ohne Custom Seeding
        def resolve_medal_placeholder(placeholder):
            # Erste Priorität: direkte Auflösung über semifinal_teams_resolved
            if placeholder in semifinal_teams_resolved:
                return semifinal_teams_resolved[placeholder]
            
            # Zweite Priorität: Standard resolve_team Funktion
            resolved = resolve_team(placeholder)
            if is_code_final(resolved):
                return resolved
                
            # Dritte Priorität: Fallback für häufige Platzhalter-Muster
            if placeholder in ['L(SF1)', 'L(SF2)']:
                # Finde Semifinal-Verlierer
                sf_losers = [v for k, v in semifinal_teams_resolved.items() if k.startswith('L(SF') and is_code_final(v)]
                if len(sf_losers) >= 2:
                    return sf_losers[0] if placeholder == 'L(SF1)' else sf_losers[1]
            elif placeholder in ['W(SF1)', 'W(SF2)']:
                # Finde Semifinal-Gewinner
                sf_winners = [v for k, v in semifinal_teams_resolved.items() if k.startswith('W(SF') and is_code_final(v)]
                if len(sf_winners) >= 2:
                    return sf_winners[0] if placeholder == 'W(SF1)' else sf_winners[1]
            
            return placeholder  # Fallback
        
        # Standard Medal Game Auflösung
        if bronze_game and bronze_game.team1_score is not None and bronze_game.team2_score is not None:
            bronze_team1 = resolve_medal_placeholder(bronze_game.team1_code)
            bronze_team2 = resolve_medal_placeholder(bronze_game.team2_code)
            
            if bronze_game.team1_score > bronze_game.team2_score:
                final_ranking[3] = bronze_team1  # Bronze Gewinner
                final_ranking[4] = bronze_team2  # 4. Platz
            else:
                final_ranking[3] = bronze_team2  # Bronze Gewinner
                final_ranking[4] = bronze_team1  # 4. Platz
        
        if final_game and final_game.team1_score is not None and final_game.team2_score is not None:
            final_team1 = resolve_medal_placeholder(final_game.team1_code)
            final_team2 = resolve_medal_placeholder(final_game.team2_code)
            
            if final_game.team1_score > final_game.team2_score:
                final_ranking[1] = final_team1  # Gold Gewinner
                final_ranking[2] = final_team2  # Silber (Finalist-Verlierer)
            else:
                final_ranking[1] = final_team2  # Gold Gewinner
                final_ranking[2] = final_team1  # Silber (Finalist-Verlierer)
    
    # Berechne die restlichen Plätze (5-16)
    prelim_stats_map = {}
    prelim_games = [
        g for g in games_this_year
        if g.round in PRELIM_ROUNDS and \
           is_code_final(g.team1_code) and \
           is_code_final(g.team2_code) and \
           g.team1_score is not None and g.team2_score is not None
    ]
    
    for game in prelim_games:
        current_game_group = game.group or "N/A"
        for team_code in [game.team1_code, game.team2_code]:
            if team_code not in prelim_stats_map:
                prelim_stats_map[team_code] = TeamStats(name=team_code, group=current_game_group)
            elif prelim_stats_map[team_code].group == "N/A" and current_game_group != "N/A":
                prelim_stats_map[team_code].group = current_game_group
        
        t1_stats = prelim_stats_map[game.team1_code]
        t2_stats = prelim_stats_map[game.team2_code]
        
        t1_stats.gp += 1; t2_stats.gp += 1
        t1_stats.gf += game.team1_score; t1_stats.ga += game.team2_score
        t2_stats.gf += game.team2_score; t2_stats.ga += game.team1_score
        
        if game.result_type == 'REG':
            if game.team1_score > game.team2_score: 
                t1_stats.w += 1; t1_stats.pts += 3; t2_stats.l += 1
            else: 
                t2_stats.w += 1; t2_stats.pts += 3; t1_stats.l += 1
        elif game.result_type == 'OT':
            if game.team1_score > game.team2_score: 
                t1_stats.otw += 1; t1_stats.pts += 2; t2_stats.otl += 1; t2_stats.pts += 1
            else: 
                t2_stats.otw += 1; t2_stats.pts += 2; t1_stats.otl += 1; t1_stats.pts += 1
        elif game.result_type == 'SO':
            if game.team1_score > game.team2_score: 
                t1_stats.sow += 1; t1_stats.pts += 2; t2_stats.sol += 1; t2_stats.pts += 1
            else: 
                t2_stats.sow += 1; t2_stats.pts += 2; t1_stats.sol += 1; t1_stats.pts += 1
    
    standings_by_group = {}
    for ts in prelim_stats_map.values():
        group_key = ts.group if ts.group else "UnknownGroup"
        standings_by_group.setdefault(group_key, []).append(ts)
    
    for group_list in standings_by_group.values():
        group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        group_list = _apply_head_to_head_tiebreaker(group_list, prelim_games)
        for i, ts in enumerate(group_list):
            ts.rank_in_group = i + 1
    
    qf_losers = []
    qf_games = [g for g in games_this_year if g.round == "Quarterfinals" and g.team1_score is not None and g.team2_score is not None]
    
    for qf_game in qf_games:
        loser_code = qf_game.team2_code if qf_game.team1_score > qf_game.team2_score else qf_game.team1_code
        loser_resolved = resolve_team(loser_code)
        if is_code_final(loser_resolved):
            qf_losers.append(loser_resolved)
    
    qf_losers_stats = [prelim_stats_map.get(team) for team in qf_losers if team in prelim_stats_map]
    qf_losers_stats = [ts for ts in qf_losers_stats if ts is not None]
    qf_losers_stats.sort(key=lambda x: (x.rank_in_group, -x.pts, -x.gd, -x.gf))
    
    for i, ts in enumerate(qf_losers_stats):
        if 5 + i <= 8:
            final_ranking[5 + i] = ts.name
    
    all_playoff_teams = set(final_ranking.values())
    remaining_teams = []
    
    for ts in prelim_stats_map.values():
        if ts.name not in all_playoff_teams:
            remaining_teams.append(ts)
    
    remaining_teams.sort(key=lambda x: (x.rank_in_group, -x.pts, -x.gd, -x.gf))
    
    current_position = 9
    for ts in remaining_teams:
        if current_position <= 16:
            final_ranking[current_position] = ts.name
            current_position += 1

    return final_ranking

def get_medal_tally_data():
    medal_tally_results = []

    all_games = Game.query.options(db.joinedload(Game.championship_year)).all()
    all_years = ChampionshipYear.query.order_by(ChampionshipYear.year.desc()).all()
    year_objects_map = {year.id: year for year in all_years}

    completed_years = []
    for year_obj in all_years:
        tournament_stats = get_tournament_statistics(year_obj)
        is_completed = (tournament_stats['total_games'] > 0 and 
                       tournament_stats['completed_games'] == tournament_stats['total_games'])
        if is_completed:
            completed_years.append(year_obj)

    games_by_year_id = {}
    for game_obj in all_games:
        games_by_year_id.setdefault(game_obj.year_id, []).append(game_obj)

    # KRITISCH: Pre-calculate correct medal game rankings (wie in record_routes.py)
    # Diese bewährte Methode funktioniert korrekt
    medal_game_rankings_by_year = {}
    
    for year_obj in completed_years:
        games_this_year = games_by_year_id.get(year_obj.id, [])
        
        # Build a basic playoff map for this year including custom seeding (wie in record_routes.py)
        temp_playoff_map = {}
        
        # Apply custom seeding if it exists (wie in record_routes.py)
        try:
            from routes.year.seeding import get_custom_seeding_from_db
            custom_seeding = get_custom_seeding_from_db(year_obj.id)
            if custom_seeding:
                temp_playoff_map['Q1'] = custom_seeding['seed1']
                temp_playoff_map['Q2'] = custom_seeding['seed2']
                temp_playoff_map['Q3'] = custom_seeding['seed3']
                temp_playoff_map['Q4'] = custom_seeding['seed4']
        except:
            pass
        
        # Pre-calculate final ranking for this year (wie in record_routes.py)
        try:
            final_ranking = calculate_complete_final_ranking(year_obj, games_this_year, temp_playoff_map, year_obj)
            medal_game_rankings_by_year[year_obj.id] = final_ranking
        except Exception as e:
            medal_game_rankings_by_year[year_obj.id] = {}

    resolved_playoff_maps_by_year_id = {}

    for year_obj_for_map in completed_years:
        year_id_iter = year_obj_for_map.id
        games_in_this_year = games_by_year_id.get(year_id_iter, [])
        
        if not games_in_this_year:
            current_app.logger.warning(f"MedalTally: No games found for completed year_id {year_id_iter}. Skipping.")
            continue

        prelim_stats_map_this_year = {}
        prelim_games_for_standings_calc = [
            g for g in games_in_this_year
            if g.round in PRELIM_ROUNDS and \
               is_code_final(g.team1_code) and \
               is_code_final(g.team2_code) and \
               g.team1_score is not None and g.team2_score is not None
        ]

        for game_prelim in prelim_games_for_standings_calc:
            current_game_group = game_prelim.group or "N/A"
            for team_code_val in [game_prelim.team1_code, game_prelim.team2_code]:
                if team_code_val not in prelim_stats_map_this_year:
                    prelim_stats_map_this_year[team_code_val] = TeamStats(name=team_code_val, group=current_game_group)
                elif prelim_stats_map_this_year[team_code_val].group == "N/A" and current_game_group != "N/A":
                    prelim_stats_map_this_year[team_code_val].group = current_game_group
            
            t1_stats = prelim_stats_map_this_year[game_prelim.team1_code]
            t2_stats = prelim_stats_map_this_year[game_prelim.team2_code]

            t1_stats.gp += 1; t2_stats.gp += 1
            t1_stats.gf += game_prelim.team1_score; t1_stats.ga += game_prelim.team2_score
            t2_stats.gf += game_prelim.team2_score; t2_stats.ga += game_prelim.team1_score

            if game_prelim.result_type == 'REG':
                if game_prelim.team1_score > game_prelim.team2_score: (t1_stats.w, t1_stats.pts, t2_stats.l) = (t1_stats.w+1, t1_stats.pts+3, t2_stats.l+1)
                else: (t2_stats.w, t2_stats.pts, t1_stats.l) = (t2_stats.w+1, t2_stats.pts+3, t1_stats.l+1)
            elif game_prelim.result_type == 'OT':
                if game_prelim.team1_score > game_prelim.team2_score: (t1_stats.otw, t1_stats.pts, t2_stats.otl, t2_stats.pts) = (t1_stats.otw+1, t1_stats.pts+2, t2_stats.otl+1, t2_stats.pts+1)
                else: (t2_stats.otw, t2_stats.pts, t1_stats.otl, t1_stats.pts) = (t2_stats.otw+1, t2_stats.pts+2, t1_stats.otl+1, t1_stats.pts+1)
            elif game_prelim.result_type == 'SO':
                if game_prelim.team1_score > game_prelim.team2_score: (t1_stats.sow, t1_stats.pts, t2_stats.sol, t2_stats.pts) = (t1_stats.sow+1, t1_stats.pts+2, t2_stats.sol+1, t2_stats.pts+1)
                else: (t2_stats.sow, t2_stats.pts, t1_stats.sol, t1_stats.pts) = (t2_stats.sow+1, t2_stats.pts+2, t1_stats.sol+1, t1_stats.pts+1)

        prelim_standings_by_group_this_year = {}
        for ts_obj in prelim_stats_map_this_year.values():
            group_key = ts_obj.group if ts_obj.group else "UnknownGroup"
            prelim_standings_by_group_this_year.setdefault(group_key, []).append(ts_obj)
        
        for group_list in prelim_standings_by_group_this_year.values():
            group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
            group_list = _apply_head_to_head_tiebreaker(group_list, prelim_games_for_standings_calc)
            for i, ts_in_group in enumerate(group_list):
                ts_in_group.rank_in_group = i + 1
        
        current_year_playoff_map = {}
        all_games_this_year_map_by_number_local = {g.game_number: g for g in games_in_this_year if g.game_number is not None}

        qf_gns, sf_gns, h_tcs = [], [], []
        fixture_absolute_path = resolve_fixture_path(year_obj_for_map.fixture_path)
        if year_obj_for_map.fixture_path and fixture_absolute_path and os.path.exists(fixture_absolute_path):
            try:
                with open(fixture_absolute_path, 'r', encoding='utf-8') as f: 
                    fixture_data = json.load(f)
                qf_gns = fixture_data.get("qf_game_numbers") or [57, 58, 59, 60]
                sf_gns = fixture_data.get("sf_game_numbers") or [61, 62]
                h_tcs = fixture_data.get("host_teams", [])
            except (json.JSONDecodeError, OSError): 
                qf_gns = [57, 58, 59, 60]; sf_gns = [61, 62]
        else: 
            qf_gns = [57, 58, 59, 60]; sf_gns = [61, 62]

        for grp_name_iter, grp_teams_stats_list in prelim_standings_by_group_this_year.items():
            for team_s in grp_teams_stats_list:
                group_letter = team_s.group
                if group_letter and group_letter.startswith("Group "):
                    group_letter = group_letter.replace("Group ", "")
                current_year_playoff_map[f"{group_letter}{team_s.rank_in_group}"] = team_s.name
                if h_tcs and team_s.name in h_tcs: 
                    current_year_playoff_map[f"H{team_s.rank_in_group}"] = team_s.name

        if qf_gns and len(qf_gns) >= 4:
            for i, qf_game_num in enumerate(qf_gns[:4]):
                current_year_playoff_map[f"Q{i+1}"] = f"W({qf_game_num})"
        
        max_iter_passes, current_pass, map_changed_this_iter = 10, 0, True
        while map_changed_this_iter and current_pass < max_iter_passes:
            map_changed_this_iter = False; current_pass += 1
            for pk, mc in list(current_year_playoff_map.items()):
                if not is_code_final(mc):
                    rc = get_resolved_team_code(mc, current_year_playoff_map, all_games_this_year_map_by_number_local)
                    if rc != mc and is_code_final(rc): 
                        current_year_playoff_map[pk] = rc; map_changed_this_iter = True
            
            for g_playoff in games_in_this_year:
                if g_playoff.round in PLAYOFF_ROUNDS and g_playoff.game_number and \
                   g_playoff.team1_score is not None and g_playoff.team2_score is not None:
                    rt1 = get_resolved_team_code(g_playoff.team1_code, current_year_playoff_map, all_games_this_year_map_by_number_local)
                    rt2 = get_resolved_team_code(g_playoff.team2_code, current_year_playoff_map, all_games_this_year_map_by_number_local)
                    if not is_code_final(rt1) or not is_code_final(rt2): 
                        continue
                    
                    wac = rt1 if g_playoff.team1_score > g_playoff.team2_score else rt2
                    lac = rt2 if g_playoff.team1_score > g_playoff.team2_score else rt1
                    wp, lp = f"W({g_playoff.game_number})", f"L({g_playoff.game_number})"
                    if current_year_playoff_map.get(wp) != wac: 
                        current_year_playoff_map[wp] = wac; map_changed_this_iter = True
                    if current_year_playoff_map.get(lp) != lac: 
                        current_year_playoff_map[lp] = lac; map_changed_this_iter = True
                    
                    if sf_gns and g_playoff.game_number in sf_gns:
                        sf_index = sf_gns.index(g_playoff.game_number) + 1
                        sf_winner_placeholder = f"W(SF{sf_index})"
                        sf_loser_placeholder = f"L(SF{sf_index})"
                        if current_year_playoff_map.get(sf_winner_placeholder) != wac: 
                            current_year_playoff_map[sf_winner_placeholder] = wac; map_changed_this_iter = True
                        if current_year_playoff_map.get(sf_loser_placeholder) != lac: 
                            current_year_playoff_map[sf_loser_placeholder] = lac; map_changed_this_iter = True
            
            if sf_gns and len(sf_gns) >= 2:
                sf_game_1_obj = all_games_this_year_map_by_number_local.get(sf_gns[0])
                sf_game_2_obj = all_games_this_year_map_by_number_local.get(sf_gns[1])
                
                if sf_game_1_obj and sf_game_2_obj:
                    q1_team = current_year_playoff_map.get('Q1')
                    q2_team = current_year_playoff_map.get('Q2') 
                    q3_team = current_year_playoff_map.get('Q3')
                    q4_team = current_year_playoff_map.get('Q4')
                    
                    if q1_team and q1_team.startswith('W('):
                        q1_resolved = current_year_playoff_map.get(q1_team)
                        if q1_resolved and is_code_final(q1_resolved):
                            current_year_playoff_map['Q1'] = q1_resolved
                            q1_team = q1_resolved
                            map_changed_this_iter = True

                    if q2_team and q2_team.startswith('W('):
                        q2_resolved = current_year_playoff_map.get(q2_team)
                        if q2_resolved and is_code_final(q2_resolved):
                            current_year_playoff_map['Q2'] = q2_resolved
                            q2_team = q2_resolved
                            map_changed_this_iter = True

                    if q3_team and q3_team.startswith('W('):
                        q3_resolved = current_year_playoff_map.get(q3_team)
                        if q3_resolved and is_code_final(q3_resolved):
                            current_year_playoff_map['Q3'] = q3_resolved
                            q3_team = q3_resolved
                            map_changed_this_iter = True

                    if q4_team and q4_team.startswith('W('):
                        q4_resolved = current_year_playoff_map.get(q4_team)
                        if q4_resolved and is_code_final(q4_resolved):
                            current_year_playoff_map['Q4'] = q4_resolved
                            q4_team = q4_resolved
                            map_changed_this_iter = True

                    if q1_team and is_code_final(q1_team) and q2_team and is_code_final(q2_team):
                        if sf_game_1_obj.team1_code == 'Q1' and sf_game_1_obj.team2_code == 'Q2':
                            current_year_playoff_map['Q1'] = q1_team
                            current_year_playoff_map['Q2'] = q2_team
                            map_changed_this_iter = True

                    if q3_team and is_code_final(q3_team) and q4_team and is_code_final(q4_team):
                        if sf_game_2_obj.team1_code == 'Q3' and sf_game_2_obj.team2_code == 'Q4':
                            current_year_playoff_map['Q3'] = q3_team
                            current_year_playoff_map['Q4'] = q4_team
                            map_changed_this_iter = True
        
        # Apply custom seeding after all team resolution is complete
        # Import here to avoid circular imports
        try:
            from routes.year.seeding import get_custom_seeding_from_db
            custom_seeding = get_custom_seeding_from_db(year_id_iter)
            if custom_seeding:
                # Override Q1-Q4 mappings with custom seeding
                current_year_playoff_map['Q1'] = custom_seeding['seed1']
                current_year_playoff_map['Q2'] = custom_seeding['seed2']
                current_year_playoff_map['Q3'] = custom_seeding['seed3']
                current_year_playoff_map['Q4'] = custom_seeding['seed4']
        except ImportError:
            pass  # If import fails, continue without custom seeding
                    
        resolved_playoff_maps_by_year_id[year_id_iter] = current_year_playoff_map

    # KRITISCH: Verwende die vorberechneten Medal Rankings (wie in record_routes.py)
    # Diese bewährte Methode liefert die korrekten Ergebnisse
    for year_obj_medal_calc in completed_years:
        year_id_current = year_obj_medal_calc.id
        
        # Verwende die vorberechneten korrekten Medal Rankings
        final_ranking = medal_game_rankings_by_year.get(year_id_current, {})
        
        gold = final_ranking.get(1)
        silver = final_ranking.get(2)
        bronze = final_ranking.get(3)
        fourth = final_ranking.get(4)
            
        medal_tally_results.append({
            'year_obj': year_obj_medal_calc,
            'final_ranking': final_ranking,
            'gold': gold,
            'silver': silver,
            'bronze': bronze,
            'fourth': fourth
        })

    medal_tally_results.sort(key=lambda x: x['year_obj'].year, reverse=True)
    
    return medal_tally_results

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






