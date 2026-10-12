import sqlite3, random, json, re
c = sqlite3.connect('file:/Users/patrykkopycinski/.hermes/state.db?mode=ro', uri=True)
rows = c.execute("select session_id,content,timestamp from messages where role='user' and content is not null "
                 "and length(content) between 25 and 800 and timestamp>strftime('%s','now')-60*86400").fetchall()
print(len(rows))
seen = set(); out = []
random.seed(7); random.shuffle(rows)
for s, t, ts in rows:
    st = t.lstrip()
    if st[:1] in '[✔⚠#/' or st.startswith(('work kanban', 'You are')) or len(st.split()) < 4:
        continue
    k = re.sub(r'\W+', '', t[:50].lower())
    if k in seen:
        continue
    seen.add(k)
    out.append({'session': s, 'q': t})
    if len(out) >= 160:
        break
json.dump(out, open('queries.json', 'w'))
print(len(out))
for o in out[:15]:
    print(repr(o['q'][:110]))
