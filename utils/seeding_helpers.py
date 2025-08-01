import json
from flask import current_app
from models import GameOverrule


def get_custom_seeding_from_db(year_id):
    """
    Lädt benutzerdefiniertes Seeding aus der Datenbank.
    
    Args:
        year_id (int): Championship year ID
        
    Returns:
        dict or None: Seeding configuration or None if not found
    """
    try:
        # Verwende GameOverrule Tabelle mit spezieller game_id für Semifinal Seeding
        special_game_id = -year_id  # Negative year_id für semifinal seeding
        
        overrule = GameOverrule.query.filter_by(game_id=special_game_id).first()
        if overrule and overrule.reason:
            try:
                data = json.loads(overrule.reason)
                # Handle both old format (just seeding) and new format (seeding + reason)
                if isinstance(data, dict) and 'seeding' in data:
                    return data['seeding']  # New format - return just the seeding part
                else:
                    return data  # Old format (backward compatibility)
            except:
                return None
        return None
    except Exception as e:
        current_app.logger.error(f"Error loading custom seeding: {str(e)}")
        return None