import unittest
from unittest.mock import patch, MagicMock

# Assuming the app structure allows these imports
# If running tests from the root directory:

# For the environment where this code will be executed, let's assume direct import works
# or that PYTHONPATH is set up correctly.
# If 'db' is used for db.joinedload, we might need to mock 'db' or ensure it's available.
# However, Game.query.options(db.joinedload(...)) means 'db' is accessed from 'models' import.
# Let's try to mock db.joinedload if it becomes an issue, or mock the full 'options' chain.

from models import Game, ChampionshipYear, AllTimeTeamStats, TeamStats, db as actual_db_object # Added TeamStats
from routes.main_routes import calculate_all_time_standings
import json # For mocking fixture open

# Mock for current_app.logger
mock_logger = MagicMock()

class TestAllTimeStandings(unittest.TestCase):

    def setUp(self):
        # Reset logger mock before each test to ensure clean assertion counts
        mock_logger.reset_mock()
        # This mock assumes db.joinedload simply returns its argument for relationship loading.
        self.db_mock = MagicMock()
        self.db_mock.joinedload = lambda x: x 

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('routes.main_routes.ChampionshipYear.query') # Mock ChampionshipYear query
    @patch('routes.main_routes.db', new_callable=MagicMock) 
    @patch('routes.main_routes.Game.query')
    def test_no_games(self, mock_game_query, mock_db_in_routes, mock_championship_year_query):
        mock_db_in_routes.joinedload = self.db_mock.joinedload
        mock_game_query.options.return_value.all.return_value = []
        mock_championship_year_query.all.return_value = [] # No years
        
        result = calculate_all_time_standings()
        self.assertEqual(result, [])
        mock_logger.warning.assert_not_called()

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('routes.main_routes.ChampionshipYear.query')
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_single_year_data_with_playoffs(self, mock_game_query, mock_db_in_routes, mock_championship_year_query, mock_file_open):
        mock_db_in_routes.joinedload = self.db_mock.joinedload
        
        year2023_obj = ChampionshipYear(id=1, name="2023 Worlds", year=2023, fixture_path="dummy_fixture_2023.json")
        mock_championship_year_query.all.return_value = [year2023_obj]
        
        # Simulate FileNotFoundError for fixture to test fallback to constants for QF/SF game numbers
        mock_file_open.side_effect = FileNotFoundError 

        # Constants from constants.py (assuming these are the fallbacks if fixture fails)
        # These numbers are illustrative. The test will use whatever is in your actual constants.py for 2023.
        # For this example, let's use game numbers starting from 13 for playoffs for clarity in test data.
        qf_nums = [13, 14, 15, 16]
        sf_nums = [17, 18]
        final_bronze_nums = [19, 20]

        games_data = [
            # Prelims - Group A (CAN A1, SUI A2, CZE A3, NOR A4)
            Game(id=1, year_id=1, championship_year=year2023, round="Preliminary Round", group="A", team1_code="CAN", team2_code="SUI", team1_score=3, team2_score=2, result_type="REG", game_number=1),
            Game(id=2, year_id=1, championship_year=year2023, round="Preliminary Round", group="A", team1_code="CAN", team2_code="CZE", team1_score=4, team2_score=1, result_type="REG", game_number=2),
            Game(id=3, year_id=1, championship_year=year2023, round="Preliminary Round", group="A", team1_code="CAN", team2_code="NOR", team1_score=5, team2_score=0, result_type="REG", game_number=3),
            Game(id=4, year_id=1, championship_year=year2023, round="Preliminary Round", group="A", team1_code="SUI", team2_code="CZE", team1_score=3, team2_score=1, result_type="REG", game_number=4),
            Game(id=5, year_id=1, championship_year=year2023, round="Preliminary Round", group="A", team1_code="SUI", team2_code="NOR", team1_score=6, team2_score=0, result_type="REG", game_number=5),
            Game(id=6, year_id=1, championship_year=year2023, round="Preliminary Round", group="A", team1_code="CZE", team2_code="NOR", team1_score=2, team2_score=0, result_type="REG", game_number=6),

            # Prelims - Group B (SWE B1, FIN B2, USA B3, GER B4)
            Game(id=7, year_id=1, championship_year=year2023, round="Preliminary Round", group="B", team1_code="SWE", team2_code="FIN", team1_score=2, team2_score=1, result_type="REG", game_number=7),
            Game(id=8, year_id=1, championship_year=year2023, round="Preliminary Round", group="B", team1_code="SWE", team2_code="USA", team1_score=3, team2_score=0, result_type="REG", game_number=8),
            Game(id=9, year_id=1, championship_year=year2023, round="Preliminary Round", group="B", team1_code="SWE", team2_code="GER", team1_score=4, team2_score=0, result_type="REG", game_number=9),
            Game(id=10, year_id=1, championship_year=year2023, round="Preliminary Round", group="B", team1_code="FIN", team2_code="USA", team1_score=4, team2_score=1, result_type="REG", game_number=10),
            Game(id=11, year_id=1, championship_year=year2023, round="Preliminary Round", group="B", team1_code="FIN", team2_code="GER", team1_score=5, team2_score=0, result_type="REG", game_number=11),
            Game(id=12, year_id=1, championship_year=year2023, round="Preliminary Round", group="B", team1_code="USA", team2_code="GER", team1_score=3, team2_score=2, result_type="REG", game_number=12),

            # Playoffs
            Game(id=13, year_id=1, championship_year=year2023, round="Quarterfinal", game_number=qf_nums[0], team1_code="A1", team2_code="B4", team1_score=5, team2_score=1, result_type="REG"), # CAN (A1) def. GER (B4)
            Game(id=14, year_id=1, championship_year=year2023, round="Quarterfinal", game_number=qf_nums[1], team1_code="A2", team2_code="B3", team1_score=3, team2_score=2, result_type="REG"), # SUI (A2) def. USA (B3)
            Game(id=15, year_id=1, championship_year=year2023, round="Quarterfinal", game_number=qf_nums[2], team1_code="B1", team2_code="A4", team1_score=6, team2_score=0, result_type="REG"), # SWE (B1) def. NOR (A4)
            Game(id=16, year_id=1, championship_year=year2023, round="Quarterfinal", game_number=qf_nums[3], team1_code="B2", team2_code="A3", team1_score=4, team2_score=1, result_type="REG"), # FIN (B2) def. CZE (A3)
            
            Game(id=17, year_id=1, championship_year=year2023, round="Semifinal", game_number=sf_nums[0], team1_code=f"W({qf_nums[0]})", team2_code=f"W({qf_nums[3]})", team1_score=3, team2_score=2, result_type="OT"), # CAN def. FIN
            Game(id=18, year_id=1, championship_year=year2023, round="Semifinal", game_number=sf_nums[1], team1_code=f"W({qf_nums[1]})", team2_code=f"W({qf_nums[2]})", team1_score=1, team2_score=4, result_type="REG"), # SWE def. SUI
            
            Game(id=19, year_id=1, championship_year=year2023, round="Bronze Medal Game", game_number=final_bronze_nums[0], team1_code=f"L({sf_nums[0]})", team2_code=f"L({sf_nums[1]})", team1_score=4, team2_score=3, result_type="REG"), # FIN def. SUI
            Game(id=20, year_id=1, championship_year=year2023, round="Final", game_number=final_bronze_nums[1], team1_code=f"W({sf_nums[0]})", team2_code=f"W({sf_nums[1]})", team1_score=2, team2_score=1, result_type="REG"), # CAN def. SWE
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()
        
        self.assertEqual(len(result), 8) # CAN, SUI, CZE, NOR, SWE, FIN, USA, GER

        can_stats = next(s for s in result if s.team_code == "CAN")
        self.assertEqual(can_stats.gp, 6); self.assertEqual(can_stats.w, 5); self.assertEqual(can_stats.otw, 1); self.assertEqual(can_stats.pts, 17)
        
        swe_stats = next(s for s in result if s.team_code == "SWE")
        self.assertEqual(swe_stats.gp, 6); self.assertEqual(swe_stats.w, 5); self.assertEqual(swe_stats.l, 1); self.assertEqual(swe_stats.pts, 15)

        fin_stats = next(s for s in result if s.team_code == "FIN")
        self.assertEqual(fin_stats.gp, 6); self.assertEqual(fin_stats.w, 4); self.assertEqual(fin_stats.otl, 1); self.assertEqual(fin_stats.pts, 13)

        sui_stats = next(s for s in result if s.team_code == "SUI") # Prelim: 2W=6. QF: W=3. SF: L=0. Bronze: L=0. Total=9
        self.assertEqual(sui_stats.gp, 6); self.assertEqual(sui_stats.w, 3); self.assertEqual(sui_stats.l, 3); self.assertEqual(sui_stats.pts, 9)

        placeholders = ["A1", "B4", f"W({qf_nums[0]})", f"L({sf_nums[0]})"]
        for p_holder in placeholders:
            self.assertFalse(any(s.team_code == p_holder for s in result), f"Placeholder {p_holder} found in final standings")
        
        mock_logger.warning.assert_not_called()


    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('routes.main_routes.ChampionshipYear.query')
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_multiple_years_data(self, mock_game_query, mock_db_in_routes, mock_championship_year_query, mock_file_open):
        mock_db_in_routes.joinedload = self.db_mock.joinedload
        mock_file_open.side_effect = FileNotFoundError # Use constants for game numbers

        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023, fixture_path="d23.json")
        year2024 = ChampionshipYear(id=2, name="2024 Worlds", year=2024, fixture_path="d24.json")
        mock_championship_year_query.all.return_value = [year2023, year2024]

        games_data = [
            # 2023 (Simplified: CAN wins, USA second)
            Game(id=1, year_id=1, championship_year=year2023, round="Preliminary Round", group="A", team1_code="CAN", team2_code="USA", team1_score=3, team2_score=1, result_type="REG", game_number=1),
            Game(id=2, year_id=1, championship_year=year2023, round="Final", game_number=2, team1_code="CAN", team2_code="USA", team1_score=5, team2_score=4, result_type="SO"), # CAN wins SO
            # 2024 (Simplified: SWE wins, CAN second)
            Game(id=3, year_id=2, championship_year=year2024, round="Preliminary Round", group="A", team1_code="SWE", team2_code="CAN", team1_score=4, team2_score=2, result_type="REG", game_number=3),
            Game(id=4, year_id=2, championship_year=year2024, round="Final", game_number=4, team1_code="SWE", team2_code="CAN", team1_score=2, team2_score=1, result_type="OT"), # SWE wins OT
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        self.assertEqual(len(result), 3) # CAN, USA, SWE
        
        can_stats = next(s for s in result if s.team_code == "CAN")
        # 2023: GP=2, W=1, SOW=1, GF=8, GA=5, PTS=3+2=5
        # 2024: GP=2, L=1, OTL=1, GF=2+1=3, GA=4+2=6, PTS=0+1=1
        # Total: GP=4, W=1, SOW=1, L=1, OTL=1, GF=11, GA=11, PTS=6
        self.assertEqual(can_stats.gp, 4)
        self.assertEqual(can_stats.w, 1)
        self.assertEqual(can_stats.sow, 1)
        self.assertEqual(can_stats.l, 1)
        self.assertEqual(can_stats.otl, 1)
        self.assertEqual(can_stats.pts, 6)
        self.assertEqual(can_stats.num_years_participated, 2)
        self.assertEqual(can_stats.years_participated, {2023, 2024})

        usa_stats = next(s for s in result if s.team_code == "USA") # Only 2023
        # GP=2, L=1, SOL=1, GF=1+4=5, GA=3+5=8, PTS=1
        self.assertEqual(usa_stats.gp, 2); self.assertEqual(usa_stats.l, 1); self.assertEqual(usa_stats.sol, 1); self.assertEqual(usa_stats.pts, 1)
        self.assertEqual(usa_stats.num_years_participated, 1)

        swe_stats = next(s for s in result if s.team_code == "SWE") # Only 2024
        # GP=2, W=1, OTW=1, GF=4+2=6, GA=2+1=3, PTS=3+2=5
        self.assertEqual(swe_stats.gp, 2); self.assertEqual(swe_stats.w, 1); self.assertEqual(swe_stats.otw, 1); self.assertEqual(swe_stats.pts, 5)
        self.assertEqual(swe_stats.num_years_participated, 1)
        
        mock_logger.warning.assert_not_called()


    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('routes.main_routes.ChampionshipYear.query')
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_specific_outcomes(self, mock_game_query, mock_db_in_routes, mock_championship_year_query, mock_file_open): # Focus on SO and OT points
        mock_db_in_routes.joinedload = self.db_mock.joinedload
        mock_file_open.side_effect = FileNotFoundError # Use constants

        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023, fixture_path="d.json")
        mock_championship_year_query.all.return_value = [year2023]
        
        games_data = [
            Game(id=1, year_id=1, championship_year=year2023, team1_code="TeamA", team2_code="TeamB", team1_score=4, team2_score=3, result_type="SO", game_number=1),
            Game(id=2, year_id=1, championship_year=year2023, team1_code="TeamC", team2_code="TeamD", team1_score=2, team2_score=1, result_type="OT", game_number=2),
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        self.assertEqual(len(result), 4)
        teamA_stats = next(s for s in result if s.team_code == "TeamA")
        self.assertEqual(teamA_stats.sow, 1); self.assertEqual(teamA_stats.pts, 2)
        mock_logger.warning.assert_not_called()

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('routes.main_routes.ChampionshipYear.query')
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_games_without_scores(self, mock_game_query, mock_db_in_routes, mock_championship_year_query, mock_file_open):
        mock_db_in_routes.joinedload = self.db_mock.joinedload
        mock_file_open.side_effect = FileNotFoundError

        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023, fixture_path="d.json")
        mock_championship_year_query.all.return_value = [year2023]
        
        games_data = [
            Game(id=1, year_id=1, championship_year=year2023, team1_code="TeamX", team2_code="TeamY", team1_score=None, team2_score=None, result_type="REG", game_number=1),
            Game(id=2, year_id=1, championship_year=year2023, team1_code="TeamX", team2_code="TeamZ", team1_score=2, team2_score=1, result_type="REG", game_number=2),
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        self.assertEqual(len(result), 2) 
        teamX_stats = next(s for s in result if s.team_code == "TeamX")
        self.assertEqual(teamX_stats.gp, 1)
        mock_logger.warning.assert_not_called()


    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('routes.main_routes.ChampionshipYear.query')
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_unknown_result_type(self, mock_game_query, mock_db_in_routes, mock_championship_year_query, mock_file_open):
        mock_db_in_routes.joinedload = self.db_mock.joinedload
        mock_file_open.side_effect = FileNotFoundError

        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023, fixture_path="d.json")
        mock_championship_year_query.all.return_value = [year2023]

        games_data = [
            Game(id=1, year_id=1, championship_year=year2023, team1_code="TeamA", team2_code="TeamB", team1_score=3, team2_score=1, result_type="REG", game_number=1),
            Game(id=2, year_id=1, championship_year=year2023, team1_code="TeamA", team2_code="TeamC", team1_score=2, team2_score=1, result_type="UNKNOWN_TYPE", game_number=2),
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()
        
        teamA_stats = next(s for s in result if s.team_code == "TeamA")
        self.assertEqual(teamA_stats.gp, 2)
        self.assertEqual(teamA_stats.w, 1) 
        self.assertEqual(teamA_stats.pts, 3) 
        mock_logger.warning.assert_any_call(f"Game ID 2 has unhandled result_type: 'UNKNOWN_TYPE'. Points not assigned for this type.")

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('routes.main_routes.ChampionshipYear.query')
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_missing_team_codes_in_game_data(self, mock_game_query, mock_db_in_routes, mock_championship_year_query, mock_file_open):
        mock_db_in_routes.joinedload = self.db_mock.joinedload
        mock_file_open.side_effect = FileNotFoundError

        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023, fixture_path="d.json")
        mock_championship_year_query.all.return_value = [year2023]
        
        games_data = [
            # Game with None for team code, should be skipped by resolver or is_code_final checks
            Game(id=1, year_id=1, championship_year=year2023, team1_code=None, team2_code="TeamB", team1_score=3, team2_score=1, result_type="REG", game_number=1),
            Game(id=2, year_id=1, championship_year=year2023, team1_code="TeamA", team2_code="TeamC", team1_score=2, team2_score=1, result_type="REG", game_number=2),
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        self.assertEqual(len(result), 2) 
        teamA_stats = next(s for s in result if s.team_code == "TeamA")
        self.assertEqual(teamA_stats.gp, 1)
        # Check that the warning for skipping due to non-final codes was logged for game 1
        # The exact log message depends on where the None code is caught first.
        # If get_resolved_team_code('') returns '', then is_code_final('') is False.
        mock_logger.warning.assert_any_call(unittest.mock.ANY) # Check if any warning was logged


    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('routes.main_routes.ChampionshipYear.query')
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_unresolved_placeholders_skipped(self, mock_game_query, mock_db_in_routes, mock_championship_year_query, mock_file_open):
        mock_db_in_routes.joinedload = self.db_mock.joinedload
        mock_file_open.side_effect = FileNotFoundError

        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023, fixture_path="d.json")
        mock_championship_year_query.all.return_value = [year2023]

        games_data = [
            # Prelims to define A1
            Game(id=1, year_id=1, championship_year=year2023, round="Preliminary Round", group="A", team1_code="CAN", team2_code="USA", team1_score=3, team2_score=1, result_type="REG", game_number=1),
            # QF game where B4 is never defined (Group B has no games or B4 doesn't exist)
            Game(id=2, year_id=1, championship_year=year2023, round="Quarterfinal", game_number=57, team1_code="A1", team2_code="B4", team1_score=5, team2_score=1, result_type="REG"),
            # Another valid game to ensure some stats are processed
            Game(id=3, year_id=1, championship_year=year2023, round="Preliminary Round", group="C", team1_code="SWE", team2_code="FIN", team1_score=2, team2_score=0, result_type="REG", game_number=3),
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        # Expected: CAN, USA, SWE, FIN. Game 2 (A1 vs B4) should be skipped.
        # CAN: GP from game 1. A1 from game 1.
        # B4 is unresolved.
        self.assertEqual(len(result), 4) # CAN, USA, SWE, FIN
        can_stats = next(s for s in result if s.team_code == "CAN")
        self.assertEqual(can_stats.gp, 1) # Only game 1, not game 2 (A1 vs B4)
        
        found_warning = False
        for call in mock_logger.warning.call_args_list:
            if "Skipping for all-time stats due to non-final team codes" in call[0][0] and \
               "Game ID 2" in call[0][0] and "'B4'" in call[0][0]: # B4 would be unresolved
                found_warning = True
                break
        self.assertTrue(found_warning, "Expected warning for unresolved placeholder B4 was not logged.")


if __name__ == '__main__':
    unittest.main()
