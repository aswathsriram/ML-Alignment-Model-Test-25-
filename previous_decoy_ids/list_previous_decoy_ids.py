#!/usr/bin/env python3
"""
Which files of the new (strict) decoy sets already had decoys in the earlier sets — five languages.

For each language the work_item_id of every decoy in the earlier file(s) is compared with the new file:
  previous_decoys_also_in_new_files.csv / .json   files with a decoy in BOTH an earlier set and the new set
  previous_decoys_not_in_new_files.csv            the rest of the earlier decoys (no decoy in the new set)

Run: python previous_decoy_ids/list_previous_decoy_ids.py
"""
import csv, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SETS = {      # language: (new file, [earlier files])
    "es_ES": ("spanish_decoys_2026-11-22/es_ES_decoy_plants.json",
              ["spanish_deliveries_decoys/spanish_deliveries_decoy_plants.json", "spanish_decoys_v1/spanish_decoy_plants.json"]),
    "pt_BR": ("portuguese_decoys_2026-11-22/pt_BR_decoy_plants.json", ["portuguese_decoys/portuguese_decoy_plants.json"]),
    "de_DE": ("german_decoys_2026-11-23/de_DE_all_decoy_plants.json", ["german_decoys/german_decoy_plants.json"]),
    "fr_FR": ("french_decoys_2026-11-23/fr_FR_decoy_plants.json", ["french_decoys/french_decoy_plants.json"]),
    "it_IT": ("italian_decoys_2026-11-23/it_IT_decoy_plants.json", ["italian_decoys/italian_decoys_plants.json"]),
}


def decoys(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))["decoys"]


def name_of(d):
    # no file_name: the earlier Italian set (decoy_ref it_004_<name>) and shared names in the new one (<name> [id])
    return d.get("file_name") or re.sub(r"^it_\d+_", "", d["decoy_ref"]).split(" [")[0]


both, rest, ids = [], [], {}
for lang, (new, olds) in SETS.items():
    new_name = {d["work_item_id"]: name_of(d) for d in decoys(new)}
    where, old_name = {}, {}
    for old in olds:
        for d in decoys(old):
            wid = d.get("work_item_id") or d["file_id"]          # the 297-file Spanish set calls it file_id
            where.setdefault(wid, []).append(old)
            old_name.setdefault(wid, name_of(d))
    for wid in sorted(where, key=lambda w: (new_name.get(w) or old_name[w], w)):
        row = {"language": lang, "work_item_id": wid, "file_name": new_name.get(wid) or old_name[wid],
               "earlier_decoy_file": " + ".join(where[wid])}
        if wid in new_name:
            both.append({**row, "new_decoy_file": new})
        else:
            rest.append(row)
    ids[lang] = [r["work_item_id"] for r in both if r["language"] == lang]
    print(f"{lang}: new decoys {len(new_name):4d} | earlier decoys {len(where):4d} | in both {len(ids[lang]):4d} | "
          f"only earlier {sum(r['language'] == lang for r in rest):4d}")

for name, rows in (("previous_decoys_also_in_new_files.csv", both), ("previous_decoys_not_in_new_files.csv", rest)):
    with open(HERE / name, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
(HERE / "previous_decoys_also_in_new_files.json").write_text(json.dumps(
    {"what": "work_item_id of every file that has a decoy both in an earlier decoy set and in the new strict set",
     "counts": {k: len(v) for k, v in ids.items()}, "work_item_ids": ids}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("total in both:", len(both), "| total only earlier:", len(rest))
