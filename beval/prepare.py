"""Turn each bank's exhibits into one block-numbered text document.

Every paragraph and every table row becomes a block with a stable id (B0001...).
All models get exactly this text, and they cite block ids. That keeps the input
identical across labs (no PDF-handling differences) and makes citations checkable.

Usage: python -m beval.prepare            # all banks with fetched filings
Output: prepared/<TICKER>/document.txt and blocks.json
"""

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "tr", "table", "center", "br"}
WS = re.compile(r"\s+")


def clean(text: str) -> str:
    return WS.sub(" ", text.replace("\xa0", " ")).strip()


def table_rows(table: Tag) -> list[str]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [clean(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
        # EDGAR splits "$" and ")" into their own cells; glue them back on.
        merged: list[str] = []
        for c in cells:
            if not c:
                continue
            if merged and (c in (")", "%", ")%") or merged[-1] in ("$", "(", "$(")):
                merged[-1] += c
            else:
                merged.append(c)
        if merged:
            rows.append(" | ".join(merged))
    return rows


def html_blocks(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "head"]):
        t.decompose()
    for t in soup.find_all(lambda x: x.name and ":" in x.name and x.name.startswith("ix:header")):
        t.decompose()
    out: list[str] = []

    def walk(node: Tag):
        if node.name == "table":
            out.extend(table_rows(node))
            return
        has_block_child = any(isinstance(c, Tag) and (c.name in BLOCK_TAGS or c.find(list(BLOCK_TAGS)))
                              for c in node.children)
        if not has_block_child:
            txt = clean(node.get_text(" "))
            if txt:
                out.append(txt)
            return
        buf = []
        for c in node.children:
            if isinstance(c, NavigableString):
                buf.append(str(c))
            elif isinstance(c, Tag) and (c.name in BLOCK_TAGS or c.find(list(BLOCK_TAGS))):
                if clean("".join(buf)):
                    out.append(clean("".join(buf)))
                buf = []
                walk(c)
            elif isinstance(c, Tag):
                buf.append(c.get_text(" "))
        if clean("".join(buf)):
            out.append(clean("".join(buf)))

    walk(soup.body or soup)
    return out


def pdf_blocks(path: Path) -> list[str]:
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            out.append(f"--- page {i} ---")
            for line in (page.extract_text() or "").splitlines():
                if clean(line):
                    out.append(clean(line))
    return out


def prepare_bank(src: Path, dst: Path) -> int:
    meta = json.loads((src / "meta.json").read_text()) if (src / "meta.json").exists() else {}
    files = [e["file"] for e in meta.get("exhibits", [])] or sorted(
        p.name for p in src.iterdir() if p.suffix.lower() in (".htm", ".html", ".pdf"))
    blocks, n = [], 0
    for fname in files:
        p = src / fname
        texts = pdf_blocks(p) if p.suffix.lower() == ".pdf" else html_blocks(p.read_text(errors="ignore"))
        blocks.append({"id": None, "exhibit": fname, "text": f"===== {fname} ====="})
        for t in texts:
            n += 1
            blocks.append({"id": f"B{n:04d}", "exhibit": fname, "text": t})
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "blocks.json").write_text(json.dumps([b for b in blocks if b["id"]], indent=0))
    lines = [b["text"] if b["id"] is None else f"[{b['id']}] {b['text']}" for b in blocks]
    (dst / "document.txt").write_text("\n".join(lines) + "\n")
    return n


def main():
    only = set(sys.argv[1:])
    if not (ROOT / "filings").exists():
        sys.exit("No filings/ yet: run `python -m beval.fetch` first.")
    for src in sorted((ROOT / "filings").iterdir()):
        if src.is_dir() and (not only or src.name in only):
            n = prepare_bank(src, ROOT / "prepared" / src.name)
            print(f"{src.name}: {n} blocks")


if __name__ == "__main__":
    main()
