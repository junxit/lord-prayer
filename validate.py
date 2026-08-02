# /// script
# requires-python = ">=3.11"
# ///
"""Validate the Lord's Prayer corpus and regenerate the derived regions of INDEX.md.

Run ``uv run validate.py`` to check the corpus. The script exits 1 if any error is
found; warnings are reported but do not fail the run. Run ``uv run validate.py
--write-index`` to rewrite the generated regions of ``prayer/INDEX.md`` from the
files on disk.

Every field of an index entry is derivable from the corpus itself: the English name
is the filename stem, the autonym is line 1 of the file, the review flag is the
presence of ``[UNVERIFIED`` anywhere in the file, and the ordinal is the position in
sorted order. The index's prose -- its title, preamble, canonical-text blockquote and
Notes bullets -- is human-authored and is never touched.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parent
PRAYER_DIR = REPO / "prayer"
INDEX_PATH = PRAYER_DIR / "INDEX.md"
README_PATH = REPO / "README.md"
NOTICE_PATH = REPO / "NOTICE.md"

TRADITIONAL_HEADER = "=== Traditional ==="
LITERAL_HEADER = "=== Literal (mirrors the canonical English) ==="
FLAG_TOKEN = "[UNVERIFIED"
CANONICAL_FLAG_PREFIX = "[UNVERIFIED — "
FLAG_SUFFIX = "  — [!] contains an UNVERIFIED section (needs human review)"
PROVENANCE_TOKENS = ("[Verified", "(Source:")

# Line 1 of a prayer file is the language's autonym. Where no consulted source
# records one, it is exactly this marker rather than a guess or the English name.
# The wording deliberately avoids "verified" in any casing: PROVENANCE_TOKENS and
# FLAG_TOKEN are matched over the whole file, so a marker containing that word
# would silently inflate the provenance count.
AUTONYM_MARKER = "[autonym not recorded]"

SECTION_RE = re.compile(r"^===.*===$")
LANGUAGES_HEADING_RE = re.compile(r"^## Languages \((\d+)\)$")
NEXT_HEADING_RE = re.compile(r"^## ")
CURRENTLY_RE = re.compile(r"(?<=Currently: )[^.]*(?=\.)")
# Counts are written with thousands separators once the corpus passes 999.
README_TOTAL_RE = re.compile(r"\*\*([\d,]+) languages\b")
README_FLAGGED_RE = re.compile(r"these are (\d+):")
NOTICE_PROVENANCE_RE = re.compile(
    r"\*\*([\d,]+) of ([\d,]+) files record their source in the file itself\.\*\*"
)
NOTICE_AUTONYM_RE = re.compile(r"\*\*([\d,]+) files record no autonym\.\*\*")


# Prayer files live in letter-range shard directories -- prayer/a-h/, prayer/i-o/ --
# because GitHub truncates a directory listing at 1,000 entries. The web UI says so;
# the Contents API does not: it returns the first 1,000 with HTTP 200, no truncation
# flag, and ignores ?page=2. Sharding turns that silent failure into an obvious one.
#
# The directory names ARE the manifest. Boundaries are frozen data in the tree, not
# recomputed here: rebalancing on every change would rename every folder each time the
# shard count changed, moving the whole corpus. Placement stays fully verifiable
# because it is a pure function of a filename and the committed boundaries.
SHARD_RE = re.compile(r"^([a-z])-([a-z])$")
SHARD_WARN_AT = 800
SHARD_HARD_CAP = 1000   # GitHub's per-directory limit
INDEX_ENTRY_RE = re.compile(r"^\s*\d+\. \[(?P<name>[^\]]+)\]\((?P<href>\S+)\) — ")


class Entry(NamedTuple):
    """One language's facts, every one of them derived from its own file."""

    autonym: str
    flagged: bool
    has_provenance: bool
    shard: str   # "" while the corpus is still flat; otherwise the directory name


def count(text: str) -> int:
    """Parse a documented count, tolerating thousands separators.

    Args:
        text: A number as written in prose, e.g. "1,247".

    Returns:
        The integer value.
    """
    return int(text.replace(",", ""))


def shard_key(stem: str) -> str:
    """Fold a filename stem to the key that decides its shard.

    Lowercasing must precede stripping. Stripping first removes the initial capital
    of every name -- "Ashaninka" would become "shaninka" and file under s.

    Args:
        stem: A filename stem, e.g. "'Auhelawa".

    Returns:
        The shard key, e.g. "auhelawa". Empty if the stem has no ASCII letters.
    """
    text = unicodedata.normalize("NFD", stem).lower()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"^[^a-z]+", "", text)


def shard_bounds(names: list[str]) -> list[tuple[str, str, str]]:
    """Turn shard directory names into ordered lower bounds.

    Membership is decided by lower bound alone: shard i owns keys k where
    lo_i <= k < lo_i+1. The upper letter in a directory name is derived and
    decorative, which is what makes the ranges contiguous and exhaustive by
    construction, and gives a home to letters no language currently starts with.

    Args:
        names: Shard directory names, e.g. ["a-h", "i-o", "p-z"].

    Returns:
        Tuples of (name, lower bound, exclusive upper bound), in order. The final
        upper bound is "{" -- the codepoint after "z".
    """
    ordered = sorted(names, key=lambda n: n.split("-")[0])
    lows = [n.split("-")[0] for n in ordered]
    uppers = lows[1:] + ["{"]
    return list(zip(ordered, lows, uppers))


def shard_for(stem: str, bounds: list[tuple[str, str, str]]) -> str | None:
    """Find the shard a filename belongs in.

    Args:
        stem: A filename stem.
        bounds: The output of :func:`shard_bounds`.

    Returns:
        The shard directory name, or None if the stem has no usable key.
    """
    key = shard_key(stem)
    if not key:
        return None
    for name, low, high in bounds:
        if low <= key[0] < high:
            return name
    return bounds[-1][0] if bounds else None


class Report:
    """Accumulates errors and warnings keyed by the file they were found in."""

    def __init__(self) -> None:
        """Initialise an empty report."""
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        """Record a failure that must block the run.

        Args:
            where: Repo-relative path the problem was found in.
            message: What is wrong, phrased so it can be acted on directly.
        """
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        """Record an advisory that is reported but does not block the run.

        Args:
            where: Repo-relative path the observation relates to.
            message: What was observed.
        """
        self.warnings.append(f"{where}: {message}")


def rel(path: Path) -> str:
    """Return a path relative to the repo root for use in messages.

    Args:
        path: Absolute path inside the repository.

    Returns:
        The repo-relative path as a string.
    """
    return str(path.relative_to(REPO))


def check_encoding(raw: bytes, where: str, report: Report) -> str | None:
    """Check byte-level hygiene shared by every text file in the repo.

    Enforces UTF-8 without a BOM, LF-only line endings, and exactly one trailing
    newline with no trailing blank line.

    Args:
        raw: Raw file bytes.
        where: Repo-relative path, for error messages.
        report: Report to record findings in.

    Returns:
        The decoded text, or None if the file could not be decoded.
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        report.error(where, "starts with a UTF-8 BOM")
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        report.error(where, f"is not valid UTF-8 ({exc})")
        return None
    if b"\r" in raw:
        report.error(where, "contains CR; line endings must be LF only")
    if not raw.endswith(b"\n"):
        report.error(where, "does not end with a newline")
    elif raw.endswith(b"\n\n"):
        report.error(where, "ends with a blank line; expected exactly one trailing newline")
    return text


def check_whitespace(text: str, where: str, report: Report) -> None:
    """Check for tabs, trailing whitespace and runs of consecutive blank lines.

    Args:
        text: Decoded file contents.
        where: Repo-relative path, for error messages.
        report: Report to record findings in.
    """
    lines = text.split("\n")
    for number, line in enumerate(lines, start=1):
        if "\t" in line:
            report.error(where, f"line {number} contains a tab")
        if line != line.rstrip():
            report.error(where, f"line {number} has trailing whitespace")
    for number in range(1, len(lines)):
        if not lines[number - 1].strip() and not lines[number].strip():
            report.error(where, f"line {number + 1} is the second of two consecutive blank lines")
            break


def paragraphs(block: str) -> list[str]:
    """Split a block of text into blank-line-separated paragraphs.

    Args:
        block: Text to split.

    Returns:
        The non-empty paragraphs, in order.
    """
    return [part for part in re.split(r"\n\s*\n", block.strip()) if part.strip()]


def check_prayer_file(path: Path, report: Report) -> Entry | None:
    """Validate one ``prayer/<Language>.txt`` file against the corpus format.

    The format is fixed: line 1 is the autonym, line 2 is blank, line 3 is the
    Traditional header, then the Traditional body, then the Literal header and its
    body. The Literal body's internal structure is deliberately not constrained --
    several files legitimately vary it.

    Line 1 may instead be exactly ``AUTONYM_MARKER``, recording that no consulted
    source gives the language's own name for itself. Any other bracketed value is an
    error rather than a warning: this construct has no legacy files, so a typo would
    otherwise create a second, silently distinct value across hundreds of index lines.

    Args:
        path: Absolute path to the prayer file.
        report: Report to record findings in.

    Returns:
        The language's Entry, or None if the file is malformed enough that the
        index cannot be built from it.
    """
    where = rel(path)
    stem = path.stem

    if stem != stem.strip():
        report.error(where, "filename stem has leading or trailing whitespace")
    if unicodedata.normalize("NFC", stem) != stem:
        report.error(where, "filename is not NFC-normalised")
    if not stem.isascii():
        report.warn(where, "filename contains non-ASCII characters")

    raw = path.read_bytes()
    text = check_encoding(raw, where, report)
    if text is None:
        return None
    check_whitespace(text, where, report)

    lines = text.split("\n")
    if len(lines) < 5:
        report.error(where, "is too short to contain both sections")
        return None

    autonym = lines[0]
    if not autonym.strip():
        report.error(where, "line 1 (autonym) is empty")
    if autonym.startswith("==="):
        report.error(where, "line 1 (autonym) looks like a section header")
    if autonym.startswith("[") and autonym != AUTONYM_MARKER:
        report.error(where, f"line 1 is bracketed but is not exactly {AUTONYM_MARKER!r}")
    if lines[1].strip():
        report.error(where, "line 2 must be blank")
    if lines[2] != TRADITIONAL_HEADER:
        report.error(where, f"line 3 must be exactly {TRADITIONAL_HEADER!r}")
        return None

    headers = [n for n, line in enumerate(lines) if SECTION_RE.match(line)]
    if len(headers) != 2:
        report.error(where, f"expected exactly 2 section headers, found {len(headers)}")
        return None
    if lines[headers[1]] != LITERAL_HEADER:
        report.error(where, f"second header must be exactly {LITERAL_HEADER!r}")
        return None
    if lines[headers[1] - 1].strip():
        report.error(where, "the Literal header must be preceded by a blank line")

    traditional = "\n".join(lines[headers[0] + 1 : headers[1]])
    literal = "\n".join(lines[headers[1] + 1 :])
    if not traditional.strip():
        report.error(where, "the Traditional section is empty")
    elif len(paragraphs(traditional)) < 2:
        report.error(where, "the Traditional section must have at least 2 paragraphs")
    if not literal.strip():
        report.error(where, "the Literal section is empty")

    flagged = FLAG_TOKEN in text
    for number, line in enumerate(lines, start=1):
        for column in (n for n in range(len(line)) if line.startswith(FLAG_TOKEN, n)):
            if not line.startswith(CANONICAL_FLAG_PREFIX, column):
                report.warn(where, f"line {number} flag is not in canonical '{CANONICAL_FLAG_PREFIX}...]' form")
    has_provenance = any(token in text for token in PROVENANCE_TOKENS)

    shard = path.parent.name if path.parent != PRAYER_DIR else ""
    return Entry(autonym, flagged, has_provenance, shard)


def index_line(ordinal: int, name: str, entry: Entry) -> str:
    """Build the canonical INDEX.md entry line for one language.

    The name is a link, because the index is the only complete listing of the corpus
    -- no directory view shows every language once the corpus passes 1,000 files.
    The target is percent-encoded: an unencoded space makes Markdown render the whole
    thing as literal text rather than a link.

    A trailing AUTONYM_MARKER is safe here. An unmatched ``[...]`` is a shortcut
    reference, and with no matching definition anywhere in INDEX.md it falls back to
    literal text -- which is already how several hundred entries render.

    Args:
        ordinal: 1-based position in the sorted list.
        name: English language name (the filename stem).
        entry: The language's facts, including the shard its file sits in.

    Returns:
        The entry line, without a trailing newline.
    """
    href = urllib.parse.quote(f"{name}.txt", safe="")
    if entry.shard:
        href = f"{entry.shard}/{href}"
    line = f"{ordinal:3d}. [{name}]({href}) — {entry.autonym}"
    return line + FLAG_SUFFIX if entry.flagged else line


def locate_index_regions(lines: list[str], report: Report) -> tuple[int, int, int] | None:
    """Find the three generated regions of INDEX.md by structure, not by markers.

    Args:
        lines: INDEX.md split into lines.
        report: Report to record findings in.

    Returns:
        A tuple of (heading index, end-of-entries index, Currently-bullet index), or
        None if any anchor is missing. Entries occupy the half-open range between the
        heading and the end index.
    """
    where = rel(INDEX_PATH)
    heading = next((n for n, line in enumerate(lines) if LANGUAGES_HEADING_RE.match(line)), None)
    if heading is None:
        report.error(where, "no '## Languages (N)' heading found")
        return None
    end = next(
        (n for n in range(heading + 1, len(lines)) if NEXT_HEADING_RE.match(lines[n])),
        len(lines),
    )
    currently = next((n for n, line in enumerate(lines) if CURRENTLY_RE.search(line)), None)
    if currently is None:
        report.error(where, "no 'Currently: ...' bullet found in the Notes section")
        return None
    return heading, end, currently


def build_index_regions(lines: list[str], corpus: dict[str, Entry]) -> list[str]:
    """Return INDEX.md's lines with the three generated regions rewritten.

    Args:
        lines: INDEX.md split into lines.
        corpus: Mapping of English name to its Entry.

    Returns:
        The rewritten lines. Everything outside the three regions is preserved.

    Raises:
        ValueError: If an anchor cannot be located.
    """
    report = Report()
    located = locate_index_regions(lines, report)
    if located is None:
        raise ValueError("; ".join(report.errors))
    heading, end, currently = located

    names = sorted(corpus)
    entries = [
        index_line(ordinal, name, corpus[name])
        for ordinal, name in enumerate(names, start=1)
    ]
    flagged = ", ".join(name for name in names if corpus[name].flagged)

    rebuilt = list(lines)
    rebuilt[heading] = f"## Languages ({len(names)})"
    rebuilt[heading + 1 : end] = ["", *entries, ""]
    offset = len(rebuilt) - len(lines)
    rebuilt[currently + offset] = CURRENTLY_RE.sub(flagged, rebuilt[currently + offset])
    return rebuilt


def check_index(corpus: dict[str, Entry], report: Report) -> None:
    """Validate INDEX.md against the corpus on disk.

    Args:
        corpus: Mapping of English name to its Entry.
        report: Report to record findings in.
    """
    where = rel(INDEX_PATH)
    raw = INDEX_PATH.read_bytes()
    text = check_encoding(raw, where, report)
    if text is None:
        return
    check_whitespace(text, where, report)

    lines = text.split("\n")
    located = locate_index_regions(lines, report)
    if located is None:
        return

    try:
        expected = build_index_regions(lines, corpus)
    except ValueError as exc:
        report.error(where, str(exc))
        return

    heading, end, _ = located
    listed = {
        match["name"]
        for line in lines[heading + 1 : end]
        if (match := INDEX_ENTRY_RE.match(line))
    }
    missing = sorted(set(corpus) - listed)
    orphans = sorted(listed - set(corpus))
    if missing:
        report.error(where, f"missing entries for: {', '.join(missing)}")
    if orphans:
        report.error(where, f"has entries with no matching file: {', '.join(orphans)}")

    if lines != expected and not missing and not orphans:
        for number, (actual, wanted) in enumerate(zip(lines, expected), start=1):
            if actual != wanted:
                report.error(where, f"line {number} is {actual!r}, expected {wanted!r}")
        if len(lines) != len(expected):
            report.error(where, f"has {len(lines)} lines, expected {len(expected)}")


def check_readme(corpus: dict[str, Entry], report: Report) -> None:
    """Validate the counts and flagged-language names stated in README.md.

    README.md is checked but never rewritten: its per-batch grouping of flagged
    languages is editorial and cannot be derived from the corpus.

    Args:
        corpus: Mapping of English name to its Entry.
        report: Report to record findings in.
    """
    where = rel(README_PATH)
    raw = README_PATH.read_bytes()
    text = check_encoding(raw, where, report)
    if text is None:
        return
    check_whitespace(text, where, report)

    flagged = sorted(name for name, e in corpus.items() if e.flagged)

    total = README_TOTAL_RE.search(text)
    if total is None:
        report.error(where, "no '**N languages ...**' count claim found")
    elif count(total.group(1)) != len(corpus):
        report.error(where, f"claims {total.group(1)} languages, corpus has {len(corpus)}")

    flagged_claim = README_FLAGGED_RE.search(text)
    if flagged_claim is None:
        report.error(where, "no 'these are N:' count of unverified files found")
    elif int(flagged_claim.group(1)) != len(flagged):
        report.error(
            where,
            f"claims {flagged_claim.group(1)} unverified files, corpus has {len(flagged)}",
        )

    for name in flagged:
        if name not in text:
            report.error(where, f"does not mention unverified language {name}")


def check_notice(corpus: dict[str, Entry], report: Report) -> None:
    """Validate the coverage figures stated in NOTICE.md.

    NOTICE.md is the document a rights holder reads, and it publishes provenance and
    autonym coverage. Nothing checked those figures before, so they could drift from
    the corpus indefinitely.

    Args:
        corpus: Mapping of English name to its Entry.
        report: Report to record findings in.
    """
    where = rel(NOTICE_PATH)
    raw = NOTICE_PATH.read_bytes()
    text = check_encoding(raw, where, report)
    if text is None:
        return
    check_whitespace(text, where, report)

    sourced = sum(1 for e in corpus.values() if e.has_provenance)
    unnamed = sum(1 for e in corpus.values() if e.autonym == AUTONYM_MARKER)

    claim = NOTICE_PROVENANCE_RE.search(text)
    if claim is None:
        report.error(where, "no '**N of M files record their source...**' claim found")
    elif (count(claim.group(1)), count(claim.group(2))) != (sourced, len(corpus)):
        report.error(
            where,
            f"claims {claim.group(1)} of {claim.group(2)} sourced, corpus has "
            f"{sourced} of {len(corpus)}",
        )

    autonym_claim = NOTICE_AUTONYM_RE.search(text)
    if unnamed and autonym_claim is None:
        report.error(where, f"{unnamed} files carry the autonym marker but NOTICE.md is silent")
    elif autonym_claim is not None and count(autonym_claim.group(1)) != unnamed:
        report.error(
            where,
            f"claims {autonym_claim.group(1)} files record no autonym, corpus has {unnamed}",
        )


def prayer_files() -> list[Path]:
    """List every prayer file, wherever it sits.

    Both layouts are accepted while the corpus is being migrated into shards: a file
    directly in ``prayer/`` and a file inside a shard directory are equally valid.

    Returns:
        Paths, sorted by filename stem so the index order does not depend on layout.
    """
    return sorted(PRAYER_DIR.glob("**/*.txt"), key=lambda p: p.stem)


def check_doc_filenames(corpus: dict[str, Entry], report: Report) -> None:
    """Check that every prayer file named in prose actually exists.

    Documentation names files without their shard -- `Spanish.txt`, never
    `prayer/p-z/Spanish.txt` -- so that a reshard can never turn prose into a lie.
    This verifies the other half of that bargain: the bare name must resolve.

    Args:
        corpus: Mapping of English name to its Entry.
        report: Report to record findings in.
    """
    for path in (README_PATH, NOTICE_PATH, REPO / "CONTRIBUTING.md"):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for named in sorted(set(re.findall(r"`([^`/\n]+)\.txt`", text))):
            if "[" in named:
                continue   # a template placeholder such as `[Language].txt`
            if named not in corpus:
                report.error(rel(path), f"names `{named}.txt`, which is not in the corpus")
        for slashed in sorted(set(re.findall(r"`(prayer/[^`\n]*\.txt)`", text))):
            if "[" in slashed:
                continue   # a template placeholder such as `prayer/[Language].txt`
            report.error(rel(path), f"names a path with a shard in it, `{slashed}` -- "
                                    f"prose should name the file alone so a reshard "
                                    f"cannot invalidate it")


def load_corpus(report: Report) -> dict[str, Entry]:
    """Read and validate every prayer file.

    A stem appearing in more than one place is an error rather than a silent
    overwrite: the corpus is keyed by stem, so a second copy would displace the first
    and make every published count quietly wrong.

    Args:
        report: Report to record findings in.

    Returns:
        Mapping of English name to its Entry, for each file that parsed successfully.
    """
    seen: dict[str, list[Path]] = {}
    for path in prayer_files():
        seen.setdefault(path.stem, []).append(path)
    for stem, paths in sorted(seen.items()):
        if len(paths) > 1:
            report.error(rel(paths[0]), f"{stem} also exists at " +
                         ", ".join(rel(p) for p in paths[1:]))

    corpus: dict[str, Entry] = {}
    for path in prayer_files():
        parsed = check_prayer_file(path, report)
        if parsed is not None:
            corpus[path.stem] = parsed
    return corpus


def check_shards(report: Report) -> None:
    """Check the shard layout, where the corpus has been sharded.

    Verifies only what the committed directory names claim: that each is a valid
    range, that every file sits in the shard its name selects, and that no shard is
    near GitHub's per-directory limit. Boundaries are not recomputed -- they are
    frozen data, and rebalancing them on every change would move the whole corpus
    each time the shard count changed.

    Args:
        report: Report to record findings in.
    """
    where = rel(PRAYER_DIR)
    directories = sorted(p for p in PRAYER_DIR.iterdir() if p.is_dir())
    if not directories:
        report.error(where, "holds no shard directories; run 'validate.py --reshard'")
        return

    # A file left directly in prayer/ would still be found by the recursive glob, but
    # it would sit outside every shard and outside the layout the index describes.
    stray = sorted(p.name for p in PRAYER_DIR.glob("*.txt"))
    if stray:
        report.error(where, f"holds .txt files directly rather than in a shard: "
                            f"{', '.join(stray[:5])}"
                            + (f" and {len(stray) - 5} more" if len(stray) > 5 else ""))

    bad = [d.name for d in directories if not SHARD_RE.match(d.name)]
    if bad:
        report.error(where, f"subdirectories are not valid shard ranges: {', '.join(bad)}")
        return

    bounds = shard_bounds([d.name for d in directories])
    if bounds[0][1] != "a":
        report.error(where, f"the first shard must start at 'a', not {bounds[0][1]!r}")
    for name, low, high in bounds:
        derived = "z" if high == "{" else chr(ord(high) - 1)
        if name != f"{low}-{derived}":
            report.error(where, f"shard {name!r} should be named {f'{low}-{derived}'!r} "
                                f"-- the upper letter is derived from the next shard")

    for path in prayer_files():
        if path.parent == PRAYER_DIR:
            continue   # already reported as stray
        want = shard_for(path.stem, bounds)
        if want and path.parent.name != want:
            report.error(rel(path), f"belongs in shard {want}, not {path.parent.name}")

    for directory in directories:
        n = len(list(directory.glob("*.txt")))
        if n >= SHARD_HARD_CAP:
            report.error(rel(directory), f"holds {n} files, at or over GitHub's "
                                         f"{SHARD_HARD_CAP}-entry directory limit")
        elif n > SHARD_WARN_AT:
            report.warn(rel(directory), f"holds {n} files; reshard before {SHARD_HARD_CAP}")


def plan_shards(stems: list[str], target: int = 400) -> list[tuple[str, str]]:
    """Compute a fresh, balanced shard layout for a set of filenames.

    Used only by ``--reshard``, which is a deliberate and rare operation. The layout
    is the minimax contiguous partition of the letter histogram: binary-search the
    smallest capacity that fits the target number of shards, then pack greedily.

    Args:
        stems: Every filename stem in the corpus.
        target: Preferred files per shard; sets how many shards are aimed for.

    Returns:
        Tuples of (shard name, lower bound), in order.

    Raises:
        SystemExit: If one letter alone reaches the hard cap, which the single-letter
            scheme cannot express and which needs a human decision, not a fallback.
    """
    histogram: dict[str, int] = {}
    for stem in stems:
        key = shard_key(stem)
        histogram[key[0]] = histogram.get(key[0], 0) + 1
    letters = sorted(histogram)
    sizes = [histogram[letter] for letter in letters]
    if max(sizes) >= SHARD_HARD_CAP:
        worst = letters[sizes.index(max(sizes))]
        raise SystemExit(
            f"letter {worst!r} alone has {max(sizes)} files, at or over the "
            f"{SHARD_HARD_CAP}-entry limit. The single-letter shard scheme is "
            f"exhausted; this needs a deliberate redesign, not an automatic fallback."
        )

    wanted = max(1, -(-sum(sizes) // target))

    def bins(cap: int) -> int:
        used, current = 1, 0
        for size in sizes:
            if current and current + size > cap:
                used, current = used + 1, 0
            current += size
        return used

    low, high = max(sizes), sum(sizes)
    while low < high:
        middle = (low + high) // 2
        if bins(middle) <= wanted:
            high = middle
        else:
            low = middle + 1

    starts, current = [letters[0]], 0
    for letter, size in zip(letters, sizes):
        if current and current + size > low:
            starts.append(letter)
            current = 0
        current += size
    uppers = starts[1:] + ["{"]
    return [(f"{s}-{'z' if u == '{' else chr(ord(u) - 1)}", s) for s, u in zip(starts, uppers)]


def main() -> int:
    """Run the validator, or regenerate INDEX.md when asked.

    Returns:
        Process exit code: 0 on success, 1 if any error was recorded.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write-index",
        action="store_true",
        help="rewrite the generated regions of prayer/INDEX.md and exit",
    )
    parser.add_argument(
        "--reshard",
        action="store_true",
        help="recompute the shard layout and move every file into it, then exit",
    )
    args = parser.parse_args()

    report = Report()
    corpus = load_corpus(report)
    if not corpus:
        print("error: no prayer files found", file=sys.stderr)
        return 1

    if args.reshard:
        if report.errors:
            for error in report.errors:
                print(f"error: {error}", file=sys.stderr)
            print("\nrefusing to reshard: fix the errors above first", file=sys.stderr)
            return 1
        layout = plan_shards(sorted(corpus))
        bounds = shard_bounds([name for name, _ in layout])
        for name, _ in layout:
            (PRAYER_DIR / name).mkdir(exist_ok=True)
        moved = 0
        for path in prayer_files():
            want = shard_for(path.stem, bounds)
            destination = PRAYER_DIR / want / path.name
            if path != destination:
                path.rename(destination)
                moved += 1
        for directory in sorted(p for p in PRAYER_DIR.iterdir() if p.is_dir()):
            if not any(directory.iterdir()):
                directory.rmdir()
        lines = INDEX_PATH.read_text(encoding="utf-8").split("\n")
        INDEX_PATH.write_text(
            "\n".join(build_index_regions(lines, load_corpus(Report()))), encoding="utf-8")
        print(f"moved {moved} files into {len(layout)} shards: "
              f"{', '.join(name for name, _ in layout)}")
        print("now run: git add -A")
        return 0

    if args.write_index:
        lines = INDEX_PATH.read_text(encoding="utf-8").split("\n")
        try:
            rebuilt = build_index_regions(lines, corpus)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        INDEX_PATH.write_text("\n".join(rebuilt), encoding="utf-8")
        print(f"wrote {rel(INDEX_PATH)} ({len(corpus)} languages)")
        return 0

    check_shards(report)
    check_index(corpus, report)
    check_readme(corpus, report)
    check_notice(corpus, report)
    check_doc_filenames(corpus, report)

    for warning in report.warnings:
        print(f"warning: {warning}")
    sys.stdout.flush()
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    sys.stderr.flush()

    flagged = sorted(name for name, e in corpus.items() if e.flagged)
    sourced = sum(1 for e in corpus.values() if e.has_provenance)
    named = sum(1 for e in corpus.values() if e.autonym != AUTONYM_MARKER)
    print(f"\nlanguages: {len(corpus)}")
    print(f"autonym: {named}/{len(corpus)}")
    print(f"provenance: {sourced}/{len(corpus)}")
    print(f"unverified: {len(flagged)}" + (f" ({', '.join(flagged)})" if flagged else ""))
    print(f"errors: {len(report.errors)}, warnings: {len(report.warnings)}")

    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
