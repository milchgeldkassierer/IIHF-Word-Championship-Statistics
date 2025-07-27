"""
Test migration of routes/players/stats.py to use service layer
This verifies that Issue #14 migration from direct DB queries to service layer maintains functionality
"""

import pytest
from unittest.mock import Mock, patch
from services.player_service import PlayerService
from routes.players.stats import get_all_player_stats
from services.exceptions import ServiceError


class TestPlayerStatsMigration:
    """Test the migration from direct DB queries to service layer"""
    
    def test_get_all_player_stats_uses_service_layer(self):
        """Test that get_all_player_stats now uses PlayerService"""
        with patch.object(PlayerService, 'get_comprehensive_player_stats') as mock_service:
            mock_service.return_value = [
                {
                    'first_name': 'Test',
                    'last_name': 'Player',
                    'team_code': 'CAN',
                    'goals': 5,
                    'assists': 3,
                    'scorer_points': 8,
                    'pims': 10,
                    'goal_year_range': '(2023)',
                    'assist_year_range': '(2023)',
                    'pim_year_range': '(2023)',
                    'overall_year_range': '(2023)'
                }
            ]
            
            result = get_all_player_stats()
            
            # Verify service was called
            mock_service.assert_called_once_with(team_filter=None)
            
            # Verify result structure is maintained
            assert len(result) == 1
            assert result[0]['first_name'] == 'Test'
            assert result[0]['scorer_points'] == 8
    
    def test_get_all_player_stats_with_team_filter(self):
        """Test that team filter is passed to service layer"""
        with patch.object(PlayerService, 'get_comprehensive_player_stats') as mock_service:
            mock_service.return_value = []
            
            get_all_player_stats(team_filter='CAN')
            
            # Verify team filter was passed
            mock_service.assert_called_once_with(team_filter='CAN')
    
    def test_get_all_player_stats_handles_service_error(self):
        """Test that service errors are handled gracefully"""
        with patch.object(PlayerService, 'get_comprehensive_player_stats') as mock_service:
            mock_service.side_effect = ServiceError("Database error")
            
            result = get_all_player_stats()
            
            # Should return empty list on error
            assert result == []
    
    def test_get_all_player_stats_handles_unexpected_error(self):
        """Test that unexpected errors are handled gracefully"""
        with patch.object(PlayerService, 'get_comprehensive_player_stats') as mock_service:
            mock_service.side_effect = Exception("Unexpected error")
            
            result = get_all_player_stats()
            
            # Should return empty list on error
            assert result == []


class TestPlayerServiceComprehensiveStats:
    """Test the new comprehensive stats method in PlayerService"""
    
    @pytest.fixture
    def player_service(self):
        return PlayerService()
    
    def test_format_year_range_single_year(self, player_service):
        """Test year range formatting for single year"""
        result = player_service._format_year_range(2023, 2023)
        assert result == "(2023)"
    
    def test_format_year_range_multiple_years(self, player_service):
        """Test year range formatting for multiple years"""
        result = player_service._format_year_range(2020, 2023)
        assert result == "(2020-2023)"
    
    def test_format_year_range_no_years(self, player_service):
        """Test year range formatting with no years"""
        result = player_service._format_year_range(None, None)
        assert result is None
    
    def test_calculate_overall_year_range(self, player_service):
        """Test calculation of overall year range from all stats"""
        result = player_service._calculate_overall_year_range(
            first_goal_year=2021, last_goal_year=2023,
            first_assist_year=2020, last_assist_year=2022,
            first_pim_year=2022, last_pim_year=2023
        )
        assert result == "(2020-2023)"  # Min of first years to max of last years
    
    def test_calculate_overall_year_range_partial_data(self, player_service):
        """Test calculation with partial data (some stats missing)"""
        result = player_service._calculate_overall_year_range(
            first_goal_year=2021, last_goal_year=2023,
            first_assist_year=None, last_assist_year=None,
            first_pim_year=2022, last_pim_year=2022
        )
        assert result == "(2021-2023)"
    
    def test_calculate_overall_year_range_no_data(self, player_service):
        """Test calculation with no data"""
        result = player_service._calculate_overall_year_range(
            first_goal_year=None, last_goal_year=None,
            first_assist_year=None, last_assist_year=None,
            first_pim_year=None, last_pim_year=None
        )
        assert result is None


if __name__ == '__main__':
    pytest.main([__file__])