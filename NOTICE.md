# Notice: sources, rights and accuracy

This repository reproduces short passages of scripture translated by other people. This file records where that material comes from, what is and is not the compiler's to license, and how a rights holder can get something changed or removed.

*This is a statement of position and practice, not legal advice.*

## What is reproduced

Each file contains **Matthew 6:9–13 — five verses** — in one language, out of roughly 31,000 verses in the Bible. Nothing else from any edition is reproduced.

Five verses is a paradigm short quotation, and it sits well inside the standard permissions thresholds published by major Bible societies, which typically allow quotation up to 500 verses, or 25% of a book, whichever is less, without written permission — subject to attribution. That position depends on attribution actually being present, which is why per-file sourcing is a requirement for new contributions (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Corpora relied on

Translations were taken from, or verified against, material published by:

- United Bible Societies and national Bible societies, including the Bible Society of India
- Wycliffe Bible Translators and SIL, including ScriptureEarth
- Faith Comes By Hearing (Bible.is)
- Asian Sahyogi Sanstha (ASSI), Gorakhpur
- Sociedades Bíblicas Unidas
- The Institute for Bible Translation
- Global Recordings Network
- YouVersion / Bible.com
- Omniglot, Wikipedia, and the christusrex *Pater Noster* collection
- National and denominational liturgical texts, missals and prayer books

Rights in each translation remain with its translators and publishers. See [LICENSE](LICENSE) for the scope of what is licensed here — the compilation, not the underlying translations.

## Copyright status varies by file

Some texts are clearly in the public domain: the 1908 Chamorro *Y Santa Biblia*, classical Nahuatl, and the 1902/1934 Asmara Tigre New Testament, among others.

Others are under active copyright, and four files record it inline:

| File | Rights statement recorded in the file |
|---|---|
| `prayer/Bhojpuri.txt` | © 2007 Asian Sahyogi Sanstha, Gorakhpur |
| `prayer/K'iche'.txt` | © 2011 Wycliffe Bible Translators |
| `prayer/Magahi.txt` | © 2014 Asian Sahyogi Sanstha India (ASSI) |
| `prayer/Yucatec Maya.txt` | © Sociedades Bíblicas Unidas 1992 |

## Provenance coverage is incomplete

**514 of 690 files record their source in the file itself.** Every file from batches 3 to 6 does, plus 24 of the 200 from batches 1 and 2.

Every file added from batch 3 onward carries a `[Verified from …]` line naming the edition, publisher and year, or an explicit marker saying why it does not.

### What the backfill established

Batches 1 and 2 predate that requirement. Rather than label those files with a plausible-looking edition, each was **verified**: `scripts/verify_provenance.py` downloads every candidate New Testament for the language from eBible.org and compares Matthew 6:9–13 against the wording already in the file, word for word.

- **12 files matched a published edition exactly** and now carry a `[Verified from …]` line: Breton, Dutch, Maithili, Mandarin Chinese, Maori, Modern Standard Arabic, Newari, Nigerian Pidgin, Odia, Somali, Tibetan, Tok Pisin.
- **The rest did not.** Around 60 more have a testable edition in the open catalogue, and none matched word for word — differences range from a single word to most of the text.
- The remainder have no edition in that catalogue at all, which carries only freely redistributable translations. Most major-language Bibles are commercially published and absent from it.

### The older claims were audited too

Ten files carried a source note written before this process existed, with no surviving record of how it was checked. They were re-tested with the same tool:

- **Chhattisgarhi and Sylheti** match their cited editions exactly.
- **Kʼicheʼ** matches the 2011 Wycliffe New Orthography edition it cites in every word but one — the file reads *käx* where that edition reads *kꞌäx*. The attribution stands; the variant is noted here rather than silently absorbed.
- **Dogri, Kabyle, Kashmiri, Manipuri, Santali, Saraiki and Tulu** cite editions that are not in the open catalogue, so the tool cannot reach them. Their claims are neither confirmed nor contradicted, and remain as originally written.

A mismatch is information, not failure. Batches 1 and 2 deliberately drew on **liturgical** texts as well as Bible translations, and those will never match a Bible edition: the German file is the ecumenical liturgical *Vater unser*, the Spanish is the Catholic liturgical text, and neither is a rendering of Matthew. Naming a Bible edition for them would be false attribution — worse than recording no source at all.

Identifying the specific liturgy or printing behind each of those files needs a human who knows the tradition. That is the largest outstanding piece of work in this repository, and it is not automatable.

`uv run validate.py` prints the current coverage figure on every run.

## Some text in this repository was composed, not translated

**This is the most important thing on this page for anyone reusing the corpus.**

Where no published translation could be retrieved, some files contain wording composed for this repository. It is marked in the file, but a reuser extracting only the prayer bodies would strip that marking. The current list:

| Files | What was composed |
|---|---|
| `Bhojpuri`, `Bodo`, `Magahi` | The entire prayer body. A published New Testament exists for each; it could not be retrieved. |
| `Banjar` | The Literal section only. The Traditional section is the published Lukan text, verbatim. |
| `Awadhi`, `Konkani` | The doxology only. Both prayer bodies are sourced; neither tradition has a published doxology. |
| `Lao`, `Umbundu` | Later petitions only. Opening verses are confirmed from published texts. |
| `Central Atlas Tamazight`, `Tigre` | Nothing — no wording is given at all. Both record the gap and a retrieval route instead. |

**Composed text must not be treated as scripture or used liturgically.** Each such file names the published edition that should replace it.

Detect these programmatically by testing for the substring `[UNVERIFIED` anywhere in a file. `prayer/INDEX.md` flags the same files, and `uv run validate.py` lists them on every run.

## Corrections and removal

If you hold rights in a translation reproduced here and want it removed, re-sourced, corrected, or attributed differently, **open an issue at https://github.com/junxit/lord-prayer/issues** and it will be actioned promptly and without argument. Removal requests are honoured on request — no justification needed.

The same applies to native speakers who find an error, a mislabelled language, or composed text that misrepresents their language. Corrections from speakers are the most valuable contributions this project can receive.
