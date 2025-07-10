import json
import os
import re
from flask import request, jsonify, current_app
from models import db, ChampionshipYear, Game, TeamStats, GameOverrule
from utils import _apply_head_to_head_tiebreaker, is_code_final
from routes.main_routes import resolve_fixture_path

# Import the blueprint from the parent package
from . import year_bp

def get_custom_seeding_from_db(year_id):
    """
    Lädt benutzerdefiniertes Seeding aus der Datenbank.
    
    Args:
        year_id (int): Championship year ID
        
    Returns:
        dict or None: Seeding configuration or None if not found
    """
    try:
        # Verwende GameOverrule Tabelle mit spezieller game_id für Semifinal Seeding
        special_game_id = -year_id  # Negative year_id für semifinal seeding
        
        overrule = GameOverrule.query.filter_by(game_id=special_game_id).first()
        if overrule and overrule.reason:
            try:
                return json.loads(overrule.reason)
            except:
                return None
        return None
    except Exception as e:
        current_app.logger.error(f"Error loading custom seeding: {str(e)}")
        return None

def save_custom_seeding_to_db(year_id, seeding):
    """
    Speichert benutzerdefiniertes Seeding in der Datenbank.
    
    Args:
        year_id (int): Championship year ID
        seeding (dict): Seeding configuration
    """
    try:
        # Verwende GameOverrule Tabelle mit spezieller game_id für Semifinal Seeding
        special_game_id = -year_id  # Negative year_id für semifinal seeding
        
        overrule = GameOverrule.query.filter_by(game_id=special_game_id).first()
        
        if overrule:
            overrule.reason = json.dumps(seeding)
        else:
            overrule = GameOverrule(
                game_id=special_game_id,
                reason=json.dumps(seeding)
            )
            db.session.add(overrule)
        
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error saving custom seeding: {str(e)}")
        db.session.rollback()
        raise


@year_bp.route('/<int:year_id>/semifinal_seeding', methods=['GET'])
def get_semifinal_seeding(year_id):
    """
    Gibt das aktuelle Semifinal-Seeding zurück.
    
    Returns:
        JSON: {
            "success": bool,
            "seeding": {
                "seed1": "team_name",
                "seed2": "team_name", 
                "seed3": "team_name",
                "seed4": "team_name"
            },
            "resolved_teams": [list of team names],
            "message": str
        }
    """
    try:
        year_obj = db.session.get(ChampionshipYear, year_id)
        if not year_obj:
            return jsonify({
                'success': False,
                'message': 'Tournament year not found.'
            }), 404

        # Games und playoff_team_map logic aus year_view wiederverwenden
        games_raw = Game.query.filter_by(year_id=year_id).order_by(Game.date, Game.start_time, Game.game_number).all()
        games_raw_map = {g.id: g for g in games_raw}
        
        # Preliminary Round Statistics für Seeding
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
        
        # Standings by group
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

        # Playoff team map
        playoff_team_map = {}
        for group_display_name, group_standings_list in standings_by_group.items():
            group_letter_match = re.match(r"Group ([A-D])", group_display_name) 
            if group_letter_match:
                group_letter = group_letter_match.group(1)
                for i, s_team_obj in enumerate(group_standings_list): 
                    playoff_team_map[f'{group_letter}{i+1}'] = s_team_obj.name 
        
        games_dict_by_num = {g.game_number: g for g in games_raw}
        
        # Fixture data für game numbers
        qf_game_numbers = []
        sf_game_numbers = []
        
        fixture_path_exists = False
        if year_obj.fixture_path:
            absolute_fixture_path = resolve_fixture_path(year_obj.fixture_path)
            fixture_path_exists = absolute_fixture_path and os.path.exists(absolute_fixture_path)

        if year_obj.fixture_path and fixture_path_exists:
            try:
                with open(absolute_fixture_path, 'r', encoding='utf-8') as f:
                    loaded_fixture_data = json.load(f)
                
                schedule_data = loaded_fixture_data.get("schedule", [])
                for game_data in schedule_data:
                    round_name = game_data.get("round", "").lower()
                    game_num = game_data.get("gameNumber")
                    
                    if "quarterfinal" in round_name: 
                        qf_game_numbers.append(game_num)
                    elif "semifinal" in round_name: 
                        sf_game_numbers.append(game_num)
                sf_game_numbers.sort()
            except Exception as e: 
                current_app.logger.error(f"Could not parse fixture {year_obj.fixture_path}. Error: {e}") 
                if year_obj.year == 2025: 
                    qf_game_numbers = [57, 58, 59, 60]
                    sf_game_numbers = [61, 62]

        # Get resolved code function (simplified version)
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
                            new_placeholder = current_code.replace(inner_placeholder, resolved_inner)
                            if new_placeholder == current_code:
                                return current_code 
                            current_code = new_placeholder
                    else:
                        return current_code 
                else:
                    return current_code 
            return current_code

        # Quarterfinal winners logic
        qf_winners_teams = []
        all_qf_winners_resolved = True
        
        if qf_game_numbers and len(qf_game_numbers) == 4:
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
                    # Standard IIHF seeding: bester gegen schlechtesten, zweibester gegen zweitschlechtesten
                    qf_winners_stats.sort(key=lambda s: (s.rank_in_group, -s.pts, -s.gd, -s.gf))
                    
                    # Check for custom seeding in database
                    custom_seeding = get_custom_seeding_from_db(year_id)
                    
                    if custom_seeding:
                        # Use custom seeding
                        seeding = custom_seeding
                    else:
                        # Use standard seeding
                        seeding = {
                            'seed1': qf_winners_stats[0].name,  # Bester Seed
                            'seed2': qf_winners_stats[1].name,  # Zweitbester Seed  
                            'seed3': qf_winners_stats[2].name,  # Drittbester Seed
                            'seed4': qf_winners_stats[3].name   # Schlechtester Seed
                        }
                    
                    return jsonify({
                        'success': True,
                        'seeding': seeding,
                        'resolved_teams': [team.name for team in qf_winners_stats],
                        'message': 'Seeding erfolgreich geladen.'
                    })

        return jsonify({
            'success': False,
            'message': 'Semifinals stehen noch nicht fest - nicht alle Quarterfinal-Sieger sind bekannt.',
            'seeding': {},
            'resolved_teams': []
        })

    except Exception as e:
        current_app.logger.error(f"Error getting semifinal seeding: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Fehler beim Laden des Seedings: {str(e)}'
        }), 500


@year_bp.route('/<int:year_id>/semifinal_seeding', methods=['POST'])
def save_semifinal_seeding(year_id):
    """
    Speichert eine angepasste Semifinal-Seeding Konfiguration.
    
    Expected JSON:
    {
        "seeding": {
            "seed1": "team_name",
            "seed2": "team_name",
            "seed3": "team_name", 
            "seed4": "team_name"
        }
    }
    
    Returns:
        JSON: {
            "success": bool,
            "message": str
        }
    """
    try:
        year_obj = db.session.get(ChampionshipYear, year_id)
        if not year_obj:
            return jsonify({
                'success': False,
                'message': 'Tournament year not found.'
            }), 404

        data = request.get_json()
        if not data or 'seeding' not in data:
            return jsonify({
                'success': False,
                'message': 'Seeding data required.'
            }), 400

        seeding = data['seeding']
        required_seeds = ['seed1', 'seed2', 'seed3', 'seed4']
        
        # Validate seeding data
        for seed in required_seeds:
            if seed not in seeding or not seeding[seed]:
                return jsonify({
                    'success': False,
                    'message': f'Fehlender oder leerer Wert für {seed}.'
                }), 400

        # Check for duplicates
        team_names = [seeding[seed] for seed in required_seeds]
        if len(set(team_names)) != 4:
            return jsonify({
                'success': False,
                'message': 'Doppelte Team-Zuweisungen sind nicht erlaubt.'
            }), 400

        # Save custom seeding to database
        save_custom_seeding_to_db(year_id, seeding)

        return jsonify({
            'success': True,
            'message': 'Semifinal-Seeding erfolgreich gespeichert.'
        })

    except Exception as e:
        current_app.logger.error(f"Error saving semifinal seeding: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Fehler beim Speichern des Seedings: {str(e)}'
        }), 500


@year_bp.route('/<int:year_id>/semifinal_seeding', methods=['DELETE'])
def reset_semifinal_seeding(year_id):
    """
    Setzt das Semifinal-Seeding auf die Standard IIHF-Regeln zurück.
    
    Returns:
        JSON: {
            "success": bool,
            "message": str
        }
    """
    try:
        year_obj = db.session.get(ChampionshipYear, year_id)
        if not year_obj:
            return jsonify({
                'success': False,
                'message': 'Tournament year not found.'
            }), 404

        # Remove custom seeding from database
        special_game_id = -year_id
        overrule = GameOverrule.query.filter_by(game_id=special_game_id).first()
        if overrule:
            db.session.delete(overrule)
            db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Semifinal-Seeding erfolgreich auf Standard-Regeln zurückgesetzt.'
        })

    except Exception as e:
        current_app.logger.error(f"Error resetting semifinal seeding: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Fehler beim Zurücksetzen des Seedings: {str(e)}'
        }), 500