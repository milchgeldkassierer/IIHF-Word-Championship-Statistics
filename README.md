# IIHF Word Championship Statistics

A Flask-based web application for managing ice hockey tournament data, including fixtures, scores, goals, penalties, and player statistics. The application supports multiple tournament years and provides features for tracking games, goals, and player performance with automated fixture loading.

## Features

- Manage multiple tournament years
- Automatic loading of tournament fixtures (YYYY.json) based on selected year from predefined directories
- Track game scores and results (Regular, OT, SO)
- Record goals with detailed information (scorer, assists, time, type, empty net)
- Record penalties with details (player, time, type, reason)
- Manage player rosters per team
- View dynamic tournament standings for preliminary rounds
- Track player statistics (goals, assists, points, PIM)
- View detailed game statistics including Shots on Goal (SOG) per period, PowerPlay opportunities and efficiency.
- Team flag display using country codes

## Prerequisites

- Python 3.7 or higher
- pip (Python package manager)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/AKurthFT/IIHF-Word-Championship-Statistics.git
cd IIHF-Word-Championship-Statistics
```

2. Create and activate a virtual environment (optional but recommended):
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

4. Initialize the database:
   This command creates the necessary database schema and directories if they don't exist.
```bash
flask init-db
```

## Running the Application

1. Ensure your fixture files (e.g., `2024.json`, `2025.json`) are present in the `fixtures/` directory at the root of the project.
2. Start the Flask development server:
```bash
flask run
```

3. Open your web browser and navigate to:
```
http://localhost:5000
```

## Project Structure

- `app.py`: Main application file containing Flask routes, database models, and business logic.
- `templates/`: HTML templates for the web interface (using Jinja2).
- `static/`: Static files (CSS, JavaScript, images - if any).
- `fixtures/`: **(Project Root)** Directory for placing master template fixture files (e.g., `YYYY.json`). The application will look here for schedules.
- `data/`: Directory for application-managed data.
  - `fixtures/`: **(Inside `data/`)** Directory where the application might also look for fixture files (e.g. `YYYY.json`). This is also the default upload location if uploads were enabled.
  - `iihf_data.db`: SQLite database file that stores all tournament, game, player, and statistical data.

## Database Models

- `ChampionshipYear`: Represents a tournament year, including its name and a path to its loaded fixture file.
- `Game`: Stores all game information, including teams, scores, round, group, location, and result type.
- `Player`: Manages player information (name, team, jersey number).
- `Goal`: Records detailed goal information (scorer, assists, time, type, empty net status).
- `Penalty`: Records penalty details (player/team, time, type, reason).
- `ShotsOnGoal`: Tracks shots on goal per team per period for each game.

## Usage

1.  **Prepare Fixture Files**:
    *   Create JSON files for each tournament year you want to manage (e.g., `2024.json`, `2025.json`).
    *   Place these files in the `fixtures/` directory at the root of the project.
    *   The format of these files is described in the "Data Format" section below.

2.  **Adding/Updating a Tournament Year**:
    *   Navigate to the home page (`/`).
    *   The "Jahr" (Year) dropdown will be populated with years for which `YYYY.json` files are found in the `fixtures/` directory.
    *   Enter a "Name des Turniers" (Tournament Name).
    *   Select a "Jahr" (Year) from the dropdown.
    *   Click "Turnier anlegen / Aktualisieren".
    *   The system will attempt to find the corresponding `YYYY.json` file (e.g., `2024.json` if you selected 2024) from the predefined locations.
    *   If found, the schedule will be loaded into the database for that tournament name and year. If a tournament with the same name and year already exists, its game schedule will be refreshed from the JSON file.

3.  **Managing Games**:
    *   From the home page, click on a tournament year to go to its overview page.
    *   Here you can view all games, standings, and player statistics.
    *   Update game scores and result types (REG, OT, SO).
    *   For each game, you can:
        *   Add/delete goals, specifying scorer, up to two assists, time, goal type (EQ, PP, SH, PS), and if it was an empty-net goal.
        *   Add/delete penalties, specifying the player (or team/bench penalty), time, penalty type, and reason.
        *   Enter Shots on Goal (SOG) for each team per period (P1, P2, P3, OT).
        *   View detailed game statistics.

4.  **Player Management**:
    *   Players can be added globally or directly when entering goal/penalty details if they don't exist yet.
    *   The system tracks player statistics (Goals, Assists, Points, PIM) across the tournament.

## Data Format

The application expects fixture files (e.g., `2024.json`) in JSON format. The main key should be `"schedule"`, containing a list of game objects:
```json
{
  "championship": "IIHF ICE HOCKEY WORLD CHAMPIONSHIP", // Optional metadata
  "year": 2024, // Optional metadata
  "hosts": ["Country"], // Optional metadata
  "schedule": [
    {
      "gameNumber": 1,
      "date": "YYYY-MM-DD",
      "startTime": "HH:MM GMT+X", // Timezone information is illustrative
      "round": "Preliminary Round", // e.g., "Preliminary Round", "Quarterfinals", "Semifinals", "Bronze Medal Game", "Gold Medal Game"
      "group": "Group A", // Nullable, typically for Preliminary Round
      "team1": "SUI", // 3-letter IIHF country code
      "team2": "NOR", // 3-letter IIHF country code
      "location": "City Name",
      "venue": "Arena Name"
      // "fullGameDescription" is ignored by the loader but can be present in the JSON
    }
    // ... more game objects
  ],
  "notes": [ // Optional metadata
    "Note 1: Some rule specific to the tournament"
  ]
}
```
The essential fields for loading are `gameNumber`, `date`, `startTime`, `round`, `team1`, `team2`, `location`, and `venue`. `group` is used for preliminary rounds.

## Contributing

1. Fork the repository.
2. Create a new branch for your feature or bug fix (`git checkout -b feature/your-feature-name`).
3. Make your changes and commit them (`git commit -am 'Add some feature'`).
4. Push to the branch (`git push origin feature/your-feature-name`).
5. Create a new Pull Request.

## License

This project is unlicensed (or specify your license, e.g., MIT License).

## Support

For issues, questions, or feature requests, please open an issue in the GitHub repository.

## Neue Backend-Routen für Semifinal Seeding (zu implementieren)

Die folgenden Routen müssen in `routes/year_routes.py` hinzugefügt werden:

### 1. Route zum Abrufen des aktuellen Seedings
```python
@year_bp.route('/<int:year_id>/semifinal_seeding', methods=['GET'])
def get_semifinal_seeding(year_id):
    """
    Gibt das aktuelle Semifinal-Seeding zurück.
    
    Returns:
        JSON: {
            "success": bool,
            "seeding": {
                "seed1": "team_name",
                "seed2": "team_name", 
                "seed3": "team_name",
                "seed4": "team_name"
            }
        }
    """
    try:
        year_obj = ChampionshipYear.query.get_or_404(year_id)
        
        # Logik zum Ermitteln des aktuellen Seedings
        # Basiert auf der bestehenden Semifinal-Logik in year_view()
        # Die Q1-Q4 Mappings aus dem playoff_team_map verwenden
        
        # Beispiel-Implementation:
        # 1. Alle QF-Gewinner sammeln
        # 2. Nach Gruppenrang, Punkte, Tordifferenz, Tore sortieren
        # 3. Seeding zuweisen: Q1=bester, Q2=viertbester, Q3=zweitbester, Q4=drittbester
        
        seeding = {
            "seed1": "Team1",  # Ersetzen durch echte Logik
            "seed2": "Team2", 
            "seed3": "Team3",
            "seed4": "Team4"
        }
        
        return jsonify({
            "success": True,
            "seeding": seeding
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Fehler beim Abrufen des Seedings: {str(e)}"
        }), 500
```

### 2. Route zum Anpassen des Seedings
```python
@year_bp.route('/<int:year_id>/adjust_semifinal_seeding', methods=['POST'])
def adjust_semifinal_seeding(year_id):
    """
    Passt das Semifinal-Seeding manuell an.
    
    Expected JSON payload:
        {
            "seed1": "team_name",
            "seed2": "team_name",
            "seed3": "team_name", 
            "seed4": "team_name"
        }
    """
    try:
        year_obj = ChampionshipYear.query.get_or_404(year_id)
        data = request.get_json()
        
        # Validierung
        required_seeds = ['seed1', 'seed2', 'seed3', 'seed4']
        for seed in required_seeds:
            if seed not in data or not data[seed]:
                return jsonify({
                    "success": False,
                    "message": f"Fehlendes oder ungültiges Seeding für {seed}"
                }), 400
        
        # Prüfung auf Duplikate
        teams = [data[seed] for seed in required_seeds]
        if len(set(teams)) != 4:
            return jsonify({
                "success": False,
                "message": "Jedes Team kann nur einmal als Seed verwendet werden"
            }), 400
            
        # Semifinal-Spiele finden (normalerweise Spiele 61 und 62)
        sf_games = Game.query.filter_by(
            year_id=year_id,
            round='Semifinals'
        ).order_by(Game.game_number).all()
        
        if len(sf_games) < 2:
            return jsonify({
                "success": False,
                "message": "Nicht genügend Semifinal-Spiele gefunden"
            }), 400
            
        # Team-Paarungen nach Standard-Seeding: 1vs4, 2vs3
        sf_game_1 = sf_games[0]  # 1 vs 4
        sf_game_2 = sf_games[1]  # 2 vs 3
        
        # Spiel 1: Seed 1 vs Seed 4
        sf_game_1.team1_code = data['seed1']
        sf_game_1.team2_code = data['seed4']
        
        # Spiel 2: Seed 2 vs Seed 3  
        sf_game_2.team1_code = data['seed2']
        sf_game_2.team2_code = data['seed3']
        
        db.session.commit()
        
        # Optional: Log der Änderung
        # SeedingAdjustment Tabelle erstellen um Änderungen zu tracken
        
        return jsonify({
            "success": True,
            "message": "Semifinal-Seeding wurde erfolgreich angepasst",
            "new_pairings": {
                "game1": f"{data['seed1']} vs {data['seed4']}",
                "game2": f"{data['seed2']} vs {data['seed3']}"
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": f"Fehler beim Anpassen des Seedings: {str(e)}"
        }), 500
```

### 3. Optionale Tabelle für Seeding-History
```python
# In models.py hinzufügen:
class SeedingAdjustment(db.Model):
    __tablename__ = 'seeding_adjustments'
    
    id = db.Column(db.Integer, primary_key=True)
    year_id = db.Column(db.Integer, db.ForeignKey('championship_years.id'), nullable=False)
    round_name = db.Column(db.String(50), nullable=False)  # 'Semifinals'
    original_seeding = db.Column(db.JSON)  # Original Q1-Q4 mapping
    adjusted_seeding = db.Column(db.JSON)  # New Q1-Q4 mapping
    adjustment_reason = db.Column(db.Text)  # Optional reason
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    year = db.relationship('ChampionshipYear', backref='seeding_adjustments')
```

## Integration in bestehende Logik

In der `year_view()` Funktion müssen Sie prüfen, ob manuelle Seeding-Anpassungen vorliegen:

```python
# In year_view() nach der Standard-Seeding-Logik:

# Prüfung auf manuelle Seeding-Anpassung
manual_seeding = SeedingAdjustment.query.filter_by(
    year_id=year_id,
    round_name='Semifinals'
).order_by(SeedingAdjustment.created_at.desc()).first()

if manual_seeding:
    # Manuelle Anpassung überschreibt automatisches Seeding
    adjusted_seeding = manual_seeding.adjusted_seeding
    playoff_team_map['Q1'] = adjusted_seeding['seed1']
    playoff_team_map['Q2'] = adjusted_seeding['seed2'] 
    playoff_team_map['Q3'] = adjusted_seeding['seed3']
    playoff_team_map['Q4'] = adjusted_seeding['seed4']
    
    # Semifinal-Spiele entsprechend anpassen
    # ... (siehe adjust_semifinal_seeding Route)
``` 