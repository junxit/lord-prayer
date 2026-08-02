# /// script
# requires-python = ">=3.11"
# ///
"""Validate the Lord's Prayer corpus and regenerate the derived regions of INDEX.md.

Run ``uv run validate.py`` to check the corpus. The script exits 1 if any error is
found; warnings are reported but do not fail the run. Run ``uv run validate.py
--write-index`` to rewrite the generated regions of ``prayer/INDEX.md`` from the
files on disk.

Every field of an index entry is derivable from the corpus itself: the English name
is the filename stem, the endonym is line 1 of the file, the review flag is the
presence of ``[UNVERIFIED`` anywhere in the file, and the ordinal is the position in
sorted order. The index's prose -- its title, preamble, canonical-text blockquote and
Notes bullets -- is human-authored and is never touched.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent
PRAYER_DIR = REPO / "prayer"
INDEX_PATH = PRAYER_DIR / "INDEX.md"
README_PATH = REPO / "README.md"

TRADITIONAL_HEADER = "=== Traditional ==="
LITERAL_HEADER = "=== Literal (mirrors the canonical English) ==="
FLAG_TOKEN = "[UNVERIFIED"
CANONICAL_FLAG_PREFIX = "[UNVERIFIED — "
FLAG_SUFFIX = "  — [!] contains an UNVERIFIED section (needs human review)"
PROVENANCE_TOKENS = ("[Verified", "(Source:")

SECTION_RE = re.compile(r"^===.*===$")
LANGUAGES_HEADING_RE = re.compile(r"^## Languages \((\d+)\)$")
NEXT_HEADING_RE = re.compile(r"^## ")
CURRENTLY_RE = re.compile(r"(?<=Currently: )[^.]*(?=\.)")
README_TOTAL_RE = re.compile(r"\*\*(\d+) languages complete\.\*\*")
README_FLAGGED_RE = re.compile(r"these are (\d+):")


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


def check_prayer_file(path: Path, report: Report) -> tuple[str, bool, bool] | None:
    """Validate one ``prayer/<Language>.txt`` file against the corpus format.

    The format is fixed: line 1 is the endonym, line 2 is blank, line 3 is the
    Traditional header, then the Traditional body, then the Literal header and its
    body. The Literal body's internal structure is deliberately not constrained --
    several files legitimately vary it.

    Args:
        path: Absolute path to the prayer file.
        report: Report to record findings in.

    Returns:
        A tuple of (endonym, is_flagged, has_provenance), or None if the file is
        malformed enough that the index cannot be built from it.
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

    endonym = lines[0]
    if not endonym.strip():
        report.error(where, "line 1 (endonym) is empty")
    if endonym.startswith("==="):
        report.error(where, "line 1 (endonym) looks like a section header")
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

    return endonym, flagged, has_provenance


def index_line(ordinal: int, name: str, endonym: str, flagged: bool) -> str:
    """Build the canonical INDEX.md entry line for one language.

    Args:
        ordinal: 1-based position in the sorted list.
        name: English language name (the filename stem).
        endonym: The language's own name, taken from line 1 of its file.
        flagged: Whether the file contains an ``[UNVERIFIED`` marker.

    Returns:
        The entry line, without a trailing newline.
    """
    line = f"{ordinal:3d}. {name} — {endonym}"
    return line + FLAG_SUFFIX if flagged else line


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


def build_index_regions(lines: list[str], corpus: dict[str, tuple[str, bool, bool]]) -> list[str]:
    """Return INDEX.md's lines with the three generated regions rewritten.

    Args:
        lines: INDEX.md split into lines.
        corpus: Mapping of English name to (endonym, flagged, has_provenance).

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
        index_line(ordinal, name, corpus[name][0], corpus[name][1])
        for ordinal, name in enumerate(names, start=1)
    ]
    flagged = ", ".join(name for name in names if corpus[name][1])

    rebuilt = list(lines)
    rebuilt[heading] = f"## Languages ({len(names)})"
    rebuilt[heading + 1 : end] = ["", *entries, ""]
    offset = len(rebuilt) - len(lines)
    rebuilt[currently + offset] = CURRENTLY_RE.sub(flagged, rebuilt[currently + offset])
    return rebuilt


def check_index(corpus: dict[str, tuple[str, bool, bool]], report: Report) -> None:
    """Validate INDEX.md against the corpus on disk.

    Args:
        corpus: Mapping of English name to (endonym, flagged, has_provenance).
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
        line.split(" — ", 1)[0].split(". ", 1)[1]
        for line in lines[heading + 1 : end]
        if ". " in line and " — " in line
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


def check_readme(corpus: dict[str, tuple[str, bool, bool]], report: Report) -> None:
    """Validate the counts and flagged-language names stated in README.md.

    README.md is checked but never rewritten: its per-batch grouping of flagged
    languages is editorial and cannot be derived from the corpus.

    Args:
        corpus: Mapping of English name to (endonym, flagged, has_provenance).
        report: Report to record findings in.
    """
    where = rel(README_PATH)
    raw = README_PATH.read_bytes()
    text = check_encoding(raw, where, report)
    if text is None:
        return
    check_whitespace(text, where, report)

    flagged = sorted(name for name, (_, is_flagged, _) in corpus.items() if is_flagged)

    total = README_TOTAL_RE.search(text)
    if total is None:
        report.error(where, "no '**N languages complete.**' claim found")
    elif int(total.group(1)) != len(corpus):
        report.error(where, f"claims {total.group(1)} languages, corpus has {len(corpus)}")

    count = README_FLAGGED_RE.search(text)
    if count is None:
        report.error(where, "no 'these are N:' count of unverified files found")
    elif int(count.group(1)) != len(flagged):
        report.error(where, f"claims {count.group(1)} unverified files, corpus has {len(flagged)}")

    for name in flagged:
        if name not in text:
            report.error(where, f"does not mention unverified language {name}")


def load_corpus(report: Report) -> dict[str, tuple[str, bool, bool]]:
    """Read and validate every prayer file.

    Args:
        report: Report to record findings in.

    Returns:
        Mapping of English name to (endonym, flagged, has_provenance) for each file
        that parsed successfully.
    """
    corpus: dict[str, tuple[str, bool, bool]] = {}
    for path in sorted(PRAYER_DIR.glob("*.txt")):
        parsed = check_prayer_file(path, report)
        if parsed is not None:
            corpus[path.stem] = parsed
    return corpus


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
    args = parser.parse_args()

    report = Report()
    corpus = load_corpus(report)
    if not corpus:
        print("error: no prayer files found", file=sys.stderr)
        return 1

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

    check_index(corpus, report)
    check_readme(corpus, report)

    for warning in report.warnings:
        print(f"warning: {warning}")
    sys.stdout.flush()
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    sys.stderr.flush()

    flagged = sorted(name for name, (_, is_flagged, _) in corpus.items() if is_flagged)
    sourced = sum(1 for _, _, has_provenance in corpus.values() if has_provenance)
    print(f"\nlanguages: {len(corpus)}")
    print(f"provenance: {sourced}/{len(corpus)}")
    print(f"unverified: {len(flagged)}" + (f" ({', '.join(flagged)})" if flagged else ""))
    print(f"errors: {len(report.errors)}, warnings: {len(report.warnings)}")

    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
