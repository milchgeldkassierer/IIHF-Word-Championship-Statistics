import os
import json
from flask import render_template, current_app
from models import db, ChampionshipYear, Game, TeamStats
from routes.blueprints import main_bp
# Import function locally to avoid circular imports
from utils import is_code_final, get_resolved_team_code, _apply_head_to_head_tiebreaker
from utils.fixture_helpers import resolve_fixture_path
from utils.standings import calculate_complete_final_ranking
from constants import TEAM_ISO_CODES, PRELIM_ROUNDS, PLAYOFF_ROUNDS
# Importiere Services
from app.services.core.tournament_service import TournamentService
from app.services.core.standings_service import StandingsService
from app.services.core.game_service import GameService
from app.exceptions import ServiceError


def get_medal_tally_data():
    """
    SERVICE VERSION - Optimierte Medal Tally Berechnung mit Service Layer
    Reduziert Queries drastisch durch Batch-Loading und Service-Optimierungen
    """
    # Services initialisieren
    tournament_service = TournamentService()
    standings_service = StandingsService()
    game_service = GameService()
    
    medal_tally_results = []
    
    try:
        # Hole alle Jahre über Service (eine Query)
        all_years = tournament_service.get_all()
        
        # Filtere nur abgeschlossene Jahre
        completed_years = []
        for year_obj in all_years:
            try:
                # Verwende Service für Tournament-Statistiken
                tournament_stats = tournament_service.get_tournament_statistics(year_obj.id)
                is_completed = (tournament_stats['total_games'] > 0 and 
                               tournament_stats['completed_games'] == tournament_stats['total_games'])
                if is_completed:
                    completed_years.append(year_obj)
            except:
                continue
        
        current_app.logger.info(f"Berechne Medal Tally für {len(completed_years)} abgeschlossene Turniere")
        
        # OPTIMIERUNG: Batch-Load alle Spiele für alle Jahre auf einmal
        # Statt N Queries (eins pro Jahr) nur eine Query
        year_ids = [y.id for y in completed_years]
        all_games_batch = game_service.get_games_for_years(year_ids)
        
        # Gruppiere Spiele nach Jahr
        games_by_year_id = {}
        for game in all_games_batch:
            games_by_year_id.setdefault(game.year_id, []).append(game)
        
        # Berechne Medal Rankings für jedes Jahr
        for year_obj in completed_years:
            year_id = year_obj.id
            
            try:
                # Verwende StandingsService für finale Platzierungen
                # Der Service hat bereits alle Optimierungen implementiert
                final_ranking = standings_service.calculate_final_tournament_ranking(year_id)
                
                # Extrahiere Medaillengewinner
                gold = final_ranking.get(1)
                silver = final_ranking.get(2)
                bronze = final_ranking.get(3)
                fourth = final_ranking.get(4)
                
                medal_tally_results.append({
                    'year_obj': year_obj,
                    'final_ranking': final_ranking,
                    'gold': gold,
                    'silver': silver,
                    'bronze': bronze,
                    'fourth': fourth
                })
                
            except ServiceError as e:
                current_app.logger.error(f"Service-Fehler für Jahr {year_obj.year}: {str(e)}")
                # Füge Jahr ohne Medaillen hinzu
                medal_tally_results.append({
                    'year_obj': year_obj,
                    'final_ranking': {},
                    'gold': None,
                    'silver': None,
                    'bronze': None,
                    'fourth': None
                })
            except Exception as e:
                current_app.logger.error(f"Fehler beim Berechnen der Medaillen für Jahr {year_obj.year}: {str(e)}")
                import traceback
                current_app.logger.error(traceback.format_exc())
                # Füge Jahr ohne Medaillen hinzu
                medal_tally_results.append({
                    'year_obj': year_obj,
                    'final_ranking': {},
                    'gold': None,
                    'silver': None,
                    'bronze': None,
                    'fourth': None
                })
        
        # Sortiere nach Jahr (neueste zuerst)
        medal_tally_results.sort(key=lambda x: x['year_obj'].year, reverse=True)
        
        current_app.logger.info(f"Medal Tally erfolgreich berechnet für {len(medal_tally_results)} Jahre")
        return medal_tally_results
        
    except Exception as e:
        current_app.logger.error(f"Kritischer Fehler bei Medal Tally Berechnung: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return []


@main_bp.route('/medal-tally')
def medal_tally_view():
    """Medal Tally View mit Service-optimierter Berechnung"""
    medal_data = get_medal_tally_data()
    return render_template('medal_tally.html', medal_data=medal_data, team_iso_codes=TEAM_ISO_CODES)