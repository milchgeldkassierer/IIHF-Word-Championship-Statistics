"""
Performance Optimization Example - Zeigt die Verwendung der optimierten Services
Demonstriert Caching, Performance-Monitoring und optimierte Queries
"""

from flask import Flask, jsonify, request
from app.services.core.standings_service_optimized import StandingsServiceOptimized
from app.services.utils.performance_monitor import get_performance_monitor, performance_tracked
from app.services.utils.cache_manager import get_global_cache
import logging

logger = logging.getLogger(__name__)

# Beispiel-Route mit optimiertem Service
def register_optimized_routes(app: Flask):
    """
    Registriert optimierte Routes mit Performance-Features
    """
    
    # Initialisiere Services
    standings_service = StandingsServiceOptimized()
    performance_monitor = get_performance_monitor()
    
    @app.route('/api/v2/standings/<int:year_id>')
    @performance_tracked(operation_name='api.standings.year', query_type='select')
    def get_year_standings_optimized(year_id):
        """
        Optimierte Version der Standings-Route
        
        Features:
        - Caching (5 Minuten TTL)
        - Performance-Tracking
        - Bulk-Queries
        """
        try:
            # Hole Standings (automatisch gecacht)
            standings = standings_service.calculate_group_standings(year_id)
            
            # Füge Cache-Statistiken hinzu
            cache_stats = standings_service.get_cache_stats()
            
            return jsonify({
                'success': True,
                'year_id': year_id,
                'standings': {
                    group: [
                        {
                            'rank': team.rank_in_group,
                            'team': team.name,
                            'games': team.gp,
                            'wins': team.w,
                            'ot_wins': team.otw,
                            'so_wins': team.sow,
                            'losses': team.l,
                            'ot_losses': team.otl,
                            'so_losses': team.sol,
                            'points': team.pts,
                            'goals_for': team.gf,
                            'goals_against': team.ga,
                            'goal_diff': team.gd
                        }
                        for team in teams
                    ]
                    for group, teams in standings.items()
                },
                'performance': {
                    'cache_hit_rate': cache_stats.get('hit_rate', '0%'),
                    'cached_entries': cache_stats.get('entries', 0)
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting standings: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/api/v2/standings/<int:year_id>/group/<group>')
    @performance_tracked(operation_name='api.standings.group', query_type='select')
    def get_group_standings_optimized(year_id, group):
        """
        Optimierte Gruppen-Standings mit SQL-Aggregation
        """
        try:
            # Nutzt optimierte SQL-Query statt N+1
            standings = standings_service.calculate_group_standings(year_id, group)
            
            if group not in standings:
                return jsonify({
                    'success': False,
                    'error': f'Group {group} not found'
                }), 404
            
            return jsonify({
                'success': True,
                'year_id': year_id,
                'group': group,
                'standings': [
                    {
                        'rank': team.rank_in_group,
                        'team': team.name,
                        'games': team.gp,
                        'points': team.pts,
                        'goal_diff': team.gd
                    }
                    for team in standings[group]
                ]
            })
            
        except Exception as e:
            logger.error(f"Error getting group standings: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/api/v2/performance/report')
    def get_performance_report():
        """
        Performance-Monitoring Dashboard
        
        Zeigt:
        - Query-Statistiken
        - Cache-Effizienz
        - Slow Queries
        - N+1 Query-Erkennungen
        """
        report = performance_monitor.get_performance_report()
        
        # Füge Cache-Statistiken hinzu
        global_cache = get_global_cache()
        report['cache_stats'] = global_cache.get_stats()
        
        return jsonify(report)
    
    @app.route('/api/v2/performance/recommendations/<operation>')
    def get_performance_recommendations(operation):
        """
        Gibt Optimierungsempfehlungen für eine spezifische Operation
        """
        recommendations = performance_monitor.get_operation_recommendations(operation)
        
        return jsonify({
            'operation': operation,
            'recommendations': recommendations
        })
    
    @app.route('/api/v2/cache/invalidate', methods=['POST'])
    def invalidate_cache():
        """
        Manuelles Cache-Invalidieren
        
        Body:
        {
            "pattern": "standings:2024",  // Optional
            "year_id": 2024              // Optional
        }
        """
        data = request.get_json() or {}
        
        if 'year_id' in data:
            # Invalidiere spezifisches Jahr
            standings_service.invalidate_year_cache(data['year_id'])
            message = f"Invalidated cache for year {data['year_id']}"
        elif 'pattern' in data:
            # Invalidiere nach Pattern
            standings_service.invalidate_cache(data['pattern'])
            message = f"Invalidated cache for pattern: {data['pattern']}"
        else:
            # Invalidiere alles
            standings_service.invalidate_cache()
            message = "Invalidated all cache entries"
        
        return jsonify({
            'success': True,
            'message': message
        })
    
    @app.route('/api/v2/performance/reset', methods=['POST'])
    def reset_performance_metrics():
        """
        Setzt Performance-Metriken zurück
        """
        performance_monitor.reset_metrics()
        
        return jsonify({
            'success': True,
            'message': 'Performance metrics reset'
        })
    
    # Beispiel für Batch-Operation
    @app.route('/api/v2/standings/bulk', methods=['POST'])
    @performance_tracked(operation_name='api.standings.bulk', query_type='select')
    def get_bulk_standings():
        """
        Bulk-Abruf von Standings für mehrere Jahre
        
        Body:
        {
            "year_ids": [2022, 2023, 2024]
        }
        """
        data = request.get_json() or {}
        year_ids = data.get('year_ids', [])
        
        if not year_ids:
            return jsonify({
                'success': False,
                'error': 'No year_ids provided'
            }), 400
        
        results = {}
        
        # Nutze Bulk-Operationen statt einzelner Queries
        for year_id in year_ids:
            try:
                standings = standings_service.calculate_group_standings(year_id)
                results[str(year_id)] = {
                    'success': True,
                    'group_count': len(standings),
                    'groups': list(standings.keys())
                }
            except Exception as e:
                results[str(year_id)] = {
                    'success': False,
                    'error': str(e)
                }
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    logger.info("Optimized routes registered successfully")


# Beispiel-Verwendung in Tests
def demonstrate_performance_improvements():
    """
    Demonstriert Performance-Verbesserungen
    """
    from time import time
    
    # Initialisiere Services
    standings_service = StandingsServiceOptimized()
    monitor = get_performance_monitor()
    
    # Test 1: Erste Anfrage (Cache miss)
    print("Test 1: First request (cache miss)")
    start = time()
    standings1 = standings_service.calculate_group_standings(2024)
    duration1 = time() - start
    print(f"Duration: {duration1:.3f}s")
    
    # Test 2: Zweite Anfrage (Cache hit)
    print("\nTest 2: Second request (cache hit)")
    start = time()
    standings2 = standings_service.calculate_group_standings(2024)
    duration2 = time() - start
    print(f"Duration: {duration2:.3f}s")
    print(f"Speedup: {duration1/duration2:.1f}x faster")
    
    # Test 3: Cache-Statistiken
    print("\nTest 3: Cache statistics")
    cache_stats = standings_service.get_cache_stats()
    print(f"Hit rate: {cache_stats['hit_rate']}")
    print(f"Entries: {cache_stats['entries']}")
    
    # Test 4: Performance-Report
    print("\nTest 4: Performance report")
    report = monitor.get_performance_report()
    print(f"Total operations: {report['summary']['total_operations']}")
    print(f"Total time: {report['summary']['total_time']:.3f}s")
    
    # Test 5: N+1 Query-Erkennung
    print("\nTest 5: N+1 query detection")
    # Simuliere N+1 Problem
    for i in range(15):
        with monitor.track_operation('test_n_plus_one', 'select'):
            pass  # Simulierte Query
    
    report = monitor.get_performance_report()
    print(f"N+1 detections: {report['summary']['n_plus_one_detections']}")


if __name__ == '__main__':
    # Führe Demonstration aus
    demonstrate_performance_improvements()