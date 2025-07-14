"""
Fixture path resolution utilities.
"""
import os
from flask import current_app


def resolve_fixture_path(relative_path):
    """
    Converts a relative fixture path to an absolute path.
    For files starting with 'fixtures/', looks in BASE_DIR/fixtures/
    For other files, looks in UPLOAD_FOLDER/
    
    Args:
        relative_path (str): The relative path to resolve
        
    Returns:
        str: The absolute path, or None if relative_path is empty
    """
    if not relative_path:
        return None
    
    if relative_path.startswith('fixtures/'):
        filename = relative_path[9:]
        absolute_path = os.path.join(current_app.config['BASE_DIR'], 'fixtures', filename)
    else:
        absolute_path = os.path.join(current_app.config['UPLOAD_FOLDER'], relative_path)
    
    return absolute_path