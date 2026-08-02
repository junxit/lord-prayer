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
3. `=== Traditional ===` — the recognized traditional/liturgical wording in that language.
4. `=== Literal (mirrors the canonical English) ===` — a faithful translation that follows the canonical English wording and clause order. When this would be identical to the Traditional form, it reads: `Same as the Traditional form above.`

Files may open the Traditional section with a bracketed editorial line — `[Verified from …]` recording the source, or `[UNVERIFIED — …]` recording a gap. Square brackets always mean an editorial statement rather than prayer text.

Two line-structure conventions coexist. Hand-curated files (batches 1–2) follow the canonical line structure and set the doxology as a separate final paragraph. Files reproduced verbatim from a published edition (batch 3 onward) keep that edition's own line structure, so the doxology appears wherever the edition prints it — usually within the last line — and any bracketing in those files is the edition's own. Preserving the printed text was preferred over reformatting it to match, since splitting a clause correctly would mean editing scripture in a language the compiler cannot read.

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

**702 languages.**

- **Batch 1 — complete:** the 100 most-spoken living languages (e.g. Mandarin, Spanish, Hindi, Arabic, Russian, Swahili).
- **Batch 2 — complete:** the next 100 living languages by speakers, folding in major languages such as Odia, Uzbek, Saraiki, Zhuang, and Tibetan; iconic ones including Hebrew and Aramaic/Syriac (the Peshitta text); and a wide spread of European-minority, Southeast Asian, Pacific, African, and Indigenous American languages.
- **Batch 3 — complete:** 100 languages with a published New Testament, ranked by speakers. Candidates come from the [eBible.org](https://ebible.org) translation catalogue joined to Wikidata speaker counts; the text of each is reproduced verbatim from the published edition rather than assembled from secondary sources. Every batch-3 file carries a `[Verified from …]` line naming its edition, publisher and year. The batch spans Malayalam and Eastern Punjabi at the top through Mesoamerican, Amazonian, Melanesian, Philippine, Tanzanian and Romani languages in the tail.
- **Batch 4 — complete:** 92 further living languages, selected for verifiability rather than speaker count. A language qualified only if its edition sets the prayer as poetry, so the narrative introduction to verse 9 separates from the prayer without guesswork, **and** its endonym came from a citable source in the same script as the text. That second test is what keeps line 1 of each file from being an educated guess.
- **Batch 5 — complete:** 213 further living languages. The limit on batches 3 and 4 was never the supply of translations but the supply of *endonyms*: a file cannot be written if line 1 would be a guess. Harvesting autonyms from Wikipedia's language infoboxes raised coverage from 222 languages to 478 and unlocked this batch.
- **Batch 6 — complete:** 85 languages whose editions print the prayer as running prose, with no poetry markers to separate the narrative introduction of verse 9 from the prayer. These are handled the way Malayalam was: the content of Matthew 6:9 is fixed across translations — 9a is the introduction, 9b begins the prayer — so where the edition prints an explicit boundary there, that boundary is the split. Only a colon or opening quotation mark counts, the introduction must be short and the remainder substantial, and each file records where the cut was made. 38 candidates that printed no such boundary were left alone.
- **Batch 7 — complete:** 12 languages recovered from an over-strict filter. Batch 5 rejected any file whose endonym matched its English name, on the reasoning that a true autonym rarely equals the exonym. That holds for a name carrying an English qualifier (*Central Cagayan Agta*) but not for a single-word name like *Tem* or *Warlpiri*, where the autonym genuinely is the name.
- **Planned:** historical and dead languages.

### Why the living-language batches stop at 702

1,225 languages in the [eBible.org](https://ebible.org) catalogue have a published New Testament. 702 are in this corpus. The 603 that are not are blocked for reasons that are recorded rather than glossed over, because the binding constraint is not translations — it is **endonyms**. A file cannot be written if line 1 would be a guess.

| Blocked | Why |
|---:|---|
| 253 | Has an English Wikipedia article, but the article records no autonym |
| 155 | The only "autonym" available is an exonym, an English alternative name, or a country name leaked from an infobox field left empty |
| 143 | No Wikipedia article at all, and no autonym in Wikidata or the catalogue |
| 34 | The published edition contains no Gospel of Matthew |
| 11 | The only autonym is written in a different script from the text |
| 7 | Prose edition printing no explicit boundary between verse 9a and 9b |

Sources tried for autonyms: Wikidata's native-name property, Wikidata labels written in the language itself, English Wikipedia's `Infobox language`, the eBible catalogue's own autonym field, Glottolog and ScriptureEarth. The last two carry reference names and undifferentiated lists of alternative names — Kalagan is listed as "Kaagan, Kalagan, Minuslim, Kinalagan, Isamal, Lupon" with no indication which the speakers use — so neither can settle an endonym.

Unblocking these needs a source that distinguishes an autonym from an exonym, or a speaker who knows. Both are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

Batches 1 and 2 were selected by speaker count. That criterion could not be continued: Ethnologue publishes a ranking only to position 200, and the deeper data is neither free nor machine-readable. Batch 3 therefore ranks by speakers *within* the set of languages that have a published New Testament — which is also the set for which a verbatim, citable text actually exists.

See `prayer/INDEX.md` for the full current list with endonyms.

## Sourcing & verification

Translations are verified against published Bible translations (Matthew 6:9–13) and established church liturgies — sources include Bible.com/YouVersion, Omniglot, Wikipedia, and national/denominational liturgical texts. Where a tradition's standard text omits the doxology ("For thine is the Kingdom…", common in Catholic forms), the recognized Protestant/ecumenical doxology is appended so each file matches the canonical form above.

Files that still need human or native-speaker review carry an inline `[UNVERIFIED]` marker, always as the first line of the section it applies to. As of Batch 2 these are 10: **Awadhi**, **Bhojpuri**, **Konkani**, **Lao** (from Batch 1) and **Banjar**, **Bodo**, **Central Atlas Tamazight**, **Magahi**, **Tigre**, **Umbundu** (from Batch 2).

They are not all unverified in the same way, and the marker says which:

| What the marker says | Files | Meaning |
|---|---|---|
| `composed, not a published translation` | Bhojpuri, Bodo, Magahi; the Literal section of Banjar | The wording was composed for this repo because the published edition could not be retrieved. **Do not treat it as scripture.** Each note names the published edition that should replace it. |
| `composed` (doxology only) | Awadhi, Konkani | The prayer body is sourced; only the appended doxology is composed, because the tradition has no published one. |
| `partly composed` | Lao, Umbundu | Opening verses confirmed from a published text; later petitions are a best-effort reconstruction. |
| `no text` | Central Atlas Tamazight, Tigre | No wording is given at all. A published translation exists but could not be retrieved, and nothing was composed in its place. |

## Adding a language

Create `prayer/[English language name].txt` following the file format above, then regenerate the index:

```bash
uv run validate.py --write-index   # rebuild prayer/INDEX.md from the files on disk
uv run validate.py                 # check the corpus; exits non-zero on any error
```

Do not hand-edit `prayer/INDEX.md` — its language list, count and review-flag markers are generated. Everything else in that file is prose and is left untouched.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before adding a language. It covers what counts as an acceptable source, what to do when a tradition has no doxology, when a distinct Literal rendering is required, and how to flag text that could not be verified.

## Licensing

The compilation is licensed **CC BY 4.0** — see [LICENSE](LICENSE).

That covers the selection, arrangement, endonym research, editorial notes, index and tooling. It does **not** cover the underlying translations of Matthew 6:9–13, which belong to their translators and publishers and are not the compiler's to license. Some are public domain; others remain under active copyright.

[NOTICE.md](NOTICE.md) records the corpora relied on, per-file copyright statements, current provenance coverage, which files contain composed rather than published text, and a contact for rights holders who want material corrected or removed.
