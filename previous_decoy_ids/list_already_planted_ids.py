#!/usr/bin/env python3
"""
The files behind the "Already planted" line of each strict delivery: files that already had decoys in the earlier
decoy file of that language when the new batch came in.

  Spanish      counted over the whole new zip (926 files): 734, of which 621 also got a new decoy
  Portuguese, German, French, Italian   counted over the files that got a new decoy: 301, 264, 96, 100

Writes already_planted_ids.csv and already_planted_ids.json next to this script.
Run: python previous_decoy_ids/list_already_planted_ids.py
"""
import csv, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SETS = {      # language: (new decoy file, dropped list of the new batch, earlier decoy file, counted over the whole zip?)
    "es_ES": ("spanish_decoys_2026-11-22/es_ES_decoy_plants.json", "spanish_decoys_2026-11-22/es_ES_dropped.csv",
              "spanish_deliveries_decoys/spanish_deliveries_decoy_plants.json", True),
    "pt_BR": ("portuguese_decoys_2026-11-22/pt_BR_decoy_plants.json", "portuguese_decoys_2026-11-22/pt_BR_dropped.csv",
              "portuguese_decoys/portuguese_decoy_plants.json", False),
    "de_DE": ("german_decoys_2026-11-23/de_DE_all_decoy_plants.json", "german_decoys_2026-11-23/de_DE_all_dropped.csv",
              "german_decoys/german_decoy_plants.json", False),
    "fr_FR": ("french_decoys_2026-11-23/fr_FR_decoy_plants.json", "french_decoys_2026-11-23/fr_FR_dropped.csv",
              "french_decoys/french_decoy_plants.json", False),
    "it_IT": ("italian_decoys_2026-11-23/it_IT_decoy_plants.json", "italian_decoys_2026-11-23/it_IT_dropped.csv",
              "italian_decoys/italian_decoys_plants.json", False),
}


def decoys(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))["decoys"]


def name_of(d):
    return d.get("file_name") or re.sub(r"^it_\d+_", "", d["decoy_ref"]).split(" [")[0]


rows, ids = [], {}
for lang, (new, dropped, old, whole_zip) in SETS.items():
    new_name = {d["work_item_id"]: name_of(d) for d in decoys(new)}
    left_out = {r["work_item_id"]: r["file_name"] for r in csv.DictReader(open(ROOT / dropped, encoding="utf-8-sig"))}
    planted = {d["work_item_id"]: name_of(d) for d in decoys(old) if d["plants"]}
    batch = {**left_out, **new_name} if whole_zip else new_name
    hit = sorted((w for w in planted if w in batch), key=lambda w: (batch[w], w))
    ids[lang] = hit
    rows += [{"language": lang, "work_item_id": w, "file_name": batch[w], "earlier_decoy_file": old,
              "has_new_decoy": "yes" if w in new_name else "no"} for w in hit]
    print(f"{lang}: {len(hit):4d} already planted | with a new decoy {sum(w in new_name for w in hit):4d} | "
          f"without {sum(w not in new_name for w in hit):4d}")

with open(HERE / "already_planted_ids.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
(HERE / "already_planted_ids.json").write_text(json.dumps(
    {"what": "work_item_id of every file that already had decoys in the earlier decoy file of its language "
             "(the 'Already planted' line of each strict delivery)",
     "counts": {k: len(v) for k, v in ids.items()}, "work_item_ids": ids}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("total", len(rows))
