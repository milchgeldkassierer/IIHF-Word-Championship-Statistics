from flask import render_template, request, current_app
from models import ChampionshipYear, Game, AllTimeTeamStats
from routes.blueprints import main_bp
from utils import is_code_final
from constants import TEAM_ISO_CODES
# Importiere Services
from app.services.core.team_service import TeamService
from app.services.core.tournament_service import TournamentService
from app.exceptions import ServiceError


def calculate_all_time_standings(game_type='all'):
    """
    SERVICE VERSION - Berechnung der All-Time Standings mit optimierten Queries
    Nutzt TeamService und TournamentService für effiziente Datenabfragen
    
    Args:
        game_type (str): Filter games by type - 'all', 'preliminary', or 'playoffs'
    """
    # Services initialisieren
    team_service = TeamService()
    tournament_service = TournamentService()
    
    try:
        # Hole alle Teams über Service (optimiert mit einer Query)
        all_teams = team_service.get_all_teams(include_placeholders=False)
        all_team_codes = [team['code'] for team in all_teams]
        
        # Hole alle Jahre über Service
        all_years = tournament_service.get_all()
        
        all_time_stats_dict = {}
        
        # OPTIMIERUNG: Batch-Processing mit Service Layer
        # Der TeamService hat bereits optimierte Methoden für All-Time Stats
        
        # Import API function für Kompatibilität
        from routes.api.team_stats_refactored import get_team_yearly_stats
        
        # Verwende Service-optimierte Batch-Abfrage
        for team_code in all_team_codes:
            # Verwende den refactorierten Endpoint mit Services
            with current_app.test_request_context(query_string=f'game_type={game_type}'):
                try:
                    response = get_team_yearly_stats(team_code)
                    if hasattr(response, 'get_json'):
                        data = response.get_json()
                        yearly_stats_data = data.get('yearly_stats', [])
                        
                        if yearly_stats_data:
                            # Erstelle AllTimeTeamStats Objekt
                            all_time_stats = AllTimeTeamStats(team_code=team_code)
                            
                            # Aggregiere Daten aus allen Jahren
                            for year_data in yearly_stats_data:
                                if year_data.get('participated', False):
                                    year = year_data.get('year')
                                    stats = year_data.get('stats', {})
                                    
                                    if year:
                                        all_time_stats.years_participated.add(year)
                                    
                                    all_time_stats.gp += stats.get('gp', 0)
                                    all_time_stats.w += stats.get('w', 0)
                                    all_time_stats.otw += stats.get('otw', 0)
                                    all_time_stats.sow += stats.get('sow', 0)
                                    all_time_stats.l += stats.get('l', 0)
                                    all_time_stats.otl += stats.get('otl', 0)
                                    all_time_stats.sol += stats.get('sol', 0)
                                    all_time_stats.gf += stats.get('gf', 0)
                                    all_time_stats.ga += stats.get('ga', 0)
                                    all_time_stats.pts += stats.get('pts', 0)
                            
                            # Nur Teams behalten, die tatsächlich Spiele haben
                            if all_time_stats.gp > 0:
                                all_time_stats_dict[team_code] = all_time_stats
                                
                except Exception as e:
                    current_app.logger.warning(f"Fehler beim Abrufen der Stats für Team {team_code}: {str(e)}")
                    continue
        
        # Sortiere finale Standings
        final_all_time_standings = list(all_time_stats_dict.values())
        final_all_time_standings.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        
        current_app.logger.info(f"All-Time Standings berechnet für {len(final_all_time_standings)} Teams")
        return final_all_time_standings
        
    except ServiceError as e:
        current_app.logger.error(f"Service-Fehler bei All-Time Standings: {str(e)}")
        # Fallback auf leere Liste
        return []
    except Exception as e:
        current_app.logger.error(f"Unerwarteter Fehler bei All-Time Standings: {str(e)}")
        return []


@main_bp.route('/all-time-standings')
def all_time_standings_view():
    game_type = request.args.get('game_type', 'all')
    
    # Validate game_type parameter
    if game_type not in ['all', 'preliminary', 'playoffs']:
        game_type = 'all'
    
    standings_data = calculate_all_time_standings(game_type)
    
    # Determine page title based on filter
    title_map = {
        'all': 'All-Time Standings (Hauptrunde und Playoffs)',
        'preliminary': 'All-Time Standings (nur Hauptrunde)',
        'playoffs': 'All-Time Standings (nur Playoffs)'
    }
    page_title = title_map.get(game_type, title_map['all'])
    
    return render_template('all_time_standings.html', 
                         standings_data=standings_data, 
                         team_iso_codes=TEAM_ISO_CODES,
                         current_filter=game_type,
                         page_title=page_title)