# IIHF World Championship Constants - New Architecture
# This file contains the new constants to be added to constants.py
# Designed to replace magic numbers throughout the codebase (Issue #8)

from enum import IntEnum, Enum

# ============================================================================
# GAME NUMBERS - Official IIHF tournament game numbering
# ============================================================================

class GameNumber(IntEnum):
    """Official IIHF game numbering for playoff rounds
    
    Game numbers 57-64 are standardized across tournaments:
    - 57-60: Quarterfinals
    - 61-62: Semifinals  
    - 63: Bronze Medal Game
    - 64: Gold Medal Game
    """
    # Viertelfinals (57-60)
    QUARTERFINAL_1 = 57
    QUARTERFINAL_2 = 58
    QUARTERFINAL_3 = 59
    QUARTERFINAL_4 = 60
    
    # Halbfinals (61-62)
    SEMIFINAL_1 = 61
    SEMIFINAL_2 = 62
    
    # Medallenspiele
    BRONZE_MEDAL = 63
    GOLD_MEDAL = 64

# Gruppierte Konstanten für Iteration
QUARTERFINAL_GAME_NUMBERS = [
    GameNumber.QUARTERFINAL_1,
    GameNumber.QUARTERFINAL_2,
    GameNumber.QUARTERFINAL_3,
    GameNumber.QUARTERFINAL_4
]

SEMIFINAL_GAME_NUMBERS = [
    GameNumber.SEMIFINAL_1,
    GameNumber.SEMIFINAL_2
]

MEDAL_GAME_NUMBERS = [
    GameNumber.BRONZE_MEDAL,
    GameNumber.GOLD_MEDAL
]

# Alle Playoff-Spielnummern
ALL_PLAYOFF_GAME_NUMBERS = QUARTERFINAL_GAME_NUMBERS + SEMIFINAL_GAME_NUMBERS + MEDAL_GAME_NUMBERS

# ============================================================================
# TOURNAMENT STRUCTURE - Phases and game types
# ============================================================================

class TournamentPhase(Enum):
    """Turnierphasen"""
    PRELIMINARY = "preliminary"      # Vorrunde
    QUARTERFINALS = "quarterfinals" # Viertelfinals
    SEMIFINALS = "semifinals"       # Halbfinals
    BRONZE_MEDAL_GAME = "bronze_medal" # Spiel um Platz 3
    GOLD_MEDAL_GAME = "gold_medal"     # Finale

class GameType(Enum):
    """Spieltypen im Turnier"""
    GROUP_STAGE = "group_stage"     # Gruppenphase
    ROUND_ROBIN = "round_robin"     # Jeder gegen jeden
    QUARTERFINAL = "quarterfinal"   # Viertelfinale
    SEMIFINAL = "semifinal"         # Halbfinale
    BRONZE_MEDAL = "bronze_medal"   # Bronzemedaillenspiel
    GOLD_MEDAL = "gold_medal"       # Goldmedaillenspiel
    PLACEMENT = "placement"         # Platzierungsspiele

# ============================================================================
# TIME CONSTANTS - Period boundaries and display
# ============================================================================

class PeriodBoundary(IntEnum):
    """Zeitgrenzen für Drittelerkennung (in Sekunden)"""
    FIRST_PERIOD_END = 1200   # Ende 1. Drittel (20:00)
    SECOND_PERIOD_END = 2400  # Ende 2. Drittel (40:00)
    THIRD_PERIOD_END = 3600   # Ende reguläre Spielzeit (60:00)

# Hilfskonstanten für Drittelerkennung
PERIOD_BOUNDARIES = [
    PeriodBoundary.FIRST_PERIOD_END,
    PeriodBoundary.SECOND_PERIOD_END,
    PeriodBoundary.THIRD_PERIOD_END
]

# Drittel-Anzeigenamen
PERIOD_DISPLAY_NAMES = {
    1: "1st Period",
    2: "2nd Period", 
    3: "3rd Period",
    4: "OT",         # Overtime / Verlängerung
    5: "SO"          # Shootout / Penaltyschießen
}

# ============================================================================
# DISPLAY LIMITS - Standard limits for rankings and records
# ============================================================================

class DisplayLimit(IntEnum):
    """Standard-Anzeigelimits für Rankings und Rekorde"""
    TOP_3 = 3       # Top 3 für Podium/Medaillenpositionen
    TOP_5 = 5       # Top 5 für erweiterte Rankings
    TOP_10 = 10     # Top 10 für umfassende Listen
    TOP_20 = 20     # Top 20 für detaillierte Statistiken
    TOP_50 = 50     # Top 50 für historische Übersichten
    
    # Spezielle Limits
    RECENT_GAMES = 5          # Anzahl der letzten Spiele
    PLAYOFF_TEAMS = 8         # Teams in den Playoffs
    GROUP_SIZE = 8            # Standard-Gruppengröße
    HEAD_TO_HEAD_HISTORY = 10 # Letzte direkte Begegnungen

# ============================================================================
# DATABASE CONSTRAINTS - Field sizes and validation limits
# ============================================================================

class FieldSize(IntEnum):
    """Datenbankfeld-Größenlimits"""
    # String-Feldgrößen
    TEAM_CODE = 3             # 3-Buchstaben-Ländercodes (ISO)
    PLAYER_NAME = 100         # Maximale Spielernamenlänge
    TEAM_NAME = 50           # Maximale Teamnamenlänge
    VENUE_NAME = 100         # Maximale Veranstaltungsortlänge
    CITY_NAME = 50           # Maximale Stadtnamenlänge
    
    # Numerische Limits für Validierung
    MAX_GOALS_PER_GAME = 20       # Vernünftiges Maximum für Validierung
    MAX_PENALTY_MINUTES = 200     # Max PIM pro Spiel für Validierung
    MAX_SHOTS_PER_GAME = 100      # Max Schüsse für Validierung
    MAX_SAVES_PER_GAME = 80       # Max Paraden für Validierung
    
    # Textfeldgrößen
    DESCRIPTION_SHORT = 255   # Kurzbeschreibungen
    DESCRIPTION_LONG = 1000   # Lange Beschreibungen
    NOTES_FIELD = 2000       # Spielnotizen, Kommentare

# ============================================================================
# TOURNAMENT CONFIGURATION - Configurable tournament parameters
# ============================================================================

class TournamentConfig:
    """Konfigurierbare Konstanten, die je nach Turnier variieren können"""
    # Standard-Spielnummern (können durch Fixtures überschrieben werden)
    DEFAULT_QF_GAMES = list(QUARTERFINAL_GAME_NUMBERS)
    DEFAULT_SF_GAMES = list(SEMIFINAL_GAME_NUMBERS)
    DEFAULT_MEDAL_GAMES = list(MEDAL_GAME_NUMBERS)
    
    # Turnierformat
    GROUPS_COUNT = 2              # Anzahl der Gruppen (A, B)
    TEAMS_PER_GROUP = 8           # Teams in jeder Gruppe
    TOTAL_TEAMS = 16              # Gesamtzahl der Teams
    GAMES_PER_TEAM_PRELIM = 7     # Spiele pro Team in der Vorrunde
    
    # Playoff-Konfiguration
    TEAMS_ADVANCING_PER_GROUP = 4  # Top 4 aus jeder Gruppe
    TOTAL_PLAYOFF_TEAMS = 8        # Gesamt-Playoff-Teams
    PLAYOFF_ROUNDS = 4             # QF, SF, Bronze, Gold

# ============================================================================
# VALIDATION HELPERS - Functions to validate against constants
# ============================================================================

def is_playoff_game(game_number: int) -> bool:
    """Prüft, ob eine Spielnummer ein Playoff-Spiel ist"""
    return game_number in ALL_PLAYOFF_GAME_NUMBERS

def is_medal_game(game_number: int) -> bool:
    """Prüft, ob eine Spielnummer ein Medaillenspiel ist"""
    return game_number in MEDAL_GAME_NUMBERS

def get_game_phase(game_number: int) -> TournamentPhase:
    """Gibt die Turnierphase für eine Spielnummer zurück"""
    if game_number in QUARTERFINAL_GAME_NUMBERS:
        return TournamentPhase.QUARTERFINALS
    elif game_number in SEMIFINAL_GAME_NUMBERS:
        return TournamentPhase.SEMIFINALS
    elif game_number == GameNumber.BRONZE_MEDAL:
        return TournamentPhase.BRONZE_MEDAL_GAME
    elif game_number == GameNumber.GOLD_MEDAL:
        return TournamentPhase.GOLD_MEDAL_GAME
    else:
        return TournamentPhase.PRELIMINARY

def get_period_from_seconds(seconds: int) -> int:
    """Bestimmt das Drittel basierend auf der Spielzeit in Sekunden"""
    if seconds <= PeriodBoundary.FIRST_PERIOD_END:
        return 1
    elif seconds <= PeriodBoundary.SECOND_PERIOD_END:
        return 2
    elif seconds <= PeriodBoundary.THIRD_PERIOD_END:
        return 3
    else:
        return 4  # Overtime/Shootout