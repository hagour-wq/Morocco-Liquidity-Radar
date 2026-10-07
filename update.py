import json
from datetime import datetime, timezone
from pathlib import Path

OUT=Path("data/dashboard.json")

def load():
    return json.loads(OUT.read_text(encoding="utf-8"))

def save(d):
    d["retrieved_at"]=datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")

# V1 volontairement conservatrice : les collecteurs officiels seront ajoutés
# source par source après validation du format et de la stabilité des publications.
if __name__=="__main__":
    data=load()
    save(data)
    print("Dashboard metadata refreshed; no synthetic market data generated.")
