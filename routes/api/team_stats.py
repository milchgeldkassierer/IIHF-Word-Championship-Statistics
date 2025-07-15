import os
import json
import re
from flask import jsonify, request, current_app
from models import db, ChampionshipYear, Game, TeamStats, GameDisplay, ShotsOnGoal, Goal, Penalty
from routes.blueprints import main_bp
from utils import is_code_final, _apply_head_to_head_tiebreaker, get_resolved_team_code
from utils.fixture_helpers import resolve_fixture_path
from utils.seeding_helpers import get_custom_seeding_from_db
from constants import PIM_MAP, POWERPLAY_PENALTY_TYPES, PRELIM_ROUNDS, PLAYOFF_ROUNDS



@main_bp.route('/api/team-yearly-stats/<team_code>')
def get_team_yearly_stats(team_code):
    """Get yearly statistics for a specific team across all years - COMPLETE VERSION with all playoff logic"""
    try:
        # Get game type filter from query parameter
        game_type = request.args.get('game_type', 'all')
        if game_type not in ['all', 'preliminary', 'playoffs']:
            game_type = 'all'
        # Get all championship years
        all_years = ChampionshipYear.query.order_by(ChampionshipYear.year).all()
        yearly_stats = []
        
        for year_obj in all_years:
            year_id = year_obj.id
            
            # Get all games for this year
            games_raw = Game.query.filter_by(year_id=year_id).order_by(Game.date, Game.start_time, Game.game_number).all()
            games_raw_map = {g.id: g for g in games_raw}
            
            if not games_raw:
                # No games in this year - team didn't participate
                yearly_stats.append({
                    'year': year_obj.year,
                    'participated': False,
                    'final_position': None,
                    'stats': {'gp': 0, 'w': 0, 'otw': 0, 'sow': 0, 'l': 0, 'otl': 0, 'sol': 0, 'gf': 0, 'ga': 0, 'gd': 0, 'pts': 0}
                })
                continue
            
            # ====== COMPLETE COPY OF YEAR_VIEW LOGIC STARTS HERE ======
            
            # Build teams_stats (preliminary round only for standings)
            teams_stats = {}
            prelim_games = [g for g in games_raw if g.round == 'Preliminary Round' and g.group]
            
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

            # Create games_processed exactly like in year_view
            games_processed = [GameDisplay(id=g.id, year_id=g.year_id, date=g.date, start_time=g.start_time, round=g.round, group=g.group, game_number=g.game_number, location=g.location, venue=g.venue, team1_code=g.team1_code, team2_code=g.team2_code, original_team1_code=g.team1_code, original_team2_code=g.team2_code, team1_score=g.team1_score, team2_score=g.team2_score, result_type=g.result_type, team1_points=g.team1_points, team2_points=g.team2_points) for g in games_raw]

            # Multi-pass resolution exactly like in year_view
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

            # COMPLETE SEMIFINAL AND FINALS PAIRING LOGIC
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
                            if playoff_team_map.get(sf_game_obj_1.team1_code) != sf_game1_teams[0]:
                                playoff_team_map[sf_game_obj_1.team1_code] = sf_game1_teams[0]
                            if playoff_team_map.get(sf_game_obj_1.team2_code) != sf_game1_teams[1]:
                                playoff_team_map[sf_game_obj_1.team2_code] = sf_game1_teams[1]
                            if playoff_team_map.get(sf_game_obj_2.team1_code) != sf_game2_teams[0]:
                                playoff_team_map[sf_game_obj_2.team1_code] = sf_game2_teams[0]
                            if playoff_team_map.get(sf_game_obj_2.team2_code) != sf_game2_teams[1]:
                                playoff_team_map[sf_game_obj_2.team2_code] = sf_game2_teams[1]
                            
                            # Apply custom seeding to seed1-seed4 mappings
                            if custom_seeding:
                                # IIHF format: SF1 = seed1 vs seed4, SF2 = seed2 vs seed3
                                # Database now directly stores this format
                                playoff_team_map['seed1'] = custom_seeding['seed1']
                                playoff_team_map['seed2'] = custom_seeding['seed2']
                                playoff_team_map['seed3'] = custom_seeding['seed3']
                                playoff_team_map['seed4'] = custom_seeding['seed4']
                                
                                # Logging removed for production
                            else:
                                # Use standard IIHF seeding based on semifinal assignments
                                playoff_team_map['seed1'] = sf_game1_teams[0]
                                playoff_team_map['seed4'] = sf_game1_teams[1]
                                playoff_team_map['seed2'] = sf_game2_teams[0]
                                playoff_team_map['seed3'] = sf_game2_teams[1]

            # Fallback seed1-seed4 mapping
            if qf_game_numbers and len(qf_game_numbers) == 4 and 'seed1' not in playoff_team_map:
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

            # Final resolution pass - CRITICAL!
            for g_disp_final_pass in games_processed:
                code_to_resolve_t1 = g_disp_final_pass.original_team1_code 
                resolved_t1_final = get_resolved_code(code_to_resolve_t1, playoff_team_map)
                if g_disp_final_pass.team1_code != resolved_t1_final:
                    g_disp_final_pass.team1_code = resolved_t1_final

                code_to_resolve_t2 = g_disp_final_pass.original_team2_code
                resolved_t2_final = get_resolved_code(code_to_resolve_t2, playoff_team_map)
                if g_disp_final_pass.team2_code != resolved_t2_final:
                    g_disp_final_pass.team2_code = resolved_t2_final

            # ====== NOW CALCULATE TEAM STATS USING FULLY RESOLVED GAMES (including ALL playoff games!) ======
            
            # Create games_processed_map
            games_processed_map = {g.id: g for g in games_processed}
            
            # Check if tournament is completed before calculating final ranking
            team_final_position = None
            try:
                from routes.records.utils import get_tournament_statistics
                tournament_stats = get_tournament_statistics(year_obj)
                is_completed = (tournament_stats['total_games'] > 0 and 
                               tournament_stats['completed_games'] == tournament_stats['total_games'])
                
                if is_completed:
                    # Calculate final ranking for this year using the same approach as medal_tally
                    # Build a basic playoff map for final ranking calculation (like in medal_tally.py)
                    temp_playoff_map = {}
                    
                    # Apply custom seeding if it exists (using medal_tally approach)
                    try:
                        custom_seeding = get_custom_seeding_from_db(year_id)
                        if custom_seeding:
                            temp_playoff_map['seed1'] = custom_seeding['seed1']
                            temp_playoff_map['seed2'] = custom_seeding['seed2']
                            temp_playoff_map['seed3'] = custom_seeding['seed3']
                            temp_playoff_map['seed4'] = custom_seeding['seed4']
                    except:
                        pass
                    
                    # Calculate final ranking (like in medal_tally.py) - use original games, not processed ones
                    from utils.standings import calculate_complete_final_ranking
                    final_ranking = calculate_complete_final_ranking(year_obj, games_raw, temp_playoff_map, year_obj)
                    if final_ranking:
                        for position, team in final_ranking.items():
                            if team == team_code:
                                try:
                                    team_final_position = int(position)
                                    break
                                except (ValueError, TypeError):
                                    pass
                # If tournament is not completed, team_final_position remains None
            except Exception as e:
                # If there's an error checking completion, don't show position
                pass
            
            # Find if team participated in this year - COMPLETE LOGIC FROM YEAR_VIEW
            team_participated = False
            gp = w = otw = sow = l = otl = sol = gf = ga = pts = 0
            sog = soga = ppgf = ppga = ppf = ppa = 0
            
            # Filter games based on game_type parameter before processing
            def should_include_game(game_obj, resolved_game_obj, game_type_filter):
                """Helper function to determine if a game should be included based on game type filter"""
                if game_type_filter == 'all':
                    return True
                elif game_type_filter == 'preliminary':
                    # Debug: print the round for debugging
                    return game_obj.round in PRELIM_ROUNDS
                elif game_type_filter == 'playoffs':
                    # Debug: print the round for debugging
                    # Check for various playoff round names that might exist in the database
                    playoff_indicators = ['Quarter', 'Semi', 'Final', 'Bronze', 'Gold', 'Playoff']
                    return (game_obj.round in PLAYOFF_ROUNDS or 
                            any(indicator in game_obj.round for indicator in playoff_indicators))
                return True
            
            # Use the EXACT same logic as year_view lines 714-779 - this includes ALL games (preliminary + playoffs)
            # Debug logging for 2016 - removed for now
            
            for game_id, resolved_game_this_iter in games_processed_map.items():
                raw_game_obj_this_iter = games_raw_map.get(game_id)
                if not raw_game_obj_this_iter:
                    continue

                # Filter out games based on game type - use the resolved game for filtering
                # since playoff games have placeholder codes that get resolved
                if not should_include_game(raw_game_obj_this_iter, resolved_game_this_iter, game_type):
                    continue

                # CRITICAL FIX: The logic needs to determine which team (team1 or team2) in the RAW game
                # corresponds to our target team. We do this by checking which resolved team matches our target.
                is_current_team_t1_in_raw_game = False
                team_found_in_game = False

                # Case-insensitive comparison to be safe
                if resolved_game_this_iter.team1_code.upper() == team_code.upper():
                    is_current_team_t1_in_raw_game = True
                    team_found_in_game = True
                elif resolved_game_this_iter.team2_code.upper() == team_code.upper():
                    is_current_team_t1_in_raw_game = False
                    team_found_in_game = True
                
                if not team_found_in_game:
                    continue

                if raw_game_obj_this_iter.team1_score is not None and raw_game_obj_this_iter.team2_score is not None: 
                    team_participated = True
                    gp += 1
                    current_team_score = raw_game_obj_this_iter.team1_score if is_current_team_t1_in_raw_game else raw_game_obj_this_iter.team2_score
                    opponent_score = raw_game_obj_this_iter.team2_score if is_current_team_t1_in_raw_game else raw_game_obj_this_iter.team1_score
                    gf += current_team_score
                    ga += opponent_score
                    
                    # Debug logging removed
                    
                    # Calculate points properly from raw game data
                    team_points = raw_game_obj_this_iter.team1_points if is_current_team_t1_in_raw_game else raw_game_obj_this_iter.team2_points
                    pts += team_points
                    
                    # Determine win/loss type based on actual result
                    result_type = raw_game_obj_this_iter.result_type
                    if result_type == 'REG':
                        if current_team_score > opponent_score:
                            w += 1
                        else:
                            l += 1
                    elif result_type == 'OT':
                        if current_team_score > opponent_score:
                            otw += 1
                        else:
                            otl += 1
                    elif result_type == 'SO':
                        if current_team_score > opponent_score:
                            sow += 1
                        else:
                            sol += 1
                    
                    # Calculate SOG statistics
                    sog_entries = ShotsOnGoal.query.filter_by(game_id=game_id, team_code=team_code).all()
                    sog += sum(entry.shots for entry in sog_entries)
                    
                    # Calculate SOGA (opponent's shots on goal)
                    opp_team_code = resolved_game_this_iter.team2_code if is_current_team_t1_in_raw_game else resolved_game_this_iter.team1_code
                    soga_entries = ShotsOnGoal.query.filter_by(game_id=game_id, team_code=opp_team_code).all()
                    soga += sum(entry.shots for entry in soga_entries)
                    
                    # Calculate PP/PK statistics
                    team_goals = Goal.query.filter_by(game_id=game_id, team_code=team_code).all()
                    opp_goals = Goal.query.filter_by(game_id=game_id, team_code=opp_team_code).all()
                    
                    # Count powerplay goals for and against
                    ppgf += sum(1 for goal in team_goals if goal.goal_type == 'PP')
                    ppga += sum(1 for goal in opp_goals if goal.goal_type == 'PP')
                    
                    # Estimate powerplay opportunities (simplified: count of opponent's penalties)
                    team_penalties = Penalty.query.filter_by(game_id=game_id, team_code=team_code).all()
                    opp_penalties = Penalty.query.filter_by(game_id=game_id, team_code=opp_team_code).all()
                    
                    ppf += len(opp_penalties)  # Team's PP opportunities = opponent's penalties
                    ppa += len(team_penalties)  # Team's PK situations = team's penalties

            gd = gf - ga
            
            # Debug logging removed
            
            # Calculate percentage statistics
            sg_pct = (gf / sog * 100) if sog > 0 else 0
            svs_pct = ((soga - ga) / soga * 100) if soga > 0 else 0
            pp_pct = (ppgf / ppf * 100) if ppf > 0 else 0
            pk_pct = ((ppa - ppga) / ppa * 100) if ppa > 0 else 0
            
            yearly_stats.append({
                'year': year_obj.year,
                'participated': team_participated,
                'final_position': team_final_position,
                'stats': {
                    'gp': gp, 'w': w, 'otw': otw, 'sow': sow, 'l': l, 'otl': otl, 'sol': sol,
                    'gf': gf, 'ga': ga, 'gd': gd, 'pts': pts,
                    'sog': sog, 'soga': soga,
                    'ppgf': ppgf, 'ppga': ppga, 'ppf': ppf, 'ppa': ppa,
                    'sg_pct': round(sg_pct, 1), 'svs_pct': round(svs_pct, 1),
                    'pp_pct': round(pp_pct, 1), 'pk_pct': round(pk_pct, 1)
                }
            })
        
        return jsonify({'team_code': team_code, 'yearly_stats': yearly_stats})
        
    except Exception as e:
        current_app.logger.error(f"Error calculating yearly stats for {team_code}: {e}")
        return jsonify({'error': 'Failed to calculate yearly statistics'}), 500