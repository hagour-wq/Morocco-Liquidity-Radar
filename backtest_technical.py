"""Backtest du score technique court terme (phase 3.6) — reproductible, sans regard vers le futur.

Protocole
- Calendrier : séances officielles (au moins 10 titres réellement échangés ; la séance recopiée
  du 17/09/2026 est exclue).
- À chaque date de rebalancement t (toutes les HOLD séances), le score de chaque titre est recalculé
  avec evaluate_technical(..., as_of=t) : seules les séances ≤ t sont visibles.
- Portefeuille : les TOP_N meilleurs scores parmi les valeurs ÉLIGIBLES à t (liquidité ≥ 1 M MAD/séance),
  équipondérés. Exécution à la clôture de la séance suivante (t+1), détention HOLD séances.
- Coûts : COST_PER_SIDE par aller simple, appliqués au turnover effectif.
- Référence 1 : univers équipondéré de toutes les valeurs éligibles à t (même calendrier, mêmes coûts).
- Référence 2 : proxy MASI = indice pondéré par la capitalisation totale publiée (non flottante),
  rendement de prix ; validé contre les clôtures MASI disponibles (corrélation des rendements).
- Analyse par quintiles : rendement moyen à HOLD séances par quintile de score, écart Q1 − Q5 et t-stat.

Limites (affichées dans le résultat)
- Rendements de prix (cours bruts) : dividendes non inclus, pour la stratégie comme pour les références.
- Biais de survivance : l'univers ne contient que les titres cotés au 09/10/2026.
- Un titre dont la période de détention traverse une opération sur titres présumée est exclu de cette période.
- Historique de ~3 ans : une seule phase de marché ; résultats statistiquement fragiles.
"""
import json, math, os
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, pstdev, stdev
import equity_store
from rank_equities import evaluate_technical

HOLDS = [int(x) for x in os.environ.get("BT_HOLDS", "5,10,20").split(",")]
TOP_N = int(os.environ.get("BT_TOP_N", 10))
COST_PER_SIDE = float(os.environ.get("BT_COST_PER_SIDE", 0.006))  # courtage + commission Bourse + TVA, hypothèse
RF_ANNUAL = float(os.environ.get("BT_RF", 0.0225))                  # taux directeur BAM actuel, approximation
WARMUP = 60
MIN_ELIGIBLE = 6
OUT = Path("data/technical_backtest.json")


def calendar(companies):
    count = {}
    for c in companies:
        for r in c["rows"]:
            if r.get("traded") and "stale_copy" not in str(r.get("status", "")):
                count[r["date"]] = count.get(r["date"], 0) + 1
    return sorted(d for d, n in count.items() if n >= 10)


def price_maps(companies):
    """Clôture et capitalisation connues à chaque date du calendrier (dernière valeur ≤ date)."""
    out = {}
    for c in companies:
        pts = sorted((r["date"], r["close"], r.get("market_cap_mad")) for r in c["rows"]
                     if r.get("close") and r["close"] > 0 and "stale_copy" not in str(r.get("status", "")))
        ca = {a["date"] for a in c.get("corporate_actions_suspected", [])}
        out[c["ticker"]] = (pts, ca)
    return out


def asof(pts, d):
    lo, hi = 0, len(pts) - 1
    if not pts or pts[0][0] > d:
        return None
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if pts[mid][0] <= d:
            lo = mid
        else:
            hi = mid - 1
    return pts[lo]


def period_return(prices, t, d0, d1):
    pts, ca = prices[t]
    a, b = asof(pts, d0), asof(pts, d1)
    if not a or not b or any(d0 < x <= d1 for x in ca):
        return None
    return b[1] / a[1] - 1


def stats(rets, years):
    """years : durée réelle couverte (dates calendaires), pas une hypothèse de 252 séances."""
    if len(rets) < 2 or not years:
        return None
    eq = [1.0]
    for r in rets:
        eq.append(eq[-1] * (1 + r))
    periods_per_year = len(rets) / years
    peak, mdd = 1.0, 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    vol = stdev(rets) * math.sqrt(periods_per_year)
    cagr = eq[-1] ** (1 / years) - 1
    return {"total_return_pct": round(100 * (eq[-1] - 1), 2), "annualized_return_pct": round(100 * cagr, 2),
            "annualized_volatility_pct": round(100 * vol, 2), "max_drawdown_pct": round(100 * mdd, 2),
            "sharpe": round((cagr - RF_ANNUAL) / vol, 2) if vol else None, "periods": len(rets),
            "equity_curve": [round(x, 5) for x in eq]}


def tstat(x):
    return round(mean(x) / (stdev(x) / math.sqrt(len(x))), 2) if len(x) > 2 and stdev(x) else None


def run(HOLD, companies, cal, prices):
    reb = list(range(WARMUP, len(cal) - HOLD - 1, HOLD))
    strat, univ, cap, dates, quint, turnover = [], [], [], [], {q: [] for q in range(1, 6)}, []
    prev, prev_u = set(), set()
    masi, masi_official = [], official_masi()
    cash_periods, sizes = 0, []
    spreads = []
    for i in reb:
        t, d0, d1 = cal[i], cal[i + 1], cal[i + 1 + HOLD]
        as_of = date.fromisoformat(t)
        scored = []
        for c in companies:
            x = evaluate_technical(c["ticker"], c.get("name"), c["rows"], as_of=as_of)
            if x.get("category") == "ELIGIBLE":
                r = period_return(prices, c["ticker"], d0, d1)
                if r is not None:
                    scored.append((x["score"], c["ticker"], r))
        # aucune période n'est sautée : avec peu de valeurs éligibles, le portefeuille se réduit
        # (au plus la moitié des éligibles) ; sous MIN_ELIGIBLE, la stratégie reste en liquidités.
        scored.sort(reverse=True)
        k = min(TOP_N, len(scored) // 2)
        top = scored[:k] if len(scored) >= MIN_ELIGIBLE else []
        cash_periods += 0 if top else 1
        held = {s[1] for s in top}
        to = len(held ^ prev) / (len(held) + len(prev)) if (held or prev) else 0.0
        turnover.append(to)
        cost = 2 * COST_PER_SIDE * to  # part du portefeuille vendue puis rachetée
        strat.append((mean(s[2] for s in top) if top else 0.0) - cost)
        sizes.append(len(top))
        uset = {s[1] for s in scored}
        to_u = len(uset ^ prev_u) / (len(uset) + len(prev_u)) if prev_u else 1.0  # entrées/sorties de l'univers éligible
        univ.append((mean(s[2] for s in scored) if scored else 0.0) - 2 * COST_PER_SIDE * to_u)
        prev_u = uset
        prev = held
        # proxy MASI : pondération par capitalisation publiée à d0
        w = [(asof(prices[t2][0], d0), period_return(prices, t2, d0, d1)) for t2 in prices]
        w = [(a[2], r) for a, r in w if a and a[2] and r is not None]
        tot = sum(a for a, _ in w)
        cap.append(sum(a * r for a, r in w) / tot if tot else 0.0)
        m0, m1 = masi_asof(masi_official, d0), masi_asof(masi_official, d1)
        masi.append(m1 / m0 - 1 if m0 and m1 else None)
        dates.append(d1)
        n = len(scored)
        if n < 10:
            continue  # analyse par quintiles seulement avec au moins 10 valeurs
        for q in range(5):
            part = scored[q * n // 5:(q + 1) * n // 5]
            if part:
                quint[q + 1].append(mean(s[2] for s in part))
        spreads.append(mean(s[2] for s in scored[:n // 5]) - mean(s[2] for s in scored[-(n // 5):]))

    first_start = cal[reb[0] + 1] if reb else None
    years = (date.fromisoformat(dates[-1]) - date.fromisoformat(first_start)).days / 365.25 if dates else None
    validation = validate_proxy(prices, cal) if HOLD == HOLDS[0] else None
    excess = [a - b for a, b in zip(strat, cap)]
    masi_cov = sum(x is not None for x in masi)
    masi_ok = masi_cov == len(masi) and masi
    excess_masi = [a - b for a, b in zip(strat, masi)] if masi_ok else []
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "RESEARCH_ONLY",
        "period": {"start": first_start, "end": dates[-1] if dates else None, "years": round(years, 2) if years else None, "rebalances": len(dates)},
        "parameters": {"hold_sessions": HOLD, "top_n": TOP_N, "cost_per_side_pct": 100 * COST_PER_SIDE,
                       "execution": "clôture de la séance suivant le signal", "risk_free_annual_pct": 100 * RF_ANNUAL,
                       "eligibility": "catégorie ÉLIGIBLE à la date du signal (montant moyen 20 j ≥ 1 M MAD)"},
        "strategy": stats(strat, years), "equal_weight_universe": stats(univ, years), "cap_weighted_proxy_masi": stats(cap, years),
        "masi_official": stats(masi, years) if masi_ok else {"status": "INCOMPLETE", "covered_periods": masi_cov, "periods": len(masi)},
        "excess_vs_masi": {"mean_period_pct": round(100 * mean(excess_masi), 3), "t_stat": tstat(excess_masi),
                           "hit_rate_pct": round(100 * sum(e > 0 for e in excess_masi) / len(excess_masi), 1)} if excess_masi else None,
        "excess_vs_proxy": {"mean_period_pct": round(100 * mean(excess), 3) if excess else None, "t_stat": tstat(excess),
                            "hit_rate_pct": round(100 * sum(e > 0 for e in excess) / len(excess), 1) if excess else None},
        "quintiles": {f"Q{q}": round(100 * mean(v), 3) for q, v in quint.items() if v},
        "q1_minus_q5": {"mean_period_pct": round(100 * mean(spreads), 3) if spreads else None, "t_stat": tstat(spreads)},
        "avg_turnover_pct": round(100 * mean(turnover), 1) if turnover else None,
        "avg_positions": round(mean(sizes), 1) if sizes else None, "cash_periods": cash_periods,
        "dates": dates, "proxy_validation": validation,
        "limits": ["Rendements de prix : dividendes non inclus (stratégie et références).",
                   "Biais de survivance : univers limité aux titres cotés au 09/10/2026.",
                   "Référence principale : MASI officiel (résumés de séance) ; le proxy pondéré par la capitalisation totale sert de contrôle.",
                   "Coûts de transaction : hypothèse de 0,6 % par aller simple ; impact de marché non modélisé au-delà du filtre de liquidité.",
                   "Environ 3 ans d'historique : une seule phase de marché, résultats statistiquement fragiles.",
                   "Performance passée : ne préjuge en rien des performances futures."],
    }
    return out


def main():
    companies = [c for c in equity_store.load_all() if c.get("rows")]
    cal = calendar(companies)
    prices = price_maps(companies)
    variants = {str(h): run(h, companies, cal, prices) for h in HOLDS}
    common = {k: variants[str(HOLDS[0])][k] for k in ("generated_at", "status", "proxy_validation", "limits")}
    for v in variants.values():
        for k in ("generated_at", "status", "proxy_validation", "limits"):
            v.pop(k, None)
    out = {**common, "protocol": __doc__.strip(), "variants": variants,
           "selection_warning": "Plusieurs horizons de détention sont présentés côte à côte ; retenir a posteriori le meilleur "
                                "introduit un biais de sélection. Aucun n'est présenté comme la stratégie de référence."}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for h, v in variants.items():
        st, px, ew = v["strategy"] or {}, v["cap_weighted_proxy_masi"] or {}, v["equal_weight_universe"] or {}
        print(f"H{h}: stratégie {st.get('annualized_return_pct')} % (MDD {st.get('max_drawdown_pct')}) | univers EW {ew.get('annualized_return_pct')} | proxy MASI {px.get('annualized_return_pct')} | excès t={v['excess_vs_proxy']['t_stat']} | Q1-Q5 t={v['q1_minus_q5']['t_stat']}")
    print("validation proxy", out["proxy_validation"])


def official_masi():
    """Clôtures MASI de source officielle (résumés de séance ou séance clôturée), par date."""
    p = Path("data/market_history.json")
    if not p.exists():
        return {}
    return {r["date"]: r["masi"] for r in json.loads(p.read_text(encoding="utf-8"))
            if r.get("masi") and "Bourse de Casablanca" in str(r.get("masi_source", ""))}


def masi_asof(series, d, tolerance_days=5):
    """Dernière clôture officielle ≤ d, si elle date de moins de tolerance_days (séance absente de l'archive)."""
    if d in series:
        return series[d]
    prior = [k for k in series if k <= d]
    if not prior:
        return None
    k = max(prior)
    return series[k] if (date.fromisoformat(d) - date.fromisoformat(k)).days <= tolerance_days else None


def validate_proxy(prices, cal):
    """Corrélation des rendements quotidiens du proxy avec les clôtures MASI disponibles (market_history.json)."""
    p = Path("data/market_history.json")
    if not p.exists():
        return None
    masi = {r["date"]: r["masi"] for r in json.loads(p.read_text(encoding="utf-8")) if r.get("masi")}
    days = [d for d in cal if d in masi]
    pairs = []
    for a, b in zip(days, days[1:]):
        if cal.index(b) - cal.index(a) != 1:
            continue
        w = [(asof(prices[t][0], a), period_return(prices, t, a, b)) for t in prices]
        w = [(x[2], r) for x, r in w if x and x[2] and r is not None]
        tot = sum(x for x, _ in w)
        if tot:
            pairs.append((sum(x * r for x, r in w) / tot, masi[b] / masi[a] - 1))
    if len(pairs) < 10:
        return {"pairs": len(pairs), "correlation": None}
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    mx, my = mean(xs), mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in pairs) / len(pairs)
    return {"pairs": len(pairs), "correlation": round(cov / (pstdev(xs) * pstdev(ys)), 3),
            "mean_abs_gap_bp": round(1e4 * mean(abs(x - y) for x, y in pairs), 1),
            "note": "Rendements quotidiens du proxy vs MASI officiel/secondaire sur les séances communes."}


if __name__ == "__main__":
    main()
