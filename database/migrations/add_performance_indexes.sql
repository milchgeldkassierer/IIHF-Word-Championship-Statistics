-- Performance-Optimierung: Datenbank-Indizes für IIHF World Championship Statistics
-- Diese Indizes verbessern die Query-Performance erheblich

-- =============================================================================
-- GAME TABLE INDEXES
-- =============================================================================

-- Composite Index für Standings-Queries (häufigste Query)
-- Deckt ab: year_id + round + group für Vorrunden-Standings
CREATE INDEX IF NOT EXISTS idx_games_year_round_group 
ON games(year_id, round, group) 
WHERE team1_score IS NOT NULL AND team2_score IS NOT NULL;

-- Index für Team-spezifische Queries
CREATE INDEX IF NOT EXISTS idx_games_year_team1 
ON games(year_id, team1_code);

CREATE INDEX IF NOT EXISTS idx_games_year_team2 
ON games(year_id, team2_code);

-- Covering Index für Playoff-Queries
CREATE INDEX IF NOT EXISTS idx_games_year_round_game_number 
ON games(year_id, round, game_number)
INCLUDE (team1_code, team2_code, team1_score, team2_score, result_type);

-- Index für Result-Type Filterung
CREATE INDEX IF NOT EXISTS idx_games_result_type 
ON games(result_type) 
WHERE result_type IS NOT NULL;

-- =============================================================================
-- GOALS TABLE INDEXES
-- =============================================================================

-- Composite Index für Spieler-Statistiken
CREATE INDEX IF NOT EXISTS idx_goals_player_game 
ON goals(player_id, game_id);

-- Index für Team-basierte Goal-Queries
CREATE INDEX IF NOT EXISTS idx_goals_team_game 
ON goals(team_code, game_id);

-- Index für Zeitbasierte Queries
CREATE INDEX IF NOT EXISTS idx_goals_game_period_time 
ON goals(game_id, period, time);

-- =============================================================================
-- PENALTIES TABLE INDEXES
-- =============================================================================

-- Index für Spieler-Strafzeiten
CREATE INDEX IF NOT EXISTS idx_penalties_player_game 
ON penalties(player_id, game_id);

-- Index für Team-Strafzeiten
CREATE INDEX IF NOT EXISTS idx_penalties_team_game 
ON penalties(team_code, game_id);

-- =============================================================================
-- PLAYERS TABLE INDEXES
-- =============================================================================

-- Index für Team-Roster Queries
CREATE INDEX IF NOT EXISTS idx_players_team 
ON players(team_code);

-- Index für Spieler-Suche nach Name
CREATE INDEX IF NOT EXISTS idx_players_name 
ON players(name);

-- =============================================================================
-- CHAMPIONSHIP_YEARS TABLE INDEXES
-- =============================================================================

-- Index für Jahr-Sortierung
CREATE INDEX IF NOT EXISTS idx_championship_years_year 
ON championship_years(year);

-- =============================================================================
-- MATERIALIZED VIEW für Standings (Optional - für extreme Performance)
-- =============================================================================

-- Diese View berechnet Standings vorab und wird bei Spiel-Updates aktualisiert
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_group_standings AS
WITH team_stats AS (
    -- Team1 Statistiken
    SELECT 
        g.year_id,
        g.group,
        g.team1_code as team_code,
        COUNT(*) as games_played,
        SUM(g.team1_score) as goals_for,
        SUM(g.team2_score) as goals_against,
        SUM(g.team1_points) as points,
        SUM(CASE WHEN g.result_type = 'REG' AND g.team1_score > g.team2_score THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN g.result_type = 'OT' AND g.team1_score > g.team2_score THEN 1 ELSE 0 END) as ot_wins,
        SUM(CASE WHEN g.result_type = 'SO' AND g.team1_score > g.team2_score THEN 1 ELSE 0 END) as so_wins,
        SUM(CASE WHEN g.result_type = 'REG' AND g.team1_score < g.team2_score THEN 1 ELSE 0 END) as losses,
        SUM(CASE WHEN g.result_type = 'OT' AND g.team1_score < g.team2_score THEN 1 ELSE 0 END) as ot_losses,
        SUM(CASE WHEN g.result_type = 'SO' AND g.team1_score < g.team2_score THEN 1 ELSE 0 END) as so_losses
    FROM games g
    WHERE g.round IN ('Preliminary Round', 'Group Stage')
      AND g.team1_score IS NOT NULL
      AND g.team2_score IS NOT NULL
    GROUP BY g.year_id, g.group, g.team1_code
    
    UNION ALL
    
    -- Team2 Statistiken
    SELECT 
        g.year_id,
        g.group,
        g.team2_code as team_code,
        COUNT(*) as games_played,
        SUM(g.team2_score) as goals_for,
        SUM(g.team1_score) as goals_against,
        SUM(g.team2_points) as points,
        SUM(CASE WHEN g.result_type = 'REG' AND g.team2_score > g.team1_score THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN g.result_type = 'OT' AND g.team2_score > g.team1_score THEN 1 ELSE 0 END) as ot_wins,
        SUM(CASE WHEN g.result_type = 'SO' AND g.team2_score > g.team1_score THEN 1 ELSE 0 END) as so_wins,
        SUM(CASE WHEN g.result_type = 'REG' AND g.team2_score < g.team1_score THEN 1 ELSE 0 END) as losses,
        SUM(CASE WHEN g.result_type = 'OT' AND g.team2_score < g.team1_score THEN 1 ELSE 0 END) as ot_losses,
        SUM(CASE WHEN g.result_type = 'SO' AND g.team2_score < g.team1_score THEN 1 ELSE 0 END) as so_losses
    FROM games g
    WHERE g.round IN ('Preliminary Round', 'Group Stage')
      AND g.team1_score IS NOT NULL
      AND g.team2_score IS NOT NULL
    GROUP BY g.year_id, g.group, g.team2_code
)
SELECT 
    year_id,
    group,
    team_code,
    SUM(games_played) as gp,
    SUM(wins) as w,
    SUM(ot_wins) as otw,
    SUM(so_wins) as sow,
    SUM(losses) as l,
    SUM(ot_losses) as otl,
    SUM(so_losses) as sol,
    SUM(points) as pts,
    SUM(goals_for) as gf,
    SUM(goals_against) as ga,
    SUM(goals_for) - SUM(goals_against) as gd
FROM team_stats
GROUP BY year_id, group, team_code;

-- Index für die Materialized View
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_group_standings_unique 
ON mv_group_standings(year_id, group, team_code);

CREATE INDEX IF NOT EXISTS idx_mv_group_standings_year_group 
ON mv_group_standings(year_id, group);

-- =============================================================================
-- STATISTICS TRACKING TABLE (für Performance-Monitoring)
-- =============================================================================

CREATE TABLE IF NOT EXISTS query_statistics (
    id SERIAL PRIMARY KEY,
    query_type VARCHAR(100) NOT NULL,
    execution_time_ms INTEGER NOT NULL,
    rows_returned INTEGER,
    cache_hit BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_query_statistics_type_time 
ON query_statistics(query_type, created_at);

-- =============================================================================
-- REFRESH FUNCTION für Materialized View
-- =============================================================================

CREATE OR REPLACE FUNCTION refresh_standings_mv()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_group_standings;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- ANALYZE TABLES für Query-Planer-Optimierung
-- =============================================================================

-- Diese Befehle sollten nach dem Erstellen der Indizes ausgeführt werden
ANALYZE games;
ANALYZE goals;
ANALYZE penalties;
ANALYZE players;
ANALYZE championship_years;

-- =============================================================================
-- HINWEISE ZUR VERWENDUNG
-- =============================================================================

-- 1. Führen Sie dieses Skript in Ihrer PostgreSQL-Datenbank aus
-- 2. Die Indizes werden nur erstellt, wenn sie noch nicht existieren
-- 3. Die Materialized View ist optional - nur bei sehr hohem Traffic empfohlen
-- 4. Aktualisieren Sie die Materialized View nach Spiel-Updates:
--    SELECT refresh_standings_mv();
-- 5. Überwachen Sie die Performance mit der query_statistics Tabelle

-- Geschätzte Performance-Verbesserung:
-- - Standings-Queries: 80-90% schneller
-- - Team-Statistiken: 70-80% schneller
-- - Spieler-Statistiken: 60-70% schneller
-- - Playoff-Queries: 75-85% schneller