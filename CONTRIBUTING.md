# Contributing

This repo collects the Lord's Prayer in as many languages as can be sourced honestly. The hard part is not the file format — it is knowing what counts as a real translation and what to do when one does not exist. Most of this document is about that.

Before opening a PR:

```bash
uv run validate.py --write-index   # rebuild prayer/INDEX.md from the files on disk
uv run validate.py                 # must exit 0
```

## The file format

One file per language: `prayer/[English language name].txt`. The English name is the filename; the language's own name goes inside.

```
Deutsch                                          ← line 1: endonym, in its native script
                                                 ← line 2: blank
=== Traditional ===                              ← line 3: exactly this
Vater unser im Himmel,                           ← the recognized liturgical wording
geheiligt werde dein Name.
…
                                                 ← blank line
Denn dein ist das Reich …  Amen.                 ← doxology, its own paragraph
                                                 ← blank line
=== Literal (mirrors the canonical English) ===  ← exactly this, parenthetical included
Same as the Traditional form above.
```

Rules the validator enforces:

- UTF-8, no BOM, LF line endings, exactly one trailing newline, no trailing blank line.
- No tabs, no trailing whitespace, no two consecutive blank lines.
- Line 1 is the endonym and is not empty. Line 2 is blank. Line 3 is `=== Traditional ===`.
- Exactly two section headers, Traditional first, both spelled exactly as above.
- The Traditional section has at least two paragraphs — the prayer, then the doxology.
- The Literal section is not empty. Its internal shape is deliberately unconstrained; several languages legitimately vary it.
- Filenames are ASCII, NFC-normalised, and use a plain ASCII apostrophe (`K'iche'.txt`).

Endonyms use a parenthetical only to disambiguate or romanize: `Akan (Twi)`, `客家話 (Hak-kâ-fa)`, `کٲشُر (कॉशुर)`.

## Where the text must come from

**Tier 1 — a published Bible translation** of Matthew 6:9–13, quoted verbatim. Name the edition, publisher and year.

**Tier 2 — an established liturgical text** of that tradition: a missal, prayer book, catechism or service book, quoted verbatim.

**Tier 3 — a reputable secondary compilation** (Omniglot, the christusrex *Pater Noster* collection, Wikipedia), and only when the underlying edition can be named. "Found on a prayer website" is not a source.

**Never acceptable:** machine translation, back-translation from English, or text taken from a *related* language.

> **The worked example.** The "Central Atlas Tamazight" Lord's Prayer circulating online — including on prayer aggregator sites — is in fact **Kabyle**, a different language. Anyone assembling this repo from secondary sources would have filed it under Tamazight and been wrong. `prayer/Central Atlas Tamazight.txt` records the trap; `prayer/Kabyle.txt` holds the actual Kabyle text. Check that a secondary source's language label matches the ISO code and the script you expect.

Record the source as the first line of the Traditional section, followed by a blank line:

```
[Verified from the Dogri New Testament (नमां नियम, Free Bibles India / Bible Society work), Matthew 6:9-13.]
```

**Only cite an edition the text actually came from.** If you are adding provenance to an existing file rather than a new one, verify it first:

```bash
uv run scripts/verify_provenance.py Somali        # compare against published editions
uv run scripts/verify_provenance.py --apply       # record only exact matches
```

The tool compares the file's wording against Matthew 6:9–13 in every eBible edition for that language and reports how many words differ. It writes a source line only on an exact word-for-word match. A near miss means the text came from somewhere else — a liturgy, or a different printing — and must not be attributed to the edition tested.

## When no published text exists

This is the situation that produces bad data, so the rules are strict.

**You may submit composed text, but it must be labelled.** Put the marker as the first line of the section it applies to, and make `composed` the first thing it says:

```
[UNVERIFIED — composed, not a published translation. <Name the published edition that should replace this, and why it could not be retrieved.>]
```

Naming the edition matters: it turns a defect into a work item for whoever fixes it. `prayer/Magahi.txt` and `prayer/Bodo.txt` are the models — both name the exact fileset and publisher that should supersede them.

Use the variants when they fit: `[UNVERIFIED — partly composed. …]` when only some petitions are reconstructed, and `[UNVERIFIED — no text. …]` when you are submitting a record of the gap and no wording at all. `prayer/Tigre.txt` is the model for the last case, and it is a perfectly good contribution — an honest gap with a retrieval route beats invented scripture.

**Before concluding a text cannot be retrieved,** try ScriptureEarth (downloadable USFM and PDF, which bypass JavaScript readers), YouVersion's version list for the ISO code, archive.org, and a plain `curl` with a browser User-Agent. Several existing gaps in this repo exist only because a Bible.is reader is a JavaScript app behind a key-gated API — not because the translation is missing.

## The doxology

The canonical form includes "For thine is the Kingdom, Power and Glory, now and forever. Amen." Many traditions — most Catholic forms, and the shorter Lukan form — do not.

If the tradition's standard text omits it, append a **published** doxology in that language: from the same Bible's other printing, from the liturgy's embolism, or from a Protestant edition. Mark where it came from.

**If no published doxology exists in that language, omit it and say so. Do not compose one.**

```
[No doxology in the Lukan form or in any published Banjar text; omitted rather than composed.]
```

`prayer/Banjar.txt` is the model. Its published Scripture covers only Luke and John, so it carries the shorter Lukan prayer verbatim and simply records that the remaining lines do not exist in Banjar.

## The Literal section

Use the exact string `Same as the Traditional form above.` only when the Traditional wording already follows the canonical English clause order and omits nothing. About four in five files qualify.

Supply a genuinely distinct Literal when the Traditional is a free or liturgical rendering that reorders, merges or drops clauses:

- `prayer/Spanish.txt` — the liturgical text reorders the kingdom/will clauses; the Literal restores canonical order.
- `prayer/Italian.txt` — the 2008 revision reads *non abbandonarci alla tentazione*; the Literal keeps the older *non indurci in tentazione*.
- `prayer/Japanese.txt` — Traditional is the Catholic 共同訳, Literal the Protestant 口語訳.
- `prayer/Cantonese.txt` — Traditional is the Chinese Union Version in written Mandarin; the Literal is genuine written Cantonese.

A short caveat may follow the boilerplate on the same line, in parentheses.

## Brackets versus parentheses

**Square brackets are editorial** — statements by the compiler about the text: `[Verified from …]`, `[UNVERIFIED — …]`, `[No doxology in …]`.

**Parentheses are supplementary** — part of the material itself: transliterations, script labels, textual-variant notes, and a trailing `(Source: …)` paragraph.

Never put prayer text in square brackets. A reader scanning for the prayer must be able to skip every `[…]` and lose nothing.

## Do not hand-edit `prayer/INDEX.md`

Its language list, count, and review-flag markers are generated from the files on disk. Run `uv run validate.py --write-index`. The title, preamble, canonical-text blockquote and Notes bullets are prose and are never touched by the generator — edit those by hand.

CI fails a PR whose index is out of date.

## Copyright

Submit only the five verses (Matthew 6:9–13), never a whole chapter. Always name the edition and rights holder. Do not submit text you lack the right to quote. See [NOTICE.md](NOTICE.md) for the repo's position and its rights-holder contact.

## Decision flow

```mermaid
flowchart TD
    A[New language] --> B{Published Bible or<br/>liturgical text found?}
    B -->|Yes| C["Quote verbatim<br/>Add [Verified from …]"]
    B -->|No| D{Exhausted ScriptureEarth,<br/>YouVersion, archive.org,<br/>browser-UA curl?}
    D -->|No| E[Keep looking]
    E --> B
    D -->|Yes| F{Submit composed text?}
    F -->|No| G["[UNVERIFIED — no text. …]<br/>Record the gap + retrieval route"]
    F -->|Yes| H["[UNVERIFIED — composed, …]<br/>Name the edition that replaces it"]
    C --> I{Does the tradition<br/>have a doxology?}
    H --> I
    I -->|Published one exists| J[Append it, note the source]
    I -->|None exists| K["[No doxology in …;<br/>omitted rather than composed.]"]
    J --> L{Traditional follows canonical<br/>English order, omits nothing?}
    K --> L
    L -->|Yes| M["Same as the Traditional form above."]
    L -->|No| N[Write a distinct Literal]
    G --> O
    M --> O[uv run validate.py --write-index]
    N --> O
    O --> P[uv run validate.py → must exit 0]
```
