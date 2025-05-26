import os
from flask import Flask

from models import db

# Import blueprints
from routes.main_routes import main_bp
from routes.year_routes import year_bp

# --- Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'fixtures')

def create_app():
    app = Flask(__name__)
    app.jinja_env.add_extension('jinja2.ext.do')
    app.config['SECRET_KEY'] = 'your_secret_key_please_change_this' # TODO: Make this configurable
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "data", "iihf_data.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['BASE_DIR'] = BASE_DIR # Make BASE_DIR available in app.config for blueprints

    db.init_app(app)

    # Register Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(year_bp)

    # --- CLI commands for DB ---
    @app.cli.command("init-db")
    def init_db_command():
        """Initializes the database and required directories."""
        # Ensure UPLOAD_FOLDER exists
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            print(f"Created fixture upload directory: {app.config['UPLOAD_FOLDER']}")
        
        # Initialize database tables
        with app.app_context(): # Ensure operations are within app context
            _init_db_tables() # Call helper to create tables
        print("Initialized the database tables.")

    def _init_db_tables():
        """Helper function to create database tables and directories."""
        # Create database directory if it doesn't exist
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            print(f"Created database directory: {db_dir}")
        db.create_all()
        print("Database tables created.")

    # Initialize DB and UPLOAD_FOLDER on app creation as well for convenience during development
    # For production, `flask init-db` is preferred before first run.
    with app.app_context():
        _init_db_tables() 
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            print(f"Created fixture upload directory (on app start): {app.config['UPLOAD_FOLDER']}")

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
