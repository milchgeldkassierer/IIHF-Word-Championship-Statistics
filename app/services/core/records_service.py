"""
Records Service für IIHF World Championship Statistics
Verwaltet Rekord-Tracking und -Abfragen
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.base.base_service import BaseService
from app.services.utils.cache_manager import CacheableService, cached
from app.repositories.core.records_repository import RecordsRepository
from app.exceptions import NotFoundError, ValidationError, ServiceError

logger = logging.getLogger(__name__)


class RecordsService(BaseService[RecordsRepository], CacheableService):
    """Service für Rekord-Management"""
    
    def __init__(self, repository: Optional[RecordsRepository] = None):
        # Initialisiere Repository falls nicht übergeben
        if repository is None:
            repository = RecordsRepository()
        
        # Use proper MRO initialization
        super().__init__(repository)
    
    # Turnier-Rekorde
    @cached(ttl=600, key_prefix="records:tournament")
    def get_tournament_records(self, year: Optional[int] = None, 
                             record_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Holt alle Turnier-Rekorde
        
        Args:
            year: Optionales Jahr für Filterung
            record_types: Liste der Rekordtypen (goals, assists, points, penalties)
            
        Returns:
            Dictionary mit allen Rekorden
        """
        if not record_types:
            record_types = ['goals', 'assists', 'points', 'penalties']
        
        records = {}
        
        try:
            if 'goals' in record_types:
                records['goal_leaders'] = self.repository.get_tournament_goal_records(year)
            
            if 'assists' in record_types:
                records['assist_leaders'] = self.repository.get_tournament_assist_records(year)
            
            if 'points' in record_types:
                records['point_leaders'] = self.repository.get_tournament_point_records(year)
            
            if 'penalties' in record_types:
                records['penalty_leaders'] = self.repository.get_tournament_penalty_records(year)
            
            # Zusätzliche Statistiken
            if records.get('point_leaders'):
                top_scorer = records['point_leaders'][0] if records['point_leaders'] else None
                if top_scorer:
                    records['tournament_mvp'] = {
                        'player': top_scorer['player_name'],
                        'team': top_scorer['team'],
                        'stats': f"{top_scorer['goals']}G + {top_scorer['assists']}A = {top_scorer['points']}P"
                    }
            
            logger.info(f"Retrieved tournament records for year={year}, types={record_types}")
            return records
            
        except Exception as e:
            logger.error(f"Error getting tournament records: {str(e)}")
            raise ServiceError(f"Failed to retrieve tournament records: {str(e)}")
    
    @cached(ttl=900, key_prefix="records:career")
    def get_career_records(self, limit: int = 10) -> Dict[str, Any]:
        """
        Holt alle Karriere-Rekorde
        
        Args:
            limit: Anzahl der Top-Spieler pro Kategorie
            
        Returns:
            Dictionary mit Karriere-Rekorden
        """
        
        try:
            records = {
                'career_goals': self.repository.get_career_goal_records(limit),
                'career_assists': self.repository.get_career_assist_records(limit),
                'career_points': self.repository.get_career_point_records(limit),
                'stats_updated': datetime.now().isoformat()
            }
            
            # Hall of Fame Kandidaten (100+ Punkte)
            hall_of_fame = [
                p for p in records['career_points'] 
                if p['points'] >= 100
            ]
            if hall_of_fame:
                records['hall_of_fame_candidates'] = hall_of_fame
            
            logger.info(f"Retrieved career records with limit={limit}")
            return records
            
        except Exception as e:
            logger.error(f"Error getting career records: {str(e)}")
            raise ServiceError(f"Failed to retrieve career records: {str(e)}")
    
    @cached(ttl=600, key_prefix="records:team")
    def get_team_records(self, team_code: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """
        Holt Team-Rekorde
        
        Args:
            team_code: Optionaler Team-Code für Filterung
            limit: Anzahl der Top-Rekorde
            
        Returns:
            Dictionary mit Team-Rekorden
        """
        try:
            records = {
                'highest_scoring_games': self.repository.get_team_highest_scoring_games(limit),
                'biggest_wins': self.repository.get_team_biggest_wins(limit)
            }
            
            # Filtern nach Team wenn angegeben
            if team_code:
                records['highest_scoring_games'] = [
                    r for r in records['highest_scoring_games']
                    if team_code in [r['teams'].split(' vs ')[0], r['teams'].split(' vs ')[1]]
                ]
                records['biggest_wins'] = [
                    r for r in records['biggest_wins']
                    if r['winner'] == team_code or r['loser'] == team_code
                ]
            
            logger.info(f"Retrieved team records for team={team_code}")
            return records
            
        except Exception as e:
            logger.error(f"Error getting team records: {str(e)}")
            raise ServiceError(f"Failed to retrieve team records: {str(e)}")
    
    @cached(ttl=600, key_prefix="records:game")
    def get_game_records(self, limit: int = 10) -> Dict[str, Any]:
        """
        Holt Spiel-Rekorde
        
        Args:
            limit: Anzahl der Top-Rekorde
            
        Returns:
            Dictionary mit Spiel-Rekorden
        """
        try:
            records = {
                'most_goals_combined': self.repository.get_game_most_goals_combined(limit),
                'most_penalties': self.repository.get_game_most_penalties(limit)
            }
            
            # Zusätzliche Analysen
            if records['most_goals_combined']:
                avg_goals = sum(r['total_goals'] for r in records['most_goals_combined']) / len(records['most_goals_combined'])
                records['stats'] = {
                    'avg_goals_in_high_scoring_games': round(avg_goals, 2),
                    'highest_scoring_game': records['most_goals_combined'][0]
                }
            
            logger.info("Retrieved game records")
            return records
            
        except Exception as e:
            logger.error(f"Error getting game records: {str(e)}")
            raise ServiceError(f"Failed to retrieve game records: {str(e)}")
    
    @cached(ttl=600, key_prefix="records:goals")
    def get_goal_records(self, record_types: Optional[List[str]] = None, limit: int = 10) -> Dict[str, Any]:
        """
        Holt Tor-Rekorde
        
        Args:
            record_types: Liste der Rekordtypen ('fastest', 'hattricks', 'career')
            limit: Anzahl der Top-Rekorde
            
        Returns:
            Dictionary mit Tor-Rekorden
        """
        if not record_types:
            record_types = ['fastest', 'hattricks']
        
        records = {}
        
        try:
            if 'fastest' in record_types:
                records['fastest_goals'] = self.repository.get_fastest_goals(limit)
            
            if 'hattricks' in record_types:
                records['fastest_hattricks'] = self.repository.get_fastest_hattricks(limit)
            
            if 'career' in record_types:
                records['career_goal_leaders'] = self.repository.get_career_goal_records(limit)
            
            logger.info(f"Retrieved goal records for types={record_types}")
            return records
            
        except Exception as e:
            logger.error(f"Error getting goal records: {str(e)}")
            raise ServiceError(f"Failed to retrieve goal records: {str(e)}")
    
    @cached(ttl=1200, key_prefix="records:all_time")
    def get_all_time_records(self) -> Dict[str, Any]:
        """
        Holt alle All-Time Rekorde in einer übersichtlichen Struktur
        
        Returns:
            Dictionary mit allen Rekordkategorien
        """
        try:
            return {
                'tournament': {
                    'single_tournament': self.get_tournament_records(limit=5),
                    'description': 'Best performances in a single tournament'
                },
                'career': {
                    'all_time': self.get_career_records(limit=5),
                    'description': 'Career totals across all tournaments'
                },
                'team': {
                    'records': self.get_team_records(limit=5),
                    'description': 'Team and game records'
                },
                'game': {
                    'records': self.get_game_records(limit=5),
                    'description': 'Individual game records'
                },
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting all-time records: {str(e)}")
            raise ServiceError(f"Failed to retrieve all-time records: {str(e)}")
    
    def get_record_progression(self, record_type: str, player_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Zeigt die historische Entwicklung eines Rekords
        
        Args:
            record_type: Typ des Rekords (z.B. 'tournament_goals')
            player_id: Optionale Spieler-ID für Filterung
            
        Returns:
            Liste mit Rekord-Entwicklung über die Jahre
        """
        valid_types = ['tournament_goals', 'tournament_assists', 'tournament_points']
        
        if record_type not in valid_types:
            raise ValidationError(f"Invalid record type. Must be one of: {valid_types}")
        
        try:
            progression = self.repository.get_record_progression(record_type, player_id)
            
            # Zusätzliche Analysen
            if progression:
                # Finde Rekord-Halter
                record_holders = {}
                for entry in progression:
                    year = entry['year']
                    if year not in record_holders or entry['value'] > record_holders[year]['value']:
                        record_holders[year] = entry
                
                # Markiere Rekord-Jahre
                current_record = 0
                for year in sorted(record_holders.keys()):
                    if record_holders[year]['value'] > current_record:
                        current_record = record_holders[year]['value']
                        record_holders[year]['new_record'] = True
                    else:
                        record_holders[year]['new_record'] = False
                
                return list(record_holders.values())
            
            return progression
            
        except Exception as e:
            logger.error(f"Error getting record progression: {str(e)}")
            raise ServiceError(f"Failed to retrieve record progression: {str(e)}")
    
    def search_records(self, search_term: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Sucht nach Rekorden basierend auf Spieler/Team-Namen
        
        Args:
            search_term: Suchbegriff
            category: Optionale Kategorie-Filterung
            
        Returns:
            Liste mit gefundenen Rekorden
        """
        if not search_term or len(search_term) < 2:
            raise ValidationError("Search term must be at least 2 characters")
        
        try:
            results = self.repository.search_records(search_term, category)
            
            # Sortiere nach Relevanz
            results.sort(key=lambda x: x['value'], reverse=True)
            
            logger.info(f"Found {len(results)} records for search term '{search_term}'")
            return results
            
        except Exception as e:
            logger.error(f"Error searching records: {str(e)}")
            raise ServiceError(f"Failed to search records: {str(e)}")
    
    def get_player_records(self, player_id: int) -> Dict[str, Any]:
        """
        Holt alle Rekorde eines bestimmten Spielers
        
        Args:
            player_id: Spieler-ID
            
        Returns:
            Dictionary mit allen Rekorden des Spielers
        """
        try:
            # Turnier-Rekorde
            tournament_goals = self.repository.get_tournament_goal_records(limit=100)
            tournament_assists = self.repository.get_tournament_assist_records(limit=100)
            tournament_points = self.repository.get_tournament_point_records(limit=100)
            
            # Karriere-Rekorde
            career_goals = self.repository.get_career_goal_records(limit=100)
            career_assists = self.repository.get_career_assist_records(limit=100)
            career_points = self.repository.get_career_point_records(limit=100)
            
            # Filtere nach Spieler
            player_records = {
                'tournament': {
                    'goals': [r for r in tournament_goals if r['player_id'] == player_id],
                    'assists': [r for r in tournament_assists if r['player_id'] == player_id],
                    'points': [r for r in tournament_points if r['player_id'] == player_id]
                },
                'career': {
                    'goals': next((r for r in career_goals if r['player_id'] == player_id), None),
                    'assists': next((r for r in career_assists if r['player_id'] == player_id), None),
                    'points': next((r for r in career_points if r['player_id'] == player_id), None)
                }
            }
            
            # Berechne Ränge
            if player_records['career']['goals']:
                player_records['career']['goals']['rank'] = career_goals.index(player_records['career']['goals']) + 1
            if player_records['career']['assists']:
                player_records['career']['assists']['rank'] = career_assists.index(player_records['career']['assists']) + 1
            if player_records['career']['points']:
                player_records['career']['points']['rank'] = career_points.index(player_records['career']['points']) + 1
            
            return player_records
            
        except Exception as e:
            logger.error(f"Error getting player records: {str(e)}")
            raise ServiceError(f"Failed to retrieve player records: {str(e)}")
    
    def get_team_record_summary(self, team_code: str) -> Dict[str, Any]:
        """
        Holt eine Zusammenfassung aller Rekorde eines Teams
        
        Args:
            team_code: Team-Code
            
        Returns:
            Dictionary mit Team-Rekord-Zusammenfassung
        """
        try:
            team_records = self.get_team_records(team_code)
            
            # Zusätzliche Team-spezifische Analysen
            summary = {
                'team': team_code,
                'records': team_records,
                'achievements': []
            }
            
            # Prüfe auf besondere Leistungen
            if team_records['highest_scoring_games']:
                highest = max(r['max_goals'] for r in team_records['highest_scoring_games'])
                if highest >= 10:
                    summary['achievements'].append(f"Scored {highest} goals in a game")
            
            if team_records['biggest_wins']:
                biggest = max(r['goal_diff'] for r in team_records['biggest_wins'])
                if biggest >= 10:
                    summary['achievements'].append(f"Won by {biggest} goals")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting team record summary: {str(e)}")
            raise ServiceError(f"Failed to retrieve team record summary: {str(e)}")
    
    @cached(ttl=1800, key_prefix="records:streaks")
    def get_streak_records(self, streak_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Holt alle Serien-Rekorde (Win/Loss/Scoring/Shutout/Goalless Streaks)
        
        Args:
            streak_types: Liste der Serien-Typen ['win', 'loss', 'scoring', 'shutout', 'goalless']
            
        Returns:
            Dictionary mit allen Serien-Rekorden
        """
        if not streak_types:
            streak_types = ['win', 'loss', 'scoring', 'shutout', 'goalless']
        
        # Import streak functions from utils for compatibility
        from routes.records.utils import get_records_data
        
        try:
            # Get pre-processed records data
            records_data = get_records_data()
            
            streaks = {}
            
            if 'win' in streak_types:
                from routes.records.streaks import get_longest_win_streak
                streaks['longest_win_streaks'] = get_longest_win_streak(records_data)
            
            if 'loss' in streak_types:
                from routes.records.streaks import get_longest_loss_streak
                streaks['longest_loss_streaks'] = get_longest_loss_streak(records_data)
            
            if 'scoring' in streak_types:
                from routes.records.streaks import get_longest_scoring_streak
                streaks['longest_scoring_streaks'] = get_longest_scoring_streak(records_data)
            
            if 'shutout' in streak_types:
                from routes.records.streaks import get_longest_shutout_streak
                streaks['longest_shutout_streaks'] = get_longest_shutout_streak(records_data)
            
            if 'goalless' in streak_types:
                from routes.records.streaks import get_longest_goalless_streak
                streaks['longest_goalless_streaks'] = get_longest_goalless_streak(records_data)
            
            # Zusätzliche Analysen
            streaks['stats_updated'] = datetime.now().isoformat()
            streaks['total_streak_categories'] = len([k for k in streaks.keys() if k.endswith('_streaks')])
            
            logger.info(f"Retrieved streak records for types={streak_types}")
            return streaks
            
        except Exception as e:
            logger.error(f"Error getting streak records: {str(e)}")
            raise ServiceError(f"Failed to retrieve streak records: {str(e)}")
    
    def get_all_records_comprehensive(self) -> Dict[str, Any]:
        """
        Holt ALLE Rekorde in einem umfassenden Dictionary
        Ersetzt die direkte Nutzung von einzelnen Funktionen in routes
        
        Returns:
            Dictionary mit allen verfügbaren Rekordkategorien
        """
        try:
            return {
                'tournament_records': self.get_tournament_records(),
                'career_records': self.get_career_records(),
                'team_records': self.get_team_records(),
                'game_records': self.get_game_records(),
                'streak_records': self.get_streak_records(),
                'last_updated': datetime.now().isoformat(),
                'version': '2.0.0'
            }
        except Exception as e:
            logger.error(f"Error getting comprehensive records: {str(e)}")
            raise ServiceError(f"Failed to retrieve comprehensive records: {str(e)}")
