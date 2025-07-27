"""
PerformanceMonitor - Überwacht und analysiert die Performance der Service Layer
Trackt Query-Zeiten, Cache-Effizienz und identifiziert Bottlenecks
"""

import time
import functools
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Container für Performance-Metriken"""
    
    def __init__(self):
        self.execution_times: List[float] = []
        self.query_counts: Dict[str, int] = defaultdict(int)
        self.cache_hits = 0
        self.cache_misses = 0
        self.slow_queries: List[Dict[str, Any]] = []
        self.n_plus_one_detections: List[Dict[str, Any]] = []
    
    def add_execution(self, duration: float, query_type: str = 'unknown'):
        """Fügt eine Ausführungszeit hinzu"""
        self.execution_times.append(duration)
        self.query_counts[query_type] += 1
        
        # Slow Query Detection (> 100ms)
        if duration > 0.1:
            self.slow_queries.append({
                'query_type': query_type,
                'duration': duration,
                'timestamp': datetime.now()
            })
    
    def get_statistics(self) -> Dict[str, Any]:
        """Berechnet Statistiken"""
        if not self.execution_times:
            return {
                'count': 0,
                'total_time': 0,
                'avg_time': 0,
                'min_time': 0,
                'max_time': 0,
                'p95_time': 0,
                'p99_time': 0
            }
        
        sorted_times = sorted(self.execution_times)
        count = len(sorted_times)
        
        return {
            'count': count,
            'total_time': sum(sorted_times),
            'avg_time': sum(sorted_times) / count,
            'min_time': sorted_times[0],
            'max_time': sorted_times[-1],
            'p95_time': sorted_times[int(count * 0.95)] if count > 20 else sorted_times[-1],
            'p99_time': sorted_times[int(count * 0.99)] if count > 100 else sorted_times[-1],
            'query_breakdown': dict(self.query_counts),
            'cache_hit_rate': self._calculate_cache_hit_rate(),
            'slow_queries_count': len(self.slow_queries),
            'n_plus_one_count': len(self.n_plus_one_detections)
        }
    
    def _calculate_cache_hit_rate(self) -> float:
        """Berechnet die Cache-Hit-Rate"""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0


class PerformanceMonitor:
    """
    Globaler Performance-Monitor für die Anwendung
    
    Features:
    - Query-Zeit-Tracking
    - N+1 Query-Erkennung
    - Cache-Effizienz-Monitoring
    - Slow-Query-Logging
    - Performance-Reports
    """
    
    def __init__(self):
        self.metrics: Dict[str, PerformanceMetrics] = defaultdict(PerformanceMetrics)
        self.query_log: List[Dict[str, Any]] = []
        self.n_plus_one_threshold = 10  # Threshold für N+1 Erkennung
        self.slow_query_threshold = 0.1  # 100ms
        self.enabled = True
    
    @contextmanager
    def track_operation(self, operation_name: str, query_type: str = 'unknown'):
        """
        Context Manager für Performance-Tracking
        
        Usage:
            with performance_monitor.track_operation('get_standings', 'select'):
                # Code hier
        """
        if not self.enabled:
            yield
            return
        
        start_time = time.time()
        
        # Log Query Start
        query_entry = {
            'operation': operation_name,
            'type': query_type,
            'start_time': start_time,
            'timestamp': datetime.now()
        }
        
        try:
            yield
        finally:
            # Berechne Dauer
            duration = time.time() - start_time
            query_entry['duration'] = duration
            
            # Update Metriken
            self.metrics[operation_name].add_execution(duration, query_type)
            
            # Log Query
            self.query_log.append(query_entry)
            
            # N+1 Detection
            self._check_n_plus_one(operation_name)
            
            # Slow Query Warning
            if duration > self.slow_query_threshold:
                logger.warning(
                    f"Slow query detected: {operation_name} took {duration:.3f}s"
                )
    
    def record_cache_hit(self, operation_name: str):
        """Zeichnet einen Cache-Hit auf"""
        if self.enabled:
            self.metrics[operation_name].cache_hits += 1
    
    def record_cache_miss(self, operation_name: str):
        """Zeichnet einen Cache-Miss auf"""
        if self.enabled:
            self.metrics[operation_name].cache_misses += 1
    
    def _check_n_plus_one(self, operation_name: str):
        """Prüft auf N+1 Query-Probleme"""
        # Analysiere die letzten Queries
        recent_queries = self.query_log[-50:]  # Letzte 50 Queries
        
        # Zähle wiederholte Query-Patterns
        query_patterns = defaultdict(int)
        for query in recent_queries:
            if query['type'] == 'select':
                pattern = f"{query['operation']}:{query['type']}"
                query_patterns[pattern] += 1
        
        # Erkenne N+1 Patterns
        for pattern, count in query_patterns.items():
            if count > self.n_plus_one_threshold:
                self.metrics[operation_name].n_plus_one_detections.append({
                    'pattern': pattern,
                    'count': count,
                    'timestamp': datetime.now()
                })
                logger.warning(
                    f"Potential N+1 query detected: {pattern} executed {count} times"
                )
    
    def get_performance_report(self) -> Dict[str, Any]:
        """
        Generiert einen umfassenden Performance-Report
        
        Returns:
            Dictionary mit Performance-Statistiken
        """
        report = {
            'summary': {
                'total_operations': sum(m.get_statistics()['count'] for m in self.metrics.values()),
                'total_time': sum(m.get_statistics()['total_time'] for m in self.metrics.values()),
                'slow_queries_total': sum(len(m.slow_queries) for m in self.metrics.values()),
                'n_plus_one_detections': sum(len(m.n_plus_one_detections) for m in self.metrics.values())
            },
            'operations': {}
        }
        
        # Detaillierte Statistiken pro Operation
        for operation, metrics in self.metrics.items():
            stats = metrics.get_statistics()
            if stats['count'] > 0:
                report['operations'][operation] = stats
        
        # Top Slow Queries
        all_slow_queries = []
        for metrics in self.metrics.values():
            all_slow_queries.extend(metrics.slow_queries)
        
        report['top_slow_queries'] = sorted(
            all_slow_queries,
            key=lambda x: x['duration'],
            reverse=True
        )[:10]
        
        # N+1 Probleme
        all_n_plus_one = []
        for operation, metrics in self.metrics.items():
            for detection in metrics.n_plus_one_detections:
                detection['operation'] = operation
                all_n_plus_one.append(detection)
        
        report['n_plus_one_issues'] = all_n_plus_one
        
        return report
    
    def reset_metrics(self):
        """Setzt alle Metriken zurück"""
        self.metrics.clear()
        self.query_log.clear()
        logger.info("Performance metrics reset")
    
    def get_operation_recommendations(self, operation_name: str) -> List[str]:
        """
        Gibt Optimierungsempfehlungen für eine Operation
        
        Args:
            operation_name: Name der Operation
            
        Returns:
            Liste von Empfehlungen
        """
        recommendations = []
        
        if operation_name not in self.metrics:
            return ["No data available for this operation"]
        
        stats = self.metrics[operation_name].get_statistics()
        
        # Langsame Queries
        if stats['avg_time'] > 0.05:  # 50ms
            recommendations.append(
                f"Average execution time is {stats['avg_time']:.3f}s. "
                "Consider adding database indexes or caching."
            )
        
        # Cache-Effizienz
        if stats['cache_hit_rate'] < 50:
            recommendations.append(
                f"Cache hit rate is only {stats['cache_hit_rate']:.1f}%. "
                "Consider increasing cache TTL or pre-warming cache."
            )
        
        # N+1 Queries
        if stats['n_plus_one_count'] > 0:
            recommendations.append(
                f"Detected {stats['n_plus_one_count']} potential N+1 query issues. "
                "Use eager loading or batch queries."
            )
        
        # Query-Verteilung
        if 'query_breakdown' in stats:
            select_count = stats['query_breakdown'].get('select', 0)
            if select_count > 10:
                recommendations.append(
                    f"High number of SELECT queries ({select_count}). "
                    "Consider using joins or reducing query count."
                )
        
        return recommendations if recommendations else ["Performance looks good!"]


# Globale Instanz
_performance_monitor = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    """Gibt die globale Performance-Monitor-Instanz zurück"""
    return _performance_monitor


def performance_tracked(operation_name: Optional[str] = None, query_type: str = 'unknown'):
    """
    Decorator für automatisches Performance-Tracking
    
    Args:
        operation_name: Name der Operation (default: Funktionsname)
        query_type: Typ der Query (select, insert, update, delete)
        
    Usage:
        @performance_tracked(query_type='select')
        def get_standings(year_id):
            # Code hier
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            with _performance_monitor.track_operation(op_name, query_type):
                result = func(*args, **kwargs)
            
            return result
        
        return wrapper
    return decorator


def log_slow_query(query: str, duration: float, params: Optional[Dict] = None):
    """
    Loggt eine langsame Query
    
    Args:
        query: Die SQL-Query
        duration: Ausführungszeit in Sekunden
        params: Query-Parameter
    """
    logger.warning(
        f"Slow query detected ({duration:.3f}s):\n"
        f"Query: {query}\n"
        f"Params: {params}"
    )