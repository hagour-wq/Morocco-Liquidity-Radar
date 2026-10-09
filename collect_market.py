"""Collecteur MASI officiel (Bourse de Casablanca) — clôture quotidienne.

La Bourse ne publie pas d'historique quotidien du MASI par API (le service
indices/historical ne renvoie que l'intraday du jour). Ce collecteur enregistre donc,
à chaque exécution après la clôture, la séance du jour :
- MASI de clôture (live-market, index_data.valeur), uniquement si la séance est « closed » ;
- séance confirmée par la présence d'une cotation ATW à cette date dans stock-historical
  (évite d'écrire un jour férié ou un week-end) ;
- montant échangé officiel (somme des montants des actions) et largeur du marché
  (hausses / (hausses + baisses)).
Les séances antérieures déjà stockées ne sont jamais modifiées. Les nouvelles séances
stockent le montant officiel dans volume_mad_official et laissent volume_mad à null,
pour ne pas mélanger des bases de calcul différentes.
Code de sortie 1 si la source est inaccessible ou incohérente ; 0 si rien à écrire (séance
non clôturée ou jour sans séance) avec la raison dans data/masi_collection_report.json.
"""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import casablanca_source as cb

OUT = Path("data/market_history.json")
REPORT = Path("data/masi_collection_report.json")
SRC = "Bourse de Casablanca (live-market, séance clôturée)"


def build_row(snap, now):
    idx = snap["index"] or {}
    masi = float(idx["valeur"])
    if not 1000 < masi < 100000:
        raise ValueError(f"MASI hors bornes : {masi}")
    acts = snap["actions"]
    up = sum(1 for a in acts if (a.get("variation") or 0) > 0)
    down = sum(1 for a in acts if (a.get("variation") or 0) < 0)
    return {"date": snap["session_date"], "masi": masi, "masi_previous_close": idx.get("veille"),
            "masi_high": idx.get("high"), "masi_low": idx.get("low"), "volume_mad": None,
            "volume_mad_official": round(sum(a.get("volume") or 0 for a in acts), 2),
            "breadth": round(up / (up + down), 4) if up + down else None,
            "advancers": up, "decliners": down, "instruments": len(acts),
            "source": SRC, "masi_source": SRC, "source_url": cb.BASE + "/live-market/indices/cours?symbol=MASI",
            "quality": "official_session_close", "collected_at": now}


def main():
    now = datetime.now(timezone.utc)
    rep = {"run_at": now.isoformat(), "written": None, "reason": None, "errors": []}
    try:
        snap = cb.live_snapshot()
        rep.update(session_status=snap["session_status"], session_date=snap["session_date"],
                   masi_live=(snap["index"] or {}).get("valeur"))
        if snap["session_status"] != "closed":
            rep["reason"] = "séance non clôturée : rien n'est écrit"
        else:
            d = snap["session_date"]
            day = datetime.fromisoformat(d).date()
            atw = cb.stock_history("ATW", day - timedelta(days=7), day)
            if not any(cb.parse_seance(x["seance"]).isoformat() == d for x in atw):
                rep["reason"] = f"aucune cotation ATW le {d} : jour sans séance, rien n'est écrit"
            else:
                rows = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
                rows = [r for r in rows if r.get("date") != d] + [build_row(snap, now.isoformat())]
                rows.sort(key=lambda r: r["date"])
                OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
                rep["written"] = d
                rep["total_sessions"] = len(rows)
    except Exception as e:
        rep["errors"].append(f"{type(e).__name__}: {e}")
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False))
    for err in rep["errors"]:
        print(f"::error title=collect_market::{err}")
    if rep["reason"]:
        print(f"::notice title=collect_market::{rep['reason']}")
    if rep["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
