TEAM_ISO_CODES = {
    "AUT": "at", "FIN": "fi", "SUI": "ch", "CZE": "cz",
    "SWE": "se", "SVK": "sk", "DEN": "dk", "USA": "us",
    "SLO": "si", "CAN": "ca", "NOR": "no", "KAZ": "kz",
    "GER": "de", "HUN": "hu", "FRA": "fr", "LAT": "lv",
    "ITA": "it", "GBR": "gb", "POL": "pl", "RUS": "ru",
    "BLR": "by", "KOR": "kr", "JAP": "jp", "UKR": "ua",
    "ROM": "ro", "EST": "ee", "CHN": "cn",
    "QF": None, "SF": None, "L(SF)": None, "W(SF)": None
}

# Team names mapping (reverse lookup from ISO codes to team names)
TEAM_NAMES = {v: k for k, v in TEAM_ISO_CODES.items() if v is not None}

# Tournament round definitions
PRELIM_ROUNDS = ["Preliminary Round", "Group Stage", "Round Robin"]
PLAYOFF_ROUNDS = ["Quarterfinals", "Quarterfinal", "Semifinals", "Semifinal", "Final", "Bronze Medal Game", "Gold Medal Game", "Playoff"]

# Hauptrunden-Spiele Konstanten
MAX_PRELIM_GAMES_PER_TEAM = 7  # Maximale Anzahl der Hauptrundenspiele pro Team

# Define penalty choices
PENALTY_TYPES_CHOICES = ["2 Min", "2+2 Min", "5 Min Disziplinar", "5 Min + Spieldauer", "10 Min Disziplinar"]
PENALTY_REASONS_CHOICES = [
    "Bandencheck",
    "Behinderung",
    "Beinstellen",
    "Check von hinten",
    "Check gegen Nackenbereich",
    "Cross Checking",
    "Ellbogencheck",
    "Haken",
    "Halten",
    "Hoher Stock",
    "Kopfstoß",
    "Spielverzögerung",
    "Stockschlag",
    "Torhüterbehinderung",
    "übertriebene Härte",
    "unerlaubter Körperangriff",
    "unsportliches Verhalten",
    "zu viele Spieler auf dem Eis"
]

PIM_MAP = {
    "2 Min": 2,
    "2+2 Min": 4,
    "5 Min Disziplinar": 5,
    "5 Min + Spieldauer": 5, # The 20 min for game misconduct is often tracked separately or implied
    "10 Min Disziplinar": 10,
}

# Penalty types that result in powerplay opportunities
POWERPLAY_PENALTY_TYPES = ["2 Min", "2+2 Min", "5 Min + Spieldauer"]



GOAL_TYPE_DISPLAY_MAP = {
    "REG": "EQ", 
    "PP": "PP", 
    "SH": "SH", 
    "PS": "PS"
}

# Playoff-Spielnummern Konstanten
QUARTERFINAL_1 = 57  # Viertelfinale 1
QUARTERFINAL_2 = 58  # Viertelfinale 2
QUARTERFINAL_3 = 59  # Viertelfinale 3
QUARTERFINAL_4 = 60  # Viertelfinale 4
SEMIFINAL_1 = 61     # Halbfinale 1
SEMIFINAL_2 = 62     # Halbfinale 2
BRONZE_MEDAL = 63    # Spiel um Platz 3 (Bronze)
GOLD_MEDAL = 64      # Finale (Gold)

# Gruppierte Spielnummern für einfachere Verwendung
QUARTERFINAL_GAME_NUMBERS = [QUARTERFINAL_1, QUARTERFINAL_2, QUARTERFINAL_3, QUARTERFINAL_4]
SEMIFINAL_GAME_NUMBERS = [SEMIFINAL_1, SEMIFINAL_2]
MEDAL_GAME_NUMBERS = [BRONZE_MEDAL, GOLD_MEDAL]
ALL_PLAYOFF_GAME_NUMBERS = QUARTERFINAL_GAME_NUMBERS + SEMIFINAL_GAME_NUMBERS + MEDAL_GAME_NUMBERS

# Zeit-Konstanten (in Sekunden)
PERIOD_1_END = 1200  # Ende 1. Drittel (20 Minuten)
PERIOD_2_END = 2400  # Ende 2. Drittel (40 Minuten)
PERIOD_3_END = 3600  # Ende 3. Drittel (60 Minuten)
SECONDS_PER_MINUTE = 60  # Sekunden pro Minute
REGULATION_TIME_SECONDS = 3600  # 60 Minuten reguläre Spielzeit
OVERTIME_DURATION_SECONDS = 300  # 5 Minuten Verlängerung
PENALTY_SHOT_TIME_SECONDS = 0  # Penalty-Schießen hat keine feste Zeit

# Anzeige-Limit Konstanten
TOP_3_DISPLAY = 3    # Top 3 Spieler/Teams anzeigen
TOP_5_DISPLAY = 5    # Top 5 Spieler/Teams anzeigen  
MAX_RECORDS = 10     # Maximale Anzahl von Datensätzen für Rekorde 