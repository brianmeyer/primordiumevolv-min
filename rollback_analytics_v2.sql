-- Rollback script for Analytics V2
-- This script safely removes Analytics V2 additions while preserving all existing data

-- Remove Analytics V2 tables
DROP TABLE IF EXISTS analytics_snapshot;
DROP TABLE IF EXISTS deprecated_entities;

-- Remove migration tracking (optional - uncomment if you want clean rollback)
-- DROP TABLE IF EXISTS schema_migrations;

-- Remove added columns (optional - these don't hurt to keep)
-- Note: SQLite doesn't support DROP COLUMN, so we'd need to recreate table
-- Leaving these as they contain useful normalized data and don't break anything
-- ALTER TABLE runs DROP COLUMN normalized_task_class;  -- Not supported in SQLite

-- Reset any deprecation flags in operator_stats if they were added
-- (This example assumes we had added a deprecated column - adapt as needed)
-- UPDATE operator_stats SET deprecated = 0 WHERE deprecated IS NOT NULL;

-- Clean up any Analytics V2 specific indexes
DROP INDEX IF EXISTS idx_analytics_snapshot_window;
DROP INDEX IF EXISTS idx_deprecated_entities_type;

-- Vacuum to reclaim space
VACUUM;