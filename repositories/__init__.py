"""
Repository Layer für IIHF World Championship Statistics
Abstrahiert Datenbankzugriff und stellt eine saubere Schnittstelle zur Verfügung
"""

from .base import BaseRepository
from .game_repository import GameRepository

__all__ = ['BaseRepository', 'GameRepository']