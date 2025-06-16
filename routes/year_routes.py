import json
import os
import re
import traceback
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from models import db, ChampionshipYear, Game, Player, Goal, Penalty, ShotsOnGoal, TeamStats, TeamOverallStats, GameDisplay, GameOverrule
from constants import TEAM_ISO_CODES, PENALTY_TYPES_CHOICES, PENALTY_REASONS_CHOICES, PIM_MAP, GOAL_TYPE_DISPLAY_MAP, POWERPLAY_PENALTY_TYPES
from utils import convert_time_to_seconds, check_game_data_consistency, is_code_final, _apply_head_to_head_tiebreaker
from routes.main_routes import resolve_fixture_path

year_bp = Blueprint('year_bp', __name__, url_prefix='/year')

@year_bp.route('/<int:year_id>', methods=['GET', 'POST'])
def year_view(year_id):
    
    year_obj = db.session.get(ChampionshipYear, year_id)
    if not year_obj:
        flash('Tournament year not found.', 'danger')
        return redirect(url_for('main_bp.index'))

    games_raw = Game.query.filter_by(year_id=year_id).order_by(Game.date, Game.start_time, Game.game_number).all()
    games_raw_map = {g.id: g for g in games_raw}

    sog_by_game_flat = {} 
    for sog_entry in ShotsOnGoal.query.join(Game).filter(Game.year_id == year_id).all():
        game_sog_data = sog_by_game_flat.setdefault(sog_entry.game_id, {})
        team_period_sog_data = game_sog_data.setdefault(sog_entry.team_code, {})
        team_period_sog_data[sog_entry.period] = sog_entry.shots

    if request.method == 'POST' and 'sog_team1_code_resolved' not in request.form:
        game_id_form = request.form.get('game_id')
        game_to_update = db.session.get(Game, game_id_form)
        if game_to_update:
            try:
                t1s = request.form.get('team1_score')
                t2s = request.form.get('team2_score')
                game_to_update.team1_score = int(t1s) if t1s and t1s.strip() else None
                game_to_update.team2_score = int(t2s) if t2s and t2s.strip() else None
                res_type = request.form.get('result_type')
                
                if game_to_update.team1_score is None or game_to_update.team2_score is None:
                    game_to_update.result_type = None
                    game_to_update.team1_points = 0
                    game_to_update.team2_points = 0
                else:
                    game_to_update.result_type = res_type
                    if res_type == 'REG':
                        if game_to_update.team1_score > game_to_update.team2_score:
                            pts1, pts2 = 3, 0
                        elif game_to_update.team2_score > game_to_update.team1_score:
                            pts1, pts2 = 0, 3
                        else:
                            pts1, pts2 = 1, 1 
                        game_to_update.team1_points, game_to_update.team2_points = pts1, pts2
                    elif res_type in ['OT', 'SO']:
                        if game_to_update.team1_score > game_to_update.team2_score:
                            game_to_update.team1_points, game_to_update.team2_points = 2, 1
                        else:
                            game_to_update.team1_points, game_to_update.team2_points = 1, 2
                db.session.commit()
                flash('Game result updated!', 'success')
                return redirect(url_for('year_bp.year_view', year_id=year_id, _anchor=f"game-{game_id_form}"))
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating result: {str(e)}', 'danger')
        else:
            flash('Game not found for update.', 'warning')

    teams_stats = {}
    prelim_games = [g for g in games_raw if g.round == 'Preliminary Round' and g.group]
    
    unique_teams_in_prelim_groups = set()
    for g in prelim_games:
        if g.team1_code and g.group: 
            unique_teams_in_prelim_groups.add((g.team1_code, g.group))
        if g.team2_code and g.group: 
            unique_teams_in_prelim_groups.add((g.team2_code, g.group))

    for team_code, group_name in unique_teams_in_prelim_groups:
        if team_code not in teams_stats: 
            teams_stats[team_code] = TeamStats(name=team_code, group=group_name)

    for g in [pg for pg in prelim_games if pg.team1_score is not None]: 
        for code, grp, gf, ga, pts, res, is_t1 in [(g.team1_code, g.group, g.team1_score, g.team2_score, g.team1_points, g.result_type, True),
                                                   (g.team2_code, g.group, g.team2_score, g.team1_score, g.team2_points, g.result_type, False)]:
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
    
    games_dict_by_num = {g.game_number: g for g in games_raw}
    
    qf_game_numbers = []
    sf_game_numbers = []
    bronze_game_number = None
    gold_game_number = None
    tournament_hosts = []

    fixture_path_exists = False
    if year_obj.fixture_path:
        absolute_fixture_path = resolve_fixture_path(year_obj.fixture_path)
        fixture_path_exists = absolute_fixture_path and os.path.exists(absolute_fixture_path)

    if year_obj.fixture_path and fixture_path_exists:
        try:
            with open(absolute_fixture_path, 'r', encoding='utf-8') as f:
                loaded_fixture_data = json.load(f)
            tournament_hosts = loaded_fixture_data.get("hosts", [])
            
            schedule_data = loaded_fixture_data.get("schedule", [])
            for game_data in schedule_data:
                round_name = game_data.get("round", "").lower()
                game_num = game_data.get("gameNumber")
                
                if "quarterfinal" in round_name: 
                    qf_game_numbers.append(game_num)
                elif "semifinal" in round_name: 
                    sf_game_numbers.append(game_num)
                elif "bronze medal game" in round_name or "bronze" in round_name or "3rd place" in round_name:
                    bronze_game_number = game_num
                elif "gold medal game" in round_name or "final" in round_name or "gold" in round_name:
                    gold_game_number = game_num
            sf_game_numbers.sort()
        except Exception as e: 
            current_app.logger.error(f"Could not parse fixture {year_obj.fixture_path} for playoff game numbers. Error: {e}") 
            if year_obj.year == 2025: 
                qf_game_numbers = [57, 58, 59, 60]
                sf_game_numbers = [61, 62]
                bronze_game_number = 63
                gold_game_number = 64
                tournament_hosts = ["SWE", "DEN"]

    if sf_game_numbers and len(sf_game_numbers) >= 2 and all(isinstance(item, int) for item in sf_game_numbers):
        playoff_team_map['SF1'] = str(sf_game_numbers[0])
        playoff_team_map['SF2'] = str(sf_game_numbers[1])

    def get_resolved_code(placeholder_code, current_map):
        max_depth = 5 
        current_code = placeholder_code
        for _ in range(max_depth):
            if current_code in current_map:
                next_code = current_map[current_code]
                if next_code == current_code:
                    return current_code 
                current_code = next_code
            elif (current_code.startswith('W(') or current_code.startswith('L(')) and current_code.endswith(')'):
                match = re.search(r'\(([^()]+)\)', current_code) 
                if match:
                    inner_placeholder = match.group(1)
                    if inner_placeholder.isdigit():
                        game_num = int(inner_placeholder)
                        game = games_dict_by_num.get(game_num)
                        if game and game.team1_score is not None:
                            raw_winner = game.team1_code if game.team1_score > game.team2_score else game.team2_code
                            raw_loser = game.team2_code if game.team1_score > game.team2_score else game.team1_code
                            outcome_based_code = raw_winner if current_code.startswith('W(') else raw_loser
                            next_code = current_map.get(outcome_based_code, outcome_based_code)
                            if next_code == current_code:
                                return next_code 
                            current_code = next_code 
                        else:
                            return current_code 
                    else: 
                        resolved_inner = current_map.get(inner_placeholder, inner_placeholder)
                        if resolved_inner == inner_placeholder:
                            return current_code 
                        if resolved_inner.isdigit():
                            current_code = f"{'W' if current_code.startswith('W(') else 'L'}({resolved_inner})"
                        else: 
                            return resolved_inner 
                else:
                    return current_code 
            else: 
                return current_code
        return current_code

    games_processed = [GameDisplay(id=g.id, year_id=g.year_id, date=g.date, start_time=g.start_time, round=g.round, group=g.group, game_number=g.game_number, location=g.location, venue=g.venue, team1_code=g.team1_code, team2_code=g.team2_code, original_team1_code=g.team1_code, original_team2_code=g.team2_code, team1_score=g.team1_score, team2_score=g.team2_score, result_type=g.result_type, team1_points=g.team1_points, team2_points=g.team2_points) for g in games_raw]

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

    # Semifinal and finals pairing logic
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
                R1, R2, R3, R4 = [ts.name for ts in qf_winners_stats] 

                matchup1 = (R1, R4)
                matchup2 = (R2, R3)
                sf_game1_teams = None
                sf_game2_teams = None
                primary_host_plays_sf1 = False

                if tournament_hosts:
                    if tournament_hosts[0] in [R1, R2, R3, R4]: 
                        primary_host_plays_sf1 = True
                        if R1 == tournament_hosts[0] or R4 == tournament_hosts[0]:
                            sf_game1_teams = matchup1
                            sf_game2_teams = matchup2
                        else:
                            sf_game1_teams = matchup2
                            sf_game2_teams = matchup1
                    elif len(tournament_hosts) > 1 and tournament_hosts[1] in [R1, R2, R3, R4]: 
                        primary_host_plays_sf1 = True 
                        if R1 == tournament_hosts[1] or R4 == tournament_hosts[1]:
                            sf_game1_teams = matchup1
                            sf_game2_teams = matchup2
                        else:
                            sf_game1_teams = matchup2
                            sf_game2_teams = matchup1
                
                if not primary_host_plays_sf1: 
                    sf_game1_teams = matchup1
                    sf_game2_teams = matchup2

                sf_game_obj_1 = games_dict_by_num.get(sf_game_numbers[0])
                sf_game_obj_2 = games_dict_by_num.get(sf_game_numbers[1])

                if sf_game_obj_1 and sf_game_obj_2 and sf_game1_teams and sf_game2_teams:
                    if playoff_team_map.get(sf_game_obj_1.team1_code) != sf_game1_teams[0]:
                        playoff_team_map[sf_game_obj_1.team1_code] = sf_game1_teams[0]
                    if playoff_team_map.get(sf_game_obj_1.team2_code) != sf_game1_teams[1]:
                        playoff_team_map[sf_game_obj_1.team2_code] = sf_game1_teams[1]
                    if playoff_team_map.get(sf_game_obj_2.team1_code) != sf_game2_teams[0]:
                        playoff_team_map[sf_game_obj_2.team1_code] = sf_game2_teams[0]
                    if playoff_team_map.get(sf_game_obj_2.team2_code) != sf_game2_teams[1]:
                        playoff_team_map[sf_game_obj_2.team2_code] = sf_game2_teams[1]
                    
                    # Add Q1-Q4 mappings based on the semifinal assignments
                    playoff_team_map['Q1'] = sf_game1_teams[0]
                    playoff_team_map['Q2'] = sf_game1_teams[1]
                    playoff_team_map['Q3'] = sf_game2_teams[0]
                    playoff_team_map['Q4'] = sf_game2_teams[1]

    # Fallback Q1-Q4 mapping
    if qf_game_numbers and len(qf_game_numbers) == 4 and 'Q1' not in playoff_team_map:
        for i, qf_game_num in enumerate(qf_game_numbers):
            winner_placeholder = f'W({qf_game_num})'
            resolved_qf_winner = get_resolved_code(winner_placeholder, playoff_team_map)
            
            if is_code_final(resolved_qf_winner):
                q_code = f'Q{i+1}'
                playoff_team_map[q_code] = resolved_qf_winner

    # Bronze and gold medal game logic
    if sf_game_numbers and len(sf_game_numbers) == 2 and bronze_game_number and gold_game_number:
        bronze_game_obj = games_dict_by_num.get(bronze_game_number)
        gold_game_obj = games_dict_by_num.get(gold_game_number)
        
        if bronze_game_obj and gold_game_obj:
            sf1_game_number = sf_game_numbers[0]
            sf2_game_number = sf_game_numbers[1]
            
            playoff_team_map['SF1'] = str(sf1_game_number)
            playoff_team_map['SF2'] = str(sf2_game_number)
            
            sf1_loser_placeholder = f'L({sf1_game_number})'
            sf2_loser_placeholder = f'L({sf2_game_number})'
            sf1_winner_placeholder = f'W({sf1_game_number})'
            sf2_winner_placeholder = f'W({sf2_game_number})'
            
            if playoff_team_map.get(bronze_game_obj.team1_code) != sf1_loser_placeholder:
                playoff_team_map[bronze_game_obj.team1_code] = sf1_loser_placeholder
            if playoff_team_map.get(bronze_game_obj.team2_code) != sf2_loser_placeholder:
                playoff_team_map[bronze_game_obj.team2_code] = sf2_loser_placeholder
                
            if playoff_team_map.get(gold_game_obj.team1_code) != sf1_winner_placeholder:
                playoff_team_map[gold_game_obj.team1_code] = sf1_winner_placeholder
            if playoff_team_map.get(gold_game_obj.team2_code) != sf2_winner_placeholder:
                playoff_team_map[gold_game_obj.team2_code] = sf2_winner_placeholder

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

    all_players_list = Player.query.order_by(Player.team_code, Player.last_name).all()
    player_cache = {p.id: p for p in all_players_list}
    selected_team_filter = request.args.get('stats_team_filter')
    
    player_stats_agg = {p.id: {'g': 0, 'a': 0, 'p': 0, 'obj': p} for p in all_players_list if not selected_team_filter or p.team_code == selected_team_filter}
    for goal in Goal.query.filter(Goal.game_id.in_([g.id for g in games_raw])).all():
        if goal.scorer_id in player_stats_agg:
            player_stats_agg[goal.scorer_id]['g'] += 1
            player_stats_agg[goal.scorer_id]['p'] += 1
        if goal.assist1_id and goal.assist1_id in player_stats_agg:
            player_stats_agg[goal.assist1_id]['a'] += 1
            player_stats_agg[goal.assist1_id]['p'] += 1
        if goal.assist2_id and goal.assist2_id in player_stats_agg:
            player_stats_agg[goal.assist2_id]['a'] += 1
            player_stats_agg[goal.assist2_id]['p'] += 1
    
    all_player_stats_list = [{'goals': v['g'], 'assists': v['a'], 'points': v['p'], 'player_obj': v['obj']} for v in player_stats_agg.values()]
    top_scorers_points = sorted([s for s in all_player_stats_list if s['points'] > 0], key=lambda x: (-x['points'], -x['goals'], x['player_obj'].last_name.lower()))
    top_goal_scorers = sorted([s for s in all_player_stats_list if s['goals'] > 0], key=lambda x: (-x['goals'], -x['points'], x['player_obj'].last_name.lower()))
    top_assist_providers = sorted([s for s in all_player_stats_list if s['assists'] > 0], key=lambda x: (-x['assists'], -x['points'], x['player_obj'].last_name.lower()))

    player_pim_agg = {p.id: {'pim': 0, 'obj': p} for p in all_players_list if (not selected_team_filter or p.team_code == selected_team_filter) and p.id is not None}
    all_penalties_for_year = Penalty.query.join(Game).filter(Game.year_id == year_id).all()
    for penalty_entry in all_penalties_for_year:
        if penalty_entry.player_id and penalty_entry.player_id in player_pim_agg:
            pim_value = PIM_MAP.get(penalty_entry.penalty_type, 0)
            player_pim_agg[penalty_entry.player_id]['pim'] += pim_value
    top_penalty_players = sorted([{'player_obj': v['obj'], 'pim': v['pim']} for v in player_pim_agg.values() if v['pim'] > 0], key=lambda x: (-x['pim'], x['player_obj'].last_name.lower()))

    game_nat_teams = set(g.team1_code for g in games_processed if not (g.team1_code.startswith(('A', 'B', 'W', 'L', 'Q', 'S')) and g.team1_code[1:].isdigit()))
    game_nat_teams.update(g.team2_code for g in games_processed if not (g.team2_code.startswith(('A', 'B', 'W', 'L', 'Q', 'S')) and g.team2_code[1:].isdigit()))
    player_nat_teams = set(p.team_code for p in all_players_list if p.team_code and not (p.team_code.startswith(('A', 'B', 'W', 'L', 'Q', 'S')) and p.team_code[1:].isdigit()))
    unique_teams_filter = sorted(list(game_nat_teams.union(player_nat_teams)))
    
    def get_pname(pid): 
        p = player_cache.get(pid)
        return f"{p.first_name} {p.last_name}" if p else "N/A"

    for g_disp in games_processed:
        g_disp.sorted_events = [] 
        for goal in Goal.query.filter_by(game_id=g_disp.id).all():
            g_disp.sorted_events.append({
                'type': 'goal',
                'time_str': goal.minute,
                'time_for_sort': convert_time_to_seconds(goal.minute),
                'data': {
                    'id': goal.id,
                    'team_code': goal.team_code,
                    'minute': goal.minute,
                    'goal_type_display': goal.goal_type,
                    'is_empty_net': goal.is_empty_net,
                    'scorer': get_pname(goal.scorer_id),
                    'assist1': get_pname(goal.assist1_id) if goal.assist1_id else None,
                    'assist2': get_pname(goal.assist2_id) if goal.assist2_id else None,
                    'team_iso': TEAM_ISO_CODES.get(goal.team_code.upper())
                }
            })
        for pnlty in Penalty.query.filter_by(game_id=g_disp.id).all():
            g_disp.sorted_events.append({
                'type': 'penalty',
                'time_str': pnlty.minute_of_game,
                'time_for_sort': convert_time_to_seconds(pnlty.minute_of_game),
                'data': {
                    'id': pnlty.id,
                    'team_code': pnlty.team_code,
                    'player_name': get_pname(pnlty.player_id) if pnlty.player_id else "Bank",
                    'minute_of_game': pnlty.minute_of_game,
                    'penalty_type': pnlty.penalty_type,
                    'reason': pnlty.reason,
                    'team_iso': TEAM_ISO_CODES.get(pnlty.team_code.upper())
                }
            })
        g_disp.sorted_events.sort(key=lambda x: x['time_for_sort'])
        
        sog_src = sog_by_game_flat.get(g_disp.id, {})
        team1_sog_values = sog_src.get(g_disp.team1_code, {})
        team2_sog_values = sog_src.get(g_disp.team2_code, {})

        g_disp.sog_data = {
            g_disp.team1_code: {p: team1_sog_values.get(p, 0) for p in range(1, 5)},
            g_disp.team2_code: {p: team2_sog_values.get(p, 0) for p in range(1, 5)}
        }
        
        consistency_check = check_game_data_consistency(g_disp, sog_src)
        g_disp.scores_fully_match_goals = consistency_check['scores_fully_match_data']

    # Load overrule data for all games
    all_overrules = GameOverrule.query.join(Game).filter(Game.year_id == year_id).all()
    overrule_by_game_id = {overrule.game_id: overrule for overrule in all_overrules}
    
    for g_disp in games_processed:
        g_disp.overrule = overrule_by_game_id.get(g_disp.id)

    games_by_round_display = {}
    for g_d in games_processed:
        games_by_round_display.setdefault(g_d.round or "Unk", []).append(g_d)

    games_processed_map = {g.id: g for g in games_processed}

    all_players_by_team_json = {
        team: [{'id': p.id, 'first_name': p.first_name, 'last_name': p.last_name, 'full_name': f"{p.last_name.upper()}, {p.first_name}"} 
               for p in all_players_list if p.team_code == team] 
        for team in unique_teams_filter
    }

    potential_teams = set()
    for g_disp in games_processed:
        if g_disp.team1_code and TEAM_ISO_CODES.get(g_disp.team1_code.upper()) is not None:
            potential_teams.add(g_disp.team1_code.upper())
        if g_disp.team2_code and TEAM_ISO_CODES.get(g_disp.team2_code.upper()) is not None:
            potential_teams.add(g_disp.team2_code.upper())
    for p_obj in all_players_list:
        if p_obj.team_code and TEAM_ISO_CODES.get(p_obj.team_code.upper()) is not None:
            potential_teams.add(p_obj.team_code.upper())
    unique_teams_in_year = sorted(list(potential_teams))

    # Build team_combinations_with_games dictionary for VS button logic
    team_combinations_with_games = {}
    all_games_across_years = Game.query.filter(
        Game.team1_score.isnot(None), 
        Game.team2_score.isnot(None)
    ).all()
    
    for game in all_games_across_years:
        if (TEAM_ISO_CODES.get(game.team1_code.upper()) and TEAM_ISO_CODES.get(game.team2_code.upper())):
            team_pair_sorted = sorted([game.team1_code, game.team2_code])
            team_pair_key = f"{team_pair_sorted[0]}_vs_{team_pair_sorted[1]}"
            team_combinations_with_games[team_pair_key] = True

    team_stats_data_list = []
    if unique_teams_in_year: 
        all_games_for_year = Game.query.filter_by(year_id=year_id).all()
        all_goals_for_year = Goal.query.join(Game).filter(Game.year_id == year_id).all()
        all_penalties_for_year_detailed = Penalty.query.join(Game).filter(Game.year_id == year_id).all()
        all_sog_for_year = ShotsOnGoal.query.join(Game).filter(Game.year_id == year_id).all()

        sog_by_game_team = {}
        for sog_entry in all_sog_for_year:
            game_sog = sog_by_game_team.setdefault(sog_entry.game_id, {})
            team_total_sog = game_sog.get(sog_entry.team_code, 0)
            game_sog[sog_entry.team_code] = team_total_sog + sog_entry.shots

        for team_code_upper in unique_teams_in_year:
            actual_team_code_from_games = None
            for g_disp_for_code in games_processed:
                if g_disp_for_code.team1_code.upper() == team_code_upper:
                    actual_team_code_from_games = g_disp_for_code.team1_code
                    break
                if g_disp_for_code.team2_code.upper() == team_code_upper:
                    actual_team_code_from_games = g_disp_for_code.team2_code
                    break
            
            if not actual_team_code_from_games:
                found_in_players = any(p.team_code.upper() == team_code_upper for p in all_players_list)
                if found_in_players:
                    player_team_match = next((p.team_code for p in all_players_list if p.team_code.upper() == team_code_upper), team_code_upper)
                    actual_team_code_from_games = player_team_match
                else: 
                    for g_raw_for_code_obj in games_raw_map.values():
                        if g_raw_for_code_obj.team1_code.upper() == team_code_upper:
                            actual_team_code_from_games = g_raw_for_code_obj.team1_code
                            break
                        if g_raw_for_code_obj.team2_code.upper() == team_code_upper:
                            actual_team_code_from_games = g_raw_for_code_obj.team2_code
                            break
                if not actual_team_code_from_games:
                    actual_team_code_from_games = team_code_upper 

            current_team_code = actual_team_code_from_games
            stats = TeamOverallStats(team_name=current_team_code, team_iso_code=TEAM_ISO_CODES.get(current_team_code.upper()))

            for game_id, resolved_game_this_iter in games_processed_map.items():
                raw_game_obj_this_iter = games_raw_map.get(game_id)
                if not raw_game_obj_this_iter:
                    continue

                is_current_team_t1_in_raw_game = False

                if resolved_game_this_iter.team1_code == current_team_code:
                    is_current_team_t1_in_raw_game = True
                elif resolved_game_this_iter.team2_code == current_team_code:
                    is_current_team_t1_in_raw_game = False 
                else:
                    continue

                if raw_game_obj_this_iter.team1_score is not None and raw_game_obj_this_iter.team2_score is not None: 
                    stats.gp += 1
                    current_team_score = raw_game_obj_this_iter.team1_score if is_current_team_t1_in_raw_game else raw_game_obj_this_iter.team2_score
                    opponent_score = raw_game_obj_this_iter.team2_score if is_current_team_t1_in_raw_game else raw_game_obj_this_iter.team1_score
                    stats.gf += current_team_score
                    stats.ga += opponent_score
                    if opponent_score == 0 and current_team_score > 0:
                        stats.so += 1
                
                game_sog_info = sog_by_game_team.get(raw_game_obj_this_iter.id, {})
                if resolved_game_this_iter.team1_code == current_team_code:
                    stats.sog += game_sog_info.get(current_team_code, 0)
                    stats.soga += game_sog_info.get(resolved_game_this_iter.team2_code, 0)
                elif resolved_game_this_iter.team2_code == current_team_code:
                    stats.sog += game_sog_info.get(current_team_code, 0)
                    stats.soga += game_sog_info.get(resolved_game_this_iter.team1_code, 0)
            
            for goal_event in all_goals_for_year:
                if goal_event.game_id not in games_processed_map:
                    continue
                
                resolved_game_of_goal = games_processed_map.get(goal_event.game_id)
                if not resolved_game_of_goal:
                    continue

                if goal_event.team_code == current_team_code:
                    if goal_event.is_empty_net:
                        stats.eng += 1
                    if goal_event.goal_type == 'PP':
                        stats.ppgf += 1
                elif (resolved_game_of_goal.team1_code == current_team_code and goal_event.team_code == resolved_game_of_goal.team2_code) or \
                     (resolved_game_of_goal.team2_code == current_team_code and goal_event.team_code == resolved_game_of_goal.team1_code):
                    if goal_event.goal_type == 'PP':
                        stats.ppga += 1

            for penalty_event in all_penalties_for_year_detailed:
                if penalty_event.game_id not in games_processed_map:
                    continue

                resolved_game_of_penalty = games_processed_map.get(penalty_event.game_id)
                if not resolved_game_of_penalty:
                    continue
                
                if penalty_event.team_code == current_team_code:
                    stats.pim += PIM_MAP.get(penalty_event.penalty_type, 0)
                    if penalty_event.penalty_type in POWERPLAY_PENALTY_TYPES:
                        stats.ppa += 1 
                elif (resolved_game_of_penalty.team1_code == current_team_code and penalty_event.team_code == resolved_game_of_penalty.team2_code) or \
                     (resolved_game_of_penalty.team2_code == current_team_code and penalty_event.team_code == resolved_game_of_penalty.team1_code):
                    if penalty_event.penalty_type in POWERPLAY_PENALTY_TYPES:
                        stats.ppf += 1
            team_stats_data_list.append(stats)

    return render_template('year_view.html', 
                           year=year_obj, games_by_round=games_by_round_display,
                           standings=standings_by_group, all_players=all_players_list, 
                           selected_team=selected_team_filter, unique_teams_in_year=unique_teams_in_year, 
                           team_iso_codes=TEAM_ISO_CODES, 
                           top_scorers_points=top_scorers_points, top_goal_scorers=top_goal_scorers,
                           top_assist_providers=top_assist_providers, top_penalty_players=top_penalty_players,
                           playoff_team_map=playoff_team_map, all_players_by_team_json=all_players_by_team_json,
                           team_codes=TEAM_ISO_CODES, penalty_types=PENALTY_TYPES_CHOICES,
                           penalty_reasons=PENALTY_REASONS_CHOICES, team_stats_data=team_stats_data_list,
                           team_combinations_with_games=team_combinations_with_games)

@year_bp.route('/<int:year_id>/stats_data')
def get_stats_data(year_id):
    selected_team_filter = request.args.get('stats_team_filter')
    year_obj = db.session.get(ChampionshipYear, year_id)
    if not year_obj:
        return jsonify({'error': 'Tournament year not found'}), 404

    all_players_list = Player.query.order_by(Player.team_code, Player.last_name).all()
    player_stats_agg = {p.id: {'g': 0, 'a': 0, 'p': 0, 'obj': p} for p in all_players_list if not selected_team_filter or p.team_code == selected_team_filter}
    all_goals_for_year = Goal.query.join(Game).filter(Game.year_id == year_id).all()

    for goal in all_goals_for_year:
        if goal.scorer_id in player_stats_agg:
            player_stats_agg[goal.scorer_id]['g'] += 1
            player_stats_agg[goal.scorer_id]['p'] += 1
        if goal.assist1_id and goal.assist1_id in player_stats_agg:
            player_stats_agg[goal.assist1_id]['a'] += 1
            player_stats_agg[goal.assist1_id]['p'] += 1
        if goal.assist2_id and goal.assist2_id in player_stats_agg:
            player_stats_agg[goal.assist2_id]['a'] += 1
            player_stats_agg[goal.assist2_id]['p'] += 1

    all_player_stats_list_for_json = [
        {'goals': v['g'], 'assists': v['a'], 'points': v['p'], 
         'player_obj': {'id': v['obj'].id, 'first_name': v['obj'].first_name, 'last_name': v['obj'].last_name, 'team_code': v['obj'].team_code}}
        for v in player_stats_agg.values()
    ]
    top_scorers_points = sorted([s for s in all_player_stats_list_for_json if s['points'] > 0], key=lambda x: (-x['points'], -x['goals'], x['player_obj']['last_name'].lower()))
    top_goal_scorers = sorted([s for s in all_player_stats_list_for_json if s['goals'] > 0], key=lambda x: (-x['goals'], -x['points'], x['player_obj']['last_name'].lower()))
    top_assist_providers = sorted([s for s in all_player_stats_list_for_json if s['assists'] > 0], key=lambda x: (-x['assists'], -x['points'], x['player_obj']['last_name'].lower()))

    player_pim_agg = {p.id: {'pim': 0, 'obj': {'id': p.id, 'first_name': p.first_name, 'last_name': p.last_name, 'team_code': p.team_code}} 
                      for p in all_players_list if (not selected_team_filter or p.team_code == selected_team_filter) and p.id is not None}
    all_penalties_for_year = Penalty.query.join(Game).filter(Game.year_id == year_id).all()
    for penalty_entry in all_penalties_for_year:
        if penalty_entry.player_id and penalty_entry.player_id in player_pim_agg:
            pim_value = PIM_MAP.get(penalty_entry.penalty_type, 0)
            player_pim_agg[penalty_entry.player_id]['pim'] += pim_value
    top_penalty_players = sorted([{'player_obj': v['obj'], 'pim': v['pim']} for v in player_pim_agg.values() if v['pim'] > 0], key=lambda x: (-x['pim'], x['player_obj']['last_name'].lower()))

    return jsonify({
        'top_scorers_points': top_scorers_points, 'top_goal_scorers': top_goal_scorers,
        'top_assist_providers': top_assist_providers, 'top_penalty_players': top_penalty_players,
        'selected_team': selected_team_filter or ""
    })

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

        existing_player = Player.query.filter_by(team_code=team_code, first_name=first_name, last_name=last_name).first()
        if existing_player:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': f'Player {first_name} {last_name} ({team_code}) already exists.'}), 400
            flash(f'Player {first_name} {last_name} ({team_code}) already exists.', 'warning')
        else:
            try:
                new_player = Player(team_code=team_code, first_name=first_name, last_name=last_name, jersey_number=jersey_number)
                db.session.add(new_player)
                db.session.commit()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True, 'message': f'Player {first_name} {last_name} added!',
                        'player': {'id': new_player.id, 'first_name': new_player.first_name, 'last_name': new_player.last_name, 'team_code': new_player.team_code, 'jersey_number': new_player.jersey_number, 'full_name': f"{new_player.last_name.upper()}, {new_player.first_name}"}
                    })
                flash(f'Player {first_name} {last_name} added!', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error adding player: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': f'Error adding player: {str(e)}'}), 500
                flash(f'Error adding player: {str(e)}', 'danger')
    
    anchor_to_use = f"game-details-{game_id_anchor}" if game_id_anchor and game_id_anchor != 'None' else "addPlayerForm-global"
    if year_id_redirect and year_id_redirect != 'None':
        return redirect(url_for('year_bp.year_view', year_id=int(year_id_redirect), _anchor=anchor_to_use))
    return redirect(url_for('main_bp.index')) 

@year_bp.route('/<int:year_id>/game/<int:game_id>/add_goal', methods=['POST'])
def add_goal(year_id, game_id):
    game = db.session.get(Game, game_id)
    if not game or game.year_id != year_id:
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

        player_cache = {p.id: p for p in Player.query.all()} 
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
    goal = db.session.get(Goal, goal_id)
    if not goal: 
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Goal not found.'}), 404
        flash('Goal not found.', 'warning')
        return redirect(url_for('year_bp.year_view', year_id=year_id))

    game = db.session.get(Game, goal.game_id)
    if not game or game.year_id != year_id:
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

@year_bp.route('/add_sog_global/<int:game_id>', methods=['POST'])
def add_sog(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden.'}), 404
    data = request.form
    try:
        resolved_t1_code = data.get('sog_team1_code_resolved') 
        resolved_t2_code = data.get('sog_team2_code_resolved')
        teams_processed_count = 0
        made_changes = False

        def process_sog_for_team(team_code, form_prefix):
            nonlocal teams_processed_count, made_changes
            if team_code and not (team_code.startswith(('A', 'B', 'W', 'L', 'Q', 'S')) and len(team_code) > 1 and team_code[1:].isdigit()):
                teams_processed_count += 1
                for period in range(1, 5):
                    shots_str = data.get(f'{form_prefix}_p{period}_shots')
                    if shots_str is None:
                        continue
                    try:
                        shots = int(shots_str.strip()) if shots_str.strip() else 0
                    except ValueError:
                        shots = 0
                    
                    sog_entry = ShotsOnGoal.query.filter_by(game_id=game_id, team_code=team_code, period=period).first()
                    if sog_entry:
                        if sog_entry.shots != shots:
                            sog_entry.shots = shots
                            db.session.add(sog_entry)
                            made_changes = True
                    elif shots != 0:
                        db.session.add(ShotsOnGoal(game_id=game_id, team_code=team_code, period=period, shots=shots))
                        made_changes = True
        
        process_sog_for_team(resolved_t1_code, 'team1')
        process_sog_for_team(resolved_t2_code, 'team2')

        if made_changes: 
            db.session.commit()
            message = 'Shots on Goal successfully saved.'
        elif teams_processed_count > 0 and not made_changes:
            message = 'SOG values were same or all zeros for new; no changes.'
        else:
            message = 'No valid teams for SOG update.'
        
        current_sog_response = {}
        for entry in ShotsOnGoal.query.filter_by(game_id=game_id).all():
            current_sog_response.setdefault(entry.team_code, {})[entry.period] = entry.shots
        for tc_resp in [resolved_t1_code, resolved_t2_code]:
            if tc_resp and not (tc_resp.startswith(('A', 'B', 'W', 'L', 'Q', 'S')) and len(tc_resp) > 1 and tc_resp[1:].isdigit()):
                current_sog_response.setdefault(tc_resp, {}) 
                for p_resp in range(1, 5):
                    current_sog_response[tc_resp].setdefault(p_resp, 0)
        
        consistency_result = check_game_data_consistency(game, current_sog_response)
        scores_match = consistency_result['scores_fully_match_data']
        
        return jsonify({'success': True, 'message': message, 'game_id': game_id, 'sog_data': current_sog_response, 'scores_fully_match_goals': scores_match})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in add_sog: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@year_bp.route('/<int:year_id>/game/<int:game_id>/stats')
def game_stats_view(year_id, game_id):
    year_obj = db.session.get(ChampionshipYear, year_id)
    game_obj_for_stats = db.session.get(Game, game_id) # Renamed to avoid conflict in this scope
    if not year_obj or not game_obj_for_stats or game_obj_for_stats.year_id != year_obj.id:
        flash('Tournament year or game not found.', 'danger'); return redirect(url_for('main_bp.index'))

    # --- START: Simplified Name Resolution Logic ---
    # Instead of duplicating the complex resolution logic from year_view,
    # let's use a simpler approach that leverages the existing year_view logic
    
    # Get all processed games from year_view logic (this ensures consistent resolution)
    games_raw = Game.query.filter_by(year_id=year_id).order_by(Game.date, Game.start_time, Game.game_number).all()
    games_raw_map = {g.id: g for g in games_raw}

    # Build preliminary round standings for playoff resolution
    teams_stats = {}
    prelim_games = [g for g in games_raw if g.round == 'Preliminary Round' and g.group]
    
    unique_teams_in_prelim_groups = set()
    for g in prelim_games:
        if g.team1_code and g.group: 
            unique_teams_in_prelim_groups.add((g.team1_code, g.group))
        if g.team2_code and g.group: 
            unique_teams_in_prelim_groups.add((g.team2_code, g.group))

    for team_code, group_name in unique_teams_in_prelim_groups:
        if team_code not in teams_stats: 
            teams_stats[team_code] = TeamStats(name=team_code, group=group_name)

    for g in [pg for pg in prelim_games if pg.team1_score is not None]: 
        for code, grp, gf, ga, pts, res, is_t1 in [(g.team1_code, g.group, g.team1_score, g.team2_score, g.team1_points, g.result_type, True),
                                                   (g.team2_code, g.group, g.team2_score, g.team1_score, g.team2_points, g.result_type, False)]:
            stats = teams_stats.setdefault(code, TeamStats(name=code, group=grp))
            
            if stats.group == grp: 
                 stats.gp+=1; stats.gf+=gf; stats.ga+=ga; stats.pts+=pts
                 if res=='REG': stats.w+=1 if gf>ga else 0; stats.l+=1 if ga>gf else 0 
                 elif res=='OT': stats.otw+=1 if gf>ga else 0; stats.otl+=1 if ga>gf else 0
                 elif res=='SO': stats.sow+=1 if gf>ga else 0; stats.sol+=1 if ga>gf else 0
    
    standings_by_group = {}
    if teams_stats:
        group_full_names = sorted(list(set(s.group for s in teams_stats.values() if s.group))) 
        for full_group_name_key in group_full_names: 
            current_group_teams = sorted(
                [s for s in teams_stats.values() if s.group == full_group_name_key],
                key=lambda x: (x.pts, x.gd, x.gf),
                reverse=True
            )
            # Apply head-to-head tiebreaker for teams with equal points
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

    games_dict_by_num = {g.game_number: g for g in games_raw}
    
    # Load fixture data for playoff game numbers
    qf_game_numbers = []
    sf_game_numbers = []
    bronze_game_number = None
    gold_game_number = None
    tournament_hosts = []

    fixture_path_exists = False
    if year_obj.fixture_path:
        absolute_fixture_path = resolve_fixture_path(year_obj.fixture_path)
        fixture_path_exists = absolute_fixture_path and os.path.exists(absolute_fixture_path)

    if year_obj.fixture_path and fixture_path_exists:
        try:
            with open(absolute_fixture_path, 'r', encoding='utf-8') as f:
                loaded_fixture_data = json.load(f)
            tournament_hosts = loaded_fixture_data.get("hosts", [])
            
            schedule_data = loaded_fixture_data.get("schedule", [])
            for game_data in schedule_data:
                round_name = game_data.get("round", "").lower()
                game_num = game_data.get("gameNumber")
                
                if "quarterfinal" in round_name: 
                    qf_game_numbers.append(game_num)
                elif "semifinal" in round_name: 
                    sf_game_numbers.append(game_num)
                elif "bronze medal game" in round_name or "bronze" in round_name or "3rd place" in round_name:
                    bronze_game_number = game_num
                elif "gold medal game" in round_name or "final" in round_name or "gold" in round_name:
                    gold_game_number = game_num
            sf_game_numbers.sort()
        except Exception as e: 
            current_app.logger.error(f"Could not parse fixture {year_obj.fixture_path} for playoff game numbers. Error: {e}") 
            if year_obj.year == 2025: 
                qf_game_numbers = [57, 58, 59, 60]
                sf_game_numbers = [61, 62]
                bronze_game_number = 63
                gold_game_number = 64
                tournament_hosts = ["SWE", "DEN"]

    if sf_game_numbers and len(sf_game_numbers) >= 2 and all(isinstance(item, int) for item in sf_game_numbers):
        playoff_team_map['SF1'] = str(sf_game_numbers[0])
        playoff_team_map['SF2'] = str(sf_game_numbers[1])

    # Use the same get_resolved_code function as year_view
    def get_resolved_code(placeholder_code, current_map):
        max_depth = 5 
        current_code = placeholder_code
        for _ in range(max_depth):
            if current_code in current_map:
                next_code = current_map[current_code]
                if next_code == current_code: return current_code 
                current_code = next_code
            elif (current_code.startswith('W(') or current_code.startswith('L(')) and current_code.endswith(')'):
                match = re.search(r'\(([^()]+)\)', current_code) 
                if match:
                    inner_placeholder = match.group(1)
                    if inner_placeholder.isdigit():
                        game_num = int(inner_placeholder)
                        game = games_dict_by_num.get(game_num)
                        if game and game.team1_score is not None:
                            raw_winner = game.team1_code if game.team1_score > game.team2_score else game.team2_code
                            raw_loser = game.team2_code if game.team1_score > game.team2_score else game.team1_code
                            outcome_based_code = raw_winner if current_code.startswith('W(') else raw_loser
                            next_code = current_map.get(outcome_based_code, outcome_based_code)
                            if next_code == current_code: return next_code 
                            current_code = next_code 
                        else: return current_code 
                    else: 
                        resolved_inner = current_map.get(inner_placeholder, inner_placeholder)
                        if resolved_inner == inner_placeholder: return current_code 
                        if resolved_inner.isdigit():
                             current_code = f"{'W' if current_code.startswith('W(') else 'L'}({resolved_inner})"
                        else: 
                             return resolved_inner 
                else: return current_code 
            else: 
                return current_code
        return current_code

    # Create GameDisplay objects and resolve them using the same logic as year_view
    games_processed = [GameDisplay(id=g.id, year_id=g.year_id, date=g.date, start_time=g.start_time, round=g.round, group=g.group, game_number=g.game_number, location=g.location, venue=g.venue, team1_code=g.team1_code, team2_code=g.team2_code, original_team1_code=g.team1_code, original_team2_code=g.team2_code, team1_score=g.team1_score, team2_score=g.team2_score, result_type=g.result_type, team1_points=g.team1_points, team2_points=g.team2_points) for g in games_raw]

    # Resolution passes (same logic as year_view)
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
                    actual_loser  = g_disp.team2_code if g_disp.team1_score > g_disp.team2_score else g_disp.team1_code
                    
                    win_key = f'W({g_disp.game_number})'; lose_key = f'L({g_disp.game_number})'
                    if playoff_team_map.get(win_key) != actual_winner: 
                        playoff_team_map[win_key] = actual_winner; changes_in_pass +=1
                    if playoff_team_map.get(lose_key) != actual_loser: 
                        playoff_team_map[lose_key] = actual_loser; changes_in_pass +=1
        
        if changes_in_pass == 0 and _pass_num > 0: 
            break 

    # --- SEMIFINAL AND FINALS PAIRING LOGIC --- 
    # This block is now OUTSIDE the main processing loop and runs once.

    if qf_game_numbers and sf_game_numbers and len(sf_game_numbers) == 2:
        
        qf_winners_teams = []
        all_qf_winners_resolved = True
        for qf_game_num in qf_game_numbers:
            winner_placeholder = f'W({qf_game_num})'
            resolved_qf_winner = get_resolved_code(winner_placeholder, playoff_team_map)

            if is_code_final(resolved_qf_winner):
                qf_winners_teams.append(resolved_qf_winner)
            else:
                all_qf_winners_resolved = False; break
        
        
        if all_qf_winners_resolved and len(qf_winners_teams) == 4:
            qf_winners_stats = []
            for team_name in qf_winners_teams:
                if team_name in teams_stats: 
                    qf_winners_stats.append(teams_stats[team_name])
                else: 
                    all_qf_winners_resolved = False; break 
            
            if all_qf_winners_resolved and len(qf_winners_stats) == 4:
                qf_winners_stats.sort(key=lambda ts: (ts.rank_in_group, -ts.pts, -ts.gd, -ts.gf))
                R1, R2, R3, R4 = [ts.name for ts in qf_winners_stats] 

                matchup1 = (R1, R4); matchup2 = (R2, R3)
                sf_game1_teams = None; sf_game2_teams = None
                primary_host_plays_sf1 = False

                if tournament_hosts:
                    if tournament_hosts[0] in [R1,R2,R3,R4]: 
                         primary_host_plays_sf1 = True
                         if R1 == tournament_hosts[0] or R4 == tournament_hosts[0]: sf_game1_teams = matchup1; sf_game2_teams = matchup2
                         else: sf_game1_teams = matchup2; sf_game2_teams = matchup1
                    elif len(tournament_hosts) > 1 and tournament_hosts[1] in [R1,R2,R3,R4]: 
                         primary_host_plays_sf1 = True 
                         if R1 == tournament_hosts[1] or R4 == tournament_hosts[1]: sf_game1_teams = matchup1; sf_game2_teams = matchup2
                         else: sf_game1_teams = matchup2; sf_game2_teams = matchup1
                
                if not primary_host_plays_sf1: 
                    sf_game1_teams = matchup1; sf_game2_teams = matchup2


                sf_game_obj_1 = games_dict_by_num.get(sf_game_numbers[0])
                sf_game_obj_2 = games_dict_by_num.get(sf_game_numbers[1])

                if sf_game_obj_1 and sf_game_obj_2 and sf_game1_teams and sf_game2_teams:
                    # Note: changes_in_pass is no longer relevant here as we are outside that loop.
                    # We directly update playoff_team_map.
                    if playoff_team_map.get(sf_game_obj_1.team1_code) != sf_game1_teams[0]:
                        playoff_team_map[sf_game_obj_1.team1_code] = sf_game1_teams[0]
                    if playoff_team_map.get(sf_game_obj_1.team2_code) != sf_game1_teams[1]:
                        playoff_team_map[sf_game_obj_1.team2_code] = sf_game1_teams[1]
                    if playoff_team_map.get(sf_game_obj_2.team1_code) != sf_game2_teams[0]:
                        playoff_team_map[sf_game_obj_2.team1_code] = sf_game2_teams[0]
                    if playoff_team_map.get(sf_game_obj_2.team2_code) != sf_game2_teams[1]:
                        playoff_team_map[sf_game_obj_2.team2_code] = sf_game2_teams[1]
                    
                    # Add Q1-Q4 mappings based on the semifinal assignments
                    # Q1 and Q2 are the teams in the first semifinal game
                    # Q3 and Q4 are the teams in the second semifinal game
                    playoff_team_map['Q1'] = sf_game1_teams[0]  # First team in SF1
                    playoff_team_map['Q2'] = sf_game1_teams[1]  # Second team in SF1
                    playoff_team_map['Q3'] = sf_game2_teams[0]  # First team in SF2
                    playoff_team_map['Q4'] = sf_game2_teams[1]  # Second team in SF2
                    
                else:
                    pass  # Empty else block
            else:
                pass  # Empty else block
        else:
            pass  # Empty else block
    else:
        pass  # Empty else block

    # --- FALLBACK Q1-Q4 MAPPING ---
    # If the full semifinal logic didn't run, try to map Q1-Q4 to available QF winners
    if qf_game_numbers and len(qf_game_numbers) == 4 and 'Q1' not in playoff_team_map:
        for i, qf_game_num in enumerate(qf_game_numbers):
            winner_placeholder = f'W({qf_game_num})'
            resolved_qf_winner = get_resolved_code(winner_placeholder, playoff_team_map)
            
            
            if is_code_final(resolved_qf_winner):
                q_code = f'Q{i+1}'  # Q1, Q2, Q3, Q4
                playoff_team_map[q_code] = resolved_qf_winner
            else:
                pass  # Empty else block
    else:
        pass  # Empty else block

    # --- BRONZE AND GOLD MEDAL GAME LOGIC ---
    # Handle Bronze Medal Game (losers of semifinals) and Gold Medal Game (winners of semifinals)
    if sf_game_numbers and len(sf_game_numbers) == 2 and bronze_game_number and gold_game_number:
        bronze_game_obj = games_dict_by_num.get(bronze_game_number)
        gold_game_obj = games_dict_by_num.get(gold_game_number)
        
        if bronze_game_obj and gold_game_obj:
            # Map SF1 and SF2 to actual game numbers
            sf1_game_number = sf_game_numbers[0]  # First semifinal game
            sf2_game_number = sf_game_numbers[1]  # Second semifinal game
            
            # Add mappings for SF1 and SF2 placeholders
            playoff_team_map['SF1'] = str(sf1_game_number)
            playoff_team_map['SF2'] = str(sf2_game_number)
            
            # Bronze Medal Game: L(SF1) vs L(SF2) -> L(61) vs L(62)
            sf1_loser_placeholder = f'L({sf1_game_number})'
            sf2_loser_placeholder = f'L({sf2_game_number})'
            
            # Gold Medal Game: W(SF1) vs W(SF2) -> W(61) vs W(62)
            sf1_winner_placeholder = f'W({sf1_game_number})'
            sf2_winner_placeholder = f'W({sf2_game_number})'
            
            # Update Bronze Medal Game teams (map L(SF1) -> L(61), L(SF2) -> L(62))
            if playoff_team_map.get(bronze_game_obj.team1_code) != sf1_loser_placeholder:
                playoff_team_map[bronze_game_obj.team1_code] = sf1_loser_placeholder
            if playoff_team_map.get(bronze_game_obj.team2_code) != sf2_loser_placeholder:
                playoff_team_map[bronze_game_obj.team2_code] = sf2_loser_placeholder
                
            # Update Gold Medal Game teams (map W(SF1) -> W(61), W(SF2) -> W(62))
            if playoff_team_map.get(gold_game_obj.team1_code) != sf1_winner_placeholder:
                playoff_team_map[gold_game_obj.team1_code] = sf1_winner_placeholder
            if playoff_team_map.get(gold_game_obj.team2_code) != sf2_winner_placeholder:
                playoff_team_map[gold_game_obj.team2_code] = sf2_winner_placeholder
        else:
            pass  # Empty else block
    else:
        pass  # Empty else block

    # Perform a final resolution pass using the updated playoff_team_map
    for g_disp_final_pass in games_processed:
        # Resolve from original placeholder if current is still a placeholder, 
        # or re-resolve current if it might have been an intermediate placeholder.
        # Prioritizing original_teamX_code ensures we pick up changes from playoff_team_map like Q1->CAN directly.
        code_to_resolve_t1 = g_disp_final_pass.original_team1_code 
        resolved_t1_final = get_resolved_code(code_to_resolve_t1, playoff_team_map)
        if g_disp_final_pass.team1_code != resolved_t1_final:
            g_disp_final_pass.team1_code = resolved_t1_final

        code_to_resolve_t2 = g_disp_final_pass.original_team2_code
        resolved_t2_final = get_resolved_code(code_to_resolve_t2, playoff_team_map)
        if g_disp_final_pass.team2_code != resolved_t2_final:
            g_disp_final_pass.team2_code = resolved_t2_final

    # Find the specific game and get its resolved team names
    games_processed_map = {g.id: g for g in games_processed}
    resolved_game = games_processed_map.get(game_id)
    
    if resolved_game:
        resolved_team1_name = resolved_game.team1_code
        resolved_team2_name = resolved_game.team2_code
    else:
        # Fallback: resolve directly from the game object
        resolved_team1_name = get_resolved_code(game_obj_for_stats.team1_code, playoff_team_map)
        resolved_team2_name = get_resolved_code(game_obj_for_stats.team2_code, playoff_team_map)

    # Set the resolved names on the game object for the template
    game_obj_for_stats.team1_display_name = resolved_team1_name
    game_obj_for_stats.team2_display_name = resolved_team2_name
    # --- END: Simplified Name Resolution Logic ---

    # --- START: Statistics Calculation using RESOLVED names ---
    sog_entries = ShotsOnGoal.query.filter_by(game_id=game_id).all()
    # Initialize with resolved names
    sog_data_processed = {resolved_team1_name: {1:0, 2:0, 3:0, 4:0}, resolved_team2_name: {1:0, 2:0, 3:0, 4:0}}
    sog_totals = {resolved_team1_name: 0, resolved_team2_name: 0}
    
    # SOG entries are keyed by RESOLVED team_code from DB.
    for sog in sog_entries:
        # sog.team_code is the resolved name of the team for which SOG was recorded.
        # We need to check if this team is one of the two teams playing in the current game.
        if sog.team_code == resolved_team1_name:
            sog_data_processed[resolved_team1_name][sog.period] = sog_data_processed[resolved_team1_name].get(sog.period, 0) + sog.shots
            sog_totals[resolved_team1_name] += sog.shots
        elif sog.team_code == resolved_team2_name:
            sog_data_processed[resolved_team2_name][sog.period] = sog_data_processed[resolved_team2_name].get(sog.period, 0) + sog.shots
            sog_totals[resolved_team2_name] += sog.shots

    # Ensure all periods exist for both resolved teams in sog_data_processed
    for team_resolved_key in [resolved_team1_name, resolved_team2_name]:
        sog_data_processed.setdefault(team_resolved_key, {1:0, 2:0, 3:0, 4:0}) # Ensure team key exists
        for p_key in range(1, 5): 
            sog_data_processed[team_resolved_key].setdefault(p_key, 0)
        sog_totals.setdefault(team_resolved_key, 0)


    penalties_raw = Penalty.query.filter_by(game_id=game_id).all()
    pim_totals = {resolved_team1_name: 0, resolved_team2_name: 0}
    # Penalties are keyed by RESOLVED team_code from DB.
    for p in penalties_raw:
        # p.team_code is the resolved name of the penalized team.
        if p.team_code == resolved_team1_name:
            pim_totals[resolved_team1_name] += PIM_MAP.get(p.penalty_type, 0)
        elif p.team_code == resolved_team2_name:
            pim_totals[resolved_team2_name] += PIM_MAP.get(p.penalty_type, 0)
    pim_totals.setdefault(resolved_team1_name, 0); pim_totals.setdefault(resolved_team2_name, 0)


    potential_pp_slots = []
    for p in penalties_raw: # p.team_code is resolved name of penalized team
        if p.penalty_type in POWERPLAY_PENALTY_TYPES:
            # Each penalty gives exactly one powerplay opportunity, regardless of duration
            beneficiary_resolved_name = None
            if p.team_code == resolved_team1_name: # If team1 was penalized
                beneficiary_resolved_name = resolved_team2_name # Team2 gets PP
            elif p.team_code == resolved_team2_name: # If team2 was penalized
                beneficiary_resolved_name = resolved_team1_name # Team1 gets PP
            
            if beneficiary_resolved_name:
                potential_pp_slots.append({'time': p.minute_of_game, 'beneficiary': beneficiary_resolved_name})
    
    grouped_slots_by_time = {}
    for slot in potential_pp_slots: grouped_slots_by_time.setdefault(slot['time'], []).append(slot)
    
    final_pp_opportunities = {resolved_team1_name: 0, resolved_team2_name: 0}
    for time, slots_at_time in grouped_slots_by_time.items():
        opps_t1_res = sum(1 for s in slots_at_time if s['beneficiary'] == resolved_team1_name)
        opps_t2_res = sum(1 for s in slots_at_time if s['beneficiary'] == resolved_team2_name)
        cancelled_res = min(opps_t1_res, opps_t2_res)
        final_pp_opportunities[resolved_team1_name] += (opps_t1_res - cancelled_res)
        final_pp_opportunities[resolved_team2_name] += (opps_t2_res - cancelled_res)
    final_pp_opportunities.setdefault(resolved_team1_name,0); final_pp_opportunities.setdefault(resolved_team2_name,0)

    goals_raw = Goal.query.filter_by(game_id=game_id).all()
    player_cache_stats = {p.id: p for p in Player.query.all()} # Assuming Player.team_code is the resolved/final one
    
    pp_goals_scored = {resolved_team1_name: 0, resolved_team2_name: 0}
    team1_scores_by_period = {1:0, 2:0, 3:0, 4:0}; team2_scores_by_period = {1:0, 2:0, 3:0, 4:0}

    for goal in goals_raw: # goal.team_code is the resolved name of the scoring team
        time_sec = convert_time_to_seconds(goal.minute)
        period = 4 
        if time_sec <= 1200: period = 1
        elif time_sec <= 2400: period = 2
        elif time_sec <= 3600: period = 3

        scoring_team_resolved_name = goal.team_code # Directly use the resolved name from DB

        if scoring_team_resolved_name == resolved_team1_name:
            team1_scores_by_period[period] += 1
            if goal.goal_type == "PP":
                 pp_goals_scored[resolved_team1_name] += 1
        elif scoring_team_resolved_name == resolved_team2_name:
            team2_scores_by_period[period] += 1
            if goal.goal_type == "PP":
                 pp_goals_scored[resolved_team2_name] += 1
        
    pp_goals_scored.setdefault(resolved_team1_name,0); pp_goals_scored.setdefault(resolved_team2_name,0)


    def get_pname_for_stats(pid): p = player_cache_stats.get(pid); return f"{p.first_name} {p.last_name}" if p else "N/A"

    game_events_for_stats = []
    for goal in goals_raw: # goal.team_code is the resolved name of the scoring team
        time_sec = convert_time_to_seconds(goal.minute)
        period_disp = "OT"; 
        if time_sec <= 1200: period_disp = "1st Period"
        elif time_sec <= 2400: period_disp = "2nd Period"
        elif time_sec <= 3600: period_disp = "3rd Period"
        
        event_team_display_name = goal.team_code # Use resolved name from DB directly

        game_events_for_stats.append({
            'type': 'goal', 'time_str': goal.minute, 'time_for_sort': time_sec,
            'period_display': period_disp, 
            'team_code': event_team_display_name, 
            'team_iso': TEAM_ISO_CODES.get(event_team_display_name.upper() if event_team_display_name else ""),
            'goal_type_display': GOAL_TYPE_DISPLAY_MAP.get(goal.goal_type, goal.goal_type),
            'is_empty_net': goal.is_empty_net, 'scorer': get_pname_for_stats(goal.scorer_id),
            'assist1': get_pname_for_stats(goal.assist1_id) if goal.assist1_id else None,
            'assist2': get_pname_for_stats(goal.assist2_id) if goal.assist2_id else None,
            'scorer_obj': player_cache_stats.get(goal.scorer_id),
            'assist1_obj': player_cache_stats.get(goal.assist1_id) if goal.assist1_id else None,
            'assist2_obj': player_cache_stats.get(goal.assist2_id) if goal.assist2_id else None,
        })
    game_events_for_stats.sort(key=lambda x: x['time_for_sort'])

    pp_percentage = {resolved_team1_name: 0.0, resolved_team2_name: 0.0}
    for tc_res in [resolved_team1_name, resolved_team2_name]:
        if tc_res in final_pp_opportunities and final_pp_opportunities[tc_res] > 0 and tc_res in pp_goals_scored:
            pp_percentage[tc_res] = round((pp_goals_scored[tc_res] / final_pp_opportunities[tc_res]) * 100, 1)
        else: # Ensure key exists even if no opportunities or goals
             pp_percentage.setdefault(tc_res, 0.0)
    # --- END: Statistics Calculation ---
    
    return render_template('game_stats.html',
                           year=year_obj, game=game_obj_for_stats, # game_obj_for_stats now has team1/2_display_name
                           team_iso_codes=TEAM_ISO_CODES,
                           sog_data_for_stats_page=sog_data_processed, sog_totals=sog_totals,
                           pim_totals=pim_totals, game_events=game_events_for_stats,
                           pp_goals_scored=pp_goals_scored, pp_opportunities=final_pp_opportunities,
                           pp_percentage=pp_percentage, team1_scores_by_period=team1_scores_by_period,
                           team2_scores_by_period=team2_scores_by_period) 

@year_bp.route('/<int:year_id>/game/<int:game_id>/overrule', methods=['POST'])
def add_overrule(year_id, game_id):
    """Add or update an overrule for a game's score matching issue"""
    game = db.session.get(Game, game_id)
    if not game or game.year_id != year_id:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404
    
    try:
        reason = request.form.get('reason', '').strip()
        if not reason:
            return jsonify({'success': False, 'message': 'Grund für Overrule muss angegeben werden.'}), 400
        
        # Check if overrule already exists
        existing_overrule = GameOverrule.query.filter_by(game_id=game_id).first()
        
        if existing_overrule:
            # Update existing overrule
            existing_overrule.reason = reason
            existing_overrule.created_at = db.func.current_timestamp()
            message = 'Overrule-Grund erfolgreich aktualisiert!'
        else:
            # Create new overrule
            new_overrule = GameOverrule(game_id=game_id, reason=reason)
            db.session.add(new_overrule)
            message = 'Overrule erfolgreich hinzugefügt!'
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': message,
            'overrule': {
                'reason': reason,
                'created_at': existing_overrule.created_at.isoformat() if existing_overrule else None
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding/updating overrule: {str(e)}")
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500

@year_bp.route('/<int:year_id>/game/<int:game_id>/overrule', methods=['DELETE'])
def remove_overrule(year_id, game_id):
    """Remove an overrule for a game"""
    game = db.session.get(Game, game_id)
    if not game or game.year_id != year_id:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404
    
    try:
        existing_overrule = GameOverrule.query.filter_by(game_id=game_id).first()
        
        if not existing_overrule:
            return jsonify({'success': False, 'message': 'Kein Overrule für dieses Spiel gefunden.'}), 404
        
        db.session.delete(existing_overrule)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Overrule erfolgreich entfernt!'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error removing overrule: {str(e)}")
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500

@year_bp.route('/<int:year_id>/team_vs_team/<team1>/<team2>')
def team_vs_team_view(year_id, team1, team2):
    year_obj = db.session.get(ChampionshipYear, year_id)
    if not year_obj:
        flash('Turnierjahr nicht gefunden.', 'danger')
        return redirect(url_for('main_bp.index'))

    # Team-Namen normalisieren für bessere Matcherkennung
    t1, t2 = team1.strip().upper(), team2.strip().upper()

    # Alle Spiele aus der gesamten Datenbank laden (alle Jahre) und nach Jahren gruppieren
    all_games = Game.query.order_by(Game.year_id, Game.date, Game.start_time, Game.game_number).all()
    games_by_year = {}
    years_processed = set()
    for game in all_games:
        if game.year_id not in games_by_year:
            games_by_year[game.year_id] = []
        games_by_year[game.year_id].append(game)
        years_processed.add(game.year_id)

    # Alle Jahre für die Platzhalter-Auflösung verarbeiten
    all_resolved_games = []
    
    for year_id_iter in years_processed:
        games_raw = games_by_year[year_id_iter]
        year_obj_iter = db.session.get(ChampionshipYear, year_id_iter)
        if not year_obj_iter:
            continue
            
        # --- TEAM RESOLUTION LOGIC (adapted from game_stats_view) ---
        # Build preliminary round standings for playoff resolution
        teams_stats = {}
        prelim_games = [g for g in games_raw if g.round == 'Preliminary Round' and g.group]
        
        unique_teams_in_prelim_groups = set()
        for g in prelim_games:
            if g.team1_code and g.group: 
                unique_teams_in_prelim_groups.add((g.team1_code, g.group))
            if g.team2_code and g.group: 
                unique_teams_in_prelim_groups.add((g.team2_code, g.group))

        for team_code, group_name in unique_teams_in_prelim_groups:
            if team_code not in teams_stats: 
                teams_stats[team_code] = TeamStats(name=team_code, group=group_name)

        for g in [pg for pg in prelim_games if pg.team1_score is not None]: 
            for code, grp, gf, ga, pts, res, is_t1 in [(g.team1_code, g.group, g.team1_score, g.team2_score, g.team1_points, g.result_type, True),
                                                       (g.team2_code, g.group, g.team2_score, g.team1_score, g.team2_points, g.result_type, False)]:
                stats = teams_stats.setdefault(code, TeamStats(name=code, group=grp))
                
                if stats.group == grp: 
                     stats.gp+=1; stats.gf+=gf; stats.ga+=ga; stats.pts+=pts
                     if res=='REG': stats.w+=1 if gf>ga else 0; stats.l+=1 if ga>gf else 0 
                     elif res=='OT': stats.otw+=1 if gf>ga else 0; stats.otl+=1 if ga>gf else 0
                     elif res=='SO': stats.sow+=1 if gf>ga else 0; stats.sol+=1 if ga>gf else 0
        
        standings_by_group = {}
        if teams_stats:
            group_full_names = sorted(list(set(s.group for s in teams_stats.values() if s.group))) 
            for full_group_name_key in group_full_names: 
                current_group_teams = sorted(
                    [s for s in teams_stats.values() if s.group == full_group_name_key],
                    key=lambda x: (x.pts, x.gd, x.gf),
                    reverse=True
                )
                # Apply head-to-head tiebreaker for teams with equal points
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

        games_dict_by_num = {g.game_number: g for g in games_raw}
        
        # Load fixture data for playoff game numbers
        qf_game_numbers = []
        sf_game_numbers = []
        bronze_game_number = None
        gold_game_number = None
        tournament_hosts = []

        fixture_path_exists = False
        if year_obj_iter.fixture_path:
            absolute_fixture_path = resolve_fixture_path(year_obj_iter.fixture_path)
            fixture_path_exists = absolute_fixture_path and os.path.exists(absolute_fixture_path)

        if year_obj_iter.fixture_path and fixture_path_exists:
            try:
                with open(absolute_fixture_path, 'r', encoding='utf-8') as f:
                    loaded_fixture_data = json.load(f)
                tournament_hosts = loaded_fixture_data.get("hosts", [])
                
                schedule_data = loaded_fixture_data.get("schedule", [])
                for i, game_data in enumerate(schedule_data):
                    round_name = game_data.get("round", "").lower()
                    game_num = game_data.get("gameNumber")
                    
                    if "quarterfinal" in round_name: 
                        qf_game_numbers.append(game_num)
                    elif "semifinal" in round_name: 
                        sf_game_numbers.append(game_num)
                    elif "bronze medal game" in round_name or "bronze" in round_name or "3rd place" in round_name:
                        bronze_game_number = game_num
                    elif "gold medal game" in round_name or "final" in round_name or "gold" in round_name:
                        gold_game_number = game_num
                sf_game_numbers.sort()
            except Exception as e: 
                current_app.logger.error(f"Could not parse fixture {year_obj_iter.fixture_path} for playoff game numbers. Error: {e}") 
                if year_obj_iter.year == 2025: 
                    qf_game_numbers = [57, 58, 59, 60]
                    sf_game_numbers = [61, 62]
                    bronze_game_number = 63
                    gold_game_number = 64
                    tournament_hosts = ["SWE", "DEN"]

        if sf_game_numbers and len(sf_game_numbers) >= 2 and all(isinstance(item, int) for item in sf_game_numbers):
            playoff_team_map['SF1'] = str(sf_game_numbers[0])
            playoff_team_map['SF2'] = str(sf_game_numbers[1])

        # Use the same get_resolved_code function as year_view
        def get_resolved_code(placeholder_code, current_map):
            max_depth = 5 
            current_code = placeholder_code
            for _ in range(max_depth):
                if current_code in current_map:
                    next_code = current_map[current_code]
                    if next_code == current_code: return current_code 
                    current_code = next_code
                elif (current_code.startswith('W(') or current_code.startswith('L(')) and current_code.endswith(')'):
                    match = re.search(r'\(([^()]+)\)', current_code) 
                    if match:
                        inner_placeholder = match.group(1)
                        if inner_placeholder.isdigit():
                            game_num = int(inner_placeholder)
                            game = games_dict_by_num.get(game_num)
                            if game and game.team1_score is not None:
                                raw_winner = game.team1_code if game.team1_score > game.team2_score else game.team2_code
                                raw_loser = game.team2_code if game.team1_score > game.team2_score else game.team1_code
                                outcome_based_code = raw_winner if current_code.startswith('W(') else raw_loser
                                next_code = current_map.get(outcome_based_code, outcome_based_code)
                                if next_code == current_code: return next_code 
                                current_code = next_code 
                            else: return current_code 
                        else: 
                            resolved_inner = current_map.get(inner_placeholder, inner_placeholder)
                            if resolved_inner == inner_placeholder: return current_code 
                            if resolved_inner.isdigit():
                                 current_code = f"{'W' if current_code.startswith('W(') else 'L'}({resolved_inner})"
                            else: 
                                 return resolved_inner 
                    else: return current_code 
                else: 
                    return current_code
            return current_code

        # Create GameDisplay objects and resolve them using the same logic as year_view
        games_processed = [GameDisplay(id=g.id, year_id=g.year_id, date=g.date, start_time=g.start_time, round=g.round, group=g.group, game_number=g.game_number, location=g.location, venue=g.venue, team1_code=g.team1_code, team2_code=g.team2_code, original_team1_code=g.team1_code, original_team2_code=g.team2_code, team1_score=g.team1_score, team2_score=g.team2_score, result_type=g.result_type, team1_points=g.team1_points, team2_points=g.team2_points) for g in games_raw]

        # Resolution passes (same logic as year_view)
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
                        actual_loser  = g_disp.team2_code if g_disp.team1_score > g_disp.team2_score else g_disp.team1_code
                        
                        win_key = f'W({g_disp.game_number})'; lose_key = f'L({g_disp.game_number})'
                        if playoff_team_map.get(win_key) != actual_winner: 
                            playoff_team_map[win_key] = actual_winner; changes_in_pass +=1
                        if playoff_team_map.get(lose_key) != actual_loser: 
                            playoff_team_map[lose_key] = actual_loser; changes_in_pass +=1
            
            if changes_in_pass == 0 and _pass_num > 0: 
                break

        # --- SEMIFINAL AND FINALS PAIRING LOGIC (simplified for team_vs_team) ---
        if qf_game_numbers and sf_game_numbers and len(sf_game_numbers) == 2:
            qf_winners_teams = []
            all_qf_winners_resolved = True
            for qf_game_num in qf_game_numbers:
                winner_placeholder = f'W({qf_game_num})'
                resolved_qf_winner = get_resolved_code(winner_placeholder, playoff_team_map)

                if is_code_final(resolved_qf_winner):
                    qf_winners_teams.append(resolved_qf_winner)
                else:
                    all_qf_winners_resolved = False; break
            
            if all_qf_winners_resolved and len(qf_winners_teams) == 4:
                qf_winners_stats = []
                for team_name in qf_winners_teams:
                    if team_name in teams_stats: 
                        qf_winners_stats.append(teams_stats[team_name])
                    else: 
                        all_qf_winners_resolved = False; break
                
                if all_qf_winners_resolved:
                    qf_winners_stats.sort(key=lambda s: (s.rank_in_group, -s.pts, -s.gd, -s.gf))
                    if len(qf_winners_stats) >= 4:
                        playoff_team_map['Q1'] = qf_winners_stats[0].name
                        playoff_team_map['Q2'] = qf_winners_stats[3].name
                        playoff_team_map['Q3'] = qf_winners_stats[1].name
                        playoff_team_map['Q4'] = qf_winners_stats[2].name

        # --- FALLBACK Q1-Q4 MAPPING ---
        if qf_game_numbers and len(qf_game_numbers) == 4 and 'Q1' not in playoff_team_map:
            for i, qf_game_num in enumerate(qf_game_numbers):
                winner_placeholder = f'W({qf_game_num})'
                resolved_qf_winner = get_resolved_code(winner_placeholder, playoff_team_map)
                
                if is_code_final(resolved_qf_winner):
                    q_code = f'Q{i+1}'  # Q1, Q2, Q3, Q4
                    playoff_team_map[q_code] = resolved_qf_winner

        # Perform a final resolution pass using the updated playoff_team_map
        for g_disp_final_pass in games_processed:
            code_to_resolve_t1 = g_disp_final_pass.original_team1_code 
            resolved_t1_final = get_resolved_code(code_to_resolve_t1, playoff_team_map)
            if g_disp_final_pass.team1_code != resolved_t1_final:
                g_disp_final_pass.team1_code = resolved_t1_final

            code_to_resolve_t2 = g_disp_final_pass.original_team2_code
            resolved_t2_final = get_resolved_code(code_to_resolve_t2, playoff_team_map)
            if g_disp_final_pass.team2_code != resolved_t2_final:
                g_disp_final_pass.team2_code = resolved_t2_final

        # Add resolved games to the collection
        all_resolved_games.extend(games_processed)
    
    # --- END TEAM RESOLUTION LOGIC ---
    
    # Jetzt alle direkten Duelle zwischen den beiden Teams finden (mit aufgelösten Teamnamen)
    direct_duels = []
    for g in all_resolved_games:
        if not g.team1_code or not g.team2_code:
            continue
        # Alle Kombinationen prüfen (A vs B und B vs A)
        if (g.team1_code.upper() == t1 and g.team2_code.upper() == t2) or \
           (g.team1_code.upper() == t2 and g.team2_code.upper() == t1):
            direct_duels.append(g)

    # Statistiken initialisieren
    stats = {
        t1: {'tore': 0, 'pim': 0, 'sog': 0, 'siege': 0, 'spiele': 0, 'ot_siege': 0, 'so_siege': 0, 'niederlagen': 0, 'ot_niederlagen': 0, 'so_niederlagen': 0, 'pp_goals': 0, 'pp_opportunities': 0},
        t2: {'tore': 0, 'pim': 0, 'sog': 0, 'siege': 0, 'spiele': 0, 'ot_siege': 0, 'so_siege': 0, 'niederlagen': 0, 'ot_niederlagen': 0, 'so_niederlagen': 0, 'pp_goals': 0, 'pp_opportunities': 0}
    }

    duel_details = []

    for g in direct_duels:
        # Team-Scores bestimmen (je nach Paarung)
        if g.team1_code.upper() == t1:
            t1_score, t2_score = g.team1_score, g.team2_score
        else:  # g.team1_code.upper() == t2
            t1_score, t2_score = g.team2_score, g.team1_score

        # Strafminuten sammeln
        penalty_entries = Penalty.query.filter_by(game_id=g.id).all()
        penalties_t1 = sum(PIM_MAP.get(p.penalty_type, 0) for p in penalty_entries if p.team_code.upper() == t1)
        penalties_t2 = sum(PIM_MAP.get(p.penalty_type, 0) for p in penalty_entries if p.team_code.upper() == t2)
        stats[t1]['pim'] += penalties_t1
        stats[t2]['pim'] += penalties_t2

        # Powerplay-Gelegenheiten zählen (basierend auf Strafen des Gegners)
        # Jede Strafe des Gegners ist eine Powerplay-Gelegenheit für das Team
        for penalty in penalty_entries:
            if penalty.team_code.upper() == t1:
                # t1 bekommt Strafe -> t2 bekommt Powerplay-Gelegenheit
                stats[t2]['pp_opportunities'] += 1
            elif penalty.team_code.upper() == t2:
                # t2 bekommt Strafe -> t1 bekommt Powerplay-Gelegenheit
                stats[t1]['pp_opportunities'] += 1

        # Powerplay-Tore sammeln
        goal_entries = Goal.query.filter_by(game_id=g.id).all()
        for goal in goal_entries:
            if goal.goal_type == 'PP':  # Powerplay-Tor
                if goal.team_code.upper() == t1:
                    stats[t1]['pp_goals'] += 1
                elif goal.team_code.upper() == t2:
                    stats[t2]['pp_goals'] += 1

        # Schüsse sammeln
        sog_entries = ShotsOnGoal.query.filter_by(game_id=g.id).all()
        for sog in sog_entries:
            if sog.team_code.upper() == t1:
                stats[t1]['sog'] += sog.shots
            elif sog.team_code.upper() == t2:
                stats[t2]['sog'] += sog.shots

        if t1_score is not None and t2_score is not None:
            stats[t1]['tore'] += t1_score
            stats[t2]['tore'] += t2_score
            stats[t1]['spiele'] += 1
            stats[t2]['spiele'] += 1
            # Siege und Niederlagen zählen nach Typ
            if t1_score > t2_score:
                # t1 gewinnt
                if g.result_type == 'REG':
                    stats[t1]['siege'] += 1
                    stats[t2]['niederlagen'] += 1
                elif g.result_type == 'OT':
                    stats[t1]['ot_siege'] += 1
                    stats[t2]['ot_niederlagen'] += 1
                elif g.result_type == 'SO':
                    stats[t1]['so_siege'] += 1
                    stats[t2]['so_niederlagen'] += 1
            elif t2_score > t1_score:
                # t2 gewinnt
                if g.result_type == 'REG':
                    stats[t2]['siege'] += 1
                    stats[t1]['niederlagen'] += 1
                elif g.result_type == 'OT':
                    stats[t2]['ot_siege'] += 1
                    stats[t1]['ot_niederlagen'] += 1
                elif g.result_type == 'SO':
                    stats[t2]['so_siege'] += 1
                    stats[t1]['so_niederlagen'] += 1

        # Für die Tabelle
        # Runden-Namen für bessere Anzeige
        round_display = g.round
        if round_display == 'Preliminary Round':
            round_display = 'Hauptrunde'
        elif 'Quarter' in round_display:
            round_display = 'Viertelfinale'
        elif 'Semi' in round_display:
            round_display = 'Halbfinale'
        elif 'Bronze' in round_display:
            round_display = 'Spiel um Platz 3'
        elif 'Gold' in round_display or 'Final' in round_display:
            round_display = 'Finale'
        
        # Ergebnis-Typ für bessere Anzeige
        result_display = ''
        if g.result_type == 'REG':
            result_display = 'Regulär'
        elif g.result_type == 'OT':
            result_display = 'n.V.'
        elif g.result_type == 'SO':
            result_display = 'n.P.'
        
        # Jahr des Spiels bestimmen
        year_display = '-'
        if g.year_id:
            year_obj_of_game = db.session.get(ChampionshipYear, g.year_id)
            if year_obj_of_game:
                year_display = str(year_obj_of_game.year)
        
        duel_details.append({
            'game': g,
            't1_score': t1_score,
            't2_score': t2_score,
            'date': g.date,
            'round_display': round_display,
            'location': g.location,
            'result_display': result_display,
            'year_display': year_display
        })

    # Durchschnittswerte pro Spiel berechnen
    for team in [t1, t2]:
        spiele = stats[team]['spiele'] if stats[team]['spiele'] > 0 else 1
        stats[team]['tore_avg'] = round(stats[team]['tore'] / spiele, 2)
        stats[team]['pim_avg'] = round(stats[team]['pim'] / spiele, 2)
        stats[team]['sog_avg'] = round(stats[team]['sog'] / spiele, 2)
        # Gesamtsiege berechnen (REG + OT + SO)
        stats[team]['siege_gesamt'] = stats[team]['siege'] + stats[team]['ot_siege'] + stats[team]['so_siege']
        stats[team]['niederlagen_gesamt'] = stats[team]['niederlagen'] + stats[team]['ot_niederlagen'] + stats[team]['so_niederlagen']
        stats[team]['siege_avg'] = round(stats[team]['siege_gesamt'] / spiele, 2)

    # Sortiere Duelle nach Datum (neueste zuerst)
    duel_details.sort(key=lambda x: (x['year_display'], x['date'] or ''), reverse=True)

    return render_template('team_vs_team.html',
                           year=year_obj,
                           team1=t1,
                           team2=t2,
                           stats=stats,
                           duel_details=duel_details,
                           team_iso_codes=TEAM_ISO_CODES)