"""Collecteur MASI officiel (Bourse de Casablanca).

1. Historique officiel de l'indice (api/live-market/indices/historical) : comble
   les séances manquantes et remplace toute valeur MASI non officielle.
2. Statut de séance officiel : la séance du jour n'est écrite qu'une fois clôturée,
   datée par la date de séance (et non par la date de collecte).

Les champs volume_mad / breadth existants (autres sources) sont conservés tels quels
avec leur provenance ; les nouvelles séances les laissent à null plutôt que de mélanger
des bases de calcul différentes. Le montant officiel du jour est stocké séparément
dans volume_mad_official.
Échoue (code 1) si l'historique officiel de l'indice est inaccessible.
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import casablanca_source as cb

OUT = Path("data/market_history.json")
REPORT = Path("data/masi_collection_report.json")
SRC = "Bourse de Casablanca (indices/historical)"


def main():
    now = datetime.now(timezone.utc).isoformat()
    rows = {r["date"]: r for r in json.loads(OUT.read_text(encoding="utf-8"))} if OUT.exists() else {}
    rep = {"run_at": now, "source": cb.BASE + "/api/live-market/indices/historical?symbol=MASI",
           "added": [], "corrected": [], "errors": []}
    try:
        snap = cb.live_snapshot()
    except Exception as e:
        snap = None
        rep["errors"].append(f"live_snapshot: {type(e).__name__}: {e}")
    today = datetime.now(timezone.utc).astimezone(cb.TZ).date().isoformat()
    try:
        hist, _ = cb.index_history("MASI")
        # la valeur du jour n'est officielle qu'après clôture
        hist = [h for h in hist if h["date"] < today or (snap and snap["session_status"] == "closed")]
    except Exception as e:
        hist = []
        rep["errors"].append(f"index_history: {type(e).__name__}: {e}")
    rep["official_sessions_received"] = len(hist)
    if hist:
        rep["official_first"], rep["official_last"] = hist[0]["date"], hist[-1]["date"]
    for h in hist:
        if not (1000 < h["close"] < 100000):
            rep["errors"].append(f"valeur hors bornes {h}")
            continue
        r = rows.get(h["date"])
        if r is None:
            rows[h["date"]] = {"date": h["date"], "masi": h["close"], "volume_mad": None, "breadth": None,
                               "source": SRC, "masi_source": SRC, "quality": "official_index_history", "collected_at": now}
            rep["added"].append(h["date"])
        elif r.get("masi_source") != SRC:
            old = r.get("masi")
            if old is None or abs(h["close"] / old - 1) > 0.0005:
                rep["corrected"].append({"date": h["date"], "previous": old, "previous_source": r.get("source"), "official": h["close"]})
            r["masi"] = h["close"]
            r["masi_source"] = SRC

    try:
        if snap is None:
            raise RuntimeError("instantané indisponible")
        rep["session_status"], rep["session_date"] = snap["session_status"], snap["session_date"]
        idx = snap["index"] or {}
        if snap["session_status"] == "closed" and snap["session_date"] and idx.get("valeur"):
            acts = snap["actions"]
            up = sum(1 for a in acts if (a.get("variation") or 0) > 0)
            down = sum(1 for a in acts if (a.get("variation") or 0) < 0)
            d = snap["session_date"]
            r = rows.setdefault(d, {"date": d, "volume_mad": None, "source": SRC})
            r.update({"masi": float(idx["valeur"]), "masi_source": "Bourse de Casablanca (live-market, séance clôturée)",
                      "volume_mad_official": round(sum(a.get("volume") or 0 for a in acts), 2),
                      "breadth": round(up / (up + down), 4) if up + down else None,
                      "breadth_source": "Bourse de Casablanca live-market/actions",
                      "quality": "official_session_close", "collected_at": now})
            rep["session_written"] = d
        else:
            rep["session_written"] = None
    except Exception as e:
        rep["errors"].append(f"live_snapshot: {type(e).__name__}: {e}")

    ordered = [rows[k] for k in sorted(rows)]
    if hist or rep.get("session_written"):
        OUT.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    rep["total_sessions"] = len(ordered)
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in rep.items()}, ensure_ascii=False))
    if not hist:
        sys.exit(1)


if __name__ == "__main__":
    main()
