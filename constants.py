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

# Tournament round definitions
PRELIM_ROUNDS = ["Preliminary Round", "Group Stage", "Round Robin"]
PLAYOFF_ROUNDS = ["Quarterfinals", "Semifinals", "Final", "Bronze Medal Game", "Gold Medal Game", "Playoff"]

# Hauptrunden-Spiele Konstanten
MAX_PRELIM_GAMES_PER_TEAM = 7  # Maximale Anzahl der Hauptrundenspiele pro Team

# Define penalty choices
PENALTY_TYPES_CHOICES = ["2 Min", "2+2 Min", "5 Min + Spieldauer", "10 Min Disziplinar", "Spieldauer Disziplinar"]
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
    "5 Min + Spieldauer": 5, # The 20 min for game misconduct is often tracked separately or implied
    "10 Min Disziplinar": 10,
    "Spieldauer Disziplinar": 20 # This is a common equivalent for a game misconduct
}

# Penalty types that result in powerplay opportunities
POWERPLAY_PENALTY_TYPES = ["2 Min", "2+2 Min", "5 Min + Spieldauer"]



GOAL_TYPE_DISPLAY_MAP = {
    "REG": "EQ", 
    "PP": "PP", 
    "SH": "SH", 
    "PS": "PS"
} 