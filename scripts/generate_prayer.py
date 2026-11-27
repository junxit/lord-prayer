# /// script
# requires-python = ">=3.15"
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
the per-clause line structure the corpus uses. A paragraph that follows the last line
inside verse 13 is narrative ("This is how you should pray," said Jesus) and is cut,
unless it carries the doxology or the close of the prayer's own quotation.

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

import argparse
import io
import json
import re
import sys
import unicodedata
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from itertools import batched
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRAYER_DIR = REPO / "prayer"


UA = "lord-prayer-corpus/1.0 (+https://github.com/junxit/lord-prayer)"
AUTONYM_MARKER = "[autonym not recorded]"

ID_MAT = re.compile(r"^\ufeff?\\id\s+MAT\b", re.I | re.M)
VERSE_RE = re.compile(r"\\v\s+(\d+(?:-\d+)?)")
POETRY_LINE = re.compile(r"\\q\d?\b")
# Paragraph markers; \b, a stanza break inside poetry, is not one.
PARAGRAPH = re.compile(r"\\(?:p|m|mi|nb|pc|pr|po|pi\d?|pm[ocr]?|li\d?|ph\d?)\b")
# A colon between a Latin-script letter and a lowercase one is part of a word in
# orthographies that mark vowel length with it (Beami "sia:ma", "A:ma"), and one
# between digits is a printed verse reference. Neither is a 9a/9b boundary. A colon
# before a capital is one, even with the space missing (Dutch "aldus:Onze").
LATIN = r"A-Za-z\u00C0-\u02AF\u0300-\u036F\u1E00-\u1EFF"
LOWER_LATIN = rf"(?![A-Z\u00C0-\u00D6\u00D8-\u00DE])[{LATIN}]"
COLON = re.compile(rf"(?!(?<=\d):(?=\d))(?!(?<=[{LATIN}]):(?={LOWER_LATIN}))[:：︓]")
INTRO_END = re.compile(r"[:：︓፦]\W*$")
OPEN_QUOTE = re.compile(r"[\u201c\u2018\u00ab\u300c\u300e\u2039\u201e]")
CLOSE_FOR = {
    "\u201c": ("\u201d",),
    "\u2018": ("\u2019",),
    "\u00ab": ("\u00bb",),
    "\u300c": ("\u300d",),
    "\u300e": ("\u300f",),
    "\u2039": ("\u203a",),
    "\u201e": ("\u201c", "\u201d"),
}
QUOTE_MARKS = set(CLOSE_FOR) | {mark for closers in CLOSE_FOR.values() for mark in closers}
# What strip_usfm() removes, for walking the printed text while keeping raw offsets.
HIDDEN = re.compile(
    r"\\(?:fe?|x|rq|fig)\b.*?\\(?:fe?|x|rq|fig)\*|\|[^\\]*?(?=\\\+?(?:w|rb)\*)|\\\+?[a-zA-Z]+\d*\*?",
    re.S,
)
DIALOGUE_DASHES = ("\u2015", "\u2014", "\u2013")
MAX_INTRO_WORDS = 12
MIN_REMAINDER_WORDS = 3

POETRY, PROSE_BOUNDARY, PROSE_NO_BOUNDARY, NO_MATTHEW, FETCH_FAIL = (
    "POETRY", "PROSE_BOUNDARY", "PROSE_NO_BOUNDARY", "NO_MATTHEW", "FETCH_FAIL")


def prayer_files() -> list[Path]:
    """List every prayer file, in a shard directory or directly in prayer/.

    Returns:
        Paths, sorted by filename stem.
    """
    return sorted(PRAYER_DIR.glob("**/*.txt"), key=lambda p: p.stem)


def target_path(english: str) -> Path:
    """Decide where a language's file belongs.

    An existing file keeps its place, so regenerating never leaves a second copy in
    another shard -- the corpus is keyed by filename stem, and a duplicate would
    silently displace the original. A new language goes into the shard its name
    selects, or directly into prayer/ while the corpus is still flat.

    Args:
        english: The language's English name.

    Returns:
        The path to write.
    """
    folded = english.casefold()
    for path in prayer_files():
        if path.stem.casefold() == folded:
            return path
    shards = sorted(d.name for d in PRAYER_DIR.iterdir()
                    if d.is_dir() and re.match(r"^[a-z]-[a-z]$", d.name))
    if not shards:
        return PRAYER_DIR / f"{english}.txt"
    key = unicodedata.normalize("NFD", english).lower()
    key = re.sub(r"^[^a-z]+", "", "".join(c for c in key if not unicodedata.combining(c)))
    lows = [s.split("-")[0] for s in shards]
    uppers = lows[1:] + ["{"]
    for name, low, high in zip(shards, lows, uppers):
        if key and low <= key[0] < high:
            return PRAYER_DIR / name / f"{english}.txt"
    return PRAYER_DIR / shards[-1] / f"{english}.txt"


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
    """Remove USFM markup, footnotes, figures and cross-references.

    Args:
        text: Raw USFM.

    Returns:
        Plain text with whitespace collapsed.
    """
    text = re.sub(r"\\fe?\b.*?\\fe?\*", "", text, flags=re.S)
    text = re.sub(r"\\x\b.*?\\x\*", "", text, flags=re.S)
    text = re.sub(r"\\rq\b.*?\\rq\*", "", text, flags=re.S)
    text = re.sub(r"\\fig\b.*?\\fig\*", "", text, flags=re.S)
    text = re.sub(r"\|[^\\]*?(?=\\\+?(?:w|rb)\*)", "", text)
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
    candidates = sorted(
        (n for n in archive.namelist() if not n.endswith("/")),
        key=lambda n: (0 if "mat" in n.lower() else 1, n),
    )
    raw = next(
        (
            text
            for name in candidates
            if ID_MAT.search((text := archive.read(name).decode("utf-8", errors="replace"))[:512])
        ),
        None,
    )
    if raw is None:
        raise LookupError("no Matthew file in archive")
    if "\\c 6" not in raw:
        raise LookupError("no chapter 6")
    return raw.split("\\c 6", 1)[1].split("\\c 7", 1)[0]


def verse_span(chapter: str) -> tuple[int, int]:
    """Locate verses 9-13: where verse 9 starts and where the next verse begins.

    Args:
        chapter: Raw USFM of Matthew 6.

    Returns:
        The offsets of verse 9's marker and of the first verse after 13 (or the
        chapter's end).

    Raises:
        LookupError: If verse 9 is not marked on its own, or a verse range runs
            past verse 13 and so would carry verse 14 into the prayer.
    """
    start, end = -1, len(chapter)
    for match in VERSE_RE.finditer(chapter):
        first, _, last = match.group(1).partition("-")
        first, last = int(first), int(last or first)
        if first <= 13 < last:
            raise LookupError(f"verse range {match.group(1)} runs past verse 13")
        if start < 0 and first == 9:
            start = match.start()
        elif start >= 0 and first >= 14:
            end = match.start()
            break
    if start < 0:
        raise LookupError("no verse 9")
    return start, end


def address_lines(preamble: str) -> list[str]:
    """Recover an opening address set as a paragraph before the first poetry line.

    Some editions print verse 9's narrative introduction, then the address ("Our
    Father in heaven,") as a paragraph of its own, and start the poetry on the next
    clause. The address is kept only when the introduction visibly ends first, at a
    colon; otherwise everything before the first poetry line is introduction.

    Args:
        preamble: Raw USFM from verse 9's marker to the first poetry line.

    Returns:
        The address lines, often none.
    """
    intro, *paragraphs = PARAGRAPH.split(preamble)
    if not INTRO_END.search(strip_usfm(VERSE_RE.sub(" ", intro))):
        return []
    lines = []
    for part in paragraphs:
        cleaned = strip_usfm(VERSE_RE.sub(" ", part))
        if cleaned and not INTRO_END.search(cleaned):
            lines.append(cleaned)
    return lines


def printed_text(segment: str) -> list[tuple[int, str]]:
    """List the characters a reader sees, with their offsets in the raw USFM.

    Args:
        segment: Raw USFM.

    Returns:
        (offset, character) pairs in order, without markup, notes or figures.
    """
    printed, pos = [], 0
    for hidden in HIDDEN.finditer(segment):
        printed.extend((i, segment[i]) for i in range(pos, hidden.start()))
        pos = hidden.end()
    printed.extend((i, segment[i]) for i in range(pos, len(segment)))
    return printed


def quotation_marks(printed: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Pick out the quotation marks from printed text.

    A mark between two letters is skipped: it is an apostrophe or a glottal stop.

    Args:
        printed: Output of printed_text().

    Returns:
        (offset, mark) pairs in order.
    """
    marks = []
    for k, (offset, char) in enumerate(printed):
        if char not in QUOTE_MARKS:
            continue
        before = printed[k - 1][1] if k else " "
        after = printed[k + 1][1] if k + 1 < len(printed) else " "
        if not (before.isalpha() and after.isalpha()):
            marks.append((offset, char))
    return marks


def prayer_end(segment: str, first_line: int, last_line: int) -> int:
    """Find where the prayer ends after its last poetry line.

    Many editions follow the last line, still inside verse 13, with a paragraph of
    narrative ("This is how you should pray," said Jesus) or a lead-in to verse 14.
    That paragraph is cut. It is kept when it carries a textual note, the way
    editions mark the doxology as a variant, or is a bracketed variant. When the
    prayer's own quotation is still open at the paragraph, the paragraph is kept up
    to the mark that closes it (Dawro "Amen.'"), and dropped if it never closes
    there. That quotation is the one opened between the introduction's last word and
    the prayer's first, not one opened earlier for the rest of Jesus's speech.

    Args:
        segment: Raw USFM of verses 9-13.
        first_line: Offset in the segment of the first poetry line's marker.
        last_line: Offset in the segment where the last poetry line with text starts.

    Returns:
        The offset at which the prayer ends.
    """
    anchor = max((m.end() for m in VERSE_RE.finditer(segment, last_line)), default=last_line)
    paragraph = PARAGRAPH.search(segment, anchor)
    if not paragraph:
        return len(segment)
    after = segment[paragraph.start():]
    if re.search(r"\\fe?\s", after) or strip_usfm(after).startswith("["):
        return len(segment)
    printed = printed_text(segment)
    letters = [offset for offset, char in printed if char.isalpha()]
    intro_end = max((offset for offset in letters if offset < first_line), default=-1)
    first_word = min((offset for offset in letters if offset >= first_line), default=len(segment))
    stack: list[str] = []
    level = None
    marks = quotation_marks(printed)
    for offset, mark in marks:
        if offset >= paragraph.start():
            break
        if stack and mark in CLOSE_FOR[stack[-1]]:
            stack.pop()
        elif mark in CLOSE_FOR:
            stack.append(mark)
            if intro_end < offset < first_word:
                level = len(stack)
    if level is None or len(stack) < level:
        return paragraph.start()
    for offset, mark in marks:
        if offset < paragraph.start():
            continue
        if stack and mark in CLOSE_FOR[stack[-1]]:
            stack.pop()
            if len(stack) < level:
                return offset + 1
        elif mark in CLOSE_FOR:
            stack.append(mark)
    return paragraph.start()


def poetry_lines(chapter: str) -> list[str]:
    """Extract the prayer as poetry lines, dropping the narrative introduction.

    Args:
        chapter: Raw USFM of Matthew 6.

    Returns:
        One string per printed line.

    Raises:
        LookupError: If the chapter has no usable poetry structure.
    """
    start, end = verse_span(chapter)
    segment = chapter[start:end]
    if "\\q" not in segment:
        raise LookupError("prose edition (no poetry markers)")
    first_q = segment.find("\\q")
    lines = address_lines(segment[:first_q])
    # The last poetry line with text: some editions end the prayer with an empty \q.
    starts = [m.end() for m in POETRY_LINE.finditer(segment)]
    ends = [m.start() for m in POETRY_LINE.finditer(segment)][1:] + [len(segment)]
    last_line = max((s for s, e in zip(starts, ends) if strip_usfm(VERSE_RE.sub(" ", segment[s:e]))),
                    default=first_q)
    for chunk in POETRY_LINE.split(segment[first_q: prayer_end(segment, first_q, last_line)]):
        text = strip_usfm(VERSE_RE.sub(" ", chunk))
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
        LookupError: If a verse is missing, a verse range runs past verse 13, or no
            explicit boundary passes the guards.
    """
    parts = VERSE_RE.split(chapter)
    verses: dict[int, str] = {}
    covered: set[int] = set()
    for spec, body in batched(parts[1:], 2, strict=True):
        first, _, last = spec.partition("-")
        first, last = int(first), int(last or first)
        if first <= 13 < last:
            raise LookupError(f"verse range {spec} runs past verse 13")
        cleaned = strip_usfm(body)
        if cleaned:
            verses[first] = cleaned
            covered.update(range(first, last + 1))
    missing = [n for n in range(9, 14) if n not in covered]
    if missing or 9 not in verses:
        raise LookupError(f"missing verses {missing or [9]}")
    return [prayer_start(verses[9])] + [verses[n] for n in range(10, 14) if n in verses]


def prayer_start(verse: str) -> str:
    """Remove verse 9's narrative introduction at the boundary the edition prints.

    Args:
        verse: Verse 9 as plain text.

    Returns:
        The verse from the start of the prayer.

    Raises:
        LookupError: If no colon or opening quotation mark passes the guards.
    """
    for pattern in (COLON, OPEN_QUOTE):
        skipped: set[int] = set()
        for match in pattern.finditer(verse):
            if match.start() in skipped:
                continue
            head, rest = verse[: match.start()].strip(), verse[match.end():]
            tail = rest.strip()
            if not (1 <= len(head.split()) <= MAX_INTRO_WORDS and len(tail.split()) >= MIN_REMAINDER_WORDS):
                continue
            if pattern is COLON and tail.startswith(DIALOGUE_DASHES) and COLON.search(rest):
                # Spanish-style editions open the prayer itself with a dash after the
                # colon. But when the dashed speech has a colon of its own (Lacandon:
                # "Jesus said: [dash] I will teach you. Pray. Say to God: Our Father"),
                # it may be a longer introduction, so no colon is trusted.
                break
            if pattern is OPEN_QUOTE:
                closers = CLOSE_FOR[match.group()]
                closed_at = min((i for c in closers if (i := rest.find(c)) >= 0), default=-1)
                reopened_at = rest.find(match.group())
                if 0 <= closed_at < reopened_at and not any(c in rest[reopened_at + 1:] for c in closers):
                    # A quotation inside the introduction, closed before the prayer's
                    # own unclosed one opens (Inoke). Skip it, and the mark closing it,
                    # which in German-style quoting is the English opening mark.
                    skipped.add(match.end() + closed_at)
                    continue
            return tail
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


def recorded_lines(text: str) -> list[str]:
    """Read the prayer lines of a generated file, after its provenance line.

    Args:
        text: Contents of a prayer file written by build().

    Returns:
        The Traditional section's lines, without the provenance line.
    """
    section = text.split("=== Traditional ===", 1)[1].split("=== Literal", 1)[0]
    return [line for line in section.splitlines() if line.strip()][1:]


def calibrate() -> int:
    """Check the classifier reproduces the decision and the text of existing files.

    Every generated file states in its provenance line which path produced it, and
    carries the lines that path extracted. A disagreement in either is a bug in the
    classifier, not a discovery, and must be fixed before the classifier is trusted
    on new languages. Checking the verdict alone misses a change in the extraction
    rules that alters the text of files already in the corpus.

    Returns:
        Process exit code.
    """
    cases = []
    for path in prayer_files():
        text = path.read_text(encoding="utf-8")
        # Only this script's own unedited output records an extraction path. Files
        # backfilled by verify_provenance.py were collated rather than generated,
        # hand-curated prose editions record the specific editorial changes made, and
        # composed files carry an [UNVERIFIED] note.
        if "obtained from eBible.org" not in text:
            continue
        if "Reproduced as printed" not in text and "No other change was made." not in text:
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
        cases.append((path.stem, ids[-1], expected, recorded_lines(text)))

    print(f"calibrating against {len(cases)} generated files", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda c: classify(c[1])[:2], cases))

    bad = []
    for (name, tid, expected, recorded), (verdict, lines) in zip(cases, results):
        if verdict != expected:
            bad.append(f"MISMATCH {name} ({tid}): recorded {expected}, classifier says {verdict}")
        elif lines != recorded:
            line = next((i for i, pair in enumerate(zip(lines, recorded), 1) if pair[0] != pair[1]),
                        min(len(lines), len(recorded)) + 1)
            bad.append(f"TEXT MISMATCH {name} ({tid}): extraction differs from the file at prayer line {line}")
    for message in bad[:20]:
        print(f"  {message}")
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
            target_path(record["english"]).write_text(
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
