"""Lecture en clair du score fondamental : profil, points forts, points de vigilance, comparaison aux pairs.

Tout est dérivé des chiffres déjà calculés (comptes publiés, cours, dividendes, liquidité) ; aucune donnée ajoutée.
Les règles sont explicites et identiques pour toutes les sociétés :
- point fort : composante ≥ 65 / 100 ; point de vigilance : composante ≤ 35 / 100 ;
- comparaison aux pairs : médiane des sociétés analysées du même modèle sectoriel (banque, assurance, société) ;
- profil :
  « Solide » : score ≥ 55, comptes complets, aucune composante ≤ 35 (hors dividende), liquidité suffisante ;
  « Contrasté » : comptes complets mais au moins un point de vigilance ;
  « Incomplet » : une composante n'a pas pu être calculée (catégorie À surveiller).
Ce n'est ni une prévision ni une recommandation d'achat ou de vente.
"""
from statistics import median

STRONG, WEAK = 65, 35
MODEL_LABEL = {"bank": "banques", "insurance": "assurances", "corporate": "sociétés non financières"}


def _f(v, d=1):
    return "n.d." if v is None else f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def peer_medians(items):
    """Médianes par modèle sectoriel, sur les sociétés dont le score est calculé."""
    out = {}
    for m in {x.get("model") for x in items}:
        grp = [x for x in items if x.get("model") == m and x.get("score") is not None]
        med = {}
        for k in ("pe", "pb", "roe_pct", "dividend_yield_pct"):
            vals = [x[k] for x in grp if isinstance(x.get(k), (int, float)) and x[k] > 0]
            med[k] = round(median(vals), 2) if len(vals) >= 3 else None
        med["n"] = len(grp)
        out[m] = med
    return out


def explain(x, med):
    """Ajoute profile, strengths, watchpoints, peer_comparison et summary à un résultat evaluate_fundamental."""
    if x.get("score") is None:
        return x
    c, ind, m = x.get("components") or {}, x.get("indicators") or {}, x.get("model")
    med = med.get(m) or {}
    strengths, watch = [], []

    def cmp(val, ref, lower_is_better, unit):
        if val is None or ref is None:
            return ""
        better = val < ref if lower_is_better else val > ref
        return f" ({'mieux' if better else 'moins bien'} que la médiane des {MODEL_LABEL.get(m, 'pairs')} : {_f(ref)}{unit})"

    # Valorisation
    v = c.get("valuation")
    pe_txt = f"PER {_f(x.get('pe'))}×{cmp(x.get('pe'), med.get('pe'), True, '×')}" if x.get("pe") else "société en perte : PER non défini"
    pb_txt = f"cours / valeur comptable {_f(x.get('pb'), 2)}×{cmp(x.get('pb'), med.get('pb'), True, '×')}"
    if v is not None and v >= STRONG:
        strengths.append(f"Valorisation attractive : {pe_txt}, {pb_txt}")
    elif v is not None and v <= WEAK:
        watch.append(f"Valorisation exigeante : {pe_txt}, {pb_txt}")
    # Qualité
    q = c.get("quality")
    extra = (f", coefficient d'exploitation {_f(ind.get('cost_income_pct'))} %" if m == "bank" else
             f", charges / produits d'assurance {_f(ind.get('insurance_expense_ratio_pct'))} %" if m == "insurance" else
             f", marge d'exploitation {_f(ind.get('operating_margin_pct'))} %" if ind.get("operating_margin_pct") is not None else "")
    roe_txt = f"ROE {_f(x.get('roe_pct'))} %{cmp(x.get('roe_pct'), med.get('roe_pct'), False, ' %')}{extra}"
    if q is not None and q >= STRONG:
        strengths.append("Rentabilité élevée : " + roe_txt)
    elif q is not None and q <= WEAK:
        watch.append("Rentabilité faible : " + roe_txt)
    # Croissance
    g = c.get("growth")
    top = ind.get("pnb_growth_pct") if m == "bank" else ind.get("revenue_growth_pct")
    g_txt = f"{'PNB' if m == 'bank' else 'chiffre d’affaires'} {_f(top)} %, résultat part du groupe {_f(ind.get('net_income_growth_pct'))} % sur un an"
    if g is not None and g >= STRONG:
        strengths.append("Croissance : " + g_txt)
    elif g is not None and g <= WEAK:
        watch.append("Croissance faible ou en recul : " + g_txt)
    if (ind.get("net_income_growth_pct") or 0) > 100:
        watch.append(f"Résultat en hausse de {_f(ind.get('net_income_growth_pct'), 0)} % : vérifier s'il s'agit d'un élément exceptionnel non récurrent")
    # Structure
    s = c.get("structure")
    s_txt = (f"coût du risque {_f(ind.get('cost_of_risk_to_loans_pct'), 2)} % des crédits" if m == "bank" else
             f"dette nette / EBITDA {_f(ind.get('net_debt_to_ebitda'), 2)}×" if ind.get("net_debt_to_ebitda") is not None else
             f"capitaux propres / total bilan {_f(ind.get('equity_ratio_pct'))} %")
    if s is not None and s >= STRONG:
        strengths.append("Solidité financière : " + s_txt)
    elif s is not None and s <= WEAK:
        watch.append("Structure financière tendue : " + s_txt)
    # Dividende
    dy = x.get("dividend_yield_pct")
    if dy is not None and dy >= 4:
        strengths.append(f"Dividende : rendement {_f(dy, 2)} % sur 12 mois{cmp(dy, med.get('dividend_yield_pct'), False, ' %')}")
    elif not dy:
        watch.append("Aucun dividende ordinaire détaché sur les 12 derniers mois")
    elif c.get("dividend") is not None and c["dividend"] <= WEAK:
        watch.append(f"Dividende modeste : rendement {_f(dy, 2)} % sur 12 mois{cmp(dy, med.get('dividend_yield_pct'), False, ' %')}")
    # Liquidité / risque de marché
    liq = x.get("liquidity") or {}
    if liq.get("tier") == "faible":
        watch.append(f"Liquidité faible : {_f((liq.get('avg_turnover_mad_20d') or 0) / 1e6, 2)} M MAD échangés en moyenne par séance (20 j) — entrées et sorties difficiles")
    if (x.get("volatility_annual_pct") or 0) > 35:
        watch.append(f"Cours très volatil : {_f(x.get('volatility_annual_pct'))} % annualisés")
    missing = x.get("missing_components") or []
    names = {"valuation": "valorisation", "quality": "rentabilité", "growth": "croissance", "structure": "structure financière", "dividend": "dividende"}
    if missing:
        watch.append("Donnée non calculable : " + ", ".join(names.get(k, k) for k in missing) + " (score partiel)")
    # le dividende n'entre pas dans le profil : une société en croissance peut légitimement peu distribuer
    weak_comp = [k for k, val in c.items() if k != "dividend" and val is not None and val <= WEAK]
    if missing:
        profile = "Incomplet"
    elif x["score"] >= 55 and not weak_comp and liq.get("tier") != "faible":
        profile = "Solide"
    else:
        profile = "Contrasté"
    x.update(profile=profile, strengths=strengths, watchpoints=watch,
             peer_comparison={"model": m, "peers": med.get("n"), "median_pe": med.get("pe"), "median_pb": med.get("pb"),
                              "median_roe_pct": med.get("roe_pct"), "median_dividend_yield_pct": med.get("dividend_yield_pct")},
             summary=f"{profile} — {len(strengths)} point(s) fort(s), {len(watch)} point(s) de vigilance")
    return x
