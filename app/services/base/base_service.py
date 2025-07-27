"""
Base Service Class with Repository Pattern
Provides common business logic patterns for all services
"""

from typing import TypeVar, Generic, Optional, List, Dict, Any
from app.repositories.base import BaseRepository
from models import db
import logging

T = TypeVar('T')
logger = logging.getLogger(__name__)


class BaseService(Generic[T]):
    """
    Base service class providing common business operations
    All services should inherit from this class
    """
    
    def __init__(self, repository: BaseRepository[T]):
        """
        Initialize the service with a repository
        
        Args:
            repository: The repository instance for data access
        """
        self.repository = repository
        self.db = db
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def get_by_id(self, id: int) -> Optional[T]:
        """
        Get entity by ID
        
        Args:
            id: The primary key ID
            
        Returns:
            The entity if found, None otherwise
        """
        return self.repository.get_by_id(id)
    
    def get_all(self, **filters) -> List[T]:
        """
        Get all entities with optional filters
        
        Args:
            **filters: Optional filter criteria
            
        Returns:
            List of entities
        """
        if filters:
            return self.repository.find_all(**filters)
        return self.repository.find_all()
    
    def find_one(self, **criteria) -> Optional[T]:
        """
        Find single entity by criteria
        
        Args:
            **criteria: Search criteria
            
        Returns:
            First matching entity or None
        """
        return self.repository.find_one(**criteria)
    
    def find_by(self, criteria: Dict[str, Any], 
                order_by: Optional[str] = None,
                limit: Optional[int] = None) -> List[T]:
        """
        Find entities with advanced filtering
        
        Args:
            criteria: Dictionary of filter criteria
            order_by: Column to order by
            limit: Maximum number of results
            
        Returns:
            List of matching entities
        """
        return self.repository.find_by(criteria, order_by=order_by, limit=limit)
    
    def create(self, **kwargs) -> T:
        """
        Create new entity with validation
        
        Args:
            **kwargs: Entity attributes
            
        Returns:
            The created entity
        """
        # Validate before creation
        self._validate_create(kwargs)
        
        # Create entity
        entity = self.repository.create(**kwargs)
        
        # Post-creation hook
        self._after_create(entity)
        
        # Commit transaction
        self.commit()
        
        self.logger.info(f"Created entity with ID: {getattr(entity, 'id', 'N/A')}")
        return entity
    
    def update(self, id: int, **kwargs) -> Optional[T]:
        """
        Update existing entity with validation
        
        Args:
            id: The entity ID to update
            **kwargs: Attributes to update
            
        Returns:
            The updated entity if found, None otherwise
        """
        # Get existing entity
        entity = self.get_by_id(id)
        if not entity:
            self.logger.warning(f"Entity with ID {id} not found for update")
            return None
        
        # Validate before update
        self._validate_update(entity, kwargs)
        
        # Update entity
        updated_entity = self.repository.update(id, **kwargs)
        
        # Post-update hook
        self._after_update(updated_entity)
        
        # Commit transaction
        self.commit()
        
        self.logger.info(f"Updated entity with ID: {id}")
        return updated_entity
    
    def delete(self, id: int) -> bool:
        """
        Delete entity by ID with validation
        
        Args:
            id: The entity ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        # Get existing entity
        entity = self.get_by_id(id)
        if not entity:
            self.logger.warning(f"Entity with ID {id} not found for deletion")
            return False
        
        # Validate before deletion
        self._validate_delete(entity)
        
        # Delete entity
        result = self.repository.delete(id)
        
        # Post-deletion hook
        self._after_delete(entity)
        
        # Commit transaction
        self.commit()
        
        self.logger.info(f"Deleted entity with ID: {id}")
        return result
    
    def bulk_create(self, entities_data: List[Dict[str, Any]]) -> List[T]:
        """
        Create multiple entities at once with validation
        
        Args:
            entities_data: List of dictionaries with entity data
            
        Returns:
            List of created entities
        """
        # Validate all entities
        for data in entities_data:
            self._validate_create(data)
        
        # Create entities
        entities = self.repository.bulk_create(entities_data)
        
        # Post-creation hook for each
        for entity in entities:
            self._after_create(entity)
        
        # Commit transaction
        self.commit()
        
        self.logger.info(f"Bulk created {len(entities)} entities")
        return entities
    
    def exists(self, id: int) -> bool:
        """
        Check if entity exists by ID
        
        Args:
            id: The entity ID to check
            
        Returns:
            True if exists, False otherwise
        """
        return self.repository.exists(id)
    
    def count(self, **filters) -> int:
        """
        Count entities with optional filters
        
        Args:
            **filters: Optional filter criteria
            
        Returns:
            Count of entities
        """
        return self.repository.count(**filters)
    
    def paginate(self, page: int = 1, per_page: int = 20,
                 filters: Optional[Dict[str, Any]] = None,
                 order_by: Optional[str] = None) -> Dict[str, Any]:
        """
        Get paginated results
        
        Args:
            page: Page number (1-based)
            per_page: Items per page
            filters: Optional filter criteria
            order_by: Optional ordering
            
        Returns:
            Paginated results dictionary
        """
        return self.repository.paginate(
            page=page,
            per_page=per_page,
            filters=filters,
            order_by=order_by
        )
    
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
    
    def flush(self) -> None:
        """
        Flush pending changes without committing
        """
        self.db.session.flush()
    
    def refresh(self, entity: T) -> None:
        """
        Refresh entity from database
        
        Args:
            entity: The entity to refresh
        """
        self.repository.refresh(entity)
    
    # Validation hooks (to be overridden in subclasses)
    
    def _validate_create(self, data: Dict[str, Any]) -> None:
        """
        Validate data before creating entity
        Override in subclasses for specific validation
        
        Args:
            data: Entity data to validate
        """
        pass
    
    def _validate_update(self, entity: T, data: Dict[str, Any]) -> None:
        """
        Validate data before updating entity
        Override in subclasses for specific validation
        
        Args:
            entity: Existing entity
            data: Update data to validate
        """
        pass
    
    def _validate_delete(self, entity: T) -> None:
        """
        Validate before deleting entity
        Override in subclasses for specific validation
        
        Args:
            entity: Entity to be deleted
        """
        pass
    
    # Lifecycle hooks (to be overridden in subclasses)
    
    def _after_create(self, entity: T) -> None:
        """
        Hook called after entity creation
        Override in subclasses for post-creation logic
        
        Args:
            entity: Created entity
        """
        pass
    
    def _after_update(self, entity: T) -> None:
        """
        Hook called after entity update
        Override in subclasses for post-update logic
        
        Args:
            entity: Updated entity
        """
        pass
    
    def _after_delete(self, entity: T) -> None:
        """
        Hook called after entity deletion
        Override in subclasses for post-deletion logic
        
        Args:
            entity: Deleted entity
        """
        pass