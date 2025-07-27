"""
Game Repository für IIHF World Championship Statistics
Handhabt spezifische Datenbankoperationen für Spiele
"""

from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import and_, or_, func
from models import Game, ShotsOnGoal, Goal, Penalty, GameOverrule
from .base import BaseRepository
import logging

logger = logging.getLogger(__name__)


class GameRepository(BaseRepository[Game]):
    """
    Repository für spielbezogene Datenbankoperationen
    """
    
    def __init__(self):
        super().__init__(Game)
    
    def find_by_year(self, year_id: int) -> List[Game]:
        """
        Findet alle Spiele eines Championship-Jahres
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Liste aller Spiele des Jahres
        """
        return self.find_by(year_id=year_id)
    
    def find_by_round(self, year_id: int, round_name: str) -> List[Game]:
        """
        Findet alle Spiele einer bestimmten Runde
        
        Args:
            year_id: Die ID des Championship-Jahres
            round_name: Der Name der Runde (z.B. 'Group Stage', 'Quarterfinals')
            
        Returns:
            Liste aller Spiele der Runde
        """
        return self.find_by(year_id=year_id, round=round_name)
    
    def find_by_group(self, year_id: int, group: str) -> List[Game]:
        """
        Findet alle Spiele einer Gruppe
        
        Args:
            year_id: Die ID des Championship-Jahres
            group: Die Gruppe (z.B. 'A', 'B')
            
        Returns:
            Liste aller Spiele der Gruppe
        """
        return self.find_by(year_id=year_id, group=group)
    
    def find_by_teams(self, year_id: int, team1: str, team2: str) -> Optional[Game]:
        """
        Findet ein Spiel zwischen zwei Teams
        
        Args:
            year_id: Die ID des Championship-Jahres
            team1: Code des ersten Teams
            team2: Code des zweiten Teams
            
        Returns:
            Das Spiel falls gefunden, sonst None
        """
        try:
            return self.session.query(Game).filter(
                and_(
                    Game.year_id == year_id,
                    or_(
                        and_(Game.team1_code == team1, Game.team2_code == team2),
                        and_(Game.team1_code == team2, Game.team2_code == team1)
                    )
                )
            ).first()
        except Exception as e:
            self.logger.error(f"Fehler beim Suchen des Spiels zwischen {team1} und {team2}: {str(e)}")
            return None
    
    def find_completed_games(self, year_id: int) -> List[Game]:
        """
        Findet alle abgeschlossenen Spiele (mit Ergebnis)
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Liste aller abgeschlossenen Spiele
        """
        try:
            return self.session.query(Game).filter(
                and_(
                    Game.year_id == year_id,
                    Game.team1_score.isnot(None),
                    Game.team2_score.isnot(None)
                )
            ).all()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen abgeschlossener Spiele: {str(e)}")
            return []
    
    def find_upcoming_games(self, year_id: int) -> List[Game]:
        """
        Findet alle anstehenden Spiele (ohne Ergebnis)
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Liste aller anstehenden Spiele
        """
        try:
            return self.session.query(Game).filter(
                and_(
                    Game.year_id == year_id,
                    or_(
                        Game.team1_score.is_(None),
                        Game.team2_score.is_(None)
                    )
                )
            ).all()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen anstehender Spiele: {str(e)}")
            return []
    
    def get_shots_on_goal(self, game_id: int) -> List[ShotsOnGoal]:
        """
        Holt alle Shots on Goal für ein Spiel
        
        Args:
            game_id: Die Spiel-ID
            
        Returns:
            Liste aller SOG-Einträge
        """
        try:
            return self.session.query(ShotsOnGoal).filter_by(game_id=game_id).all()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der SOG für Spiel {game_id}: {str(e)}")
            return []
    
    def get_goals(self, game_id: int) -> List[Goal]:
        """
        Holt alle Tore eines Spiels
        
        Args:
            game_id: Die Spiel-ID
            
        Returns:
            Liste aller Tore
        """
        try:
            return self.session.query(Goal).filter_by(game_id=game_id).all()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der Tore für Spiel {game_id}: {str(e)}")
            return []
    
    def get_penalties(self, game_id: int) -> List[Penalty]:
        """
        Holt alle Strafen eines Spiels
        
        Args:
            game_id: Die Spiel-ID
            
        Returns:
            Liste aller Strafen
        """
        try:
            return self.session.query(Penalty).filter_by(game_id=game_id).all()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der Strafen für Spiel {game_id}: {str(e)}")
            return []
    
    def get_overrule(self, game_id: int) -> Optional[GameOverrule]:
        """
        Holt die Overrule-Information eines Spiels
        
        Args:
            game_id: Die Spiel-ID
            
        Returns:
            Die Overrule falls vorhanden, sonst None
        """
        try:
            return self.session.query(GameOverrule).filter_by(game_id=game_id).first()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der Overrule für Spiel {game_id}: {str(e)}")
            return None
    
    def get_games_with_overtime(self, year_id: int) -> List[Game]:
        """
        Findet alle Spiele mit Verlängerung oder Penaltyschiessen
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Liste aller OT/SO-Spiele
        """
        try:
            return self.session.query(Game).filter(
                and_(
                    Game.year_id == year_id,
                    Game.result_type.in_(['OT', 'SO'])
                )
            ).all()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der OT/SO-Spiele: {str(e)}")
            return []
    
    def get_team_games(self, year_id: int, team_code: str) -> List[Game]:
        """
        Findet alle Spiele eines bestimmten Teams
        
        Args:
            year_id: Die ID des Championship-Jahres
            team_code: Der Team-Code
            
        Returns:
            Liste aller Spiele des Teams
        """
        try:
            return self.session.query(Game).filter(
                and_(
                    Game.year_id == year_id,
                    or_(
                        Game.team1_code == team_code,
                        Game.team2_code == team_code
                    )
                )
            ).all()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der Spiele für Team {team_code}: {str(e)}")
            return []
    
    def count_games_by_result_type(self, year_id: int) -> Dict[str, int]:
        """
        Zählt Spiele nach Ergebnistyp
        
        Args:
            year_id: Die ID des Championship-Jahres
            
        Returns:
            Dictionary mit Ergebnistyp als Schlüssel und Anzahl als Wert
        """
        try:
            results = self.session.query(
                Game.result_type,
                func.count(Game.id)
            ).filter(
                and_(
                    Game.year_id == year_id,
                    Game.result_type.isnot(None)
                )
            ).group_by(Game.result_type).all()
            
            return {result_type: count for result_type, count in results}
        except Exception as e:
            self.logger.error(f"Fehler beim Zählen nach Ergebnistyp: {str(e)}")
            return {}
    
    def save_shots_on_goal(self, sog: ShotsOnGoal) -> ShotsOnGoal:
        """
        Speichert einen Shots-on-Goal-Eintrag
        
        Args:
            sog: Der zu speichernde SOG-Eintrag
            
        Returns:
            Der gespeicherte Eintrag
        """
        try:
            self.session.add(sog)
            self.session.flush()
            return sog
        except Exception as e:
            self.logger.error(f"Fehler beim Speichern der SOG: {str(e)}")
            raise
    
    def delete_shots_on_goal(self, game_id: int, team_code: Optional[str] = None) -> int:
        """
        Löscht Shots-on-Goal-Einträge für ein Spiel
        
        Args:
            game_id: Die Spiel-ID
            team_code: Optional - nur für ein bestimmtes Team löschen
            
        Returns:
            Anzahl der gelöschten Einträge
        """
        try:
            query = self.session.query(ShotsOnGoal).filter_by(game_id=game_id)
            if team_code:
                query = query.filter_by(team_code=team_code)
            
            count = query.count()
            query.delete()
            self.session.flush()
            return count
        except Exception as e:
            self.logger.error(f"Fehler beim Löschen der SOG: {str(e)}")
            raise