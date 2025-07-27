"""
PlayoffResolver - Zentralisierte Klasse zur Auflösung von Playoff-Team-Codes

Diese Klasse kapselt die komplette Logik zur Auflösung von Team-Platzhaltern
(z.B. 'A1', 'W(57)', 'L(61)') zu tatsächlichen Team-Codes in einem einzigen Aufruf.
"""

import re
import os
import json
from typing import Dict, List, Tuple, Optional
from flask import current_app

from models import Game, ChampionshipYear, TeamStats
from constants import PLAYOFF_ROUNDS, PRELIM_ROUNDS


class PlayoffResolver:
    """
    Zentrale Klasse zur Auflösung von Playoff-Team-Codes.
    
    Diese Klasse bietet eine vereinfachte API, um Team-Platzhalter in einem einzigen
    Aufruf aufzulösen, ohne mehrere Utils-Funktionen aufrufen zu müssen.
    """
    
    def __init__(self, year_obj: ChampionshipYear, all_games: List[Game]):
        """
        Initialisiert den PlayoffResolver mit den notwendigen Daten.
        
        Args:
            year_obj: ChampionshipYear-Objekt für das Jahr
            all_games: Liste aller Spiele für das Jahr
        """
        self.year_obj = year_obj
        self.all_games = all_games
        self._playoff_team_map = None
        self._games_by_number = {g.game_number: g for g in all_games if g.game_number is not None}
        
    def get_resolved_code(self, placeholder_code: str) -> str:
        """
        Hauptmethode zur Auflösung eines Team-Platzhalters.
        
        Diese Methode initialisiert bei Bedarf die interne Playoff-Map und
        löst dann den gegebenen Platzhalter auf.
        
        Args:
            placeholder_code: Der aufzulösende Platzhalter (z.B. 'A1', 'W(57)')
            
        Returns:
            Der aufgelöste Team-Code (3-Buchstaben-Code) oder der ursprüngliche
            Platzhalter, falls keine Auflösung möglich ist.
        """
        # Initialisiere die Playoff-Map beim ersten Aufruf
        if self._playoff_team_map is None:
            self._initialize_playoff_map()
            
        # Verwende die interne Auflösungslogik
        return self._resolve_team_code(placeholder_code)
    
    def _initialize_playoff_map(self):
        """
        Initialisiert die interne Playoff-Team-Map.
        
        Diese Methode baut die vollständige Zuordnung von Platzhaltern zu
        tatsächlichen Team-Codes auf, basierend auf Vorrunden-Standings und
        Playoff-Ergebnissen.
        """
        # Importiere notwendige Funktionen aus anderen Utils
        from .standings import _calculate_basic_prelim_standings
        from .playoff_mapping import _build_playoff_team_map_for_year
        
        # Filtere Vorrundenspiele für Standings-Berechnung
        prelim_games_for_standings = [
            g for g in self.all_games
            if g.round in PRELIM_ROUNDS and
               self._is_code_final(g.team1_code) and
               self._is_code_final(g.team2_code) and
               g.team1_score is not None and g.team2_score is not None
        ]
        
        # Berechne Vorrunden-Standings
        prelim_standings_map = _calculate_basic_prelim_standings(prelim_games_for_standings)
        
        # Gruppiere Standings nach Gruppe
        prelim_standings_by_group: Dict[str, List[TeamStats]] = {}
        for ts_obj in prelim_standings_map.values():
            group_key = ts_obj.group if ts_obj.group else "UnknownGroup"
            if group_key not in prelim_standings_by_group:
                prelim_standings_by_group[group_key] = []
            prelim_standings_by_group[group_key].append(ts_obj)
        
        # Sortiere Teams innerhalb jeder Gruppe nach Rang
        for group_name in prelim_standings_by_group:
            prelim_standings_by_group[group_name].sort(key=lambda x: x.rank_in_group)
        
        # Baue die Playoff-Team-Map auf
        self._playoff_team_map = _build_playoff_team_map_for_year(
            self.year_obj,
            self.all_games,
            prelim_standings_by_group
        )
    
    def _resolve_team_code(self, placeholder_code: str) -> str:
        """
        Interne Methode zur Auflösung eines Team-Codes.
        
        Diese Methode implementiert die Auflösungslogik mit Zyklenerkennung
        und iterativer Auflösung von verketteten Platzhaltern.
        
        Args:
            placeholder_code: Der aufzulösende Platzhalter
            
        Returns:
            Der aufgelöste Team-Code oder der ursprüngliche Platzhalter
        """
        if not placeholder_code:
            return ""
            
        if self._is_code_final(placeholder_code):
            return placeholder_code
        
        current_code = placeholder_code
        visited_codes = {current_code}  # Zur Zyklenerkennung
        
        # Maximal 10 Iterationen zur Auflösung
        for _ in range(10):
            if self._is_code_final(current_code):
                return current_code
            
            # Versuche direkte Auflösung über die Map
            resolved_from_map = self._playoff_team_map.get(current_code)
            
            if resolved_from_map is not None:
                if self._is_code_final(resolved_from_map):
                    return resolved_from_map
                
                # Prüfe auf Selbstreferenz
                if resolved_from_map == current_code and not re.match(r"^[WL]\((\d+)\)$", current_code):
                    break
                
                current_code = resolved_from_map
            
            # Versuche Auflösung über Spielergebnis für W(X) oder L(X)
            elif re.match(r"^[WL]\(.+\)$", current_code):
                match = re.match(r"^([WL])\((.+)\)$", current_code)
                prefix = match.group(1)  # W oder L
                inner_code = match.group(2)
                
                # Prüfe ob inner_code eine Zahl ist
                if inner_code.isdigit():
                    game_num = int(inner_code)
                else:
                    # inner_code könnte SF1, SF2, etc. sein - versuche es aufzulösen
                    resolved_inner = self._playoff_team_map.get(inner_code)
                    if resolved_inner and resolved_inner.isdigit():
                        game_num = int(resolved_inner)
                    else:
                        # Kann nicht aufgelöst werden
                        break
                
                game = self._games_by_number.get(game_num)
                if game and game.team1_score is not None and game.team2_score is not None:
                    # Verhindere direkte Rekursion
                    if game.team1_code == current_code or game.team2_code == current_code:
                        break
                    
                    # Löse Spielteilnehmer auf
                    team1_resolved = self._resolve_team_code(game.team1_code)
                    team2_resolved = self._resolve_team_code(game.team2_code)
                    
                    if self._is_code_final(team1_resolved) and self._is_code_final(team2_resolved):
                        winner_code = team1_resolved if game.team1_score > game.team2_score else team2_resolved
                        loser_code = team2_resolved if game.team1_score > game.team2_score else team1_resolved
                        
                        current_code = winner_code if prefix == 'W' else loser_code
                    else:
                        break
                else:
                    break
            else:
                # Unbekanntes Format oder nicht auflösbarer Platzhalter
                break
            
            # Zyklenerkennung
            if current_code in visited_codes:
                return placeholder_code
            visited_codes.add(current_code)
        
        # Rückgabe des finalen Codes oder des ursprünglichen Platzhalters
        return current_code if self._is_code_final(current_code) else placeholder_code
    
    def _is_code_final(self, team_code: Optional[str]) -> bool:
        """
        Prüft, ob ein Team-Code ein definitiver 3-Buchstaben-Ländercode ist.
        
        Args:
            team_code: Der zu prüfende Code
            
        Returns:
            True, wenn es ein gültiger 3-Buchstaben-Code ist, sonst False
        """
        if not team_code:
            return False
        return len(team_code) == 3 and team_code.isalpha() and team_code.isupper()
    
    def get_all_resolutions(self) -> Dict[str, str]:
        """
        Gibt alle aufgelösten Platzhalter-zu-Team-Zuordnungen zurück.
        
        Diese Methode ist nützlich für Debugging und um alle Auflösungen
        auf einmal zu sehen.
        
        Returns:
            Dictionary mit allen Platzhalter-zu-Team-Zuordnungen
        """
        if self._playoff_team_map is None:
            self._initialize_playoff_map()
        return self._playoff_team_map.copy()
    
    def resolve_game_participants(self, game: Game) -> Tuple[str, str]:
        """
        Löst beide Teilnehmer eines Spiels auf.
        
        Args:
            game: Das Game-Objekt mit den aufzulösenden Teilnehmern
            
        Returns:
            Tupel mit (aufgelöster_team1_code, aufgelöster_team2_code)
        """
        team1_code = game.team1_code if game.team1_code else ""
        team2_code = game.team2_code if game.team2_code else ""
        
        resolved_team1 = self.get_resolved_code(team1_code)
        resolved_team2 = self.get_resolved_code(team2_code)
        
        return resolved_team1, resolved_team2


# Convenience-Funktion für einfache Nutzung
def resolve_playoff_code(placeholder_code: str, year_obj: ChampionshipYear, all_games: List[Game]) -> str:
    """
    Convenience-Funktion zur direkten Auflösung eines Playoff-Codes.
    
    Args:
        placeholder_code: Der aufzulösende Platzhalter (z.B. 'A1', 'W(57)')
        year_obj: ChampionshipYear-Objekt für das Jahr
        all_games: Liste aller Spiele für das Jahr
        
    Returns:
        Der aufgelöste Team-Code oder der ursprüngliche Platzhalter
    """
    resolver = PlayoffResolver(year_obj, all_games)
    return resolver.get_resolved_code(placeholder_code)