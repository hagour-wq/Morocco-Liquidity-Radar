"""Fondamentaux à partir des comptes annuels publiés (registre data/fundamentals_sources.json).

Pour chaque émetteur : téléchargement du PDF officiel, extraction des lignes d'états financiers
(extract_financials.py), contrôles croisés avec le nombre de titres du bulletin de la cote,
indicateurs dérivés. Statuts :
- VERIFIED : grandeurs principales extraites et contrôles réussis ;
- PARTIAL : extraction incomplète (grandeurs manquantes listées) ;
- REJECTED : contrôle bloquant en échec ;
- UNREADABLE : document sans texte exploitable (PDF image).
Sortie : data/company_fundamentals.json — chaque grandeur garde la ligne source, l'unité et l'URL.
"""
import io, json, sys
from datetime import datetime, timezone
from pathlib import Path
import casablanca_source as cb
from extract_financials import extract, checks

SOURCES = Path("data/fundamentals_sources.json")
REF = Path("data/issuer_reference.json")
OUT = Path("data/company_fundamentals.json")
REQUIRED = {"bank": ["pnb", "net_income_group", "equity_total", "minority_interests", "cost_of_risk", "operating_expenses"],
            "corporate": ["revenue", "operating_income", "net_income_group", "equity_total"]}


def analyse(src, text, shares):
    if len(text.strip()) < 2000:
        return {"status": "UNREADABLE", "reason": "document sans texte exploitable (PDF image) : reconnaissance de caractères non mise en place"}
    fin = extract(text, src["model"])
    derived, errors, notes = checks(fin, src["model"], shares)
    missing = [k for k in REQUIRED[src["model"]] if not fin.get(k)]
    status = "REJECTED" if errors else "PARTIAL" if missing else "VERIFIED"
    return {"status": status, "errors": errors, "notes": notes, "missing": missing,
            "statements": {k: ({kk: x[kk] for kk in ("current", "previous", "unit", "mad", "mad_previous", "line", "ambiguous_split", "method") if kk in x} if x else None)
                           for k, x in fin.items()},
            "derived": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in derived.items()}}


def main():
    from pypdf import PdfReader
    now = datetime.now(timezone.utc).isoformat()
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    ref = json.loads(REF.read_text(encoding="utf-8")).get("issuers", {}) if REF.exists() else {}
    out = {"generated_at": now, "source_registry": str(SOURCES), "listing": sources.get("listing"), "companies": []}
    for src in sources["issuers"]:
        t = src["ticker"]
        r = ref.get(t, {})
        rec = {**src, "isin": r.get("isin"), "shares": r.get("shares"), "shares_source": "bulletin de la cote " + str(json.loads(REF.read_text(encoding="utf-8")).get("bulletin_date")) if r else None,
               "listing_exchange": "Casablanca Stock Exchange", "listing_country": "MA", "collected_at": now}
        try:
            b = cb._get(src["url"], accept="application/pdf")
            text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages)
            rec.update(analyse(src, text, r.get("shares")))
        except Exception as e:
            rec.update(status="SOURCE_ERROR", reason=f"{type(e).__name__}: {e}"[:200])
        out["companies"].append(rec)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({c["ticker"]: (c["status"], c.get("errors") or c.get("missing") or c.get("reason")) for c in out["companies"]}, ensure_ascii=False))
    for c in out["companies"]:
        if c["status"] not in ("VERIFIED",):
            print(f"::warning title=collect_fundamentals {c['ticker']}::{c['status']} {c.get('reason') or c.get('errors') or c.get('missing')}")
    if not any(c["status"] == "VERIFIED" for c in out["companies"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
