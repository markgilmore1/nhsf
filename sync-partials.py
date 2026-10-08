#!/usr/bin/env python3
"""Keep the shared header, menu and footer identical on every page.

The shared markup lives in partials/. Each page holds a generated copy of it
between marker comments:

    <!-- sync:header -->  ...generated...  <!-- /sync:header -->

Pages stay plain static HTML, so they work on any host.

    python3 sync-partials.py            rewrite every marked section from partials/
    python3 sync-partials.py --check    change nothing; exit 1 if any page is out of date
    python3 sync-partials.py --adopt    one-off: wrap the existing header/menu/footer
                                        blocks of pages that don't have markers yet

Links in partials are written root-relative (/background/mission.htm) and are
rewritten per page to relative paths (../background/mission.htm), so the site
works from any folder or subdomain.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PARTIALS = os.path.join(ROOT, "partials")
SECTIONS = ("header", "nav", "footer")  # order of appearance in a page
SKIP_DIRS = {".git", ".claude", "archive", "temp", "Template", "partials", "QRcodes"}

MARK = re.compile(
    r"(?P<indent>[ \t]*)<!-- sync:(?P<name>\w+)\b[^>]*-->\n"
    r".*?"
    r"(?P=indent)<!-- /sync:(?P=name) -->",
    re.S,
)
PLACEHOLDER = re.compile(r"^([ \t]*)\{\{([\w-]+)\}\}[ \t]*$", re.M)
URL_ATTR = re.compile(r'\b(href|src)="/(?!/)([^"]*)"')
TAG = re.compile(r"<(/?)(div|header|footer|nav)\b[^>]*>", re.I)
OPENERS = {
    "header": r'<(?:header|div)\s+class="site-header-wrapper"',
    "nav": r'<div\s+class="main-nav-wrapper"',
    "footer": r'<(?:footer|div)\s+class="site-footer-wrapper"',
}


def read(path):
    raw = open(path, "rb").read()
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"


def write(path, text, enc):
    with open(path, "wb") as f:
        f.write(text.encode(enc))


def pages():
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and d != "_vti_cnf")
        for name in sorted(files):
            if name.lower().endswith((".htm", ".html")):
                yield os.path.join(dirpath, name)


def indent_block(text, indent):
    return "\n".join(indent + l if l.strip() else l for l in text.rstrip("\n").split("\n"))


def partial(name, _seen=()):
    """Partial text with {{other-partial}} placeholders expanded, indentation kept."""
    if name in _seen:
        raise SystemExit(f"partials include each other in a loop: {name}")
    with open(os.path.join(PARTIALS, name + ".html"), encoding="utf-8") as f:
        text = f.read().rstrip("\n")
    return PLACEHOLDER.sub(
        lambda m: indent_block(partial(m.group(2), _seen + (name,)), m.group(1)), text
    )


def relativise(html, page):
    """Turn root-relative /x links into links relative to this page's folder."""
    depth = os.path.relpath(os.path.dirname(page), ROOT).count(os.sep) + (
        0 if os.path.dirname(page) == ROOT else 1
    )
    prefix = "../" * depth
    return URL_ATTR.sub(lambda m: f'{m.group(1)}="{prefix}{m.group(2)}"', html)


def render(name, page, indent):
    body = relativise(partial(name), page)
    head = f"{indent}<!-- sync:{name} (generated from partials/{name}.html; edit that, then run sync-partials.py) -->"
    return f"{head}\n{indent_block(body, indent)}\n{indent}<!-- /sync:{name} -->"


def sync_text(text, page):
    return MARK.sub(lambda m: render(m.group("name"), page, m.group("indent")), text)


def find_block(text, opener):
    m = re.search(opener, text)
    if not m:
        return None
    depth = 0
    for t in TAG.finditer(text, m.start()):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return m.start(), t.end()
    return None


def adopt_text(text):
    """Replace the old hand-copied blocks with empty marker pairs (sync fills them)."""
    spans = {n: find_block(text, OPENERS[n]) for n in SECTIONS}
    if any(v is None for v in spans.values()):
        return None
    for name in reversed(SECTIONS):  # back to front keeps offsets valid
        a, b = spans[name]
        line_start = text.rfind("\n", 0, a) + 1
        indent = text[line_start:a] if not text[line_start:a].strip() else ""
        text = (
            text[:a]
            + f"<!-- sync:{name} -->\n{indent}<!-- /sync:{name} -->"
            + text[b:]
        )
        spans = {n: find_block(text, OPENERS[n]) if n != name else None for n in SECTIONS}
    return text


def main(argv):
    mode = argv[0] if argv else "--write"
    if mode not in ("--write", "--check", "--adopt"):
        raise SystemExit(__doc__)
    changed, adopted, skipped = [], [], []
    for page in pages():
        rel = os.path.relpath(page, ROOT)
        text, enc = read(page)
        if mode == "--adopt":
            if "<!-- sync:" in text:
                continue
            new = adopt_text(text)
            if new is None:
                skipped.append(rel)
                continue
            text = new
            adopted.append(rel)
            write(page, sync_text(text, page), enc)
            continue
        if "<!-- sync:" not in text:
            continue
        new = sync_text(text, page)
        if new != text:
            changed.append(rel)
            if mode == "--write":
                write(page, new, enc)
    if mode == "--adopt":
        print(f"adopted {len(adopted)} pages")
        if skipped:
            print("no header/menu/footer to adopt (left alone):", *skipped, sep="\n  ")
        return 0
    verb = "out of date" if mode == "--check" else "updated"
    print(f"{len(changed)} pages {verb}")
    for rel in changed:
        print("  ", rel)
    return 1 if (mode == "--check" and changed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
