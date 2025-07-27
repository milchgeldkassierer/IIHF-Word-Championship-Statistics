"""
Static playoff structure mapping for IIHF tournaments
Defines the placeholder mappings for all playoff stages
"""

# Static playoff team mapping structure
# This defines which placeholders are used for each playoff stage
playoff_team_map = {
    'Quarter-Finals': {
        'QF1': ['A1', 'B2'],
        'QF2': ['B1', 'A2'],
        'QF3': ['C1', 'D2'],
        'QF4': ['D1', 'C2']
    },
    'Semi-Finals': {
        'SF1': ['W(QF1)', 'W(QF3)'],  # Winners of QF1 vs QF3
        'SF2': ['W(QF2)', 'W(QF4)']   # Winners of QF2 vs QF4
    },
    'Bronze Medal Game': {
        'Bronze': ['L(SF1)', 'L(SF2)']  # Losers of both semi-finals
    },
    'Gold Medal Game': {
        'Gold': ['W(SF1)', 'W(SF2)']    # Winners of both semi-finals
    }
}

# Game number mappings (can be overridden by fixture files)
default_game_numbers = {
    'qf': [57, 58, 59, 60],
    'sf': [61, 62],
    'bronze': 63,
    'gold': 64
}