from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
import json
import os
from werkzeug.utils import secure_filename
from dataclasses import dataclass, field # Added for TeamStats
import re # Add this at the top of your app.py

# --- Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'fixtures')
ALLOWED_EXTENSIONS = {'json'}

# --- Team ISO Codes for Flags (lowercase for flagcdn.com) ---
TEAM_ISO_CODES = {
    "AUT": "at", "FIN": "fi", "SUI": "ch", "CZE": "cz",
    "SWE": "se", "SVK": "sk", "DEN": "dk", "USA": "us",
    "SLO": "si", "CAN": "ca", "NOR": "no", "KAZ": "kz",
    "GER": "de", "HUN": "hu", "FRA": "fr", "LAT": "lv",
    "ITA": "it", "GBR": "gb", "POL": "pl",
    # For teams like QF, SF, etc., we won't have a country flag.
    # The template will need to handle cases where the code is None or not found.
    "QF": None, "SF": None, "L(SF)": None, "W(SF)": None 
}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_please_change_this' 
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "data", "iihf_data.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Dataclass for Team Statistics ---
@dataclass
class TeamStats:
    name: str
    group: str # Group identifier like 'Group A', 'Group B'
    gp: int = 0
    w: int = 0
    otw: int = 0
    sow: int = 0
    l: int = 0
    otl: int = 0
    sol: int = 0
    gf: int = 0
    ga: int = 0
    pts: int = 0
    gd: int = field(init=False)

    def __post_init__(self):
        self.gd = self.gf - self.ga

# --- Models ---
class ChampionshipYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, unique=True, nullable=False)
    fixture_path = db.Column(db.String(300), nullable=True) 
    games = db.relationship('Game', backref='championship_year', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<ChampionshipYear {self.year}>'

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year_id = db.Column(db.Integer, db.ForeignKey('championship_year.id'), nullable=False)
    
    date = db.Column(db.String(20))
    start_time = db.Column(db.String(20))
    round = db.Column(db.String(50))
    group = db.Column(db.String(10), nullable=True)
    game_number = db.Column(db.Integer) # Should be unique within a year's fixture
    team1_code = db.Column(db.String(3))
    team2_code = db.Column(db.String(3))
    location = db.Column(db.String(100))
    venue = db.Column(db.String(100))
    
    # Results
    team1_score = db.Column(db.Integer, nullable=True)
    team2_score = db.Column(db.Integer, nullable=True)
    result_type = db.Column(db.String(10), nullable=True, default='REG') # REG, OT, SO

    # Calculated after result entry
    team1_points = db.Column(db.Integer, default=0)
    team2_points = db.Column(db.Integer, default=0)

    # Felder für Toranzahl und Übereinstimmung mit Spielstand werden NICHT als DB-Spalten hinzugefügt,
    # sondern dynamisch in der Route berechnet.

    def __repr__(self):
        return f'<Game {self.game_number}: {self.team1_code} vs {self.team2_code}>'

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_code = db.Column(db.String(3), nullable=False) # e.g., GER, CAN
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<Player {self.first_name} {self.last_name} ({self.team_code})>'

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    team_code = db.Column(db.String(3), nullable=False) # Team that scored
    minute = db.Column(db.String(5), nullable=False) # mm:ss
    goal_type = db.Column(db.String(10), nullable=False) # REG, PP, SH, EN

    scorer_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    assist1_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    assist2_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)

    # Relationships
    game = db.relationship('Game', backref=db.backref('goals', lazy='dynamic', cascade="all, delete-orphan"))
    scorer = db.relationship('Player', foreign_keys=[scorer_id], backref=db.backref('goals_scored', lazy=True))
    assist1 = db.relationship('Player', foreign_keys=[assist1_id], backref=db.backref('assists1', lazy=True))
    assist2 = db.relationship('Player', foreign_keys=[assist2_id], backref=db.backref('assists2', lazy=True))

    def __repr__(self):
        return f'<Goal by {self.scorer_id} in Game {self.game_id} at {self.minute}>'

# --- Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'delete_year' in request.form:
            year_id_to_delete = request.form.get('year_id_to_delete')
            year_obj = db.session.get(ChampionshipYear, year_id_to_delete)
            if year_obj:
                if year_obj.fixture_path and os.path.exists(year_obj.fixture_path):
                    try:
                        os.remove(year_obj.fixture_path)
                    except OSError as e:
                        flash(f"Fehler beim Löschen der Spielplandatei: {e}", "danger")
                db.session.delete(year_obj)
                db.session.commit()
                flash(f'Jahr {year_obj.year} und zugehörige Daten erfolgreich gelöscht!', 'success')
            else:
                flash('Jahr zum Löschen nicht gefunden.', 'warning')
            return redirect(url_for('index'))

        year_str = request.form.get('year')
        fixture_file = request.files.get('fixture_file')

        if not year_str:
            flash('Jahr ist ein Pflichtfeld!', 'danger')
            return redirect(url_for('index'))
        
        try:
            year_int = int(year_str)
        except ValueError:
            flash('Jahr muss eine Zahl sein!', 'danger')
            return redirect(url_for('index'))

        existing_year = ChampionshipYear.query.filter_by(year=year_int).first()
        target_year = existing_year

        if not target_year:
            new_year = ChampionshipYear(year=year_int)
            db.session.add(new_year)
            # Commit early to get ID if needed for file naming, or before processing
            # However, if fixture processing fails for a new year, we might want to roll back this year creation.
            # Let's commit after successful fixture processing or if no fixture is provided initially.
            # For now, simple commit to create the year object.
            try:
                db.session.commit()
                target_year = new_year
                flash(f'Jahr {year_int} erstellt.', 'success')
            except Exception as e: # Handles potential unique constraint violation if somehow re-entered
                db.session.rollback()
                flash(f'Fehler beim Erstellen des Jahres {year_int}: {e}', 'danger')
                return redirect(url_for('index'))
        else:
            flash(f'Jahr {year_int} existiert bereits. Spielplan wird ggf. aktualisiert.', 'info')


        if fixture_file and fixture_file.filename != '':
            if not target_year: # Should not happen if we just created/found it
                flash('Fehler: Zieljahr nicht definiert vor Datei-Upload.', 'danger')
                return redirect(url_for('index'))

            if allowed_file(fixture_file.filename):
                filename = secure_filename(f"{target_year.year}_{fixture_file.filename}")
                fixture_save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                old_fixture_path = target_year.fixture_path

                try:
                    fixture_file.save(fixture_save_path)
                    target_year.fixture_path = fixture_save_path
                    
                    # Delete old games if re-uploading fixture
                    Game.query.filter_by(year_id=target_year.id).delete()
                    # db.session.commit() # Commit game deletion before adding new ones

                    with open(fixture_save_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if "schedule" not in data or not isinstance(data["schedule"], list):
                        flash('JSON-Datei muss ein "schedule"-Array enthalten.', 'danger')
                        raise ValueError("Invalid fixture format: no schedule array")

                    game_numbers_in_fixture = set()
                    games_to_add = []
                    for game_data in data['schedule']:
                        game_num = game_data.get('gameNumber')
                        if game_num is None:
                             raise ValueError("Spiel im Spielplan ohne Spielnummer gefunden.")
                        if game_num in game_numbers_in_fixture:
                            raise ValueError(f"Doppelte Spielnummer {game_num} im Spielplan gefunden.")
                        game_numbers_in_fixture.add(game_num)

                        game = Game(
                            year_id=target_year.id,
                            date=game_data.get('date'),
                            start_time=game_data.get('startTime'),
                            round=game_data.get('round'),
                            group=game_data.get('group'),
                            game_number=game_num,
                            team1_code=game_data.get('team1'),
                            team2_code=game_data.get('team2'),
                            location=game_data.get('location'),
                            venue=game_data.get('venue')
                        )
                        games_to_add.append(game)
                    
                    db.session.add_all(games_to_add)
                    db.session.commit()
                    flash(f'Spielplan für {target_year.year} erfolgreich hochgeladen und verarbeitet!', 'success')
                    
                    # Delete old physical fixture file if new one is different and successfully processed
                    if old_fixture_path and old_fixture_path != fixture_save_path and os.path.exists(old_fixture_path):
                        try:
                            os.remove(old_fixture_path)
                        except OSError:
                            flash(f'Konnte alte Spielplandatei {old_fixture_path} nicht löschen.', 'warning')

                except Exception as e:
                    db.session.rollback()
                    flash(f'Fehler bei der Verarbeitung der Spielplandatei: {str(e)}', 'danger')
                    # Revert fixture_path if new upload failed
                    target_year.fixture_path = old_fixture_path 
                    if os.path.exists(fixture_save_path):
                        try: 
                            os.remove(fixture_save_path)
                        except OSError:
                             pass # if removal of bad upload fails, not much to do
                    # If it was a new year and fixture upload failed, delete the year unless user wants to keep it empty
                    # Current logic keeps the year. This could be changed.
                    # If it was an existing year, its old games are already deleted. This is a bit destructive.
                    # A better approach might be to load games into a temporary list and only commit if all is well.
                    # For now, a rollback occurs, but previous games for this year are gone if re-uploading.
                    # This needs careful consideration for data integrity on failed re-uploads.
                    # Simpler for now: commit() on game deletion, then try to add new games.
                    # Let's refine: we already deleted games. If new load fails, year has no games.
                    # And fixture_path should be reset if the new file is bad.
                    # This needs careful consideration for data integrity on failed re-uploads.
                    # Simpler for now: commit() on game deletion, then try to add new games.
                    # Let's refine: we already deleted games. If new load fails, year has no games.
                    # And fixture_path should be reset if the new file is bad.
                    db.session.commit() # Commit the rollback of fixture_path change and game additions.
            else:
                flash('Ungültiger Dateityp. Nur JSON-Dateien sind erlaubt.', 'danger')
        elif fixture_file and fixture_file.filename == '' and target_year and not target_year.fixture_path:
             flash('Bitte wählen Sie eine Spielplandatei zum Hochladen aus.', 'warning')
        elif not fixture_file and existing_year is None: # Only show this if it's a truly new year with no file attempt
             flash(f'Jahr {target_year.year} erstellt, aber kein Spielplan hochgeladen.', 'info')


        return redirect(url_for('index'))

    years = ChampionshipYear.query.order_by(ChampionshipYear.year.desc()).all()
    return render_template('index.html', years=years, team_iso_codes=TEAM_ISO_CODES)

@app.route('/year/<int:year_id>', methods=['GET', 'POST'])
def year_view(year_id):
    year_obj = ChampionshipYear.query.get_or_404(year_id)
    all_games_for_year_obj = Game.query.filter_by(year_id=year_obj.id).order_by(Game.game_number).all()

    # Get the selected team filter for statistics
    stats_team_filter = request.args.get('stats_team_filter', 'ALL') # 'ALL' is default

    if request.method == 'POST':
        game_id = request.form.get('game_id')
        team1_score_str = request.form.get('team1_score')
        team2_score_str = request.form.get('team2_score')
        result_type = request.form.get('result_type') # REG, OT, SO

        game_to_update = db.session.get(Game, game_id)
        if not game_to_update or game_to_update.year_id != year_obj.id:
            flash('Spiel nicht gefunden oder ungültig für dieses Jahr!', 'danger')
            return redirect(url_for('year_view', year_id=year_id))

        try:
            team1_score = int(team1_score_str) if team1_score_str and team1_score_str.strip() else None
            team2_score = int(team2_score_str) if team2_score_str and team2_score_str.strip() else None

            if (team1_score is not None and team1_score < 0) or \
               (team2_score is not None and team2_score < 0):
                 flash('Spielstände müssen nicht-negative Zahlen sein.', 'danger')
                 return redirect(url_for('year_view', year_id=year_id, _anchor=f'game-{game_to_update.id}'))
            
            if team1_score is not None and team2_score is not None: # Both scores must be present
                # Validation based on result type
                if result_type == 'REG':
                    if team1_score == team2_score:
                        flash('Bei regulärer Spielzeit darf das Ergebnis nicht unentschieden sein.', 'danger')
                        return redirect(url_for('year_view', year_id=year_id, _anchor=f'game-{game_to_update.id}'))
                elif result_type in ['OT', 'SO']:
                    if team1_score == team2_score:
                        flash('Bei Overtime/Penalty darf das Ergebnis nicht unentschieden sein.', 'danger')
                        return redirect(url_for('year_view', year_id=year_id, _anchor=f'game-{game_to_update.id}'))
                    if abs(team1_score - team2_score) != 1:
                        flash('Bei Overtime/Penalty muss der Unterschied genau ein Tor betragen.', 'danger')
                        return redirect(url_for('year_view', year_id=year_id, _anchor=f'game-{game_to_update.id}'))
                
                game_to_update.team1_score = team1_score
                game_to_update.team2_score = team2_score
                game_to_update.result_type = result_type

                # Calculate points
                if team1_score > team2_score:
                    if result_type == 'REG':
                        game_to_update.team1_points = 3
                        game_to_update.team2_points = 0
                    else: # OT or SO win
                        game_to_update.team1_points = 2
                        game_to_update.team2_points = 1
                elif team2_score > team1_score:
                    if result_type == 'REG':
                        game_to_update.team2_points = 3
                        game_to_update.team1_points = 0
                    else: # OT or SO win
                        game_to_update.team2_points = 2
                        game_to_update.team1_points = 1
                else: # Should not happen due to validation, but as a fallback
                    game_to_update.team1_points = 0
                    game_to_update.team2_points = 0
            
            else: # One or both scores are empty, treat as clearing the result
                game_to_update.team1_score = None
                game_to_update.team2_score = None
                game_to_update.result_type = 'REG' # Default back
                game_to_update.team1_points = 0
                game_to_update.team2_points = 0
                
            db.session.commit()
            flash('Ergebnis erfolgreich gespeichert!', 'success')
        except ValueError:
            flash('Ungültige Eingabe für Spielstand.', 'danger')
        
        # Redirect to the same page, possibly to an anchor for the game
        # The anchor part needs the game_id or some identifier in the template
        return redirect(url_for('year_view', year_id=year_id, _anchor=f'game-{game_to_update.id}'))

    # Prepare games by round (for display)
    games_by_round = {}
    for game_obj in all_games_for_year_obj: # Renamed to avoid confusion with game model class
        round_name = game_obj.round if game_obj.round else "Unbekannte Runde"
        if round_name not in games_by_round:
            games_by_round[round_name] = []
        
        # Dynamically calculate goal count vs score for indicator
        # These will be attributes of the game_obj instance, not DB columns
        team1_goals_actual = 0
        team2_goals_actual = 0

        # Ensure scores are integers for comparison, or None
        current_team1_score = game_obj.team1_score
        current_team2_score = game_obj.team2_score

        if current_team1_score is not None:
            team1_goals_actual = sum(1 for goal in game_obj.goals if goal.team_code == game_obj.team1_code)
        
        if current_team2_score is not None:
            team2_goals_actual = sum(1 for goal in game_obj.goals if goal.team_code == game_obj.team2_code)

        # Adjust expected scores if it's a shootout result
        team1_score_for_comparison = current_team1_score
        team2_score_for_comparison = current_team2_score

        if game_obj.result_type == 'SO':
            if current_team1_score is not None and current_team2_score is not None:
                if current_team1_score > current_team2_score: # Team 1 won SO
                    team1_score_for_comparison = current_team1_score - 1
                elif current_team2_score > current_team1_score: # Team 2 won SO
                    team2_score_for_comparison = current_team2_score - 1
                # If scores are equal in an SO game, it's an invalid state for this logic,
                # but we'll proceed and it will likely result in a mismatch, which is acceptable.

        # Set match status attributes
        game_obj.team1_score_matches_goals = (team1_score_for_comparison == team1_goals_actual) if current_team1_score is not None else False
        game_obj.team2_score_matches_goals = (team2_score_for_comparison == team2_goals_actual) if current_team2_score is not None else False
        
        # Overall indicator: True if all entered scores match their respective goal counts.
        # If a score isn't entered, it doesn't count as a mismatch for that team.
        # If both scores are entered, both must match.
        # If only one is entered, only that one needs to match.
        # If no scores are entered, it's not considered a match or mismatch for this purpose (False).
        if current_team1_score is not None and current_team2_score is not None:
            game_obj.scores_fully_match_goals = game_obj.team1_score_matches_goals and game_obj.team2_score_matches_goals
        elif current_team1_score is not None:
            game_obj.scores_fully_match_goals = game_obj.team1_score_matches_goals
        elif current_team2_score is not None:
            game_obj.scores_fully_match_goals = game_obj.team2_score_matches_goals
        else: # No scores entered
            game_obj.scores_fully_match_goals = False # Default to False, consider if True makes more sense when no scores

        games_by_round[round_name].append(game_obj)

    # --- Calculate standings for Preliminary Round ---
    standings_data = {} # Using TeamStats objects
    
    # Identify all unique teams and their groups from the preliminary round fixtures
    all_prelim_teams_with_groups = {} # team_code -> group_name
    if 'Preliminary Round' in games_by_round:
        for game in games_by_round['Preliminary Round']:
            if game.group: # Ensure game has a group
                if game.team1_code not in all_prelim_teams_with_groups:
                    all_prelim_teams_with_groups[game.team1_code] = game.group
                if game.team2_code not in all_prelim_teams_with_groups:
                    all_prelim_teams_with_groups[game.team2_code] = game.group
                
                # Initialize TeamStats if not already present
                if game.team1_code not in standings_data:
                    standings_data[game.team1_code] = TeamStats(name=game.team1_code, group=game.group)
                if game.team2_code not in standings_data:
                    standings_data[game.team2_code] = TeamStats(name=game.team2_code, group=game.group)

    # Iterate over preliminary games with results to calculate stats
    prelim_games_with_results = [
        g for g in all_games_for_year_obj 
        if g.round == 'Preliminary Round' and g.team1_score is not None and g.team2_score is not None and g.group
    ]

    for game in prelim_games_with_results:
        s1 = standings_data.get(game.team1_code)
        s2 = standings_data.get(game.team2_code)

        if not s1 or not s2: # Should not happen if initialization was correct
            continue

        s1.gp += 1; s2.gp += 1
        s1.gf += game.team1_score; s1.ga += game.team2_score
        s2.gf += game.team2_score; s2.ga += game.team1_score
        s1.pts += game.team1_points; s2.pts += game.team2_points

        if game.team1_score > game.team2_score:
            if game.result_type == 'REG': s1.w += 1; s2.l += 1
            elif game.result_type == 'OT': s1.otw += 1; s2.otl += 1
            elif game.result_type == 'SO': s1.sow += 1; s2.sol += 1
        elif game.team2_score > game.team1_score:
            if game.result_type == 'REG': s2.w += 1; s1.l += 1
            elif game.result_type == 'OT': s2.otw += 1; s1.otl += 1
            elif game.result_type == 'SO': s2.sow += 1; s1.sol += 1
        
        # Update GD after GF/GA change
        s1.__post_init__() 
        s2.__post_init__()

    # Group and Sort standings
    sorted_standings = {} # This will be group_name -> list of TeamStats
    temp_standings_by_group = {} # group_name -> list of TeamStats
    for team_stat in standings_data.values():
        if team_stat.group not in temp_standings_by_group:
            temp_standings_by_group[team_stat.group] = []
        temp_standings_by_group[team_stat.group].append(team_stat)
    
    for group_name, group_teams_stats in temp_standings_by_group.items():
        sorted_standings[group_name] = sorted(
            group_teams_stats,
            key=lambda x: (x.pts, x.gd, x.gf),
            reverse=True
        )
    # --- End of Standings Calculation ---

    # --- Resolve Playoff Team Placeholders ---
    playoff_team_map = {}
    games_dict_by_number = {g.game_number: g for g in all_games_for_year_obj}

    # 1. Resolve QF placeholders from standings (A1-A4, B1-B4)
    group_a_standings_teams = sorted_standings.get('Group A', [])
    group_b_standings_teams = sorted_standings.get('Group B', [])

    for i, team_stat_obj in enumerate(group_a_standings_teams):
        playoff_team_map[f'A{i+1}'] = team_stat_obj.name
    for i, team_stat_obj in enumerate(group_b_standings_teams):
        playoff_team_map[f'B{i+1}'] = team_stat_obj.name
    
    # 2. Resolve SF placeholders (Q1-Q4 from QF winners)
    # Assuming fixed game numbers for QFs as per 2025.json: 57, 58, 59, 60
    # And these map to Q1, Q2, Q3, Q4 respectively
    qf_game_to_sf_placeholder = {
        57: 'Q1', 58: 'Q2', 59: 'Q3', 60: 'Q4'
    }
    for game_num, sf_placeholder in qf_game_to_sf_placeholder.items():
        qf_game = games_dict_by_number.get(game_num)
        if qf_game and qf_game.team1_score is not None and qf_game.team2_score is not None:
            qf_team1_original_ph = qf_game.team1_code # e.g., "A1"
            qf_team2_original_ph = qf_game.team2_code # e.g., "B4"

            qf_team1_actual = playoff_team_map.get(qf_team1_original_ph) # Resolved e.g., "SWE"
            qf_team2_actual = playoff_team_map.get(qf_team2_original_ph) # Resolved e.g., "FIN"
            
            # Only proceed if both QF teams are resolved from standings
            if qf_team1_actual and qf_team2_actual:
                winner_actual_code = qf_team1_actual if qf_game.team1_points > qf_game.team2_points else qf_team2_actual
                playoff_team_map[sf_placeholder] = winner_actual_code

    # 3. Resolve Final placeholders (W(SF1), L(SF1), W(SF2), L(SF2) from SF winners/losers)
    # Assuming fixed game numbers for SFs as per 2025.json: 61 (SF1), 62 (SF2)
    sf_game_to_final_placeholders = {
        61: 'SF1', # Game 61 is SF1, its teams are Q1 vs Q2 from fixture
        62: 'SF2'  # Game 62 is SF2, its teams are Q3 vs Q4 from fixture
    }
    for game_num, sf_id_placeholder in sf_game_to_final_placeholders.items():
        sf_game = games_dict_by_number.get(game_num)
        if sf_game and sf_game.team1_score is not None and sf_game.team2_score is not None:
            # sf_game.team1_code is e.g. "Q1", sf_game.team2_code is e.g. "Q2"
            sf_team1_original_ph = sf_game.team1_code 
            sf_team2_original_ph = sf_game.team2_code

            sf_team1_actual = playoff_team_map.get(sf_team1_original_ph) # Resolved e.g. "SWE" from Q1
            sf_team2_actual = playoff_team_map.get(sf_team2_original_ph) # Resolved e.g. "CAN" from Q2

            # Only proceed if both SF teams are resolved from QF winners
            if sf_team1_actual and sf_team2_actual:
                if sf_game.team1_points > sf_game.team2_points:
                    playoff_team_map[f'W({sf_id_placeholder})'] = sf_team1_actual
                    playoff_team_map[f'L({sf_id_placeholder})'] = sf_team2_actual
                else: # team2 won or score is invalid (but points should reflect winner)
                    playoff_team_map[f'W({sf_id_placeholder})'] = sf_team2_actual
                    playoff_team_map[f'L({sf_id_placeholder})'] = sf_team1_actual
    # --- End of Playoff Team Resolution ---

    # Fetch all players, grouped by team_code (players are now global)
    all_players_query = Player.query.all()
    all_players_by_team = {}
    for player in all_players_query:
        if player.team_code not in all_players_by_team:
            all_players_by_team[player.team_code] = []
        all_players_by_team[player.team_code].append({
            "id": player.id,
            "first_name": player.first_name,
            "last_name": player.last_name,
            "full_name": f"{player.last_name.upper()} {player.first_name}"
        })
    
    for team_code_key in all_players_by_team: # Changed variable name to avoid conflict
        all_players_by_team[team_code_key].sort(key=lambda p: (p['last_name'].lower(), p['first_name'].lower()))

    # --- Create team_codes for "Add Player" form dropdown ---
    unique_tournament_team_codes = set()
    for game_obj_item in all_games_for_year_obj:
        if game_obj_item.team1_code:
            unique_tournament_team_codes.add(game_obj_item.team1_code)
        if game_obj_item.team2_code:
            unique_tournament_team_codes.add(game_obj_item.team2_code)
    
    # Filter for actual 3-letter uppercase team codes
    actual_team_codes_for_dropdown = {
        code for code in unique_tournament_team_codes 
        if code and isinstance(code, str) and code.isupper() and len(code) == 3
    }
    # Create a sorted dictionary for the template
    # The values are the same as keys, but you could map to fuller names if available/desired
    team_codes_dropdown_dict = {code: code for code in sorted(list(actual_team_codes_for_dropdown))}
    # For the statistics filter, we'll add an "ALL" option.
    stats_filter_teams = {'ALL': 'Alle Teams'}
    stats_filter_teams.update(team_codes_dropdown_dict)


    # --- Player Statistics Calculation ---
    player_stats = {}
    all_players_dict = {p.id: p for p in all_players_query} # For quick lookup

    # Get all games for the current year to link goals to the correct year
    current_year_games_ids = [g.id for g in all_games_for_year_obj]
    all_goals_for_year = Goal.query.filter(Goal.game_id.in_(current_year_games_ids)).all()

    for player in all_players_query:
        player_stats[player.id] = {
            'player_id': player.id,
            'first_name': player.first_name,
            'last_name': player.last_name,
            'team_code': player.team_code,
            'goals': 0,
            'assists': 0,
            'points': 0
        }

    for goal in all_goals_for_year:
        if goal.scorer_id in player_stats:
            player_stats[goal.scorer_id]['goals'] += 1
            player_stats[goal.scorer_id]['points'] += 1
        if goal.assist1_id and goal.assist1_id in player_stats:
            player_stats[goal.assist1_id]['assists'] += 1
            player_stats[goal.assist1_id]['points'] += 1
        if goal.assist2_id and goal.assist2_id in player_stats:
            player_stats[goal.assist2_id]['assists'] += 1
            player_stats[goal.assist2_id]['points'] += 1
    
    # Filter player_stats if a specific team is selected for stats viewing
    filtered_player_stats_values = player_stats.values()
    if stats_team_filter != 'ALL' and stats_team_filter in team_codes_dropdown_dict:
        filtered_player_stats_values = [p for p in player_stats.values() if p['team_code'] == stats_team_filter]

    # Filter out players with no points for the lists, then sort
    # Torschützen (sorted by goals, then assists, then name)
    goal_scorers_list = sorted(
        [p for p in filtered_player_stats_values if p['goals'] > 0],
        key=lambda x: (-x['goals'], -x['assists'], x['last_name'].lower(), x['first_name'].lower())
    )
    # Assistgeber (sorted by assists, then goals, then name)
    assist_providers_list = sorted(
        [p for p in filtered_player_stats_values if p['assists'] > 0],
        key=lambda x: (-x['assists'], -x['goals'], x['last_name'].lower(), x['first_name'].lower())
    )
    # Top Scorer (sorted by points, then goals, then assists, then name)
    top_scorers_list = sorted(
        [p for p in filtered_player_stats_values if p['points'] > 0],
        key=lambda x: (-x['points'], -x['goals'], -x['assists'], x['last_name'].lower(), x['first_name'].lower())
    )
    # --- End of Player Statistics Calculation ---

    return render_template('year_view.html', 
                           year=year_obj, 
                           games_by_round=games_by_round, 
                           standings=sorted_standings, 
                           team_iso_codes=TEAM_ISO_CODES,
                           playoff_team_map=playoff_team_map,
                           all_players_by_team_json=all_players_by_team, # For goal entry dropdowns
                           team_codes=team_codes_dropdown_dict, # For Add Player form team dropdown
                           goal_scorers=goal_scorers_list,
                           assist_providers=assist_providers_list,
                           top_scorers=top_scorers_list,
                           stats_filter_teams=stats_filter_teams, # Teams for the filter dropdown
                           current_stats_team_filter=stats_team_filter # Active filter
                           )

# Route to add a new player (year_id removed from URL and logic)
@app.route('/add_player', methods=['POST'])
def add_player():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        team_code = request.form.get('team_code')
        year_id_for_context = request.form.get('year_id_for_redirect') # Still useful for context if needed

        if not first_name or not last_name or not team_code:
            return jsonify({'success': False, 'message': 'Vorname, Nachname und Team sind Pflichtfelder.'}), 400

        existing_player = Player.query.filter_by(
            team_code=team_code,
            first_name=first_name, # Consider case-insensitivity if needed
            last_name=last_name
        ).first()

        if existing_player:
            return jsonify({
                'success': False, 
                'message': f'Spieler {first_name} {last_name} existiert bereits für Team {team_code}.'
            }), 409 # 409 Conflict
        
        try:
            new_player = Player(
                first_name=first_name,
                last_name=last_name,
                team_code=team_code
            )
            db.session.add(new_player)
            db.session.commit()
            
            # Prepare player data for JSON response, including the ID
            player_data = {
                'id': new_player.id,
                'first_name': new_player.first_name,
                'last_name': new_player.last_name,
                'team_code': new_player.team_code,
                'full_name': f"{new_player.last_name.upper()} {new_player.first_name}"
            }
            return jsonify({
                'success': True, 
                'message': f'Spieler {first_name} {last_name} erfolgreich zu Team {team_code} hinzugefügt.',
                'player': player_data
            }), 201 # 201 Created
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Fehler beim Hinzufügen des Spielers: {str(e)}") # Log error
            return jsonify({'success': False, 'message': f'Serverfehler beim Hinzufügen des Spielers: {str(e)}'}), 500
    
    # GET requests or other methods not allowed for this AJAX endpoint now
    return jsonify({'success': False, 'message': 'Invalid request method.'}), 405

# Route to add a goal
@app.route('/year/<int:year_id>/game/<int:game_id>/add_goal', methods=['POST'])
def add_goal(year_id, game_id):
    # year_obj = ChampionshipYear.query.get_or_404(year_id) # Already have year_id
    game_obj = Game.query.get_or_404(game_id)

    if game_obj.year_id != year_id:
        return jsonify({'success': False, 'message': 'Ungültiges Spiel für dieses Jahr.'}), 400

    if request.method == 'POST':
        minute = request.form.get('minute')
        team_code = request.form.get('team_code_goal') # Use a specific name from form to avoid conflict
        goal_type = request.form.get('goal_type')
        scorer_id_str = request.form.get('scorer_id')
        assist1_id_str = request.form.get('assist1_id')
        assist2_id_str = request.form.get('assist2_id')

        if not minute or not team_code or not goal_type or not scorer_id_str:
            return jsonify({'success': False, 'message': 'Minute, Team, Typ und Torschütze sind Pflichtfelder.'}), 400
        
        # Validate minute format (mm:ss)
        if not re.match(r"^([0-5]?\d):([0-5]\d)$", minute) and not re.match(r"^\d{1,2}:([0-5]\d)$", minute): 
             # Allows 0:00 to 59:59 or m:ss where m can be >59 if needed for full game times (e.g. 60:00 for end of 3rd)
             # Stricter for typical goal times: ^([0-5]?\d):([0-5]\d)$ for up to 59:59
             # Allowing more general \d{1,2} for minutes for simplicity, assuming typical hockey periods don't exceed 99 min.
             # Let's use a more common pattern for game time up to 99:59
            if not re.match(r"^(\d{1,2}):([0-5]\d)$", minute):
                 return jsonify({'success': False, 'message': 'Minutenformat ungültig. Bitte mm:ss oder m:ss verwenden (z.B. 01:23, 60:00).', 'debug_minute': minute}), 400

        try:
            scorer_id = int(scorer_id_str)
            scorer = Player.query.filter_by(id=scorer_id, team_code=team_code).first()
            if not scorer:
                return jsonify({'success': False, 'message': f'Ungültiger Torschütze oder Spieler (ID: {scorer_id_str}) gehört nicht zum Team {team_code}.'}), 400

            assist1, assist2 = None, None
            assist1_player_data, assist2_player_data = None, None

            if assist1_id_str and assist1_id_str != "":
                assist1_id = int(assist1_id_str)
                if assist1_id == scorer_id:
                    return jsonify({'success': False, 'message': 'Torschütze und Assist 1 dürfen nicht derselbe Spieler sein.'}), 400
                assist1 = Player.query.filter_by(id=assist1_id, team_code=team_code).first()
                if not assist1:
                    return jsonify({'success': False, 'message': f'Ungültiger Assist 1 oder Spieler (ID: {assist1_id_str}) gehört nicht zum Team {team_code}.'}), 400
                assist1_player_data = {'id': assist1.id, 'first_name': assist1.first_name, 'last_name': assist1.last_name}

            if assist2_id_str and assist2_id_str != "":
                assist2_id = int(assist2_id_str)
                if assist2_id == scorer_id:
                    return jsonify({'success': False, 'message': 'Torschütze und Assist 2 dürfen nicht derselbe Spieler sein.'}), 400
                if assist1 and assist2_id == assist1.id:
                    return jsonify({'success': False, 'message': 'Assist 1 und Assist 2 dürfen nicht derselbe Spieler sein.'}), 400
                assist2 = Player.query.filter_by(id=assist2_id, team_code=team_code).first()
                if not assist2:
                    return jsonify({'success': False, 'message': f'Ungültiger Assist 2 oder Spieler (ID: {assist2_id_str}) gehört nicht zum Team {team_code}.'}), 400
                assist2_player_data = {'id': assist2.id, 'first_name': assist2.first_name, 'last_name': assist2.last_name}
            
            new_goal = Goal(
                game_id=game_id,
                team_code=team_code,
                minute=minute,
                goal_type=goal_type,
                scorer_id=scorer.id,
                assist1_id=assist1.id if assist1 else None,
                assist2_id=assist2.id if assist2 else None
            )
            db.session.add(new_goal)
            db.session.commit()

            # Refresh game_obj to get updated goals list and calculate match status
            db.session.refresh(game_obj) # Ensures game_obj.goals is up-to-date
            
            team1_goals_actual = 0
            team2_goals_actual = 0
            current_team1_score = game_obj.team1_score
            current_team2_score = game_obj.team2_score

            # Use game_obj.goals.all() if lazy='dynamic', or game_obj.goals if lazy=True (default)
            # Assuming game.goals is a dynamic relationship or needs to be queried
            all_game_goals = Goal.query.filter_by(game_id=game_obj.id).all()


            if current_team1_score is not None:
                team1_goals_actual = sum(1 for goal_in_list in all_game_goals if goal_in_list.team_code == game_obj.team1_code)
            
            if current_team2_score is not None:
                team2_goals_actual = sum(1 for goal_in_list in all_game_goals if goal_in_list.team_code == game_obj.team2_code)

            # Adjust expected scores if it's a shootout result
            team1_score_for_comparison = current_team1_score
            team2_score_for_comparison = current_team2_score

            if game_obj.result_type == 'SO':
                if current_team1_score is not None and current_team2_score is not None:
                    if current_team1_score > current_team2_score: # Team 1 won SO
                        team1_score_for_comparison = current_team1_score - 1
                    elif current_team2_score > current_team1_score: # Team 2 won SO
                        team2_score_for_comparison = current_team2_score - 1

            team1_score_matches_goals = (team1_score_for_comparison == team1_goals_actual) if current_team1_score is not None else False
            team2_score_matches_goals = (team2_score_for_comparison == team2_goals_actual) if current_team2_score is not None else False
            
            # Determine overall scores_fully_match_goals for the AJAX response
            # This should mirror the logic in year_view for consistency
            ajax_scores_fully_match_goals = False
            if current_team1_score is not None and current_team2_score is not None:
                ajax_scores_fully_match_goals = team1_score_matches_goals and team2_score_matches_goals
            elif current_team1_score is not None:
                ajax_scores_fully_match_goals = team1_score_matches_goals
            elif current_team2_score is not None:
                ajax_scores_fully_match_goals = team2_score_matches_goals
            # else: it remains False if no scores entered, which is fine for AJAX update

            new_goal_count_for_game = len(all_game_goals)


            # Get team display names for the game
            p1_display_name = game_obj.team1_code # Fallback
            p2_display_name = game_obj.team2_code # Fallback
            # This logic to get p1_display_name and p2_display_name needs to be available here or passed
            # For simplicity, just use team_code for now in JSON response

            goal_data = {
                'id': new_goal.id,
                'minute': new_goal.minute,
                'team_code': new_goal.team_code,
                'goal_type': new_goal.goal_type,
                'scorer': {'id': scorer.id, 'first_name': scorer.first_name, 'last_name': scorer.last_name, 'full_name': f"{scorer.last_name.upper()} {scorer.first_name}"},
                'assist1': assist1_player_data if assist1 else None,
                'assist2': assist2_player_data if assist2 else None,
                'game_id': new_goal.game_id
            }
            if assist1_player_data:
                 goal_data['assist1']['full_name'] = f"{assist1.last_name.upper()} {assist1.first_name}"
            if assist2_player_data:
                 goal_data['assist2']['full_name'] = f"{assist2.last_name.upper()} {assist2.first_name}"


            return jsonify({
                'success': True, 
                'message': 'Tor erfolgreich hinzugefügt!', 
                'goal': goal_data,
                'new_goal_count': new_goal_count_for_game,
                'scores_fully_match_goals': ajax_scores_fully_match_goals
            }), 201

        except ValueError: # For int conversion errors
             return jsonify({'success': False, 'message': 'Ungültige Spieler-ID erhalten.'}), 400
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Fehler beim Hinzufügen des Tores: {str(e)}")
            return jsonify({'success': False, 'message': f'Serverfehler beim Hinzufügen des Tores: {str(e)}'}), 500
    
    return jsonify({'success': False, 'message': 'Invalid request method.'}), 405

# Route to delete a goal
@app.route('/year/<int:year_id>/goal/<int:goal_id>/delete', methods=['POST'])
def delete_goal(year_id, goal_id):
    year_obj = ChampionshipYear.query.get_or_404(year_id)
    goal_to_delete = Goal.query.get_or_404(goal_id)
    game_id_anchor = request.form.get('game_id_anchor', goal_to_delete.game_id) # Fallback to goal's game_id

    if goal_to_delete.game.year_id != year_obj.id:
        flash("Ungültiges Tor zum Löschen für dieses Jahr.", "danger")
        return redirect(url_for('year_view', year_id=year_id))

    try:
        db.session.delete(goal_to_delete)
        db.session.commit()
        flash('Tor erfolgreich gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Löschen des Tores: {str(e)}', 'danger')

    redirect_anchor = f'#goal-entry-{game_id_anchor}' if game_id_anchor else ''
    return redirect(url_for('year_view', year_id=year_id, _anchor=redirect_anchor.lstrip('#')))


# --- CLI commands for DB ---
@app.cli.command("init-db")
def init_db_command():
    """Erstellt die Datenbanktabellen und notwendige Verzeichnisse."""
    data_dir = os.path.join(BASE_DIR, 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Verzeichnis '{data_dir}' erstellt.")
    
    fixtures_dir = os.path.join(data_dir, 'fixtures')
    if not os.path.exists(fixtures_dir):
        os.makedirs(fixtures_dir)
        print(f"Verzeichnis '{fixtures_dir}' erstellt.")
        
    db.create_all()
    print("Datenbank initialisiert und Tabellen erstellt.")

def _init_app_context_and_db():
    """Ensures app context and db/dirs are set up. Called on run/CLI command."""
    # This function might be called multiple times, ensure operations are idempotent.
    app_context_created = False
    if not hasattr(app, 'app_context_pushed'): # Simple flag to avoid re-entry issues in some setups
        app.app_context_pushed = True 
        app_context_created = True
        ctx = app.app_context()
        ctx.push()

    try:
        db_path_str = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_path_str.startswith('sqlite:///'):
            db_file_path = db_path_str[len('sqlite:///'):]
            data_dir = os.path.dirname(db_file_path)
            if data_dir: # Ensure data_dir is not empty if db_file_path is just a filename
                os.makedirs(data_dir, exist_ok=True)
        
        fixtures_dir = app.config.get('UPLOAD_FOLDER')
        if fixtures_dir:
            os.makedirs(fixtures_dir, exist_ok=True)
        
        db.create_all()
    finally:
        if app_context_created:
            ctx.pop()
            del app.app_context_pushed

if __name__ == '__main__':
    # When running with `python app.py`, ensure context for `_init_app_context_and_db`
    with app.app_context():
        _init_app_context_and_db()
    app.run(debug=True)

# Note: If using `flask run`, Flask's CLI handles app context for `init-db`.
# The _init_app_context_and_db() function will create dirs/db if they don't exist
# when called by `init-db` or by `python app.py`. 