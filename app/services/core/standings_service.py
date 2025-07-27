"""
StandingsService - Kernservice für Turniertabellen und Platzierungen
Berechnet Gruppenstandings, Playoffs-Qualifikation und finale Platzierungen
"""

from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from models import TeamStats, Game, db
from app.services.base import BaseService
from app.services.utils.cache_manager import CacheableService, cached
from app.repositories.core.standings_repository import StandingsRepository
from constants import PRELIM_ROUNDS, MAX_PRELIM_GAMES_PER_TEAM
import logging

logger = logging.getLogger(__name__)


class StandingsService(CacheableService, BaseService[TeamStats]):
    """
    Service für die Berechnung und Verwaltung von Turniertabellen
    
    Features:
    - Gruppenstandings berechnen
    - Head-to-Head Tiebreaker anwenden
    - Playoff-Qualifikation bestimmen
    - Finale Platzierungen (1-16) berechnen
    - Performance-optimiert (keine N+1 Queries)
    """
    
    def __init__(self):
        """Initialisiert den StandingsService mit Repository und Cache"""
        repository = StandingsRepository()
        # Initialisiere beide Elternklassen
        # Use proper MRO initialization
        super().__init__(repository)
        self.repository: StandingsRepository = repository
    
    @cached(ttl=300, key_prefix="standings:group")
    def calculate_group_standings(self, year_id: int, group: Optional[str] = None) -> Dict[str, List[TeamStats]]:
        """
        Berechnet die Gruppenstandings für ein Jahr
        
        Args:
            year_id: Die ID des Championship-Jahres
            group: Optional - spezifische Gruppe (z.B. "Group A")
            
        Returns:
            Dictionary mit Gruppen als Keys und sortierten TeamStats-Listen als Values
        """
        # Hole alle Vorrunden-Spiele effizient
        games = self.repository.get_preliminary_games(year_id, group)
        
        # Berechne Standings aus den Spielen
        standings_map = self._calculate_standings_from_games(games)
        
        # Gruppiere nach Gruppen
        grouped_standings = self._group_standings_by_group(standings_map)
        
        # Sortiere und wende Tiebreaker an
        for group_name, teams in grouped_standings.items():
            grouped_standings[group_name] = self._apply_sorting_and_tiebreakers(teams, games)
        
        return grouped_standings
    
    @cached(ttl=600, key_prefix="standings:final_ranking")
    def calculate_final_tournament_ranking(self, year_id: int) -> Dict[int, str]:
        """
        Berechnet die finale Turnierplatzierung (1-16)
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Dictionary mit Platz (1-16) als Key und Team-Code als Value
        """
        # Hole alle notwendigen Daten in einem Query
        all_games = self.repository.get_all_games_for_year(year_id)
        playoff_mapping = self.repository.get_playoff_mapping(year_id)
        custom_seeding = self.repository.get_custom_seeding(year_id)
        
        # Trenne Spiele nach Runden
        prelim_games = [g for g in all_games if g.round in PRELIM_ROUNDS]
        qf_games = [g for g in all_games if g.round == "Quarterfinals"]
        sf_games = [g for g in all_games if g.round == "Semifinals"]
        bronze_game = next((g for g in all_games if g.round == "Bronze Medal Game"), None)
        gold_game = next((g for g in all_games if g.round == "Gold Medal Game"), None)
        
        # Berechne Medaillengewinner
        medal_ranking = self._calculate_medal_positions(
            sf_games, bronze_game, gold_game, playoff_mapping, custom_seeding
        )
        
        # Berechne Plätze 5-8 (QF-Verlierer)
        qf_losers_ranking = self._calculate_quarterfinal_losers_ranking(
            qf_games, prelim_games, playoff_mapping
        )
        
        # Berechne Plätze 9-16 (Nicht-Playoff-Teams)
        remaining_ranking = self._calculate_remaining_positions(
            prelim_games, set(medal_ranking.values()) | set(qf_losers_ranking.values())
        )
        
        # Kombiniere alle Rankings
        final_ranking = {}
        final_ranking.update(medal_ranking)
        final_ranking.update(qf_losers_ranking)
        final_ranking.update(remaining_ranking)
        
        return final_ranking
    
    def calculate_standings_from_games(self, games: List[Game], group_filter: Optional[str] = None) -> Dict[str, TeamStats]:
        """
        Berechnet die Standings aus einer Liste von Spielen (öffentliche Methode)
        
        Args:
            games: Liste von Game-Objekten
            group_filter: Optionaler Gruppenfilter
            
        Returns:
            Dictionary mit Team-Code als Key und TeamStats als Value
        """
        # Filtere Spiele nach Gruppe falls angegeben
        filtered_games = games
        if group_filter:
            filtered_games = [g for g in games if g.group == group_filter]
        
        # Verwende die interne optimierte Implementierung
        return self._calculate_standings_from_games(filtered_games)

    def get_team_standings_stats(self, year_id: int, team_code: str) -> Optional[TeamStats]:
        """
        Holt die Standings-Statistiken für ein spezifisches Team
        
        Args:
            year_id: Die ID des Championship-Jahres
            team_code: Der Team-Code
            
        Returns:
            TeamStats-Objekt oder None
        """
        games = self.repository.get_team_games(year_id, team_code, PRELIM_ROUNDS)
        standings = self._calculate_standings_from_games(games)
        return standings.get(team_code)
    
    def get_playoff_qualifiers(self, year_id: int) -> List[Tuple[str, str]]:
        """
        Bestimmt die Playoff-Qualifikanten basierend auf Gruppenstandings
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Liste von Tupeln (Team-Code, Platzhalter wie "A1")
        """
        grouped_standings = self.calculate_group_standings(year_id)
        qualifiers = []
        
        for group_name, teams in grouped_standings.items():
            group_letter = group_name.replace("Group ", "") if group_name.startswith("Group ") else group_name
            
            # Top 4 jeder Gruppe qualifizieren sich
            for i, team in enumerate(teams[:4], 1):
                placeholder = f"{group_letter}{i}"
                qualifiers.append((team.name, placeholder))
        
        return qualifiers
    
    def apply_head_to_head_tiebreaker(self, teams: List[TeamStats], 
                                    relevant_games: List[Game]) -> List[TeamStats]:
        """
        Wendet Head-to-Head Tiebreaker-Regeln an
        
        IIHF Regeln:
        - Bei 2 Teams: Direkter Vergleich (falls gespielt)
        - Bei 3+ Teams: Mini-Tabelle aller Spiele untereinander
        - Fallback: Tordifferenz, dann Tore erzielt
        
        Args:
            teams: Liste von Teams mit gleichen Punkten
            relevant_games: Alle relevanten Spiele
            
        Returns:
            Sortierte Liste nach Tiebreaker
        """
        if len(teams) <= 1:
            return teams
        
        if len(teams) == 2:
            return self._apply_two_team_tiebreaker(teams, relevant_games)
        else:
            return self._apply_multi_team_tiebreaker(teams, relevant_games)
    
    # Private Hilfsmethoden
    
    def _calculate_standings_from_games(self, games: List[Game]) -> Dict[str, TeamStats]:
        """Berechnet TeamStats aus einer Liste von Spielen"""
        standings = {}
        
        for game in games:
            if game.team1_score is None or game.team2_score is None:
                continue
            
            # Initialisiere Teams falls nötig
            if game.team1_code not in standings:
                standings[game.team1_code] = TeamStats(
                    name=game.team1_code,
                    group=game.group or "N/A"
                )
            if game.team2_code not in standings:
                standings[game.team2_code] = TeamStats(
                    name=game.team2_code,
                    group=game.group or "N/A"
                )
            
            # Update Statistiken
            self._update_team_stats_from_game(standings[game.team1_code], standings[game.team2_code], game)
        
        return standings
    
    def _update_team_stats_from_game(self, team1_stats: TeamStats, team2_stats: TeamStats, game: Game):
        """Aktualisiert TeamStats basierend auf einem Spiel"""
        # Spiele gespielt
        team1_stats.gp += 1
        team2_stats.gp += 1
        
        # Tore
        team1_stats.gf += game.team1_score
        team1_stats.ga += game.team2_score
        team2_stats.gf += game.team2_score
        team2_stats.ga += game.team1_score
        
        # Punkte und Siege/Niederlagen
        if game.result_type == 'REG':
            if game.team1_score > game.team2_score:
                team1_stats.w += 1
                team1_stats.pts += 3
                team2_stats.l += 1
            else:
                team2_stats.w += 1
                team2_stats.pts += 3
                team1_stats.l += 1
        elif game.result_type == 'OT':
            if game.team1_score > game.team2_score:
                team1_stats.otw += 1
                team1_stats.pts += 2
                team2_stats.otl += 1
                team2_stats.pts += 1
            else:
                team2_stats.otw += 1
                team2_stats.pts += 2
                team1_stats.otl += 1
                team1_stats.pts += 1
        elif game.result_type == 'SO':
            if game.team1_score > game.team2_score:
                team1_stats.sow += 1
                team1_stats.pts += 2
                team2_stats.sol += 1
                team2_stats.pts += 1
            else:
                team2_stats.sow += 1
                team2_stats.pts += 2
                team1_stats.sol += 1
                team1_stats.pts += 1
    
    def _group_standings_by_group(self, standings: Dict[str, TeamStats]) -> Dict[str, List[TeamStats]]:
        """Gruppiert TeamStats nach Gruppe"""
        grouped = defaultdict(list)
        
        for team_stats in standings.values():
            group = team_stats.group if team_stats.group and team_stats.group != "N/A" else "Unknown"
            grouped[group].append(team_stats)
        
        return dict(grouped)
    
    def _apply_sorting_and_tiebreakers(self, teams: List[TeamStats], 
                                     all_games: List[Game]) -> List[TeamStats]:
        """Sortiert Teams und wendet Tiebreaker an"""
        # Erste Sortierung nach Punkten, Tordifferenz, Tore erzielt
        teams.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        
        # Gruppiere Teams mit gleichen Punkten
        teams_by_points = defaultdict(list)
        for team in teams:
            teams_by_points[team.pts].append(team)
        
        # Wende Tiebreaker für jede Punktgruppe an
        result = []
        for points in sorted(teams_by_points.keys(), reverse=True):
            tied_teams = teams_by_points[points]
            if len(tied_teams) > 1:
                tied_teams = self.apply_head_to_head_tiebreaker(tied_teams, all_games)
            result.extend(tied_teams)
        
        # Setze rank_in_group
        for i, team in enumerate(result, 1):
            team.rank_in_group = i
        
        return result
    
    def _apply_two_team_tiebreaker(self, teams: List[TeamStats], 
                                  games: List[Game]) -> List[TeamStats]:
        """Head-to-Head für genau 2 Teams"""
        team1, team2 = teams[0], teams[1]
        
        # Finde direktes Spiel
        h2h_game = None
        for game in games:
            if ((game.team1_code == team1.name and game.team2_code == team2.name) or
                (game.team1_code == team2.name and game.team2_code == team1.name)):
                if game.team1_score is not None and game.team2_score is not None:
                    h2h_game = game
                    break
        
        if not h2h_game:
            # Kein direktes Spiel - nutze Gesamtstatistik
            return sorted(teams, key=lambda x: (x.gd, x.gf), reverse=True)
        
        # Bestimme Gewinner des direkten Spiels
        if game.team1_code == team1.name:
            if game.team1_score > game.team2_score:
                return [team1, team2]
            else:
                return [team2, team1]
        else:
            if game.team2_score > game.team1_score:
                return [team1, team2]
            else:
                return [team2, team1]
    
    def _apply_multi_team_tiebreaker(self, teams: List[TeamStats], 
                                    games: List[Game]) -> List[TeamStats]:
        """Head-to-Head für 3+ Teams"""
        # Prüfe ob alle Teams alle Spiele gespielt haben
        if not all(team.gp >= MAX_PRELIM_GAMES_PER_TEAM for team in teams):
            # Nicht alle Spiele gespielt - nutze Gesamtstatistik
            return sorted(teams, key=lambda x: (x.gd, x.gf), reverse=True)
        
        # Erstelle Mini-Tabelle der direkten Spiele
        team_names = {team.name for team in teams}
        h2h_stats = {team.name: {'pts': 0, 'gf': 0, 'ga': 0, 'team': team} 
                     for team in teams}
        
        for game in games:
            if (game.team1_code in team_names and game.team2_code in team_names and
                game.team1_score is not None and game.team2_score is not None):
                
                t1_stats = h2h_stats[game.team1_code]
                t2_stats = h2h_stats[game.team2_code]
                
                # Tore
                t1_stats['gf'] += game.team1_score
                t1_stats['ga'] += game.team2_score
                t2_stats['gf'] += game.team2_score
                t2_stats['ga'] += game.team1_score
                
                # Punkte
                if game.result_type == 'REG':
                    if game.team1_score > game.team2_score:
                        t1_stats['pts'] += 3
                    else:
                        t2_stats['pts'] += 3
                elif game.result_type in ['OT', 'SO']:
                    if game.team1_score > game.team2_score:
                        t1_stats['pts'] += 2
                        t2_stats['pts'] += 1
                    else:
                        t2_stats['pts'] += 2
                        t1_stats['pts'] += 1
        
        # Sortiere nach H2H-Kriterien
        h2h_list = list(h2h_stats.values())
        h2h_list.sort(key=lambda x: (
            x['pts'],                           # H2H Punkte
            x['gf'] - x['ga'],                  # H2H Tordifferenz
            x['gf'],                            # H2H Tore erzielt
            x['team'].gd,                       # Gesamt Tordifferenz
            x['team'].gf                        # Gesamt Tore erzielt
        ), reverse=True)
        
        return [h2h['team'] for h2h in h2h_list]
    
    def _calculate_medal_positions(self, sf_games: List[Game], bronze_game: Optional[Game],
                                 gold_game: Optional[Game], playoff_mapping: Dict[str, str],
                                 custom_seeding: Optional[Dict[str, str]]) -> Dict[int, str]:
        """Berechnet Plätze 1-4 (Medaillengewinner)"""
        ranking = {}
        
        if not sf_games or len(sf_games) < 2:
            return ranking
        
        # Erweitere playoff_mapping mit custom_seeding
        if custom_seeding:
            playoff_mapping = playoff_mapping.copy() if playoff_mapping else {}
            playoff_mapping.update(custom_seeding)
        
        # Bestimme Semifinal-Gewinner und -Verlierer
        sf_results = {}
        for sf_game in sf_games:
            if sf_game.team1_score is None or sf_game.team2_score is None:
                continue
                
            winner = sf_game.team1_code if sf_game.team1_score > sf_game.team2_score else sf_game.team2_code
            loser = sf_game.team2_code if sf_game.team1_score > sf_game.team2_score else sf_game.team1_code
            
            # Löse Platzhalter auf
            winner = self._resolve_team_code(winner, playoff_mapping)
            loser = self._resolve_team_code(loser, playoff_mapping)
            
            if sf_game.game_number == 61:  # SF1
                sf_results['W(SF1)'] = winner
                sf_results['L(SF1)'] = loser
            elif sf_game.game_number == 62:  # SF2
                sf_results['W(SF2)'] = winner
                sf_results['L(SF2)'] = loser
        
        # Bronze Medal Game
        if bronze_game and bronze_game.team1_score is not None and bronze_game.team2_score is not None:
            bronze_winner = bronze_game.team1_code if bronze_game.team1_score > bronze_game.team2_score else bronze_game.team2_code
            bronze_loser = bronze_game.team2_code if bronze_game.team1_score > bronze_game.team2_score else bronze_game.team1_code
            
            # Bestimme welches Team Bronze und welches 4. wird
            if bronze_winner in ['L(SF1)', 'L(SF2)'] and bronze_winner in sf_results:
                ranking[3] = sf_results[bronze_winner]
            elif 'L(SF1)' in sf_results and 'L(SF2)' in sf_results:
                # Fallback: Nutze SF-Verlierer direkt
                if bronze_game.team1_code == 'L(SF1)':
                    ranking[3] = sf_results['L(SF1)'] if bronze_game.team1_score > bronze_game.team2_score else sf_results['L(SF2)']
                    ranking[4] = sf_results['L(SF2)'] if bronze_game.team1_score > bronze_game.team2_score else sf_results['L(SF1)']
                else:
                    ranking[3] = sf_results['L(SF2)'] if bronze_game.team1_score > bronze_game.team2_score else sf_results['L(SF1)']
                    ranking[4] = sf_results['L(SF1)'] if bronze_game.team1_score > bronze_game.team2_score else sf_results['L(SF2)']
        
        # Gold Medal Game
        if gold_game and gold_game.team1_score is not None and gold_game.team2_score is not None:
            gold_winner = gold_game.team1_code if gold_game.team1_score > gold_game.team2_score else gold_game.team2_code
            silver_winner = gold_game.team2_code if gold_game.team1_score > gold_game.team2_score else gold_game.team1_code
            
            # Bestimme Gold und Silber
            if 'W(SF1)' in sf_results and 'W(SF2)' in sf_results:
                if gold_game.team1_code == 'W(SF1)':
                    ranking[1] = sf_results['W(SF1)'] if gold_game.team1_score > gold_game.team2_score else sf_results['W(SF2)']
                    ranking[2] = sf_results['W(SF2)'] if gold_game.team1_score > gold_game.team2_score else sf_results['W(SF1)']
                else:
                    ranking[1] = sf_results['W(SF2)'] if gold_game.team1_score > gold_game.team2_score else sf_results['W(SF1)']
                    ranking[2] = sf_results['W(SF1)'] if gold_game.team1_score > gold_game.team2_score else sf_results['W(SF2)']
        
        return ranking
    
    def _calculate_quarterfinal_losers_ranking(self, qf_games: List[Game], 
                                              prelim_games: List[Game],
                                              playoff_mapping: Dict[str, str]) -> Dict[int, str]:
        """Berechnet Plätze 5-8 (Quarterfinal-Verlierer)"""
        ranking = {}
        
        # Hole QF-Verlierer
        qf_losers = []
        for game in qf_games:
            if game.team1_score is None or game.team2_score is None:
                continue
                
            loser = game.team2_code if game.team1_score > game.team2_score else game.team1_code
            loser_resolved = self._resolve_team_code(loser, playoff_mapping)
            qf_losers.append(loser_resolved)
        
        if not qf_losers:
            return ranking
        
        # Berechne Vorrunden-Statistiken für QF-Verlierer
        prelim_standings = self._calculate_standings_from_games(prelim_games)
        
        # Sortiere QF-Verlierer nach Vorrunden-Performance
        qf_losers_stats = []
        for team in qf_losers:
            if team in prelim_standings:
                stats = prelim_standings[team]
                qf_losers_stats.append(stats)
        
        qf_losers_stats.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        
        # Vergebe Plätze 5-8
        for i, team_stats in enumerate(qf_losers_stats[:4], 5):
            ranking[i] = team_stats.name
        
        return ranking
    
    def _calculate_remaining_positions(self, prelim_games: List[Game],
                                     already_ranked_teams: Set[str]) -> Dict[int, str]:
        """Berechnet Plätze 9-16 (Teams die nicht in Playoffs waren)"""
        ranking = {}
        
        # Berechne alle Vorrunden-Standings
        all_standings = self._calculate_standings_from_games(prelim_games)
        
        # Filtere bereits platzierte Teams
        remaining_teams = []
        for team_code, stats in all_standings.items():
            if team_code not in already_ranked_teams:
                remaining_teams.append(stats)
        
        # Sortiere nach Vorrunden-Performance
        remaining_teams.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        
        # Vergebe Plätze 9-16
        position = 9
        for team_stats in remaining_teams:
            if position <= 16:
                ranking[position] = team_stats.name
                position += 1
        
        return ranking
    
    def _resolve_team_code(self, code: str, mapping: Dict[str, str]) -> str:
        """Löst Platzhalter-Codes zu echten Team-Codes auf"""
        if code in mapping:
            return self._resolve_team_code(mapping[code], mapping)
        return code
    
    @cached(ttl=300, key_prefix="standings:summary")
    def get_standings_summary(self, year_id: int) -> Dict[str, any]:
        """
        Erstellt eine Zusammenfassung aller Standings für ein Jahr
        
        Returns:
            Dictionary mit group_standings, playoff_qualifiers, final_ranking
        """
        return {
            'group_standings': self.calculate_group_standings(year_id),
            'playoff_qualifiers': self.get_playoff_qualifiers(year_id),
            'final_ranking': self.calculate_final_tournament_ranking(year_id)
        }