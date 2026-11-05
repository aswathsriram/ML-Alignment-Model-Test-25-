# Hindi alignment test: 20 clips

Download **hindi_alignment_20_complete.zip** for the complete reviewed package, original source, full test prefill, weighted JSON/CSV/Excel answer keys, audit, reproducible scripts and validation report.

Individual downloads:

- [Complete ZIP](hindi_alignment_20_complete.zip)
- [Enriched Hindi test JSON](hi_alignment_test_20_enriched.json)
- [Template-format supported subset](decoy_corpus.json)
- [Excel answer key](answer_key.xlsx)

Open a file and click **Download raw file**, or use **Code → Download ZIP** to download the repository.

All original gold data and 240 original answer-key entries are preserved. Missing applicable coverage was filled with 104 additions, producing **405 weighted grading events**. The counts differ from the original 240 because each changed boundary edge is measured separately and other preexisting timing differences are audited. All 20 records needed at least a segmentation addition.

Weights total **50% boundary**, then **10% each** for missing segments, extra segments, wrong words, segmentation, and guideline errors. Individual A1/A2/A3 factors are 3/2/1 within each group. The full answer key documents preserved and newly planted events separately.

The standalone `decoy_corpus.json` is the requested `align-decoy-kit/v1` format: **20 active records, 98 supported injections**. It is a supported subset, not the full 405-event test. Its matching prefill is `alignment_prefill_hi_IN_supported.json` inside the ZIP. The full prefill preserves the original overlaps and text errors; do not interchange the two tests.

Validation passed 405/405 unchanged-decoy, 405/405 gold, 405/405 gold-with-±20 ms-jitter checks, and 20 partial-correction controls. Existing test overlaps are retained; no new ones were introduced. Case errors affect only Latin code-switch tokens; Hindi vowel marks were not treated as removable Spanish-style accents.

No audio was supplied or generated. The gold data and durations are accepted from the source, not independently acoustically verified. Platform import remains untested. See the ZIP README for scoring commands and detailed limitations.
