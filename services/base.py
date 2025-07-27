"""
Base Service Class for IIHF World Championship Statistics
Provides common database operations and patterns for all services
"""

from typing import TypeVar, Generic, Optional, List, Dict, Any
from sqlalchemy.orm import Session
from models import db
import logging

T = TypeVar('T')
logger = logging.getLogger(__name__)

class BaseService(Generic[T]):
    """
    Base service class providing common database operations
    All services should inherit from this class
    """
    
    def __init__(self, model_class: type[T]):
        """
        Initialize the service with a model class
        
        Args:
            model_class: The SQLAlchemy model class this service manages
        """
        self.model_class = model_class
        self.db = db
        self.logger = logging.getLogger(f"{__name__}.{model_class.__name__}Service")
    
    def get_by_id(self, id: int, session: Optional[Session] = None) -> Optional[T]:
        """
        Get entity by ID with optional session
        
        Args:
            id: The primary key ID
            session: Optional database session
            
        Returns:
            The entity if found, None otherwise
        """
        session = session or self.db.session
        return session.get(self.model_class, id)
    
    def get_all(self, session: Optional[Session] = None) -> List[T]:
        """
        Get all entities
        
        Args:
            session: Optional database session
            
        Returns:
            List of all entities
        """
        session = session or self.db.session
        return session.query(self.model_class).all()
    
    def filter_by(self, session: Optional[Session] = None, **kwargs) -> List[T]:
        """
        Filter entities by given criteria
        
        Args:
            session: Optional database session
            **kwargs: Filter criteria
            
        Returns:
            List of filtered entities
        """
        session = session or self.db.session
        return session.query(self.model_class).filter_by(**kwargs).all()
    
    def create(self, commit: bool = True, **kwargs) -> T:
        """
        Create new entity
        
        Args:
            commit: Whether to commit the transaction
            **kwargs: Entity attributes
            
        Returns:
            The created entity
        """
        entity = self.model_class(**kwargs)
        self.db.session.add(entity)
        
        if commit:
            self.commit()
        
        self.logger.info(f"Created {self.model_class.__name__} with ID: {entity.id}")
        return entity
    
    def update(self, id: int, commit: bool = True, **kwargs) -> Optional[T]:
        """
        Update existing entity
        
        Args:
            id: The entity ID to update
            commit: Whether to commit the transaction
            **kwargs: Attributes to update
            
        Returns:
            The updated entity if found, None otherwise
        """
        entity = self.get_by_id(id)
        if entity:
            for key, value in kwargs.items():
                if hasattr(entity, key):
                    setattr(entity, key, value)
                else:
                    self.logger.warning(f"Attribute {key} not found on {self.model_class.__name__}")
            
            if commit:
                self.commit()
            
            self.logger.info(f"Updated {self.model_class.__name__} with ID: {id}")
        else:
            self.logger.warning(f"{self.model_class.__name__} with ID {id} not found for update")
        
        return entity
    
    def delete(self, id: int, commit: bool = True) -> bool:
        """
        Delete entity by ID
        
        Args:
            id: The entity ID to delete
            commit: Whether to commit the transaction
            
        Returns:
            True if deleted, False if not found
        """
        entity = self.get_by_id(id)
        if entity:
            self.db.session.delete(entity)
            
            if commit:
                self.commit()
            
            self.logger.info(f"Deleted {self.model_class.__name__} with ID: {id}")
            return True
        
        self.logger.warning(f"{self.model_class.__name__} with ID {id} not found for deletion")
        return False
    
    def bulk_create(self, entities_data: List[Dict[str, Any]], commit: bool = True) -> List[T]:
        """
        Create multiple entities at once
        
        Args:
            entities_data: List of dictionaries with entity data
            commit: Whether to commit the transaction
            
        Returns:
            List of created entities
        """
        entities = []
        for data in entities_data:
            entity = self.model_class(**data)
            self.db.session.add(entity)
            entities.append(entity)
        
        if commit:
            self.commit()
        
        self.logger.info(f"Bulk created {len(entities)} {self.model_class.__name__} entities")
        return entities
    
    def exists(self, id: int) -> bool:
        """
        Check if entity exists by ID
        
        Args:
            id: The entity ID to check
            
        Returns:
            True if exists, False otherwise
        """
        return self.db.session.query(
            self.db.session.query(self.model_class).filter_by(id=id).exists()
        ).scalar()
    
    def count(self, **filters) -> int:
        """
        Count entities with optional filters
        
        Args:
            **filters: Optional filter criteria
            
        Returns:
            Count of entities
        """
        query = self.db.session.query(self.model_class)
        if filters:
            query = query.filter_by(**filters)
        return query.count()
    
    def commit(self) -> None:
        """
        Commit current transaction
        """
        try:
            self.db.session.commit()
            self.logger.debug("Transaction committed successfully")
        except Exception as e:
            self.logger.error(f"Error committing transaction: {str(e)}")
            self.rollback()
            raise
    
    def rollback(self) -> None:
        """
        Rollback current transaction
        """
        self.db.session.rollback()
        self.logger.info("Transaction rolled back")
    
    def refresh(self, entity: T) -> None:
        """
        Refresh entity from database
        
        Args:
            entity: The entity to refresh
        """
        self.db.session.refresh(entity)
    
    def expunge(self, entity: T) -> None:
        """
        Remove entity from session
        
        Args:
            entity: The entity to expunge
        """
        self.db.session.expunge(entity)
    
    def flush(self) -> None:
        """
        Flush pending changes to database without committing
        """
        self.db.session.flush()