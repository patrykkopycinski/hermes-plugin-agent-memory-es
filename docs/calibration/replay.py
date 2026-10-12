"""Read-only replay of real user prompts against prod AMES recall. Never retains/deletes."""
import json, os, sys, urllib.request, time

base = os.environ["AMES_SERVICE_URL"]
key = os.environ["AMES_SERVICE_KEY"]
qs = json.load(open("queries.json"))
out = []
for i, o in enumerate(qs):
    q = o["q"]
    if not q.strip()[:1].isalnum():
        continue
    req = urllib.request.Request(base + "/memory/recall", data=json.dumps({"query": q, "size": 8}).encode(),
                                 method="POST", headers={"Content-Type": "application/json", "X-API-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
    except Exception as e:
        print("ERR", i, type(e).__name__, file=sys.stderr)
        continue
    fused = d.get("fused", [])
    out.append({"i": i, "q": q, "hits": [{"id": h.get("id"), "kind": h.get("kind"), "score": h.get("score"),
                                           "text": h.get("text", "")} for h in fused]})
    if len(out) >= 130:
        break
json.dump(out, open("replay.json", "w"))
print(len(out), "queries;", sum(len(x["hits"]) for x in out), "hits")
