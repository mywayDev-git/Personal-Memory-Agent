"""Additive, idempotent chat extension; applied by the host Store transaction."""

DDL = """
CREATE TABLE IF NOT EXISTS chat_ui_actions (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
 message_id TEXT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
 state TEXT NOT NULL CHECK(state IN ('ACTIVE','LOADING','RESOLVED','EXPIRED')),
 context_version INTEGER NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)),
 request_id TEXT, result TEXT CHECK(result IS NULL OR json_valid(result)));
CREATE UNIQUE INDEX IF NOT EXISTS chat_action_request ON chat_ui_actions(session_id,request_id)
 WHERE request_id IS NOT NULL;
CREATE TRIGGER IF NOT EXISTS chat_action_source_changed AFTER UPDATE OF version,state ON records
 WHEN NEW.version<>OLD.version OR NEW.state<>OLD.state BEGIN
 UPDATE chat_ui_actions SET state='EXPIRED',result=NULL
 WHERE EXISTS(SELECT 1 FROM json_each(payload,'$.source_versions') s WHERE s.key=NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS chat_action_source_deleted BEFORE DELETE ON records BEGIN
 UPDATE chat_ui_actions SET state='EXPIRED',result=NULL
 WHERE EXISTS(SELECT 1 FROM json_each(payload,'$.source_versions') s WHERE s.key=OLD.id);
END;
CREATE TABLE IF NOT EXISTS chat_schema_migrations (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO chat_schema_migrations VALUES(1);
CREATE TABLE IF NOT EXISTS chat_context (
 session_id TEXT PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
 version INTEGER NOT NULL DEFAULT 0,
 payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TABLE IF NOT EXISTS chat_retrieval_runs (
 message_id TEXT PRIMARY KEY REFERENCES chat_messages(id) ON DELETE CASCADE,
 payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TABLE IF NOT EXISTS chat_clarifications (
 message_id TEXT PRIMARY KEY REFERENCES chat_messages(id) ON DELETE CASCADE,
 payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TRIGGER IF NOT EXISTS chat_context_source_changed AFTER UPDATE OF version,state ON records
 WHEN NEW.version<>OLD.version OR NEW.state<>OLD.state BEGIN
 UPDATE chat_context SET version=version+1,
 payload=json_set(payload,'$.version',version+1,'$.active_evidence',json('[]'),
 '$.pending_clarification',NULL)
 WHERE session_id IN (SELECT m.session_id FROM chat_messages m
 JOIN chat_message_evidence e ON e.message_id=m.id WHERE e.record_id=NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS chat_context_source_deleted BEFORE DELETE ON records BEGIN
 UPDATE chat_context SET version=version+1,
 payload=json_set(payload,'$.version',version+1,'$.active_evidence',json('[]'),
 '$.pending_clarification',NULL)
 WHERE session_id IN (SELECT m.session_id FROM chat_messages m
 JOIN chat_message_evidence e ON e.message_id=m.id WHERE e.record_id=OLD.id);
END;
"""
