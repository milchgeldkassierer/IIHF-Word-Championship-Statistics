"""
Services Modul für IIHF Word Championship Statistics
Exportiert alle Service-Klassen für die Geschäftslogik
"""

# Nur StandingsCalculator importieren, um zirkuläre Imports zu vermeiden
from .standings_calculator import StandingsCalculator

__all__ = [
    'StandingsCalculator'
]