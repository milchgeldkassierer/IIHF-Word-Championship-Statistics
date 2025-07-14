from models import db, Game, Goal, Player, ChampionshipYear, Penalty, TeamStats
from collections import defaultdict
import re, os, json
from constants import TEAM_ISO_CODES, PIM_MAP
from utils import resolve_game_participants, get_resolved_team_code, is_code_final, _apply_head_to_head_tiebreaker
from utils.data_validation import calculate_tournament_penalty_minutes
from sqlalchemy import func, case


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
        
        # Calculate PIM using centralized function
        penalties_count = calculate_tournament_penalty_minutes(year_obj.id, completed_games_only=True)
    
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


def get_all_resolved_games():
    """
    Holt alle Spiele und löst Platzhalter auf
    """
    
    all_resolved_games = []
    years = ChampionshipYear.query.all()
    
    # Pre-calculate correct medal game rankings for each year (like in calculate_all_time_standings)
    # CRITICAL: Must use the same playoff resolution logic as the main function to be consistent
    medal_game_rankings_by_year = {}
    games_by_year_id = {}
    
    # First pass: collect all games by year and calculate medal rankings with proper custom seeding
    for year_obj in years:
        games_this_year = Game.query.filter_by(year_id=year_obj.id).order_by(Game.date, Game.start_time, Game.game_number).all()
        games_by_year_id[year_obj.id] = games_this_year
        
        # Build a basic playoff map for this year including custom seeding
        temp_playoff_map = {}
        
        # Apply custom seeding if it exists
        try:
            from routes.year.seeding import get_custom_seeding_from_db
            custom_seeding = get_custom_seeding_from_db(year_obj.id)
            if custom_seeding:
                temp_playoff_map['seed1'] = custom_seeding['seed1']
                temp_playoff_map['seed2'] = custom_seeding['seed2']
                temp_playoff_map['seed3'] = custom_seeding['seed3']
                temp_playoff_map['seed4'] = custom_seeding['seed4']
        except:
            pass
        
        # Pre-calculate final ranking for this year
        try:
            from utils.standings import calculate_complete_final_ranking
            final_ranking = calculate_complete_final_ranking(year_obj, games_this_year, temp_playoff_map, year_obj)
            medal_game_rankings_by_year[year_obj.id] = final_ranking
        except Exception as e:
            medal_game_rankings_by_year[year_obj.id] = {}
    
    for year_obj in years:
        try:
            games_raw = Game.query.filter_by(year_id=year_obj.id).order_by(Game.date, Game.start_time, Game.game_number).all()
            
            if not games_raw:
                continue
                
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
                try:
                    from utils.fixture_helpers import resolve_fixture_path
                    absolute_fixture_path = resolve_fixture_path(year_obj.fixture_path)
                    fixture_path_exists = absolute_fixture_path and os.path.exists(absolute_fixture_path)
                except:
                    fixture_path_exists = False

            if year_obj.fixture_path and fixture_path_exists:
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

            for _pass_num in range(max(3, len(games_raw) // 2)): 
                changes_in_pass = 0
                for game in games_raw:
                    if game.team1_score is None or game.team2_score is None:
                        continue
                    
                    resolved_t1 = get_resolved_code(game.team1_code, playoff_team_map)
                    resolved_t2 = get_resolved_code(game.team2_code, playoff_team_map)
                    
                    if game.round != 'Preliminary Round':
                        if is_code_final(resolved_t1) and is_code_final(resolved_t2):
                            actual_winner = resolved_t1 if game.team1_score > game.team2_score else resolved_t2
                            actual_loser = resolved_t2 if game.team1_score > game.team2_score else resolved_t1
                            
                            win_key = f'W({game.game_number})'
                            lose_key = f'L({game.game_number})'
                            if playoff_team_map.get(win_key) != actual_winner: 
                                playoff_team_map[win_key] = actual_winner
                                changes_in_pass += 1
                            if playoff_team_map.get(lose_key) != actual_loser: 
                                playoff_team_map[lose_key] = actual_loser
                                changes_in_pass += 1
                
                if changes_in_pass == 0 and _pass_num > 0: 
                    break 

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
                        
                        # Check for custom seeding for this specific year
                        from routes.year.seeding import get_custom_seeding_from_db
                        custom_seeding = get_custom_seeding_from_db(year_obj.id)
                        
                        if custom_seeding:
                            # NOTE: Custom seeding will be applied at the end of the resolution process
                            # to ensure consistent application. For now, just note that custom seeding exists.
                            pass
                        else:
                            # Use standard IIHF seeding
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
                                
                                playoff_team_map['seed1'] = sf_game1_teams[0]
                                playoff_team_map['seed4'] = sf_game1_teams[1]
                                playoff_team_map['seed2'] = sf_game2_teams[0]
                                playoff_team_map['seed3'] = sf_game2_teams[1]

            # Apply custom seeding after all team resolution is complete (like in get_medal_tally_data)
            # This ensures that custom seeding overrides any previous seed1-seed4 mappings
            try:
                from routes.year.seeding import get_custom_seeding_from_db
                custom_seeding = get_custom_seeding_from_db(year_obj.id)
                if custom_seeding:
                    # Override seed1-seed4 mappings with custom seeding
                    playoff_team_map['seed1'] = custom_seeding['seed1']
                    playoff_team_map['seed2'] = custom_seeding['seed2']
                    playoff_team_map['seed3'] = custom_seeding['seed3']
                    playoff_team_map['seed4'] = custom_seeding['seed4']
            except ImportError:
                pass  # If import fails, continue without custom seeding

            for game in games_raw:
                if game.team1_score is not None and game.team2_score is not None:
                    # CRITICAL: Special handling for Medal Games using correct final ranking (like in calculate_all_time_standings)
                    final_team1_code = None
                    final_team2_code = None
                    
                    if game.round in ['Gold Medal Game', 'Bronze Medal Game', 'Semifinals']:
                        # Use correct medal game resolution from calculate_complete_final_ranking
                        year_ranking = medal_game_rankings_by_year.get(year_obj.id, {})
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
                                # Check if custom seeding exists for this year first
                                try:
                                    from routes.year.seeding import get_custom_seeding_from_db
                                    custom_seeding = get_custom_seeding_from_db(year_obj.id)
                                    
                                    if custom_seeding:
                                        # For custom seeding, we know the exact teams that played
                                        if game.game_number == 61:  # SF1: seed1 vs seed4
                                            # Teams that played: seed1 and seed4
                                            sf1_teams = [custom_seeding['seed1'], custom_seeding['seed4']]
                                            # Assign based on who's listed first in team codes (maintain order)
                                            final_team1_code = sf1_teams[0]  # seed1
                                            final_team2_code = sf1_teams[1]  # seed4
                                        elif game.game_number == 62:  # SF2: seed2 vs seed3
                                            # Teams that played: seed2 and seed3
                                            sf2_teams = [custom_seeding['seed2'], custom_seeding['seed3']]
                                            # Assign based on who's listed first in team codes (maintain order)
                                            final_team1_code = sf2_teams[0]  # seed2
                                            final_team2_code = sf2_teams[1]  # seed3
                                        else:
                                            # Unknown game number, use standard resolution
                                            final_team1_code = get_resolved_code(game.team1_code, playoff_team_map)
                                            final_team2_code = get_resolved_code(game.team2_code, playoff_team_map)
                                    else:
                                        # No custom seeding, use standard resolution
                                        final_team1_code = get_resolved_code(game.team1_code, playoff_team_map)
                                        final_team2_code = get_resolved_code(game.team2_code, playoff_team_map)
                                except:
                                    # Fallback to standard resolution
                                    final_team1_code = get_resolved_code(game.team1_code, playoff_team_map)
                                    final_team2_code = get_resolved_code(game.team2_code, playoff_team_map)
                    
                    # Fallback to standard resolution if medal game resolution failed
                    if not final_team1_code or not final_team2_code:
                        resolved_team1_code = get_resolved_code(game.team1_code, playoff_team_map)
                        resolved_team2_code = get_resolved_code(game.team2_code, playoff_team_map)
                        final_team1_code = resolved_team1_code
                        final_team2_code = resolved_team2_code
                    
                    all_resolved_games.append({
                        'game': game,
                        'team1_code': final_team1_code,
                        'team2_code': final_team2_code,
                        'year': year_obj.year
                    })
                        
        except Exception as e:
            for game in Game.query.filter_by(year_id=year_obj.id).all():
                if (game.team1_score is not None and game.team2_score is not None and
                    is_code_final(game.team1_code) and is_code_final(game.team2_code)):
                    all_resolved_games.append({
                        'game': game,
                        'team1_code': game.team1_code,
                        'team2_code': game.team2_code,
                        'year': year_obj.year
                    })

    return all_resolved_games


def get_resolved_team_info(team_code, game=None):
    """
    Hilfsfunktion um Team-Codes zu bereinigen und ISO-Codes zu holen
    """
    if not team_code:
        return team_code, None
    
    if game and game.year_id:
        try:
            year_obj = db.session.query(ChampionshipYear).filter_by(id=game.year_id).first()
            if year_obj:
                all_games = db.session.query(Game).filter_by(year_id=game.year_id).all()
                resolved_team1, resolved_team2 = resolve_game_participants(game, year_obj, all_games)
                
                if game.team1_code == team_code:
                    team_code = resolved_team1
                elif game.team2_code == team_code:
                    team_code = resolved_team2
        except:
            pass
    
    iso_code = TEAM_ISO_CODES.get(team_code)
    
    return team_code, iso_code