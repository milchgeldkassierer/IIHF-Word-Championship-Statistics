import re
from collections import defaultdict
from models import db, Goal, Player, Game, ChampionshipYear
from .utils import get_all_resolved_games


def get_fastest_goal():
    """Findet die TOP 3 schnellsten Tore (basierend auf Minute)"""
    def parse_minute(minute_str):
        if not minute_str:
            return 999
        match = re.match(r'(\d+):(\d+)', minute_str)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            return minutes * 60 + seconds
        try:
            return int(minute_str) * 60
        except:
            return 999
    
    goals = db.session.query(Goal).join(Player, Goal.scorer_id == Player.id).all()
    resolved_games = get_all_resolved_games()
    
    # Erstelle ein Mapping von game_id zu aufgelösten Team-Codes
    game_id_to_resolved = {}
    for resolved_game in resolved_games:
        game_id_to_resolved[resolved_game['game'].id] = {
            'team1_code': resolved_game['team1_code'], 
            'team2_code': resolved_game['team2_code']
        }
    
    goal_times = []
    for goal in goals:
        time_seconds = parse_minute(goal.minute)
        game = db.session.query(Game).filter_by(id=goal.game_id).first()
        year = db.session.query(ChampionshipYear).filter_by(id=game.year_id).first()
        
        # Verwende aufgelöste Team-Codes falls verfügbar
        resolved_teams = game_id_to_resolved.get(goal.game_id)
        if resolved_teams:
            team1_code = resolved_teams['team1_code']
            team2_code = resolved_teams['team2_code']
            vs_team = team2_code if team1_code == goal.team_code else team1_code
        else:
            # Fallback auf ursprüngliche Logik
            vs_team = game.team2_code if game and game.team1_code == goal.team_code else (game.team1_code if game else 'Unknown')
        
        goal_times.append({
            'player': f"{goal.scorer.first_name} {goal.scorer.last_name}",
            'team': goal.team_code,
            'minute': goal.minute,
            'time_seconds': time_seconds,
            'year': year.year if year else 'Unknown',
            'tournament': year.name if year else 'Unknown',
            'vs_team': vs_team,
            'rank': 0
        })
    
    goal_times.sort(key=lambda x: x['time_seconds'])
    
    top_3_results = []
    current_rank = 1
    last_time = None
    
    for goal_time in goal_times:
        if last_time is None or goal_time['time_seconds'] != last_time:
            if current_rank > 3:
                break
            goal_time['rank'] = current_rank
            last_time = goal_time['time_seconds']
            current_rank += 1
        else:
            goal_time['rank'] = current_rank - 1
        
        if goal_time['rank'] <= 3:
            top_3_results.append(goal_time)
    
    return top_3_results


def get_fastest_hattrick():
    """Findet die TOP 3 schnellsten Hattricks"""
    goals = db.session.query(Goal).join(Player, Goal.scorer_id == Player.id).order_by(Goal.game_id, Goal.scorer_id, Goal.minute).all()
    resolved_games = get_all_resolved_games()
    
    # Erstelle ein Mapping von game_id zu aufgelösten Team-Codes
    game_id_to_resolved = {}
    for resolved_game in resolved_games:
        game_id_to_resolved[resolved_game['game'].id] = {
            'team1_code': resolved_game['team1_code'], 
            'team2_code': resolved_game['team2_code']
        }
    
    player_game_goals = defaultdict(list)
    for goal in goals:
        key = (goal.scorer_id, goal.game_id)
        player_game_goals[key].append(goal)
    
    all_hattricks = []
    
    def parse_minute(minute_str):
        if not minute_str:
            return 999
        match = re.match(r'(\d+):(\d+)', minute_str)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            return minutes * 60 + seconds
        try:
            return int(minute_str) * 60
        except:
            return 999
    
    def format_duration(duration_seconds):
        """Konvertiert Sekunden in Minuten:Sekunden Format"""
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    for (player_id, game_id), game_goals in player_game_goals.items():
        if len(game_goals) >= 3:
            game_goals.sort(key=lambda g: parse_minute(g.minute))
            
            first_goal_time = parse_minute(game_goals[0].minute)
            third_goal_time = parse_minute(game_goals[2].minute)
            duration = third_goal_time - first_goal_time
            
            player = db.session.query(Player).filter_by(id=player_id).first()
            game = db.session.query(Game).filter_by(id=game_id).first()
            year = db.session.query(ChampionshipYear).filter_by(id=game.year_id).first()
            
            # Verwende aufgelöste Team-Codes falls verfügbar
            resolved_teams = game_id_to_resolved.get(game_id)
            if resolved_teams:
                team1_code = resolved_teams['team1_code']
                team2_code = resolved_teams['team2_code']
                vs_team = team2_code if team1_code == game_goals[0].team_code else team1_code
            else:
                # Fallback auf ursprüngliche Logik
                vs_team = game.team2_code if game and game.team1_code == game_goals[0].team_code else (game.team1_code if game else 'Unknown')
            
            all_hattricks.append({
                'player': f"{player.first_name} {player.last_name}" if player else 'Unknown',
                'team': game_goals[0].team_code,
                'first_goal': game_goals[0].minute,
                'second_goal': game_goals[1].minute,
                'third_goal': game_goals[2].minute,
                'duration_seconds': duration,
                'duration_formatted': format_duration(duration),
                'year': year.year if year else 'Unknown',
                'tournament': year.name if year else 'Unknown',
                'vs_team': vs_team,
                'rank': 0
            })
    
    all_hattricks.sort(key=lambda x: x['duration_seconds'])
    
    top_3_results = []
    current_rank = 1
    last_duration = None
    
    for hattrick in all_hattricks:
        if last_duration is None or hattrick['duration_seconds'] != last_duration:
            if current_rank > 3:
                break
            hattrick['rank'] = current_rank
            last_duration = hattrick['duration_seconds']
            current_rank += 1
        else:
            hattrick['rank'] = current_rank - 1
        
        if hattrick['rank'] <= 3:
            top_3_results.append(hattrick)
    
    return top_3_results