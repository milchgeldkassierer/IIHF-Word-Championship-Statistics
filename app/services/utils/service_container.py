"""
Service Container for Dependency Injection
Manages service and repository instances
"""

from typing import Dict, Any, Optional, List
from app.repositories.core import GameRepository
from app.services.core import GameService
import logging

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    Simple dependency injection container for services and repositories
    Provides centralized management of service instances
    """
    
    def __init__(self):
        """Initialize the container"""
        self._repositories: Dict[str, Any] = {}
        self._services: Dict[str, Any] = {}
        self._initialized = False
    
    def initialize(self) -> None:
        """
        Initialize all repositories and services
        Called once during application startup
        """
        if self._initialized:
            logger.warning("Service container already initialized")
            return
        
        try:
            # Initialize repositories
            self._initialize_repositories()
            
            # Initialize services with dependencies
            self._initialize_services()
            
            self._initialized = True
            logger.info("Service container initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize service container: {str(e)}")
            raise
    
    def _initialize_repositories(self) -> None:
        """Initialize all repository instances"""
        # Core repositories
        self._repositories['game'] = GameRepository()
        
        # Future repositories will be added here
        # self._repositories['player'] = PlayerRepository()
        # self._repositories['team'] = TeamRepository()
        # self._repositories['tournament'] = TournamentRepository()
        
        logger.info(f"Initialized {len(self._repositories)} repositories")
    
    def _initialize_services(self) -> None:
        """Initialize all service instances with their dependencies"""
        # Core services
        self._services['game'] = GameService(self._repositories['game'])
        
        # Future services will be added here
        # self._services['player'] = PlayerService(self._repositories['player'])
        # self._services['team'] = TeamService(self._repositories['team'])
        # self._services['tournament'] = TournamentService(self._repositories['tournament'])
        
        # Statistics services
        # self._services['standings'] = StandingsService(
        #     self._repositories['game'],
        #     self._repositories['team']
        # )
        # self._services['records'] = RecordsService(
        #     self._repositories['game'],
        #     self._repositories['player'],
        #     self._repositories['team']
        # )
        
        logger.info(f"Initialized {len(self._services)} services")
    
    def get_service(self, name: str) -> Optional[Any]:
        """
        Get service by name
        
        Args:
            name: Service name (e.g., 'game', 'player', 'team')
            
        Returns:
            Service instance or None if not found
        """
        if not self._initialized:
            raise RuntimeError("Service container not initialized. Call initialize() first.")
        
        service = self._services.get(name)
        if not service:
            logger.warning(f"Service '{name}' not found in container")
        
        return service
    
    def get_repository(self, name: str) -> Optional[Any]:
        """
        Get repository by name
        
        Args:
            name: Repository name (e.g., 'game', 'player', 'team')
            
        Returns:
            Repository instance or None if not found
        """
        if not self._initialized:
            raise RuntimeError("Service container not initialized. Call initialize() first.")
        
        repository = self._repositories.get(name)
        if not repository:
            logger.warning(f"Repository '{name}' not found in container")
        
        return repository
    
    def list_services(self) -> List[str]:
        """
        Get list of available service names
        
        Returns:
            List of service names
        """
        return list(self._services.keys())
    
    def list_repositories(self) -> List[str]:
        """
        Get list of available repository names
        
        Returns:
            List of repository names
        """
        return list(self._repositories.keys())
    
    def reset(self) -> None:
        """
        Reset the container, clearing all instances
        Useful for testing
        """
        self._repositories.clear()
        self._services.clear()
        self._initialized = False
        logger.info("Service container reset")


# Global container instance
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """
    Get the global service container instance
    
    Returns:
        ServiceContainer instance
    """
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def get_service(name: str) -> Any:
    """
    Convenience function to get a service from the global container
    
    Args:
        name: Service name
        
    Returns:
        Service instance
        
    Raises:
        RuntimeError: If container not initialized
        ValueError: If service not found
    """
    container = get_container()
    if not container._initialized:
        container.initialize()
    
    service = container.get_service(name)
    if service is None:
        raise ValueError(f"Service '{name}' not found")
    
    return service


def get_repository(name: str) -> Any:
    """
    Convenience function to get a repository from the global container
    
    Args:
        name: Repository name
        
    Returns:
        Repository instance
        
    Raises:
        RuntimeError: If container not initialized
        ValueError: If repository not found
    """
    container = get_container()
    if not container._initialized:
        container.initialize()
    
    repository = container.get_repository(name)
    if repository is None:
        raise ValueError(f"Repository '{name}' not found")
    
    return repository