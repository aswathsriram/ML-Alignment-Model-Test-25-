#!/usr/bin/env python3
"""
One German upload from the two batches: de_DE (501 work items, 284 decoys) + de_DE_part2 (126 work items, 76 decoys).
The decoys are copied as built — nothing is re-planned — so the first batch stays exactly as delivered.

Run    : python german_decoys_2026-11-23/combine_german.py
Output : de_DE_all_decoy_plants.json, de_DE_all_decoy_review.csv, de_DE_all_dropped.csv
"""
import csv, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
PARTS = ["de_DE", "de_DE_part2"]

docs = [json.loads((HERE / f"{p}_decoy_plants.json").read_text(encoding="utf-8")) for p in PARTS]
assert docs[0]["format"] == docs[1]["format"] and docs[0]["instructions"] == docs[1]["instructions"]
decoys = [d for doc in docs for d in doc["decoys"]]
assert len({d["work_item_id"] for d in decoys}) == len(decoys) <= 1000
out = {"format": docs[0]["format"], "instructions": docs[0]["instructions"], "decoys": decoys}
(HERE / "de_DE_all_decoy_plants.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for name in ("decoy_review", "dropped"):
    rows = [r for p in PARTS for r in csv.DictReader(open(HERE / f"{p}_{name}.csv", encoding="utf-8-sig"))]
    with open(HERE / f"de_DE_all_{name}.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
print(f"{len(decoys)} decoys ({' + '.join(str(len(d['decoys'])) for d in docs)}), "
      f"{sum(len(d['plants']) for d in decoys)} mistakes -> de_DE_all_decoy_plants.json")
