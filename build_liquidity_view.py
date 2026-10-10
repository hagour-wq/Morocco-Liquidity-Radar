"""Répartition de l'épargne collective (OPCVM) : où va la liquidité ?

Source officielle : statistiques hebdomadaires de l'AMMC (STAT_OPCVM_HEBDO_AMMC_<date>), déjà téléchargées et lues
par collect_liquidity.py (data/liquidity_inputs.json → ammc_workbook_inspection).
- Encours (actif net) par catégorie, part dans le total, variations publiées : chiffres officiels.
- Flux nets de souscriptions / rachats : ESTIMÉS, car l'AMMC ne les publie pas dans ce fichier.
  Flux estimé = actif net fin de semaine − actif net début × (1 + performance de l'indice de la catégorie).
  Calculés uniquement entre deux publications consécutives (≤ 10 jours d'écart).
Historique conservé d'une exécution à l'autre : data/opcvm_history.json (une ligne par publication).
Sortie : data/liquidity_allocation.json.
"""
import json, re
from datetime import date, datetime, timezone
from pathlib import Path
from collect_liquidity import parse_opcvm_snapshot

INP = Path("data/liquidity_inputs.json")
HIST = Path("data/opcvm_history.json")
OUT = Path("data/liquidity_allocation.json")
CATS = ["Monétaire", "Obligations CT", "Obligations MLT", "Diversifiés", "Actions", "Contractuel"]
GROUPS = {"Monétaire": "Monétaire", "Obligations CT": "Obligataire", "Obligations MLT": "Obligataire",
          "Diversifiés": "Diversifié", "Actions": "Actions", "Contractuel": "Contractuel"}


def file_date(url):
    """« …_02102026.xls », « …%2018-09-2026.xls », « …-11092026.xlsx » → date ISO."""
    name = url.rsplit("/", 1)[-1].replace("%20", " ")
    m = re.search(r"(\d{2})[-_ ]?(\d{2})[-_ ]?(20\d{2})\.xlsx?$", name)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat() if m else None


def full_snapshot(info):
    """Encours, part et variations publiées (hebdomadaire, mensuelle, annuelle) par catégorie."""
    snap = parse_opcvm_snapshot(info)
    rows = next(iter(info["samples"].values()))["rows"]
    extra = {}
    for r in rows:
        v = r["values"]
        label = str(v[1]).strip() if len(v) > 1 and v[1] is not None else ""
        if label in CATS and label in snap.get("nav", {}) and label not in extra:
            try:
                extra[label] = {"share_pct": float(v[4]), "monthly_pct": float(v[6]), "annual_pct": float(v[7]), "funds": int(float(v[2]))}
            except (ValueError, TypeError, IndexError):
                pass
    for k, e in extra.items():
        snap["nav"][k].update(e)
    return snap


def flows(cur, prev):
    out = {}
    for cat, c in cur["nav"].items():
        p, perf = prev["nav"].get(cat), cur.get("performance", {}).get(cat)
        if p and perf is not None:
            est = c["amount"] - p["amount"] * (1 + perf["weekly_pct"] / 100)
            out[cat] = {"flow_mad": round(est), "flow_pct": round(100 * est / p["amount"], 3),
                        "market_effect_mad": round(p["amount"] * perf["weekly_pct"] / 100)}
    return out


def build(inp, hist):
    for info in inp.get("ammc_workbook_inspection", []):
        d = file_date(info.get("url", ""))
        if not d or info.get("status") != "SCHEMA_READ":
            continue
        snap = full_snapshot(info)
        if len(snap.get("nav", {})) >= 5:
            hist[d] = {"date": d, "url": info["url"], **snap}
    dates = sorted(hist)
    weeks = []
    for a, b in zip(dates, dates[1:]):
        gap = (date.fromisoformat(b) - date.fromisoformat(a)).days
        if gap <= 10:
            weeks.append({"from": a, "to": b, "flows": flows(hist[b], hist[a])})
    if not dates:
        return None
    last = hist[dates[-1]]
    total = sum(x["amount"] for x in last["nav"].values())
    cats = []
    for cat in CATS:
        x = last["nav"].get(cat)
        if not x:
            continue
        def cum(n):
            ws = weeks[-n:]
            if len(ws) < n or any(cat not in w["flows"] for w in ws):
                return None   # flux non estimable (pas d'indice de performance publié pour la catégorie)
            return sum(w["flows"][cat]["flow_mad"] for w in ws)
        cats.append({"category": cat, "group": GROUPS[cat], "amount_mad": round(x["amount"]), "share_pct": round(100 * x["amount"] / total, 2),
                     "weekly_pct": x.get("weekly_pct"), "monthly_pct": x.get("monthly_pct"), "annual_pct": x.get("annual_pct"),
                     "funds": x.get("funds"), "performance_weekly_pct": (last.get("performance", {}).get(cat) or {}).get("weekly_pct"),
                     "flow_last_week_mad": (weeks[-1]["flows"].get(cat, {}).get("flow_mad") if weeks and weeks[-1]["to"] == dates[-1] else None),
                     "flow_4w_mad": cum(4), "flow_8w_mad": cum(8)})
    groups = {}
    for c in cats:
        g = groups.setdefault(c["group"], {"group": c["group"], "amount_mad": 0, "flow_4w_mad": 0})
        g["amount_mad"] += c["amount_mad"]
        g["flow_4w_mad"] = None if g["flow_4w_mad"] is None or c["flow_4w_mad"] is None else g["flow_4w_mad"] + c["flow_4w_mad"]
    for g in groups.values():
        g["share_pct"] = round(100 * g["amount_mad"] / total, 2)
    inflow = sorted((c for c in cats if c["flow_4w_mad"] is not None), key=lambda c: c["flow_4w_mad"], reverse=True)
    summary = None
    if inflow:
        pos = [c for c in inflow if c["flow_4w_mad"] > 0]
        neg = [c for c in inflow[::-1] if c["flow_4w_mad"] < 0]
        f = lambda c: f"{c['category']} ({c['flow_4w_mad'] / 1e9:+.1f} Md MAD)".replace(".", ",")
        summary = ("Sur les 4 dernières semaines, l'épargne OPCVM s'est " +
                   (f"dirigée vers {', '.join(f(c) for c in pos[:2])}" if pos else "retirée de toutes les catégories") +
                   (f" et a quitté {', '.join(f(c) for c in neg[:2])}" if pos and neg else "") + " (flux estimés, hors effet de marché).")
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "as_of": dates[-1], "source": "AMMC — statistiques hebdomadaires des OPCVM",
            "source_url": last["url"], "total_amount_mad": round(total), "categories": cats, "groups": sorted(groups.values(), key=lambda g: -g["amount_mad"]),
            "weeks": weeks[-12:], "history": [{"date": d, **{c: round(hist[d]["nav"][c]["amount"]) for c in CATS if c in hist[d]["nav"]}} for d in dates],
            "summary": summary,
            "method": "Encours et parts : chiffres officiels AMMC. Flux = actif net fin − actif net début × (1 + performance hebdomadaire de l'indice de la catégorie) : estimation de la collecte nette, l'AMMC ne publiant pas les souscriptions / rachats dans ce fichier."}


def main():
    inp = json.loads(INP.read_text(encoding="utf-8"))
    hist = json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else {}
    out = build(inp, hist)
    HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if out:
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({"as_of": out["as_of"], "weeks": len(out["weeks"]), "summary": out["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
