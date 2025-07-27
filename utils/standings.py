from typing import Dict, List
from collections import defaultdict

from models import Game, TeamStats
from constants import PRELIM_ROUNDS, MAX_PRELIM_GAMES_PER_TEAM
from .team_resolution import is_code_final


def _calculate_basic_prelim_standings(prelim_games_for_year: List[Game]) -> Dict[str, TeamStats]:
    """
    Calculates simplified standings for preliminary round games of a single year.
    Focuses on points, goal difference, goals for, and rank_in_group for ranking.
    Returns a dictionary mapping team codes to their TeamStats objects.
    """
    standings: Dict[str, TeamStats] = {}

    for game in prelim_games_for_year:
        if game.round not in PRELIM_ROUNDS or game.team1_score is None or game.team2_score is None:
            continue

        # Ensure teams are initialized with their group
        # Only process games where both participants are final team codes
        if not is_code_final(game.team1_code) or not is_code_final(game.team2_code):
            continue # Should not happen for prelim games used for standings
            
        current_game_group = game.group # Assuming game object has group info for prelims

        if game.team1_code not in standings:
            # Ensure group is a string, default if None for safety, though expected from fixture
            standings[game.team1_code] = TeamStats(name=game.team1_code, group=current_game_group or "N/A")
        # Update group if it was N/A and now we have one
        elif standings[game.team1_code].group == "N/A" and current_game_group is not None:
             standings[game.team1_code].group = current_game_group


        if game.team2_code not in standings:
            standings[game.team2_code] = TeamStats(name=game.team2_code, group=current_game_group or "N/A")
        elif standings[game.team2_code].group == "N/A" and current_game_group is not None:
            standings[game.team2_code].group = current_game_group


        # Verwende StandingsCalculator für die Aktualisierung der Statistiken
        from services.standings_calculator_adapter import StandingsCalculator
        calculator = StandingsCalculator()
        calculator.update_team_stats(standings, game)
    
    # Calculate rank_in_group with head-to-head comparison
    grouped_standings_for_ranking: Dict[str, List[TeamStats]] = {}
    for ts_code, ts_obj in standings.items():
        # Ensure all objects have a group; default if necessary
        group_key = ts_obj.group if ts_obj.group else "UnknownGroup" 
        if group_key not in grouped_standings_for_ranking:
            grouped_standings_for_ranking[group_key] = []
        grouped_standings_for_ranking[group_key].append(ts_obj)

    for group_name, group_list in grouped_standings_for_ranking.items():
        # Sort by pts (desc), head-to-head comparison, gd (desc), gf (desc)
        group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        
        # Apply head-to-head tiebreaker for teams with equal points
        group_list = _apply_head_to_head_tiebreaker(group_list, prelim_games_for_year)
        
        for i, ts_in_group in enumerate(group_list):
            ts_in_group.rank_in_group = i + 1
            # The original standings dict values are the same objects, so rank is updated.

    return standings


def _apply_head_to_head_tiebreaker(teams_list: List[TeamStats], all_games: List[Game]) -> List[TeamStats]:
    """
    Apply head-to-head tiebreaker for teams with equal points.
    Returns the sorted list with head-to-head results considered.
    """
    if len(teams_list) <= 1:
        return teams_list
    
    # Group teams by points
    teams_by_points = {}
    for team in teams_list:
        points = team.pts
        if points not in teams_by_points:
            teams_by_points[points] = []
        teams_by_points[points].append(team)
    
    result = []
    
    # Process each point group separately
    for points in sorted(teams_by_points.keys(), reverse=True):
        point_group = teams_by_points[points]
        
        if len(point_group) == 1:
            result.extend(point_group)
        else:
            # Apply head-to-head tiebreaker within this point group
            sorted_group = _sort_teams_by_head_to_head(point_group, all_games)
            result.extend(sorted_group)
    
    return result


def _sort_teams_by_head_to_head(tied_teams: List[TeamStats], all_games: List[Game]) -> List[TeamStats]:
    """
    Sort teams that are tied on points by head-to-head results following updated IIHF rules.
    
    Updated Tie-breaking procedure:
    - For 2 teams: Direct game between them is decisive ONLY if it has been played
      If direct game not played: Use overall goal difference and goals for
    - For 3+ teams tied: 
      Head-to-head tiebreaker ONLY applies if ALL teams have played ALL their 7 preliminary games
      If not all games played: Use overall goal difference and goals for
    """
    if len(tied_teams) <= 1:
        return tied_teams
    
    # Check if we have exactly 2 teams or more than 2 teams
    if len(tied_teams) == 2:
        return _sort_two_teams_by_head_to_head(tied_teams, all_games)
    else:
        return _sort_multiple_teams_by_head_to_head(tied_teams, all_games)


def _sort_two_teams_by_head_to_head(tied_teams: List[TeamStats], all_games: List[Game]) -> List[TeamStats]:
    """
    Sort exactly 2 teams that are tied on points.
    Uses head-to-head if the direct game has been played, otherwise overall stats.
    """
    team1, team2 = tied_teams[0], tied_teams[1]
    
    # Find head-to-head games between these two teams
    head_to_head_games = []
    for game in all_games:
        if (game.team1_code == team1.name and game.team2_code == team2.name) or \
           (game.team1_code == team2.name and game.team2_code == team1.name):
            if (game.team1_score is not None and game.team2_score is not None and
                game.round in PRELIM_ROUNDS):
                head_to_head_games.append(game)
    
    # If direct game has been played, use head-to-head result
    if head_to_head_games:
        # Calculate head-to-head stats
        h2h_stats = {
            team1.name: {'points': 0, 'gf': 0, 'ga': 0},
            team2.name: {'points': 0, 'gf': 0, 'ga': 0}
        }
        
        for game in head_to_head_games:
            team1_h2h = h2h_stats[game.team1_code] if game.team1_code in h2h_stats else h2h_stats[game.team2_code]
            team2_h2h = h2h_stats[game.team2_code] if game.team2_code in h2h_stats else h2h_stats[game.team1_code]
            
            # Determine which team is which in the game
            if game.team1_code == team1.name:
                t1_score, t2_score = game.team1_score, game.team2_score
                t1_h2h, t2_h2h = h2h_stats[team1.name], h2h_stats[team2.name]
            else:
                t1_score, t2_score = game.team2_score, game.team1_score
                t1_h2h, t2_h2h = h2h_stats[team1.name], h2h_stats[team2.name]
            
            t1_h2h['gf'] += t1_score
            t1_h2h['ga'] += t2_score
            t2_h2h['gf'] += t2_score
            t2_h2h['ga'] += t1_score
            
            # Award points based on result
            if game.result_type == 'REG':
                if t1_score > t2_score:
                    t1_h2h['points'] += 3
                else:
                    t2_h2h['points'] += 3
            elif game.result_type in ['OT', 'SO']:
                if t1_score > t2_score:
                    t1_h2h['points'] += 2
                    t2_h2h['points'] += 1
                else:
                    t2_h2h['points'] += 2
                    t1_h2h['points'] += 1
        
        # Sort by head-to-head results
        team_list = [(team1, h2h_stats[team1.name]), (team2, h2h_stats[team2.name])]
        team_list.sort(key=lambda x: (
            x[1]['points'],                    # H2H points
            x[1]['gf'] - x[1]['ga'],          # H2H goal difference
            x[1]['gf'],                       # H2H goals for
            x[0].gd,                          # Overall goal difference
            x[0].gf                           # Overall goals for
        ), reverse=True)
        
        return [team_obj for team_obj, _ in team_list]
    
    # No direct game played, use overall stats
    return sorted(tied_teams, key=lambda x: (x.gd, x.gf), reverse=True)


def _sort_multiple_teams_by_head_to_head(tied_teams: List[TeamStats], all_games: List[Game]) -> List[TeamStats]:
    """
    Sort 3+ teams that are tied on points.
    Uses head-to-head only if ALL teams have played ALL their 7 preliminary games.
    """
    # Check if all teams have played all their preliminary games
    all_games_completed = all(team.gp >= MAX_PRELIM_GAMES_PER_TEAM for team in tied_teams)
    
    if not all_games_completed:
        # Not all games played, use overall stats
        return sorted(tied_teams, key=lambda x: (x.gd, x.gf), reverse=True)
    
    # All games completed, use head-to-head tiebreaker
    team_names = {team.name for team in tied_teams}
    head_to_head_games = []
    
    for game in all_games:
        if (game.team1_code in team_names and game.team2_code in team_names and 
            game.team1_score is not None and game.team2_score is not None and
            game.round in PRELIM_ROUNDS):
            head_to_head_games.append(game)
    
    # Calculate head-to-head records
    h2h_stats = {}
    for team in tied_teams:
        h2h_stats[team.name] = {
            'points': 0,
            'gf': 0,
            'ga': 0,
            'team_obj': team
        }
    
    for game in head_to_head_games:
        team1_h2h = h2h_stats[game.team1_code]
        team2_h2h = h2h_stats[game.team2_code]
        
        team1_h2h['gf'] += game.team1_score
        team1_h2h['ga'] += game.team2_score
        team2_h2h['gf'] += game.team2_score
        team2_h2h['ga'] += game.team1_score
        
        # Award points based on result (IIHF 3-point system)
        if game.result_type == 'REG':
            if game.team1_score > game.team2_score:
                team1_h2h['points'] += 3
            else:
                team2_h2h['points'] += 3
        elif game.result_type in ['OT', 'SO']:
            if game.team1_score > game.team2_score:
                team1_h2h['points'] += 2
                team2_h2h['points'] += 1
            else:
                team2_h2h['points'] += 2
                team1_h2h['points'] += 1
    
    # Sort by head-to-head criteria
    h2h_list = list(h2h_stats.values())
    h2h_list.sort(key=lambda x: (
        x['points'],                # Head-to-head points
        x['gf'] - x['ga'],         # Head-to-head goal difference
        x['gf'],                   # Head-to-head goals for
        x['team_obj'].gd,          # Overall goal difference
        x['team_obj'].gf           # Overall goals for
    ), reverse=True)
    
    return [h2h['team_obj'] for h2h in h2h_list]


def calculate_complete_final_ranking(year_obj, games_this_year, playoff_map, year_obj_for_map):
    """
    Calculates complete final tournament ranking (1st-16th place) including medals.
    Handles playoff seeding, medal games, and custom seeding scenarios.
    """
    final_ranking = {}
    
    # Load custom QF seeding if it exists to ensure proper team resolution
    custom_qf_seeding = None
    try:
        from routes.year.seeding import get_custom_qf_seeding_from_db
        custom_qf_seeding = get_custom_qf_seeding_from_db(year_obj_for_map.id)
    except ImportError:
        pass  # Continue without custom QF seeding if import fails
    
    # Create a copy of playoff_map and integrate custom QF seeding
    enhanced_playoff_map = playoff_map.copy() if playoff_map else {}
    if custom_qf_seeding:
        # Apply custom QF seeding to playoff map for proper team resolution
        for position, team_name in custom_qf_seeding.items():
            enhanced_playoff_map[position] = team_name
    
    def trace_team_from_medal_games():
        sf_games = [g for g in games_this_year if g.round == "Semifinals" and g.team1_score is not None and g.team2_score is not None]
        
        # Bei manuell geändertem Seeding: sammle alle Semifinal-Gewinner und -Verlierer
        # unabhängig von Game-Nummern, da die Zuordnung durch das Custom Seeding gestört ist
        sf_winners = []
        sf_losers = []
        sf_results = {}
        
        for sf_game in sf_games:
            # Löse die Teams direkt auf, falls sie noch Platzhalter sind
            team1_resolved = sf_game.team1_code
            team2_resolved = sf_game.team2_code
            
            # CRITICAL FIX: Resolve seed1, seed2, seed3, seed4 placeholders using enhanced_playoff_map for custom seeding
            if not is_code_final(team1_resolved) and enhanced_playoff_map and team1_resolved in enhanced_playoff_map:
                team1_resolved = enhanced_playoff_map.get(team1_resolved, team1_resolved)
            if not is_code_final(team2_resolved) and enhanced_playoff_map and team2_resolved in enhanced_playoff_map:
                team2_resolved = enhanced_playoff_map.get(team2_resolved, team2_resolved)
            
            # Bei manuell geändertem Seeding sind die Teams jetzt aufgelöst
            if is_code_final(team1_resolved) and is_code_final(team2_resolved):
                winner = team1_resolved if sf_game.team1_score > sf_game.team2_score else team2_resolved
                loser = team2_resolved if sf_game.team1_score > sf_game.team2_score else team1_resolved
            else:
                # Fallback für den Fall, dass noch Platzhalter verwendet werden
                winner = sf_game.team1_code if sf_game.team1_score > sf_game.team2_score else sf_game.team2_code
                loser = sf_game.team2_code if sf_game.team1_score > sf_game.team2_score else sf_game.team1_code
            
            sf_winners.append(winner)
            sf_losers.append(loser)
            
            # CRITICAL FIX: Determine SF1/SF2 based on which teams are playing
            # With custom seeding, we need to identify which semifinal is which
            # SF1 should be seed1 vs seed4 (standard IIHF format)
            # SF2 should be seed2 vs seed3 (standard IIHF format)
            
            # First, check if we can determine SF1/SF2 from the teams playing
            if enhanced_playoff_map and 'seed1' in enhanced_playoff_map and 'seed2' in enhanced_playoff_map and 'seed3' in enhanced_playoff_map and 'seed4' in enhanced_playoff_map:
                q1_team = enhanced_playoff_map['seed1']
                q2_team = enhanced_playoff_map['seed2']
                q3_team = enhanced_playoff_map['seed3']
                q4_team = enhanced_playoff_map['seed4']
                
                # Check which teams are in this semifinal
                teams_in_game = {team1_resolved, team2_resolved}
                
                # Standard IIHF bracket: SF1 = seed1 vs seed4, SF2 = seed2 vs seed3
                if q1_team in teams_in_game and (q4_team in teams_in_game or q2_team in teams_in_game):
                    # This is SF1
                    sf_results["W(SF1)"] = winner
                    sf_results["L(SF1)"] = loser
                elif q2_team in teams_in_game and q3_team in teams_in_game:
                    # This is SF2 (seed2 vs seed3)
                    sf_results["W(SF2)"] = winner
                    sf_results["L(SF2)"] = loser
                elif q3_team in teams_in_game and q4_team in teams_in_game:
                    # This is SF2 (was old format, now should be seed2 vs seed3)
                    sf_results["W(SF2)"] = winner
                    sf_results["L(SF2)"] = loser
                else:
                    # Fallback to game number
                    if sf_game.game_number == 61:
                        sf_results["W(SF1)"] = winner
                        sf_results["L(SF1)"] = loser
                    elif sf_game.game_number == 62:
                        sf_results["W(SF2)"] = winner
                        sf_results["L(SF2)"] = loser
            else:
                # Fallback: use game numbers
                if sf_game.game_number == 61:  # SF1
                    sf_results["W(SF1)"] = winner
                    sf_results["L(SF1)"] = loser
                elif sf_game.game_number == 62:  # SF2  
                    sf_results["W(SF2)"] = winner
                    sf_results["L(SF2)"] = loser
        
        team_map = {}
        prelim_games = [g for g in games_this_year if g.round in PRELIM_ROUNDS and is_code_final(g.team1_code) and is_code_final(g.team2_code)]
        
        # Verwende StandingsCalculator für die Berechnung der Gruppenstandings
        from services.standings_calculator_adapter import StandingsCalculator
        calculator = StandingsCalculator()
        all_team_stats = calculator.calculate_standings_from_games(
            [g for g in prelim_games if g.team1_score is not None]
        )
        
        # Gruppiere Teams nach ihrer Gruppe
        group_standings = {}
        for team_code, team_stats in all_team_stats.items():
            group = team_stats.group
            if group and group != "N/A":
                if group not in group_standings:
                    group_standings[group] = []
                group_standings[group].append(team_stats)
        
        # Sortiere und berechne Ränge für jede Gruppe
        for group, team_stats_list in group_standings.items():
            team_stats_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
            team_stats_list = _apply_head_to_head_tiebreaker(team_stats_list, prelim_games)
            
            group_letter = group.replace("Group ", "") if group.startswith("Group ") else group
            for i, team_stat in enumerate(team_stats_list, 1):
                team_map[f"{group_letter}{i}"] = team_stat.name
        
        qf_games = [g for g in games_this_year if g.round == "Quarterfinals" and g.team1_score is not None and g.team2_score is not None]
        qf_games.sort(key=lambda x: x.game_number or 0)
        
        qf_winners = []
        for qf_game in qf_games:
            winner_code = qf_game.team1_code if qf_game.team1_score > qf_game.team2_score else qf_game.team2_code
            if winner_code in team_map:
                actual_team = team_map[winner_code]
                qf_winners.append(actual_team)
            else:
                qf_winners.append(winner_code)
        
        qf_winner_stats = []
        for actual_team in qf_winners:
            team_rank_in_group = None
            team_group = None
            team_stats = None
            
            for placeholder, mapped_team in team_map.items():
                if mapped_team == actual_team:
                    if len(placeholder) >= 2:
                        team_group = placeholder[0]
                        try:
                            team_rank_in_group = int(placeholder[1:])
                        except ValueError:
                            continue
                    break
            
            for group, teams in group_standings.items():
                group_letter = group.replace("Group ", "") if group.startswith("Group ") else group
                if group_letter == team_group and actual_team in teams:
                    team_stats = teams[actual_team]
                    break
            
            if team_rank_in_group and team_stats:
                qf_winner_stats.append({
                    'team': actual_team,
                    'group': team_group,
                    'rank_in_group': team_rank_in_group,
                    'pts': team_stats['pts'],
                    'gd': team_stats['gf'] - team_stats['ga'],
                    'gf': team_stats['gf']
                })
        
        qf_winner_stats.sort(key=lambda x: (-x['pts'], -x['gd'], -x['gf'], x['rank_in_group']))
        
        qf_results = {}
        
        # CRITICAL: Use enhanced_playoff_map for seed1-seed4 if provided (contains custom seeding)
        if enhanced_playoff_map and all(key in enhanced_playoff_map for key in ['seed1', 'seed2', 'seed3', 'seed4']):
            # Use enhanced_playoff_map (which contains custom seeding)
            qf_results["seed1"] = enhanced_playoff_map['seed1']
            qf_results["seed2"] = enhanced_playoff_map['seed2']
            qf_results["seed3"] = enhanced_playoff_map['seed3']
            qf_results["seed4"] = enhanced_playoff_map['seed4']
        elif len(qf_winner_stats) >= 4:
            # Fallback to calculated seeding if no playoff_map provided
            qf_results["seed1"] = qf_winner_stats[0]['team']
            qf_results["seed2"] = qf_winner_stats[1]['team']
            qf_results["seed3"] = qf_winner_stats[2]['team']
            qf_results["seed4"] = qf_winner_stats[3]['team']
        
        def resolve_code(code):
            if is_code_final(code):
                return code
            # Check enhanced_playoff_map first (includes custom QF seeding)
            if code in enhanced_playoff_map:
                return enhanced_playoff_map[code]
            if code in team_map:
                return team_map[code]
            if code in qf_results:
                return resolve_code(qf_results[code])
            if code in sf_results:
                return resolve_code(sf_results[code])
            
            # Spezielle Behandlung für Medal Game Platzhalter bei manuell geändertem Seeding
            # Da die Game-Nummer-basierte Zuordnung gestört ist, nutze die tatsächlichen Ergebnisse
            if code.startswith('L(SF') and len(sf_losers) >= 2:
                # Für Bronze Medal Game: nutze die beiden Semifinal-Verlierer
                if code == 'L(SF1)':
                    return sf_losers[0] if is_code_final(sf_losers[0]) else sf_losers[0]
                elif code == 'L(SF2)':
                    return sf_losers[1] if is_code_final(sf_losers[1]) else sf_losers[1]
            elif code.startswith('W(SF') and len(sf_winners) >= 2:
                # Für Gold Medal Game: nutze die beiden Semifinal-Gewinner
                if code == 'W(SF1)':
                    return sf_winners[0] if is_code_final(sf_winners[0]) else sf_winners[0]
                elif code == 'W(SF2)':
                    return sf_winners[1] if is_code_final(sf_winners[1]) else sf_winners[1]
                    
            return code
        
        return resolve_code

    resolve_team = trace_team_from_medal_games()
    
    def calculate_medals_simple(games_this_year, enhanced_playoff_map):
        """
        Simple medal calculation following IIHF rules:
        - SF1 = Game 61: seed1 vs seed4
        - SF2 = Game 62: seed2 vs seed3  
        - Bronze: Loser(SF1) vs Loser(SF2) → Winner gets Bronze
        - Gold: Winner(SF1) vs Winner(SF2) → Winner gets Gold
        """
        final_ranking = {}
        
        # Check if we have custom seeding in enhanced_playoff_map
        has_seeding = (enhanced_playoff_map and 
                       'seed1' in enhanced_playoff_map and 
                       'seed2' in enhanced_playoff_map and 
                       'seed3' in enhanced_playoff_map and 
                       'seed4' in enhanced_playoff_map and
                       is_code_final(enhanced_playoff_map['seed1']))
        
        # If no proper seeding in enhanced_playoff_map, build it from QF results
        if not has_seeding:
            from .seeding_helpers import get_custom_seeding_from_db
            try:
                custom_seeding = get_custom_seeding_from_db(year_obj_for_map.id)
                if custom_seeding:
                    # Use custom seeding
                    enhanced_playoff_map = enhanced_playoff_map.copy() if enhanced_playoff_map else {}
                    enhanced_playoff_map.update(custom_seeding)
                else:
                    # Build seeding from QF winners for years without custom seeding
                    qf_games = [g for g in games_this_year if g.round == "Quarterfinals" and g.team1_score is not None and g.team2_score is not None]
                    qf_winners = []
                    for qf_game in qf_games:
                        winner = qf_game.team1_code if qf_game.team1_score > qf_game.team2_score else qf_game.team2_code
                        qf_winners.append(winner)
                    
                    # Resolve QF winners to actual teams and build seeding based on group rank
                    if len(qf_winners) == 4:
                        # Get group standings
                        prelim_games = [g for g in games_this_year if g.round in PRELIM_ROUNDS and is_code_final(g.team1_code) and is_code_final(g.team2_code) and g.team1_score is not None]
                        group_standings = {"Group A": [], "Group B": []}
                        
                        # Build proper group standings using same logic as codebase
                        prelim_stats_map = {}
                        
                        # Build stats using same method as existing codebase
                        for game_prelim in prelim_games:
                            current_game_group = game_prelim.group or "N/A"
                            for team_code_val in [game_prelim.team1_code, game_prelim.team2_code]:
                                if team_code_val not in prelim_stats_map:
                                    prelim_stats_map[team_code_val] = TeamStats(name=team_code_val, group=current_game_group)
                                elif prelim_stats_map[team_code_val].group == "N/A" and current_game_group != "N/A":
                                    prelim_stats_map[team_code_val].group = current_game_group
                            
                            # Verwende StandingsCalculator für die Aktualisierung der Statistiken
                            from services.standings_calculator_adapter import StandingsCalculator
                            calculator = StandingsCalculator()
                            calculator.update_team_stats(prelim_stats_map, game_prelim)

                        # Sort teams by group using proper tiebreaker
                        for group_name in group_standings:
                            group_teams = [ts for ts in prelim_stats_map.values() if ts.group == group_name]
                            group_teams.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
                            
                            # Apply head-to-head tiebreaker (critical for correct standings!)
                            group_games = [g for g in prelim_games if g.group == group_name]
                            group_teams = _apply_head_to_head_tiebreaker(group_teams, group_games)
                            
                            # Set ranks and convert to tuple format
                            for i, ts in enumerate(group_teams):
                                ts.rank_in_group = i + 1
                                group_standings[group_name].append((ts.name, ts.pts, ts.gd))
                        
                        # Resolve QF winners and determine seeding
                        qf_teams_resolved = []
                        for winner_code in qf_winners:
                            if winner_code.startswith('A'):
                                rank = int(winner_code[1:])
                                if rank <= len(group_standings["Group A"]):
                                    team, pts, gd = group_standings["Group A"][rank-1]
                                    qf_teams_resolved.append((team, "A", rank, pts, gd))
                            elif winner_code.startswith('B'):
                                rank = int(winner_code[1:])
                                if rank <= len(group_standings["Group B"]):
                                    team, pts, gd = group_standings["Group B"][rank-1]
                                    qf_teams_resolved.append((team, "B", rank, pts, gd))
                            else:
                                # Already resolved team name
                                qf_teams_resolved.append((winner_code, "?", 99, 0, 0))
                        
                        
                        # Sort for seeding (by points first, then goal difference, then rank)
                        qf_teams_resolved.sort(key=lambda x: (-x[3], -x[4], x[2]))
                        
                        
                        if len(qf_teams_resolved) == 4:
                            enhanced_playoff_map = enhanced_playoff_map.copy() if enhanced_playoff_map else {}
                            enhanced_playoff_map['seed1'] = qf_teams_resolved[0][0]
                            enhanced_playoff_map['seed2'] = qf_teams_resolved[1][0]
                            enhanced_playoff_map['seed3'] = qf_teams_resolved[2][0]
                            enhanced_playoff_map['seed4'] = qf_teams_resolved[3][0]
            except:
                pass  # Continue with original enhanced_playoff_map
        
        # Step 1: Find SF games (always game 61 and 62)
        sf1_game = next((g for g in games_this_year if g.game_number == 61 and g.team1_score is not None), None)
        sf2_game = next((g for g in games_this_year if g.game_number == 62 and g.team1_score is not None), None)
        
        if not sf1_game or not sf2_game:
            return final_ranking
        
        # Step 2: Resolve seed1-seed4 to actual teams
        seed1 = enhanced_playoff_map.get('seed1', 'seed1') if enhanced_playoff_map else 'seed1'
        seed2 = enhanced_playoff_map.get('seed2', 'seed2') if enhanced_playoff_map else 'seed2'
        seed3 = enhanced_playoff_map.get('seed3', 'seed3') if enhanced_playoff_map else 'seed3'
        seed4 = enhanced_playoff_map.get('seed4', 'seed4') if enhanced_playoff_map else 'seed4'
        
        
        # Step 3: Determine SF winners and losers
        # SF1: seed1 vs seed4
        if sf1_game.team1_score > sf1_game.team2_score:
            w_sf1, l_sf1 = seed1, seed4
        else:
            w_sf1, l_sf1 = seed4, seed1
            
        # SF2: seed2 vs seed3
        if sf2_game.team1_score > sf2_game.team2_score:
            w_sf2, l_sf2 = seed2, seed3
        else:
            w_sf2, l_sf2 = seed3, seed2
        
        # Step 4: Find medal games
        bronze_game = next((g for g in games_this_year if g.round == "Bronze Medal Game" and g.team1_score is not None), None)
        gold_game = next((g for g in games_this_year if g.round == "Gold Medal Game" and g.team1_score is not None), None)
        
        # Step 5: Apply simple medal logic
        if bronze_game:
            # Bronze: L(SF1) vs L(SF2) - But we need to check which loser is team1 vs team2
            # The bronze game has placeholders L(SF1) and L(SF2), not necessarily in that order
            if bronze_game.team1_score > bronze_game.team2_score:
                # team1 won the bronze game
                if bronze_game.team1_code == 'L(SF1)':
                    bronze, fourth = l_sf1, l_sf2  # L(SF1) won
                else:  # bronze_game.team1_code == 'L(SF2)'
                    bronze, fourth = l_sf2, l_sf1  # L(SF2) won
            else:
                # team2 won the bronze game
                if bronze_game.team2_code == 'L(SF1)':
                    bronze, fourth = l_sf1, l_sf2  # L(SF1) won
                else:  # bronze_game.team2_code == 'L(SF2)'
                    bronze, fourth = l_sf2, l_sf1  # L(SF2) won
        
        if gold_game:
            # Gold: W(SF1) vs W(SF2) - But we need to check which winner is team1 vs team2
            # The gold game has placeholders W(SF1) and W(SF2), not necessarily in that order
            if gold_game.team1_score > gold_game.team2_score:
                # team1 won the gold game
                if gold_game.team1_code == 'W(SF1)':
                    gold, silver = w_sf1, w_sf2  # W(SF1) won
                else:  # gold_game.team1_code == 'W(SF2)'
                    gold, silver = w_sf2, w_sf1  # W(SF2) won
            else:
                # team2 won the gold game
                if gold_game.team2_code == 'W(SF1)':
                    gold, silver = w_sf1, w_sf2  # W(SF1) won
                else:  # gold_game.team2_code == 'W(SF2)'
                    gold, silver = w_sf2, w_sf1  # W(SF2) won
        
        # Set final ranking
        if bronze_game and gold_game:
            final_ranking[1] = gold
            final_ranking[2] = silver
            final_ranking[3] = bronze
            final_ranking[4] = fourth
        
        return final_ranking
    
    games_map = {g.game_number: g for g in games_this_year if g.game_number is not None}
    
    # Finde Medal Games (Bronze und Final)
    bronze_game = None
    final_game = None
    
    for game in games_this_year:
        if game.round == "Bronze Medal Game":
            bronze_game = game
        elif game.round == "Gold Medal Game":
            final_game = game
    
    # GENERELLE LÖSUNG FÜR CUSTOM SEEDING PROBLEM
    # Verbesserte Medal Game Auflösung die mit allen Jahren und Seeding-Arten funktioniert
    
    # Sammle alle Semifinal-Ergebnisse mit korrekter Team-Auflösung
    semifinal_teams_resolved = {}
    sf_games = [g for g in games_this_year if g.round == "Semifinals" and g.team1_score is not None and g.team2_score is not None]
    
    for sf_game in sf_games:
        # Löse Teams auf (bei Custom Seeding sind es bereits echte Teams, sonst Platzhalter)
        team1 = sf_game.team1_code if is_code_final(sf_game.team1_code) else resolve_team(sf_game.team1_code)
        team2 = sf_game.team2_code if is_code_final(sf_game.team2_code) else resolve_team(sf_game.team2_code)
        
        winner = team1 if sf_game.team1_score > sf_game.team2_score else team2
        loser = team2 if sf_game.team1_score > sf_game.team2_score else team1
        
        # Speichere mit Game-Nummer für korrekte Zuordnung
        game_key = f"SF{sf_game.game_number - 60}" if sf_game.game_number >= 61 else f"SF{len(semifinal_teams_resolved) + 1}"
        semifinal_teams_resolved[f"W({game_key})"] = winner
        semifinal_teams_resolved[f"L({game_key})"] = loser
    
    # Prüfe ob Custom Seeding verwendet wird
    has_custom_seeding = False
    try:
        from .seeding_helpers import get_custom_seeding_from_db
        custom_seeding = get_custom_seeding_from_db(year_obj_for_map.id)
        has_custom_seeding = custom_seeding is not None
    except Exception as e:
        has_custom_seeding = False
    
    # Prepare semifinal data for medal game resolution
    sf_winners = []
    sf_losers = []
    
    # Simple medal calculation for all years (both custom seeding and automatic)
    final_ranking = calculate_medals_simple(games_this_year, enhanced_playoff_map)
    
    # Berechne die restlichen Plätze (5-16)
    prelim_stats_map = {}
    prelim_games = [
        g for g in games_this_year
        if g.round in PRELIM_ROUNDS and \
           is_code_final(g.team1_code) and \
           is_code_final(g.team2_code) and \
           g.team1_score is not None and g.team2_score is not None
    ]
    
    for game in prelim_games:
        current_game_group = game.group or "N/A"
        for team_code in [game.team1_code, game.team2_code]:
            if team_code not in prelim_stats_map:
                prelim_stats_map[team_code] = TeamStats(name=team_code, group=current_game_group)
            elif prelim_stats_map[team_code].group == "N/A" and current_game_group != "N/A":
                prelim_stats_map[team_code].group = current_game_group
        
        # Verwende StandingsCalculator für die Aktualisierung der Statistiken
        from services.standings_calculator_adapter import StandingsCalculator
        calculator = StandingsCalculator()
        calculator.update_team_stats(prelim_stats_map, game)
    
    standings_by_group = {}
    for ts in prelim_stats_map.values():
        group_key = ts.group if ts.group else "UnknownGroup"
        standings_by_group.setdefault(group_key, []).append(ts)
    
    for group_list in standings_by_group.values():
        group_list.sort(key=lambda x: (x.pts, x.gd, x.gf), reverse=True)
        group_list = _apply_head_to_head_tiebreaker(group_list, prelim_games)
        for i, ts in enumerate(group_list):
            ts.rank_in_group = i + 1
    
    qf_losers = []
    qf_games = [g for g in games_this_year if g.round == "Quarterfinals" and g.team1_score is not None and g.team2_score is not None]
    
    for qf_game in qf_games:
        loser_code = qf_game.team2_code if qf_game.team1_score > qf_game.team2_score else qf_game.team1_code
        loser_resolved = resolve_team(loser_code)
        if is_code_final(loser_resolved):
            qf_losers.append(loser_resolved)
    
    qf_losers_stats = [prelim_stats_map.get(team) for team in qf_losers if team in prelim_stats_map]
    qf_losers_stats = [ts for ts in qf_losers_stats if ts is not None]
    qf_losers_stats.sort(key=lambda x: (-x.pts, -x.gd, -x.gf, x.rank_in_group))
    
    for i, ts in enumerate(qf_losers_stats):
        if 5 + i <= 8:
            final_ranking[5 + i] = ts.name
    
    all_playoff_teams = set(final_ranking.values())
    remaining_teams = []
    
    for ts in prelim_stats_map.values():
        if ts.name not in all_playoff_teams:
            remaining_teams.append(ts)
    
    remaining_teams.sort(key=lambda x: (-x.pts, -x.gd, -x.gf, x.rank_in_group))
    
    current_position = 9
    for ts in remaining_teams:
        if current_position <= 16:
            final_ranking[current_position] = ts.name
            current_position += 1

    return final_ranking