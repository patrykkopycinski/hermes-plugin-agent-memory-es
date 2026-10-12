import json, statistics as st
d = json.load(open("replay.json"))
rows = json.load(open("labels.json"))
R = [r for r in rows if r["relevant"]]; N = [r for r in rows if not r["relevant"]]
print("| min_score | abstain rate (130 q) | median injected chars (size 5) | relevant lost (13) | irrelevant dropped (32) |")
print("|---|---|---|---|---|")
for t in (None, 0.0183, 0.01835, 0.0184, 0.01845, 0.0185, 0.0186, 0.0187, 0.0188, 0.0189):
    ch = []; ab = 0
    for x in d:
        hs = [h for h in x["hits"][:5] if t is None or h["score"] >= t]
        if not hs: ab += 1
        ch.append(sum(len(h["text"]) + 10 for h in hs))
    lost = "-" if t is None else "%d (%.0f%%)" % (sum(r["score"] < t for r in R), 100 * sum(r["score"] < t for r in R) / len(R))
    drop = "-" if t is None else "%d (%.0f%%)" % (sum(r["score"] < t for r in N), 100 * sum(r["score"] < t for r in N) / len(N))
    print("| %s | %.0f%% | %d | %s | %s |" % ("off" if t is None else t, 100 * ab / len(d), st.median(ch), lost, drop))
