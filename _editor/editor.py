#!/usr/bin/env python3
"""Local editor app for the website.

    python3 _editor/editor.py            # opens http://localhost:8000/_editor/
    python3 _editor/editor.py --port 8123 --no-browser

Serves the site plus a small JSON API used by editor.html. It only listens on
127.0.0.1 and rejects cross-origin requests. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

ROOT = build.ROOT
IMAGE_DIR = ROOT / "assets" / "images"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
MAX_UPLOAD = 25 * 1024 * 1024
# What "Publish" stages. Everything the editor can change lives under these.
PUBLISH_PATHS = ["index.html", "assets", "_editor/content.json"]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


class Handler(SimpleHTTPRequestHandler):
    server_version = "SiteEditor/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):  # keep the terminal quiet except for API calls
        if self.path.startswith("/api/"):
            sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # ------------------------------------------------------------------ utils
    def _same_origin(self) -> bool:
        host = self.headers.get("Host", "")
        if not re.fullmatch(r"(localhost|127\.0\.0\.1)(:\d+)?", host):
            return False
        origin = self.headers.get("Origin")
        return origin is None or urlparse(origin).netloc == host

    def _json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self, limit=MAX_UPLOAD) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise ValueError("Upload is too large (max 25 MB).")
        return self.rfile.read(length)

    def _read_json(self):
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ValueError("Expected JSON.")
        return json.loads(self._body(5 * 1024 * 1024) or b"{}")

    # ---------------------------------------------------------------- routing
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/_editor", "/_editor/"):
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/_editor/editor.html")
            self.end_headers()
            return
        if path.startswith("/api/"):
            if not self._same_origin():
                return self._json({"error": "Forbidden"}, HTTPStatus.FORBIDDEN)
            try:
                if path == "/api/content":
                    return self._json(build.load_content())
                if path == "/api/meta":
                    return self._json({"themeDefaults": build.THEME_DEFAULTS})
                if path == "/api/images":
                    files = sorted(
                        (p for p in IMAGE_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    return self._json([f"assets/images/{p.name}" for p in files])
                if path == "/api/git-status":
                    return self._json(self._git_status())
            except Exception as exc:  # surface errors in the UI
                return self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._same_origin():
            return self._json({"error": "Forbidden"}, HTTPStatus.FORBIDDEN)
        try:
            if path == "/api/render":
                data = self._read_json()
                content = build.sanitize_content(data["content"])
                html = build.render(content, data.get("page", "index.html"))
                # Resolve relative asset URLs when the preview is shown via srcdoc.
                return self._html(html.replace("<head>", '<head>\n  <base href="/">', 1))
            if path == "/api/save":
                content = build.sanitize_content(self._read_json()["content"])
                written = build.build(content)  # build first so a template error doesn't save
                build.save_content(content)
                return self._json({"ok": True, "content": content, "written": written})
            if path == "/api/upload":
                return self._json(self._upload())
            if path == "/api/publish":
                return self._json(self._publish(self._read_json()))
        except Exception as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    # --------------------------------------------------------------- actions
    def _upload(self):
        raw_name = self.headers.get("X-Filename") or "image.png"
        name = Path(raw_name).name
        ext = Path(name).suffix.lower()
        if ext not in IMAGE_EXTS:
            raise ValueError(f"Unsupported image type: {ext or '(none)'}")
        stem = re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-")[:60] or "image"
        target = IMAGE_DIR / f"{stem}{ext}"
        n = 2
        while target.exists():
            target = IMAGE_DIR / f"{stem}-{n}{ext}"
            n += 1
        data = self._body()
        if not data:
            raise ValueError("Empty upload.")
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"path": f"assets/images/{target.name}"}

    def _git_status(self):
        if git("rev-parse", "--is-inside-work-tree").returncode != 0:
            return {"available": False}
        status = git("status", "--porcelain", "--", *PUBLISH_PATHS, *[p["file"] for p in build.load_content()["pages"]])
        branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        remote = git("remote", "get-url", "origin").stdout.strip()
        return {
            "available": True,
            "branch": branch,
            "remote": remote,
            "changes": [line for line in status.stdout.splitlines() if line.strip()],
        }

    def _publish(self, data):
        message = (data.get("message") or "").strip() or "Update website"
        paths = PUBLISH_PATHS + [p["file"] for p in build.load_content()["pages"]]
        paths = [p for p in paths if (ROOT / p).exists()]
        log = []

        def run(*args):
            result = git(*args)
            log.append(f"$ git {' '.join(args)}\n{result.stdout}{result.stderr}".rstrip())
            return result

        run("add", "--", *paths)
        if run("diff", "--cached", "--quiet").returncode == 0:
            return {"ok": True, "log": "\n\n".join(log + ["Nothing new to publish."])}
        if run("commit", "-m", message).returncode != 0:
            return {"ok": False, "log": "\n\n".join(log)}
        pushed = run("push")
        return {"ok": pushed.returncode == 0, "log": "\n\n".join(log)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = None
    for port in range(args.port, args.port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit(f"No free port between {args.port} and {args.port + 19}.")

    url = f"http://localhost:{server.server_address[1]}/_editor/editor.html"
    print(f"Website editor running at {url}\nPress Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
