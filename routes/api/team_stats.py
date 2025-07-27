import os
import json
import re
from flask import jsonify, request, current_app
from models import db, ChampionshipYear, Game, TeamStats, GameDisplay, ShotsOnGoal, Goal, Penalty
from routes.blueprints import main_bp
from utils import is_code_final, _apply_head_to_head_tiebreaker, get_resolved_team_code
from utils.fixture_helpers import resolve_fixture_path
from utils.seeding_helpers import get_custom_seeding_from_db
from utils.playoff_resolver import PlayoffResolver
from constants import PIM_MAP, POWERPLAY_PENALTY_TYPES, PRELIM_ROUNDS, PLAYOFF_ROUNDS
# Importiere Services
from app.services.core.team_service import TeamService
from app.services.core.game_service import GameService
from app.services.core.standings_service import StandingsService
from app.services.core.tournament_service import TournamentService
from app.exceptions import NotFoundError, ServiceError


@main_bp.route('/api/team-yearly-stats/<team_code>')
def get_team_yearly_stats(team_code):
    """
    Get yearly statistics for a specific team across all years - SERVICE VERSION
    Optimiert für weniger Queries durch Service Layer
    """
    # Services initialisieren
    team_service = TeamService()
    game_service = GameService()
    standings_service = StandingsService()
    tournament_service = TournamentService()
    
    try:
        # Get game type filter from query parameter
        game_type = request.args.get('game_type', 'all')
        if game_type not in ['all', 'preliminary', 'playoffs']:
            game_type = 'all'
            
        # Get all championship years through service
        all_years = tournament_service.get_all()
        yearly_stats = []
        
        for year_obj in all_years:
            year_id = year_obj.id
            
            # Hole alle Spiele für das Jahr über Service (mit optimierten Queries)
            games_data = game_service.get_games_by_year_with_details(year_id)
            games_raw = games_data['games']
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
            
            # Verwende StandingsService für die Gruppenstandings
            group_standings = standings_service.calculate_group_standings(year_id)
            
            # Flache teams_stats Map aus den Gruppenstandings erstellen
            teams_stats = {}
            for group_name, teams in group_standings.items():
                for team in teams:
                    teams_stats[team.name] = team
            
            # Erstelle playoff_team_map basierend auf Standings
            playoff_team_map = {}
            for group_name, teams in group_standings.items():
                group_letter = group_name.replace("Group ", "") if group_name.startswith("Group ") else group_name
                for i, team in enumerate(teams, 1):
                    playoff_team_map[f'{group_letter}{i}'] = team.name
            
            # Check for custom QF seeding and apply if exists
            from routes.year.seeding import get_custom_qf_seeding_from_db
            custom_qf_seeding = get_custom_qf_seeding_from_db(year_id)
            if custom_qf_seeding:
                # Override standard group position mappings with custom seeding
                for position, team_name in custom_qf_seeding.items():
                    playoff_team_map[position] = team_name
            
            games_dict_by_num = {g.game_number: g for g in games_raw}
            
            # Verwende GameService für Fixture-Daten
            fixture_data = game_service.get_fixture_info(year_obj)
            qf_game_numbers = fixture_data.get('quarterfinal_games', [])
            sf_game_numbers = fixture_data.get('semifinal_games', [])
            bronze_game_number = fixture_data.get('bronze_game_number')
            gold_game_number = fixture_data.get('gold_game_number')
            tournament_hosts = fixture_data.get('hosts', [])
            
            if sf_game_numbers and len(sf_game_numbers) >= 2 and all(isinstance(item, int) for item in sf_game_numbers):
                playoff_team_map['SF1'] = str(sf_game_numbers[0])
                playoff_team_map['SF2'] = str(sf_game_numbers[1])
            
            # Initialisiere PlayoffResolver für die Auflösung von Playoff-Codes
            playoff_resolver = PlayoffResolver(year_obj, games_raw)
            
            # Wrapper-Funktion für Kompatibilität mit existierendem Code
            def get_resolved_code(placeholder_code, current_map):
                # Verwende PlayoffResolver für die Auflösung
                return playoff_resolver.get_resolved_code(placeholder_code)
            
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
            
            # ====== NOW CALCULATE TEAM STATS USING SERVICE ======
            # Check if tournament is completed before calculating final ranking
            team_final_position = None
            try:
                tournament_stats = tournament_service.get_tournament_statistics(year_id)
                is_completed = (tournament_stats['total_games'] > 0 and 
                               tournament_stats['completed_games'] == tournament_stats['total_games'])
                
                if is_completed:
                    # Hole finale Platzierung über Service
                    final_ranking = standings_service.calculate_final_tournament_ranking(year_id)
                    for position, team in final_ranking.items():
                        if team == team_code:
                            team_final_position = position
                            break
            except Exception as e:
                # If there's an error checking completion, don't show position
                pass
            
            # Find if team participated in this year
            team_participated = False
            gp = w = otw = sow = l = otl = sol = gf = ga = pts = 0
            sog = soga = ppgf = ppga = ppf = ppa = 0
            
            # Verwende TeamService für effiziente Statistikberechnung
            # Der Service hat bereits optimierte Queries
            team_codes_in_year = [team_code]
            games_processed_map = {g.id: g for g in games_processed}
            
            # Filter games based on game_type parameter before processing
            def should_include_game(game_obj, resolved_game_obj, game_type_filter, target_team_code):
                """Helper function to determine if a game should be included based on game type filter"""
                playoff_indicators = ['Quarter', 'Semi', 'Final', 'Bronze', 'Gold', 'Playoff']
                is_playoff_game = (game_obj.round in PLAYOFF_ROUNDS or 
                                 any(indicator in game_obj.round for indicator in playoff_indicators))
                
                if game_type_filter == 'all':
                    if is_playoff_game:
                        team_in_resolved = (resolved_game_obj.team1_code.upper() == target_team_code.upper() or
                                          resolved_game_obj.team2_code.upper() == target_team_code.upper())
                        return team_in_resolved
                    else:
                        return True
                elif game_type_filter == 'preliminary':
                    return game_obj.round in PRELIM_ROUNDS
                elif game_type_filter == 'playoffs':
                    if is_playoff_game:
                        team_in_resolved = (resolved_game_obj.team1_code.upper() == target_team_code.upper() or
                                          resolved_game_obj.team2_code.upper() == target_team_code.upper())
                        return team_in_resolved
                    return False
                return True
            
            # Berechne Statistiken manuell (später optimieren mit Service)
            for game_id, resolved_game_this_iter in games_processed_map.items():
                raw_game_obj_this_iter = games_raw_map.get(game_id)
                if not raw_game_obj_this_iter:
                    continue

                # Filter out games based on game type
                if not should_include_game(raw_game_obj_this_iter, resolved_game_this_iter, game_type, team_code):
                    continue

                is_current_team_t1_in_raw_game = False
                team_found_in_game = False

                # First check if team is directly in the raw game (for preliminary games)
                if raw_game_obj_this_iter.team1_code and raw_game_obj_this_iter.team1_code.upper() == team_code.upper():
                    is_current_team_t1_in_raw_game = True
                    team_found_in_game = True
                elif raw_game_obj_this_iter.team2_code and raw_game_obj_this_iter.team2_code.upper() == team_code.upper():
                    is_current_team_t1_in_raw_game = False
                    team_found_in_game = True
                # If not found in raw game, check resolved game (for playoff games with placeholders)
                elif resolved_game_this_iter.team1_code.upper() == team_code.upper():
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
                    
                    # Hole SOG, Goal und Penalty Statistiken über Service
                    # Dies vermeidet N+1 Queries
                    game_stats = game_service.get_game_advanced_stats(game_id)
                    
                    # SOG für das Team
                    sog += game_stats['team_stats'].get(team_code, {}).get('shots', 0)
                    
                    # SOGA (Gegner SOG)
                    opp_team_code = resolved_game_this_iter.team2_code if is_current_team_t1_in_raw_game else resolved_game_this_iter.team1_code
                    soga += game_stats['team_stats'].get(opp_team_code, {}).get('shots', 0)
                    
                    # PP/PK Statistiken
                    ppgf += game_stats['team_stats'].get(team_code, {}).get('powerplay_goals', 0)
                    ppga += game_stats['team_stats'].get(opp_team_code, {}).get('powerplay_goals', 0)
                    ppf += game_stats['team_stats'].get(team_code, {}).get('powerplay_opportunities', 0)
                    ppa += game_stats['team_stats'].get(opp_team_code, {}).get('powerplay_opportunities', 0)

            gd = gf - ga
            
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
        
    except NotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except ServiceError as e:
        current_app.logger.error(f"Service error calculating yearly stats for {team_code}: {e}")
        return jsonify({'error': 'Failed to calculate yearly statistics'}), 500
    except Exception as e:
        current_app.logger.error(f"Error calculating yearly stats for {team_code}: {e}")
        return jsonify({'error': 'Failed to calculate yearly statistics'}), 500