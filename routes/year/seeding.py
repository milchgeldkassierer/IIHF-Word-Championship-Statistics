import json
import os
import re
from flask import request, jsonify, current_app
from models import db, ChampionshipYear, Game, TeamStats, GameOverrule
from utils import _apply_head_to_head_tiebreaker, is_code_final
from utils.fixture_helpers import resolve_fixture_path
from utils.playoff_resolver import PlayoffResolver
from app.services.core.tournament_service import TournamentService
from app.services.core.game_service import GameService
from app.services.core.standings_service import StandingsService
from app.exceptions import NotFoundError, ValidationError, ServiceError

# Import the blueprint from the parent package
from . import year_bp

def get_custom_seeding_from_db(year_id, include_reason=False):
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
                data = json.loads(overrule.reason)
                # Handle both old format (just seeding) and new format (seeding + reason)
                if isinstance(data, dict) and 'seeding' in data:
                    # New format
                    if include_reason:
                        return {'seeding': data['seeding'], 'reason': data.get('reason', '')}
                    else:
                        return data['seeding']
                else:
                    # Old format (backward compatibility)
                    if include_reason:
                        return {'seeding': data, 'reason': ''}
                    else:
                        return data
            except:
                return None
        return None
    except Exception as e:
        current_app.logger.error(f"Error loading custom seeding: {str(e)}")
        return None

def save_custom_seeding_to_db(year_id, seeding, reason=None):
    """
    Speichert benutzerdefiniertes Seeding in der Datenbank.
    
    Args:
        year_id (int): Championship year ID
        seeding (dict): Seeding configuration
        reason (str, optional): Grund für die Seeding-Änderung
    """
    try:
        # Verwende GameOverrule Tabelle mit spezieller game_id für Semifinal Seeding
        special_game_id = -year_id  # Negative year_id für semifinal seeding
        
        overrule = GameOverrule.query.filter_by(game_id=special_game_id).first()
        
        # Combine seeding and reason data
        data_to_store = {
            'seeding': seeding,
            'reason': reason
        }
        
        if overrule:
            overrule.reason = json.dumps(data_to_store)
        else:
            overrule = GameOverrule(
                game_id=special_game_id,
                reason=json.dumps(data_to_store)
            )
            db.session.add(overrule)
        
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error saving custom seeding: {str(e)}")
        db.session.rollback()
        raise


def get_custom_qf_seeding_from_db(year_id, include_reason=False):
    """
    Lädt benutzerdefiniertes Quarterfinal-Seeding aus der Datenbank.
    
    Args:
        year_id (int): Championship year ID
        include_reason (bool): If True, returns both seeding and reason
        
    Returns:
        dict or None: QF seeding configuration or None if not found
        If include_reason=True, returns dict with 'seeding' and 'reason' keys
    """
    try:
        # Verwende GameOverrule Tabelle mit spezieller game_id für QF Seeding
        special_game_id = -(year_id + 1000)  # Negative (year_id + 1000) für QF seeding
        
        overrule = GameOverrule.query.filter_by(game_id=special_game_id).first()
        if overrule and overrule.reason:
            try:
                data = json.loads(overrule.reason)
                # Handle both old format (just seeding) and new format (seeding + reason)
                if isinstance(data, dict) and 'seeding' in data:
                    # New format
                    if include_reason:
                        return {'seeding': data['seeding'], 'reason': data.get('reason', '')}
                    else:
                        return data['seeding']
                else:
                    # Old format (backward compatibility)
                    if include_reason:
                        return {'seeding': data, 'reason': ''}
                    else:
                        return data
            except:
                return None
        return None
    except Exception as e:
        current_app.logger.error(f"Error loading custom QF seeding: {str(e)}")
        return None


def save_custom_qf_seeding_to_db(year_id, seeding, reason=None):
    """
    Speichert benutzerdefiniertes Quarterfinal-Seeding in der Datenbank.
    
    Args:
        year_id (int): Championship year ID
        seeding (dict): QF seeding configuration
        reason (str, optional): Grund für die Seeding-Änderung
    """
    try:
        # Verwende GameOverrule Tabelle mit spezieller game_id für QF Seeding
        special_game_id = -(year_id + 1000)  # Negative (year_id + 1000) für QF seeding
        
        overrule = GameOverrule.query.filter_by(game_id=special_game_id).first()
        
        # Combine seeding and reason data
        data_to_store = {
            'seeding': seeding,
            'reason': reason
        }
        
        if overrule:
            overrule.reason = json.dumps(data_to_store)
        else:
            overrule = GameOverrule(
                game_id=special_game_id,
                reason=json.dumps(data_to_store)
            )
            db.session.add(overrule)
        
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error saving custom QF seeding: {str(e)}")
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
        # Service-Layer verwenden
        tournament_service = TournamentService()
        try:
            year_obj = tournament_service.get_by_id(year_id)
        except NotFoundError:
            return jsonify({
                'success': False,
                'message': 'Tournament year not found.'
            }), 404

        # Service-Layer für Spiele verwenden
        game_service = GameService()
        games_raw = game_service.get_by_tournament(year_id)
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

        # Verwende StandingsCalculator für die Berechnung der Teamstatistiken
        from services.standings_calculator_adapter import StandingsCalculator
        calculator = StandingsCalculator()
        teams_stats = calculator.calculate_standings_from_games(
            [pg for pg in prelim_games if pg.team1_score is not None]
        )
        
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
        
        # Check for custom QF seeding and apply if exists
        custom_qf_seeding = get_custom_qf_seeding_from_db(year_id)
        if custom_qf_seeding:
            # Override standard group position mappings with custom seeding
            for position, team_name in custom_qf_seeding.items():
                playoff_team_map[position] = team_name
        
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

        # Erstelle PlayoffResolver-Instanz für Team-Code-Auflösung
        resolver = PlayoffResolver(year_obj, games_raw)

        # Quarterfinal winners logic
        qf_winners_teams = []
        all_qf_winners_resolved = True
        
        if qf_game_numbers and len(qf_game_numbers) == 4:
            for qf_game_num in qf_game_numbers:
                winner_placeholder = f'W({qf_game_num})'
                resolved_qf_winner = resolver.get_resolved_code(winner_placeholder)

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
                        resolved_teams = list(custom_seeding.values())
                    else:
                        # Use standard seeding
                        seeding = {
                            'seed1': qf_winners_stats[0].name,  # Bester Seed
                            'seed2': qf_winners_stats[1].name,  # Zweitbester Seed  
                            'seed3': qf_winners_stats[2].name,  # Drittbester Seed
                            'seed4': qf_winners_stats[3].name   # Schlechtester Seed
                        }
                        resolved_teams = [team.name for team in qf_winners_stats]
                    
                    return jsonify({
                        'success': True,
                        'seeding': seeding,
                        'resolved_teams': resolved_teams,
                        'message': 'Seeding erfolgreich geladen.'
                    })

        # If QF winners are not all resolved, check for custom seeding anyway
        custom_seeding = get_custom_seeding_from_db(year_id)
        if custom_seeding:
            return jsonify({
                'success': True,
                'seeding': custom_seeding,
                'resolved_teams': list(custom_seeding.values()),
                'message': 'Benutzerdefiniertes Seeding geladen.'
            })
        
        # If no custom seeding and QF not resolved, use available QF teams or all teams
        available_teams = qf_winners_teams if qf_winners_teams else []
        if not available_teams:
            # Fallback: use all teams from group standings (top 4 from each group)
            for group_name, teams in standings_by_group.items():
                available_teams.extend([team.name for team in teams[:4]])
        
        # Provide empty seeding structure with available teams
        return jsonify({
            'success': True,
            'seeding': {},
            'resolved_teams': available_teams[:8] if available_teams else [],
            'message': 'Seeding kann angepasst werden.'
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
        # Service-Layer verwenden
        tournament_service = TournamentService()
        try:
            year_obj = tournament_service.get_by_id(year_id)
        except NotFoundError:
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
        reason = data.get('reason', '')  # Optional reason field
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
        save_custom_seeding_to_db(year_id, seeding, reason)

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
        # Service-Layer verwenden
        tournament_service = TournamentService()
        try:
            year_obj = tournament_service.get_by_id(year_id)
        except NotFoundError:
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


@year_bp.route('/<int:year_id>/quarterfinal_seeding', methods=['GET'])
def get_quarterfinal_seeding(year_id):
    """
    Gibt das aktuelle Quarterfinal-Seeding zurück.
    
    Returns:
        JSON: {
            "success": bool,
            "seeding": {
                "A1": "team_name",
                "A2": "team_name",
                "A3": "team_name", 
                "A4": "team_name",
                "B1": "team_name",
                "B2": "team_name",
                "B3": "team_name",
                "B4": "team_name"
            },
            "group_standings": {
                "Group A": [list of teams in order],
                "Group B": [list of teams in order]
            },
            "message": str
        }
    """
    try:
        # Service-Layer verwenden
        tournament_service = TournamentService()
        try:
            year_obj = tournament_service.get_by_id(year_id)
        except NotFoundError:
            return jsonify({
                'success': False,
                'message': 'Tournament year not found.'
            }), 404

        # Service-Layer für Spiele verwenden
        game_service = GameService()
        games_raw = game_service.get_by_tournament(year_id)
        
        # Preliminary Round Statistics
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

        # Calculate team statistics
        # Verwende StandingsCalculator für die Berechnung der Teamstatistiken
        from services.standings_calculator_adapter import StandingsCalculator
        calculator = StandingsCalculator()
        teams_stats = calculator.calculate_standings_from_games(
            [pg for pg in prelim_games if pg.team1_score is not None]
        )
        
        # Get standings by group
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

        # No restrictions - seeding can be changed at any time

        # Build group standings for response
        group_standings = {}
        for group_name, teams in standings_by_group.items():
            group_standings[group_name] = [team.name for team in teams]

        # Check for custom seeding
        custom_seeding = get_custom_qf_seeding_from_db(year_id)
        
        if custom_seeding:
            # Return custom seeding
            return jsonify({
                'success': True,
                'seeding': custom_seeding,
                'group_standings': group_standings,
                'message': 'Benutzerdefiniertes Seeding geladen.'
            })
        else:
            # Build standard seeding based on group standings
            seeding = {}
            
            # Group A seeding
            group_a_teams = standings_by_group.get('Group A', [])
            for i, team in enumerate(group_a_teams[:4]):
                seeding[f'A{i+1}'] = team.name
                
            # Group B seeding  
            group_b_teams = standings_by_group.get('Group B', [])
            for i, team in enumerate(group_b_teams[:4]):
                seeding[f'B{i+1}'] = team.name
            
            return jsonify({
                'success': True,
                'seeding': seeding,
                'group_standings': group_standings,
                'message': 'Standard-Seeding basierend auf Gruppenergebnissen.'
            })

    except Exception as e:
        current_app.logger.error(f"Error getting quarterfinal seeding: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Fehler beim Laden des QF-Seedings: {str(e)}'
        }), 500


@year_bp.route('/<int:year_id>/quarterfinal_seeding', methods=['POST'])
def save_quarterfinal_seeding(year_id):
    """
    Speichert eine angepasste Quarterfinal-Seeding Konfiguration.
    
    Expected JSON:
    {
        "seeding": {
            "A1": "team_name",
            "A2": "team_name", 
            "A3": "team_name",
            "A4": "team_name",
            "B1": "team_name",
            "B2": "team_name",
            "B3": "team_name", 
            "B4": "team_name"
        }
    }
    
    Returns:
        JSON: {
            "success": bool,
            "message": str
        }
    """
    try:
        # Service-Layer verwenden
        tournament_service = TournamentService()
        try:
            year_obj = tournament_service.get_by_id(year_id)
        except NotFoundError:
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
        reason = data.get('reason', '')  # Optional reason field
        required_positions = ['A1', 'A2', 'A3', 'A4', 'B1', 'B2', 'B3', 'B4']
        
        # Validate seeding data
        for pos in required_positions:
            if pos not in seeding or not seeding[pos]:
                return jsonify({
                    'success': False,
                    'message': f'Fehlender oder leerer Wert für {pos}.'
                }), 400

        # Check for duplicates
        team_names = [seeding[pos] for pos in required_positions]
        if len(set(team_names)) != 8:
            return jsonify({
                'success': False,
                'message': 'Doppelte Team-Zuweisungen sind nicht erlaubt.'
            }), 400

        # Save custom seeding to database
        save_custom_qf_seeding_to_db(year_id, seeding, reason)

        return jsonify({
            'success': True,
            'message': 'Quarterfinal-Seeding erfolgreich gespeichert.'
        })

    except Exception as e:
        current_app.logger.error(f"Error saving quarterfinal seeding: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Fehler beim Speichern des QF-Seedings: {str(e)}'
        }), 500


@year_bp.route('/<int:year_id>/quarterfinal_seeding', methods=['DELETE'])
def reset_quarterfinal_seeding(year_id):
    """
    Setzt das Quarterfinal-Seeding auf die Standard-Gruppenergebnisse zurück.
    
    Returns:
        JSON: {
            "success": bool,
            "message": str
        }
    """
    try:
        # Service-Layer verwenden
        tournament_service = TournamentService()
        try:
            year_obj = tournament_service.get_by_id(year_id)
        except NotFoundError:
            return jsonify({
                'success': False,
                'message': 'Tournament year not found.'
            }), 404

        # Remove custom seeding from database
        special_game_id = -(year_id + 1000)
        overrule = GameOverrule.query.filter_by(game_id=special_game_id).first()
        if overrule:
            db.session.delete(overrule)
            db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Quarterfinal-Seeding erfolgreich auf Standard-Gruppenergebnisse zurückgesetzt.'
        })

    except Exception as e:
        current_app.logger.error(f"Error resetting quarterfinal seeding: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Fehler beim Zurücksetzen des QF-Seedings: {str(e)}'
        }), 500


@year_bp.route('/<int:year_id>/semifinal_seeding/status', methods=['GET'])
def get_semifinal_seeding_status(year_id):
    """
    Überprüft, ob benutzerdefiniertes Semifinal-Seeding existiert und gibt den Grund zurück.
    
    Returns:
        JSON: {
            "has_custom_seeding": bool,
            "reason": str or None
        }
    """
    try:
        custom_data = get_custom_seeding_from_db(year_id, include_reason=True)
        
        if custom_data:
            return jsonify({
                'has_custom_seeding': True,
                'reason': custom_data.get('reason', '') if isinstance(custom_data, dict) else ''
            })
        else:
            return jsonify({
                'has_custom_seeding': False,
                'reason': None
            })
    except Exception as e:
        current_app.logger.error(f"Error checking semifinal seeding status: {str(e)}")
        return jsonify({
            'has_custom_seeding': False,
            'reason': None
        }), 500


@year_bp.route('/<int:year_id>/quarterfinal_seeding/status', methods=['GET'])
def get_quarterfinal_seeding_status(year_id):
    """
    Überprüft, ob benutzerdefiniertes Quarterfinal-Seeding existiert und gibt den Grund zurück.
    
    Returns:
        JSON: {
            "has_custom_seeding": bool,
            "reason": str or None
        }
    """
    try:
        custom_data = get_custom_qf_seeding_from_db(year_id, include_reason=True)
        
        if custom_data:
            return jsonify({
                'has_custom_seeding': True,
                'reason': custom_data.get('reason', '') if isinstance(custom_data, dict) else ''
            })
        else:
            return jsonify({
                'has_custom_seeding': False,
                'reason': None
            })
    except Exception as e:
        current_app.logger.error(f"Error checking quarterfinal seeding status: {str(e)}")
        return jsonify({
            'has_custom_seeding': False,
            'reason': None
        }), 500