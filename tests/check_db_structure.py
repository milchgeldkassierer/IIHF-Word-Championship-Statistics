#!/usr/bin/env python3
"""Check database structure."""

import sqlite3
import os

# Try different database files
db_files = [
    'iihf_stats.db',
    'instance/iihf_stats.db', 
    'instance/hockey_stats.db',
    'data/iihf_data.db',
    'data/iihf-championships.db'
]

for db_file in db_files:
    if os.path.exists(db_file):
        print(f"\n{'='*60}")
        print(f"Database: {db_file}")
        print('='*60)
        
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            print(f"Tables found: {len(tables)}")
            for table in tables:
                print(f"  - {table[0]}")
                
                # Get row count for key tables
                if table[0] in ['games', 'game', 'Game', 'championship_games']:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
                        count = cursor.fetchone()[0]
                        print(f"    Row count: {count}")
                        
                        # Get column info
                        cursor.execute(f"PRAGMA table_info({table[0]})")
                        columns = cursor.fetchall()
                        print(f"    Columns: {', '.join([col[1] for col in columns[:5]])}...")
                    except Exception as e:
                        print(f"    Error: {e}")
            
            conn.close()
            
        except Exception as e:
            print(f"Error opening database: {e}")
    else:
        print(f"\nDatabase not found: {db_file}")