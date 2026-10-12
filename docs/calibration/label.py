"""Hand-labelled calibration sample: top-5 hits of 9 real replayed prompts (45 hits), every hit read in full
before labelling. relevant=1: would help the agent act on that prompt. Keyed by query_i (replay.json)."""
import json
LAB = {
 0:  [1, 1, 0, 1, 1],
 1:  [1, 0, 0, 0, 1],
 6:  [1, 1, 0, 0, 0],
 7:  [0, 0, 0, 0, 0],
 8:  [1, 0, 0, 1, 0],
 10: [0, 0, 0, 0, 0],
 11: [0, 0, 0, 0, 0],
 12: [0, 0, 0, 0, 0],
 13: [1, 1, 0, 1, 0],
}
d = {x["i"]: x for x in json.load(open("replay.json"))}
rows = []
for qi, labs in LAB.items():
    x = d[qi]
    for r, l in enumerate(labs):
        h = x["hits"][r]
        rows.append({"query_i": qi, "query": x["q"][:120], "rank": r, "id": h["id"], "kind": h["kind"],
                     "score": h["score"], "relevant": l, "text": h["text"][:140]})
json.dump(rows, open("labels.json", "w"), indent=1)
R = [r for r in rows if r["relevant"]]; N = [r for r in rows if not r["relevant"]]
print("labelled", len(rows), "relevant", len(R), "irrelevant", len(N))
print("thr       lost_rel   dropped_irrel")
for t in sorted({round(r["score"], 5) for r in rows}):
    lr = sum(1 for r in R if r["score"] < t); di = sum(1 for r in N if r["score"] < t)
    print("%.5f   %2d (%3.0f%%)  %2d (%3.0f%%)" % (t, lr, 100 * lr / len(R), di, 100 * di / len(N)))
print("mean relevant %.5f irrelevant %.5f" % (sum(r["score"] for r in R) / len(R), sum(r["score"] for r in N) / len(N)))
pairs = [(a["score"] > b["score"]) + 0.5 * (a["score"] == b["score"]) for a in R for b in N]
print("AUC(score as relevance ranker)", round(sum(pairs) / len(pairs), 3))
for rk in range(5):
    rr = [r for r in rows if r["rank"] == rk]
    print("rank", rk, "relevant %d/%d" % (sum(r["relevant"] for r in rr), len(rr)))
for k in ("episodic", "semantic", "procedural"):
    rr = [r for r in rows if r["kind"] == k]
    print(k, "relevant %d/%d" % (sum(r["relevant"] for r in rr), len(rr)))
