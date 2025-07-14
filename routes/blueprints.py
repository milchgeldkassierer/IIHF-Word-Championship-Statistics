from flask import Blueprint

# Main blueprint for core routes
main_bp = Blueprint('main_bp', __name__)

# Import route functions from modular structure to register them with the blueprint
# These imports will register the routes with main_bp
import routes.tournament.management
import routes.standings.all_time
import routes.standings.medals  
import routes.players.stats
import routes.players.management
import routes.api.team_stats