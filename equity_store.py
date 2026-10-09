"""Stockage de l'historique des actions : un fichier par titre (data/equities/<TICKER>.json).

Chaque séance occupe une ligne : les commits quotidiens n'ajoutent qu'une ligne par titre,
ce qui garde le dépôt léger avec 81 valeurs et ~750 séances chacune.
Le fichier reste un JSON standard.
"""
import json
from pathlib import Path

DIR = Path("data/equities")


def path(ticker):
    return DIR / f"{ticker}.json"


def load(ticker):
    p = path(ticker)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_all():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(DIR.glob("*.json")) if p.name != "index.json"]


def save(company):
    DIR.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in company.items() if k != "rows"}
    head = json.dumps(meta, ensure_ascii=False, indent=1)[:-2]  # retire "\n}" final
    rows = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in company.get("rows", []))
    path(company["ticker"]).write_text(f'{head},\n "rows": [\n{rows}\n ]\n}}\n', encoding="utf-8")


def save_index(companies, updated_at):
    DIR.mkdir(parents=True, exist_ok=True)
    idx = {"updated_at": updated_at, "companies": [
        {k: c.get(k) for k in ("ticker", "name", "sector", "compartment", "code_valeur")} |
        {"sessions": len(c.get("rows", [])), "first_date": c["rows"][0]["date"] if c.get("rows") else None,
         "last_date": c["rows"][-1]["date"] if c.get("rows") else None} for c in companies]}
    (DIR / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
