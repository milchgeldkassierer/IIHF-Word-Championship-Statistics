from typing import Dict, Any
from models import db, ChampionshipYear, Game, Goal, Penalty
from sqlalchemy import func

def calculate_overall_tournament_summary() -> Dict[str, Any]:
    """
    Berechnet die Gesamtstatistiken aller Turniere:
    - Gesamtanzahl der Spiele (eingetragen/gesamt)
    - Gesamtanzahl der Tore
    - Gesamtanzahl der Penalties
    - Anzahl der Turniere
    """
    
    # Alle Jahre/Turniere abfragen
    all_years = ChampionshipYear.query.all()
    
    # Grundwerte initialisieren
    total_tournaments = len(all_years)
    total_games = 0
    completed_games = 0
    total_goals = 0
    total_penalties = 0
    
    # Für jedes Turnier die Statistiken sammeln
    for year in all_years:
        # Spiele für dieses Turnier
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
            year_goals = Goal.query.filter(Goal.game_id.in_(completed_game_ids)).count()
            year_penalties = Penalty.query.filter(Penalty.game_id.in_(completed_game_ids)).count()
            
            total_goals += year_goals
            total_penalties += year_penalties
    
    return {
        'total_tournaments': total_tournaments,
        'total_games': total_games,
        'completed_games': completed_games,
        'total_goals': total_goals,
        'total_penalties': total_penalties,
        'completion_percentage': round((completed_games / total_games * 100) if total_games > 0 else 0, 1)
    }

def get_detailed_tournament_stats(year_obj) -> Dict[str, Any]:
    """
    Erweiterte Statistiken für ein einzelnes Turnier
    """
    if not year_obj:
        return {
            'total_games': 0,
            'completed_games': 0,
            'goals': 0,
            'penalties': 0
        }
    
    # Spiele für dieses Turnier
    games_in_year = Game.query.filter_by(year_id=year_obj.id).all()
    total_games = len(games_in_year)
    
    completed_games = [game for game in games_in_year 
                      if game.team1_score is not None and game.team2_score is not None]
    completed_games_count = len(completed_games)
    
    # Tore und Penalties nur für abgeschlossene Spiele
    if completed_games:
        completed_game_ids = [game.id for game in completed_games]
        goals_count = Goal.query.filter(Goal.game_id.in_(completed_game_ids)).count()
        penalties_count = Penalty.query.filter(Penalty.game_id.in_(completed_game_ids)).count()
    else:
        goals_count = 0
        penalties_count = 0
    
    return {
        'total_games': total_games,
        'completed_games': completed_games_count,
        'goals': goals_count,
        'penalties': penalties_count
    } 