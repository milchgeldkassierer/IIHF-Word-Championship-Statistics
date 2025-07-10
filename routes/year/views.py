import json
import os
import re
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from models import db, ChampionshipYear, Game, Player, Goal, Penalty, ShotsOnGoal, TeamStats, TeamOverallStats, GameDisplay, GameOverrule
from constants import TEAM_ISO_CODES, PENALTY_TYPES_CHOICES, PENALTY_REASONS_CHOICES, PIM_MAP, POWERPLAY_PENALTY_TYPES
from utils import convert_time_to_seconds, check_game_data_consistency, is_code_final, _apply_head_to_head_tiebreaker
from routes.main_routes import resolve_fixture_path
from routes.record_routes import get_all_resolved_games

# Import the blueprint from the parent package
from . import year_bp
from .seeding import get_custom_seeding_from_db

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
                
                # Check for custom seeding
                custom_seeding = get_custom_seeding_from_db(year_id)
                
                if custom_seeding:
                    # Use custom seeding mapping
                    R1 = custom_seeding.get('seed1')
                    R2 = custom_seeding.get('seed2') 
                    R3 = custom_seeding.get('seed3')
                    R4 = custom_seeding.get('seed4')
                    
                    # Validate custom seeding teams are in QF winners
                    custom_teams = [R1, R2, R3, R4]
                    qf_team_names = [ts.name for ts in qf_winners_stats]
                    
                    if all(team in qf_team_names for team in custom_teams):
                        # Custom seeding is valid
                        pass
                    else:
                        # Custom seeding invalid, fall back to standard
                        R1, R2, R3, R4 = [ts.name for ts in qf_winners_stats]
                else:
                    # Standard IIHF seeding
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
                    
                    # Check for custom seeding first
                    custom_seeding = get_custom_seeding_from_db(year_id)
                    
                    if custom_seeding:
                        # Use custom seeding - map Q1-Q4 to custom seed order
                        playoff_team_map['Q1'] = custom_seeding['seed1']
                        playoff_team_map['Q2'] = custom_seeding['seed2']
                        playoff_team_map['Q3'] = custom_seeding['seed3']
                        playoff_team_map['Q4'] = custom_seeding['seed4']
                        
                        # Update semifinal game assignments based on custom seeding
                        # Semifinal 1: seed1 vs seed4, Semifinal 2: seed2 vs seed3
                        sf_game1_teams = [custom_seeding['seed1'], custom_seeding['seed4']]
                        sf_game2_teams = [custom_seeding['seed2'], custom_seeding['seed3']]
                        
                        # Update the actual game team assignments in the playoff_team_map
                        if sf_game_obj_1:
                            playoff_team_map[sf_game_obj_1.team1_code] = custom_seeding['seed1']
                            playoff_team_map[sf_game_obj_1.team2_code] = custom_seeding['seed4']
                        if sf_game_obj_2:
                            playoff_team_map[sf_game_obj_2.team1_code] = custom_seeding['seed2']
                            playoff_team_map[sf_game_obj_2.team2_code] = custom_seeding['seed3']
                    else:
                        # Use standard IIHF seeding based on semifinal assignments
                        playoff_team_map['Q1'] = sf_game1_teams[0]  # First team in SF1
                        playoff_team_map['Q2'] = sf_game1_teams[1]  # Second team in SF1
                        playoff_team_map['Q3'] = sf_game2_teams[0]  # First team in SF2
                        playoff_team_map['Q4'] = sf_game2_teams[1]  # Second team in SF2

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

    # Build team_combinations_with_games dictionary for VS button logic (including resolved playoff teams)
    team_combinations_with_games = {}
    
    # Get all years to build year-specific playoff maps
    all_years = ChampionshipYear.query.all()
    playoff_maps_by_year = {}
    
    for year_item in all_years:
        current_playoff_map = {}
        if year_item.fixture_path:
            absolute_fixture_path = resolve_fixture_path(year_item.fixture_path)
            if absolute_fixture_path and os.path.exists(absolute_fixture_path):
                try:
                    with open(absolute_fixture_path, 'r', encoding='utf-8') as f:
                        fixture_data = json.load(f)
                    
                    # Get all games for this year to use in playoff resolution
                    year_games = Game.query.filter_by(year_id=year_item.id).all()
                    year_games_dict = {g.game_number: g for g in year_games}
                    
                    # Build playoff map using similar logic as in the main function
                    # First handle group rankings (A1, A2, etc.)
                    year_prelim_games = [g for g in year_games if g.round == 'Preliminary Round' and g.group]
                    year_unique_teams_in_prelim_groups = set()
                    for g in year_prelim_games:
                        if g.team1_code and g.group: 
                            year_unique_teams_in_prelim_groups.add((g.team1_code, g.group))
                        if g.team2_code and g.group: 
                            year_unique_teams_in_prelim_groups.add((g.team2_code, g.group))

                    year_teams_stats = {}
                    for team_code, group_name in year_unique_teams_in_prelim_groups:
                        if team_code not in year_teams_stats: 
                            year_teams_stats[team_code] = TeamStats(name=team_code, group=group_name)

                    for g in [pg for pg in year_prelim_games if pg.team1_score is not None]: 
                        for code, grp, gf, ga, pts, res, is_t1 in [(g.team1_code, g.group, g.team1_score, g.team2_score, g.team1_points, g.result_type, True),
                                                                (g.team2_code, g.group, g.team2_score, g.team1_score, g.team2_points, g.result_type, False)]:
                            stats = year_teams_stats.setdefault(code, TeamStats(name=code, group=grp))
                            
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
                    
                    # Create standings and map group positions
                    year_standings_by_group = {}
                    if year_teams_stats:
                        group_full_names = sorted(list(set(s.group for s in year_teams_stats.values() if s.group))) 
                        for full_group_name_key in group_full_names: 
                            current_group_teams = sorted(
                                [s for s in year_teams_stats.values() if s.group == full_group_name_key],
                                key=lambda x: (x.pts, x.gd, x.gf),
                                reverse=True
                            )
                            current_group_teams = _apply_head_to_head_tiebreaker(current_group_teams, year_prelim_games)
                            year_standings_by_group[full_group_name_key] = current_group_teams
                    
                    # Map group positions (A1, A2, etc.)
                    for group_display_name, group_standings_list in year_standings_by_group.items():
                        group_letter_match = re.match(r"Group ([A-D])", group_display_name) 
                        if group_letter_match:
                            group_letter = group_letter_match.group(1)
                            for i, s_team_obj in enumerate(group_standings_list): 
                                current_playoff_map[f'{group_letter}{i+1}'] = s_team_obj.name
                    
                    # Now resolve W(game_number) placeholders
                    max_iterations = 10  # Prevent infinite loops
                    for iteration in range(max_iterations):
                        changes_made = False
                        schedule_data = fixture_data.get("schedule", [])
                        for game_data in schedule_data:
                            team1_code = game_data.get('team1_code', '')
                            team2_code = game_data.get('team2_code', '')
                            game_number = game_data.get('gameNumber')
                            
                            # Resolve W(game_number) or L(game_number) placeholders
                            for team_code in [team1_code, team2_code]:
                                if (team_code.startswith('W(') or team_code.startswith('L(')) and team_code.endswith(')'):
                                    if team_code not in current_playoff_map:
                                        # Extract the dependency game number
                                        dependency_str = team_code[2:-1]  # Remove W( or L( and )
                                        if dependency_str.isdigit():
                                            dependency_game_num = int(dependency_str)
                                            dependency_game = year_games_dict.get(dependency_game_num)
                                            
                                            if dependency_game and dependency_game.team1_score is not None and dependency_game.team2_score is not None:
                                                # Determine winner/loser
                                                if dependency_game.team1_score > dependency_game.team2_score:
                                                    winner_code = dependency_game.team1_code
                                                    loser_code = dependency_game.team2_code
                                                else:
                                                    winner_code = dependency_game.team2_code
                                                    loser_code = dependency_game.team1_code
                                                
                                                # Resolve the winner/loser code if it's also a placeholder
                                                resolved_winner = current_playoff_map.get(winner_code, winner_code)
                                                resolved_loser = current_playoff_map.get(loser_code, loser_code)
                                                
                                                # Only add if we can resolve to actual team names
                                                if team_code.startswith('W(') and TEAM_ISO_CODES.get(resolved_winner.upper()):
                                                    current_playoff_map[team_code] = resolved_winner
                                                    changes_made = True
                                                elif team_code.startswith('L(') and TEAM_ISO_CODES.get(resolved_loser.upper()):
                                                    current_playoff_map[team_code] = resolved_loser
                                                    changes_made = True
                        
                        if not changes_made:
                            break  # No more changes possible
                            
                except Exception as e:
                    current_app.logger.warning(f"Error processing playoff map for year {year_item.id}: {e}")
                    pass
        
        playoff_maps_by_year[year_item.id] = current_playoff_map
    
    # Now process all games with their respective playoff maps
    all_games_across_years = Game.query.filter(
        Game.team1_score.isnot(None), 
        Game.team2_score.isnot(None)
    ).all()
    
    for game in all_games_across_years:
        # Get the playoff map for this game's year
        game_playoff_map = playoff_maps_by_year.get(game.year_id, {})
        
        # Resolve team codes using the playoff map
        resolved_team1 = game_playoff_map.get(game.team1_code, game.team1_code)
        resolved_team2 = game_playoff_map.get(game.team2_code, game.team2_code)
        
        # Only add if both resolved teams are actual teams (not placeholders)
        if (TEAM_ISO_CODES.get(resolved_team1.upper()) and TEAM_ISO_CODES.get(resolved_team2.upper())):
            team_pair_sorted = sorted([resolved_team1, resolved_team2])
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

@year_bp.route('/<int:year_id>/team_vs_team/<team1>/<team2>')
def team_vs_team_view(year_id, team1, team2):
    year_obj = db.session.get(ChampionshipYear, year_id)
    if not year_obj:
        flash('Turnierjahr nicht gefunden.', 'danger')
        return redirect(url_for('main_bp.index'))

    # Team-Namen normalisieren für bessere Matcherkennung
    t1, t2 = team1.strip().upper(), team2.strip().upper()

    # Verwende die bewährte get_all_resolved_games() Funktion aus record_routes.py
    from constants import PIM_MAP, TEAM_ISO_CODES
    
    # Hole alle aufgelösten Spiele
    all_resolved_games = get_all_resolved_games()
    
    # Filtere nach unseren beiden Teams
    filtered_games = []
    for resolved_game in all_resolved_games:
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        
        # Prüfe ob dieses Spiel unsere beiden Teams betrifft
        if ((team1_code == t1 and team2_code == t2) or 
            (team1_code == t2 and team2_code == t1)):
            
            # Bestimme welches Team t1 und t2 ist basierend auf der aufgelösten Reihenfolge
            if team1_code == t1:
                t1_score = resolved_game['game'].team1_score
                t2_score = resolved_game['game'].team2_score
            else:
                t1_score = resolved_game['game'].team2_score 
                t2_score = resolved_game['game'].team1_score
            
            filtered_games.append({
                'game': resolved_game['game'],
                'team1_code': team1_code,
                'team2_code': team2_code,
                't1_score': t1_score,
                't2_score': t2_score,
                'year': resolved_game['year']
            })

    # Calculate stats that the template expects
    stats = {
        t1: {'tore': 0, 'pim': 0, 'sog': 0, 'siege': 0, 'spiele': 0, 'ot_siege': 0, 'so_siege': 0, 'niederlagen': 0, 'ot_niederlagen': 0, 'so_niederlagen': 0, 'pp_goals': 0, 'pp_opportunities': 0},
        t2: {'tore': 0, 'pim': 0, 'sog': 0, 'siege': 0, 'spiele': 0, 'ot_siege': 0, 'so_siege': 0, 'niederlagen': 0, 'ot_niederlagen': 0, 'so_niederlagen': 0, 'pp_goals': 0, 'pp_opportunities': 0}
    }
    
    duel_details = []
    
    for resolved_game in filtered_games:
        game = resolved_game['game']
        t1_score = resolved_game['t1_score']
        t2_score = resolved_game['t2_score']
        
        # Import required models
        from models import Penalty, Goal, ShotsOnGoal
        
        # Strafminuten sammeln
        penalty_entries = Penalty.query.filter_by(game_id=game.id).all()
        penalties_t1 = sum(PIM_MAP.get(p.penalty_type, 0) for p in penalty_entries if p.team_code.upper() == t1)
        penalties_t2 = sum(PIM_MAP.get(p.penalty_type, 0) for p in penalty_entries if p.team_code.upper() == t2)
        stats[t1]['pim'] += penalties_t1
        stats[t2]['pim'] += penalties_t2

        # Powerplay-Gelegenheiten zählen
        for penalty in penalty_entries:
            if penalty.team_code.upper() == t1:
                stats[t2]['pp_opportunities'] += 1
            elif penalty.team_code.upper() == t2:
                stats[t1]['pp_opportunities'] += 1

        # Powerplay-Tore sammeln
        goal_entries = Goal.query.filter_by(game_id=game.id).all()
        for goal in goal_entries:
            if goal.goal_type == 'PP':
                if goal.team_code.upper() == t1:
                    stats[t1]['pp_goals'] += 1
                elif goal.team_code.upper() == t2:
                    stats[t2]['pp_goals'] += 1

        # Schüsse sammeln
        sog_entries = ShotsOnGoal.query.filter_by(game_id=game.id).all()
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
            
            # Siege und Niederlagen zählen
            if t1_score > t2_score:
                if game.result_type == 'REG':
                    stats[t1]['siege'] += 1
                    stats[t2]['niederlagen'] += 1
                elif game.result_type == 'OT':
                    stats[t1]['ot_siege'] += 1
                    stats[t2]['ot_niederlagen'] += 1
                elif game.result_type == 'SO':
                    stats[t1]['so_siege'] += 1
                    stats[t2]['so_niederlagen'] += 1
            elif t2_score > t1_score:
                if game.result_type == 'REG':
                    stats[t2]['siege'] += 1
                    stats[t1]['niederlagen'] += 1
                elif game.result_type == 'OT':
                    stats[t2]['ot_siege'] += 1
                    stats[t1]['ot_niederlagen'] += 1
                elif game.result_type == 'SO':
                    stats[t2]['so_siege'] += 1
                    stats[t1]['so_niederlagen'] += 1

        # Für duel_details
        round_display = game.round
        if round_display == 'Preliminary Round':
            round_display = 'Hauptrunde'
        elif 'Quarter' in round_display:
            round_display = 'Viertelfinale'
        elif 'Semi' in round_display:
            round_display = 'Halbfinale'
        elif 'Bronze' in round_display or round_display == 'Spiel um Platz 3':
            round_display = 'Spiel um Platz 3'
        elif 'Gold' in round_display or 'Final' in round_display or round_display == 'Finale':
            round_display = 'Finale'
        
        result_display = ''
        if game.result_type == 'REG':
            result_display = 'Regulär'
        elif game.result_type == 'OT':
            result_display = 'n.V.'
        elif game.result_type == 'SO':
            result_display = 'n.P.'
        
        # Jahr des Spiels bestimmen
        year_display = '-'
        if game.year_id:
            year_obj_of_game = db.session.get(ChampionshipYear, game.year_id)
            if year_obj_of_game:
                year_display = str(year_obj_of_game.year)
        
        duel_details.append({
            'game': game,
            't1_score': t1_score,
            't2_score': t2_score,
            'date': game.date,
            'round_display': round_display,
            'location': game.location,
            'result_display': result_display,
            'year_display': year_display
        })

    # Durchschnittswerte berechnen
    for team in [t1, t2]:
        spiele = stats[team]['spiele'] if stats[team]['spiele'] > 0 else 1
        stats[team]['tore_avg'] = round(stats[team]['tore'] / spiele, 2)
        stats[team]['pim_avg'] = round(stats[team]['pim'] / spiele, 2)
        stats[team]['sog_avg'] = round(stats[team]['sog'] / spiele, 2)
        stats[team]['siege_gesamt'] = stats[team]['siege'] + stats[team]['ot_siege'] + stats[team]['so_siege']
        stats[team]['niederlagen_gesamt'] = stats[team]['niederlagen'] + stats[team]['ot_niederlagen'] + stats[team]['so_niederlagen']
        stats[team]['siege_avg'] = round(stats[team]['siege_gesamt'] / spiele, 2)

    # Sortiere nach Datum (neueste zuerst)
    duel_details.sort(key=lambda x: (x['year_display'], x['date'] or ''), reverse=True)
    
    # DEBUG ENTFERNT - Problem war nicht im Backend
    
    return render_template('team_vs_team.html',
                         year=year_obj,
                         team1=t1, team2=t2,
                         stats=stats,
                         duel_details=duel_details,
                         team_iso_codes=TEAM_ISO_CODES)