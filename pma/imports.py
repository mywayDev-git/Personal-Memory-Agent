"""Preview and atomic UTF-8 import; original offsets remain traceable."""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from pydantic import Field

from .errors import AppError
from .store import identifier

DDL = """
CREATE TABLE IF NOT EXISTS record_imports (
 id TEXT PRIMARY KEY, filename TEXT NOT NULL, source TEXT NOT NULL,
 created_at TEXT NOT NULL, request_id TEXT UNIQUE, result TEXT);
CREATE TABLE IF NOT EXISTS record_import_locations (
 record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
 import_id TEXT NOT NULL REFERENCES record_imports(id), start INTEGER NOT NULL, end INTEGER NOT NULL);
"""


def chunks(text):
    start, result = 0, []
    while start < len(text):
        end = min(start + 4000, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + 2000, end)
            if boundary >= 0:
                end = boundary + 1
        if text[start:end].strip():
            result.append({"start": start, "end": end, "text": text[start:end]})
        start = end
    return result


class TextImporter:
    def __init__(self, store):
        self.store = store

    def preview(self, filename, text):
        if (
            not filename.lower().endswith((".txt", ".md"))
            or any(c in filename for c in "/\\\0")
            or not text.strip()
            or "\0" in text
            or len(text.encode("utf-8")) > 1024 * 1024
        ):
            raise AppError(
                "INVALID_IMPORT", "1MiB 이하의 UTF-8 텍스트·Markdown 파일을 선택해 주세요.", 422
            )
        iid = identifier()
        with self.store.connect(True) as db:
            db.execute(
                "DELETE FROM record_imports WHERE request_id IS NULL AND created_at<?",
                ((datetime.fromisoformat(self.store.clock()) - timedelta(days=1)).isoformat(),),
            )
            db.execute(
                "INSERT INTO record_imports VALUES(?,?,?,?,NULL,NULL)",
                (iid, filename, text, self.store.clock()),
            )
        return {"import_id": iid, "filename": filename, "chunks": chunks(text), "state": "preview"}

    def commit(self, iid, request_id):
        with self.store.connect(True) as db:
            row = db.execute("SELECT * FROM record_imports WHERE id=?", (iid,)).fetchone()
            if not row:
                raise AppError("IMPORT_EXPIRED", "파일을 다시 선택해 주세요.", 404)
            if row["request_id"]:
                if row["request_id"] != request_id:
                    raise AppError("REQUEST_CONFLICT", "이미 가져온 파일입니다.", 409)
                return json.loads(row["result"])
            if db.execute(
                "SELECT 1 FROM record_imports WHERE request_id=?", (request_id,)
            ).fetchone():
                raise AppError("REQUEST_CONFLICT", "다른 파일에 사용한 요청 ID입니다.", 409)
            if datetime.fromisoformat(row["created_at"]) <= datetime.fromisoformat(
                self.store.clock()
            ) - timedelta(days=1):
                raise AppError(
                    "IMPORT_EXPIRED", "미리보기가 만료되었습니다. 파일을 다시 선택해 주세요.", 409
                )
            records = []
            for part in chunks(row["source"]):
                rid, rev, ts = identifier(), identifier(), self.store.clock()
                db.execute(
                    "INSERT INTO records VALUES(?,1,'active','queued',?,?,NULL,NULL)", (rid, ts, ts)
                )
                db.execute(
                    "INSERT INTO revisions VALUES(?,?,1,?,NULL,?)", (rev, rid, part["text"], ts)
                )
                job = self.store.queue(db, rev)
                db.execute(
                    "INSERT INTO record_import_locations VALUES(?,?,?,?)",
                    (rid, iid, part["start"], part["end"]),
                )
                records.append(
                    {
                        "record_id": rid,
                        "version": 1,
                        "job_id": job,
                        "status": "queued",
                        "source_location": {
                            "filename": row["filename"],
                            "start": part["start"],
                            "end": part["end"],
                        },
                    }
                )
            self.store.bump(db)
            result = {"import_id": iid, "state": "saved", "records": records}
            # Committed source lives only in records, so deletion cannot leave another raw copy.
            db.execute(
                "UPDATE record_imports SET request_id=?,result=?,source='' WHERE id=?",
                (request_id, json.dumps(result, ensure_ascii=False), iid),
            )
        return result

    def discard(self, iid):
        with self.store.connect(True) as db:
            db.execute("DELETE FROM record_imports WHERE id=? AND request_id IS NULL", (iid,))


def router(input_type):
    routes = APIRouter(prefix="/api/v1/imports")

    class Preview(input_type):
        filename: str = Field(min_length=1, max_length=200)
        text: str = Field(min_length=1, max_length=1024 * 1024)

    class Commit(input_type):
        request_id: str = Field(min_length=1, max_length=128)

    @routes.post("/preview", status_code=201)
    def preview(data: Preview, request: Request):
        return TextImporter(request.app.state.store).preview(data.filename, data.text)

    @routes.post("/{iid}/commit", status_code=202)
    def commit(iid: str, data: Commit, request: Request):
        return TextImporter(request.app.state.store).commit(iid, data.request_id)

    @routes.delete("/{iid}", status_code=204)
    def discard(iid: str, request: Request):
        from fastapi import Response

        TextImporter(request.app.state.store).discard(iid)
        return Response(status_code=204)

    return routes
