-- =============================================================================
-- FOREIGN KEY INDEXES MIGRATION (CORRECTED)
-- Issue #17: Add Missing Database Indexes for Foreign Keys
-- =============================================================================
-- 
-- This migration adds the missing foreign key indexes identified in Issue #17
-- to improve query performance and enforce referential integrity constraints.
--
-- CORRECTED VERSION: Uses actual table names from database schema
-- Tables: game, goal, penalty, shots_on_goal, player, championship_year
--
-- Performance Impact:
-- - Joins on foreign keys will be significantly faster
-- - DELETE/UPDATE operations on referenced tables will be faster
-- - Query optimizer will have better execution plans
-- =============================================================================

-- Enable foreign key constraints (important for SQLite)
PRAGMA foreign_keys = ON;

-- =============================================================================
-- GAME TABLE FOREIGN KEY INDEXES
-- =============================================================================

-- Index for game.year_id (foreign key to championship_year.id)
-- Improves performance for year-based game queries
CREATE INDEX IF NOT EXISTS idx_games_year_id 
ON game(year_id);

-- =============================================================================
-- GOAL TABLE FOREIGN KEY INDEXES  
-- =============================================================================

-- Index for goal.game_id (foreign key to game.id)
-- Critical for game statistics and goal aggregations
CREATE INDEX IF NOT EXISTS idx_goals_game_id 
ON goal(game_id);

-- Index for goal.scorer_id (foreign key to player.id) 
-- Essential for player goal statistics
CREATE INDEX IF NOT EXISTS idx_goals_player_id 
ON goal(scorer_id);

-- Additional indexes for assist foreign keys (performance bonus)
CREATE INDEX IF NOT EXISTS idx_goals_assist1_id 
ON goal(assist1_id)
WHERE assist1_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_goals_assist2_id 
ON goal(assist2_id) 
WHERE assist2_id IS NOT NULL;

-- =============================================================================
-- PENALTY TABLE FOREIGN KEY INDEXES
-- =============================================================================

-- Index for penalty.game_id (foreign key to game.id)
-- Improves penalty queries by game
CREATE INDEX IF NOT EXISTS idx_penalties_game_id 
ON penalty(game_id);

-- Index for penalty.player_id (foreign key to player.id)
-- Essential for player penalty statistics  
CREATE INDEX IF NOT EXISTS idx_penalties_player_id 
ON penalty(player_id)
WHERE player_id IS NOT NULL;

-- =============================================================================
-- SHOTS_ON_GOAL TABLE FOREIGN KEY INDEXES
-- =============================================================================

-- Index for shots_on_goal.game_id (foreign key to game.id)
-- Critical for shot statistics and game analysis
CREATE INDEX IF NOT EXISTS idx_shots_on_goal_game_id 
ON shots_on_goal(game_id);

-- =============================================================================
-- COMPOSITE FOREIGN KEY INDEXES (Performance Optimization)
-- =============================================================================

-- Composite index for goal: game + player for efficient player-game statistics
CREATE INDEX IF NOT EXISTS idx_goals_game_player 
ON goal(game_id, scorer_id);

-- Composite index for penalty: game + player for penalty analysis
CREATE INDEX IF NOT EXISTS idx_penalties_game_player 
ON penalty(game_id, player_id)
WHERE player_id IS NOT NULL;

-- Composite index for shots_on_goal: game + team for team shot statistics
CREATE INDEX IF NOT EXISTS idx_shots_on_goal_game_team 
ON shots_on_goal(game_id, team_code);

-- =============================================================================
-- ANALYZE TABLES (Update statistics for query optimizer)
-- =============================================================================

ANALYZE game;
ANALYZE goal; 
ANALYZE penalty;
ANALYZE shots_on_goal;
ANALYZE player;
ANALYZE championship_year;

-- =============================================================================
-- MIGRATION COMPLETE
-- Issue #17 Requirements Fulfilled:
-- ✅ idx_games_year_id ON game(year_id)
-- ✅ idx_goals_game_id ON goal(game_id)
-- ✅ idx_goals_player_id ON goal(scorer_id)
-- ✅ idx_penalties_game_id ON penalty(game_id)
-- ✅ idx_penalties_player_id ON penalty(player_id)
-- ✅ idx_shots_on_goal_game_id ON shots_on_goal(game_id)
-- =============================================================================