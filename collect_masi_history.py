"""Historique officiel du MASI à partir des « Résumés de séance » PDF de la Bourse de Casablanca.

Source : https://www.casablanca-bourse.com/market-data/editions-statistiques (liste paginée de PDF).
Pour chaque séance : clôture du MASI, performance journalière publiée, montant échangé sur le
marché central actions, nombre de hausses / baisses (liste des variations).

Contrôles :
- date du nom de fichier = date imprimée dans le document ;
- cohérence : MASI(t) / MASI(t-1) − 1 ≈ performance journalière publiée (écart ≤ 0,02 point) ;
- bornes plausibles.
Cache incrémental : data/masi_official.json (un PDF n'est lu qu'une fois).
Fusion : data/market_history.json reçoit, pour chaque séance couverte, le MASI officiel
(masi_source), le montant du marché central (volume_mad, volume_source) et la largeur du marché.
Les valeurs remplacées sont journalisées dans data/masi_collection_report.json.
"""
import io, json, re, sys, time
from datetime import date, datetime, timezone
from pathlib import Path
import casablanca_source as cb

CACHE = Path("data/masi_official.json")
HIST = Path("data/market_history.json")
REPORT = Path("data/masi_history_report.json")
LISTING = "/market-data/editions-statistiques"
MONTHS = {m: i for i, m in enumerate(["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                                      "septembre", "octobre", "novembre", "décembre"], 1)}
NUM = r"-?\d{1,3}(?:[\s  ]\d{3})*,\d+"
SRC = "Bourse de Casablanca — Résumé de séance (PDF)"


def fr(s):
    return float(re.sub(r"[\s  ]", "", s).replace(",", "."))


def parse_resume(text, file_date):
    t = re.sub(r"[ \t]+", " ", text)
    out = {"date": file_date}
    m = re.search(r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", t, re.I)
    if m and m.group(2).lower() in MONTHS:
        out["printed_date"] = date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
    m = re.search(r"Indices\s+MASI\b.*?Valeur\s+(" + NUM + ")", t, re.S)
    out["masi"] = fr(m.group(1)) if m else None
    m = re.search(r"Performance journalière\s+(" + NUM + r")\s*%", t)
    out["masi_daily_pct"] = fr(m.group(1)) if m else None
    m = re.search(r"Volume en MAD\s+Actions\s+Marché central\s+(" + NUM + ")", t)
    out["central_actions_mad"] = fr(m.group(1)) if m else None
    m = re.search(r"Volume global MAD\s+(" + NUM + ")", t)
    out["volume_global_mad"] = fr(m.group(1)) if m else None
    var = re.findall(r"^\S.*?\s(" + NUM + r")\s(" + NUM + r")\s(" + NUM + r")\s?%\s", t, re.M)
    pct = [fr(v[2]) for v in var]
    out["advancers"], out["decliners"] = sum(p > 0 for p in pct), sum(p < 0 for p in pct)
    out["unchanged"], out["instruments_listed"] = sum(p == 0 for p in pct), len(pct)
    return out


def trading_days():
    """Calendrier des séances déduit des cotations officielles d'ATW (data/equities/ATW.json), s'il existe."""
    p = Path("data/equities/ATW.json")
    return {r["date"] for r in json.loads(p.read_text(encoding="utf-8"))["rows"]} if p.exists() else set()


def validate(rec, prev, sessions_cal=frozenset()):
    flags = []
    gap = prev and any(prev["date"] < d < rec["date"] for d in sessions_cal)
    if gap:
        flags.append("previous_session_missing_in_archive")  # recoupement impossible, pas une anomalie de la valeur
    if not rec.get("masi") or not 1000 < rec["masi"] < 100000:
        flags.append("masi_missing_or_out_of_bounds")
    if rec.get("printed_date") and rec["printed_date"] != rec["date"]:
        flags.append("date_mismatch")
    if prev and not gap and rec.get("masi") and rec.get("masi_daily_pct") is not None and prev.get("masi"):
        implied = 100 * (rec["masi"] / prev["masi"] - 1)
        rec["implied_daily_pct"] = round(implied, 4)
        if abs(implied - rec["masi_daily_pct"]) > 0.02:
            flags.append("daily_change_mismatch")
    return flags


def list_pdfs(known_listing, max_pages=400):
    """Liste paginée, la plus récente d'abord. Premier passage : parcours complet (jusqu'à une page vide).
    Ensuite : arrêt après 3 pages sans PDF absent de la liste mémorisée."""
    links, empty, complete, page = {}, 0, False, 0
    for page in range(max_pages):
        h = cb.get_html(f"{LISTING}?page={page}")
        found = {f"{d[:4]}-{d[4:6]}-{d[6:]}": (u if u.startswith("http") else cb.BASE + u)
                 for u, d in re.findall(r'href="([^"]*resume_seance_(\d{8})\.pdf)"', h, re.I)}
        if not found:
            complete = True
            break
        new = {d for d in found if d not in known_listing and d not in links}
        for d, u in found.items():
            links.setdefault(d, u)
        empty = empty + 1 if not new else 0
        if known_listing and empty >= 3:
            break
        time.sleep(0.15)
    return links, page + 1, complete


MAX_PDFS = int(__import__("os").environ.get("MASI_MAX_PDFS", "200"))   # par exécution : reprise par tranches
TIME_BUDGET_S = int(__import__("os").environ.get("MASI_TIME_BUDGET_S", "900"))


def save_cache(cache, sessions, now):
    cache.update(updated_at=now, source=SRC, sessions=sessions)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main():
    from pypdf import PdfReader
    t0 = time.time()
    now = datetime.now(timezone.utc).isoformat()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"sessions": {}}
    sessions = cache["sessions"]
    rep = {"run_at": now, "source": cb.BASE + LISTING, "errors": [], "parsed": 0, "corrections": [], "added": []}
    try:
        listing = cache.get("listing", {})
        found, pages, complete = list_pdfs(listing if cache.get("listing_complete") else {})
        listing.update({d: u for d, u in found.items() if d not in listing})
        cache["listing"] = listing
        cache["listing_complete"] = cache.get("listing_complete") or complete
        pdfs = listing
        rep.update(listing_pages=pages, listing_complete=cache["listing_complete"], pdfs_listed=len(pdfs),
                   listed_range=[min(pdfs), max(pdfs)] if pdfs else None)
    except Exception as e:
        rep["errors"].append(f"listing: {type(e).__name__}: {e}")
        pdfs = cache.get("listing", {})
    todo = [(d, u) for d, u in sorted(pdfs.items(), reverse=True) if not (d in sessions and sessions[d].get("masi"))]
    rep["remaining_before_run"] = len(todo)
    for n, (d, url) in enumerate(todo[:MAX_PDFS]):
        if time.time() - t0 > TIME_BUDGET_S:
            rep["stopped"] = "budget de temps atteint ; reprise à la prochaine exécution"
            break
        if n and n % 25 == 0:
            save_cache(cache, sessions, now)
        try:
            b = cb._get(url, accept="application/pdf")
            text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages)
            rec = parse_resume(text, d)
            rec.update(url=url, collected_at=now)
            sessions[d] = rec
            rep["parsed"] += 1
            time.sleep(0.15)
        except Exception as e:
            rep["errors"].append(f"{d}: {type(e).__name__}: {e}"[:200])
    prev = None
    cal = trading_days()
    for d in sorted(sessions):
        rec = sessions[d]
        rec.pop("implied_daily_pct", None)
        rec["status"] = ",".join(validate(rec, prev, cal)) or "validated"
        if rec.get("masi"):
            prev = rec
    save_cache(cache, sessions, now)
    rep["remaining_after_run"] = len([1 for d in pdfs if not sessions.get(d, {}).get("masi")])

    rows = {r["date"]: r for r in json.loads(HIST.read_text(encoding="utf-8"))} if HIST.exists() else {}
    for d, rec in sorted(sessions.items()):
        if rec["status"] not in ("validated", "previous_session_missing_in_archive"):
            continue  # valeur douteuse : non fusionnée, visible dans le rapport
        r = rows.get(d)
        breadth = round(rec["advancers"] / (rec["advancers"] + rec["decliners"]), 4) if rec["advancers"] + rec["decliners"] else None
        new = {"masi": rec["masi"], "masi_source": SRC, "masi_daily_pct_published": rec.get("masi_daily_pct"),
               "volume_mad": rec.get("central_actions_mad"), "volume_source": SRC + " — marché central actions",
               "volume_global_mad": rec.get("volume_global_mad"), "breadth": breadth,
               "advancers": rec["advancers"], "decliners": rec["decliners"], "breadth_source": SRC,
               "source_url": rec["url"], "quality": "official_session_summary", "control": rec["status"]}
        if r is None:
            rows[d] = {"date": d, "source": SRC, **new}
            rep["added"].append(d)
        else:
            if r.get("masi") and abs(r["masi"] / rec["masi"] - 1) > 0.0005:
                rep["corrections"].append({"date": d, "previous": r["masi"], "previous_source": r.get("masi_source") or r.get("source"), "official": rec["masi"]})
            r.update(new)
    ordered = [rows[k] for k in sorted(rows)]
    HIST.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    vals = [s for s in sessions.values() if s.get("masi")]
    rep.update(sessions_official=len(vals), official_range=[min(s["date"] for s in vals), max(s["date"] for s in vals)] if vals else None,
               anomalies=[d for d, s in sessions.items() if s["status"] not in ("validated", "previous_session_missing_in_archive")],
               archive_gaps=[d for d, s in sessions.items() if s["status"] == "previous_session_missing_in_archive"],
               market_history_sessions=len(ordered))
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, list) or len(v) < 8 else f"{len(v)} éléments") for k, v in rep.items()}, ensure_ascii=False))
    for e in rep["errors"][:5]:
        print(f"::warning title=collect_masi_history::{e}")
    if not vals:
        sys.exit(1)


if __name__ == "__main__":
    main()
