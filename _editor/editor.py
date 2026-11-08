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
RESUME_FILE = ROOT / "assets" / "files" / "resume.pdf"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
MAX_UPLOAD = 25 * 1024 * 1024
# "Publish" stages every change in the repository (new, edited and deleted files),
# so pages renamed or removed by hand and editor updates aren't left behind.
# Keep things that shouldn't go live out of the repo with .gitignore.


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


def _usage_sources() -> list[Path]:
    """Files that can reference an image: the saved content, the editor's own page
    (its logo), every page at the site root (including ones the editor doesn't
    manage) and the site's CSS/JS."""
    return [build.CONTENT_FILE, build.EDITOR_DIR / "editor.html", *sorted(ROOT.glob("*.html")),
            *sorted((ROOT / "assets").rglob("*.css")), *sorted((ROOT / "assets").rglob("*.js"))]


def _name_pattern(name: str) -> re.Pattern:
    return re.compile(r"(?<![\w.-])" + re.escape(name) + r"(?![\w.-])")


def image_usages(names: list[str], draft: dict | None = None) -> dict[str, list[str]]:
    """Map each image file name to the places that reference it."""
    texts = []
    if draft is not None:
        texts.append(("unsaved editor changes", json.dumps(draft, ensure_ascii=False)))
    for f in _usage_sources():
        try:
            texts.append((str(f.relative_to(ROOT)), f.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            pass
    out = {}
    for name in names:
        pat = _name_pattern(name)
        out[name] = [label for label, text in texts if name in text and pat.search(text)]
    return out


def image_file(rel: str) -> Path:
    """Resolve "assets/images/<name>" to an existing image file, or raise."""
    m = re.fullmatch(r"assets/images/([^/\\]+)", str(rel or ""))
    if not m:
        raise ValueError("Only files directly in assets/images can be changed.")
    target = (IMAGE_DIR / m.group(1)).resolve()
    if target.parent != IMAGE_DIR.resolve() or target.suffix.lower() not in IMAGE_EXTS:
        raise ValueError(f"{rel} is not an image in assets/images.")
    if not target.is_file():
        raise ValueError(f"{rel} does not exist.")
    return target


def _replace_strings(obj, old: str, new: str):
    if isinstance(obj, str):
        return obj.replace(old, new)
    if isinstance(obj, list):
        return [_replace_strings(x, old, new) for x in obj]
    if isinstance(obj, dict):
        return {k: _replace_strings(v, old, new) for k, v in obj.items()}
    return obj


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
                if path == "/api/resume":
                    return self._json(self._resume_info())
                if path == "/api/images/details":
                    return self._json(self._image_details())
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
            if path == "/api/upload-resume":
                return self._json(self._upload_resume())
            if path == "/api/delete-images":
                return self._json(self._delete_images(self._read_json()))
            if path == "/api/rename-image":
                return self._json(self._rename_image(self._read_json()))
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

    def _resume_info(self):
        if not RESUME_FILE.is_file():
            return {"exists": False, "path": "assets/files/resume.pdf"}
        st = RESUME_FILE.stat()
        return {"exists": True, "path": "assets/files/resume.pdf", "size": st.st_size, "mtime": st.st_mtime}

    def _upload_resume(self):
        """Replace assets/files/resume.pdf with the uploaded PDF (written atomically)."""
        data = self._body()
        if not data.startswith(b"%PDF-"):
            raise ValueError("That file isn't a PDF.")
        RESUME_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = RESUME_FILE.with_name(".resume.pdf.uploading")
        tmp.write_bytes(data)
        tmp.replace(RESUME_FILE)
        return self._resume_info()

    def _image_details(self):
        files = sorted((p for p in IMAGE_DIR.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        usage = image_usages([p.name for p in files])
        return [{"path": f"assets/images/{p.name}", "name": p.name, "size": p.stat().st_size,
                 "mtime": p.stat().st_mtime, "usedIn": usage[p.name]} for p in files]

    def _delete_images(self, data: dict):
        """Delete files in assets/images, skipping any that something still uses."""
        targets, errors = [], []
        for rel in data.get("paths") or []:
            try:
                targets.append((rel, image_file(rel)))
            except ValueError as exc:
                errors.append({"path": rel, "error": str(exc)})
        usage = image_usages([t.name for _, t in targets], data.get("content"))
        deleted, blocked = [], []
        for rel, target in targets:
            if usage[target.name]:
                blocked.append({"path": rel, "usedIn": usage[target.name]})
                continue
            try:
                target.unlink()
                deleted.append(rel)
            except OSError as exc:
                errors.append({"path": rel, "error": str(exc)})
        return {"deleted": deleted, "blocked": blocked, "errors": errors}

    def _rename_image(self, data: dict):
        """Rename an image and update the editor's saved content to match.

        Refuses when the image is referenced anywhere the editor can't rewrite
        (hand-made pages, CSS, JS). Generated pages are rebuilt afterwards."""
        target = image_file(data.get("path"))
        raw = Path(str(data.get("newName") or "")).name
        stem = re.sub(r"[^a-z0-9]+", "-", Path(raw).stem.lower()).strip("-")[:80]
        if not stem:
            raise ValueError("Enter a new file name.")
        new = target.with_name(stem + target.suffix.lower())
        if new.name == target.name:
            return {"path": f"assets/images/{new.name}", "unchanged": True}
        if new.exists():
            raise ValueError(f"{new.name} already exists.")
        saved = build.load_content()
        managed = {"_editor/content.json", *build.page_files(saved)}
        elsewhere = [u for u in image_usages([target.name])[target.name] if u not in managed]
        if elsewhere:
            return {"ok": False, "usedIn": elsewhere}
        old_rel, new_rel = f"assets/images/{target.name}", f"assets/images/{new.name}"
        target.rename(new)
        updated = _replace_strings(saved, old_rel, new_rel)
        if updated != saved:
            build.build(updated)
            build.save_content(updated)
        return {"ok": True, "old": old_rel, "path": new_rel}

    def _git_status(self):
        if git("rev-parse", "--is-inside-work-tree").returncode != 0:
            return {"available": False}
        status = git("status", "--porcelain", "--untracked-files=all")
        branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        remote = git("remote", "get-url", "origin").stdout.strip()
        return {
            "available": True,
            "branch": branch,
            "remote": remote,
            "changes": [line for line in status.stdout.splitlines() if line.strip()],
            "unpushed": self._unpushed(),
        }

    @staticmethod
    def _unpushed() -> int:
        """Commits on this branch that haven't reached GitHub yet (e.g. a push that failed)."""
        r = git("rev-list", "--count", "@{upstream}..HEAD")
        return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0

    def _publish(self, data):
        message = (data.get("message") or "").strip() or "Update website"
        log = []

        def run(*args):
            result = git(*args)
            log.append(f"$ git {' '.join(args)}\n{result.stdout}{result.stderr}".rstrip())
            return result

        run("add", "--all")
        if run("diff", "--cached", "--quiet").returncode != 0:
            if run("commit", "-m", message).returncode != 0:
                return {"ok": False, "log": "\n\n".join(log)}
        elif not self._unpushed():
            return {"ok": True, "log": "\n\n".join(log + ["Nothing new to publish."])}
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
