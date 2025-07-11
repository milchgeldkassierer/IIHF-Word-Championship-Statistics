#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('data/iihf_data.db')
cursor = conn.cursor()

print('All 2025 playoff games:')
query = """SELECT g.game_number, g.date, g.team1_code, g.team2_code, g.team1_score, g.team2_score, g.round 
           FROM game g 
           JOIN championship_year cy ON g.year_id = cy.id 
           WHERE cy.year = 2025 AND g.round != 'Preliminary Round'
           ORDER BY g.game_number"""

cursor.execute(query)
playoff_games = cursor.fetchall()

for game in playoff_games:
    game_num, date, team1, team2, score1, score2, round_type = game
    print(f'Game #{game_num}: {team1} {score1}-{score2} {team2} ({round_type}) on {date}')

print()
print('Checking semifinals specifically:')
semifinals = [g for g in playoff_games if g[6] == 'Semifinals']
for game in semifinals:
    game_num, date, team1, team2, score1, score2, round_type = game
    print(f'Game #{game_num}: {team1} {score1}-{score2} {team2} ({round_type}) on {date}')

print(f'\nTotal playoff games: {len(playoff_games)}')
print(f'Semifinals games: {len(semifinals)}')

conn.close()