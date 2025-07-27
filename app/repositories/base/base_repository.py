"""
Base Repository Class for IIHF World Championship Statistics
Provides data access patterns and query abstractions
"""

from typing import TypeVar, Generic, Optional, List, Dict, Any, Union, Callable
from sqlalchemy.orm import Session, Query
from sqlalchemy import and_, or_, desc, asc
from models import db
import logging

T = TypeVar('T')
logger = logging.getLogger(__name__)


class BaseRepository(Generic[T]):
    """
    Base repository providing data access patterns
    All repositories should inherit from this class
    """
    
    def __init__(self, model_class: type[T]):
        """
        Initialize the repository with a model class
        
        Args:
            model_class: The SQLAlchemy model class this repository manages
        """
        self.model_class = model_class
        self.db = db
        self.logger = logging.getLogger(f"{__name__}.{model_class.__name__}Repository")
    
    def get_by_id(self, id: int, session: Optional[Session] = None) -> Optional[T]:
        """
        Get entity by ID
        
        Args:
            id: The primary key ID
            session: Optional database session
            
        Returns:
            The entity if found, None otherwise
        """
        session = session or self.db.session
        return session.get(self.model_class, id)
    
    def find_one(self, session: Optional[Session] = None, **filters) -> Optional[T]:
        """
        Find single entity by filters
        
        Args:
            session: Optional database session
            **filters: Filter criteria
            
        Returns:
            First matching entity or None
        """
        session = session or self.db.session
        return session.query(self.model_class).filter_by(**filters).first()
    
    def find_all(self, session: Optional[Session] = None, **filters) -> List[T]:
        """
        Find all entities matching filters
        
        Args:
            session: Optional database session
            **filters: Filter criteria
            
        Returns:
            List of matching entities
        """
        session = session or self.db.session
        return session.query(self.model_class).filter_by(**filters).all()
    
    def find_by(self, criteria: Dict[str, Any], 
                order_by: Optional[Union[str, List[str]]] = None,
                limit: Optional[int] = None,
                offset: Optional[int] = None,
                session: Optional[Session] = None) -> List[T]:
        """
        Find entities with advanced filtering
        
        Args:
            criteria: Dictionary of filter criteria
            order_by: Column(s) to order by
            limit: Maximum number of results
            offset: Number of results to skip
            session: Optional database session
            
        Returns:
            List of matching entities
        """
        session = session or self.db.session
        query = session.query(self.model_class)
        
        # Apply filters
        for key, value in criteria.items():
            if hasattr(self.model_class, key):
                query = query.filter(getattr(self.model_class, key) == value)
        
        # Apply ordering
        if order_by:
            if isinstance(order_by, str):
                order_by = [order_by]
            
            for order in order_by:
                if order.startswith('-'):
                    # Descending order
                    column = order[1:]
                    if hasattr(self.model_class, column):
                        query = query.order_by(desc(getattr(self.model_class, column)))
                else:
                    # Ascending order
                    if hasattr(self.model_class, order):
                        query = query.order_by(asc(getattr(self.model_class, order)))
        
        # Apply pagination
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def create(self, commit: bool = False, **kwargs) -> T:
        """
        Create new entity
        
        Args:
            commit: Whether to commit immediately
            **kwargs: Entity attributes
            
        Returns:
            The created entity
        """
        entity = self.model_class(**kwargs)
        self.db.session.add(entity)
        
        if commit:
            self.db.session.commit()
        else:
            self.db.session.flush()
        
        self.logger.info(f"Created {self.model_class.__name__} with ID: {getattr(entity, 'id', 'N/A')}")
        return entity
    
    def bulk_create(self, entities_data: List[Dict[str, Any]], 
                    commit: bool = False) -> List[T]:
        """
        Create multiple entities at once
        
        Args:
            entities_data: List of dictionaries with entity data
            commit: Whether to commit immediately
            
        Returns:
            List of created entities
        """
        entities = []
        for data in entities_data:
            entity = self.model_class(**data)
            self.db.session.add(entity)
            entities.append(entity)
        
        if commit:
            self.db.session.commit()
        else:
            self.db.session.flush()
        
        self.logger.info(f"Bulk created {len(entities)} {self.model_class.__name__} entities")
        return entities
    
    def update(self, id: int, commit: bool = False, **kwargs) -> Optional[T]:
        """
        Update entity by ID
        
        Args:
            id: The entity ID to update
            commit: Whether to commit immediately
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
                self.db.session.commit()
            else:
                self.db.session.flush()
            
            self.logger.info(f"Updated {self.model_class.__name__} with ID: {id}")
        else:
            self.logger.warning(f"{self.model_class.__name__} with ID {id} not found for update")
        
        return entity
    
    def update_by(self, criteria: Dict[str, Any], 
                  updates: Dict[str, Any],
                  commit: bool = False) -> int:
        """
        Update multiple entities matching criteria
        
        Args:
            criteria: Filter criteria
            updates: Dictionary of updates to apply
            commit: Whether to commit immediately
            
        Returns:
            Number of updated entities
        """
        query = self.db.session.query(self.model_class)
        
        for key, value in criteria.items():
            if hasattr(self.model_class, key):
                query = query.filter(getattr(self.model_class, key) == value)
        
        count = query.update(updates)
        
        if commit:
            self.db.session.commit()
        else:
            self.db.session.flush()
        
        self.logger.info(f"Updated {count} {self.model_class.__name__} entities")
        return count
    
    def delete(self, id: int, commit: bool = False) -> bool:
        """
        Delete entity by ID
        
        Args:
            id: The entity ID to delete
            commit: Whether to commit immediately
            
        Returns:
            True if deleted, False if not found
        """
        entity = self.get_by_id(id)
        if entity:
            self.db.session.delete(entity)
            
            if commit:
                self.db.session.commit()
            else:
                self.db.session.flush()
            
            self.logger.info(f"Deleted {self.model_class.__name__} with ID: {id}")
            return True
        
        self.logger.warning(f"{self.model_class.__name__} with ID {id} not found for deletion")
        return False
    
    def delete_by(self, criteria: Dict[str, Any], commit: bool = False) -> int:
        """
        Delete multiple entities matching criteria
        
        Args:
            criteria: Filter criteria
            commit: Whether to commit immediately
            
        Returns:
            Number of deleted entities
        """
        query = self.db.session.query(self.model_class)
        
        for key, value in criteria.items():
            if hasattr(self.model_class, key):
                query = query.filter(getattr(self.model_class, key) == value)
        
        count = 0
        for entity in query.all():
            self.db.session.delete(entity)
            count += 1
        
        if commit:
            self.db.session.commit()
        else:
            self.db.session.flush()
        
        self.logger.info(f"Deleted {count} {self.model_class.__name__} entities")
        return count
    
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
    
    def exists_by(self, **criteria) -> bool:
        """
        Check if entity exists by criteria
        
        Args:
            **criteria: Filter criteria
            
        Returns:
            True if exists, False otherwise
        """
        return self.db.session.query(
            self.db.session.query(self.model_class).filter_by(**criteria).exists()
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
    
    def get_query(self, session: Optional[Session] = None) -> Query:
        """
        Get base query for advanced operations
        
        Args:
            session: Optional database session
            
        Returns:
            SQLAlchemy Query object
        """
        session = session or self.db.session
        return session.query(self.model_class)
    
    def paginate(self, page: int = 1, per_page: int = 20,
                 filters: Optional[Dict[str, Any]] = None,
                 order_by: Optional[Union[str, List[str]]] = None) -> Dict[str, Any]:
        """
        Paginate query results
        
        Args:
            page: Page number (1-based)
            per_page: Items per page
            filters: Optional filter criteria
            order_by: Optional ordering
            
        Returns:
            Dictionary with items, total, page, per_page, pages
        """
        query = self.get_query()
        
        # Apply filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)
        
        # Apply ordering
        if order_by:
            if isinstance(order_by, str):
                order_by = [order_by]
            
            for order in order_by:
                if order.startswith('-'):
                    column = order[1:]
                    if hasattr(self.model_class, column):
                        query = query.order_by(desc(getattr(self.model_class, column)))
                else:
                    if hasattr(self.model_class, order):
                        query = query.order_by(asc(getattr(self.model_class, order)))
        
        # Calculate pagination
        total = query.count()
        pages = (total + per_page - 1) // per_page
        offset = (page - 1) * per_page
        
        items = query.offset(offset).limit(per_page).all()
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': pages,
            'has_prev': page > 1,
            'has_next': page < pages
        }
    
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
    
    def execute_query(self, query_func: Callable[[], Any]) -> Any:
        """
        Execute a custom query function
        
        Args:
            query_func: Function that returns query result
            
        Returns:
            Query result
        """
        try:
            return query_func()
        except Exception as e:
            self.logger.error(f"Error executing custom query: {str(e)}")
            raise