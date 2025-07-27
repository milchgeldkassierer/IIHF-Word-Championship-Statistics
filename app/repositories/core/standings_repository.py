"""
StandingsRepository - Datenzugriffsschicht für Standings-bezogene Operationen
Optimiert für Performance mit effizienten Queries und Eager Loading
"""

from typing import List, Dict, Optional, Set, Tuple
from sqlalchemy import and_, or_, func, select, case
from sqlalchemy.orm import joinedload, selectinload, subqueryload, contains_eager
from models import Game, ChampionshipYear, TeamStats, db
from app.repositories.base import BaseRepository
from constants import PRELIM_ROUNDS


class StandingsRepository(BaseRepository[Game]):
    """
    Repository für standings-bezogene Datenbankoperationen
    
    Features:
    - Optimierte Queries mit Eager Loading
    - Vermeidung von N+1 Query-Problemen
    - Effiziente Aggregationen
    - Caching-freundliche Query-Struktur
    """
    
    def __init__(self):
        """Initialisiert das Repository mit der Datenbank-Session"""
        super().__init__(Game)
    
    def get_preliminary_games(self, year_id: int, group: Optional[str] = None) -> List[Game]:
        """
        Holt alle Vorrunden-Spiele für ein Jahr
        
        Args:
            year_id: Die ID des Championship-Jahres
            group: Optional - spezifische Gruppe filtern
            
        Returns:
            Liste von Game-Objekten
        """
        query = self.db.session.query(Game).filter(
            Game.year_id == year_id,
            Game.round.in_(PRELIM_ROUNDS)
        )
        
        if group:
            query = query.filter(Game.group == group)
        
        # Sortiere nach Spielnummer für konsistente Reihenfolge
        return query.order_by(Game.game_number).all()
    
    def get_all_games_for_year(self, year_id: int) -> List[Game]:
        """
        Holt alle Spiele eines Jahres mit einer effizienten Query
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Liste aller Game-Objekte des Jahres
        """
        return self.db.session.query(Game).filter(
            Game.year_id == year_id
        ).order_by(Game.game_number).all()
    
    def get_team_games(self, year_id: int, team_code: str, 
                      rounds: Optional[List[str]] = None) -> List[Game]:
        """
        Holt alle Spiele eines Teams in einem Jahr
        
        Args:
            year_id: Die ID des Championship-Jahres
            team_code: Der Team-Code
            rounds: Optional - nur bestimmte Runden
            
        Returns:
            Liste von Game-Objekten
        """
        query = self.db.session.query(Game).filter(
            Game.year_id == year_id,
            or_(Game.team1_code == team_code, Game.team2_code == team_code)
        )
        
        if rounds:
            query = query.filter(Game.round.in_(rounds))
        
        return query.order_by(Game.game_number).all()
    
    def get_playoff_games(self, year_id: int) -> Dict[str, List[Game]]:
        """
        Holt alle Playoff-Spiele gruppiert nach Runde
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Dictionary mit Runde als Key und Game-Liste als Value
        """
        playoff_rounds = ["Quarterfinals", "Semifinals", "Bronze Medal Game", "Gold Medal Game"]
        
        games = self.db.session.query(Game).filter(
            Game.year_id == year_id,
            Game.round.in_(playoff_rounds)
        ).order_by(Game.game_number).all()
        
        # Gruppiere nach Runde
        grouped = {}
        for game in games:
            if game.round not in grouped:
                grouped[game.round] = []
            grouped[game.round].append(game)
        
        return grouped
    
    def get_games_between_teams(self, year_id: int, team_codes: Set[str]) -> List[Game]:
        """
        Holt alle Spiele zwischen einer Gruppe von Teams
        
        Args:
            year_id: Die ID des Championship-Jahres
            team_codes: Set von Team-Codes
            
        Returns:
            Liste von Game-Objekten
        """
        return self.db.session.query(Game).filter(
            Game.year_id == year_id,
            Game.team1_code.in_(team_codes),
            Game.team2_code.in_(team_codes)
        ).order_by(Game.game_number).all()
    
    def get_completed_games_count(self, year_id: int, team_code: str, 
                                rounds: Optional[List[str]] = None) -> int:
        """
        Zählt die Anzahl der gespielten Spiele eines Teams
        
        Args:
            year_id: Die ID des Championship-Jahres
            team_code: Der Team-Code
            rounds: Optional - nur bestimmte Runden
            
        Returns:
            Anzahl der Spiele mit Ergebnis
        """
        query = self.db.session.query(func.count(Game.id)).filter(
            Game.year_id == year_id,
            or_(Game.team1_code == team_code, Game.team2_code == team_code),
            Game.team1_score.isnot(None),
            Game.team2_score.isnot(None)
        )
        
        if rounds:
            query = query.filter(Game.round.in_(rounds))
        
        return query.scalar()
    
    def get_playoff_mapping(self, year_id: int) -> Dict[str, str]:
        """
        Holt das Playoff-Mapping für Team-Platzhalter
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Dictionary mit Platzhalter-Mappings
        """
        # Diese Methode würde normalerweise aus einer separaten Tabelle lesen
        # Für jetzt geben wir ein leeres Dict zurück
        # TODO: Implementiere playoff_mapping Tabelle wenn benötigt
        return {}
    
    def get_custom_seeding(self, year_id: int) -> Optional[Dict[str, str]]:
        """
        Holt custom Seeding-Informationen falls vorhanden
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Dictionary mit custom Seeding oder None
        """
        # Diese Methode würde normalerweise aus einer separaten Tabelle lesen
        # Für jetzt geben wir None zurück
        # TODO: Implementiere custom_seeding Tabelle wenn benötigt
        return None
    
    def get_teams_in_group(self, year_id: int, group: str) -> List[str]:
        """
        Holt alle Teams einer Gruppe
        
        Args:
            year_id: Die ID des Championship-Jahres
            group: Die Gruppe (z.B. "Group A")
            
        Returns:
            Liste von Team-Codes
        """
        # Hole alle Teams die in dieser Gruppe gespielt haben
        games = self.db.session.query(Game.team1_code, Game.team2_code).filter(
            Game.year_id == year_id,
            Game.group == group,
            Game.round.in_(PRELIM_ROUNDS)
        ).all()
        
        # Sammle unique Team-Codes
        teams = set()
        for game in games:
            teams.add(game.team1_code)
            teams.add(game.team2_code)
        
        return sorted(list(teams))
    
    def get_group_standings_raw(self, year_id: int, group: str) -> List[Dict]:
        """
        Holt rohe Standings-Daten direkt aus der Datenbank
        Nutzt SQL-Aggregation für bessere Performance
        
        Args:
            year_id: Die ID des Championship-Jahres
            group: Die Gruppe
            
        Returns:
            Liste von Dictionaries mit Standings-Daten
        """
        # Optimierte Query mit SQL-Aggregation für direkte Standings-Berechnung
        # Dies vermeidet N+1 Queries und berechnet alles in der Datenbank
        
        # Subquery für Team1 Statistiken
        team1_stats = self.db.session.query(
            Game.team1_code.label('team_code'),
            func.count(Game.id).label('games_played'),
            func.sum(Game.team1_score).label('goals_for'),
            func.sum(Game.team2_score).label('goals_against'),
            func.sum(Game.team1_points).label('points'),
            func.sum(
                case(
                    (and_(Game.result_type == 'REG', Game.team1_score > Game.team2_score), 1),
                    else_=0
                )
            ).label('wins'),
            func.sum(
                case(
                    (and_(Game.result_type == 'OT', Game.team1_score > Game.team2_score), 1),
                    else_=0
                )
            ).label('ot_wins'),
            func.sum(
                case(
                    (and_(Game.result_type == 'SO', Game.team1_score > Game.team2_score), 1),
                    else_=0
                )
            ).label('so_wins')
        ).filter(
            Game.year_id == year_id,
            Game.group == group,
            Game.round.in_(PRELIM_ROUNDS),
            Game.team1_score.isnot(None)
        ).group_by(Game.team1_code).subquery()
        
        # Subquery für Team2 Statistiken
        team2_stats = self.db.session.query(
            Game.team2_code.label('team_code'),
            func.count(Game.id).label('games_played'),
            func.sum(Game.team2_score).label('goals_for'),
            func.sum(Game.team1_score).label('goals_against'),
            func.sum(Game.team2_points).label('points'),
            func.sum(
                case(
                    (and_(Game.result_type == 'REG', Game.team2_score > Game.team1_score), 1),
                    else_=0
                )
            ).label('wins'),
            func.sum(
                case(
                    (and_(Game.result_type == 'OT', Game.team2_score > Game.team1_score), 1),
                    else_=0
                )
            ).label('ot_wins'),
            func.sum(
                case(
                    (and_(Game.result_type == 'SO', Game.team2_score > Game.team1_score), 1),
                    else_=0
                )
            ).label('so_wins')
        ).filter(
            Game.year_id == year_id,
            Game.group == group,
            Game.round.in_(PRELIM_ROUNDS),
            Game.team2_score.isnot(None)
        ).group_by(Game.team2_code).subquery()
        
        # Union und finale Aggregation
        union_query = self.db.session.query(team1_stats).union_all(
            self.db.session.query(team2_stats)
        ).subquery()
        
        # Finale Aggregation
        final_stats = self.db.session.query(
            union_query.c.team_code,
            func.sum(union_query.c.games_played).label('gp'),
            func.sum(union_query.c.goals_for).label('gf'),
            func.sum(union_query.c.goals_against).label('ga'),
            func.sum(union_query.c.points).label('pts'),
            func.sum(union_query.c.wins).label('w'),
            func.sum(union_query.c.ot_wins).label('otw'),
            func.sum(union_query.c.so_wins).label('sow'),
            (func.sum(union_query.c.goals_for) - func.sum(union_query.c.goals_against)).label('gd')
        ).group_by(union_query.c.team_code).all()
        
        # Konvertiere zu Dictionary-Format
        standings_data = []
        for row in final_stats:
            standings_data.append({
                'team_code': row.team_code,
                'group': group,
                'gp': row.gp or 0,
                'w': row.w or 0,
                'otw': row.otw or 0,
                'sow': row.sow or 0,
                'l': row.gp - (row.w or 0) - (row.otw or 0) - (row.sow or 0),
                'pts': row.pts or 0,
                'gf': row.gf or 0,
                'ga': row.ga or 0,
                'gd': row.gd or 0
            })
        
        return standings_data
    
    def bulk_get_team_games(self, year_id: int, team_codes: List[str]) -> Dict[str, List[Game]]:
        """
        Holt Spiele für mehrere Teams auf einmal (vermeidet N+1)
        
        Args:
            year_id: Die ID des Championship-Jahres
            team_codes: Liste von Team-Codes
            
        Returns:
            Dictionary mit Team-Code als Key und Game-Liste als Value
        """
        games = self.db.session.query(Game).filter(
            Game.year_id == year_id,
            or_(
                Game.team1_code.in_(team_codes),
                Game.team2_code.in_(team_codes)
            )
        ).all()
        
        # Gruppiere nach Team
        team_games = {team: [] for team in team_codes}
        
        for game in games:
            if game.team1_code in team_games:
                team_games[game.team1_code].append(game)
            if game.team2_code in team_games:
                team_games[game.team2_code].append(game)
        
        return team_games
    
    def get_year_info(self, year_id: int) -> Optional[ChampionshipYear]:
        """
        Holt Informationen zum Championship-Jahr
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            ChampionshipYear-Objekt oder None
        """
        return self.db.session.query(ChampionshipYear).filter(
            ChampionshipYear.id == year_id
        ).first()
    
    def has_playoff_games(self, year_id: int) -> bool:
        """
        Prüft ob Playoff-Spiele für ein Jahr existieren
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            True wenn Playoff-Spiele existieren
        """
        return self.db.session.query(
            self.db.session.query(Game).filter(
                Game.year_id == year_id,
                Game.round.in_(["Quarterfinals", "Semifinals", 
                              "Bronze Medal Game", "Gold Medal Game"])
            ).exists()
        ).scalar()
    
    def get_teams_by_final_position(self, year_id: int, positions: List[int]) -> Dict[int, str]:
        """
        Holt Teams nach ihrer finalen Platzierung
        
        Args:
            year_id: Die ID des Championship-Jahres
            positions: Liste der gewünschten Positionen (z.B. [1, 2, 3])
            
        Returns:
            Dictionary mit Position als Key und Team-Code als Value
        """
        # Diese Methode würde normalerweise aus einer berechneten Tabelle lesen
        # Für jetzt wird sie im Service implementiert
        return {}