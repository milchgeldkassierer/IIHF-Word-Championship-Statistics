from flask import Blueprint

# Create the blueprint
year_bp = Blueprint('year_bp', __name__, url_prefix='/year')

# Import all route functions from views.py (they will be split later)
# This ensures all routes are registered with the blueprint
from .views import (
    year_view, get_stats_data, team_vs_team_view
)
from .players import add_player
from .goals import add_goal, delete_goal
from .penalties import add_penalty, delete_penalty
from .seeding import get_semifinal_seeding, save_semifinal_seeding, reset_semifinal_seeding
from .games import game_stats_view, add_overrule, remove_overrule, add_sog