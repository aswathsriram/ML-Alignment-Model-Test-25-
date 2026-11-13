# Chinese (cn_ZH) decoys (platform delivery)

Input: `deliveries/…_SO-71310-20260915-20260919.json` (93 work items, one character per segment).
Run: `python chinese_decoys/build_chinese.py`. It uses `german_decoys/build_german.py` with Chinese settings.

- `chinese_decoy_plants.json`: 90 decoys in the align-decoys/v1 format, keyed on `work_item_id` (plus `file_name`),
  laid out like the German / Portuguese / French / Spanish plants files.
- `chinese_skipped.json`: the 3 work items with no segments (entirely synthetic), skipped.

2-3 mistakes per file (266 in all), at least 3 characters apart, 1 "critical": true per file. Only four kinds:
- boundary mismatch: `move`, minor 40-80 ms, major 100-300 ms, critical 310-700 ms (40 each)
- missing word: `delete` (character gone) 32 · missing segment: `remove` (text kept, no chip) 21
- hallucinated word: `add`, an extra chip in a pause of at least 0.35 s 32
- wrong transcription, one character: homophone (的 / 地 / 得, 在 / 再, 到 / 道 ...) 34, or the traditional form of a
  simplified character (国 -> 國, 说 -> 說; zh_CN is written in simplified characters) 27

No split / join, punctuation, capital-letter, digit or speaker-flag mistakes.
