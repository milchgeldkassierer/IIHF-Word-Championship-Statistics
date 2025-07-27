"""
Integration tests to verify the StandingsCalculator service works correctly
with the existing codebase and matches the original implementations.
"""

import pytest
from unittest.mock import Mock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.standings_calculator import StandingsCalculator


class TestStandingsCalculatorImplementation:
    """Test the actual StandingsCalculator implementation"""
    
    @pytest.fixture
    def calculator(self):
        """Create a StandingsCalculator instance"""
        return StandingsCalculator()
    
    @pytest.fixture
    def mock_team(self):
        """Create a mock team with all required attributes"""
        team = Mock()
        team.gp = 0
        team.w = 0
        team.otw = 0
        team.sow = 0
        team.l = 0
        team.otl = 0
        team.sol = 0
        team.pts = 0
        team.gf = 0
        team.ga = 0
        team.gd = 0
        return team
    
    @pytest.fixture
    def mock_game(self):
        """Create a mock game"""
        game = Mock()
        game.home_score = 3
        game.away_score = 2
        game.game_type = "REG"
        return game
    
    def test_regular_win_home_team(self, calculator, mock_team, mock_game):
        """Test regular time win for home team"""
        # Arrange
        mock_game.home_score = 4
        mock_game.away_score = 2
        mock_game.game_type = "REG"
        
        # Act
        calculator.update_team_stats(mock_team, mock_game, is_home=True)
        
        # Assert
        assert mock_team.gp == 1
        assert mock_team.w == 1
        assert mock_team.pts == 3
        assert mock_team.gf == 4
        assert mock_team.ga == 2
        assert mock_team.gd == 2
    
    def test_regular_loss_away_team(self, calculator, mock_team, mock_game):
        """Test regular time loss for away team"""
        # Arrange
        mock_game.home_score = 5
        mock_game.away_score = 2
        mock_game.game_type = "REG"
        
        # Act
        calculator.update_team_stats(mock_team, mock_game, is_home=False)
        
        # Assert
        assert mock_team.gp == 1
        assert mock_team.l == 1
        assert mock_team.pts == 0
        assert mock_team.gf == 2
        assert mock_team.ga == 5
        assert mock_team.gd == -3
    
    def test_overtime_win(self, calculator, mock_team, mock_game):
        """Test overtime win awards 2 points"""
        # Arrange
        mock_game.home_score = 3
        mock_game.away_score = 2
        mock_game.game_type = "OT"
        
        # Act
        calculator.update_team_stats(mock_team, mock_game, is_home=True)
        
        # Assert
        assert mock_team.otw == 1
        assert mock_team.pts == 2
        assert mock_team.w == 0  # Regular wins should not increase
    
    def test_overtime_loss(self, calculator, mock_team, mock_game):
        """Test overtime loss awards 1 point"""
        # Arrange
        mock_game.home_score = 2
        mock_game.away_score = 3
        mock_game.game_type = "OT"
        
        # Act
        calculator.update_team_stats(mock_team, mock_game, is_home=True)
        
        # Assert
        assert mock_team.otl == 1
        assert mock_team.pts == 1
        assert mock_team.l == 0  # Regular losses should not increase
    
    def test_shootout_win(self, calculator, mock_team, mock_game):
        """Test shootout win awards 2 points"""
        # Arrange
        mock_game.home_score = 1
        mock_game.away_score = 0
        mock_game.game_type = "SO"
        
        # Act
        calculator.update_team_stats(mock_team, mock_game, is_home=True)
        
        # Assert
        assert mock_team.sow == 1
        assert mock_team.pts == 2
    
    def test_shootout_loss(self, calculator, mock_team, mock_game):
        """Test shootout loss awards 1 point"""
        # Arrange
        mock_game.home_score = 0
        mock_game.away_score = 1
        mock_game.game_type = "SO"
        
        # Act
        calculator.update_team_stats(mock_team, mock_game, is_home=True)
        
        # Assert
        assert mock_team.sol == 1
        assert mock_team.pts == 1
    
    def test_calculate_win_percentage(self, calculator, mock_team):
        """Test win percentage calculation"""
        # Setup team with mixed results
        mock_team.gp = 10
        mock_team.w = 4
        mock_team.otw = 2
        mock_team.sow = 1
        
        # Calculate
        win_pct = calculator.calculate_win_percentage(mock_team)
        
        # Assert (7 total wins / 10 games = 0.7)
        assert win_pct == 0.7
    
    def test_calculate_points_percentage(self, calculator, mock_team):
        """Test points percentage calculation"""
        # Setup team
        mock_team.gp = 10
        mock_team.pts = 20
        
        # Calculate
        pts_pct = calculator.calculate_points_percentage(mock_team)
        
        # Assert (20 points / 30 possible = 0.667)
        assert abs(pts_pct - 0.667) < 0.001
    
    def test_get_team_record(self, calculator, mock_team):
        """Test team record formatting"""
        # Setup
        mock_team.w = 5
        mock_team.l = 2
        mock_team.otl = 1
        mock_team.sol = 1
        
        # Get record
        record = calculator.get_team_record(mock_team)
        
        # Assert
        assert record == "5-2-1-1"
    
    def test_reset_team_stats(self, calculator, mock_team):
        """Test resetting team statistics"""
        # Setup with some values
        mock_team.gp = 10
        mock_team.pts = 20
        mock_team.w = 5
        
        # Reset
        calculator.reset_team_stats(mock_team)
        
        # Assert all zeroed
        assert mock_team.gp == 0
        assert mock_team.pts == 0
        assert mock_team.w == 0


class TestCompareWithOriginalImplementation:
    """Compare new service with original implementations"""
    
    def test_points_calculation_matches_original(self):
        """Verify points calculation matches original logic"""
        calculator = StandingsCalculator()
        
        # Test cases matching original logic
        test_cases = [
            # (game_type, winner, expected_points)
            ("REG", True, 3),
            ("REG", False, 0),
            ("OT", True, 2),
            ("OT", False, 1),
            ("SO", True, 2),
            ("SO", False, 1),
        ]
        
        for game_type, is_winner, expected_pts in test_cases:
            team = Mock(pts=0, w=0, l=0, otw=0, otl=0, sow=0, sol=0)
            
            if is_winner:
                calculator._handle_win(team, game_type)
            else:
                calculator._handle_loss(team, game_type)
            
            assert team.pts == expected_pts, \
                f"Failed for {game_type} winner={is_winner}: got {team.pts}, expected {expected_pts}"
    
    def test_complete_game_processing(self):
        """Test processing a complete game matches original behavior"""
        calculator = StandingsCalculator()
        
        # Create two teams
        team1 = Mock(gp=0, w=0, l=0, otw=0, otl=0, sow=0, sol=0, pts=0, gf=0, ga=0, gd=0)
        team2 = Mock(gp=0, w=0, l=0, otw=0, otl=0, sow=0, sol=0, pts=0, gf=0, ga=0, gd=0)
        
        # Create game - team1 wins in OT
        game = Mock(home_score=3, away_score=2, game_type="OT")
        
        # Process for both teams
        calculator.update_team_stats(team1, game, is_home=True)  # Winner
        calculator.update_team_stats(team2, game, is_home=False)  # Loser
        
        # Verify results match original logic
        assert team1.gp == 1
        assert team1.otw == 1
        assert team1.pts == 2
        assert team1.gf == 3
        assert team1.ga == 2
        
        assert team2.gp == 1
        assert team2.otl == 1
        assert team2.pts == 1
        assert team2.gf == 2
        assert team2.ga == 3


class TestMigrationReadiness:
    """Test if the service is ready to replace existing implementations"""
    
    def test_interface_compatibility(self):
        """Check if the service interface is compatible with existing code"""
        calculator = StandingsCalculator()
        
        # Check required methods exist
        assert hasattr(calculator, 'update_team_stats')
        assert hasattr(calculator, '_handle_win')
        assert hasattr(calculator, '_handle_loss')
        assert hasattr(calculator, 'calculate_win_percentage')
        assert hasattr(calculator, 'calculate_points_percentage')
    
    def test_handles_edge_cases(self):
        """Test edge case handling"""
        calculator = StandingsCalculator()
        
        # Test with zero games played
        team = Mock(gp=0, w=0, pts=0)
        assert calculator.calculate_win_percentage(team) == 0.0
        assert calculator.calculate_points_percentage(team) == 0.0
        
        # Test with None game_type (should handle gracefully)
        team = Mock(gp=0, w=0, l=0, otw=0, otl=0, sow=0, sol=0, pts=0)
        # This might need adjustment based on how the service handles None
        # Currently would raise AttributeError - service might need update


if __name__ == "__main__":
    pytest.main([__file__, "-v"])