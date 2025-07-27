from collections import defaultdict
from models import db, Game, ChampionshipYear, Penalty
from sqlalchemy import func, case, desc, asc
from utils import is_code_final
from utils.data_validation import calculate_tournament_penalty_minutes
from constants import TOP_3_DISPLAY
from .utils import get_all_resolved_games


# Helper-Funktionen für Validierung
def is_valid_gold_medal_game(game):
    """
    Prüft, ob ein Spiel ein gültiges Gold Medal Game ist.
    
    Args:
        game: Das zu prüfende Spiel-Objekt
        
    Returns:
        bool: True wenn es ein Gold Medal Game mit gültigen Scores ist
    """
    return (game.round and 
            game.round == 'Gold Medal Game' and
            game.team1_score is not None and 
            game.team2_score is not None)


def are_teams_valid(team1_code, team2_code):
    """
    Prüft, ob beide Team-Codes gültig und unterschiedlich sind.
    
    Args:
        team1_code: Code des ersten Teams
        team2_code: Code des zweiten Teams
        
    Returns:
        bool: True wenn beide Codes final und unterschiedlich sind
    """
    return (is_code_final(team1_code) and 
            is_code_final(team2_code) and
            team1_code != team2_code)


def determine_winner(game, team1_code, team2_code):
    """
    Bestimmt den Gewinner eines Spiels basierend auf den Scores.
    
    Args:
        game: Das Spiel-Objekt mit Scores
        team1_code: Code des ersten Teams
        team2_code: Code des zweiten Teams
        
    Returns:
        str or None: Team-Code des Gewinners oder None bei Unentschieden
    """
    if game.team1_score > game.team2_score:
        return team1_code
    elif game.team2_score > game.team1_score:
        return team2_code
    else:
        return None  # Unentschieden


def is_tournament_completed(tournament_stats):
    """
    Prüft, ob ein Turnier abgeschlossen ist.
    
    Args:
        tournament_stats: Dictionary mit Turnierstatistiken
        
    Returns:
        bool: True wenn alle Spiele des Turniers abgeschlossen sind
    """
    return (tournament_stats['total_games'] > 0 and 
            tournament_stats['completed_games'] == tournament_stats['total_games'])


def get_most_consecutive_tournament_wins():
    """Findet die meisten Turniersiege in Folge basierend auf Gold Medal Game Gewinnern"""
    resolved_games = get_all_resolved_games()
    
    tournament_winners = []
    year_winners = {}
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        # Verwende Helper-Funktionen für Validierung
        if not is_valid_gold_medal_game(game):
            continue
            
        if not are_teams_valid(team1_code, team2_code):
            continue
            
        if not year:
            continue
        
        # Bestimme Gewinner mit Helper-Funktion
        winner = determine_winner(game, team1_code, team2_code)
        if winner:
            year_winners[year] = winner
    
    sorted_years = sorted(year_winners.keys())
    
    team_current_streak = defaultdict(int)
    team_current_years = defaultdict(list)
    team_max_streak = defaultdict(int)
    team_max_streak_years = defaultdict(list)
    
    for year in sorted_years:
        winner = year_winners[year]
        
        for team in team_current_streak:
            if team != winner:
                team_current_streak[team] = 0
                team_current_years[team] = []
        
        team_current_streak[winner] += 1
        team_current_years[winner].append(year)
        
        if team_current_streak[winner] > team_max_streak[winner]:
            team_max_streak[winner] = team_current_streak[winner]
            team_max_streak_years[winner] = team_current_years[winner][:]
    
    if not team_max_streak:
        return []
    
    max_streak = max(team_max_streak.values())
    results = []
    
    for team, streak in team_max_streak.items():
        if streak == max_streak:
            years = team_max_streak_years[team]
            results.append({
                'team': team, 
                'streak': streak,
                'years': years
            })
    
    return results


def get_most_final_appearances():
    """Berechnet die meisten Finalteilnahmen basierend auf echten Gold Medal Games"""
    resolved_games = get_all_resolved_games()
    team_final_appearances = defaultdict(int)
    team_final_years = defaultdict(list)
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        # Verwende Helper-Funktionen für Validierung
        if not is_valid_gold_medal_game(game):
            continue
            
        if not are_teams_valid(team1_code, team2_code):
            continue
        
        # Teams in Finalteilnahmen zählen
        team_final_appearances[team1_code] += 1
        team_final_appearances[team2_code] += 1
        
        # Jahre speichern wenn vorhanden
        if year:
            team_final_years[team1_code].append(year)
            team_final_years[team2_code].append(year)
    
    if not team_final_appearances:
        return []
    
    # Sort teams by appearances (descending) and return top 3
    sorted_teams = sorted(team_final_appearances.items(), key=lambda x: x[1], reverse=True)
    results = []
    
    for team, appearances in sorted_teams[:TOP_3_DISPLAY]:
        years = sorted(list(set(team_final_years[team]))) if team in team_final_years else []
        results.append({
            'team': team, 
            'appearances': appearances,
            'years': years
        })
    
    return results


def get_record_champion():
    """Berechnet das Team mit den meisten Turniersiegen (Gold Medal Game Gewinner)"""
    resolved_games = get_all_resolved_games()
    team_championships = defaultdict(int)
    team_championship_years = defaultdict(list)
    
    for resolved_game in resolved_games:
        game = resolved_game['game']
        team1_code = resolved_game['team1_code']
        team2_code = resolved_game['team2_code']
        year = resolved_game['year']
        
        # Verwende Helper-Funktionen für Validierung
        if not is_valid_gold_medal_game(game):
            continue
            
        if not are_teams_valid(team1_code, team2_code):
            continue
        
        # Bestimme Gewinner mit Helper-Funktion
        winner = determine_winner(game, team1_code, team2_code)
        if not winner:
            continue
        
        # Meisterschaft zählen
        team_championships[winner] += 1
        if year:
            team_championship_years[winner].append(year)
    
    if not team_championships:
        return []
    
    # Sort teams by championships (descending) and return top 3
    sorted_teams = sorted(team_championships.items(), key=lambda x: x[1], reverse=True)
    results = []
    
    for team, championships in sorted_teams[:TOP_3_DISPLAY]:
        years = sorted(team_championship_years[team]) if team in team_championship_years else []
        results.append({
            'team': team, 
            'championships': championships,
            'years': years
        })
    
    return results


def get_tournament_metric_extremes(metric_type='goals', order='desc'):
    """Generische Funktion für Turnier-Metriken (meiste/wenigste)
    
    Args:
        metric_type: 'goals' oder 'penalties'
        order: 'desc' für meiste, 'asc' für wenigste
    """
    from .utils import get_tournament_statistics
    
    # Hole nur abgeschlossene Turniere
    all_years = db.session.query(ChampionshipYear).all()
    completed_years = []
    
    for year_obj in all_years:
        tournament_stats = get_tournament_statistics(year_obj)
        is_completed = (tournament_stats['total_games'] > 0 and 
                       tournament_stats['completed_games'] == tournament_stats['total_games'])
        if is_completed:
            completed_years.append(year_obj)
    
    if not completed_years:
        return []
    
    if metric_type == 'goals':
        # Berechne Tore pro Turnier
        tournament_data = db.session.query(
            ChampionshipYear,
            func.sum(Game.team1_score + Game.team2_score).label('total_value'),
            func.count(Game.id).label('games_count')
        ).join(Game, ChampionshipYear.id == Game.year_id).filter(
            Game.team1_score.isnot(None),
            Game.team2_score.isnot(None),
            ChampionshipYear.id.in_([year.id for year in completed_years])
        ).group_by(ChampionshipYear.id).order_by(
            desc('total_value') if order == 'desc' else asc('total_value')
        ).all()
        
        if not tournament_data:
            return []
        
        # Bestimme Extremwert und erstelle Ergebnisse
        extreme_value = tournament_data[0].total_value
        results = []
        
        for year, total_value, games in tournament_data:
            if total_value == extreme_value:
                results.append({
                    'tournament': year.name,
                    'year': year.year,
                    'total_goals': total_value,
                    'games': games,
                    'goals_per_game': round(total_value / games, 2) if games > 0 else 0
                })
            else:
                break
        
        return results
    
    elif metric_type == 'penalties':
        # Berechne Strafminuten pro Turnier
        tournament_pim_data = []
        
        for year_obj in completed_years:
            # Berechne Strafminuten mit zentraler Funktion
            total_pim = calculate_tournament_penalty_minutes(year_obj.id, completed_games_only=True)
            
            # Anzahl der gespielten Spiele
            games_count = db.session.query(func.count(Game.id)).filter(
                Game.year_id == year_obj.id,
                Game.team1_score.isnot(None),
                Game.team2_score.isnot(None)
            ).scalar() or 0
            
            if games_count > 0:
                tournament_pim_data.append({
                    'tournament': year_obj.name,
                    'year': year_obj.year,
                    'total_pim': total_pim,
                    'games': games_count,
                    'pim_per_game': round(total_pim / games_count, 2) if games_count > 0 else 0
                })
        
        if not tournament_pim_data:
            return []
        
        # Sortiere nach Extremwert
        tournament_pim_data.sort(key=lambda x: x['total_pim'], reverse=(order == 'desc'))
        extreme_value = tournament_pim_data[0]['total_pim']
        
        # Gib alle Turniere mit dem Extremwert zurück
        results = []
        for data in tournament_pim_data:
            if data['total_pim'] == extreme_value:
                results.append(data)
            else:
                break
        
        return results
    
    else:
        raise ValueError(f"Unbekannter metric_type: {metric_type}")


def get_tournament_with_most_goals():
    """Turnier mit den meisten Toren - nur beendete Turniere"""
    return get_tournament_metric_extremes(metric_type='goals', order='desc')


def get_tournament_with_least_goals():
    """Turnier mit den wenigsten Toren - nur beendete Turniere"""
    return get_tournament_metric_extremes(metric_type='goals', order='asc')


def get_tournament_with_most_penalty_minutes():
    """Turnier mit den meisten Strafminuten - nur beendete Turniere"""
    return get_tournament_metric_extremes(metric_type='penalties', order='desc')


def get_tournament_with_least_penalty_minutes():
    """Turnier mit den wenigsten Strafminuten - nur beendete Turniere"""
    return get_tournament_metric_extremes(metric_type='penalties', order='asc')