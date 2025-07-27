"""
CacheManager - Zentrales Caching-System für Performance-Optimierung
Implementiert In-Memory und Redis-basiertes Caching mit TTL-Support
"""

import json
import time
from typing import Any, Dict, Optional, Union, Callable
from functools import wraps
from datetime import datetime, timedelta
import hashlib
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Cache-Manager für Service Layer
    
    Features:
    - In-Memory Caching mit TTL
    - Cache-Key-Generierung
    - Cache-Invalidierung
    - Performance-Metriken
    """
    
    def __init__(self, default_ttl: int = 300):
        """
        Initialisiert den Cache-Manager
        
        Args:
            default_ttl: Standard TTL in Sekunden (5 Minuten)
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl
        self.hit_count = 0
        self.miss_count = 0
        self.invalidation_count = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        Holt einen Wert aus dem Cache
        
        Args:
            key: Cache-Schlüssel
            
        Returns:
            Gecachter Wert oder None
        """
        if key in self.cache:
            entry = self.cache[key]
            if entry['expires_at'] > time.time():
                self.hit_count += 1
                logger.debug(f"Cache hit: {key}")
                return entry['value']
            else:
                # Eintrag abgelaufen
                del self.cache[key]
        
        self.miss_count += 1
        logger.debug(f"Cache miss: {key}")
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Speichert einen Wert im Cache
        
        Args:
            key: Cache-Schlüssel
            value: Zu cachender Wert
            ttl: Time-to-Live in Sekunden
        """
        ttl = ttl or self.default_ttl
        self.cache[key] = {
            'value': value,
            'expires_at': time.time() + ttl,
            'created_at': time.time()
        }
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
    
    def invalidate(self, pattern: Optional[str] = None):
        """
        Invalidiert Cache-Einträge
        
        Args:
            pattern: Optional - nur Keys mit diesem Muster löschen
        """
        if pattern:
            keys_to_delete = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self.cache[key]
                self.invalidation_count += 1
            logger.info(f"Invalidated {len(keys_to_delete)} cache entries with pattern: {pattern}")
        else:
            count = len(self.cache)
            self.cache.clear()
            self.invalidation_count += count
            logger.info(f"Invalidated all {count} cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Gibt Cache-Statistiken zurück
        
        Returns:
            Dictionary mit Statistiken
        """
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'entries': len(self.cache),
            'hits': self.hit_count,
            'misses': self.miss_count,
            'hit_rate': f"{hit_rate:.2f}%",
            'invalidations': self.invalidation_count,
            'memory_entries': self._get_memory_stats()
        }
    
    def _get_memory_stats(self) -> Dict[str, int]:
        """Berechnet Speicher-Statistiken"""
        stats = {
            'total_keys': len(self.cache),
            'expired_keys': 0,
            'active_keys': 0
        }
        
        current_time = time.time()
        for entry in self.cache.values():
            if entry['expires_at'] > current_time:
                stats['active_keys'] += 1
            else:
                stats['expired_keys'] += 1
        
        return stats
    
    @staticmethod
    def generate_key(*args, **kwargs) -> str:
        """
        Generiert einen Cache-Key aus Argumenten
        
        Returns:
            MD5-Hash als Cache-Key
        """
        # Kombiniere alle Argumente zu einem String
        key_parts = []
        
        # Füge positionale Argumente hinzu
        for arg in args:
            if isinstance(arg, (str, int, float, bool)):
                key_parts.append(str(arg))
            elif isinstance(arg, (list, tuple)):
                key_parts.append(json.dumps(sorted(arg)))
            elif isinstance(arg, dict):
                key_parts.append(json.dumps(arg, sort_keys=True))
            else:
                key_parts.append(str(type(arg)))
        
        # Füge Keyword-Argumente hinzu
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        
        # Erstelle Hash
        key_string = ":".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()


def cached(ttl: Optional[int] = None, key_prefix: Optional[str] = None):
    """
    Decorator für Caching von Funktions-Ergebnissen
    
    Args:
        ttl: Time-to-Live in Sekunden
        key_prefix: Prefix für Cache-Keys
        
    Example:
        @cached(ttl=600, key_prefix="standings")
        def get_standings(year_id):
            return expensive_calculation()
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Stelle sicher, dass self einen cache_manager hat
            if not hasattr(self, 'cache_manager'):
                # Führe Funktion ohne Caching aus
                return func(self, *args, **kwargs)
            
            # Generiere Cache-Key
            prefix = key_prefix or f"{self.__class__.__name__}.{func.__name__}"
            cache_key = f"{prefix}:{CacheManager.generate_key(*args, **kwargs)}"
            
            # Prüfe Cache
            cached_value = self.cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Führe Funktion aus
            result = func(self, *args, **kwargs)
            
            # Cache Ergebnis
            self.cache_manager.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


class CacheableService:
    """
    Mixin für Services mit Caching-Support
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_manager = CacheManager()
    
    def invalidate_cache(self, pattern: Optional[str] = None):
        """
        Invalidiert Service-Cache
        
        Args:
            pattern: Optional - nur Keys mit diesem Muster löschen
        """
        if hasattr(self, 'cache_manager'):
            self.cache_manager.invalidate(pattern)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Gibt Cache-Statistiken zurück
        
        Returns:
            Dictionary mit Statistiken
        """
        if hasattr(self, 'cache_manager'):
            return self.cache_manager.get_stats()
        return {}


# Globale Cache-Instanz für gemeinsame Nutzung
_global_cache = CacheManager(default_ttl=300)


def get_global_cache() -> CacheManager:
    """Gibt die globale Cache-Instanz zurück"""
    return _global_cache


def invalidate_standings_cache(year_id: Optional[int] = None):
    """
    Invalidiert Standings-bezogene Cache-Einträge
    
    Args:
        year_id: Optional - nur für dieses Jahr invalidieren
    """
    if year_id:
        pattern = f"standings:{year_id}"
    else:
        pattern = "standings:"
    
    _global_cache.invalidate(pattern)
    logger.info(f"Invalidated standings cache for pattern: {pattern}")


def invalidate_team_cache(team_code: Optional[str] = None):
    """
    Invalidiert Team-bezogene Cache-Einträge
    
    Args:
        team_code: Optional - nur für dieses Team invalidieren
    """
    if team_code:
        pattern = f"team:{team_code}"
    else:
        pattern = "team:"
    
    _global_cache.invalidate(pattern)
    logger.info(f"Invalidated team cache for pattern: {pattern}")