TEAM_ISO_CODES = {
    "AUT": "at", "FIN": "fi", "SUI": "ch", "CZE": "cz",
    "SWE": "se", "SVK": "sk", "DEN": "dk", "USA": "us",
    "SLO": "si", "CAN": "ca", "NOR": "no", "KAZ": "kz",
    "GER": "de", "HUN": "hu", "FRA": "fr", "LAT": "lv",
    "ITA": "it", "GBR": "gb", "POL": "pl",
    "QF": None, "SF": None, "L(SF)": None, "W(SF)": None
}

# Tournament round definitions
PRELIM_ROUNDS = ["Preliminary Round", "Group Stage", "Round Robin"]
PLAYOFF_ROUNDS = ["Quarterfinal", "Semifinal", "Final", "Bronze Medal Game", "Playoff"]

# Game number mappings by year for quarterfinals and semifinals
QF_GAME_NUMBERS_BY_YEAR = {
    # Add specific game numbers for quarterfinals by year as needed
    # Example: 2023: [45, 46, 47, 48]
}

SF_GAME_NUMBERS_BY_YEAR = {
    # Add specific game numbers for semifinals by year as needed
    # Example: 2023: [49, 50]
}

FINAL_BRONZE_GAME_NUMBERS_BY_YEAR = {
    # Add specific game numbers for final and bronze medal games by year as needed
    # Example: 2023: [51, 52]
}

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
    "Halten des Stocks",
    "Hoher Stock",
    "Kopfstoß",
    "Schiedsrichterkritik",
    "Stockschlag",
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

OPP_COUNT_MAP = {
    "2 Min": 1, 
    "2+2 Min": 2, 
    "5 Min + Spieldauer": 1
}

GOAL_TYPE_DISPLAY_MAP = {
    "REG": "EQ", 
    "PP": "PP", 
    "SH": "SH", 
    "PS": "PS"
} 