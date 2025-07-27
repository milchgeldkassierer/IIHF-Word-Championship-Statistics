from typing import Dict, Any
from models import db, ChampionshipYear, Game, Goal, Penalty
from sqlalchemy import func, case
from constants import PIM_MAP

# Import Service Layer
from app.services.core.tournament_service import TournamentService
from app.services.core.game_service import GameService
from app.exceptions import ServiceError

def calculate_overall_tournament_summary() -> Dict[str, Any]:
    """
    Berechnet die Gesamtstatistiken aller Turniere:
    - Gesamtanzahl der Spiele (eingetragen/gesamt)
    - Gesamtanzahl der Tore
    - Gesamtanzahl der Strafminuten (PIM)
    - Anzahl der Turniere
    """
    
    # Initialize Services
    tournament_service = TournamentService()
    game_service = GameService()
    
    try:
        # Alle Jahre/Turniere über Service abfragen
        all_years = tournament_service.get_all()
    except ServiceError:
        # Fallback auf direkte DB-Abfrage bei Service-Fehler
        all_years = ChampionshipYear.query.all()
    
    # Grundwerte initialisieren
    total_tournaments = len(all_years)
    total_games = 0
    completed_games = 0
    total_goals = 0
    total_penalties = 0
    total_penalty_count = 0
    
    # Für jedes Turnier die Statistiken sammeln
    for year in all_years:
        # Spiele für dieses Turnier - direkte DB-Abfrage für Performance
        games_in_year = Game.query.filter_by(year_id=year.id).all()
        year_total_games = len(games_in_year)
        year_completed_games = sum(1 for game in games_in_year 
                                 if game.team1_score is not None and game.team2_score is not None)
        
        total_games += year_total_games
        completed_games += year_completed_games
        
        # Tore für dieses Turnier (nur für abgeschlossene Spiele)
        completed_game_ids = [game.id for game in games_in_year 
                            if game.team1_score is not None and game.team2_score is not None]
        
        if completed_game_ids:
            # Tore direkt abfragen (kein spezifischer Service für diese Aggregation vorhanden)
            # TODO: Erwägen Sie, eine Methode in GameService für Gesamtstatistiken hinzuzufügen
            year_goals = Goal.query.filter(Goal.game_id.in_(completed_game_ids)).count()
            
            # Berechne tatsächliche Strafminuten (PIM)
            pim_case_statement = case(
                *[(Penalty.penalty_type == penalty_type, pim_value) for penalty_type, pim_value in PIM_MAP.items()],
                else_=2  # Default für unbekannte Straftypen
            )
            
            # Strafminuten direkt berechnen (komplexe Aggregation, kein Service vorhanden)
            # TODO: Erwägen Sie, eine Methode in GameService für PIM-Statistiken hinzuzufügen
            year_penalties = db.session.query(func.sum(pim_case_statement)).filter(
                Penalty.game_id.in_(completed_game_ids)
            ).scalar() or 0
            
            # Gesamtanzahl der Strafen direkt abfragen
            year_penalty_count = Penalty.query.filter(Penalty.game_id.in_(completed_game_ids)).count()
            
            total_goals += year_goals
            total_penalties += year_penalties
            total_penalty_count += year_penalty_count
    
    return {
        'total_tournaments': total_tournaments,
        'total_games': total_games,
        'completed_games': completed_games,
        'total_goals': total_goals,
        'total_penalties': total_penalties,
        'total_penalty_count': total_penalty_count,
        'completion_percentage': round((completed_games / total_games * 100) if total_games > 0 else 0, 1)
    }