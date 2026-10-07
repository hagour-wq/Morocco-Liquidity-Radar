"""Official liquidity collector skeleton.
Never fabricates values: only writes a component after a source-specific parser
has produced a numeric value, a comparison basis and a reference date.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

P=Path("data/liquidity_inputs.json")

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def save(d):
    d["collector_checked_at"]=datetime.now(timezone.utc).isoformat()
    P.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def validate_component(x):
    if not x.get("verified"): return True
    return isinstance(x.get("score"),(int,float)) and bool(x.get("reference_date")) and bool(x.get("source"))

def main():
    d=load()
    # Safety gate: future AMMC/BAM parsers plug in here. Until a parser validates
    # comparable official observations, existing verified values are preserved
    # and unavailable components remain null.
    for name,x in d.get("components",{}).items():
        if not validate_component(x):
            raise ValueError(f"Invalid verified liquidity component: {name}")
    save(d)
    active=[k for k,v in d["components"].items() if v.get("verified")]
    print("Verified liquidity components:", ", ".join(active) or "none")

if __name__=="__main__": main()
