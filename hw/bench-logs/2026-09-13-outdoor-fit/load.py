import json, pandas as pd
rows={}
for line in open('gas.ndjson'):
    d=json.loads(line); n=d['metric']['__name__'][4:]
    s=pd.Series(d['values'], index=pd.to_datetime(d['timestamps'], unit='ms', utc=True))
    rows[n]=s[~s.index.duplicated()]
df=pd.DataFrame(rows).sort_index()
df.to_pickle('gas.pkl')
