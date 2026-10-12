"""Read-only before/after replay for the prefetch `kinds` default. Never retains/deletes.

Runs the same queries as replay.py twice, with the exact prefetch payload (size 5, calibrated
min_score): once with no `kinds` (old behaviour) and once with kinds=[episodic, semantic].
Needs queries.json (sample.py), labels.json (label.py), AMES_SERVICE_URL, AMES_SERVICE_KEY.
"""
import json, os, statistics as st, sys, urllib.request

base, key = os.environ["AMES_SERVICE_URL"], os.environ["AMES_SERVICE_KEY"]
MIN_SCORE = 0.0184
qs = json.load(open("queries.json"))
replay = json.load(open("replay.json"))   # defines the 130 queries used for calibration
labels = json.load(open("labels.json"))


def recall(q, kinds):
    body = {"query": q, "size": 5, "min_score": MIN_SCORE}
    if kinds:
        body["kinds"] = kinds
    req = urllib.request.Request(base + "/memory/recall", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-API-Key": key})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    return [] if d.get("abstained") else d.get("fused", [])


def injected(hits):  # same shape as prefetch(): "[id] text" joined by newlines
    return len("\n".join("[%s] %s" % (h["id"], h["text"]) for h in hits[:5]))


out = {"before": {}, "after": {}}
for x in replay:
    for arm, kinds in (("before", None), ("after", ["episodic", "semantic"])):
        try:
            out[arm][x["i"]] = [{"id": h["id"], "kind": h.get("kind"), "score": h.get("score"),
                                 "n": len(h["text"])} for h in recall(x["q"], kinds)]
        except Exception as e:
            print("ERR", arm, x["i"], type(e).__name__, file=sys.stderr)
# recompute injected chars from text lengths (text itself is not stored: public repo)
def chars(hits):
    return sum(len(h["id"]) + 3 + h["n"] for h in hits) + max(len(hits) - 1, 0)

summary = {}
for arm in ("before", "after"):
    ch = [chars(h) for h in out[arm].values()]
    kinds = [h["kind"] for hs in out[arm].values() for h in hs]
    summary[arm] = {"queries": len(ch), "median_chars": st.median(ch), "mean_chars": round(st.mean(ch)),
                    "hits": len(kinds), "procedural_hits": kinds.count("procedural"),
                    "abstain": sum(1 for c in ch if c == 0)}
# relevance: labelled relevant hits (query_i, id) still present in the after top-5?
rel = [r for r in labels if r["relevant"]]
lost = [r for r in rel if r["id"] not in {h["id"] for h in out["after"].get(r["query_i"], [])}]
lost_before = [r for r in rel if r["id"] not in {h["id"] for h in out["before"].get(r["query_i"], [])}]
proc_labelled = [r for r in labels if r["kind"] == "procedural"]
summary["labelled"] = {"relevant": len(rel), "relevant_missing_before_arm": len(lost_before),
                       "relevant_missing_after_arm": len(lost), "procedural_labelled": len(proc_labelled),
                       "procedural_labelled_relevant": sum(r["relevant"] for r in proc_labelled)}
print(json.dumps(summary, indent=1))
