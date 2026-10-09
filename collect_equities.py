"""Historique OHLCV officiel des actions cotées à Casablanca.

Source unique : service stock-historical de la Bourse de Casablanca (cours bruts,
non ajustés des dividendes / opérations sur titres). Historique durable : les
séances déjà stockées sont conservées, les nouvelles ajoutées, une séance
existante n'est remplacée que par une observation officielle.

Univers : toutes les actions de la liste officielle (défaut) ou EQUITY_UNIVERSE=pilot (ATW, BCP, IAM, MSA, MNG).
Stockage : data/equities/<TICKER>.json (une séance par ligne). Collecte incrémentale (45 jours)
une fois l'historique constitué ; EQUITY_FULL_REFRESH=1 force un rechargement complet.
Échoue (code 1) si aucun titre n'a pu être collecté.
"""
import json, os, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import casablanca_source as cb
import equity_store as store

REPORT = Path("data/equity_collection_report.json")
PILOT = ["ATW", "BCP", "IAM", "MSA", "MNG"]
START = date.fromisoformat(os.environ.get("EQUITY_HISTORY_START", "2023-01-01"))


def validate_row(r, prev_close):
    flags = []
    c, o, h, l = r["close"], r["open"], r["high"], r["low"]
    if c is None or c <= 0:
        flags.append("close_non_positive")
    if h is not None and l is not None and c:
        if l > h or (o and not (l - 1e-6 <= o <= h + 1e-6)) or not (l - 1e-6 <= c <= h + 1e-6):
            flags.append("ohlc_incoherent")
    if r["volume"] is not None and r["volume"] < 0:
        flags.append("negative_volume")
    if r.get("incomplete_volume"):
        flags.append("incomplete_volume")
    if date.fromisoformat(r["date"]).weekday() >= 5:
        flags.append("weekend_date")
    if prev_close and c and abs(c / prev_close - 1) > 0.10:
        flags.append("move_gt_10pct")  # la Bourse de Casablanca plafonne en général à ±10 % / séance
    return flags


def split_factor(prev_close, row):
    """Rapport prev_close/open proche d'un entier ≥ 2 (ou de son inverse) : division ou regroupement
    de titres présumé. Retourne le facteur arrondi, sinon None."""
    if not prev_close or not row.get("open"):
        return None
    for ratio in (prev_close / row["open"], row["open"] / prev_close):
        n = round(ratio)
        if n >= 2 and abs(ratio / n - 1) < 0.12:
            return n if ratio == prev_close / row["open"] else 1 / n
    return None


def to_row(it, collected_at):
    """Distingue trois cas pour le volume :
    - séance échangée : volume > 0 ;
    - séance sans échange (traded=False) : ni ouverture, ni plus haut / bas, cours de référence reporté → volume 0 ;
    - enregistrement incomplet (incomplete_volume=True) : plus haut / bas présents mais volume 0 ou absent →
      volume, montant et nombre de transactions mis à null (donnée manquante, pas un zéro)."""
    r = _raw_row(it, collected_at)
    has_range = r["high"] is not None and r["low"] is not None
    if not r["volume"]:
        if has_range:
            r.update(volume=None, turnover_mad=None, trades=None, traded=None, incomplete_volume=True)
        else:
            r.update(volume=0.0, turnover_mad=0.0, trades=0.0, traded=False, incomplete_volume=False)
    else:
        r.update(traded=True, incomplete_volume=False)
    return r


def _raw_row(it, collected_at):
    return {
        "date": cb.parse_seance(it["seance"]).isoformat(),
        "open": cb.num(it.get("ouverture")), "high": cb.num(it.get("plusHaut")), "low": cb.num(it.get("plusBas")),
        "close": cb.num(it.get("dernierCours")), "adj_close": None,
        "volume": cb.num(it.get("titresEchanges")), "turnover_mad": cb.num(it.get("volumeEchanges")),
        "trades": cb.num(it.get("nbTransactions")), "market_cap_mad": cb.num(it.get("capitalisation")),
        "collected_at": collected_at,
    }


def fetch_rows(t, existing, today, collected_at, closed):
    """Collecte incrémentale : 45 derniers jours si l'historique stocké est récent et profond,
    sinon historique complet depuis START (premier passage ou trou)."""
    full = os.environ.get("EQUITY_FULL_REFRESH") == "1" or not existing or len(existing) < 200 or \
        (today - date.fromisoformat(existing[-1]["date"])).days > 30
    start = START if full else today - timedelta(days=45)
    items = cb.stock_history(t, start, today)
    new = []
    for it in items:
        try:
            r = to_row(it, collected_at)
        except (KeyError, ValueError):
            continue
        if r["date"] == today.isoformat() and not closed:  # séance du jour exclue tant qu'elle n'est pas clôturée
            continue
        new.append(r)
    return new, len(items), "full" if full else "incremental"


def annotate(rows):
    prev = None
    actions = []
    for r in rows:
        flags = validate_row(r, prev)
        f = split_factor(prev, r) if "move_gt_10pct" in flags else None
        if f:
            flags = [x for x in flags if x != "move_gt_10pct"] + ["corporate_action_suspected"]
            actions.append({"date": r["date"], "estimated_factor": round(f, 4), "previous_close": prev, "open": r["open"],
                            "status": "à confirmer par un avis officiel ; aucune série ajustée n'est produite"})
        r["status"] = ",".join(flags) or "validated"
        prev = r["close"] or prev
    return actions


def main():
    now = datetime.now(timezone.utc)
    collected_at = now.isoformat()
    snap = cb.live_snapshot()
    live = {a["symbol"].strip(): a for a in snap["actions"] if a.get("symbol")}
    universe = PILOT if os.environ.get("EQUITY_UNIVERSE", "all") == "pilot" else sorted(live)
    if not universe:
        raise SystemExit("Liste officielle des actions vide : arrêt sans écriture.")
    today = now.astimezone(cb.TZ).date()
    report = {"run_at": collected_at, "source": cb.SOURCE_NAME, "endpoint": cb.BASE + "/api/boursenova/stock-historical",
              "session_status": snap["session_status"], "session_date": snap["session_date"], "universe_size": len(universe),
              "price_basis": "cours bruts non ajustés (adj_close = null)", "tickers": {}}
    saved = []
    for t in universe:
        meta = live.get(t, {})
        rep = report["tickers"].setdefault(t, {})
        comp = store.load(t) or {"ticker": t, "rows": []}
        try:
            new, received, mode = fetch_rows(t, comp.get("rows"), today, collected_at, snap["session_status"] == "closed")
        except Exception as e:
            rep.update(status="SOURCE_ERROR", error=f"{type(e).__name__}: {e}"[:300])
            continue
        rows = {r["date"]: r for r in comp.get("rows", [])}
        for r in new:
            rows[r["date"]] = r
        ordered = [rows[k] for k in sorted(rows)]
        for r in ordered:  # provenance portée au niveau du fichier (identique pour toutes les séances)
            r.pop("source", None), r.pop("source_endpoint", None)
        actions = annotate(ordered)
        comp.update({
            "ticker": t, "name": (meta.get("emetteur") or {}).get("fr") or comp.get("name"), "isin": comp.get("isin"),
            "code_valeur": meta.get("ce") or comp.get("code_valeur"),
            "sector": (meta.get("secteur") or {}).get("fr") or comp.get("sector"),
            "compartment": (meta.get("compartiment") or {}).get("fr") or comp.get("compartment"),
            "shares_outstanding": meta.get("nombreTitres") or comp.get("shares_outstanding"),
            "listing_exchange": "Casablanca Stock Exchange", "listing_country": "MA", "currency": "MAD",
            "listing_verified_by": "Présence dans la liste officielle live-market/actions de la Bourse de Casablanca",
            "source": cb.SOURCE_NAME, "source_endpoint": cb.BASE + "/api/boursenova/stock-historical", "updated_at": collected_at, "corporate_actions_suspected": actions,
            "fields": {"close": "dernier cours (MAD)", "adj_close": "null : non fourni de façon fiable", "volume": "titres échangés",
                       "turnover_mad": "montant échangé (MAD)", "trades": "nombre de transactions"},
            "rows": ordered})
        if ordered:
            store.save(comp)
            saved.append(comp)
        flagged = [r for r in ordered if r["status"] != "validated"]
        last = ordered[-1] if ordered else None
        rep.update(status="OK" if ordered else "NO_DATA", mode=mode, sessions=len(ordered), received=received,
                   first_date=ordered[0]["date"] if ordered else None, last_date=last["date"] if last else None,
                   last_close=last["close"] if last else None, flagged_sessions=len(flagged),
                   flags_sample=[(r["date"], r["status"]) for r in flagged[:5]],
                   no_trade_sessions=sum(1 for r in ordered if r.get("traded") is False),
                   incomplete_volume_sessions=[r["date"] for r in ordered if r.get("incomplete_volume")],
                   corporate_actions_suspected=actions)
        time.sleep(0.2)  # courtoisie envers le serveur

    if saved:
        store.save_index(store.load_all(), collected_at)
    ok = [t for t, r in report["tickers"].items() if r.get("status") == "OK"]
    bad = {t: r for t, r in report["tickers"].items() if r.get("status") != "OK"}
    report["status"] = "OK" if not bad else ("PARTIAL" if ok else "FAILED")
    report["ok_count"], report["failed"] = len(ok), {t: r.get("error") or r.get("status") for t, r in bad.items()}
    report["corporate_actions_suspected"] = {t: r["corporate_actions_suspected"] for t, r in report["tickers"].items() if r.get("corporate_actions_suspected")}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if bad:
        print(f"::{'error' if not ok else 'warning'} title=collect_equities::{len(bad)} titre(s) non collecté(s) : " + ", ".join(f"{t} ({v})" for t, v in list(report['failed'].items())[:15]))
    if report["corporate_actions_suspected"]:
        print("::warning title=collect_equities::Opérations sur titres présumées : " + ", ".join(f"{t} {a[-1]['date']}" for t, a in report["corporate_actions_suspected"].items()))
    print(json.dumps({"status": report["status"], "ok": len(ok), "failed": report["failed"]}, ensure_ascii=False))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
