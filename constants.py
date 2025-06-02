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
PLAYOFF_ROUNDS = ["Quarterfinals", "Semifinals", "Final", "Bronze Medal Game", "Gold Medal Game", "Playoff"]

# Game number mappings by year for quarterfinals and semifinals
# Based on fixture files: QF=57-60, SF=61-62, Bronze=63, Final=64
QF_GAME_NUMBERS_BY_YEAR = {
    # Default game numbers for quarterfinals (games 57-60)
    1: [57, 58, 59, 60],  # 2019
    2: [57, 58, 59, 60],  # 2021  
    3: [57, 58, 59, 60],  # 2023
    4: [57, 58, 59, 60],  # 2025
}

SF_GAME_NUMBERS_BY_YEAR = {
    # Default game numbers for semifinals (games 61-62)
    1: [61, 62],  # 2019
    2: [61, 62],  # 2021
    3: [61, 62],  # 2023
    4: [61, 62],  # 2025
}

FINAL_BRONZE_GAME_NUMBERS_BY_YEAR = {
    # Default game numbers for final and bronze medal games (games 63-64)
    1: [63, 64],  # 2019 - Bronze=63, Final=64
    2: [63, 64],  # 2021
    3: [63, 64],  # 2023
    4: [63, 64],  # 2025
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