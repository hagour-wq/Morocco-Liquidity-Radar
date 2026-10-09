"""Rotation de marché de la dernière séance, calculée sur les cours officiels (data/equities).

Remplace l'instantané saisi à la main du 07/10/2026 :
- secteurs : variation pondérée par la capitalisation de la veille ;
- hausses / baisses : titres ayant échangé au moins MIN_TURNOVER MAD (écarte les cotations anecdotiques) ;
- valeurs les plus actives : montant échangé ;
- ligne « Bourse de Casablanca » du bloc Traçabilité & fraîcheur.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import equity_store

DASH = Path("data/dashboard.json")
MIN_TURNOVER = 100_000


def last_session(companies):
    c = Counter(r["date"] for x in companies for r in x["rows"][-5:] if r.get("traded") and "stale_copy" not in str(r.get("status", "")))
    return max(d for d, n in c.items() if n >= 10)


def daily_moves(companies, d):
    out = []
    for x in companies:
        rows = [r for r in x["rows"] if r.get("close") and r["close"] > 0 and "stale_copy" not in str(r.get("status", ""))]
        idx = next((i for i, r in enumerate(rows) if r["date"] == d), None)
        if not idx:
            continue
        r, p = rows[idx], rows[idx - 1]
        if "corporate_action_suspected" in str(r.get("status", "")):
            continue
        out.append({"ticker": x["ticker"], "name": x.get("name"), "sector": x.get("sector"), "change_pct": round(100 * (r["close"] / p["close"] - 1), 2),
                    "turnover_mad": r.get("turnover_mad") or 0, "traded": bool(r.get("traded")), "prev_cap": p.get("market_cap_mad")})
    return out


def rotation(companies):
    d = last_session(companies)
    moves = daily_moves(companies, d)
    sect = {}
    for m in moves:
        if m["sector"] and m["prev_cap"]:
            s = sect.setdefault(m["sector"], [0.0, 0.0])
            s[0] += m["prev_cap"] * m["change_pct"]
            s[1] += m["prev_cap"]
    sectors = sorted(({"name": k, "change_pct": round(v[0] / v[1], 2)} for k, v in sect.items() if v[1]), key=lambda x: -x["change_pct"])
    liquid = [m for m in moves if m["traded"] and m["turnover_mad"] >= MIN_TURNOVER]
    by = sorted(liquid, key=lambda m: -m["change_pct"])
    pick = lambda m: {"ticker": m["ticker"], "name": m["name"], "change_pct": m["change_pct"]}
    return {"reference_date": d, "quality": "official_session", "source": "Bourse de Casablanca — cours officiels (stock-historical)",
            "computed_at": datetime.now(timezone.utc).isoformat(), "min_turnover_mad": MIN_TURNOVER,
            "sectors": sectors[:3] + [s for s in sectors[-3:] if s not in sectors[:3]],
            "leaders": [pick(m) for m in by[:5] if m["change_pct"] > 0], "laggards": [pick(m) for m in by[::-1][:5] if m["change_pct"] < 0],
            "active": [{"ticker": m["ticker"], "name": m["name"], "volume_mad": m["turnover_mad"]} for m in sorted(moves, key=lambda m: -m["turnover_mad"])[:5]],
            "breadth": {"advancers": sum(m["change_pct"] > 0 for m in moves if m["traded"]), "decliners": sum(m["change_pct"] < 0 for m in moves if m["traded"]),
                        "traded": sum(m["traded"] for m in moves), "listed": len(companies)}}


def main():
    companies = [c for c in equity_store.load_all() if c.get("rows")]
    rot = rotation(companies)
    dash = json.loads(DASH.read_text(encoding="utf-8"))
    dash["rotation"] = rot
    d = rot["reference_date"]
    src = {"name": "Bourse de Casablanca", "dataset": "Cours, volumes et secteurs (81 actions) ; MASI (résumés de séance)",
           "reference_date": f"{d[8:]}/{d[5:7]}/{d[:4]}", "status": f"OFFICIEL · {rot['breadth']['traded']} titres échangés sur {rot['breadth']['listed']}",
           "freshness": "quotidienne", "official_page": "https://www.casablanca-bourse.com/"}
    dash["sources"] = [s for s in dash.get("sources", []) if s.get("name") != "Bourse de Casablanca"] + [src]
    DASH.write_text(json.dumps(dash, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: rot[k] for k in ("reference_date", "sectors", "leaders", "laggards", "breadth")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
