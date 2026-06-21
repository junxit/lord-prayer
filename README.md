# The Lord's Prayer in Every Language

A growing collection of the Lord's Prayer translated into every language — living and dead. Each language has a plain-text file containing the language's own name (endonym) and two renderings of the prayer.

## Repository layout

```
.
├── README.md          ← this file
└── prayer/            ← one file per language
    ├── INDEX.md       ← index of every language included, with endonyms and review flags
    ├── English.txt
    ├── Spanish.txt
    ├── Mandarin Chinese.txt
    └── … (one [Language].txt per language)
```

Every translation lives in `prayer/`, named `[Language].txt`, where `[Language]` is the name of the language **in English**. New translations are always added to `prayer/`.

## File format

Each `prayer/[Language].txt` contains, in order:

1. **Line 1** — the language's own name for itself (endonym), in its native script.
2. A blank line.
3. `=== Traditional ===` — the recognized traditional/liturgical wording in that language, preserving the canonical line structure and including the doxology as a separate final paragraph.
4. `=== Literal (mirrors the canonical English) ===` — a faithful translation that follows the canonical English wording and clause order. When this would be identical to the Traditional form, it reads: `Same as the Traditional form above.`

All files are UTF-8.

## Canonical reference text

Every translation is kept loyal to this canonical form:

```
Our Father, who art in heaven, hallowed be Thy name.
Thy Kingdom come, Thy will be done, on earth as it is in heaven.
Give us this day our daily bread;
and forgive us our trespasses
as we forgive those who trespass against us;
and lead us not into temptation,
but deliver us from evil.

For thine is the Kingdom, Power and Glory, now and forever. Amen.
```

## Coverage

- **Batch 1 — complete:** the 100 most-spoken living languages.
- **Planned:** further batches of living languages, then historical and dead languages.

See `prayer/INDEX.md` for the full current list with endonyms.

## Sourcing & verification

Translations are verified against published Bible translations (Matthew 6:9–13) and established church liturgies — sources include Bible.com/YouVersion, Omniglot, Wikipedia, and national/denominational liturgical texts. Where a tradition's standard text omits the doxology ("For thine is the Kingdom…", common in Catholic forms), the recognized Protestant/ecumenical doxology is appended so each file matches the canonical form above.

Files that still need human or native-speaker review carry an inline `[UNVERIFIED]` marker. As of Batch 1 these are: **Awadhi**, **Bhojpuri**, **Konkani** (doxology line only — the prayer body is sourced), and **Lao** (full review needed).

## Adding a language

Create `prayer/[English language name].txt` following the file format above, then update `prayer/INDEX.md`.
