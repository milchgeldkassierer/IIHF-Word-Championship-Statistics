"""
StandingsCalculator Service für die Berechnung der Turniertabellen
Berechnet Punkte, Siege, Niederlagen und andere Statistiken basierend auf Spielergebnissen
"""

from typing import Dict, Optional, Tuple, TYPE_CHECKING

# Flexible imports für Tests und Produktion
if TYPE_CHECKING:
    from models import Team, Game
    from constants import GameType


class StandingsCalculator:
    """
    Service zur Berechnung und Aktualisierung der Teamstatistiken
    basierend auf Spielergebnissen
    """
    
    def __init__(self):
        """Initialisiert den StandingsCalculator"""
        pass
    
    def update_team_stats(self, team: 'Team', game: 'Game', is_home: bool) -> None:
        """
        Aktualisiert die Statistiken eines Teams basierend auf einem Spielergebnis
        
        Args:
            team: Das Team-Objekt, dessen Statistiken aktualisiert werden sollen
            game: Das Game-Objekt mit dem Spielergebnis
            is_home: True wenn das Team Heimmannschaft ist, False wenn Auswärtsmannschaft
        """
        # Erhöhe Anzahl der gespielten Spiele
        team.gp += 1
        
        # Bestimme Tore für und gegen das Team
        if is_home:
            goals_for = game.home_score
            goals_against = game.away_score
        else:
            goals_for = game.away_score
            goals_against = game.home_score
        
        # Aktualisiere Torstatistiken
        team.gf += goals_for
        team.ga += goals_against
        team.gd = team.gf - team.ga
        
        # Bestimme ob das Team gewonnen hat
        if is_home:
            team_won = game.home_score > game.away_score
        else:
            team_won = game.away_score > game.home_score
        
        # Berechne Punkte und aktualisiere Sieg/Niederlagen-Statistiken
        if team_won:
            self._handle_win(team, game.game_type)
        else:
            self._handle_loss(team, game.game_type)
    
    def _handle_win(self, team: 'Team', game_type: 'GameType') -> None:
        """
        Behandelt einen Sieg und aktualisiert die entsprechenden Statistiken
        
        Args:
            team: Das siegreiche Team
            game_type: Der Typ des Spiels (REG, OT, SO)
        """
        if game_type == "REG":
            # Regulärer Sieg: 3 Punkte
            team.pts += 3
            team.w += 1
        elif game_type == "OT":
            # Overtime-Sieg: 2 Punkte
            team.pts += 2
            team.otw += 1
        elif game_type == "SO":
            # Shootout-Sieg: 2 Punkte
            team.pts += 2
            team.sow += 1
    
    def _handle_loss(self, team: 'Team', game_type: 'GameType') -> None:
        """
        Behandelt eine Niederlage und aktualisiert die entsprechenden Statistiken
        
        Args:
            team: Das unterlegene Team
            game_type: Der Typ des Spiels (REG, OT, SO)
        """
        if game_type == "REG":
            # Reguläre Niederlage: 0 Punkte
            team.l += 1
        elif game_type == "OT":
            # Overtime-Niederlage: 1 Punkt
            team.pts += 1
            team.otl += 1
        elif game_type == "SO":
            # Shootout-Niederlage: 1 Punkt
            team.pts += 1
            team.sol += 1
    
    def calculate_win_percentage(self, team: 'Team') -> float:
        """
        Berechnet die Siegquote eines Teams
        
        Args:
            team: Das Team für die Berechnung
            
        Returns:
            Die Siegquote als Dezimalzahl (0.0 - 1.0)
        """
        if team.gp == 0:
            return 0.0
        
        # Zähle alle Siege (regulär, OT und SO)
        total_wins = team.w + team.otw + team.sow
        return total_wins / team.gp
    
    def calculate_points_percentage(self, team: 'Team') -> float:
        """
        Berechnet den Prozentsatz der möglichen Punkte, die das Team gewonnen hat
        
        Args:
            team: Das Team für die Berechnung
            
        Returns:
            Der Punkteprozentsatz als Dezimalzahl (0.0 - 1.0)
        """
        if team.gp == 0:
            return 0.0
        
        # Maximale Punkte = 3 pro Spiel
        max_points = team.gp * 3
        return team.pts / max_points
    
    def reset_team_stats(self, team: 'Team') -> None:
        """
        Setzt alle Statistiken eines Teams zurück
        
        Args:
            team: Das Team dessen Statistiken zurückgesetzt werden sollen
        """
        team.gp = 0
        team.w = 0
        team.otw = 0
        team.sow = 0
        team.l = 0
        team.otl = 0
        team.sol = 0
        team.pts = 0
        team.gf = 0
        team.ga = 0
        team.gd = 0
    
    def get_team_record(self, team: 'Team') -> str:
        """
        Gibt den Spielrekord eines Teams als formatierten String zurück
        
        Args:
            team: Das Team für die Anzeige
            
        Returns:
            Formatierter String mit dem Rekord (z.B. "5-2-1-0" für W-L-OTL-SOL)
        """
        return f"{team.w}-{team.l}-{team.otl}-{team.sol}"
    
    def get_detailed_wins(self, team: 'Team') -> Tuple[int, int, int]:
        """
        Gibt die Anzahl der Siege nach Typ zurück
        
        Args:
            team: Das Team für die Statistik
            
        Returns:
            Tuple mit (reguläre Siege, OT-Siege, SO-Siege)
        """
        return (team.w, team.otw, team.sow)
    
    def get_detailed_losses(self, team: 'Team') -> Tuple[int, int, int]:
        """
        Gibt die Anzahl der Niederlagen nach Typ zurück
        
        Args:
            team: Das Team für die Statistik
            
        Returns:
            Tuple mit (reguläre Niederlagen, OT-Niederlagen, SO-Niederlagen)
        """
        return (team.l, team.otl, team.sol)