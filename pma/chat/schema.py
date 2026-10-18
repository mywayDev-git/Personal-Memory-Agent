"""Additive v3 migration and source lifecycle constraints."""

DDL = """
CREATE TABLE IF NOT EXISTS chat_searches (
 id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat_search_results (
 search_id TEXT NOT NULL REFERENCES chat_searches(id) ON DELETE CASCADE,
 memory_id TEXT NOT NULL, record_id TEXT NOT NULL, version INTEGER NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(search_id,memory_id));
CREATE INDEX IF NOT EXISTS chat_search_record ON chat_search_results(record_id);
CREATE TABLE IF NOT EXISTS chat_sessions (
 id TEXT PRIMARY KEY, search_id TEXT REFERENCES chat_searches(id) ON DELETE SET NULL,
 title TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('active','read_only')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat_snapshots (
 session_id TEXT PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
 payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat_snapshot_items (
 session_id TEXT NOT NULL REFERENCES chat_snapshots(session_id) ON DELETE CASCADE,
 memory_id TEXT NOT NULL, record_id TEXT NOT NULL, version INTEGER NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(session_id,memory_id));
CREATE INDEX IF NOT EXISTS chat_snapshot_record ON chat_snapshot_items(record_id);
CREATE TABLE IF NOT EXISTS chat_messages (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
 request_id TEXT NOT NULL, question TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('running','completed','failed')),
 response TEXT, error_code TEXT, created_at TEXT NOT NULL, completed_at TEXT,
 UNIQUE(session_id,request_id));
CREATE UNIQUE INDEX IF NOT EXISTS chat_one_running ON chat_messages(session_id)
 WHERE state='running';
CREATE TABLE IF NOT EXISTS chat_citations (
 message_id TEXT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
 item_index INTEGER NOT NULL, memory_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(message_id,item_index,memory_id));
CREATE TRIGGER IF NOT EXISTS chat_source_modified AFTER UPDATE OF version ON records
 WHEN NEW.version <> OLD.version BEGIN
 UPDATE chat_sessions SET state='read_only' WHERE id IN
 (SELECT session_id FROM chat_snapshot_items WHERE record_id=NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS chat_source_trashed BEFORE UPDATE OF state ON records
 WHEN NEW.state='trash' BEGIN
 DELETE FROM chat_sessions WHERE id IN
 (SELECT session_id FROM chat_snapshot_items WHERE record_id=OLD.id);
 DELETE FROM chat_searches WHERE id IN
 (SELECT search_id FROM chat_search_results WHERE record_id=OLD.id);
END;
CREATE TRIGGER IF NOT EXISTS chat_source_purged BEFORE DELETE ON records BEGIN
 DELETE FROM chat_sessions WHERE id IN
 (SELECT session_id FROM chat_snapshot_items WHERE record_id=OLD.id);
 DELETE FROM chat_searches WHERE id IN
 (SELECT search_id FROM chat_search_results WHERE record_id=OLD.id);
END;
CREATE TRIGGER IF NOT EXISTS chat_session_removed AFTER DELETE ON chat_sessions BEGIN
 DELETE FROM chat_searches WHERE id=OLD.search_id AND NOT EXISTS
 (SELECT 1 FROM chat_sessions WHERE search_id=OLD.search_id);
END;
PRAGMA user_version=3;
"""
