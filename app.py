from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
import json
import os
from werkzeug.utils import secure_filename
from dataclasses import dataclass, field
import re
import traceback

# --- Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'fixtures')
ALLOWED_EXTENSIONS = {'json'}

TEAM_ISO_CODES = {
    "AUT": "at", "FIN": "fi", "SUI": "ch", "CZE": "cz",
    "SWE": "se", "SVK": "sk", "DEN": "dk", "USA": "us",
    "SLO": "si", "CAN": "ca", "NOR": "no", "KAZ": "kz",
    "GER": "de", "HUN": "hu", "FRA": "fr", "LAT": "lv",
    "ITA": "it", "GBR": "gb", "POL": "pl",
    "QF": None, "SF": None, "L(SF)": None, "W(SF)": None
}

app = Flask(__name__)
app.jinja_env.add_extension('jinja2.ext.do') # Enable the 'do' extension
app.config['SECRET_KEY'] = 'your_secret_key_please_change_this'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "data", "iihf_data.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# Define penalty choices
PENALTY_TYPES_CHOICES = ["2 Min", "2+2 Min", "5 Min + Spieldauer", "10 Min Disziplinar", "Spieldauer Disziplinar"]
PENALTY_REASONS_CHOICES = [
    "Bandencheck",
    "Behinderung",
    "Beinstellen",
    "Check von hinten",
    "Check gegen Nackenbereich", # Corrected from "Check gegen den Kopf/Nacken" to be more specific if intended, or keep as is if head is also included. Assuming Nackenbereich is the key focus.
    "Cross Checking",
    "Ellbogencheck",
    "Haken",
    "Halten",
    "Halten des Stocks",
    "Hoher Stock",
    "Kopfstoß",
    "Schiedsrichterkritik",
    "Stockschlag", # New
    "übertriebene Härte", # Corrected from "Übertriebene Härte"
    "unerlaubter Körperangriff", # New
    "unsportliches Verhalten", # Corrected from "Unsportliches Verhalten"
    "zu viele Spieler auf dem Eis" # New
    # "Stockschlag" and "Spielverzögerung" are removed as per the new list.
]

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_time_to_seconds(time_str):
    if not time_str or ':' not in time_str:
        return float('inf')
    try:
        minutes, seconds = map(int, time_str.split(':'))
        return minutes * 60 + seconds
    except ValueError:
        return float('inf')

# --- Dataclass for Team Statistics ---
@dataclass
class TeamStats:
    name: str
    group: str
    gp: int = 0; w: int = 0; otw: int = 0; sow: int = 0
    l: int = 0; otl: int = 0; sol: int = 0
    gf: int = 0; ga: int = 0; pts: int = 0
    rank_in_group: int = 0 # Added for semifinal seeding

    @property
    def gd(self) -> int:
        return self.gf - self.ga

@dataclass
class TeamOverallStats:
    team_name: str
    team_iso_code: str | None
    gp: int = 0
    gf: int = 0
    ga: int = 0
    eng: int = 0  # Empty Net Goals scored by this team
    sog: int = 0  # Shots On Goal FOR this team
    soga: int = 0 # Shots On Goal AGAINST this team
    so: int = 0   # Shutouts achieved by this team
    ppgf: int = 0 # Powerplay Goals For
    ppga: int = 0 # Powerplay Goals Against (goals conceded while opponent was on PP)
    ppf: int = 0  # Powerplay Opportunities For (estimated)
    ppa: int = 0  # Powerplay Opportunities Against (times shorthanded - estimated)
    pim: int = 0  # Total Penalty Infraction Minutes for the team

# --- Models ---
class ChampionshipYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    fixture_path = db.Column(db.String(300), nullable=True)
    games = db.relationship('Game', backref='championship_year', lazy=True, cascade="all, delete-orphan")
    def __repr__(self): return f'<ChampionshipYear {self.name} ({self.year})>'

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year_id = db.Column(db.Integer, db.ForeignKey('championship_year.id'), nullable=False)
    date = db.Column(db.String(20)); start_time = db.Column(db.String(20))
    round = db.Column(db.String(50)); group = db.Column(db.String(10), nullable=True)
    game_number = db.Column(db.Integer)
    team1_code = db.Column(db.String(3)); team2_code = db.Column(db.String(3))
    location = db.Column(db.String(100)); venue = db.Column(db.String(100))
    team1_score = db.Column(db.Integer, nullable=True); team2_score = db.Column(db.Integer, nullable=True)
    result_type = db.Column(db.String(10), nullable=True, default='REG')
    team1_points = db.Column(db.Integer, default=0); team2_points = db.Column(db.Integer, default=0)
    def __repr__(self): return f'<Game {self.game_number}: {self.team1_code} vs {self.team2_code}>'

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_code = db.Column(db.String(3), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    jersey_number = db.Column(db.Integer, nullable=True)
    def __repr__(self): return f'<Player {self.first_name} {self.last_name} (#{self.jersey_number} - {self.team_code})>'

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    team_code = db.Column(db.String(3), nullable=False)
    minute = db.Column(db.String(5), nullable=False)
    goal_type = db.Column(db.String(10), nullable=False)
    is_empty_net = db.Column(db.Boolean, default=False, nullable=False)
    scorer_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    assist1_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    assist2_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    game = db.relationship('Game', backref=db.backref('goals', lazy='dynamic', cascade="all, delete-orphan"))
    scorer = db.relationship('Player', foreign_keys=[scorer_id], backref=db.backref('goals_scored', lazy=True))
    assist1 = db.relationship('Player', foreign_keys=[assist1_id], backref=db.backref('assists1', lazy=True))
    assist2 = db.relationship('Player', foreign_keys=[assist2_id], backref=db.backref('assists2', lazy=True))
    def __repr__(self): return f'<Goal by {self.scorer_id} in Game {self.game_id} at {self.minute}>'

class Penalty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    team_code = db.Column(db.String(3), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    minute_of_game = db.Column(db.String(5), nullable=False)
    penalty_type = db.Column(db.String(10), nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    game = db.relationship('Game', backref=db.backref('penalties', lazy='dynamic', cascade="all, delete-orphan"))
    player = db.relationship('Player', foreign_keys=[player_id], backref=db.backref('penalties_taken', lazy=True))
    def __repr__(self): return f'<Penalty {self.penalty_type} to {self.team_code} in Game {self.game_id} at {self.minute_of_game}>'

class ShotsOnGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    team_code = db.Column(db.String(3), nullable=False)
    period = db.Column(db.Integer, nullable=False) # 1, 2, 3, 4 (OT)
    shots = db.Column(db.Integer, default=0, nullable=False)
    game = db.relationship('Game', backref=db.backref('sog_entries', lazy='dynamic', cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint('game_id', 'team_code', 'period', name='_game_team_period_uc'),)
    def __repr__(self): return f'<ShotsOnGoal Game {self.game_id} Team {self.team_code} P{self.period}: {self.shots}>'

# --- Dataclass for Game Display ---
@dataclass
class GameDisplay:
    id: int; year_id: int; date: str; start_time: str; round: str; group: str; game_number: int
    location: str; venue: str
    team1_code: str  # RESOLVED team code
    team2_code: str  # RESOLVED team code
    original_team1_code: str 
    original_team2_code: str 
    team1_score: int = None; team2_score: int = None
    result_type: str = None
    team1_points: int = 0; team2_points: int = 0
    sorted_events: list = field(default_factory=list)
    sog_data: dict = field(default_factory=dict) # {team_code: {period: shots}}
    scores_fully_match_goals: bool = False # Placeholder

# --- Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'delete_year' in request.form:
            year_id_to_delete = request.form.get('year_id_to_delete')
            year_obj_del = db.session.get(ChampionshipYear, year_id_to_delete)
            if year_obj_del:
                if year_obj_del.fixture_path and os.path.exists(year_obj_del.fixture_path):
                    # Only delete the fixture file if it's within the UPLOAD_FOLDER (managed files)
                    # and not one of the root template files in 'fixtures/'.
                    try:
                        abs_fixture_path = os.path.abspath(year_obj_del.fixture_path)
                        abs_upload_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
                        # Also consider the root 'fixtures' path to ensure templates there are not deleted.
                        # However, the primary check should be if it's *in* the UPLOAD_FOLDER.
                        # Files outside UPLOAD_FOLDER (like those directly in root 'fixtures') should be preserved.
                        if abs_fixture_path.startswith(abs_upload_folder):
                             # This implies the file is inside data/fixtures/ (e.g. data/fixtures/1_2024.json)
                             os.remove(year_obj_del.fixture_path)
                             flash(f'Associated fixture file "{os.path.basename(year_obj_del.fixture_path)}" from data directory deleted.', 'info')
                        # else: Do not delete if it's not in the UPLOAD_FOLDER (e.g. it is a template from root 'fixtures/')
                        # In this case, year_obj_del.fixture_path would be something like 'fixtures/2024.json'
                        # and we want to keep that file.
                    except OSError as e:
                        flash(f"Error deleting managed fixture file: {e}", "danger")
                
                db.session.delete(year_obj_del)
                db.session.commit()
                flash(f'Tournament "{year_obj_del.name} ({year_obj_del.year})" deleted.', 'success')
            else:
                flash('Tournament to delete not found.', 'warning')
            return redirect(url_for('index'))

        name_str = request.form.get('tournament_name')
        year_str = request.form.get('year')
        # fixture_file = request.files.get('fixture_file') # Removed: No longer uploading file manually

        if not name_str or not year_str:
            flash('Name and Year are required.', 'danger'); return redirect(url_for('index'))
        try: year_int = int(year_str)
        except ValueError: flash('Year must be a number.', 'danger'); return redirect(url_for('index'))

        existing_tournament = ChampionshipYear.query.filter_by(name=name_str, year=year_int).first()
        target_year_obj = existing_tournament # Use a different variable name to avoid confusion

        if not target_year_obj:
            new_tournament = ChampionshipYear(name=name_str, year=year_int)
            db.session.add(new_tournament)
            try:
                db.session.commit()
                target_year_obj = new_tournament
                flash(f'Tournament "{target_year_obj.name} ({target_year_obj.year})" created.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating tournament: {str(e)}', 'danger')
                return redirect(url_for('index'))
        else:
            flash(f'Tournament "{name_str} ({year_int})" already exists. Updating fixture based on selected year.', 'info')

        # Automatic fixture loading logic
        if target_year_obj: # Ensure tournament object exists (either new or existing)
            potential_fixture_filename = f"{year_str}.json"
            fixture_path_to_load = None

            # Check in UPLOAD_FOLDER (data/fixtures/) first
            path_in_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], potential_fixture_filename)
            if os.path.exists(path_in_upload_folder):
                fixture_path_to_load = path_in_upload_folder
            else:
                # Check in root 'fixtures' directory as a fallback
                path_in_root_fixtures = os.path.join(BASE_DIR, 'fixtures', potential_fixture_filename)
                if os.path.exists(path_in_root_fixtures):
                    fixture_path_to_load = path_in_root_fixtures
            
            # Try <id>_<year>.json format in UPLOAD_FOLDER if year.json not found there
            # This is primarily for files saved by the app itself if they used that naming.
            # For auto-loading, YYYY.json is the primary target.
            if not fixture_path_to_load and target_year_obj.id: # only if target_year_obj already has an id
                 potential_id_fixture_filename = f"{target_year_obj.id}_{year_str}.json"
                 path_id_in_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], potential_id_fixture_filename)
                 if os.path.exists(path_id_in_upload_folder):
                      fixture_path_to_load = path_id_in_upload_folder

            if fixture_path_to_load:
                # Delete old games for this tournament year before loading new ones
                Game.query.filter_by(year_id=target_year_obj.id).delete()
                try:
                    target_year_obj.fixture_path = fixture_path_to_load # Store the path of the loaded file
                    with open(fixture_path_to_load, 'r', encoding='utf-8') as f:
                        fixture_data = json.load(f)
                    
                    games_from_json = fixture_data.get("schedule", [])
                    for game_data_item in games_from_json:
                        mapped_game_data = {
                            'date': game_data_item.get('date'),
                            'start_time': game_data_item.get('startTime'),
                            'round': game_data_item.get('round'),
                            'group': game_data_item.get('group'),
                            'game_number': game_data_item.get('gameNumber'),
                            'team1_code': game_data_item.get('team1'),
                            'team2_code': game_data_item.get('team2'),
                            'location': game_data_item.get('location'),
                            'venue': game_data_item.get('venue')
                        }
                        new_game = Game(year_id=target_year_obj.id, **mapped_game_data)
                        db.session.add(new_game)
                    
                    db.session.commit()
                    flash(f'Fixture "{os.path.basename(fixture_path_to_load)}" loaded and games updated for "{target_year_obj.name} ({target_year_obj.year})".', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error processing fixture file "{os.path.basename(fixture_path_to_load if fixture_path_to_load else potential_fixture_filename)}": {str(e)} - {traceback.format_exc()}', 'danger')
            else:
                # If no fixture file is found, still commit the ChampionshipYear if it's new
                # but flash a warning that no schedule was loaded.
                if not existing_tournament: # It was a new tournament creation attempt
                    # db.session.commit() # Already committed if new_tournament was created
                    flash(f'Tournament "{target_year_obj.name} ({target_year_obj.year})" created, but no fixture file like "{year_str}.json" found in ./data/fixtures/ or ./fixtures/. Please add it and try again, or ensure it is named correctly.', 'warning')
                else: # It was an existing tournament, just inform that no fixture was found to update from
                    flash(f'No fixture file like "{year_str}.json" found in ./data/fixtures/ or ./fixtures/ for "{target_year_obj.name} ({target_year_obj.year})". Existing games (if any) remain.', 'info')
                # If the fixture_path was previously set and the new auto-detected file is not found, we should probably clear it or leave it.
                # For now, if no new file is found, we don't change target_year_obj.fixture_path if it was an existing tournament.
                # If it was a new tournament, target_year_obj.fixture_path will be None.

    all_years_db = ChampionshipYear.query.order_by(ChampionshipYear.year.desc(), ChampionshipYear.name).all()
    
    # Dynamically get years from fixture directories
    all_found_years = set()

    # Location 1: app.config['UPLOAD_FOLDER'] (e.g., data/fixtures)
    upload_folder_path = app.config['UPLOAD_FOLDER']
    if os.path.exists(upload_folder_path):
        for f_name in os.listdir(upload_folder_path):
            if f_name.endswith('.json'):
                year_part = f_name[:-5]  # Remove .json
                if '_' in year_part:  # Check for <id>_<year>.json format
                    potential_year = year_part.split('_')[-1]
                    if potential_year.isdigit():
                        all_found_years.add(potential_year)
                elif year_part.isdigit():  # Check for <year>.json format
                    all_found_years.add(year_part)

    # Location 2: 'fixtures' directory at the project root
    # (os.path.join(BASE_DIR, 'fixtures') would be more robust if app.py is not at root)
    # Assuming app.py is at project root, 'fixtures' is fine.
    root_fixtures_path = 'fixtures' 
    if os.path.exists(root_fixtures_path):
        for f_name in os.listdir(root_fixtures_path):
            if f_name.endswith('.json'):
                year_part = f_name[:-5] # Remove .json
                if year_part.isdigit(): # Expects simple YYYY.json in root 'fixtures'
                    all_found_years.add(year_part)
    
    sorted_fixture_years = sorted(list(all_found_years), reverse=True)

    return render_template('index.html', all_years=all_years_db, available_fixture_years=sorted_fixture_years)


@app.route('/year/<int:year_id>', methods=['GET', 'POST'])
def year_view(year_id):
    year_obj = db.session.get(ChampionshipYear, year_id)
    if not year_obj:
        flash('Tournament year not found.', 'danger'); return redirect(url_for('index'))

    games_raw = Game.query.filter_by(year_id=year_id).order_by(Game.date, Game.start_time, Game.game_number).all()
    
    sog_by_game_flat = {} 
    for sog_entry in ShotsOnGoal.query.join(Game).filter(Game.year_id == year_id).all():
        sog_by_game_flat.setdefault(sog_entry.game_id, {}).setdefault(sog_entry.team_code, {})[sog_entry.period] = sog_entry.shots

    if request.method == 'POST' and 'sog_team1_code_resolved' not in request.form:
        game_id_form = request.form.get('game_id')
        game_to_update = db.session.get(Game, game_id_form)
        if game_to_update:
            try:
                t1s = request.form.get('team1_score'); t2s = request.form.get('team2_score')
                game_to_update.team1_score = int(t1s) if t1s and t1s.strip() else None
                game_to_update.team2_score = int(t2s) if t2s and t2s.strip() else None
                res_type = request.form.get('result_type')
                
                if game_to_update.team1_score is None or game_to_update.team2_score is None:
                    game_to_update.result_type = None; game_to_update.team1_points = 0; game_to_update.team2_points = 0
                else:
                    game_to_update.result_type = res_type
                    if res_type == 'REG':
                        if game_to_update.team1_score > game_to_update.team2_score: pts1, pts2 = 3,0
                        elif game_to_update.team2_score > game_to_update.team1_score: pts1, pts2 = 0,3
                        else: pts1, pts2 = 1,1 # Draw in REG (if allowed by rules)
                        game_to_update.team1_points, game_to_update.team2_points = pts1, pts2
                    elif res_type in ['OT', 'SO']:
                        if game_to_update.team1_score > game_to_update.team2_score: game_to_update.team1_points, game_to_update.team2_points = 2,1
                        else: game_to_update.team1_points, game_to_update.team2_points = 1,2
                db.session.commit()
                flash('Game result updated!', 'success')
                return redirect(url_for('year_view', year_id=year_id, _anchor=f"game-{game_id_form}"))
            except Exception as e:
                db.session.rollback(); flash(f'Error updating result: {str(e)}', 'danger')
        else: flash('Game not found for update.', 'warning')

    # Initialize teams_stats with all teams scheduled in Preliminary Round groups
    teams_stats = {}
    prelim_games = [g for g in games_raw if g.round == 'Preliminary Round' and g.group]
    
    # Ensure all unique teams from preliminary round games are in teams_stats
    # Their stats will be updated if they have played games with scores.
    # Otherwise, they will appear with 0s.
    unique_teams_in_prelim_groups = set()
    for g in prelim_games:
        if g.team1_code and g.group: # Ensure team code and group are not None
            unique_teams_in_prelim_groups.add((g.team1_code, g.group))
        if g.team2_code and g.group: # Ensure team code and group are not None
            unique_teams_in_prelim_groups.add((g.team2_code, g.group))

    for team_code, group_name in unique_teams_in_prelim_groups:
        if team_code not in teams_stats: # Add if not already (e.g. from other group if team plays in multiple)
            teams_stats[team_code] = TeamStats(name=team_code, group=group_name)
        # If a team could somehow be listed in two groups in raw schedule data (should not happen for prelims),
        # this would prioritize the first group encountered. Or, ensure TeamStats.group is correctly set/updated.
        # For simplicity, we assume a team belongs to one preliminary group.
        # If a team's group in teams_stats is different from current g.group, this might need refinement
        # but typical preliminary rounds have fixed groups per team.

    # Update stats for games that have been played and have scores
    for g in [pg for pg in prelim_games if pg.team1_score is not None]: # Iterate only over played prelim games
        for code, grp, gf, ga, pts, res, is_t1 in [(g.team1_code, g.group, g.team1_score, g.team2_score, g.team1_points, g.result_type, True),
                                                   (g.team2_code, g.group, g.team2_score, g.team1_score, g.team2_points, g.result_type, False)]:
            # team_stats should already have 'code' due to pre-population.
            stats = teams_stats.setdefault(code, TeamStats(name=code, group=grp))
            
            if stats.group == grp: # Ensure we are updating stats for the team in its primary group
                 stats.gp+=1; stats.gf+=gf; stats.ga+=ga; stats.pts+=pts
                 if res=='REG': stats.w+=1 if gf>ga else 0; stats.l+=1 if ga>gf else 0 # Assuming draw gives 0 W/L
                 elif res=='OT': stats.otw+=1 if gf>ga else 0; stats.otl+=1 if ga>gf else 0
                 elif res=='SO': stats.sow+=1 if gf>ga else 0; stats.sol+=1 if ga>gf else 0
    
    standings_by_group = {}
    if teams_stats:
        group_full_names = sorted(list(set(s.group for s in teams_stats.values() if s.group))) # e.g. ['Group A', 'Group B']
        for full_group_name_key in group_full_names: # full_group_name_key is 'Group A' or 'Group B'
            current_group_teams = sorted(
                [s for s in teams_stats.values() if s.group == full_group_name_key],
                key=lambda x: (x.pts, x.gd, x.gf),
                reverse=True
            )
            for i, team_stat_obj in enumerate(current_group_teams):
                team_stat_obj.rank_in_group = i + 1 # Assign 1-indexed rank
            
            standings_by_group[full_group_name_key] = current_group_teams # Key is "Group A", "Group B"

    playoff_team_map = {}
    # Populate from preliminary round standings (e.g., "A1", "B2")
    for group_display_name, group_standings_list in standings_by_group.items():
        # group_display_name is "Group A", "Group B"
        group_letter_match = re.match(r"Group ([A-D])", group_display_name) # Assuming groups A-D
        if group_letter_match:
            group_letter = group_letter_match.group(1)
            for i, s_team_obj in enumerate(group_standings_list): # s_team_obj is a TeamStats object
                playoff_team_map[f'{group_letter}{i+1}'] = s_team_obj.name # s_team_obj.name should be "CAN", "USA" etc.
    
    games_dict_by_num = {g.game_number: g for g in games_raw}
    
    # --- Semifinal and Final Game Identification (Example for 2025 fixture) ---
    # This might need to be made more dynamic if fixture structures vary widely
    # For 2025.json: QFs 57-60, SFs 61-62, Finals 63-64
    qf_game_numbers = []
    sf_game_numbers = []
    bronze_game_number = None
    gold_game_number = None

    # Attempt to load fixture to identify game numbers and hosts dynamically
    tournament_hosts = []
    if year_obj.fixture_path and os.path.exists(year_obj.fixture_path):
        try:
            with open(year_obj.fixture_path, 'r', encoding='utf-8') as f:
                loaded_fixture_data = json.load(f)
            tournament_hosts = loaded_fixture_data.get("hosts", [])
            for game_data in loaded_fixture_data.get("schedule", []):
                round_name = game_data.get("round", "").lower()
                game_num = game_data.get("gameNumber")
                if "quarterfinal" in round_name: qf_game_numbers.append(game_num)
                elif "semifinal" in round_name: sf_game_numbers.append(game_num)
                elif "bronze" in round_name: bronze_game_number = game_num
                elif "gold" in round_name: gold_game_number = game_num
            sf_game_numbers.sort() # Ensure SF1 is the lower game number
        except Exception: # Fallback if fixture parsing fails
            app.logger.error(f"Could not parse fixture {year_obj.fixture_path} for playoff game numbers.")
            # Hardcoded fallback for 2025 example if dynamic loading fails
            if year_obj.year == 2025:
                qf_game_numbers = [57, 58, 59, 60]
                sf_game_numbers = [61, 62] # SF1=61, SF2=62
                tournament_hosts = ["SWE", "DEN"] # Example hosts

    if sf_game_numbers and len(sf_game_numbers) >= 2:
        playoff_team_map['SF1'] = str(sf_game_numbers[0])
        playoff_team_map['SF2'] = str(sf_game_numbers[1])
    # QF game numbers are used below directly.

    def get_resolved_code(placeholder_code, current_map):
        # Iteratively resolve: W(QF1) -> W(50) -> SUI
        max_depth = 5 # Avoid infinite loops
        current_code = placeholder_code
        for _ in range(max_depth):
            if current_code in current_map:
                next_code = current_map[current_code]
                if next_code == current_code: # Stable
                    return current_code 
                current_code = next_code
            elif (current_code.startswith('W(') or current_code.startswith('L(')) and current_code.endswith(')'):
                match = re.search(r'\(([^()]+)\)', current_code) # Innermost like (50) or (QF1)
                if match:
                    inner_placeholder = match.group(1)
                    # If inner_placeholder is a game number string, proceed with game outcome
                    if inner_placeholder.isdigit():
                        game_num = int(inner_placeholder)
                        game = games_dict_by_num.get(game_num)
                        if game and game.team1_score is not None:
                            # These are original team codes from game object, might be placeholders themselves
                            raw_winner = game.team1_code if game.team1_score > game.team2_score else game.team2_code
                            raw_loser = game.team2_code if game.team1_score > game.team2_score else game.team1_code
                            
                            outcome_based_code = raw_winner if current_code.startswith('W(') else raw_loser
                            # Resolve this outcome_based_code further
                            next_code = current_map.get(outcome_based_code, outcome_based_code)

                            if next_code == current_code: # Stable or no further mapping
                                return next_code 
                            current_code = next_code # Continue resolving this new code
                        else: return current_code # Game not played or inner not numeric, cannot resolve W(game_num)
                    else: # Inner placeholder like QF1, resolve that first
                        resolved_inner = current_map.get(inner_placeholder, inner_placeholder)
                        if resolved_inner == inner_placeholder: return current_code # Inner didn't resolve
                        # Reconstruct W(resolved_inner) or L(resolved_inner) and try again, or map directly if resolved_inner is game number
                        # This part can be complex; for now, assume W(QF1) -> QF1 maps to game number, then W(game_number)
                        # Simplified: if inner_placeholder was resolved to a game_number string:
                        if resolved_inner.isdigit():
                             current_code = f"{'W' if current_code.startswith('W(') else 'L'}({resolved_inner})"
                        else: # inner placeholder resolved to a team, e.g. QFA -> SUI
                             return resolved_inner # this means W(SUI) which is just SUI
                else: return current_code # Malformed W()/L()
            else: # Not in map, not W()/L() pattern, must be final or unresolved basic placeholder
                return current_code
        return current_code # Max depth reached

    games_processed = [GameDisplay(id=g.id, year_id=g.year_id, date=g.date, start_time=g.start_time, round=g.round, group=g.group, game_number=g.game_number, location=g.location, venue=g.venue, team1_code=g.team1_code, team2_code=g.team2_code, original_team1_code=g.team1_code, original_team2_code=g.team2_code, team1_score=g.team1_score, team2_score=g.team2_score, result_type=g.result_type, team1_points=g.team1_points, team2_points=g.team2_points) for g in games_raw]

    for _pass_num in range(max(3, len(games_processed) // 2)): # Iterate for resolution
        changes_in_pass = 0
        for g_disp in games_processed:
            # Resolve team codes using the original placeholder from the fixture
            resolved_t1 = get_resolved_code(g_disp.original_team1_code, playoff_team_map)
            if g_disp.team1_code != resolved_t1: # Update if current resolved code differs from new one
                g_disp.team1_code = resolved_t1
                changes_in_pass += 1
            
            resolved_t2 = get_resolved_code(g_disp.original_team2_code, playoff_team_map)
            if g_disp.team2_code != resolved_t2: # Update if current resolved code differs from new one
                g_disp.team2_code = resolved_t2
                changes_in_pass += 1

            # Update playoff_team_map with W(game_number)/L(game_number) from resolved game outcomes
            if g_disp.round != 'Preliminary Round' and g_disp.team1_score is not None:
                # Ensure g_disp.team1/2_code are NOT placeholders like 'A1' before using them as W/L results
                is_t1_final = not (g_disp.team1_code.startswith(('A','B','W','L','Q','S','SF')) and len(g_disp.team1_code)>1 and (g_disp.team1_code[1:].isdigit() or g_disp.team1_code[1:].isalnum()))
                is_t2_final = not (g_disp.team2_code.startswith(('A','B','W','L','Q','S','SF')) and len(g_disp.team2_code)>1 and (g_disp.team2_code[1:].isdigit() or g_disp.team2_code[1:].isalnum()))

                if is_t1_final and is_t2_final:
                    actual_winner = g_disp.team1_code if g_disp.team1_score > g_disp.team2_score else g_disp.team2_code
                    actual_loser  = g_disp.team2_code if g_disp.team1_score > g_disp.team2_score else g_disp.team1_code
                    
                    win_key = f'W({g_disp.game_number})'; lose_key = f'L({g_disp.game_number})'
                    if playoff_team_map.get(win_key) != actual_winner: playoff_team_map[win_key] = actual_winner; changes_in_pass +=1
                    if playoff_team_map.get(lose_key) != actual_loser: playoff_team_map[lose_key] = actual_loser; changes_in_pass +=1
        
        # --- Semifinal Seeding Logic (after one pass of W/L resolution for QFs) ---
        if _pass_num >= 0 and qf_game_numbers and sf_game_numbers and len(sf_game_numbers) == 2: # Ensure QF games ran, apply SF seeding
            qf_winners_teams = []
            all_qf_winners_resolved = True
            for qf_game_num in qf_game_numbers:
                winner_placeholder = f'W({qf_game_num})'
                # Resolve the winner placeholder itself before using it
                resolved_qf_winner = get_resolved_code(winner_placeholder, playoff_team_map)

                if resolved_qf_winner and not (resolved_qf_winner.startswith(('W(','L(','A','B','Q','S','SF')) and (resolved_qf_winner[1:].isdigit() or resolved_qf_winner[1:].isalnum()) ):
                    qf_winners_teams.append(resolved_qf_winner)
                else:
                    all_qf_winners_resolved = False
                    break
            
            if all_qf_winners_resolved and len(qf_winners_teams) == 4:
                # Get TeamStats for each winner (which includes rank_in_group, pts, gd, gf)
                qf_winners_stats = []
                for team_name in qf_winners_teams:
                    if team_name in teams_stats: # teams_stats keys are original team codes
                        qf_winners_stats.append(teams_stats[team_name])
                    else: # Should not happen if team played prelims
                        all_qf_winners_resolved = False; break 
                
                if all_qf_winners_resolved and len(qf_winners_stats) == 4:
                    # Sort QF winners: 1. rank_in_group (asc), 2. pts (desc), 3. gd (desc), 4. gf (desc)
                    qf_winners_stats.sort(key=lambda ts: (ts.rank_in_group, -ts.pts, -ts.gd, -ts.gf))
                    
                    R1, R2, R3, R4 = [ts.name for ts in qf_winners_stats] # Ranked team names

                    matchup1 = (R1, R4) # Best vs Lowest
                    matchup2 = (R2, R3) # Second Best vs Third Best

                    # Assign matchups to SF games based on host rules (example for 2025)
                    # Game 61 (placeholders Q1,Q2), Game 62 (placeholders Q3,Q4)
                    # Rule: If SWE is SF, plays Game 61. Else if DEN is SF, plays Game 61. Else R1's matchup is Game 61.
                    
                    sf_game1_teams = None
                    sf_game2_teams = None

                    # tournament_hosts might be ["SWE", "DEN"]
                    # Check if primary host (e.g., SWE for 2025 as per note for SF1) is in R1,R2,R3,R4
                    primary_host_plays_sf1 = False
                    if tournament_hosts:
                        # Based on 2025 notes: "If both SWE and DEN qualifies, SWE will play SF1 - Game 61 at 14:20. 
                        # If only SWE or DEN qualifies, SWE or DEN will play SF1." This implies SWE has priority for SF1.
                        if tournament_hosts[0] in [R1,R2,R3,R4]: # Check SWE
                             primary_host_plays_sf1 = True
                             if R1 == tournament_hosts[0] or R4 == tournament_hosts[0]: sf_game1_teams = matchup1; sf_game2_teams = matchup2
                             else: sf_game1_teams = matchup2; sf_game2_teams = matchup1
                        elif len(tournament_hosts) > 1 and tournament_hosts[1] in [R1,R2,R3,R4]: # Check DEN if SWE not in
                             primary_host_plays_sf1 = True # DEN also aims for SF1 if SWE is not playing SF1
                             if R1 == tournament_hosts[1] or R4 == tournament_hosts[1]: sf_game1_teams = matchup1; sf_game2_teams = matchup2
                             else: sf_game1_teams = matchup2; sf_game2_teams = matchup1
                    
                    if not primary_host_plays_sf1: # Neither host qualified or rule not applicable
                        # Default: R1's matchup (best ranked) plays SF1
                        sf_game1_teams = matchup1
                        sf_game2_teams = matchup2

                    # Q-placeholders correspond to specific SF game slots defined in the fixture.
                    # e.g. Game 61: team1="Q1", team2="Q2"
                    #      Game 62: team1="Q3", team2="Q4"
                    
                    # Ensure sf_game_numbers is populated correctly earlier
                    sf_game_obj_1 = games_dict_by_num.get(sf_game_numbers[0])
                    sf_game_obj_2 = games_dict_by_num.get(sf_game_numbers[1])

                    if sf_game_obj_1 and sf_game_obj_2 and sf_game1_teams and sf_game2_teams:
                        # Check if playoff_team_map needs update
                        if playoff_team_map.get(sf_game_obj_1.team1_code) != sf_game1_teams[0]:
                            playoff_team_map[sf_game_obj_1.team1_code] = sf_game1_teams[0]; changes_in_pass +=1
                        if playoff_team_map.get(sf_game_obj_1.team2_code) != sf_game1_teams[1]:
                            playoff_team_map[sf_game_obj_1.team2_code] = sf_game1_teams[1]; changes_in_pass +=1
                        
                        if playoff_team_map.get(sf_game_obj_2.team1_code) != sf_game2_teams[0]:
                            playoff_team_map[sf_game_obj_2.team1_code] = sf_game2_teams[0]; changes_in_pass +=1
                        if playoff_team_map.get(sf_game_obj_2.team2_code) != sf_game2_teams[1]:
                            playoff_team_map[sf_game_obj_2.team2_code] = sf_game2_teams[1]; changes_in_pass +=1
                            
        if changes_in_pass == 0 and _pass_num > 0: break # Stable after min 1 full pass (pass 0 is first calculation)

    all_players_list = Player.query.order_by(Player.team_code, Player.last_name).all()
    player_cache = {p.id: p for p in all_players_list}
    selected_team_filter = request.args.get('stats_team_filter')
    
    player_stats_agg = {p.id: {'g':0,'a':0,'p':0,'obj':p} for p in all_players_list if not selected_team_filter or p.team_code == selected_team_filter}
    for goal in Goal.query.filter(Goal.game_id.in_([g.id for g in games_raw])).all():
        if goal.scorer_id in player_stats_agg: player_stats_agg[goal.scorer_id]['g']+=1; player_stats_agg[goal.scorer_id]['p']+=1
        if goal.assist1_id and goal.assist1_id in player_stats_agg: player_stats_agg[goal.assist1_id]['a']+=1; player_stats_agg[goal.assist1_id]['p']+=1
        if goal.assist2_id and goal.assist2_id in player_stats_agg: player_stats_agg[goal.assist2_id]['a']+=1; player_stats_agg[goal.assist2_id]['p']+=1
    
    # Create a list of dictionaries in the format expected by the template
    all_player_stats_list = [
        {'goals': v['g'], 'assists': v['a'], 'points': v['p'], 'player_obj': v['obj']}
        for v in player_stats_agg.values()
    ]

    # Top Scorers (Points)
    top_scorers_points = sorted(
        [s for s in all_player_stats_list if s['points'] > 0],
        key=lambda x: (-x['points'], -x['goals'], x['player_obj'].last_name.lower())
    )

    # Top Goal Scorers
    top_goal_scorers = sorted(
        [s for s in all_player_stats_list if s['goals'] > 0],
        key=lambda x: (-x['goals'], -x['points'], x['player_obj'].last_name.lower())
    )

    # Top Assist Providers
    top_assist_providers = sorted(
        [s for s in all_player_stats_list if s['assists'] > 0],
        key=lambda x: (-x['assists'], -x['points'], x['player_obj'].last_name.lower())
    )

    # Calculate PIM for players
    PIM_MAP = {
        "2 Min": 2, "2+2 Min": 4, "5 Min + Spieldauer": 5,
        "10 Min Disziplinar": 10, "Spieldauer Disziplinar": 10 
    }
    player_pim_agg = {p.id: {'pim': 0, 'obj': p} for p in all_players_list if (not selected_team_filter or p.team_code == selected_team_filter) and p.id is not None}
    
    all_penalties_for_year = Penalty.query.join(Game).filter(Game.year_id == year_id).all()

    for penalty_entry in all_penalties_for_year:
        if penalty_entry.player_id and penalty_entry.player_id in player_pim_agg:
            pim_value = PIM_MAP.get(penalty_entry.penalty_type, 0)
            player_pim_agg[penalty_entry.player_id]['pim'] += pim_value
    
    top_penalty_players = sorted(
        [{ 'player_obj': v['obj'], 'pim': v['pim'] } for v in player_pim_agg.values() if v['pim'] > 0],
        key=lambda x: (-x['pim'], x['player_obj'].last_name.lower())
    )

    game_nat_teams = set(g.team1_code for g in games_processed if not (g.team1_code.startswith(('A','B','W','L','Q','S')) and g.team1_code[1:].isdigit()))
    game_nat_teams.update(g.team2_code for g in games_processed if not (g.team2_code.startswith(('A','B','W','L','Q','S')) and g.team2_code[1:].isdigit()))
    player_nat_teams = set(p.team_code for p in all_players_list if p.team_code and not (p.team_code.startswith(('A','B','W','L','Q','S')) and p.team_code[1:].isdigit()))
    unique_teams_filter = sorted(list(game_nat_teams.union(player_nat_teams)))
    
    def get_pname(pid): p=player_cache.get(pid); return f"{p.first_name} {p.last_name}" if p else "N/A"

    for g_disp in games_processed:
        for goal in Goal.query.filter_by(game_id=g_disp.id).all():
            g_disp.sorted_events.append({'type':'goal','time_str':goal.minute,'time_for_sort':convert_time_to_seconds(goal.minute), 'data':{'id':goal.id,'team_code':goal.team_code,'minute':goal.minute,'goal_type_display':goal.goal_type,'is_empty_net':goal.is_empty_net,'scorer':get_pname(goal.scorer_id),'assist1':get_pname(goal.assist1_id) if goal.assist1_id else None,'assist2':get_pname(goal.assist2_id) if goal.assist2_id else None,'team_iso':TEAM_ISO_CODES.get(goal.team_code.upper())}})
        for pnlty in Penalty.query.filter_by(game_id=g_disp.id).all():
            g_disp.sorted_events.append({'type':'penalty','time_str':pnlty.minute_of_game,'time_for_sort':convert_time_to_seconds(pnlty.minute_of_game), 'data':{'id':pnlty.id,'team_code':pnlty.team_code,'player_name':get_pname(pnlty.player_id) if pnlty.player_id else "Bank",'minute_of_game':pnlty.minute_of_game,'penalty_type':pnlty.penalty_type,'reason':pnlty.reason,'team_iso':TEAM_ISO_CODES.get(pnlty.team_code.upper())}})
        g_disp.sorted_events.sort(key=lambda x: x['time_for_sort'])
        
        sog_src = sog_by_game_flat.get(g_disp.id, {})
        g_disp.sog_data = {
            g_disp.team1_code: {p: sog_src.get(g_disp.team1_code, {}).get(p,0) for p in range(1,5)},
            g_disp.team2_code: {p: sog_src.get(g_disp.team2_code, {}).get(p,0) for p in range(1,5)}
        }
        # Check if team codes in sog_data are placeholders; if so, they won't match sog_src keys unless SOG saved with placeholders
        # This ensures the sog_data on g_disp uses the *resolved* team codes as keys.

        # --- Start: Score and SOG Matching Logic --- 
        goal_score_match = False # Default to False
        # Calculate goal-score match (handles SO rules)
        if g_disp.team1_score is not None and g_disp.team2_score is not None: # Scores must be set
            actual_goals_team1_db = Goal.query.filter_by(game_id=g_disp.id, team_code=g_disp.team1_code).count()
            actual_goals_team2_db = Goal.query.filter_by(game_id=g_disp.id, team_code=g_disp.team2_code).count()
            expected_db_goals_team1 = g_disp.team1_score
            expected_db_goals_team2 = g_disp.team2_score
            if g_disp.result_type == 'SO':
                if g_disp.team1_score > g_disp.team2_score: expected_db_goals_team1 -= 1
                elif g_disp.team2_score > g_disp.team1_score: expected_db_goals_team2 -= 1
            goal_score_match = (actual_goals_team1_db == expected_db_goals_team1) and \
                               (actual_goals_team2_db == expected_db_goals_team2)
        elif g_disp.team1_score is None and g_disp.team2_score is None: # No scores set
            actual_goals_team1_db = Goal.query.filter_by(game_id=g_disp.id, team_code=g_disp.team1_code).count()
            actual_goals_team2_db = Goal.query.filter_by(game_id=g_disp.id, team_code=g_disp.team2_code).count()
            goal_score_match = (actual_goals_team1_db == 0) and (actual_goals_team2_db == 0)
        # else: one score set, one is None -> goal_score_match remains False

        # SOG Criteria Check
        sog_criteria_met = False # Default to False
        # Only check SOG if scores are actually entered for the game
        if g_disp.team1_score is not None and g_disp.team2_score is not None:
            sog_data_for_current_game = sog_by_game_flat.get(g_disp.id, {})
            team1_sog_periods = sog_data_for_current_game.get(g_disp.team1_code, {})
            team2_sog_periods = sog_data_for_current_game.get(g_disp.team2_code, {})

            sog_p1_ok = team1_sog_periods.get(1, 0) > 0 and team2_sog_periods.get(1, 0) > 0
            sog_p2_ok = team1_sog_periods.get(2, 0) > 0 and team2_sog_periods.get(2, 0) > 0
            sog_p3_ok = team1_sog_periods.get(3, 0) > 0 and team2_sog_periods.get(3, 0) > 0
            
            sog_ot_ok = True # Assume OT SOG is fine if not an OT/SO game
            if g_disp.result_type in ['OT', 'SO']:
                sog_ot_ok = team1_sog_periods.get(4, 0) > 0 and team2_sog_periods.get(4, 0) > 0
            
            sog_criteria_met = sog_p1_ok and sog_p2_ok and sog_p3_ok and sog_ot_ok
        elif g_disp.team1_score is None and g_disp.team2_score is None:
             # If no scores are entered (future game), SOG criteria are considered met by default (or irrelevant)
             # The indicator logic in template already hides for games with no scores.
             # To prevent an 'X' for future games just due to missing SOG, set to True here.
             sog_criteria_met = True 
        # else: one score set, one is None -> sog_criteria_met remains False (as SOG wouldn't be complete)

        g_disp.scores_fully_match_goals = goal_score_match and sog_criteria_met
        # --- End: Score and SOG Matching Logic ---

    games_by_round_display = {}
    for g_d in games_processed: games_by_round_display.setdefault(g_d.round or "Unk", []).append(g_d)

    # For player dropdowns in forms
    all_players_by_team_json = {
        team: [{'id': p.id, 
                'first_name': p.first_name, 
                'last_name': p.last_name,
                'full_name': f"{p.last_name.upper()}, {p.first_name}"} 
               for p in all_players_list if p.team_code == team] 
        for team in unique_teams_filter
    }

    # Refined unique_teams_in_year to only include actual countries with ISO codes
    potential_teams = set()
    for g_disp in games_processed:
        if g_disp.team1_code and TEAM_ISO_CODES.get(g_disp.team1_code.upper()) is not None:
            potential_teams.add(g_disp.team1_code.upper())
        if g_disp.team2_code and TEAM_ISO_CODES.get(g_disp.team2_code.upper()) is not None:
            potential_teams.add(g_disp.team2_code.upper())
    for p_obj in all_players_list:
        if p_obj.team_code and TEAM_ISO_CODES.get(p_obj.team_code.upper()) is not None:
            potential_teams.add(p_obj.team_code.upper())
    unique_teams_in_year = sorted(list(potential_teams))

    # Player stats aggregation (existing code)
    all_player_stats_list = [] # Ensure it's initialized before potential return in new AJAX endpoint
    top_scorers_points = []
    top_goal_scorers = []
    top_assist_providers = []
    top_penalty_players = []

    # This block calculates all stats, will be reused by AJAX endpoint or initial load
    player_stats_agg = {p.id: {'g':0,'a':0,'p':0,'obj':p} for p in all_players_list if not selected_team_filter or p.team_code == selected_team_filter}
    for goal in Goal.query.filter(Goal.game_id.in_([g.id for g in games_raw])).all():
        if goal.scorer_id in player_stats_agg: player_stats_agg[goal.scorer_id]['g']+=1; player_stats_agg[goal.scorer_id]['p']+=1
        if goal.assist1_id and goal.assist1_id in player_stats_agg: player_stats_agg[goal.assist1_id]['a']+=1; player_stats_agg[goal.assist1_id]['p']+=1
        if goal.assist2_id and goal.assist2_id in player_stats_agg: player_stats_agg[goal.assist2_id]['a']+=1; player_stats_agg[goal.assist2_id]['p']+=1
    
    # Create a list of dictionaries in the format expected by the template
    all_player_stats_list = [
        {'goals': v['g'], 'assists': v['a'], 'points': v['p'], 'player_obj': v['obj']}
        for v in player_stats_agg.values()
    ]

    # Top Scorers (Points)
    top_scorers_points = sorted(
        [s for s in all_player_stats_list if s['points'] > 0],
        key=lambda x: (-x['points'], -x['goals'], x['player_obj'].last_name.lower())
    )

    # Top Goal Scorers
    top_goal_scorers = sorted(
        [s for s in all_player_stats_list if s['goals'] > 0],
        key=lambda x: (-x['goals'], -x['points'], x['player_obj'].last_name.lower())
    )

    # Top Assist Providers
    top_assist_providers = sorted(
        [s for s in all_player_stats_list if s['assists'] > 0],
        key=lambda x: (-x['assists'], -x['points'], x['player_obj'].last_name.lower())
    )

    # Calculate PIM for players
    PIM_MAP = {
        "2 Min": 2, "2+2 Min": 4, "5 Min + Spieldauer": 5,
        "10 Min Disziplinar": 10, "Spieldauer Disziplinar": 10 
    }
    player_pim_agg = {p.id: {'pim': 0, 'obj': p} for p in all_players_list if (not selected_team_filter or p.team_code == selected_team_filter) and p.id is not None}
    
    all_penalties_for_year = Penalty.query.join(Game).filter(Game.year_id == year_id).all()

    for penalty_entry in all_penalties_for_year:
        if penalty_entry.player_id and penalty_entry.player_id in player_pim_agg:
            pim_value = PIM_MAP.get(penalty_entry.penalty_type, 0)
            player_pim_agg[penalty_entry.player_id]['pim'] += pim_value
    
    top_penalty_players = sorted(
        [{ 'player_obj': v['obj'], 'pim': v['pim'] } for v in player_pim_agg.values() if v['pim'] > 0],
        key=lambda x: (-x['pim'], x['player_obj'].last_name.lower())
    )

    # --- START: Calculate TeamOverallStats ---
    team_stats_data_list = []
    if unique_teams_in_year: # Ensure there are teams to process
        # Fetch all relevant data for the year once to minimize DB calls
        all_games_for_year = Game.query.filter_by(year_id=year_id).all()
        all_goals_for_year = Goal.query.join(Game).filter(Game.year_id == year_id).all()
        all_penalties_for_year_detailed = Penalty.query.join(Game).filter(Game.year_id == year_id).all()
        all_sog_for_year = ShotsOnGoal.query.join(Game).filter(Game.year_id == year_id).all()

        # Pre-process SOG data for quick lookup: {game_id: {team_code: total_sog}}
        sog_by_game_team = {}
        for sog_entry in all_sog_for_year:
            game_sog = sog_by_game_team.setdefault(sog_entry.game_id, {})
            team_total_sog = game_sog.get(sog_entry.team_code, 0)
            game_sog[sog_entry.team_code] = team_total_sog + sog_entry.shots
        
        # Define PIM values for team PIM calculation
        TEAM_PIM_MAP = {
            "2 Min": 2,
            "2+2 Min": 4,
            "5 Min + Spieldauer": 5, # The major penalty itself
            "10 Min Disziplinar": 0, # Usually doesn't count towards team PIM for shorthanded purposes
            "Spieldauer Disziplinar": 0 # Same as 10 Min Disziplinar
        }
        # Penalties that grant a powerplay to the other team
        POWERPLAY_PENALTY_TYPES = ["2 Min", "2+2 Min", "5 Min + Spieldauer"]


        for team_code_upper in unique_teams_in_year:
            # Find the actual team code (case-sensitive) as used in DB, from one of the games
            # This assumes unique_teams_in_year contains upper-case codes.
            # A more robust way would be to use the resolved team codes from games_processed if they are final.
            # For now, let's find a game where this team_code_upper (or its original form) participated.
            
            # Attempt to find a canonical team_code as used in game records
            # This is important because unique_teams_in_year might have different casing than DB.
            # We will iterate through games_processed to find the matching team code.
            actual_team_code_from_games = None
            for g_disp_for_code in games_processed:
                if g_disp_for_code.team1_code.upper() == team_code_upper:
                    actual_team_code_from_games = g_disp_for_code.team1_code
                    break
                if g_disp_for_code.team2_code.upper() == team_code_upper:
                    actual_team_code_from_games = g_disp_for_code.team2_code
                    break
            
            if not actual_team_code_from_games:
                 # If not found in resolved game codes (e.g., team only in player list but no games yet),
                 # try to find in raw game data team codes or player list team codes.
                 # Fallback to the upper version if no exact match found (less ideal).
                 found_in_players = any(p.team_code == team_code_upper for p in all_players_list)
                 if found_in_players:
                     actual_team_code_from_games = team_code_upper # Assume direct match if in player list
                 else: # Try to find in raw game objects (less precise due to placeholders)
                     for g_raw_for_code in games_raw:
                         if g_raw_for_code.team1_code == team_code_upper:
                             actual_team_code_from_games = g_raw_for_code.team1_code; break
                         if g_raw_for_code.team2_code == team_code_upper:
                             actual_team_code_from_games = g_raw_for_code.team2_code; break
                 if not actual_team_code_from_games:
                     actual_team_code_from_games = team_code_upper # Last resort

            current_team_code = actual_team_code_from_games

            stats = TeamOverallStats(
                team_name=current_team_code,
                team_iso_code=TEAM_ISO_CODES.get(current_team_code.upper())
            )

            for game_obj in all_games_for_year:
                opponent_code = None
                is_team1 = False
                if game_obj.team1_code == current_team_code:
                    opponent_code = game_obj.team2_code
                    is_team1 = True
                elif game_obj.team2_code == current_team_code:
                    opponent_code = game_obj.team1_code
                    is_team1 = False
                
                if opponent_code is None: # Team didn't play in this game
                    continue

                # Ensure opponent_code is also a "final" team code for accurate SOGA etc.
                # For SOGA, we need the SOG of the *actual* opponent.
                # The games_processed list has resolved team codes. Find the matching game:
                resolved_game_disp = next((g_disp for g_disp in games_processed if g_disp.id == game_obj.id), None)
                actual_opponent_resolved_code = None
                if resolved_game_disp:
                    actual_opponent_resolved_code = resolved_game_disp.team2_code if is_team1 else resolved_game_disp.team1_code
                    # Ensure this resolved opponent is not a placeholder
                    if actual_opponent_resolved_code and \
                       (actual_opponent_resolved_code.startswith(('A','B','W','L','Q','S')) and \
                        len(actual_opponent_resolved_code)>1 and \
                        actual_opponent_resolved_code[1:].isdigit()):
                        actual_opponent_resolved_code = None # Can't use placeholder for SOGA lookup yet


                if game_obj.team1_score is not None and game_obj.team2_score is not None: # Game has been played
                    stats.gp += 1
                    
                    current_team_score = game_obj.team1_score if is_team1 else game_obj.team2_score
                    opponent_score = game_obj.team2_score if is_team1 else game_obj.team1_score
                    
                    stats.gf += current_team_score
                    stats.ga += opponent_score

                    if opponent_score == 0 and current_team_score > 0 : # Assuming win implies >0 score for SO
                        stats.so += 1
                
                # SOG and SOGA
                game_sog_info = sog_by_game_team.get(game_obj.id, {})
                stats.sog += game_sog_info.get(current_team_code, 0)
                if actual_opponent_resolved_code: # Only add SOGA if opponent is resolved to a national team
                    stats.soga += game_sog_info.get(actual_opponent_resolved_code, 0)
                
            # Goals details (ENG, PPGF)
            for goal in all_goals_for_year:
                if goal.game_id not in [g.id for g in all_games_for_year if g.team1_code == current_team_code or g.team2_code == current_team_code]:
                    continue # Goal not in a game this team played

                if goal.team_code == current_team_code:
                    if goal.is_empty_net:
                        stats.eng += 1
                    if goal.goal_type == 'PP':
                        stats.ppgf += 1
                else: # Goal scored by opponent against current_team_code
                    # Check if this opponent's goal was a PP goal
                    # This requires knowing if current_team_code was shorthanded when opponent scored.
                    # For simplicity, PPGA = goals scored by opponent IF opponent's goal_type was 'PP'
                    # This means the current_team_code was shorthanded and conceded.
                    if goal.goal_type == 'PP': # Opponent scored a PP goal
                        stats.ppga +=1


            # Penalties (PIM, PPF, PPA)
            for penalty in all_penalties_for_year_detailed:
                if penalty.game_id not in [g.id for g in all_games_for_year if g.team1_code == current_team_code or g.team2_code == current_team_code]:
                    continue

                if penalty.team_code == current_team_code: # Penalty taken by current team
                    stats.pim += TEAM_PIM_MAP.get(penalty.penalty_type, 0)
                    if penalty.penalty_type in POWERPLAY_PENALTY_TYPES:
                        stats.ppa += 1 # Team was shorthanded
                else: # Penalty taken by opponent
                    if penalty.penalty_type in POWERPLAY_PENALTY_TYPES:
                        stats.ppf += 1 # Team had a powerplay opportunity
            
            team_stats_data_list.append(stats)
    # --- END: Calculate TeamOverallStats ---


    return render_template('year_view.html', 
                           year=year_obj,
                           games_by_round=games_by_round_display,
                           standings=standings_by_group, # Use the new dynamic standings
                           all_players=all_players_list, 
                           selected_team=selected_team_filter,
                           unique_teams_in_year=unique_teams_in_year, 
                           Goal=Goal, Penalty=Penalty, ShotsOnGoal=ShotsOnGoal,
                           team_iso_codes=TEAM_ISO_CODES, 
                           top_scorers_points=top_scorers_points,
                           top_goal_scorers=top_goal_scorers,
                           top_assist_providers=top_assist_providers,
                           top_penalty_players=top_penalty_players,
                           playoff_team_map=playoff_team_map, 
                           all_players_by_team_json=all_players_by_team_json,
                           team_codes=TEAM_ISO_CODES,
                           penalty_types=PENALTY_TYPES_CHOICES,
                           penalty_reasons=PENALTY_REASONS_CHOICES,
                           team_stats_data=team_stats_data_list # Add new team stats data
                           )


@app.route('/year/<int:year_id>/stats_data')
def get_stats_data(year_id):
    selected_team_filter = request.args.get('stats_team_filter')
    year_obj = db.session.get(ChampionshipYear, year_id)
    if not year_obj:
        return jsonify({'error': 'Tournament year not found'}), 404

    games_raw = Game.query.filter_by(year_id=year_id).all() # Needed for goal query
    all_players_list = Player.query.order_by(Player.team_code, Player.last_name).all()

    # Player stats aggregation (replicated from year_view for now, can be refactored)
    player_stats_agg = {p.id: {'g':0,'a':0,'p':0,'obj':p} for p in all_players_list 
                        if not selected_team_filter or p.team_code == selected_team_filter}
    
    # Efficiently fetch all goals for the year once
    all_goals_for_year = Goal.query.join(Game).filter(Game.year_id == year_id).all()

    for goal in all_goals_for_year:
        if goal.scorer_id in player_stats_agg:
            player_stats_agg[goal.scorer_id]['g'] += 1
            player_stats_agg[goal.scorer_id]['p'] += 1
        if goal.assist1_id and goal.assist1_id in player_stats_agg:
            player_stats_agg[goal.assist1_id]['a'] += 1
            player_stats_agg[goal.assist1_id]['p'] += 1
        if goal.assist2_id and goal.assist2_id in player_stats_agg:
            player_stats_agg[goal.assist2_id]['a'] += 1
            player_stats_agg[goal.assist2_id]['p'] += 1

    all_player_stats_list_for_json = [
        {'goals': v['g'], 'assists': v['a'], 'points': v['p'], 
         'player_obj': {'id': v['obj'].id, 'first_name': v['obj'].first_name, 'last_name': v['obj'].last_name, 'team_code': v['obj'].team_code}}
        for v in player_stats_agg.values()
    ]

    top_scorers_points = sorted(
        [s for s in all_player_stats_list_for_json if s['points'] > 0],
        key=lambda x: (-x['points'], -x['goals'], x['player_obj']['last_name'].lower())
    )

    top_goal_scorers = sorted(
        [s for s in all_player_stats_list_for_json if s['goals'] > 0],
        key=lambda x: (-x['goals'], -x['points'], x['player_obj']['last_name'].lower())
    )

    top_assist_providers = sorted(
        [s for s in all_player_stats_list_for_json if s['assists'] > 0],
        key=lambda x: (-x['assists'], -x['points'], x['player_obj']['last_name'].lower())
    )

    PIM_MAP = {
        "2 Min": 2, "2+2 Min": 4, "5 Min + Spieldauer": 5,
        "10 Min Disziplinar": 10, "Spieldauer Disziplinar": 10 
    }
    player_pim_agg = {p.id: {'pim': 0, 'obj': {'id': p.id, 'first_name': p.first_name, 'last_name': p.last_name, 'team_code': p.team_code}} 
                      for p in all_players_list if (not selected_team_filter or p.team_code == selected_team_filter) and p.id is not None}
    
    all_penalties_for_year = Penalty.query.join(Game).filter(Game.year_id == year_id).all()

    for penalty_entry in all_penalties_for_year:
        if penalty_entry.player_id and penalty_entry.player_id in player_pim_agg:
            pim_value = PIM_MAP.get(penalty_entry.penalty_type, 0)
            player_pim_agg[penalty_entry.player_id]['pim'] += pim_value
    
    top_penalty_players = sorted(
        [{ 'player_obj': v['obj'], 'pim': v['pim'] } for v in player_pim_agg.values() if v['pim'] > 0],
        key=lambda x: (-x['pim'], x['player_obj']['last_name'].lower())
    )

    return jsonify({
        'top_scorers_points': top_scorers_points,
        'top_goal_scorers': top_goal_scorers,
        'top_assist_providers': top_assist_providers,
        'top_penalty_players': top_penalty_players,
        'selected_team': selected_team_filter or ""
    })

@app.route('/add_player', methods=['POST'])
def add_player():
    team_code = request.form.get('team_code')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    jersey_number_str = request.form.get('jersey_number')
    year_id_redirect = request.form.get('year_id_redirect') # For redirecting back
    game_id_anchor = request.form.get('game_id_anchor') # For AJAX response

    if not team_code or not first_name or not last_name:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Team, First Name, and Last Name are required.'}), 400
        flash('Team, First Name, and Last Name are required to add a player.', 'danger')
    else:
        try:
            jersey_number = int(jersey_number_str) if jersey_number_str and jersey_number_str.isdigit() else None
        except ValueError:
            jersey_number = None
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                 return jsonify({'success': False, 'message': 'Invalid Jersey Number format.'}), 400
            flash('Invalid Jersey Number format.', 'danger')
            anchor_to_use = f"game-details-{game_id_anchor}" if game_id_anchor and game_id_anchor != 'None' else "addPlayerForm-global"
            if year_id_redirect and year_id_redirect != 'None':
                return redirect(url_for('year_view', year_id=int(year_id_redirect), _anchor=anchor_to_use))
            return redirect(url_for('index'))

        existing_player_query = Player.query.filter_by(team_code=team_code, first_name=first_name, last_name=last_name)
        if jersey_number is not None:
            pass

        existing_player = existing_player_query.first()
        if existing_player:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': f'Player {first_name} {last_name} ({team_code}) already exists.'}), 400 # Return 400 for duplicate
            flash(f'Player {first_name} {last_name} ({team_code}) already exists.', 'warning')
        else:
            try:
                new_player = Player(team_code=team_code, first_name=first_name, last_name=last_name, jersey_number=jersey_number)
                db.session.add(new_player)
                db.session.commit()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True, 
                        'message': f'Player {first_name} {last_name} (#{jersey_number if jersey_number else "N/A"}) ({team_code}) added successfully!',
                        'player': {'id': new_player.id, 'first_name': new_player.first_name, 'last_name': new_player.last_name, 'team_code': new_player.team_code, 'jersey_number': new_player.jersey_number, 'full_name': f"{new_player.last_name.upper()}, {new_player.first_name}"}
                    })
                flash(f'Player {first_name} {last_name} (#{jersey_number if jersey_number else "N/A"}) ({team_code}) added successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Error adding player: {str(e)}") # Log the error
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': f'Error adding player: {str(e)}'}), 500
                flash(f'Error adding player: {str(e)}', 'danger')
    
    # Redirect logic for non-AJAX or if AJAX needs a fallback
    anchor_to_use = f"game-details-{game_id_anchor}" if game_id_anchor and game_id_anchor != 'None' else "addPlayerForm-global"
    if year_id_redirect and year_id_redirect != 'None': # Check if year_id_redirect is not None or 'None'
        return redirect(url_for('year_view', year_id=int(year_id_redirect), _anchor=anchor_to_use))
    return redirect(url_for('index')) # Fallback redirect


@app.route('/year/<int:year_id>/game/<int:game_id>/add_goal', methods=['POST'])
def add_goal(year_id, game_id):
    game = db.session.get(Game, game_id)
    if not game or game.year_id != year_id :
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404

    try:
        team_code = request.form.get('team_code_goal')
        minute = request.form.get('minute')
        goal_type = request.form.get('goal_type')
        scorer_id = request.form.get('scorer_id')
        assist1_id = request.form.get('assist1_id')
        assist2_id = request.form.get('assist2_id')
        is_empty_net = request.form.get('is_empty_net') == 'on'

        if not all([team_code, minute, goal_type, scorer_id]):
            return jsonify({'success': False, 'message': 'Fehlende Daten für Toreingabe.'}), 400
        
        new_goal = Goal(
            game_id=game_id, team_code=team_code, minute=minute, goal_type=goal_type,
            scorer_id=int(scorer_id),
            assist1_id=int(assist1_id) if assist1_id and assist1_id.isdigit() else None,
            assist2_id=int(assist2_id) if assist2_id and assist2_id.isdigit() else None,
            is_empty_net=is_empty_net
        )
        db.session.add(new_goal)
        db.session.commit()

        player_cache = {p.id: p for p in Player.query.all()} 
        def get_pname_local(pid): p=player_cache.get(pid); return f"{p.first_name} {p.last_name}" if p else "N/A"
        
        # --- Start: Score and SOG Matching Logic for add_goal ---
        scores_match = False # Default
        # 1. Goal-Score Matching
        if game.team1_score is not None and game.team2_score is not None:
            game_goals_team1_db = Goal.query.filter_by(game_id=game_id, team_code=game.team1_code).count()
            game_goals_team2_db = Goal.query.filter_by(game_id=game_id, team_code=game.team2_code).count()
            expected_db_goals_t1 = game.team1_score
            expected_db_goals_t2 = game.team2_score
            if game.result_type == 'SO':
                if game.team1_score > game.team2_score: expected_db_goals_t1 -= 1
                elif game.team2_score > game.team1_score: expected_db_goals_t2 -= 1
            goal_score_match_local = (expected_db_goals_t1 == game_goals_team1_db) and \
                                     (expected_db_goals_t2 == game_goals_team2_db)
        elif game.team1_score is None and game.team2_score is None:
            game_goals_team1_db = Goal.query.filter_by(game_id=game_id, team_code=game.team1_code).count()
            game_goals_team2_db = Goal.query.filter_by(game_id=game_id, team_code=game.team2_code).count()
            goal_score_match_local = (game_goals_team1_db == 0) and (game_goals_team2_db == 0)
        else:
            goal_score_match_local = False

        # 2. SOG Criteria Check
        sog_criteria_met_local = False # Default
        if game.team1_score is not None and game.team2_score is not None:
            sog_entries_for_game = ShotsOnGoal.query.filter_by(game_id=game_id).all()
            sog_data_current_game = {game.team1_code: {}, game.team2_code: {}}
            for sog_entry in sog_entries_for_game:
                if sog_entry.team_code in sog_data_current_game:
                    sog_data_current_game[sog_entry.team_code][sog_entry.period] = sog_entry.shots
            
            team1_sog = sog_data_current_game.get(game.team1_code, {})
            team2_sog = sog_data_current_game.get(game.team2_code, {})
            sog_p1_ok = team1_sog.get(1,0) > 0 and team2_sog.get(1,0) > 0
            sog_p2_ok = team1_sog.get(2,0) > 0 and team2_sog.get(2,0) > 0
            sog_p3_ok = team1_sog.get(3,0) > 0 and team2_sog.get(3,0) > 0
            sog_ot_ok = True
            if game.result_type in ['OT', 'SO']:
                sog_ot_ok = team1_sog.get(4,0) > 0 and team2_sog.get(4,0) > 0
            sog_criteria_met_local = sog_p1_ok and sog_p2_ok and sog_p3_ok and sog_ot_ok
        elif game.team1_score is None and game.team2_score is None: 
            sog_criteria_met_local = True # Bypass SOG for future games
        
        scores_match = goal_score_match_local and sog_criteria_met_local
        # --- End: Score and SOG Matching Logic for add_goal ---

        goal_data_for_js = {
            'id': new_goal.id, 'team_code': new_goal.team_code, 'minute': new_goal.minute,
            'goal_type_display': new_goal.goal_type, 'is_empty_net': new_goal.is_empty_net,
            'scorer': get_pname_local(new_goal.scorer_id),
            'assist1': get_pname_local(new_goal.assist1_id) if new_goal.assist1_id else None,
            'assist2': get_pname_local(new_goal.assist2_id) if new_goal.assist2_id else None,
            'team_iso': TEAM_ISO_CODES.get(new_goal.team_code.upper()),
            'time_for_sort': convert_time_to_seconds(new_goal.minute),
            'scores_fully_match_goals': scores_match
        }
        return jsonify({'success': True, 'message': 'Tor erfolgreich hinzugefügt!', 'goal': goal_data_for_js, 'game_id': game_id})

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error adding goal for game {game_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Fehler beim Hinzufügen des Tores: {str(e)}'}), 500
    

@app.route('/year/<int:year_id>/goal/<int:goal_id>/delete', methods=['POST'])
def delete_goal(year_id, goal_id):
    goal = db.session.get(Goal, goal_id)
    if not goal:
        # AJAX response for not found
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Goal not found.'}), 404
        flash('Goal not found.', 'warning')
        return redirect(url_for('year_view', year_id=year_id)) # Fallback for non-AJAX

    game = db.session.get(Game, goal.game_id) # Get game before deleting goal link
    if not game or game.year_id != year_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid goal or game association for this tournament year.'}), 400
        flash('Invalid goal for this tournament year.', 'danger')
        return redirect(url_for('year_view', year_id=year_id))
    
    game_id_for_response = game.id
    db.session.delete(goal)
    db.session.commit()

    # --- Start: Score and SOG Matching Logic for delete_goal ---
    scores_match = False # Default
    # 1. Goal-Score Matching
    if game.team1_score is not None and game.team2_score is not None:
        game_goals_team1_db = Goal.query.filter_by(game_id=game_id_for_response, team_code=game.team1_code).count()
        game_goals_team2_db = Goal.query.filter_by(game_id=game_id_for_response, team_code=game.team2_code).count()
        expected_db_goals_t1 = game.team1_score
        expected_db_goals_t2 = game.team2_score
        if game.result_type == 'SO':
            if game.team1_score > game.team2_score: expected_db_goals_t1 -= 1
            elif game.team2_score > game.team1_score: expected_db_goals_t2 -= 1
        goal_score_match_local = (expected_db_goals_t1 == game_goals_team1_db) and \
                                 (expected_db_goals_t2 == game_goals_team2_db)
    elif game.team1_score is None and game.team2_score is None:
        game_goals_team1_db = Goal.query.filter_by(game_id=game_id_for_response, team_code=game.team1_code).count()
        game_goals_team2_db = Goal.query.filter_by(game_id=game_id_for_response, team_code=game.team2_code).count()
        goal_score_match_local = (game_goals_team1_db == 0) and (game_goals_team2_db == 0)
    else:
        goal_score_match_local = False

    # 2. SOG Criteria Check
    sog_criteria_met_local = False # Default
    if game.team1_score is not None and game.team2_score is not None:
        sog_entries_for_game = ShotsOnGoal.query.filter_by(game_id=game_id_for_response).all()
        sog_data_current_game = {game.team1_code: {}, game.team2_code: {}}
        for sog_entry in sog_entries_for_game:
            if sog_entry.team_code in sog_data_current_game:
                sog_data_current_game[sog_entry.team_code][sog_entry.period] = sog_entry.shots
        
        team1_sog = sog_data_current_game.get(game.team1_code, {})
        team2_sog = sog_data_current_game.get(game.team2_code, {})
        sog_p1_ok = team1_sog.get(1,0) > 0 and team2_sog.get(1,0) > 0
        sog_p2_ok = team1_sog.get(2,0) > 0 and team2_sog.get(2,0) > 0
        sog_p3_ok = team1_sog.get(3,0) > 0 and team2_sog.get(3,0) > 0
        sog_ot_ok = True
        if game.result_type in ['OT', 'SO']:
            sog_ot_ok = team1_sog.get(4,0) > 0 and team2_sog.get(4,0) > 0
        sog_criteria_met_local = sog_p1_ok and sog_p2_ok and sog_p3_ok and sog_ot_ok
    elif game.team1_score is None and game.team2_score is None: 
        sog_criteria_met_local = True # Bypass SOG for future games
    
    scores_match = goal_score_match_local and sog_criteria_met_local
    # --- End: Score and SOG Matching Logic for delete_goal ---

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True, 
            'message': 'Goal deleted successfully.', 
            'goal_id': goal_id, 
            'game_id': game_id_for_response,
            'scores_fully_match_goals': scores_match
        })
    
    flash('Goal deleted.', 'success') # Fallback for non-AJAX
    return redirect(url_for('year_view', year_id=year_id, _anchor=f"game-details-{game_id_for_response}"))

@app.route('/year/<int:year_id>/game/<int:game_id>/add_penalty', methods=['POST'])
def add_penalty(year_id, game_id):
    game = db.session.get(Game, game_id)
    if not game or game.year_id != year_id:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden oder gehört nicht zum Turnier.'}), 404

    try:
        team_code = request.form.get('team_code_penalty')
        player_id_str = request.form.get('player_id_penalty') 
        minute_of_game = request.form.get('minute_of_game')
        penalty_type = request.form.get('penalty_type')
        reason = request.form.get('reason')

        if not all([team_code, minute_of_game, penalty_type, reason]):
            return jsonify({'success': False, 'message': 'Fehlende Daten für Strafeneingabe.'}), 400

        new_penalty = Penalty(
            game_id=game_id, team_code=team_code,
            player_id=int(player_id_str) if player_id_str and player_id_str != '-1' and player_id_str.isdigit() else None, # Handle Team Penalty (-1) and empty string
            minute_of_game=minute_of_game,
            penalty_type=penalty_type, reason=reason
        )
        db.session.add(new_penalty)
        db.session.commit()
        
        player_cache = {p.id: p for p in Player.query.all()}
        def get_pname_local(pid): 
            if pid is None: return "Teamstrafe" # Explicitly handle None as Team Penalty if player_id becomes None
            p=player_cache.get(pid)
            return f"{p.first_name} {p.last_name}" if p else "Bankstrafe"


        penalty_data_for_js = {
            'id': new_penalty.id, 'team_code': new_penalty.team_code,
            'player_name': get_pname_local(new_penalty.player_id),
            'minute_of_game': new_penalty.minute_of_game,
            'penalty_type': new_penalty.penalty_type, 'reason': new_penalty.reason,
            'team_iso': TEAM_ISO_CODES.get(new_penalty.team_code.upper()),
            'time_for_sort': convert_time_to_seconds(new_penalty.minute_of_game)
        }
        return jsonify({'success': True, 'message': 'Strafe erfolgreich hinzugefügt!', 'penalty': penalty_data_for_js, 'game_id': game_id})

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error adding penalty for game {game_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Fehler beim Hinzufügen der Strafe: {str(e)}'}), 500

@app.route('/year/<int:year_id>/penalty/<int:penalty_id>/delete', methods=['POST'])
def delete_penalty(year_id, penalty_id):
    penalty = db.session.get(Penalty, penalty_id)
    if not penalty:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Penalty not found.'}), 404
        flash('Penalty not found.', 'warning')
        return redirect(url_for('year_view', year_id=year_id))

    game = db.session.get(Game, penalty.game_id) # Get game before deleting penalty link
    if not game or game.year_id != year_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid penalty or game association for this tournament year.'}), 400
        flash('Invalid penalty for this tournament year.', 'danger')
        return redirect(url_for('year_view', year_id=year_id))

    game_id_for_response = game.id
    db.session.delete(penalty)
    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True, 
            'message': 'Penalty deleted successfully.', 
            'penalty_id': penalty_id, 
            'game_id': game_id_for_response
        })
    
    flash('Penalty deleted.', 'success') # Fallback for non-AJAX
    return redirect(url_for('year_view', year_id=year_id, _anchor=f"game-details-{game_id_for_response}"))


@app.route('/add_sog/<int:game_id>', methods=['POST'])
def add_sog(game_id):
    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Spiel nicht gefunden.'}), 404

    data = request.form
    try:
        resolved_t1_code = data.get('sog_team1_code_resolved') 
        resolved_t2_code = data.get('sog_team2_code_resolved')
        teams_processed_count = 0
        made_changes = False # Flag to track if any actual DB changes were made

        def process_sog_for_team(team_code, form_prefix):
            nonlocal teams_processed_count, made_changes
            if team_code and not (team_code.startswith(('A','B','W','L','Q','S')) and len(team_code) > 1 and team_code[1:].isdigit()):
                teams_processed_count += 1
                for period in range(1, 5):
                    shots_str = data.get(f'{form_prefix}_p{period}_shots')
                    if shots_str is None: continue
                    try: shots = int(shots_str.strip()) if shots_str.strip() else 0
                    except ValueError: shots = 0
                    
                    sog_entry = ShotsOnGoal.query.filter_by(game_id=game_id, team_code=team_code, period=period).first()
                    if sog_entry:
                        if sog_entry.shots != shots:
                            sog_entry.shots = shots
                            db.session.add(sog_entry) # Explicitly add modified entry to session
                            made_changes = True
                    elif shots != 0:
                        db.session.add(ShotsOnGoal(game_id=game_id, team_code=team_code, period=period, shots=shots))
                        made_changes = True
        
        process_sog_for_team(resolved_t1_code, 'team1')
        process_sog_for_team(resolved_t2_code, 'team2')

        if made_changes: # Only commit if actual changes were staged
            db.session.commit()
            message = 'Shots on Goal successfully saved.'
        elif teams_processed_count > 0 and not made_changes:
            message = 'SOG values submitted were the same as current or all zeros for new entries; no changes made.'
        else: # teams_processed_count == 0
            message = 'No valid teams for SOG update (possibly placeholders).'
        
        current_sog_response = {}
        for entry in ShotsOnGoal.query.filter_by(game_id=game_id).all():
            current_sog_response.setdefault(entry.team_code, {})[entry.period] = entry.shots
        
        for tc_resp in [resolved_t1_code, resolved_t2_code]:
            if tc_resp and not (tc_resp.startswith(('A','B','W','L','Q','S')) and len(tc_resp)>1 and tc_resp[1:].isdigit()):
                 current_sog_response.setdefault(tc_resp, {}) 
                 for p_resp in range(1,5): current_sog_response[tc_resp].setdefault(p_resp, 0)
        
        return jsonify({'success': True, 'message': message, 'game_id': game_id, 'sog_data': current_sog_response})

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in add_sog for game {game_id}: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

# --- New Game Statistics Route ---
@app.route('/year/<int:year_id>/game/<int:game_id>/stats')
def game_stats_view(year_id, game_id):
    year_obj = db.session.get(ChampionshipYear, year_id)
    game_obj = db.session.get(Game, game_id)

    if not year_obj or not game_obj or game_obj.year_id != year_obj.id:
        flash('Tournament year or game not found, or game does not belong to this year.', 'danger')
        return redirect(url_for('index'))

    # 1. Fetch SOG data
    sog_entries = ShotsOnGoal.query.filter_by(game_id=game_id).all()
    sog_data_processed = {game_obj.team1_code: {1:0, 2:0, 3:0, 4:0}, game_obj.team2_code: {1:0, 2:0, 3:0, 4:0}}
    sog_totals = {game_obj.team1_code: 0, game_obj.team2_code: 0}
    for sog in sog_entries:
        if sog.team_code in sog_data_processed:
            sog_data_processed[sog.team_code][sog.period] = sog.shots
            sog_totals[sog.team_code] += sog.shots
    for team_code_key in [game_obj.team1_code, game_obj.team2_code]:
        for p_key in range(1, 5):
            sog_data_processed[team_code_key].setdefault(p_key, 0)

    # 2. Fetch Penalties and Calculate PIM & PP Opportunities
    penalties_raw = Penalty.query.filter_by(game_id=game_id).all()
    pim_totals = {game_obj.team1_code: 0, game_obj.team2_code: 0}
    
    PIM_MAP = {
        "2 Min": 2, "2+2 Min": 4, "5 Min + Spieldauer": 5,
        "10 Min Disziplinar": 10, "Spieldauer Disziplinar": 10 
    }
    for p in penalties_raw: # Calculate PIM first
        if p.team_code in pim_totals:
            pim_totals[p.team_code] += PIM_MAP.get(p.penalty_type, 0)

    # Calculate PP Opportunities with offsetting for simultaneous penalties
    potential_pp_slots = []
    OPP_COUNT_MAP = {"2 Min": 1, "2+2 Min": 2, "5 Min + Spieldauer": 1}

    for p in penalties_raw:
        if p.penalty_type in OPP_COUNT_MAP:
            num_opportunities = OPP_COUNT_MAP[p.penalty_type]
            beneficiary_team = game_obj.team2_code if p.team_code == game_obj.team1_code else game_obj.team1_code
            for _ in range(num_opportunities):
                potential_pp_slots.append({
                    'time': p.minute_of_game, 
                    'beneficiary': beneficiary_team,
                    'penalized_team': p.team_code 
                })
    
    grouped_slots_by_time = {}
    for slot in potential_pp_slots:
        grouped_slots_by_time.setdefault(slot['time'], []).append(slot)
    
    final_pp_opportunities = {game_obj.team1_code: 0, game_obj.team2_code: 0}
    for time, slots_at_time in grouped_slots_by_time.items():
        opps_for_team1_at_ts = sum(1 for s in slots_at_time if s['beneficiary'] == game_obj.team1_code)
        opps_for_team2_at_ts = sum(1 for s in slots_at_time if s['beneficiary'] == game_obj.team2_code)
        
        cancelled_count = min(opps_for_team1_at_ts, opps_for_team2_at_ts)
        
        net_opps_for_team1 = opps_for_team1_at_ts - cancelled_count
        net_opps_for_team2 = opps_for_team2_at_ts - cancelled_count
        
        final_pp_opportunities[game_obj.team1_code] += net_opps_for_team1
        final_pp_opportunities[game_obj.team2_code] += net_opps_for_team2

    # 3. Fetch Goals and process for display & PP Goals
    goals_raw = Goal.query.filter_by(game_id=game_id).all()
    player_cache_for_stats = {p.id: p for p in Player.query.all()}
    pp_goals_scored = {game_obj.team1_code: 0, game_obj.team2_code: 0}

    # Calculate scores per period for the header table
    team1_scores_by_period = {1: 0, 2: 0, 3: 0, 4: 0} # Period 4 for OT
    team2_scores_by_period = {1: 0, 2: 0, 3: 0, 4: 0}

    for goal in goals_raw:
        time_in_seconds = convert_time_to_seconds(goal.minute)
        period = 4 # Default to OT
        if time_in_seconds <= 1200: period = 1
        elif time_in_seconds <= 2400: period = 2
        elif time_in_seconds <= 3600: period = 3
        
        if goal.team_code == game_obj.team1_code:
            team1_scores_by_period[period] += 1
        elif goal.team_code == game_obj.team2_code:
            team2_scores_by_period[period] += 1

    def get_pname_for_stats(player_id):
        p = player_cache_for_stats.get(player_id)
        return f"{p.first_name} {p.last_name}" if p else "N/A"

    GOAL_TYPE_DISPLAY_MAP = {
        "REG": "EQ", "PP": "PP", "SH": "SH", "PS": "PS"
    }

    game_events_for_stats = []
    for goal in goals_raw:
        time_in_seconds = convert_time_to_seconds(goal.minute)
        period_display = "OT"
        if time_in_seconds <= 1200: period_display = "1st Period"
        elif time_in_seconds <= 2400: period_display = "2nd Period"
        elif time_in_seconds <= 3600: period_display = "3rd Period"

        # Increment PP goals scored
        if goal.goal_type == "PP":
            if goal.team_code in pp_goals_scored:
                pp_goals_scored[goal.team_code] += 1

        game_events_for_stats.append({
            'type': 'goal',
            'time_str': goal.minute,
            'time_for_sort': time_in_seconds,
            'period_display': period_display,
            'team_code': goal.team_code,
            'team_iso': TEAM_ISO_CODES.get(goal.team_code.upper()),
            'goal_type_display': GOAL_TYPE_DISPLAY_MAP.get(goal.goal_type, goal.goal_type), # Mapped type
            'is_empty_net': goal.is_empty_net,
            'scorer': get_pname_for_stats(goal.scorer_id),
            'assist1': get_pname_for_stats(goal.assist1_id) if goal.assist1_id else None,
            'assist2': get_pname_for_stats(goal.assist2_id) if goal.assist2_id else None,
            'scorer_obj': player_cache_for_stats.get(goal.scorer_id),
            'assist1_obj': player_cache_for_stats.get(goal.assist1_id) if goal.assist1_id else None,
            'assist2_obj': player_cache_for_stats.get(goal.assist2_id) if goal.assist2_id else None,
        })
    game_events_for_stats.sort(key=lambda x: x['time_for_sort'])

    # 4. Calculate PP Percentage
    pp_percentage = {game_obj.team1_code: 0, game_obj.team2_code: 0}
    for team_code in [game_obj.team1_code, game_obj.team2_code]:
        if final_pp_opportunities[team_code] > 0:
            pp_percentage[team_code] = round((pp_goals_scored[team_code] / final_pp_opportunities[team_code]) * 100, 1)
        else:
            pp_percentage[team_code] = 0.0 # Or can be displayed as '-' or 'N/A' in template

    return render_template('game_stats.html',
                           year=year_obj,
                           game=game_obj,
                           team_iso_codes=TEAM_ISO_CODES,
                           sog_data_for_stats_page=sog_data_processed,
                           sog_totals=sog_totals,
                           pim_totals=pim_totals,
                           game_events=game_events_for_stats,
                           pp_goals_scored=pp_goals_scored, 
                           pp_opportunities=final_pp_opportunities,
                           pp_percentage=pp_percentage,
                           team1_scores_by_period=team1_scores_by_period,
                           team2_scores_by_period=team2_scores_by_period)

# --- CLI commands for DB ---
@app.cli.command("init-db")
def init_db_command():
    """Initializes the database."""
    global _app_context_initialized_for_db
    if not _app_context_initialized_for_db:
        _init_app_context_and_db() # This will create tables and directories
    
    # Check if UPLOAD_FOLDER (for fixtures) exists, if not create it
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
        print(f"Created fixture upload directory: {app.config['UPLOAD_FOLDER']}")
        
    print("Initialized the database and required directories.")

_app_context_initialized_for_db = False
def _init_app_context_and_db():
    """Ensures app context and creates DB tables if not present."""
    global _app_context_initialized_for_db
    if _app_context_initialized_for_db:
        return

    # Create an app context if we're not already in one (e.g., when running `flask init-db`)
    # If app.app_context() is already active, this creates a new one, which is fine.
    # The important part is that db.create_all() is called within an app context.
    with app.app_context():
        # Create database directory if it doesn't exist
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            print(f"Created database directory: {db_dir}")

        db.create_all()
    _app_context_initialized_for_db = True


# Ensure DB init is called if app is run directly (python app.py)
# This is for convenience during development. `flask init-db` is more explicit.
if __name__ == '__main__':
    if not _app_context_initialized_for_db:
         _init_app_context_and_db()
    app.run(debug=True)
