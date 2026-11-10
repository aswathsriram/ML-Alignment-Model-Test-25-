#!/usr/bin/env python3
"""
Spanish decoys (297 platform files) in the align-decoys/v1 format, laid out like hindi_decoys/hindi_decoys_plants.json:
{format, instructions (verbatim from the template), decoys: [{decoy_ref, file_id, file_name, plants}]},
every plant with a note "<error type> · <severity> · <detail>" and "critical": true on the most obvious one(s).

The plants are those of spanish_fix/spanish_decoy_plants.json, unchanged: move (boundary mismatch: minor 40-80 ms,
major 100-300 ms, critical over 300 ms), remove (missing segment), add (hallucinated segment).

Run    : python spanish_decoys_v1/convert_spanish.py
Output : spanish_decoys_v1/spanish_decoy_plants.json
"""
import collections, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
KIND = {"move": "boundary mismatch", "remove": "missing segment", "add": "hallucinated segment"}


def main():
    t = json.loads((ROOT / "hindi_decoys" / "alignment-decoys-template.json").read_text(encoding="utf-8"))
    src = json.loads((ROOT / "spanish_fix" / "spanish_decoy_plants.json").read_text(encoding="utf-8"))
    decoys = []
    for d in src["decoys"]:
        plants = []
        for p in d["plants"]:
            note = p["note"]
            m = re.search(r"\((minor|major|critical)\)$", note)
            if p["action"] == "move":
                sev, detail = m.group(1), note[:m.start()].strip()
            else:
                sev, detail = ("critical" if p.get("critical") else "major"), note
            q = {k: v for k, v in p.items() if k != "note"}
            plants.append({**q, "note": f"{KIND[p['action']]} · {sev} · {detail}"})
        plants.sort(key=lambda p: p.get("word", p.get("after_word")))
        decoys.append({"decoy_ref": d["decoy_ref"], "file_id": d["file_id"], "file_name": d["file_name"], "plants": plants})
    out = {"format": t["format"], "instructions": t["instructions"], "decoys": decoys}
    (HERE / "spanish_decoy_plants.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    acts = collections.Counter(p["action"] for d in decoys for p in d["plants"])
    crit = collections.Counter(sum(p.get("critical", False) for p in d["plants"]) for d in decoys)
    print(f"{len(decoys)} files | {sum(acts.values())} plants {dict(acts)} | critical per file {dict(crit)}")


if __name__ == "__main__":
    main()
