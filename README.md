# Ice Hockey Tournament Manager

A Flask-based web application for managing ice hockey tournament data, including fixtures, scores, goals, and player statistics. The application supports multiple tournament years and provides features for tracking games, goals, and player performance.

## Features

- Manage multiple tournament years
- Upload and manage tournament fixtures
- Track game scores and results
- Record goals with detailed information (scorer, assists, time, type)
- Manage player rosters
- View tournament standings
- Track player statistics (goals, assists, points)
- Support for different game types (regular time, overtime, shootout)
- Team flag display using country codes

## Prerequisites

- Python 3.7 or higher
- pip (Python package manager)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd table_calc
```

2. Create and activate a virtual environment (recommended):
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
```bash
flask init-db
```

## Running the Application

1. Start the Flask development server:
```bash
flask run
```

2. Open your web browser and navigate to:
```
http://localhost:5000
```

## Project Structure

- `app.py`: Main application file containing routes and database models
- `templates/`: HTML templates for the web interface
- `data/`: Directory for storing tournament data
  - `fixtures/`: JSON files containing tournament fixtures
  - `iihf_data.db`: SQLite database file

## Database Models

- `ChampionshipYear`: Represents a tournament year
- `Game`: Stores game information and results
- `Player`: Manages player information
- `Goal`: Records goal details including scorer and assists

## Usage

1. **Adding a New Tournament Year**
   - Navigate to the home page
   - Enter the year and upload a fixture file (JSON format)
   - The system will process and store the tournament schedule

2. **Managing Games**
   - View games by tournament year
   - Enter game scores and results
   - Record goals with detailed information
   - Track player statistics

3. **Player Management**
   - Add players to teams
   - View player statistics
   - Track goals and assists

## Data Format

The application expects fixture files in JSON format with the following structure:
```json
{
  "schedule": [
    {
      "gameNumber": 1,
      "date": "YYYY-MM-DD",
      "startTime": "HH:MM",
      "round": "Preliminary Round",
      "group": "Group A",
      "team1": "TEAM1",
      "team2": "TEAM2",
      "location": "City",
      "venue": "Arena"
    }
  ]
}
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Add your license information here]

## Support

[Add support information or contact details here] 