"""Extraction d'états financiers publiés (communiqués / comptes consolidés PDF des émetteurs).

Principe : aucune saisie manuelle. Chaque grandeur est lue sur une ligne de tableau repérée par
son libellé et suivie de deux montants (exercice N et N-1). La ligne source est conservée comme
preuve, l'unité est déduite de l'en-tête de tableau le plus proche (milliers / millions de MAD).
Des contrôles croisés décident du statut ; une grandeur non trouvée reste null.
"""
import math
import re

NOTE = r"(?:\s+\d+(?:\.\d+)+(?:\s*/\s*\d+(?:\.\d+)+)?)?"       # renvoi de note « 3.4 », « 2.4 / 2.12 »
SUFFIX = r"(?:\s*\([^)\n]{0,80}\))?"                              # « (ou des propriétaires de la société mère) »
TAIL = r"\s+(-?\(?\d[\d ,()-]*)\s*$"                              # zone numérique en fin de ligne

LABELS = {
    "bank": {
        "pnb": [r"PRODUIT NET BANCAIRE(?: IFRS)?"],
        "operating_expenses": [r"Charges générales d'exploitation"],
        "depreciation": [r"Dotations aux amortissements et aux dépréciations des immobilisations incorporelles et corporelles",
                         r"Dotations aux amortissements et aux dépréciations des immobilisations"],
        "cost_of_risk": [r"Coût du risque(?: de crédit)?"],
        "net_income": [r"R[ÉE]SULTAT NET(?: CONSOLIDÉ)?(?=\s+-?\d)"],
        "net_income_group": [r"R[ÉE]SULTAT NET ?-? ?PART DU GROUPE", r"Résultat net,? ?-? ?part du groupe"],
        "eps": [r"Résultat (?:de base |net )?par action"],
        "equity_total": [r"Capitaux propres(?=\s+-?\d)"],
        "minority_interests": [],
        "total_assets": [r"TOTAL ACTIF(?: IFRS)?"],
        "customer_loans": [r"Prêts et créances sur la clientèle(?:, au coût amorti)?"],
    },
    "corporate": {
        "revenue": [r"Chiffre d'affaires(?: consolidé)?(?=\s+-?\d)"],
        "ebitda": [r"EBITDA(?=\s+-?\d)", r"Excédent brut d'exploitation(?=\s+-?\d)"],
        "operating_income": [r"Résultat d'exploitation(?: courant)?", r"Résultat opérationnel(?: courant)?", r"Résultat des activités opérationnelles"],
        "net_income": [r"Résultat net de l'ensemble consolidé", r"Résultat de l'ensemble consolidé", r"Résultat net consolidé"],
        "net_income_group": [r"Résultat net ?-? ?part du groupe", r"Résultat net de l'exercice ?-? ?part du groupe"],
        "eps": [r"Résultat (?:de base |net )?par action(?: en MAD)?", r"Calcul du résultat par action"],
        "equity_group": [r"Capitaux propres attribuables aux actionnaires\s*ordinaires de la société mère", r"Capitaux propres part du groupe"],
        "equity_total": [r"Capitaux propres de l'ensemble consolidé", r"Total capitaux propres", r"Capitaux propres totaux"],
        "minority_interests": [],
        "net_debt": [r"Endettement net", r"Dette nette"],
        "total_assets": [r"TOTAL ACTIF(?: IFRS)?", r"Total actif"],
    },
}
PER_SHARE = {"eps"}


def _number(tokens):
    """Un montant : premier groupe de 1 à 3 chiffres puis groupes de 3 ; seule la dernière partie peut porter une virgule."""
    core = [t.strip("()-") for t in tokens]
    ints = [c.split(",")[0] for c in core]
    if any("," in c for c in core[:-1]):
        return None
    if len(core) > 1 and (not 1 <= len(ints[0]) <= 3 or any(len(i) != 3 for i in ints[1:])):
        return None
    dec = core[-1].split(",")[1] if "," in core[-1] else ""
    val = float("".join(ints) + ("." + dec if dec else ""))
    return -val if tokens[0].startswith(("-", "(")) else val


def split_two(tail):
    """Découpe « 1 117 724 821 216 » en deux montants (N, N-1). Parmi les découpages valides, retient celui
    dont les deux montants sont les plus proches en ordre de grandeur. Renvoie (n, n_1, ambigu) ou None."""
    toks = re.findall(r"-?\(?\d+(?:,\d+)?\)?", tail)
    cands = []
    for k in range(1, len(toks)):
        a, b = _number(toks[:k]), _number(toks[k:])
        if a is not None and b is not None:
            cands.append((abs(math.log10(abs(a) + 1) - math.log10(abs(b) + 1)), a, b))
    if not cands:
        return None
    cands.sort()
    return cands[0][1], cands[0][2], len(cands) > 1 and cands[1][0] - cands[0][0] < 0.3


def unit_at(text, pos):
    """Unité du tableau : en-tête « milliers » / « millions » le plus proche avant la ligne."""
    head = text[max(0, pos - 6000):pos].lower()
    k = max(head.rfind("milliers"), head.rfind("en kdh"), head.rfind("kmad"))
    m = max(head.rfind("millions"), head.rfind("en mdh"), head.rfind("en mmad"))
    if k < 0 and m < 0:
        return None
    return 1e3 if k > m else 1e6


def flatten(text):
    return re.sub(r"[ \t   ]+", " ", text.replace("’", "'"))


def find(text, patterns, start=0, end=None, all_matches=False):
    flat = flatten(text)
    seg = flat[start:end]
    found = []
    for p in patterns:
        for m in re.finditer(r"^\s*" + p + SUFFIX + NOTE + TAIL, seg, re.M | re.I):
            two = split_two(m.group(1))
            if not two:
                continue
            rec = {"current": two[0], "previous": two[1], "ambiguous_split": two[2], "line": m.group(0).strip()[:220],
                   "unit": unit_at(flat, start + m.start()), "pos": start + m.start()}
            if not all_matches:
                return rec
            found.append(rec)
        if found:
            return found
    return found if all_matches else None


def minorities_near(text, equity):
    """Intérêts minoritaires au bilan, lus autour de la ligne « Capitaux propres » : ligne unique
    « Intérêts minoritaires » ou somme des lignes « … Part des minoritaires »."""
    if not equity:
        return None
    lo, hi = max(0, equity["pos"] - 1500), equity["pos"] + 1500
    single = find(text, [r"Intérêts minoritaires(?! \(ou)"], lo, hi)
    if single and single["current"] > 0:
        return {**single, "method": "ligne « Intérêts minoritaires » du bilan"}
    parts = find(text, [r"[^\n]{0,80}?Part des minoritaires"], lo, hi, all_matches=True)
    if parts:
        return {"current": sum(x["current"] for x in parts), "previous": sum(x["previous"] for x in parts),
                "unit": parts[0]["unit"], "line": " + ".join(x["line"][-70:] for x in parts)[:500],
                "method": f"somme de {len(parts)} lignes « Part des minoritaires » du bilan",
                "ambiguous_split": any(x["ambiguous_split"] for x in parts)}
    return None


def extract(text, model):
    out = {}
    for key, pats in LABELS[model].items():
        f = minorities_near(text, out.get("equity_total")) if key == "minority_interests" else find(text, pats)
        if not f:
            out[key] = None
            continue
        f.pop("pos", None) if key != "equity_total" else None
        if key in PER_SHARE:
            f["mad"], f["mad_previous"] = f["current"], f["previous"]
        elif f["unit"]:
            f["mad"], f["mad_previous"] = f["current"] * f["unit"], f["previous"] * f["unit"]
        else:
            f["mad"] = f["mad_previous"] = None
        out[key] = f
    if out.get("equity_total"):
        out["equity_total"].pop("pos", None)
    return out


def v(x, k="mad"):
    return x.get(k) if x else None


def checks(fin, model, shares_now):
    """Contrôles croisés ; renvoie (indicateurs dérivés, anomalies bloquantes, notes)."""
    errors, notes, d = [], [], {}
    for k, x in fin.items():
        if x and x.get("ambiguous_split"):
            notes.append(f"{k} : découpage des montants ambigu, valeur retenue selon la cohérence N / N-1")
    rn = v(fin.get("net_income_group"))
    if rn is None:
        errors.append("résultat net part du groupe introuvable")
    eps = v(fin.get("eps"))
    if rn and eps:
        implied = rn / eps
        d["shares_implied_by_published_eps"] = round(implied)
        if shares_now:
            ratio = shares_now / implied
            if abs(ratio - 1) > 0.03:
                if round(ratio) >= 2 and abs(ratio / round(ratio) - 1) <= 0.03:
                    notes.append(f"BPA publié calculé sur {round(implied):,} titres, {shares_now:,} titres aujourd'hui : "
                                 f"opération sur titres (facteur {round(ratio)}), BPA recalculé sur le nombre actuel de titres".replace(",", " "))
                else:
                    errors.append(f"BPA publié incohérent avec résultat / nombre de titres (rapport {ratio:.2f})")
    if shares_now and rn:
        d["eps_current_shares_mad"] = rn / shares_now
    eq_total, minor = v(fin.get("equity_total")), v(fin.get("minority_interests"))
    eq_group = v(fin.get("equity_group"))
    prev_group = v(fin.get("equity_group"), "mad_previous")
    if eq_group is None and eq_total is not None and minor is not None:
        eq_group = eq_total - minor
        pt, pm = v(fin.get("equity_total"), "mad_previous"), v(fin.get("minority_interests"), "mad_previous")
        prev_group = pt - pm if pt is not None and pm is not None else None
        d["equity_group_method"] = "capitaux propres totaux − intérêts minoritaires (" + fin["minority_interests"].get("method", "") + ")"
    if eq_group is None:
        errors.append("capitaux propres part du groupe introuvables")
    elif eq_group <= 0 or (eq_total and eq_group > eq_total * 1.001):
        errors.append("capitaux propres part du groupe incohérents")
    d["equity_group_mad"] = eq_group
    if eq_group and eq_group > 0 and rn:
        base = (eq_group + prev_group) / 2 if prev_group and prev_group > 0 else eq_group
        d["roe_pct"] = 100 * rn / base
        d["roe_basis"] = "capitaux propres part du groupe moyens N / N-1" if base != eq_group else "capitaux propres part du groupe de clôture"
    if shares_now and eq_group and eq_group > 0:
        d["book_value_per_share_mad"] = eq_group / shares_now
    if model == "bank":
        pnb, opex, dep, cor = (v(fin.get(k)) for k in ("pnb", "operating_expenses", "depreciation", "cost_of_risk"))
        if pnb and opex is not None:
            d["cost_income_pct"] = 100 * (abs(opex) + abs(dep or 0)) / pnb
        if pnb and cor is not None:
            d["cost_of_risk_to_pnb_pct"] = 100 * abs(cor) / pnb
        loans = v(fin.get("customer_loans"))
        if loans and cor is not None:
            d["cost_of_risk_to_loans_pct"] = 100 * abs(cor) / loans
        pp = v(fin.get("pnb"), "mad_previous")
        if pnb and pp:
            d["pnb_growth_pct"] = 100 * (pnb / pp - 1)
        if pnb is None:
            errors.append("PNB introuvable")
    else:
        rev, op = v(fin.get("revenue")), v(fin.get("operating_income"))
        if rev and op is not None:
            d["operating_margin_pct"] = 100 * op / rev
        if rev and rn is not None:
            d["net_margin_pct"] = 100 * rn / rev
        rp = v(fin.get("revenue"), "mad_previous")
        if rev and rp:
            d["revenue_growth_pct"] = 100 * (rev / rp - 1)
        eb = v(fin.get("ebitda"))
        if rev and eb:
            d["ebitda_margin_pct"] = 100 * eb / rev
        nd = v(fin.get("net_debt"))
        if nd is not None and eb:
            d["net_debt_to_ebitda"] = nd / eb
        ta = v(fin.get("total_assets"))
        if ta and eq_total:
            d["equity_ratio_pct"] = 100 * eq_total / ta   # autonomie financière : capitaux propres totaux / total bilan
        if rev is None:
            errors.append("chiffre d'affaires introuvable")
    rp = v(fin.get("net_income_group"), "mad_previous")
    if rn and rp and rp > 0:
        d["net_income_growth_pct"] = 100 * (rn / rp - 1)
    return d, errors, notes
