# /// script
# requires-python = ">=3.11"
# ///
"""Check a prayer file's text against published editions, and record the source.

Provenance may only be added to a file whose wording actually came from the edition
being cited. This tool does not label files; it *verifies* them. For each language it
downloads every candidate New Testament from eBible.org, extracts Matthew 6:9-13, and
compares it word for word against the text already in the file.

    uv run scripts/verify_provenance.py                 # report on every unsourced file
    uv run scripts/verify_provenance.py Somali Breton   # report on named languages
    uv run scripts/verify_provenance.py --apply         # write [Verified from ...] lines

Only exact word-for-word matches are written. A file whose text differs from the
edition by even one word is reported, never attributed: batches 1 and 2 drew on
liturgical texts as well as Bible translations, so a mismatch usually means the
wording came from a liturgy or a different printing, which this tool cannot identify.

Comparison folds case, punctuation and zero-width joiners, since editions differ in
all three without differing in wording.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import io
import re
import sys
import unicodedata
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRAYER_DIR = REPO / "prayer"
CATALOGUE = "https://ebible.org/Scriptures/translations.csv"
UA = "lord-prayer-corpus/1.0 (+https://github.com/junxit/lord-prayer)"
HEADER = "=== Traditional ==="
ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}


def fetch(url: str) -> bytes:
    """Fetch a URL with a descriptive User-Agent.

    Args:
        url: URL to retrieve.

    Returns:
        The response body.
    """
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def normalise(name: str) -> str:
    """Reduce a language name to a comparison key.

    Args:
        name: A language name from either the repo or the catalogue.

    Returns:
        Lowercase alphabetic tokens, with SIL-style "Chinese, Mandarin" inverted.
    """
    text = name.strip().lower()
    if "," in text:
        text = " ".join(reversed([part.strip() for part in text.split(",")]))
    text = re.sub(r"\(.*?\)", " ", text)
    return " ".join(re.sub(r"[^a-z ]", " ", text).split())


def words(text: str) -> list[str]:
    """Split text into comparison tokens, folding case, punctuation and joiners.

    Args:
        text: Text to tokenise.

    Returns:
        The comparison tokens.
    """
    text = unicodedata.normalize("NFC", text).lower()
    text = "".join(ch for ch in text if ord(ch) not in ZERO_WIDTH)
    text = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text)
    return text.split()


def strip_usfm(text: str) -> str:
    """Remove USFM markup, footnotes and cross-references.

    Args:
        text: Raw USFM.

    Returns:
        Plain text with whitespace collapsed.
    """
    text = re.sub(r"\\f\b.*?\\f\*", "", text, flags=re.S)
    text = re.sub(r"\\x\b.*?\\x\*", "", text, flags=re.S)
    text = re.sub(r"\|[^\\]*?(?=\\w\*)", "", text)
    text = re.sub(r"\\\+?[a-zA-Z]+\d*\*?", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def edition_prayer(translation_id: str) -> str:
    """Fetch Matthew 6:9-13 from an eBible edition.

    Args:
        translation_id: eBible translation identifier.

    Returns:
        The five verses joined into one string.

    Raises:
        LookupError: If Matthew, chapter 6 or the verses are absent.
    """
    archive = zipfile.ZipFile(io.BytesIO(fetch(f"https://ebible.org/Scriptures/{translation_id}_usfm.zip")))
    names = [n for n in archive.namelist() if re.search(r"(MAT|^41|-MAT)", n, re.I)]
    if not names:
        raise LookupError("no Matthew file")
    raw = archive.read(names[0]).decode("utf-8", errors="replace")
    if "\\c 6" not in raw:
        raise LookupError("no chapter 6")
    chapter = raw.split("\\c 6", 1)[1].split("\\c 7", 1)[0]
    parts = re.split(r"\\v\s+(\d+)", chapter)
    verses: dict[int, str] = {}
    for i in range(1, len(parts) - 1, 2):
        try:
            verses[int(parts[i])] = strip_usfm(parts[i + 1])
        except ValueError:
            continue
    found = [verses.get(n, "") for n in range(9, 14)]
    if not any(found):
        raise LookupError("verses 9-13 absent")
    return " ".join(found)


def file_prayer(path: Path) -> list[list[str]]:
    """Read a file's Traditional text as comparison tokens.

    Bracketed editorial lines are dropped. Both the whole section and its first
    paragraph are returned, since a file may append a doxology the edition lacks.

    Args:
        path: A prayer file.

    Returns:
        One or two token lists to try.
    """
    text = path.read_text(encoding="utf-8")
    section = text.split(HEADER, 1)[1].split("=== Literal", 1)[0]
    kept = "\n".join(ln for ln in section.split("\n") if not ln.strip().startswith("["))
    paragraphs = [p for p in re.split(r"\n\s*\n", kept.strip()) if p.strip()]
    candidates = [words(kept)]
    if paragraphs:
        candidates.append(words(paragraphs[0]))
    return [c for c in candidates if c]


def compare(path: Path, translation_id: str) -> tuple[float, int]:
    """Compare a file's wording against one edition.

    Args:
        path: A prayer file.
        translation_id: eBible translation identifier.

    Returns:
        The best (coverage, number of unmatched words) over the candidate texts.
    """
    edition = words(edition_prayer(translation_id))
    best = (-1.0, 10**6)
    for candidate in file_prayer(path):
        matcher = difflib.SequenceMatcher(None, candidate, edition, autojunk=False)
        covered = sum(block.size for block in matcher.get_matching_blocks())
        missing = sum(a2 - a1 for op, a1, a2, _, _ in matcher.get_opcodes() if op in ("replace", "delete"))
        if (covered / len(candidate), -missing) > (best[0], -best[1]):
            best = (covered / len(candidate), missing)
    return best


def catalogue() -> dict[str, list[dict]]:
    """Download the eBible catalogue, indexed by normalised English language name.

    Returns:
        Mapping of normalised name to the editions that contain a New Testament.
    """
    rows = csv.DictReader(io.StringIO(fetch(CATALOGUE).decode("utf-8-sig")))
    index: dict[str, list[dict]] = {}
    for row in rows:
        try:
            if int(row.get("NTbooks") or 0) <= 0:
                continue
        except ValueError:
            continue
        index.setdefault(normalise(row["languageNameInEnglish"] or ""), []).append(row)
    return index


def provenance_line(row: dict) -> str:
    """Compose the bracketed provenance line for a verified file.

    Args:
        row: The matching catalogue row.

    Returns:
        The full bracketed line.
    """
    rights = (row.get("Copyright") or "").replace("Copyright ", "").strip()
    return (
        f"[Verified from {row['title']} ({row['translationId']}), "
        f"{rights + ', ' if rights else ''}Matthew 6:9-13. The wording in this file "
        f"matches that edition word for word; collated against the text published at eBible.org.]"
    )


def main() -> int:
    """Verify the requested files and, with --apply, record confirmed sources."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("languages", nargs="*", help="English language names; default is every unsourced file")
    parser.add_argument("--apply", action="store_true", help="write provenance lines for exact matches")
    args = parser.parse_args()

    if args.languages:
        targets = [PRAYER_DIR / f"{name}.txt" for name in args.languages]
        missing = [p for p in targets if not p.exists()]
        if missing:
            print(f"no such file: {', '.join(p.name for p in missing)}", file=sys.stderr)
            return 1
    else:
        targets = [
            p for p in sorted(PRAYER_DIR.glob("*.txt"))
            if "[Verified" not in p.read_text(encoding="utf-8")
            and "(Source:" not in p.read_text(encoding="utf-8")
        ]

    index = catalogue()
    jobs = [(p, row) for p in targets for row in index.get(normalise(p.stem), [])]
    if not jobs:
        print("no candidate editions found for the requested files")
        return 0

    def run(job):
        path, row = job
        try:
            coverage, missing = compare(path, row["translationId"])
        except Exception as exc:  # noqa: BLE001 - reported per row
            return path, row, -1.0, 10**6, str(exc)[:40]
        return path, row, coverage, missing, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, jobs))

    best: dict[Path, tuple] = {}
    for path, row, coverage, missing, error in results:
        current = best.get(path)
        if current is None or (coverage, -missing) > (current[1], -current[2]):
            best[path] = (row, coverage, missing, error)

    exact = applied = 0
    print(f"{'file':26} {'match':>7} {'diff':>5}  edition")
    print("-" * 78)
    for path in sorted(best, key=lambda p: p.stem):
        row, coverage, missing, error = best[path]
        verdict = "EXACT" if missing == 0 and coverage >= 0.999 else f"{missing} words differ"
        print(f"{path.stem[:26]:26} {coverage:>7.3f} {missing if missing < 10**6 else '-':>5}  "
              f"{row['translationId'][:14]:14} {error or verdict}")
        if missing == 0 and coverage >= 0.999:
            exact += 1
            if args.apply:
                text = path.read_text(encoding="utf-8")
                if "[Verified" in text or "(Source:" in text:
                    continue
                head, sep, rest = text.partition(HEADER + "\n")
                if sep:
                    path.write_text(f"{head}{sep}{provenance_line(row)}\n\n{rest}", encoding="utf-8")
                    applied += 1

    print(f"\nchecked {len(best)} languages against {len(jobs)} editions")
    print(f"exact word-for-word matches: {exact}")
    if args.apply:
        print(f"provenance lines written:    {applied}")
    else:
        print("re-run with --apply to record the confirmed sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
