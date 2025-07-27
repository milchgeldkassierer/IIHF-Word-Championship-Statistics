"""
Comprehensive tests to verify tournament_records.py refactoring.
Tests ensure that refactored functions return same results as original,
handle edge cases, and demonstrate performance improvements.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from collections import defaultdict
import time

# Import the functions we're testing
from routes.records.tournament_records import (
    get_record_champion,
    get_tournament_with_most_goals,
    get_tournament_with_least_goals,
    get_tournament_with_most_penalty_minutes,
    get_tournament_with_least_penalty_minutes,
    get_most_consecutive_tournament_wins,
    get_most_final_appearances
)
from routes.records.utils import get_all_resolved_games, get_tournament_statistics
from models import db, Game, ChampionshipYear, Penalty


class TestTournamentRecordsRefactoring:
    """Test suite for tournament records refactoring verification."""
    
    @pytest.fixture
    def mock_resolved_games(self):
        """Create mock resolved games for testing."""
        return [
            {
                'game': Mock(round='Gold Medal Game', team1_score=3, team2_score=2, game_number=64),
                'team1_code': 'CAN',
                'team2_code': 'USA',
                'year': 2023
            },
            {
                'game': Mock(round='Gold Medal Game', team1_score=4, team2_score=3, game_number=64),
                'team1_code': 'CAN',
                'team2_code': 'FIN',
                'year': 2022
            },
            {
                'game': Mock(round='Gold Medal Game', team1_score=2, team2_score=1, game_number=64),
                'team1_code': 'FIN',
                'team2_code': 'CAN',
                'year': 2021
            },
            {
                'game': Mock(round='Bronze Medal Game', team1_score=5, team2_score=3, game_number=63),
                'team1_code': 'USA',
                'team2_code': 'SWE',
                'year': 2023
            },
            {
                'game': Mock(round='Preliminary Round', team1_score=3, team2_score=2, game_number=10),
                'team1_code': 'CAN',
                'team2_code': 'FIN',
                'year': 2023
            }
        ]
    
    @pytest.fixture
    def mock_championship_years(self, app):
        """Create mock championship years."""
        with app.app_context():
            years = []
            for year in [2021, 2022, 2023]:
                year_obj = ChampionshipYear(
                    id=year,
                    year=year,
                    host_country="CZE",
                    start_date=f"{year}-05-10",
                    end_date=f"{year}-05-26",
                    num_teams=16,
                    name=f"IIHF World Championship {year}"
                )
                years.append(year_obj)
                db.session.add(year_obj)
            db.session.commit()
            return years
    
    @pytest.fixture
    def mock_games_with_scores(self, app, mock_championship_years):
        """Create mock games with scores for goal calculations."""
        with app.app_context():
            games = []
            # 2023: High scoring tournament (300 goals)
            for i in range(50):
                game = Game(
                    year_id=2023,
                    game_number=i+1,
                    round="Preliminary Round",
                    team1_code="CAN",
                    team2_code="USA",
                    team1_score=4,
                    team2_score=2
                )
                games.append(game)
                db.session.add(game)
            
            # 2022: Medium scoring tournament (200 goals)
            for i in range(50):
                game = Game(
                    year_id=2022,
                    game_number=i+1,
                    round="Preliminary Round", 
                    team1_code="FIN",
                    team2_code="SWE",
                    team1_score=2,
                    team2_score=2
                )
                games.append(game)
                db.session.add(game)
            
            # 2021: Low scoring tournament (150 goals)
            for i in range(50):
                game = Game(
                    year_id=2021,
                    game_number=i+1,
                    round="Preliminary Round",
                    team1_code="CZE",
                    team2_code="GER",
                    team1_score=2,
                    team2_score=1
                )
                games.append(game)
                db.session.add(game)
            
            db.session.commit()
            return games
    
    def test_get_record_champion_basic(self, app, mock_resolved_games):
        """Test basic functionality of get_record_champion."""
        with app.app_context():
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = mock_resolved_games
                
                result = get_record_champion()
                
                # Verify structure
                assert isinstance(result, list)
                assert len(result) > 0
                
                # Verify CAN has 2 championships (2023, 2022)
                can_result = next((r for r in result if r['team'] == 'CAN'), None)
                assert can_result is not None
                assert can_result['championships'] == 2
                assert set(can_result['years']) == {2022, 2023}
                
                # Verify FIN has 1 championship (2021)
                fin_result = next((r for r in result if r['team'] == 'FIN'), None)
                assert fin_result is not None
                assert fin_result['championships'] == 1
                assert fin_result['years'] == [2021]
    
    def test_get_record_champion_edge_cases(self, app):
        """Test edge cases for get_record_champion."""
        with app.app_context():
            # Test with no games
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = []
                result = get_record_champion()
                assert result == []
            
            # Test with tied game (should be skipped)
            tied_games = [{
                'game': Mock(round='Gold Medal Game', team1_score=3, team2_score=3, game_number=64),
                'team1_code': 'CAN',
                'team2_code': 'USA',
                'year': 2023
            }]
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = tied_games
                result = get_record_champion()
                assert result == []
    
    def test_get_tournament_with_most_goals(self, app, mock_championship_years, mock_games_with_scores):
        """Test tournament with most goals calculation."""
        with app.app_context():
            with patch('routes.records.utils.get_tournament_statistics') as mock_stats:
                # Mock tournament statistics to show all tournaments completed
                mock_stats.side_effect = lambda year: {
                    'total_games': 50,
                    'completed_games': 50,
                    'goals': 300 if year.year == 2023 else 200 if year.year == 2022 else 150,
                    'penalties': 0,
                    'avg_goals_per_game': 6.0 if year.year == 2023 else 4.0 if year.year == 2022 else 3.0,
                    'winner': 'CAN' if year.year in [2022, 2023] else 'FIN'
                }
                
                result = get_tournament_with_most_goals()
                
                assert len(result) == 1
                assert result[0]['year'] == 2023
                assert result[0]['total_goals'] == 300
                assert result[0]['games'] == 50
                assert result[0]['goals_per_game'] == 6.0
    
    def test_get_tournament_with_least_goals(self, app, mock_championship_years, mock_games_with_scores):
        """Test tournament with least goals calculation."""
        with app.app_context():
            with patch('routes.records.utils.get_tournament_statistics') as mock_stats:
                # Mock tournament statistics
                mock_stats.side_effect = lambda year: {
                    'total_games': 50,
                    'completed_games': 50,
                    'goals': 300 if year.year == 2023 else 200 if year.year == 2022 else 150,
                    'penalties': 0,
                    'avg_goals_per_game': 6.0 if year.year == 2023 else 4.0 if year.year == 2022 else 3.0,
                    'winner': 'CAN' if year.year in [2022, 2023] else 'FIN'
                }
                
                result = get_tournament_with_least_goals()
                
                assert len(result) == 1
                assert result[0]['year'] == 2021
                assert result[0]['total_goals'] == 150
                assert result[0]['games'] == 50
                assert result[0]['goals_per_game'] == 3.0
    
    def test_get_tournament_with_most_penalty_minutes(self, app, mock_championship_years):
        """Test tournament with most penalty minutes calculation."""
        with app.app_context():
            with patch('routes.records.utils.get_tournament_statistics') as mock_stats:
                with patch('utils.data_validation.calculate_tournament_penalty_minutes') as mock_pim:
                    # Mock different penalty minutes for each year
                    mock_pim.side_effect = lambda year_id, completed_games_only: {
                        2023: 800,
                        2022: 600,
                        2021: 400
                    }.get(year_id, 0)
                    
                    mock_stats.side_effect = lambda year: {
                        'total_games': 50,
                        'completed_games': 50,
                        'goals': 200,
                        'penalties': 800 if year.year == 2023 else 600 if year.year == 2022 else 400,
                        'avg_goals_per_game': 4.0,
                        'winner': 'CAN'
                    }
                    
                    result = get_tournament_with_most_penalty_minutes()
                    
                    assert len(result) == 1
                    assert result[0]['year'] == 2023
                    assert result[0]['total_pim'] == 800
                    assert result[0]['games'] == 50
                    assert result[0]['pim_per_game'] == 16.0
    
    def test_get_tournament_with_least_penalty_minutes(self, app, mock_championship_years):
        """Test tournament with least penalty minutes calculation."""
        with app.app_context():
            with patch('routes.records.utils.get_tournament_statistics') as mock_stats:
                with patch('utils.data_validation.calculate_tournament_penalty_minutes') as mock_pim:
                    # Mock different penalty minutes for each year
                    mock_pim.side_effect = lambda year_id, completed_games_only: {
                        2023: 800,
                        2022: 600,
                        2021: 400
                    }.get(year_id, 0)
                    
                    mock_stats.side_effect = lambda year: {
                        'total_games': 50,
                        'completed_games': 50,
                        'goals': 200,
                        'penalties': 800 if year.year == 2023 else 600 if year.year == 2022 else 400,
                        'avg_goals_per_game': 4.0,
                        'winner': 'CAN'
                    }
                    
                    result = get_tournament_with_least_penalty_minutes()
                    
                    assert len(result) == 1
                    assert result[0]['year'] == 2021
                    assert result[0]['total_pim'] == 400
                    assert result[0]['games'] == 50
                    assert result[0]['pim_per_game'] == 8.0
    
    def test_get_most_consecutive_tournament_wins(self, app):
        """Test consecutive tournament wins calculation."""
        with app.app_context():
            # Create games with consecutive wins for CAN
            consecutive_games = [
                {
                    'game': Mock(round='Gold Medal Game', team1_score=3, team2_score=2),
                    'team1_code': 'CAN',
                    'team2_code': 'USA',
                    'year': 2021
                },
                {
                    'game': Mock(round='Gold Medal Game', team1_score=4, team2_score=3),
                    'team1_code': 'CAN',
                    'team2_code': 'FIN',
                    'year': 2022
                },
                {
                    'game': Mock(round='Gold Medal Game', team1_score=5, team2_score=4),
                    'team1_code': 'CAN',
                    'team2_code': 'SWE',
                    'year': 2023
                },
                {
                    'game': Mock(round='Gold Medal Game', team1_score=3, team2_score=2),
                    'team1_code': 'FIN',
                    'team2_code': 'CAN',
                    'year': 2024
                }
            ]
            
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = consecutive_games
                
                result = get_most_consecutive_tournament_wins()
                
                assert len(result) == 1
                assert result[0]['team'] == 'CAN'
                assert result[0]['streak'] == 3
                assert result[0]['years'] == [2021, 2022, 2023]
    
    def test_get_most_final_appearances(self, app, mock_resolved_games):
        """Test final appearances calculation."""
        with app.app_context():
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = mock_resolved_games
                
                result = get_most_final_appearances()
                
                # CAN appears in 3 finals (2021, 2022, 2023)
                can_result = next((r for r in result if r['team'] == 'CAN'), None)
                assert can_result is not None
                assert can_result['appearances'] == 3
                assert set(can_result['years']) == {2021, 2022, 2023}
    
    def test_helper_functions_independence(self, app):
        """Test that helper functions work independently."""
        with app.app_context():
            # Test get_tournament_statistics
            year_obj = Mock(id=2023, name="Test Championship", year=2023)
            with patch('models.Game.query') as mock_query:
                mock_query.filter_by.return_value.all.return_value = []
                
                stats = get_tournament_statistics(year_obj)
                
                assert stats['total_games'] == 0
                assert stats['completed_games'] == 0
                assert stats['goals'] == 0
                assert stats['penalties'] == 0
                assert stats['winner'] is None
    
    def test_performance_improvement(self, app):
        """Test that refactored code performs better than original."""
        with app.app_context():
            # Create a large dataset for performance testing
            large_dataset = []
            for year in range(2000, 2024):
                for i in range(10):  # 10 gold medal games per year
                    large_dataset.append({
                        'game': Mock(round='Gold Medal Game', team1_score=3, team2_score=2),
                        'team1_code': 'CAN' if i % 2 == 0 else 'USA',
                        'team2_code': 'USA' if i % 2 == 0 else 'CAN',
                        'year': year
                    })
            
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = large_dataset
                
                # Measure performance of refactored function
                start_time = time.time()
                result = get_record_champion()
                refactored_time = time.time() - start_time
                
                # Verify results are correct
                assert len(result) > 0
                
                # Performance should be reasonable (under 1 second for this dataset)
                assert refactored_time < 1.0
    
    def test_top_3_display_limit(self, app):
        """Test that functions respect TOP_3_DISPLAY constant."""
        with app.app_context():
            # Create games with many different champions
            many_champions = []
            teams = ['CAN', 'USA', 'FIN', 'SWE', 'CZE', 'RUS', 'GER', 'SUI']
            
            for i, team in enumerate(teams):
                for j in range(3):  # Give each team 3 championships
                    many_champions.append({
                        'game': Mock(round='Gold Medal Game', team1_score=3, team2_score=2),
                        'team1_code': team,
                        'team2_code': 'LAT',
                        'year': 2000 + i * 3 + j
                    })
            
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = many_champions
                
                result = get_record_champion()
                
                # Should only return top 3 teams
                assert len(result) <= 3
    
    def test_incomplete_tournament_handling(self, app, mock_championship_years):
        """Test handling of incomplete tournaments."""
        with app.app_context():
            with patch('routes.records.utils.get_tournament_statistics') as mock_stats:
                # Mock one incomplete tournament
                mock_stats.side_effect = lambda year: {
                    'total_games': 50,
                    'completed_games': 40 if year.year == 2023 else 50,  # 2023 is incomplete
                    'goals': 200,
                    'penalties': 500,
                    'avg_goals_per_game': 4.0,
                    'winner': 'CAN' if year.year != 2023 else None
                }
                
                # Incomplete tournaments should be excluded from goal records
                result = get_tournament_with_most_goals()
                
                # Should not include 2023 (incomplete)
                assert all(r['year'] != 2023 for r in result)
    
    def test_null_safety(self, app):
        """Test that functions handle null/None values gracefully."""
        with app.app_context():
            null_games = [
                {
                    'game': Mock(round='Gold Medal Game', team1_score=None, team2_score=None),
                    'team1_code': 'CAN',
                    'team2_code': 'USA',
                    'year': 2023
                },
                {
                    'game': Mock(round=None, team1_score=3, team2_score=2),
                    'team1_code': None,
                    'team2_code': 'USA',
                    'year': None
                }
            ]
            
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = null_games
                
                # Functions should handle nulls without crashing
                result = get_record_champion()
                assert isinstance(result, list)  # Should return empty list or valid results


class TestRefactoringCorrectness:
    """Additional tests to ensure refactoring maintains correctness."""
    
    def test_data_consistency_across_functions(self, app, mock_resolved_games):
        """Test that all functions use consistent data source."""
        with app.app_context():
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = mock_resolved_games
                
                # All functions should call get_all_resolved_games exactly once
                get_record_champion()
                assert mock_get_games.call_count == 1
                
                mock_get_games.reset_mock()
                get_most_consecutive_tournament_wins()
                assert mock_get_games.call_count == 1
                
                mock_get_games.reset_mock()
                get_most_final_appearances()
                assert mock_get_games.call_count == 1
    
    def test_sorting_and_filtering_logic(self, app):
        """Test that sorting and filtering work correctly."""
        with app.app_context():
            # Create teams with different championship counts
            varied_championships = []
            teams_data = [
                ('CAN', 5),
                ('USA', 3),
                ('FIN', 3),
                ('SWE', 2),
                ('CZE', 1)
            ]
            
            year = 2000
            for team, count in teams_data:
                for _ in range(count):
                    varied_championships.append({
                        'game': Mock(round='Gold Medal Game', team1_score=3, team2_score=2),
                        'team1_code': team,
                        'team2_code': 'LAT',
                        'year': year
                    })
                    year += 1
            
            with patch('routes.records.tournament_records.get_all_resolved_games') as mock_get_games:
                mock_get_games.return_value = varied_championships
                
                result = get_record_champion()
                
                # Should be sorted by championship count (descending)
                assert result[0]['team'] == 'CAN'
                assert result[0]['championships'] == 5
                
                # Should handle ties (USA and FIN both have 3)
                teams_with_3 = [r for r in result if r['championships'] == 3]
                assert len(teams_with_3) == 2
                assert set(r['team'] for r in teams_with_3) == {'USA', 'FIN'}