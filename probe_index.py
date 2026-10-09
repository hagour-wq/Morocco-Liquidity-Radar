import json, casablanca_source as cb
from datetime import datetime, timezone
out={}
for label,params in {"default":{"symbol":"MASI","v":"4.0.0"},"daily":{"symbol":"MASI","resolution":"1D","v":"4.0.0"},
                     "range":{"symbol":"MASI","from":"2025-10-01","to":"2026-10-08"},"period":{"symbol":"MASI","period":"1Y"}}.items():
    try:
        d=cb.get_json("/api/live-market/indices/historical",params)
        it=d.get("items",[]) if isinstance(d,dict) else d
        days=sorted({cb.session_day(float(x["time"])/(1000 if float(x["time"])>1e11 else 1)).isoformat() for x in it if x.get("time")})
        out[label]={"keys":list(d.keys()) if isinstance(d,dict) else "list","n":len(it),"first":it[:2],"last":it[-2:],"distinct_days":len(days),"days_head":days[:3],"days_tail":days[-3:]}
    except Exception as e: out[label]={"error":str(e)[:300]}
open("data/masi_raw_probe.json","w").write(json.dumps(out,ensure_ascii=False,indent=1))
