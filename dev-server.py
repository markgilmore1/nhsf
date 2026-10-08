#!/usr/bin/env python3
"""Local preview server that expands Apache-style SSI includes.

Mirrors what .htaccess turns on in production, so pages using
<!--#include virtual="/partials/x.html" --> render the same locally.
Usage: python3 dev-server.py [port]   (default 8765)
"""
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
INCLUDE = re.compile(r'<!--#include\s+virtual="([^"]+)"\s*-->')


def expand(text, depth=0):
    if depth > 5:
        raise RuntimeError("include nesting too deep")

    def sub(m):
        path = os.path.normpath(os.path.join(ROOT, m.group(1).lstrip("/")))
        if not path.startswith(ROOT + os.sep) or not os.path.isfile(path):
            return f"[include not found: {m.group(1)}]"
        with open(path, encoding="utf-8") as f:
            return expand(f.read(), depth + 1)

    return INCLUDE.sub(sub, text)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if path.lower().endswith((".htm", ".html")) and os.path.isfile(path):
            with open(path, "rb") as f:
                raw = f.read()
            try:
                body = expand(raw.decode("utf-8")).encode("utf-8")
                charset = "utf-8"
            except UnicodeDecodeError:  # legacy pages not in UTF-8
                body = expand(raw.decode("latin-1")).encode("latin-1")
                charset = "iso-8859-1"
            self.send_response(200)
            self.send_header("Content-Type", f"text/html; charset={charset}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    ThreadingHTTPServer(("", port), Handler).serve_forever()
