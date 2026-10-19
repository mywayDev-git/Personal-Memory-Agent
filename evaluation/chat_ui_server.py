"""Disposable browser fixture using production HTML/CSS/chat.js and in-memory fake API.
Run: python -m evaluation.chat_ui_server (localhost:8880; no personal data).
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            content = (ROOT / "pma/static/index.html").read_text(encoding="utf-8").replace("/static/app.js", "/fixture.js")
            mime = "text/html"
        elif path == "/mobile":
            content = '<iframe title="모바일 대화" src="/" style="width:390px;height:844px;border:1px solid #ddd"></iframe>'
            mime = "text/html"
        elif path == "/fixture.js":
            content = (ROOT / "evaluation/chat_ui_fixture.js").read_text(encoding="utf-8")
            mime = "text/javascript"
        elif path in {"/static/" + p for p in ("chat.js", "memory.js", "search-explanation.js", "style.css", "evaluation-link.js")}:
            content = (ROOT / "pma" / path.lstrip("/")).read_text(encoding="utf-8")
            mime = "text/css" if path.endswith(".css") else "text/javascript"
        else:
            self.send_error(404)
            return
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    print("Chat fixture: http://127.0.0.1:8880/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8880), Handler).serve_forever()
