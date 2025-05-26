import unittest
from unittest.mock import patch, MagicMock

# Assuming the app structure allows these imports
# If running tests from the root directory:
# from models import Game, ChampionshipYear, AllTimeTeamStats, db # db might not be needed if fully mocking
# from routes.main_routes import calculate_all_time_standings

# For the environment where this code will be executed, let's assume direct import works
# or that PYTHONPATH is set up correctly.
# If 'db' is used for db.joinedload, we might need to mock 'db' or ensure it's available.
# However, Game.query.options(db.joinedload(...)) means 'db' is accessed from 'models' import.
# Let's try to mock db.joinedload if it becomes an issue, or mock the full 'options' chain.

from models import Game, ChampionshipYear, AllTimeTeamStats, db as actual_db_object
from routes.main_routes import calculate_all_time_standings

# Mock for current_app.logger
mock_logger = MagicMock()

class TestAllTimeStandings(unittest.TestCase):

    def setUp(self):
        # Create minimal mock for db.joinedload to avoid issues if it's called by the SUT
        # This mock assumes db.joinedload simply returns its argument, which is often sufficient
        # if the loaded relationship (game.championship_year) is manually set on test objects.
        self.db_mock = MagicMock()
        self.db_mock.joinedload = lambda x: x # Simple pass-through

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('routes.main_routes.db', new_callable=MagicMock) # Mock the db object used for joinedload
    @patch('routes.main_routes.Game.query')
    def test_no_games(self, mock_game_query, mock_db_in_routes):
        mock_db_in_routes.joinedload = lambda x: x # Ensure joinedload is a pass-through
        mock_game_query.options.return_value.all.return_value = []
        
        result = calculate_all_time_standings()
        self.assertEqual(result, [])
        mock_logger.warning.assert_not_called()

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_single_year_data(self, mock_game_query, mock_db_in_routes):
        mock_db_in_routes.joinedload = lambda x: x
        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023)
        
        games_data = [
            Game(id=1, year_id=1, championship_year=year2023, team1_code="CAN", team2_code="FIN", team1_score=3, team2_score=1, result_type="REG"),
            Game(id=2, year_id=1, championship_year=year2023, team1_code="SWE", team2_code="USA", team1_score=2, team2_score=3, result_type="OT"), # USA wins in OT
            Game(id=3, year_id=1, championship_year=year2023, team1_code="CAN", team2_code="SWE", team1_score=5, team2_score=4, result_type="SO"), # CAN wins in SO
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        
        result = calculate_all_time_standings()
        
        self.assertEqual(len(result), 4) # CAN, FIN, SWE, USA

        # Expected:
        # CAN: GP=2, W=1 (vs FIN), SOW=1 (vs SWE), GF=3+5=8, GA=1+4=5, GD=3, PTS=3+2=5, Years=1
        # USA: GP=1, OTW=1 (vs SWE), GF=3, GA=2, GD=1, PTS=2, Years=1
        # FIN: GP=1, L=1 (vs CAN), GF=1, GA=3, GD=-2, PTS=0, Years=1
        # SWE: GP=2, OTL=1 (vs USA), SOL=1 (vs CAN), GF=2+4=6, GA=3+5=8, GD=-2, PTS=1+1=2, Years=1
        
        # Order: CAN (5pts), USA (2pts, GD 1), SWE (2pts, GD -2), FIN (0pts)
        
        can_stats = next(s for s in result if s.team_code == "CAN")
        self.assertEqual(can_stats.gp, 2)
        self.assertEqual(can_stats.w, 1)
        self.assertEqual(can_stats.otw, 0)
        self.assertEqual(can_stats.sow, 1)
        self.assertEqual(can_stats.l, 0)
        self.assertEqual(can_stats.otl, 0)
        self.assertEqual(can_stats.sol, 0)
        self.assertEqual(can_stats.gf, 8)
        self.assertEqual(can_stats.ga, 5)
        self.assertEqual(can_stats.gd, 3)
        self.assertEqual(can_stats.pts, 5)
        self.assertEqual(can_stats.num_years_participated, 1)
        self.assertEqual(can_stats.years_participated, {2023})

        usa_stats = next(s for s in result if s.team_code == "USA")
        self.assertEqual(usa_stats.gp, 1)
        self.assertEqual(usa_stats.w, 0)
        self.assertEqual(usa_stats.otw, 1)
        self.assertEqual(usa_stats.sow, 0)
        self.assertEqual(usa_stats.gf, 3)
        self.assertEqual(usa_stats.ga, 2)
        self.assertEqual(usa_stats.gd, 1)
        self.assertEqual(usa_stats.pts, 2)
        self.assertEqual(usa_stats.num_years_participated, 1)

        swe_stats = next(s for s in result if s.team_code == "SWE")
        self.assertEqual(swe_stats.gp, 2)
        self.assertEqual(swe_stats.l, 0) # No regulation losses
        self.assertEqual(swe_stats.otl, 1)
        self.assertEqual(swe_stats.sol, 1)
        self.assertEqual(swe_stats.gf, 6)
        self.assertEqual(swe_stats.ga, 8)
        self.assertEqual(swe_stats.gd, -2)
        self.assertEqual(swe_stats.pts, 2) # 1 from OTL, 1 from SOL
        self.assertEqual(swe_stats.num_years_participated, 1)

        fin_stats = next(s for s in result if s.team_code == "FIN")
        self.assertEqual(fin_stats.gp, 1)
        self.assertEqual(fin_stats.l, 1)
        self.assertEqual(fin_stats.gf, 1)
        self.assertEqual(fin_stats.ga, 3)
        self.assertEqual(fin_stats.gd, -2)
        self.assertEqual(fin_stats.pts, 0)
        self.assertEqual(fin_stats.num_years_participated, 1)
        
        # Check sorting: CAN, USA, SWE, FIN
        self.assertEqual(result[0].team_code, "CAN")
        self.assertEqual(result[1].team_code, "USA")
        self.assertEqual(result[2].team_code, "SWE")
        self.assertEqual(result[3].team_code, "FIN")
        mock_logger.warning.assert_not_called()

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_multiple_years_data(self, mock_game_query, mock_db_in_routes):
        mock_db_in_routes.joinedload = lambda x: x
        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023)
        year2024 = ChampionshipYear(id=2, name="2024 Worlds", year=2024)

        games_data = [
            # 2023
            Game(id=1, year_id=1, championship_year=year2023, team1_code="CAN", team2_code="FIN", team1_score=3, team2_score=1, result_type="REG"), # CAN 3pts
            Game(id=2, year_id=1, championship_year=year2023, team1_code="SWE", team2_code="USA", team1_score=2, team2_score=3, result_type="OT"),  # USA 2pts, SWE 1pt
            # 2024
            Game(id=3, year_id=2, championship_year=year2024, team1_code="CAN", team2_code="SWE", team1_score=4, team2_score=2, result_type="REG"), # CAN 3pts
            Game(id=4, year_id=2, championship_year=year2024, team1_code="FIN", team2_code="GER", team1_score=5, team2_score=1, result_type="REG"), # FIN 3pts
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        self.assertEqual(len(result), 5) # CAN, FIN, SWE, USA, GER

        # CAN: 2023 (W vs FIN), 2024 (W vs SWE)
        # GP=2, W=2, GF=3+4=7, GA=1+2=3, GD=4, PTS=3+3=6, Years=2 ({2023, 2024})
        can_stats = next(s for s in result if s.team_code == "CAN")
        self.assertEqual(can_stats.gp, 2)
        self.assertEqual(can_stats.w, 2)
        self.assertEqual(can_stats.gf, 7)
        self.assertEqual(can_stats.ga, 3)
        self.assertEqual(can_stats.pts, 6)
        self.assertEqual(can_stats.num_years_participated, 2)
        self.assertEqual(can_stats.years_participated, {2023, 2024})

        # FIN: 2023 (L vs CAN), 2024 (W vs GER)
        # GP=2, W=1, L=1, GF=1+5=6, GA=3+1=4, GD=2, PTS=0+3=3, Years=2 ({2023, 2024})
        fin_stats = next(s for s in result if s.team_code == "FIN")
        self.assertEqual(fin_stats.gp, 2)
        self.assertEqual(fin_stats.w, 1)
        self.assertEqual(fin_stats.l, 1)
        self.assertEqual(fin_stats.gf, 6)
        self.assertEqual(fin_stats.ga, 4)
        self.assertEqual(fin_stats.pts, 3)
        self.assertEqual(fin_stats.num_years_participated, 2)
        self.assertEqual(fin_stats.years_participated, {2023, 2024})

        # SWE: 2023 (OTL vs USA), 2024 (L vs CAN)
        # GP=2, L=1, OTL=1, GF=2+2=4, GA=3+4=7, GD=-3, PTS=1+0=1, Years=2 ({2023, 2024})
        swe_stats = next(s for s in result if s.team_code == "SWE")
        self.assertEqual(swe_stats.gp, 2)
        self.assertEqual(swe_stats.l, 1)
        self.assertEqual(swe_stats.otl, 1)
        self.assertEqual(swe_stats.gf, 4)
        self.assertEqual(swe_stats.ga, 7)
        self.assertEqual(swe_stats.pts, 1)
        self.assertEqual(swe_stats.num_years_participated, 2)
        self.assertEqual(swe_stats.years_participated, {2023, 2024})
        
        # USA: 2023 (OTW vs SWE)
        # GP=1, OTW=1, GF=3, GA=2, GD=1, PTS=2, Years=1 ({2023})
        usa_stats = next(s for s in result if s.team_code == "USA")
        self.assertEqual(usa_stats.gp, 1)
        self.assertEqual(usa_stats.otw, 1)
        self.assertEqual(usa_stats.gf, 3)
        self.assertEqual(usa_stats.ga, 2)
        self.assertEqual(usa_stats.pts, 2)
        self.assertEqual(usa_stats.num_years_participated, 1)
        self.assertEqual(usa_stats.years_participated, {2023})

        # GER: 2024 (L vs FIN)
        # GP=1, L=1, GF=1, GA=5, GD=-4, PTS=0, Years=1 ({2024})
        ger_stats = next(s for s in result if s.team_code == "GER")
        self.assertEqual(ger_stats.gp, 1)
        self.assertEqual(ger_stats.l, 1)
        self.assertEqual(ger_stats.gf, 1)
        self.assertEqual(ger_stats.ga, 5)
        self.assertEqual(ger_stats.pts, 0)
        self.assertEqual(ger_stats.num_years_participated, 1)
        self.assertEqual(ger_stats.years_participated, {2024})

        # Expected Order: CAN (6pts), FIN (3pts), USA (2pts), SWE (1pt), GER (0pts)
        self.assertEqual(result[0].team_code, "CAN")
        self.assertEqual(result[1].team_code, "FIN")
        self.assertEqual(result[2].team_code, "USA")
        self.assertEqual(result[3].team_code, "SWE")
        self.assertEqual(result[4].team_code, "GER")
        mock_logger.warning.assert_not_called()

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_specific_outcomes(self, mock_game_query, mock_db_in_routes): # Focus on SO and OT points
        mock_db_in_routes.joinedload = lambda x: x
        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023)
        games_data = [
            # Team A wins in SO (2pts), Team B loses in SO (1pt)
            Game(id=1, year_id=1, championship_year=year2023, team1_code="TeamA", team2_code="TeamB", team1_score=4, team2_score=3, result_type="SO"),
            # Team C wins in OT (2pts), Team D loses in OT (1pt)
            Game(id=2, year_id=1, championship_year=year2023, team1_code="TeamC", team2_code="TeamD", team1_score=2, team2_score=1, result_type="OT"),
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        self.assertEqual(len(result), 4)
        
        teamA_stats = next(s for s in result if s.team_code == "TeamA")
        self.assertEqual(teamA_stats.sow, 1); self.assertEqual(teamA_stats.pts, 2)

        teamB_stats = next(s for s in result if s.team_code == "TeamB")
        self.assertEqual(teamB_stats.sol, 1); self.assertEqual(teamB_stats.pts, 1)

        teamC_stats = next(s for s in result if s.team_code == "TeamC")
        self.assertEqual(teamC_stats.otw, 1); self.assertEqual(teamC_stats.pts, 2)

        teamD_stats = next(s for s in result if s.team_code == "TeamD")
        self.assertEqual(teamD_stats.otl, 1); self.assertEqual(teamD_stats.pts, 1)
        mock_logger.warning.assert_not_called()

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_games_without_scores(self, mock_game_query, mock_db_in_routes):
        mock_db_in_routes.joinedload = lambda x: x
        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023)
        games_data = [
            Game(id=1, year_id=1, championship_year=year2023, team1_code="TeamX", team2_code="TeamY", team1_score=None, team2_score=None, result_type="REG"),
            Game(id=2, year_id=1, championship_year=year2023, team1_code="TeamX", team2_code="TeamZ", team1_score=2, team2_score=1, result_type="REG"),
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        self.assertEqual(len(result), 2) # TeamX, TeamZ (TeamY not included if only in game w/o score)
        
        teamX_stats = next(s for s in result if s.team_code == "TeamX")
        self.assertEqual(teamX_stats.gp, 1) # Only counts game with score
        self.assertEqual(teamX_stats.w, 1)
        self.assertEqual(teamX_stats.pts, 3)
        self.assertEqual(teamX_stats.gf, 2)
        self.assertEqual(teamX_stats.ga, 1)

        teamZ_stats = next(s for s in result if s.team_code == "TeamZ")
        self.assertEqual(teamZ_stats.gp, 1)
        self.assertEqual(teamZ_stats.l, 1)
        self.assertEqual(teamZ_stats.pts, 0)
        
        # Check if TeamY is in results - it shouldn't be if its only game had no score
        teamY_exists = any(s.team_code == "TeamY" for s in result)
        self.assertFalse(teamY_exists, "TeamY should not be in standings if its only game had no score.")
        mock_logger.warning.assert_not_called() # No warnings expected for skipping games with None scores

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_unknown_result_type(self, mock_game_query, mock_db_in_routes):
        mock_db_in_routes.joinedload = lambda x: x
        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023)
        games_data = [
            Game(id=1, year_id=1, championship_year=year2023, team1_code="TeamA", team2_code="TeamB", team1_score=3, team2_score=1, result_type="REG"),
            Game(id=2, year_id=1, championship_year=year2023, team1_code="TeamA", team2_code="TeamC", team1_score=2, team2_score=1, result_type="UNKNOWN_TYPE"),
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        teamA_stats = next(s for s in result if s.team_code == "TeamA")
        # TeamA: Game1 (W, 3pts), Game2 (W, 0pts due to unknown type)
        self.assertEqual(teamA_stats.gp, 2)
        self.assertEqual(teamA_stats.w, 1) # Only 1 REG win counted for points logic
        self.assertEqual(teamA_stats.pts, 3) # Points only from REG game
        self.assertEqual(teamA_stats.gf, 3 + 2)
        self.assertEqual(teamA_stats.ga, 1 + 1)
        
        mock_logger.warning.assert_any_call(f"Game ID 2 has unknown result_type: UNKNOWN_TYPE. Points not assigned.")

    @patch('routes.main_routes.current_app.logger', mock_logger)
    @patch('routes.main_routes.db', new_callable=MagicMock)
    @patch('routes.main_routes.Game.query')
    def test_missing_team_codes(self, mock_game_query, mock_db_in_routes):
        mock_db_in_routes.joinedload = lambda x: x
        year2023 = ChampionshipYear(id=1, name="2023 Worlds", year=2023)
        games_data = [
            Game(id=1, year_id=1, championship_year=year2023, team1_code=None, team2_code="TeamB", team1_score=3, team2_score=1, result_type="REG"),
            Game(id=2, year_id=1, championship_year=year2023, team1_code="TeamA", team2_code="TeamC", team1_score=2, team2_score=1, result_type="REG"),
        ]
        mock_game_query.options.return_value.all.return_value = games_data
        result = calculate_all_time_standings()

        self.assertEqual(len(result), 2) # Only TeamA and TeamC
        teamA_stats = next(s for s in result if s.team_code == "TeamA")
        self.assertEqual(teamA_stats.gp, 1)

        mock_logger.warning.assert_any_call(f"Game ID 1 has missing team codes. Skipping.")


if __name__ == '__main__':
    unittest.main()
