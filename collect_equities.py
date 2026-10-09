"""Historique OHLCV officiel des actions cotées à Casablanca.

Source unique : service stock-historical de la Bourse de Casablanca (cours bruts,
non ajustés des dividendes / opérations sur titres). Historique durable : les
séances déjà stockées sont conservées, les nouvelles ajoutées, une séance
existante n'est remplacée que par une observation officielle.

Univers : EQUITY_UNIVERSE=pilot (défaut : ATW, BCP, IAM, MSA, MNG) ou all.
Échoue (code 1) si aucun titre n'a pu être collecté.
"""
import json, os, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import casablanca_source as cb

HIST = Path("data/equity_history.json")
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
        "source": cb.SOURCE_NAME, "source_endpoint": "api/boursenova/stock-historical", "collected_at": collected_at,
    }


def main():
    now = datetime.now(timezone.utc)
    collected_at = now.isoformat()
    store = json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else {}
    by_ticker = {c["ticker"]: c for c in store.get("companies", []) if c.get("ticker")}

    snap = cb.live_snapshot()
    live = {a["symbol"].strip(): a for a in snap["actions"] if a.get("symbol")}
    universe = sorted(live) if os.environ.get("EQUITY_UNIVERSE", "pilot") == "all" else PILOT
    today = now.astimezone(cb.TZ).date()
    report = {"run_at": collected_at, "source": cb.SOURCE_NAME, "endpoint": cb.BASE + "/api/boursenova/stock-historical",
              "session_status": snap["session_status"], "session_date": snap["session_date"],
              "universe": universe, "price_basis": "cours bruts non ajustés (adj_close = null)", "tickers": {}}

    for t in universe:
        meta = live.get(t, {})
        rep = report["tickers"].setdefault(t, {})
        try:
            items = cb.stock_history(t, START, today)
        except Exception as e:
            rep.update(status="SOURCE_ERROR", error=f"{type(e).__name__}: {e}")
            continue
        new = []
        for it in items:
            try:
                r = to_row(it, collected_at)
            except (KeyError, ValueError):
                continue
            # séance du jour exclue tant qu'elle n'est pas clôturée
            if r["date"] == today.isoformat() and snap["session_status"] != "closed":
                continue
            new.append(r)
        comp = by_ticker.setdefault(t, {"ticker": t, "rows": []})
        rows = {r["date"]: r for r in comp.get("rows", [])}
        for r in new:
            rows[r["date"]] = r
        ordered = [rows[k] for k in sorted(rows)]
        prev = None
        actions = []
        for r in ordered:
            flags = validate_row(r, prev)
            f = split_factor(prev, r) if "move_gt_10pct" in flags else None
            if f:
                flags = [x for x in flags if x != "move_gt_10pct"] + ["corporate_action_suspected"]
                actions.append({"date": r["date"], "estimated_factor": round(f, 4), "previous_close": prev, "open": r["open"],
                                "status": "à confirmer par un avis officiel ; aucune série ajustée n'est produite"})
            r["status"] = ",".join(flags) or "validated"
            prev = r["close"] or prev
        comp["corporate_actions_suspected"] = actions
        lab = (meta.get("emetteur") or {}).get("fr") or comp.get("name")
        comp.update({
            "ticker": t, "name": lab, "isin": comp.get("isin"), "code_valeur": meta.get("ce") or comp.get("code_valeur"),
            "sector": (meta.get("secteur") or {}).get("fr") or comp.get("sector"),
            "compartment": (meta.get("compartiment") or {}).get("fr") or comp.get("compartment"),
            "shares_outstanding": meta.get("nombreTitres") or comp.get("shares_outstanding"),
            "listing_exchange": "Casablanca Stock Exchange", "listing_country": "MA", "currency": "MAD",
            "listing_verified_by": "Présence dans la liste officielle live-market/actions de la Bourse de Casablanca" if meta else comp.get("listing_verified_by"),
            "source": cb.SOURCE_NAME, "rows": ordered})
        flagged = [r for r in ordered if r["status"] != "validated"]
        last = ordered[-1] if ordered else None
        rep.update(status="OK" if ordered else "NO_DATA", sessions=len(ordered), received=len(items), first_date=ordered[0]["date"] if ordered else None,
                   last_date=last["date"] if last else None, last_close=last["close"] if last else None,
                   flagged_sessions=len(flagged), flags_sample=[(r["date"], r["status"]) for r in flagged[:5]],
                   no_trade_sessions=sum(1 for r in ordered if r.get("traded") is False),
                   incomplete_volume_sessions=[r["date"] for r in ordered if r.get("incomplete_volume")], corporate_actions_suspected=actions)

    ok = [t for t, r in report["tickers"].items() if r.get("status") == "OK"]
    report["status"] = "OK" if len(ok) == len(universe) else ("PARTIAL" if ok else "FAILED")
    store = {"schema_version": 2, "updated_at": collected_at, "source": cb.SOURCE_NAME,
             "fields": {"close": "dernier cours de la séance (MAD)", "adj_close": "non fourni de façon fiable par la source : null",
                        "volume": "nombre de titres échangés", "turnover_mad": "montant échangé en MAD", "trades": "nombre de transactions"},
             "companies": sorted(by_ticker.values(), key=lambda c: c["ticker"])}
    if ok:
        HIST.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for t, r in report["tickers"].items():
        if r.get("status") != "OK":
            print(f"::error title=collect_equities {t}::{r.get('status')} {r.get('error', '')}")
        elif r.get("flagged_sessions"):
            print(f"::warning title=collect_equities {t}::{r['flagged_sessions']} séance(s) signalée(s) {r['flags_sample']}")
    print(json.dumps({t: {k: r.get(k) for k in ("status", "sessions", "first_date", "last_date", "last_close", "flagged_sessions", "error")} for t, r in report["tickers"].items()}, ensure_ascii=False, indent=1))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
