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


def upgrade_v4(previous):
    """Replace session-wide invalidation with transactional answer provenance."""
    migration = ""
    if previous < 4:
        migration = """
        INSERT OR IGNORE INTO chat_message_snapshots
        SELECT m.id,s.payload FROM chat_messages m JOIN chat_snapshots s ON s.session_id=m.session_id;
        INSERT OR IGNORE INTO chat_message_evidence
        SELECT m.id,i.memory_id,i.record_id,i.version,i.payload FROM chat_messages m
        JOIN chat_snapshot_items i ON i.session_id=m.session_id;
        UPDATE chat_messages SET error_code='SOURCE_MODIFIED' WHERE session_id IN
        (SELECT id FROM chat_sessions WHERE state='read_only');
        UPDATE chat_sessions SET state='active';
        """
    deletion = """
        UPDATE chat_messages SET response=NULL,error_code='SOURCE_DELETED',state='completed'
        WHERE id IN (SELECT message_id FROM chat_message_evidence WHERE record_id=OLD.id);
        DELETE FROM chat_citations WHERE message_id IN
        (SELECT message_id FROM chat_message_evidence WHERE record_id=OLD.id);
        DELETE FROM chat_message_snapshots WHERE message_id IN
        (SELECT message_id FROM chat_message_evidence WHERE record_id=OLD.id);
        DELETE FROM chat_message_evidence WHERE message_id IN
        (SELECT message_id FROM chat_message_evidence WHERE record_id=OLD.id);
        DELETE FROM chat_snapshots WHERE session_id IN
        (SELECT session_id FROM chat_snapshot_items WHERE record_id=OLD.id);
        DELETE FROM chat_searches WHERE id IN
        (SELECT search_id FROM chat_search_results WHERE record_id=OLD.id);
    """
    return (
        """
        DROP TRIGGER IF EXISTS chat_source_modified;
        DROP TRIGGER IF EXISTS chat_source_trashed;
        DROP TRIGGER IF EXISTS chat_source_purged;
        CREATE TABLE IF NOT EXISTS chat_message_snapshots (
          message_id TEXT PRIMARY KEY REFERENCES chat_messages(id) ON DELETE CASCADE,
          payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS chat_message_evidence (
          message_id TEXT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
          memory_id TEXT NOT NULL,record_id TEXT NOT NULL,version INTEGER NOT NULL,payload TEXT NOT NULL,
          PRIMARY KEY(message_id,memory_id));
        CREATE INDEX IF NOT EXISTS chat_message_source ON chat_message_evidence(record_id);
        """
        + migration
        + """
        CREATE TRIGGER chat_source_modified AFTER UPDATE OF version ON records
        WHEN NEW.version<>OLD.version BEGIN
          UPDATE chat_messages SET error_code='SOURCE_MODIFIED' WHERE id IN
          (SELECT message_id FROM chat_message_evidence WHERE record_id=NEW.id);
        END;
        CREATE TRIGGER chat_source_trashed BEFORE UPDATE OF state ON records
        WHEN NEW.state='trash' BEGIN
        """
        + deletion
        + """ END;
        CREATE TRIGGER chat_source_purged BEFORE DELETE ON records BEGIN
        """
        + deletion
        + """ END;
        PRAGMA user_version=4;
    """
    )


def upgrade_v5(has_request_input):
    """Retain the exact request body for retries, including optional date input."""
    return (
        "" if has_request_input else "ALTER TABLE chat_messages ADD COLUMN request_input TEXT;\n"
    ) + "PRAGMA user_version=5;\n"
