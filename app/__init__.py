"""
App package for IIHF World Championship Statistics
Contains the service layer and repository modules
"""

# This file makes the 'app' directory a Python package
# Required for imports like 'from app.services import ...'

__version__ = "1.0.0"

# Import create_app from the main app.py for compatibility
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from app_main import create_app
except ImportError:
    # Fallback to reading create_app from app.py
    import importlib.util
    spec = importlib.util.spec_from_file_location("app_main", os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py"))
    app_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_main)
    create_app = app_main.create_app

__all__ = ['create_app']