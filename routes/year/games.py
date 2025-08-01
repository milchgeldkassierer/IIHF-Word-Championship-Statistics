import json
import os
import re
import traceback
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from models import ChampionshipYear, Game, Player, Goal, Penalty, ShotsOnGoal, TeamStats, TeamOverallStats, GameDisplay, GameOverrule
from constants import TEAM_ISO_CODES, PENALTY_TYPES_CHOICES, PENALTY_REASONS_CHOICES, PIM_MAP, GOAL_TYPE_DISPLAY_MAP, POWERPLAY_PENALTY_TYPES, PERIOD_1_END, PERIOD_2_END, PERIOD_3_END, QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4
from utils import convert_time_to_seconds, check_game_data_consistency, is_code_final, _apply_head_to_head_tiebreaker
from utils.fixture_helpers import resolve_fixture_path
from utils.standings import calculate_complete_final_ranking
from utils.playoff_resolver import PlayoffResolver
from app.services.core.game_service import GameService
from app.exceptions import NotFoundError, ValidationError, BusinessRuleError

# Import the blueprint from the parent package
from . import year_bp
from .seeding import get_custom_seeding_from_db, save_custom_seeding_to_db, get_custom_qf_seeding_from_db

@year_bp.route('/add_sog_global/<int:game_id>', methods=['POST'])
def add_sog(game_id):
    """Add or update shots on goal using the GameService"""
    try:
        # Service Layer nutzen statt direktem Datenbankzugriff
        game_service = GameService()
        
        # Daten aus Request
        data = request.form
        resolved_t1_code = data.get('sog_team1_code_resolved') 
        resolved_t2_code = data.get('sog_team2_code_resolved')
        
        # SOG-Daten in das erwartete Format umwandeln
        sog_data = {}
        
        def collect_sog_for_team(team_code, form_prefix):
            if team_code and not (team_code.startswith(('A', 'B', 'W', 'L', 'Q', 'S')) and len(team_code) > 1 and team_code[1:].isdigit()):
                sog_data[team_code] = {}
                for period in range(1, 5):
                    shots_str = data.get(f'{form_prefix}_p{period}_shots')
                    if shots_str is not None:
                        try:
                            shots = int(shots_str.strip()) if shots_str.strip() else 0
                            sog_data[team_code][period] = shots
                        except ValueError:
                            sog_data[team_code][period] = 0
        
        collect_sog_for_team(resolved_t1_code, 'team1')
        collect_sog_for_team(resolved_t2_code, 'team2')
        
        # Service aufrufen
        result = game_service.add_shots_on_goal(game_id, sog_data)
        
        # Antwort vorbereiten - Formatierung für Kompatibilität
        current_sog_response = result['sog_data']
        # Stelle sicher, dass alle Teams alle Perioden haben
        for tc_resp in [resolved_t1_code, resolved_t2_code]:
            if tc_resp and not (tc_resp.startswith(('A', 'B', 'W', 'L', 'Q', 'S')) and len(tc_resp) > 1 and tc_resp[1:].isdigit()):
                current_sog_response.setdefault(tc_resp, {}) 
                for p_resp in range(1, 5):
                    current_sog_response[tc_resp].setdefault(p_resp, 0)
        
        # Nachricht basierend auf Ergebnis
        if result['made_changes']:
            message = 'Shots on Goal successfully saved.'
        elif sog_data and not result['made_changes']:
            message = 'SOG values were same or all zeros for new; no changes.'
        else:
            message = 'No valid teams for SOG update.'
        
        return jsonify({
            'success': True, 
            'message': message, 
            'game_id': game_id, 
            'sog_data': current_sog_response, 
            'scores_fully_match_goals': result['consistency']['scores_fully_match_data']
        })
        
    except NotFoundError as e:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden.'}), 404
    except ValidationError as e:
        return jsonify({'success': False, 'message': f'Validierungsfehler: {str(e)}'}), 400
    except Exception as e:
        current_app.logger.error(f"Error in add_sog: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@year_bp.route('/<int:year_id>/game/<int:game_id>/stats')
def game_stats_view(year_id, game_id):
    try:
        # Service Layer nutzen für Basis-Daten
        game_service = GameService()
        
        # Hole umfassende Spielstatistiken über Service
        stats_data = game_service.get_game_stats_for_view(year_id, game_id)
        
        # Extrahiere Daten für Template-Kompatibilität
        year_obj = stats_data['year']
        game_obj_for_stats = stats_data['game']

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

        # Verwende StandingsService für die Berechnung der Teamstatistiken (ultra-compact style beibehalten)
        from app.services.core.standings_service import StandingsService
        calculator = StandingsService()
        teams_stats = calculator.calculate_standings_from_games([pg for pg in prelim_games if pg.team1_score is not None])
    
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

        # Check for custom QF seeding and apply if exists
        custom_qf_seeding = get_custom_qf_seeding_from_db(year_id)
        if custom_qf_seeding:
            # Override standard group position mappings with custom seeding
            for position, team_name in custom_qf_seeding.items():
                playoff_team_map[position] = team_name

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
                
                qf_game_numbers.sort()
                sf_game_numbers.sort()
            except Exception as e:
                current_app.logger.error(f"Could not parse fixture {year_obj.fixture_path} for playoff game numbers. Error: {e}") 
                if year_obj.year == 2025: 
                    qf_game_numbers = [QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4]
                    sf_game_numbers = [61, 62]
                    bronze_game_number = 63
                    gold_game_number = 64
                    tournament_hosts = ["SWE", "DEN"]

        # SF1/SF2 Mappings werden jetzt in playoff_mapping._build_playoff_team_map_for_year() erstellt
        # if sf_game_numbers and len(sf_game_numbers) >= 2 and all(isinstance(item, int) for item in sf_game_numbers):
        #     playoff_team_map['SF1'] = str(sf_game_numbers[0])
        #     playoff_team_map['SF2'] = str(sf_game_numbers[1])

        # Initialisiere PlayoffResolver für die Auflösung von Team-Codes
        playoff_resolver = PlayoffResolver(year_obj, games_raw)
    
        # Verwende die zentrale get_resolved_code Methode des PlayoffResolver
        # mit Fallback auf die lokale playoff_team_map für spezielle Fälle
        def get_resolved_code(placeholder_code, current_map):
            # Prüfe zuerst die lokale Map (enthält ggf. aktuellere Daten)
            if placeholder_code in current_map:
                local_result = current_map[placeholder_code]
                # Wenn das lokale Ergebnis ein finaler Code ist, verwende es
                if local_result and len(local_result) == 3 and local_result.isalpha() and local_result.isupper():
                    return local_result
            
            # Für Platzhalter wie W(SF1), L(SF1), etc. müssen wir sicherstellen,
            # dass der PlayoffResolver die SF1/SF2 Mappings kennt
            if re.match(r"^[WL]\(SF[12]\)$", placeholder_code):
                # Extrahiere SF1 oder SF2
                match = re.match(r"^([WL])\((SF[12])\)$", placeholder_code)
                if match:
                    prefix = match.group(1)
                    sf_code = match.group(2)
                    # Hole die Spielnummer aus der lokalen Map
                    if sf_code in current_map:
                        game_num = current_map[sf_code]
                        # Erstelle den neuen Platzhalter mit der Spielnummer
                        new_placeholder = f"{prefix}({game_num})"
                        # Lasse den PlayoffResolver dies auflösen
                        return playoff_resolver.get_resolved_code(new_placeholder)
            
            # Ansonsten nutze den PlayoffResolver für die Auflösung
            resolver_result = playoff_resolver.get_resolved_code(placeholder_code)
            
            # Wenn der Resolver einen finalen Code zurückgibt, verwende ihn
            if resolver_result and len(resolver_result) == 3 and resolver_result.isalpha() and resolver_result.isupper():
                return resolver_result
            
            # Falls der Resolver keinen finalen Code liefert, prüfe nochmal die lokale Map
            # Dies ist wichtig für Zwischenschritte wie SF1/SF2 -> Spielnummern
            if placeholder_code in current_map:
                return current_map[placeholder_code]
            
            # Fallback: Gib das Ergebnis des Resolvers zurück (oder den ursprünglichen Code)
            return resolver_result

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
                        
                        # Check for custom seeding first
                        custom_seeding = get_custom_seeding_from_db(year_id)
                        
                        if custom_seeding:
                            # Use custom seeding - map seed1-seed4 directly to custom seed order
                            playoff_team_map['seed1'] = custom_seeding['seed1']
                            playoff_team_map['seed2'] = custom_seeding['seed2']
                            playoff_team_map['seed3'] = custom_seeding['seed3']
                            playoff_team_map['seed4'] = custom_seeding['seed4']
                            
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
                            playoff_team_map['seed1'] = sf_game1_teams[0]  # First team in SF1
                            playoff_team_map['seed4'] = sf_game1_teams[1]  # Second team in SF1
                            playoff_team_map['seed2'] = sf_game2_teams[0]  # First team in SF2
                            playoff_team_map['seed3'] = sf_game2_teams[1]  # Second team in SF2

        # --- FALLBACK seed1-seed4 MAPPING ---
        # If the full semifinal logic didn't run, try to map seed1-seed4 to available QF winners
        if qf_game_numbers and len(qf_game_numbers) == 4 and 'seed1' not in playoff_team_map:
            for i, qf_game_num in enumerate(qf_game_numbers):
                winner_placeholder = f'W({qf_game_num})'
                resolved_qf_winner = get_resolved_code(winner_placeholder, playoff_team_map)
                
                if is_code_final(resolved_qf_winner):
                    q_code = f'seed{i+1}'  # seed1, seed2, seed3, seed4
                    playoff_team_map[q_code] = resolved_qf_winner

        # --- BRONZE AND GOLD MEDAL GAME LOGIC ---
        # Handle Bronze Medal Game (losers of semifinals) and Gold Medal Game (winners of semifinals)
        if sf_game_numbers and len(sf_game_numbers) == 2 and bronze_game_number and gold_game_number:
            bronze_game_obj = games_dict_by_num.get(bronze_game_number)
            gold_game_obj = games_dict_by_num.get(gold_game_number)
            
            if bronze_game_obj and gold_game_obj:
                # Map SF1 and SF2 to actual game numbers
                sf1_game_number = sf_game_numbers[0]  # First semifinal game
                sf2_game_number = sf_game_numbers[1]  # Second semifinal game
                
                # SF1/SF2 Mappings werden bereits in playoff_mapping._build_playoff_team_map_for_year() erstellt
                # playoff_team_map['SF1'] = str(sf1_game_number)
                # playoff_team_map['SF2'] = str(sf2_game_number)
                
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

        # Perform a final resolution pass using the updated playoff_team_map
        for g_disp_final_pass in games_processed:
            # Resolve from original placeholder if current is still a placeholder, 
            # or re-resolve current if it might have been an intermediate placeholder.
            # Prioritizing original_teamX_code ensures we pick up changes from playoff_team_map like seed1->CAN directly.
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
            if time_sec <= PERIOD_1_END: period = 1
            elif time_sec <= PERIOD_2_END: period = 2
            elif time_sec <= PERIOD_3_END: period = 3

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
            if time_sec <= PERIOD_1_END: period_disp = "1st Period"
            elif time_sec <= PERIOD_2_END: period_disp = "2nd Period"
            elif time_sec <= PERIOD_3_END: period_disp = "3rd Period"
            
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
    
    except NotFoundError as e:
        current_app.logger.error(f"Game not found: {str(e)}")
        flash(f'Spiel nicht gefunden: {str(e)}', 'danger')
        return redirect(url_for('year_bp.year_view', year_id=year_id))
    except Exception as e:
        current_app.logger.error(f"Error in game_stats_view: {str(e)}")
        flash(f'Fehler beim Laden der Spielstatistiken: {str(e)}', 'danger')
        return redirect(url_for('year_bp.year_view', year_id=year_id)) 

@year_bp.route('/<int:year_id>/game/<int:game_id>/overrule', methods=['POST'])
def add_overrule(year_id, game_id):
    """Add or update an overrule for a game's score matching issue using GameService"""
    try:
        # Service Layer nutzen
        game_service = GameService()
        
        # Prüfung, ob das Spiel zum Jahr gehört
        game = game_service.get_by_id(game_id)
        if not game or game.year_id != year_id:
            return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404
        
        reason = request.form.get('reason', '').strip()
        
        # Service aufrufen
        overrule = game_service.add_overrule(game_id, reason)
        
        # Nachricht basierend darauf, ob es ein Update war
        message = 'Overrule-Grund erfolgreich aktualisiert!' if hasattr(overrule, 'id') else 'Overrule erfolgreich hinzugefügt!'
        
        return jsonify({
            'success': True, 
            'message': message,
            'overrule': {
                'reason': overrule.reason,
                'created_at': overrule.created_at.isoformat() if overrule.created_at else None
            }
        })
        
    except NotFoundError as e:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404
    except ValidationError as e:
        if e.field == 'reason':
            return jsonify({'success': False, 'message': 'Grund für Overrule muss angegeben werden.'}), 400
        return jsonify({'success': False, 'message': f'Validierungsfehler: {str(e)}'}), 400
    except Exception as e:
        current_app.logger.error(f"Error adding/updating overrule: {str(e)}")
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500

@year_bp.route('/<int:year_id>/game/<int:game_id>/overrule', methods=['DELETE'])
def remove_overrule(year_id, game_id):
    """Remove an overrule for a game using GameService"""
    try:
        # Service Layer nutzen
        game_service = GameService()
        
        # Prüfung, ob das Spiel zum Jahr gehört
        game = game_service.get_by_id(game_id)
        if not game or game.year_id != year_id:
            return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404
        
        # Service aufrufen
        removed = game_service.remove_overrule(game_id)
        
        if not removed:
            return jsonify({'success': False, 'message': 'Kein Overrule für dieses Spiel gefunden.'}), 404
        
        return jsonify({'success': True, 'message': 'Overrule erfolgreich entfernt!'})
        
    except NotFoundError as e:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404
    except Exception as e:
        current_app.logger.error(f"Error removing overrule: {str(e)}")
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500


# Neue Route mit Service Layer - Proof of Concept
@year_bp.route('/api/game/<int:game_id>/update-score', methods=['POST'])
def update_game_score_via_service(game_id):
    """
    Update game score using the GameService (Service Layer Implementation)
    Dies ist ein Proof of Concept für die Service Layer Architektur
    """
    try:
        # Service Layer nutzen statt direktem Datenbankzugriff
        game_service = GameService()
        
        # Daten aus Request holen
        data = request.get_json()
        team1_score = data.get('team1_score')
        team2_score = data.get('team2_score')
        result_type = data.get('result_type', 'REG')
        
        # Service aufrufen - alle Geschäftslogik ist im Service gekapselt
        updated_game = game_service.update_game_score(
            game_id=game_id,
            team1_score=team1_score,
            team2_score=team2_score,
            result_type=result_type
        )
        
        return jsonify({
            'success': True,
            'message': 'Spielstand erfolgreich aktualisiert!',
            'game': {
                'id': updated_game.id,
                'team1_score': updated_game.team1_score,
                'team2_score': updated_game.team2_score,
                'team1_points': updated_game.team1_points,
                'team2_points': updated_game.team2_points,
                'result_type': updated_game.result_type
            }
        })
        
    except NotFoundError as e:
        return jsonify({'success': False, 'message': str(e)}), 404
    except ValidationError as e:
        return jsonify({'success': False, 'message': f'Validierungsfehler: {str(e)}', 'field': e.field}), 400
    except BusinessRuleError as e:
        return jsonify({'success': False, 'message': f'Geschäftsregel verletzt: {str(e)}'}), 400
    except Exception as e:
        current_app.logger.error(f"Unerwarteter Fehler beim Update: {str(e)}")
        return jsonify({'success': False, 'message': 'Ein unerwarteter Fehler ist aufgetreten'}), 500


@year_bp.route('/api/game/<int:game_id>/sog', methods=['POST'])
def update_shots_on_goal_via_service(game_id):
    """
    Update shots on goal using the GameService (Service Layer Implementation)
    Dies demonstriert die Verwendung des Repository Patterns
    """
    try:
        # Service Layer nutzen
        game_service = GameService()
        
        # Daten aus Request
        data = request.get_json()
        sog_data = data.get('sog_data', {})
        
        # Service aufrufen
        result = game_service.add_shots_on_goal(game_id, sog_data)
        
        return jsonify({
            'success': True,
            'message': 'Shots on Goal erfolgreich aktualisiert!',
            'made_changes': result['made_changes'],
            'sog_data': result['sog_data'],
            'consistency': result['consistency']
        })
        
    except NotFoundError as e:
        return jsonify({'success': False, 'message': str(e)}), 404
    except ValidationError as e:
        return jsonify({'success': False, 'message': f'Validierungsfehler: {str(e)}'}), 400
    except Exception as e:
        current_app.logger.error(f"Fehler beim SOG Update: {str(e)}")
        return jsonify({'success': False, 'message': 'Ein Fehler ist aufgetreten'}), 500