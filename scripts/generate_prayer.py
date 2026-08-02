# /// script
# requires-python = ">=3.11"
# ///
"""Generate prayer files from published Scripture hosted by eBible.org.

Downloads a translation's USFM, extracts Matthew 6:9-13 verbatim, and writes a
``prayer/<Language>.txt`` in the repository's format with a ``[Verified from …]``
line naming the edition.

    uv run scripts/generate_prayer.py --census candidates.json   # classify only
    uv run scripts/generate_prayer.py candidates.json            # write the files
    uv run scripts/generate_prayer.py --calibrate                # check against history

Each input record is ``{iso, translationId, english, autonym, title, copyright}``.
A null ``autonym`` writes the marker rather than a guess.

Two extraction paths, because editions differ in how they print the prayer:

**Poetry.** Most editions set it with USFM ``\\q`` markers. That marker does two jobs
no heuristic can do for a language we cannot read: it separates the narrative
introduction of verse 9 ("Pray then like this:") from the prayer proper, and it gives
the per-clause line structure the corpus uses.

**Prose.** Some editions print it as running text with no markers. The content of
Matthew 6:9 is fixed across translations -- 9a introduces, 9b begins the prayer -- so
where the edition prints an explicit boundary there, a colon or an opening quotation
mark, that boundary is the split, and it is the edition's own punctuation rather than
an editorial judgement. Guards require a short introduction and a substantial
remainder; anything else is reported, never guessed at.

No file asserts whether its edition carries the doxology. Editions differ, some print
it as a bracketed textual variant, and some carry it without an "Amen", so any
automatic claim would be wrong for a meaningful share of files.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRAYER_DIR = REPO / "prayer"
UA = "lord-prayer-corpus/1.0 (+https://github.com/junxit/lord-prayer)"
AUTONYM_MARKER = "[autonym not recorded]"

COLON = re.compile(r"[:：︓]")
OPEN_QUOTE = re.compile(r"[\u201c\u2018\u00ab\u300c\u300e\u2039\u201e]")
MAX_INTRO_WORDS = 12
MIN_REMAINDER_WORDS = 3

POETRY, PROSE_BOUNDARY, PROSE_NO_BOUNDARY, NO_MATTHEW, FETCH_FAIL = (
    "POETRY", "PROSE_BOUNDARY", "PROSE_NO_BOUNDARY", "NO_MATTHEW", "FETCH_FAIL")


def fetch(url: str) -> bytes:
    """Fetch a URL with a descriptive User-Agent.

    Args:
        url: URL to retrieve.

    Returns:
        Response body.
    """
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def strip_usfm(text: str) -> str:
    """Remove USFM markup, footnotes and cross-references.

    Args:
        text: Raw USFM.

    Returns:
        Plain text with whitespace collapsed.
    """
    text = re.sub(r"\\f\b.*?\\f\*", "", text, flags=re.S)
    text = re.sub(r"\\x\b.*?\\x\*", "", text, flags=re.S)
    text = re.sub(r"\\rq\b.*?\\rq\*", "", text, flags=re.S)
    text = re.sub(r"\|[^\\]*?(?=\\w\*)", "", text)
    text = re.sub(r"\\\+?[a-zA-Z]+\d*\*?", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def matthew_six(translation_id: str) -> str:
    """Fetch the raw USFM of Matthew chapter 6 for one edition.

    Args:
        translation_id: eBible translation identifier.

    Returns:
        The chapter's raw USFM.

    Raises:
        LookupError: If Matthew or chapter 6 is absent.
    """
    archive = zipfile.ZipFile(io.BytesIO(fetch(f"https://ebible.org/Scriptures/{translation_id}_usfm.zip")))
    names = [n for n in archive.namelist() if re.search(r"(MAT|^41|-MAT)", n, re.I)]
    if not names:
        raise LookupError("no Matthew file in archive")
    raw = archive.read(names[0]).decode("utf-8", errors="replace")
    if "\\c 6" not in raw:
        raise LookupError("no chapter 6")
    return raw.split("\\c 6", 1)[1].split("\\c 7", 1)[0]


def poetry_lines(chapter: str) -> list[str]:
    """Extract the prayer as poetry lines, dropping the narrative introduction.

    Args:
        chapter: Raw USFM of Matthew 6.

    Returns:
        One string per printed line.

    Raises:
        LookupError: If the chapter has no usable poetry structure.
    """
    start, end = chapter.find("\\v 9"), chapter.find("\\v 14")
    if start < 0:
        raise LookupError("no verse 9")
    segment = chapter[start: end if end > start else len(chapter)]
    if "\\q" not in segment:
        raise LookupError("prose edition (no poetry markers)")
    segment = segment[segment.find("\\q"):]   # everything before is the introduction
    lines = []
    for chunk in re.split(r"\\q\d?\b", segment):
        text = strip_usfm(re.sub(r"\\v\s+\d+", " ", chunk))
        if text:
            lines.append(text)
    if len(lines) < 4:
        raise LookupError(f"only {len(lines)} poetry lines")
    return lines


def prose_lines(chapter: str) -> list[str]:
    """Extract the prayer from a prose edition, splitting at its own punctuation.

    Args:
        chapter: Raw USFM of Matthew 6.

    Returns:
        One string per verse, with verse 9's introduction removed.

    Raises:
        LookupError: If a verse is missing or no explicit boundary passes the guards.
    """
    parts = re.split(r"\\v\s+(\d+)", chapter)
    verses: dict[int, str] = {}
    for i in range(1, len(parts) - 1, 2):
        try:
            verses[int(parts[i])] = strip_usfm(parts[i + 1])
        except ValueError:
            continue
    missing = [n for n in range(9, 14) if not verses.get(n)]
    if missing:
        raise LookupError(f"missing verses {missing}")
    for pattern in (COLON, OPEN_QUOTE):
        match = pattern.search(verses[9])
        if not match:
            continue
        head, tail = verses[9][: match.start()].strip(), verses[9][match.end():].strip()
        if 1 <= len(head.split()) <= MAX_INTRO_WORDS and len(tail.split()) >= MIN_REMAINDER_WORDS:
            return [tail] + [verses[n] for n in range(10, 14)]
    raise LookupError("no explicit 9a/9b boundary passing the guards")


def classify(translation_id: str) -> tuple[str, list[str] | None, str]:
    """Decide which extraction path an edition supports.

    Args:
        translation_id: eBible translation identifier.

    Returns:
        A tuple of (verdict, extracted lines or None, detail).
    """
    try:
        chapter = matthew_six(translation_id)
    except LookupError as exc:
        return NO_MATTHEW, None, str(exc)
    except Exception as exc:  # noqa: BLE001 - network and archive failures
        return FETCH_FAIL, None, f"{type(exc).__name__}: {exc}"
    try:
        return POETRY, poetry_lines(chapter), ""
    except LookupError:
        pass
    try:
        return PROSE_BOUNDARY, prose_lines(chapter), ""
    except LookupError as exc:
        return PROSE_NO_BOUNDARY, None, str(exc)


def build(record: dict, verdict: str, lines: list[str]) -> str:
    """Assemble a prayer file in the repository's format.

    Args:
        record: The input record for this language.
        verdict: Which extraction path produced the lines.
        lines: The prayer's lines.

    Returns:
        Complete file contents ending in a single newline.
    """
    note = (
        "Reproduced as printed, including the edition's own line structure."
        if verdict == POETRY else
        "This edition prints the prayer as running prose; the narrative introduction "
        "to verse 9 has been removed at the boundary the edition itself prints, and "
        "the verses are set one per line. No other change was made."
    )
    source = (
        f"[Verified from {record['title']} ({record['translationId']}, "
        f"ISO 639-3 {record['iso']}), {record['copyright']}, Matthew 6:9-13, "
        f"obtained from eBible.org. {note}]"
    )
    return (
        f"{record.get('autonym') or AUTONYM_MARKER}\n\n"
        f"=== Traditional ===\n{source}\n\n"
        + "\n".join(lines)
        + "\n\n=== Literal (mirrors the canonical English) ===\n"
        "Same as the Traditional form above.\n"
    )


def calibrate() -> int:
    """Check the classifier reproduces the decision recorded in existing files.

    Every generated file states in its provenance line which path produced it. A
    disagreement is a bug in the classifier, not a discovery, and must be fixed
    before the classifier is trusted on new languages.

    Returns:
        Process exit code.
    """
    cases = []
    for path in sorted(PRAYER_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        # Only this script's own output records an extraction path. Files backfilled
        # by verify_provenance.py were collated rather than generated, and composed
        # files carry an [UNVERIFIED] note whose text can look like a provenance line.
        if "obtained from eBible.org" not in text or "matches that edition word for word" in text:
            continue
        # The identifier is the bracketed group followed by a comma. Take the last
        # such group before the verse reference: titles carry parentheses of their
        # own ("Indian Revised Version (IRV) Malayalam"), and the first match is
        # frequently one of those rather than the translation id.
        head = text.split(", Matthew 6:9-13", 1)[0]
        ids = re.findall(r"\(([A-Za-z0-9_\-]+)(?:, ISO 639-3 [a-z]{3})?\)(?=,|$)", head)
        if not ids:
            continue
        expected = PROSE_BOUNDARY if "running prose" in text else POETRY
        cases.append((path.stem, ids[-1], expected))

    print(f"calibrating against {len(cases)} generated files", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=8) as pool:
        verdicts = list(pool.map(lambda c: classify(c[1])[0], cases))

    bad = [(n, t, e, g) for (n, t, e), g in zip(cases, verdicts) if g != e]
    for name, tid, expected, got in bad[:20]:
        print(f"  MISMATCH {name} ({tid}): recorded {expected}, classifier says {got}")
    print(f"\nagreed: {len(cases) - len(bad)}/{len(cases)}")
    return 1 if bad else 0


def main() -> int:
    """Census or generate, depending on the flags given."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("candidates", nargs="?", help="JSON list of language records")
    parser.add_argument("--census", action="store_true", help="classify without writing")
    parser.add_argument("--calibrate", action="store_true", help="check against existing files")
    args = parser.parse_args()

    if args.calibrate:
        return calibrate()
    if not args.candidates:
        parser.error("a candidates file is required unless --calibrate is given")

    records = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda r: (r, *classify(r["translationId"])), records))

    tally: dict[str, int] = {}
    written = 0
    for record, verdict, lines, detail in results:
        tally[verdict] = tally.get(verdict, 0) + 1
        if lines and not args.census:
            (PRAYER_DIR / f"{record['english']}.txt").write_text(
                build(record, verdict, lines), encoding="utf-8")
            written += 1
        if verdict in (PROSE_NO_BOUNDARY, NO_MATTHEW, FETCH_FAIL) and args.census:
            print(f"  skip {record['english'][:28]:30} {verdict:18} {detail[:40]}", file=sys.stderr)

    print(f"\ncandidates: {len(records)}")
    for verdict in (POETRY, PROSE_BOUNDARY, PROSE_NO_BOUNDARY, NO_MATTHEW, FETCH_FAIL):
        if tally.get(verdict):
            print(f"  {verdict:18} {tally[verdict]}")
    usable = tally.get(POETRY, 0) + tally.get(PROSE_BOUNDARY, 0)
    print(f"  {'usable':18} {usable}")
    if not args.census:
        print(f"  {'written':18} {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
