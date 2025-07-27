"""
Base Repository Class für IIHF World Championship Statistics
Stellt grundlegende Datenbankoperationen für alle Repositories bereit
"""

from typing import TypeVar, Generic, Optional, List, Dict, Any, Type
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from sqlalchemy import and_, or_
from models import db
import logging

T = TypeVar('T')
logger = logging.getLogger(__name__)


class BaseRepository(Generic[T]):
    """
    Basis-Repository-Klasse für Datenbankoperationen
    Alle Repositories sollten von dieser Klasse erben
    """
    
    def __init__(self, model_class: Type[T]):
        """
        Initialisiert das Repository mit einer Model-Klasse
        
        Args:
            model_class: Die SQLAlchemy Model-Klasse, die dieses Repository verwaltet
        """
        self.model_class = model_class
        self.db = db
        self._session = db.session
        self.logger = logging.getLogger(f"{__name__}.{model_class.__name__}Repository")
    
    @property
    def session(self) -> Session:
        """Gibt die aktuelle Datenbank-Session zurück"""
        return self._session
    
    def find_by_id(self, entity_id: int) -> Optional[T]:
        """
        Findet eine Entität anhand ihrer ID
        
        Args:
            entity_id: Die Primärschlüssel-ID
            
        Returns:
            Die Entität falls gefunden, sonst None
        """
        try:
            return self.session.get(self.model_class, entity_id)
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen von {self.model_class.__name__} mit ID {entity_id}: {str(e)}")
            return None
    
    def find_all(self) -> List[T]:
        """
        Gibt alle Entitäten zurück
        
        Returns:
            Liste aller Entitäten
        """
        try:
            return self.session.query(self.model_class).all()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen aller {self.model_class.__name__}: {str(e)}")
            return []
    
    def find_by(self, **kwargs) -> List[T]:
        """
        Findet Entitäten anhand gegebener Kriterien
        
        Args:
            **kwargs: Filterkriterien
            
        Returns:
            Liste der gefilterten Entitäten
        """
        try:
            return self.session.query(self.model_class).filter_by(**kwargs).all()
        except Exception as e:
            self.logger.error(f"Fehler beim Filtern von {self.model_class.__name__}: {str(e)}")
            return []
    
    def find_one_by(self, **kwargs) -> Optional[T]:
        """
        Findet eine einzelne Entität anhand gegebener Kriterien
        
        Args:
            **kwargs: Filterkriterien
            
        Returns:
            Die erste gefundene Entität oder None
        """
        try:
            return self.session.query(self.model_class).filter_by(**kwargs).first()
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen von {self.model_class.__name__}: {str(e)}")
            return None
    
    def save(self, entity: T) -> T:
        """
        Speichert eine Entität (erstellt neue oder aktualisiert bestehende)
        
        Args:
            entity: Die zu speichernde Entität
            
        Returns:
            Die gespeicherte Entität
        """
        try:
            self.session.add(entity)
            self.session.flush()
            return entity
        except Exception as e:
            self.logger.error(f"Fehler beim Speichern von {self.model_class.__name__}: {str(e)}")
            raise
    
    def save_all(self, entities: List[T]) -> List[T]:
        """
        Speichert mehrere Entitäten auf einmal
        
        Args:
            entities: Liste der zu speichernden Entitäten
            
        Returns:
            Liste der gespeicherten Entitäten
        """
        try:
            self.session.add_all(entities)
            self.session.flush()
            return entities
        except Exception as e:
            self.logger.error(f"Fehler beim Massenspeichern von {self.model_class.__name__}: {str(e)}")
            raise
    
    def delete(self, entity: T) -> bool:
        """
        Löscht eine Entität
        
        Args:
            entity: Die zu löschende Entität
            
        Returns:
            True wenn erfolgreich gelöscht
        """
        try:
            self.session.delete(entity)
            self.session.flush()
            return True
        except Exception as e:
            self.logger.error(f"Fehler beim Löschen von {self.model_class.__name__}: {str(e)}")
            raise
    
    def delete_by_id(self, entity_id: int) -> bool:
        """
        Löscht eine Entität anhand ihrer ID
        
        Args:
            entity_id: Die ID der zu löschenden Entität
            
        Returns:
            True wenn gelöscht, False wenn nicht gefunden
        """
        entity = self.find_by_id(entity_id)
        if entity:
            return self.delete(entity)
        return False
    
    def exists(self, entity_id: int) -> bool:
        """
        Prüft ob eine Entität mit der gegebenen ID existiert
        
        Args:
            entity_id: Die zu prüfende ID
            
        Returns:
            True wenn existiert, sonst False
        """
        try:
            return self.session.query(
                self.session.query(self.model_class).filter_by(id=entity_id).exists()
            ).scalar()
        except Exception as e:
            self.logger.error(f"Fehler beim Prüfen der Existenz: {str(e)}")
            return False
    
    def count(self, **filters) -> int:
        """
        Zählt Entitäten mit optionalen Filtern
        
        Args:
            **filters: Optionale Filterkriterien
            
        Returns:
            Anzahl der Entitäten
        """
        try:
            query = self.session.query(self.model_class)
            if filters:
                query = query.filter_by(**filters)
            return query.count()
        except Exception as e:
            self.logger.error(f"Fehler beim Zählen: {str(e)}")
            return 0
    
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Führt eine benutzerdefinierte SQL-Abfrage aus
        
        Args:
            query: Die SQL-Abfrage
            params: Optionale Parameter für die Abfrage
            
        Returns:
            Liste der Ergebnisse
        """
        try:
            result = self.session.execute(text(query), params or {})
            return result.fetchall()
        except Exception as e:
            self.logger.error(f"Fehler beim Ausführen der Abfrage: {str(e)}")
            raise
    
    def refresh(self, entity: T) -> None:
        """
        Aktualisiert eine Entität aus der Datenbank
        
        Args:
            entity: Die zu aktualisierende Entität
        """
        try:
            self.session.refresh(entity)
        except Exception as e:
            self.logger.error(f"Fehler beim Aktualisieren: {str(e)}")
            raise
    
    def expunge(self, entity: T) -> None:
        """
        Entfernt eine Entität aus der Session
        
        Args:
            entity: Die zu entfernende Entität
        """
        try:
            self.session.expunge(entity)
        except Exception as e:
            self.logger.error(f"Fehler beim Entfernen aus Session: {str(e)}")
            raise