"""[race tracks] A box's circuit table added to circuit/list.json: circuits already listed (from other boxes' runs)
kept, those in this run replaced.

    python3 scripts/merge_circuit_list.py circuit_list.json circuit/list.json
"""
import json
import os
import sys

new = json.load(open(sys.argv[1]))
old = json.load(open(sys.argv[2])) if os.path.exists(sys.argv[2]) else {"circuits": []}
ids = {c["id"] for c in new["circuits"]}
new["circuits"] = [c for c in old.get("circuits", []) if c["id"] not in ids] + new["circuits"]
with open(sys.argv[2], "w") as f:
    json.dump(new, f, indent=1)
print("circuit list: %d circuits" % len(new["circuits"]))
