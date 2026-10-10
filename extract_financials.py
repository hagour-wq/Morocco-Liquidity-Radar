"""Extraction d'états financiers publiés (communiqués / comptes consolidés PDF des émetteurs).

Principe : aucune saisie manuelle. Chaque grandeur est lue sur une ligne de tableau repérée par
son libellé et suivie de deux montants (exercice N et N-1). La ligne source est conservée comme
preuve, l'unité est déduite de l'en-tête de tableau le plus proche (milliers / millions de MAD).
Des contrôles croisés décident du statut ; une grandeur non trouvée reste null.
"""
import math
import re

NOTE = r"(?:\s+(?:N\s?\.\s?\d{1,2}|Note\s+\d{1,2})|\s+\d{1,2}(?:\.\d{1,2})+(?:\s*/\s*\d{1,2}(?:\.\d{1,2})+)?)?"       # renvoi de note « 3.4 », « 2.4 / 2.12 »
SUFFIX = r"(?:\s*\((?:\d{1,2}|(?=[^)\n]*[A-Za-zÀ-ÿ])[^)\n]{0,80})\))?"                              # « (ou des propriétaires de la société mère) »
TAIL = r"\s+((?:[-–]\s?)?\(?\d[\d ,.()%+–-]*)[A-Z]?\s*$"     # zone numérique en fin de ligne (lettre isolée collée : texte vertical en marge)                              # zone numérique en fin de ligne

RNPG = r"R[ÉE]SULTATS? NETS?(?: DE L'EXERCICE| CONSOLIDÉ)?\s*[-,(]?\s*PART DU GROUPE\)?"
LABELS = {
    "bank": {
        "pnb": [r"PRODUIT NET BANCAIRE(?: IFRS| CONSOLIDÉ)?"],
        "operating_expenses": [r"Charges g[ée]n[ée]rales d'exploitation"],
        "depreciation": [r"Dotations aux amortissements et aux dépréciations des immobilisations incorporelles et corporelles",
                         r"Dotations aux amortissements et aux dépréciations des immobilisations"],
        "cost_of_risk": [r"Coût du risque(?: de crédit)?"],
        "net_income": [r"R[ÉE]SULTAT NET(?: CONSOLIDÉ)?(?=\s+-?\d)"],
        "net_income_group": [RNPG],
        "eps": [r"Résultat (?:de base |net )?par action"],
        "equity_total": [r"Capitaux propres(?: consolidés)?(?=\s+-?\d)", r"Total capitaux propres(?: consolid[ée]s)?"],
        "minority_interests": [],
        "total_assets": [r"TOTAL ACTIF(?: IFRS)?", r"TOTAL DE L\s?'\s?ACTIF"],
        "customer_loans": [r"Prêts et créances sur la clientèle(?:, au coût amorti)?"],
    },
    "corporate": {
        "revenue": [r"Chiffres? d'affaires(?: consolidé)?(?=\s+(?:-?\d|N\s?\.|Note))", r"Produits des activit[ÉE]s ordinaires"],
        "ebitda": [r"EBITDA(?=\s+-?\d)", r"Excédent brut d'exploitation(?=\s+-?\d)"],
        "operating_income": [r"Résultat d'exploitation(?: courant)?", r"Résultat opérationnel(?: courant)?", r"Résultat des activités opérationnelles"],
        "net_income": [r"Résultat net de l'ensemble consolidé", r"Résultat de l'ensemble consolidé", r"Résultat net consolidé"],
        "net_income_group": [RNPG],
        "eps": [r"Résultat (?:de base |net )?par action(?: en MAD)?", r"Calcul du résultat par action"],
        "equity_group": [r"Capitaux propres attribuables aux (?:actionnaires\s*ordinaires|propriétaires) de la société mère",
                         r"(?:Total )?Capitaux propres\s*[-,]?\s*\(?(?:part du groupe|du groupe|part groupe)\)?"],
        "equity_total": [r"Capitaux propres (?:de l'|d')ensemble(?: consolidé)?", r"Total (?:des )?capitaux propres(?: consolidés)?", r"Capitaux propres (?:totaux|consolidés)",
                         r"Capitaux propres(?=\s+-?\d)"],
        "minority_interests": [],
        "net_debt": [r"Endettement net", r"Dette nette"],
        "share_capital": [r"Capital(?: social)?(?=\s+-?\d)"],
        "total_assets": [r"TOTAL ACTIF(?: IFRS)?", r"Total actifs?(?=\s+-?\d)", r"TOTAL DE L\s?'\s?ACTIF", r"Total (?:du )?bilan", r"TOTAL DU PASSIF"],
    },
    "insurance": {
        "revenue": [r"Produits des activités d'assurance", r"Primes (?:émises|acquises)(?: brutes)?"],
        "insurance_expenses": [r"Charges afférentes aux activités d'assurance", r"Charges des activités d'assurance"],
        "net_income": [r"Résultat net consolidé", r"Résultat net de l'ensemble consolidé"],
        "net_income_group": [RNPG],
        "eps": [r"Résultat (?:de base |net )?par action"],
        "equity_group": [r"Capitaux propres\s*[-,(]?\s*part du groupe\)?"],
        "equity_total": [r"(?:Total )?Capitaux propres(?: consolidés)?(?=\s+-?\d)"],
        "minority_interests": [],
        "total_assets": [r"TOTAL ACTIF(?: IFRS)?", r"Total actif"],
    },
}
# Comptes sociaux (émetteur sans comptes consolidés dans le document) : modèle comptable marocain (CGNC / PCEC)
SOCIAL = {
    "corporate": {
        "revenue": [r"Chiffres? d'affaires(?=\s+-?\d)"],
        "operating_income": [r"R[ÉE]SULTAT D'EXPLOITATION"],
        "net_income_group": [r"R[ÉE]SULTATS? NETS? DE L'EXERCICE", r"R[ÉE]SULTAT NET(?=\s*\(XI ?- ?XII\))", r"R[ÉE]SULTAT NET(?=\s+-?\d)"],
        "equity_total": [r"T ?otal des capitaux propres"],
        "total_assets": [r"TOTAL (?:GÉNÉRAL|GENERAL|ACTIF)(?:\s*\(?\s*I\s*\+\s*II\s*\+\s*III\s*\)?)?"],
    },
    "bank": {
        "pnb": [r"PRODUIT NET BANCAIRE"],
        "operating_expenses": [r"Charges g[ée]n[ée]rales d'exploitation"],
        "cost_of_risk": [r"Coût du risque"],
        "net_income_group": [r"R[ÉE]SULTAT NET DE L'EXERCICE"],
        "equity_total": [r"Capitaux propres(?=\s+-?\d)"],
        "total_assets": [r"TOTAL (?:DE L')?ACTIF"],
    },
    "insurance": {},   # comptes sociaux d'assurance (modèle CGNC assurances) : non retenus, colonnes brutes / cessions / nettes
}
CONSOLIDATED_RN = r"(?:R[ÉE]SULTAT (?:NET )?(?:TOTAL )?(?:DE L'ENSEMBLE )?CONSOLIDÉ(?: DE L'EXERCICE)?|R[ÉE]SULTAT NET DU GROUPE)"   # le second : états consolidés PCEC
BALANCE = {"equity_group", "equity_total", "minority_interests", "net_debt", "total_assets", "customer_loans", "share_capital"}
PER_SHARE = {"eps"}


def _number(tokens):
    """Un montant : premier groupe de 1 à 3 chiffres puis groupes de 3 ; seule la dernière partie peut porter une virgule."""
    core = [t.strip("()-") for t in tokens]
    ints = [c.split(",")[0] for c in core]
    if any("," in c for c in core[:-1]) or not all(ints):
        return None
    if len(core) > 1 and (not 1 <= len(ints[0]) <= 3 or any(len(i) != 3 for i in ints[1:]) or ints[0].startswith("0")):
        return None
    if len(core) == 1 and len(ints[0]) > 3 and ints[0].startswith("0"):
        return None
    dec = core[-1].split(",")[1] if "," in core[-1] else ""
    val = float("".join(ints) + ("." + dec if dec else ""))
    return -val if tokens[0].startswith(("-", "(")) else val


def _partitions(toks, n):
    """Toutes les découpes de la suite de jetons en n montants valides."""
    if n == 1:
        x = _number(toks)
        return [[x]] if x is not None else []
    out = []
    for k in range(1, len(toks) - n + 2):
        a = _number(toks[:k])
        if a is None:
            continue
        out += [[a] + rest for rest in _partitions(toks[k:], n - 1)]
    return out


def _close(x, y, rel=0.0, absolute=1.5):
    return abs(x - y) <= max(absolute, rel * max(abs(x), abs(y)))


def _pct_ok(cur, prev, pct, dec=2):
    """Variation publiée compatible avec N / N-1, compte tenu de l'arrondi des montants affichés."""
    if not prev:
        return False
    tol = 100 * 0.5 / abs(prev) * (1 + abs(cur / prev)) + max(0.15, 0.5 * 10 ** -dec)
    return abs(100 * (cur / prev - 1) - pct) <= tol


def normalize_tail(tail, dash_as_sign=False):
    """Séparateur de milliers « . » -> espace. Tiret isolé : colonne vide (0) ou, si dash_as_sign,
    signe du montant qui suit (« - 185 186 »)."""
    tail = re.sub(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+)(?=,\d+\b|(?![\d.,]))", lambda m: m.group(1).replace(".", ""), tail)   # groupes à point : un seul jeton, frontières de colonnes conservées
    tail = re.sub(r"(?<![\d.,])(\d{1,3})\.(\d{1,2})(?![\d.,])", r"\1,\2", tail)
    if dash_as_sign:
        return re.sub(r"(?:(?<=\s)|^)[-–—]\s+(?=\d)", "-", tail)
    return re.sub(r"(?:(?<=\s)|^)[-–—](?=\s|$)", "0", tail)     # « - » : colonne vide


def parse_tail(tail):
    """Essaie le tiret isolé comme colonne vide puis comme signe ; retient une disposition à identité
    arithmétique si l'une des lectures en donne une."""
    a = _parse_tail(normalize_tail(tail))
    if not re.search(r"(?:^|\s)[-–—]\s", tail.strip() + " "):
        return a
    b = _parse_tail(normalize_tail(tail, dash_as_sign=True))
    plain = lambda r: r is None or r[2] in ("N / N-1", "3 colonnes : N et N-1 = deux premières colonnes")
    if tail.strip()[:1] in "-–—" and tail.strip()[1:2] == " " and b:
        return b
    if a and not plain(a):
        return a
    if b and not plain(b):
        return b
    lead = tail.strip()[:1] in "-–—" and tail.strip()[1:2] == " "
    return (b or a) if lead else (a or b)



def _parse_tail(tail):
    """Lit la zone numérique d'une ligne d'état financier et renvoie (N, N-1, disposition, ambigu) ou None.
    Dispositions reconnues :
    - deux colonnes N / N-1 ;
    - avec variation publiée en % (ordre des colonnes vérifié par le %, colonne d'écart éventuelle) ;
    - CPC marocain : propres à l'exercice, exercices précédents, total N (= somme), total N-1 ;
    - trois colonnes N / N / N-1 (colonne intermédiaire vide) ou N / N-1 / écart ;
    - trois colonnes de même ordre de grandeur sans identité : deux premières retenues (marqué ambigu)."""
    raw = re.findall(r"([+-]?\s?\d+(?:,\d+)?)\s*%", tail)
    pcts = [float(p.replace(",", ".").replace(" ", "")) for p in raw]
    dec = len(raw[0].split(",")[1]) if raw and "," in raw[0] else 0
    seg = re.split(r"[+-]?\s?\d+(?:,\d+)?\s*%", tail)[0]
    toks = re.findall(r"-?\(?\d+(?:,\d+)?\)?", seg)
    if len(toks) < 2:
        return None
    if pcts:
        sols = set()
        for a, b in _partitions(toks, 2):
            if _pct_ok(a, b, pcts[0], dec):
                sols.add((a, b, "N / N-1 / variation %"))
            elif _pct_ok(b, a, pcts[0], dec):
                sols.add((b, a, "N-1 / N / variation % (ordre vérifié par le %)"))
        for a, b, c in _partitions(toks, 3):
            if _close(a - b, c) and _pct_ok(a, b, pcts[0], dec):
                sols.add((a, b, "N / N-1 / écart / variation %"))
            elif _close(b - a, c) and _pct_ok(b, a, pcts[0], dec):
                sols.add((b, a, "N-1 / N / écart / variation %"))
        if sols:
            vals = {(x[0], x[1]) for x in sols}
            x = sorted(sols)[0]
            return x[0], x[1], x[2], len(vals) > 1
        return None
    sols = {}
    for a, b, c, d in _partitions(toks, 4):
        if abs(c) >= 1000 and abs(a + b - c) <= (0.011 if "," in tail else 1.0):
            sols.setdefault("CPC : exercice + exercices précédents = total N ; total N-1", set()).add((c, d))
        elif a == 0 and b == 0 and abs(c) >= 1000 and abs(d) >= 1 and 0.05 <= abs(c / d) <= 20:
            sols.setdefault("CPC : colonnes de détail vides ; total N ; total N-1", set()).add((c, d))
        elif abs(c) >= 1000 and b >= 0 and abs(a - b - c) <= (0.011 if "," in tail else 1.0):
            sols.setdefault("Bilan actif : brut − amortissements = net N ; net N-1", set()).add((c, d))
    if not sols:
        for a, b, c in _partitions(toks, 3):
            if a == b and a != 0:
                sols.setdefault("N / total N / N-1", set()).add((b, c))
            elif _close(a - b, c) and c != 0 and not (b == 0 and a == c):   # « X 0,00 X » : propres + précédents = total N, sans N-1
                sols.setdefault("N / N-1 / écart", set()).add((a, b))
    if sols:
        layout, vals = next(iter(sols.items()))
        allv = set().union(*sols.values())
        a, b = sorted(vals)[0]
        return a, b, layout, len(allv) > 1
    mag = lambda x: math.log10(abs(x) + 1)
    cands = sorted((abs(mag(a) - mag(b)), a, b) for a, b in _partitions(toks, 2))
    three = sorted((max(mag(a), mag(b), mag(c)) - min(mag(a), mag(b), mag(c)), a, b) for a, b, c in _partitions(toks, 3)
                   if (a > 0) == (b > 0) == (c > 0))
    if three and three[0][0] < 0.5 and (not cands or cands[0][0] > 1.0):
        return three[0][1], three[0][2], "3 colonnes : N et N-1 = deux premières colonnes", True
    if not cands:
        return None
    return cands[0][1], cands[0][2], "N / N-1", len(cands) > 1 and cands[1][0] - cands[0][0] < 0.3


def split_two(tail):
    """Compatibilité : (N, N-1, ambigu)."""
    r = parse_tail(tail)
    return (r[0], r[1], r[3]) if r else None


UNIT_RE = re.compile(r"(milliers|en kdh|kmad|\bkdh\b)|(millions|en mdh|\bmdh\b|en mmad|\bmmad\b)|(?:montants?\s+)?\ben\s+(?:dhs?|dirhams|mad)\b", re.I)


def unit_at(text, pos, tail=""):
    """Unité du tableau : dernière mention d'unité sur une ligne d'en-tête (sans montants en fin de ligne)
    dans les 6 000 caractères qui précèdent ; à défaut, montants à centimes ⇒ dirhams."""
    lo = max(0, pos - 6000)
    best = None
    lines = text[lo:pos].split("\n")
    for i, l in enumerate(lines):
        nxt = next((x for x in lines[i + 1:i + 3] if x.strip()), "")
        if _PAIR.search(nxt) and _chart_axis(lines, lines.index(nxt, i + 1)):
            continue   # « (en MDH) » au-dessus d'un graphique en barres : pas l'unité des tableaux
        if re.match(r"\s*\(?(?:en|montants? en)\s+(?:kmad|kdh|mmad|mdh|milliers|millions)\b", l, re.I):
            for m in list(UNIT_RE.finditer(l))[:1]:
                best = 1e3 if m.group(1) else 1e6 if m.group(2) else 1.0
            continue
        if re.search(r"\.\s*$", l) or (len(l.split()) > 14 and not re.search(r"\((?:en |montants? )[^)]*\)", l, re.I)):
            continue   # phrase de texte (« … 130 millions de dirhams. ») : pas un en-tête de tableau
        if not l or re.search(r"(?:\d{1,3}(?: \d{3})+|\d,\d+|\d{4,})\s*\)?\s*$", l) and not re.search(r"(?:19|20)\d\d\s*$", l):
            continue
        for m in UNIT_RE.finditer(l):
            best = 1e3 if m.group(1) else 1e6 if m.group(2) else 1.0
    if re.search(r"\d{1,3}([ .])\d{3}\1\d{3},\d{2}\b", tail):
        best = 1.0   # montants à centimes : dirhams (un tableau en milliers n'affiche pas de centimes)
    return best


def flatten(text):
    text = re.sub(r"R([ÉE])SUL ?T ?A ?T", r"R\1SULTAT", text)           # « RÉSUL T A T » : lettres espacées dans la couche texte
    text = re.sub(r"(R[ée]sul)\s+(tat)", r"\1\2", text, flags=re.I)
    text = re.sub(r"(\d) ,(\d{2})(?!\d)", r"\1,\2", text)                # « 107 ,91 » : espace parasite avant les centimes
    t = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"[ \t\u00a0\u202f\u2009]+", " ", t)


PREFIX = r"(?:(?:[IVX]{1,5}|\d{1,2})\s*[.)=\[-]?\s*(?:=\s*)?|Dont\s*:?\s*|[•*:|]\s*|-\s+(?=[A-Za-zÀ-ÿ])|Net\s+|[A-Z]\s+)?"   # « T Total… », « E Chiffres… » : lettre du texte vertical en marge


_PAIR_RAW = re.compile(r"(?<![\w/.-])(\d{1,2}[/.]\d{1,2}[/.])?(20[0-4]\d)\s*\|?\s+(\d{1,2}[/.]\d{1,2}[/.])?(20[0-4]\d)(?![\w/.-])")


class _Pair:
    """Deux dates de clôture côte à côte : années seules, ou dates complètes de même jour / mois (« 31/12/2024 31/12/2025 »)."""
    @staticmethod
    def search(line):
        for m in _PAIR_RAW.finditer(line):
            d1, y1, d2, y2 = m.groups()
            if (d1 or "") == (d2 or "") and y1 != y2:
                return _Match(y1, y2)
        return None


class _Match:
    def __init__(self, a, b):
        self._g = (a, b)

    def group(self, i):
        return self._g[i - 1]


_PAIR = _Pair()
_DOC_ORDER = {}


_LONE_NUMBER = re.compile(r"^\s*[-+]?[\d\s]+(?:,\d+)?\s*%?\s*$")


def _chart_axis(lines, i):
    """Ligne « 2024 2025 » suivie d'une valeur seule : axe d'un graphique en barres, pas un en-tête de tableau."""
    nxt = next((l for l in lines[i + 1:i + 3] if l.strip()), "")
    return bool(_LONE_NUMBER.match(nxt))


def doc_year_order(flat):
    """Ordre des colonnes commun à tout le document : en-têtes à exactement deux années consécutives
    et en-têtes « Exercice / Exercice précédent » ; tous doivent concorder, sinon None."""
    k = hash(flat)
    if k not in _DOC_ORDER:
        orders = set()
        lines = flat.split("\n")
        for i, line in enumerate(lines):
            if re.search(r"exercice\s+(?:n\s+)?exercice\s+pr[ée]c[ée]dent", line, re.I):
                orders.add("desc")
            years = re.findall(r"(?<!\d)20[0-4]\d(?!\d)", line)
            m = _PAIR.search(line)
            if m and len(years) == 2 and abs(int(m.group(1)) - int(m.group(2))) == 1 and not _chart_axis(lines, i):
                orders.add("asc" if m.group(1) < m.group(2) else "desc")
        _DOC_ORDER[k] = orders.pop() if len(orders) == 1 else None
    return _DOC_ORDER[k]


def year_order_at(flat, pos):
    """Ordre des colonnes annoncé par l'en-tête le plus proche (« 2024 2025 » = N-1 puis N)."""
    head = flat[max(0, pos - 2500):pos].split("\n")
    for j in range(len(head) - 2, -1, -1):
        line = head[j]
        if _PAIR.search(line) and _chart_axis(head, j):
            continue
        if re.search(r"exercice\s+(?:n\s+)?exercice\s+pr[ée]c[ée]dent|exercice\s+n\s+exercice\s+n\s*-\s*1", line, re.I):
            return "desc"
        if re.search(r"\bdu\b.*\bau\b|p[ée]riode", line, re.I):   # « Du 1/4/2025 Au 31/3/2026 » : une période, pas deux colonnes
            continue
        pair = _PAIR.search(line)
        if pair and pair.group(1) != pair.group(2):   # deux dates de clôture côte à côte = en-tête des colonnes
            return "asc" if pair.group(1) < pair.group(2) else "desc"
    return None


def find(text, patterns, start=0, end=None, all_matches=False):
    flat = flatten(text)
    seg = flat[start:end]
    found = []
    for p in patterns:
        for m in re.finditer(r"^\s*" + PREFIX + p + SUFFIX + NOTE + TAIL, seg, re.M | re.I):
            two = parse_tail(m.group(1))
            if not two:
                continue
            rec = {"current": two[0], "previous": two[1], "layout": two[2], "ambiguous_split": two[3], "line": m.group(0).strip()[:220],
                   "unit": unit_at(flat, start + m.start(), m.group(1)), "pos": start + m.start()}
            if not rec["layout"].startswith(("N-1", "CPC", "N / N-1 /")) and (year_order_at(flat, start + m.start()) or doc_year_order(flat)) == "asc":
                rec.update(current=two[1], previous=two[0], layout=rec["layout"] + " — en-tête « N-1 puis N » : colonnes inversées")
            if not all_matches:
                return rec
            found.append(rec)
        if found:
            return found
    return found if all_matches else None


def detach_labels(text, model):
    """Texte OCR d'une page à deux colonnes : « …risques de pertes et PRODUIT NET BANCAIRE 20 338 747 18 716 574 ».
    Quand un libellé connu des états financiers suivi de ses montants apparaît au milieu d'une ligne, le texte qui le
    précède (autre colonne, logo) est renvoyé sur une ligne à part. Les montants ne sont pas modifiés."""
    pats = [p for ps in LABELS[model].values() for p in ps] + [RNPG]
    rx = [re.compile(r"(?<![\w'])" + p + SUFFIX + NOTE + TAIL, re.I) for p in pats]
    out, moved = [], 0
    for line in text.split("\n"):
        # libellé de tableau commençant par une majuscule (« PRODUIT NET… », « Coût du risque ») : un fragment en minuscules
        # (« …dépréciations sur prêts et créances… ») est la fin d'un autre libellé et n'est pas détaché
        starts = [m.start() for r in rx for m in [r.search(line)] if m and m.start() > 0 and line[:m.start()].strip() and line[m.start()].isupper()]
        if starts and not any(r.match(line.lstrip()) for r in rx):
            k = min(starts)
            out += [line[:k].rstrip(), line[k:]]
            moved += 1
        else:
            out.append(line)
    return "\n".join(out), moved


def minorities_near(text, equity):
    """Intérêts minoritaires au bilan, lus autour de la ligne « Capitaux propres » : ligne unique
    « Intérêts minoritaires » ou somme des lignes « … Part des minoritaires »."""
    if not equity:
        return None
    lo, hi = max(0, equity["pos"] - 1500), equity["pos"] + 1500
    single = find(text, [r"Intérêts minoritaires(?! \(ou)", r"(?:Participations|Intérêts) ne donnant pas le contr[ôo]le", r"Parts minoritaires"], lo, hi)
    if single and single["current"] > 0:
        return {**single, "method": "ligne « Intérêts minoritaires » du bilan"}
    parts = find(text, [r"[^\n]{0,80}?Part des minoritaires"], lo, hi, all_matches=True)
    if parts:
        return {"current": sum(x["current"] for x in parts), "previous": sum(x["previous"] for x in parts),
                "unit": parts[0]["unit"], "line": " + ".join(x["line"][-70:] for x in parts)[:500],
                "method": f"somme de {len(parts)} lignes « Part des minoritaires » du bilan",
                "ambiguous_split": any(x["ambiguous_split"] for x in parts)}
    seg = flatten(text)[lo:hi]
    nil = re.findall(r"^\s*Part des minoritaires\s+-\s+-\s*$", seg, re.M)
    if len(nil) >= 2 and not re.search(r"^\s*Part des minoritaires\s+-?\d", seg, re.M):
        return {"current": 0.0, "previous": 0.0, "unit": equity.get("unit"), "line": f"{len(nil)} lignes « Part des minoritaires - - »",
                "method": "intérêts minoritaires à néant (lignes « Part des minoritaires » sans montant)", "ambiguous_split": False}
    return None


def _to_mad(f, key):
    if key in PER_SHARE:
        f["mad"], f["mad_previous"] = f["current"], f["previous"]
    elif f["unit"]:
        f["mad"], f["mad_previous"] = f["current"] * f["unit"], (None if f["previous"] is None else f["previous"] * f["unit"])
    else:
        f["mad"] = f["mad_previous"] = None
    return f


SOCIAL_SIGNATURE = re.compile(r"^\s*(?:[IVX]{1,5}\b\s*(?:=\s*)?[A-ZÉ]|T ?otal des capitaux propres\s*\(A\))")


def _social_like(c):
    """Ligne typique des états de synthèse sociaux (modèle CGNC : numérotation romaine, colonnes CPC, centimes)."""
    return bool(SOCIAL_SIGNATURE.search(c["line"]) or c.get("layout", "").startswith(("CPC", "N / total N"))
                or re.search(r"\d{3},\d{2}\b", c["line"]))


def _nearest(cands, anchor, anchor_rec=None):
    """Parmi les lignes candidates : unité connue, pas de signature de comptes sociaux (sauf si l'ancre en a une),
    puis la plus proche de l'ancre (même tableau)."""
    if not cands:
        return None
    social_anchor = bool(anchor_rec and _social_like(anchor_rec))
    cands = [c for c in cands if _social_like(c) == social_anchor]   # jamais de mélange sociaux / consolidés
    if not cands:
        return None
    return min(cands, key=lambda c: (c["unit"] is None, _social_like(c) != social_anchor, abs(c["pos"] - anchor)))


MINOR = r"minoritaires|ne donnant pas le contr[ôo]le|hors groupe"


def group_share_from_split(text):
    """Résultat part du groupe sans libellé explicite : ligne X proche d'un « résultat (net) consolidé » R,
    accompagnée d'une ligne intérêts minoritaires M, avec X + M = R pour N et N-1 (contrôle arithmétique)."""
    out = []
    for c in find(text, [CONSOLIDATED_RN], all_matches=True):
        near = [x for x in find(text, [r"[^\n\d]{3,100}?"], max(0, c["pos"] - 400), c["pos"] + 600, all_matches=True)
                if x["pos"] != c["pos"]]
        minors = [x for x in near if re.search(MINOR, x["line"], re.I)]
        for x in near:
            if re.search(MINOR + r"|consolid|capitaux|total", x["line"], re.I):
                continue
            for m in minors:
                if _close(x["current"] + m["current"], c["current"], 0, 2.5) and _close(x["previous"] + m["previous"], c["previous"], 0, 2.5):
                    x = dict(x, unit=x["unit"] or c["unit"],
                             method=f"part du groupe = « {c['line'][:60]} » − « {m['line'][:60]} » (somme vérifiée N et N-1)")
                    out.append(x)
                    break
        if out:
            return out
    return out


MAX_PL_DISTANCE = 10000   # au-delà, la ligne appartient à un autre document / tableau que le résultat retenu


def _select_consolidated(text, labels, model, rn):
    out = {"net_income_group": dict(rn) if rn else None}
    pl_anchor = rn["pos"] if rn else 0
    bs_anchor = None
    for key, pats in labels.items():
        if key in ("net_income_group", "minority_interests"):
            continue
        if key == "equity_total" and out.get("equity_group"):
            bs_anchor = out["equity_group"]["pos"]
        anchor = bs_anchor if key in BALANCE and bs_anchor is not None else pl_anchor
        out[key] = None
        for p in pats:   # ordre de priorité des libellés, puis tableau le plus proche
            cands = find(text, [p], all_matches=True)
            if rn and key not in BALANCE:
                cands = [c for c in cands if abs(c["pos"] - pl_anchor) <= MAX_PL_DISTANCE]
            if rn and rn.get("unit") and key in ("equity_total", "equity_group", "total_assets"):
                # fonds propres ou total bilan très inférieurs au résultat de l'exercice : ligne d'un autre tableau
                # (seuil : 25 % du résultat, soit un ROE de 400 % ; une société qui distribue tout peut avoir des fonds propres < résultat)
                cands = [c for c in cands if not c.get("unit") or c["current"] < 0 or c["current"] * c["unit"] >= 0.25 * abs(rn["current"] * rn["unit"])]   # négatif : situation nette négative, signalée ensuite
            out[key] = _nearest(cands, anchor, rn) if key not in PER_SHARE else (min(cands, key=lambda c: abs(c["pos"] - anchor)) if cands else None)
            if out[key]:
                out[key] = dict(out[key])
                break
        if key == "equity_group" and out[key]:
            bs_anchor = out[key]["pos"]
    out["minority_interests"] = minorities_near(text, out.get("equity_total")) if model == "bank" or not out.get("equity_group") else None
    if model == "bank" and not out.get("cost_of_risk"):   # états consolidés au format PCEC : pas de ligne « Coût du risque »
        out["cost_of_risk"] = social_cost_of_risk(text, pl_anchor)
    if model == "bank" and not out.get("customer_loans") and out["cost_of_risk"] and "PCEC" in out["cost_of_risk"].get("method", ""):
        out["customer_loans"] = social_loans(text, pl_anchor)
    return out


def _last_three_with_identity(toks):
    """Trois derniers montants (a, b, c) de la ligne avec a + b = c. Les montants peuvent être d'un seul jeton
    (« 2.065.577 ») ou en groupes séparés par des espaces (« 1 485 722 717 1 486 439 ») : toutes les découpes des
    derniers jetons sont essayées, et la ligne n'est retenue que si une seule vérifie l'identité."""
    sols = set()
    tail = []
    for t in reversed(toks[-12:]):   # suite finale de jetons numériques seulement
        if not re.fullmatch(r"-?\(?\d[\d,]*\)?", t):
            break
        tail.insert(0, t)
    n = len(tail)
    for i in range(n - 2):
        for j in range(i + 1, n - 1):
            for k in range(j + 1, n):
                a, b, c = _number(tail[i:j]), _number(tail[j:k]), _number(tail[k:])
                if None in (a, b, c):
                    continue
                if _close(a + b, c, 0, 2.5) and c != 0:
                    sols.add((a, b, c))                       # part du groupe, minoritaires, total
                elif _close(b + c, a, 0, 2.5) and a != 0 and abs(c) >= abs(b):
                    sols.add((c, b, a))                       # total, minoritaires, part du groupe (Label'Vie)
    return list(sols)[0] if len(sols) == 1 else None


def equity_from_variation(text):
    """Capitaux propres part du groupe lus dans le tableau de variation des capitaux propres
    (lignes « Capitaux propres au 31 décembre AAAA … part du groupe, minoritaires, total ») :
    retenus seulement si part du groupe + minoritaires = total, pour l'exercice et le précédent."""
    flat = flatten(text)
    rows = {}
    # « Capitaux propres (clôture) au 31 décembre AAAA … part du groupe  minoritaires  total » (coquille « propores » tolérée)
    for m in re.finditer(r"^\s*(?:Capitaux propo?res (?:cl[ôo]ture )?au 31 d[ée]cembre|Situation au 31 d[ée]cembre|SITUATION A LA CL[ÔO]TURE DE L'EXERCICE) (20\d\d)(?! corrig)\s+(.*?)\s*$", flat, re.M | re.I):
        toks = normalize_tail(m.group(2)).split()
        trio = _last_three_with_identity(toks)
        if trio:
            rows[int(m.group(1))] = (trio, m.group(0).strip(), m.start())
    if not rows:
        return None
    y = max(rows)
    if y - 1 not in rows:
        return None
    (g, mi, tot), line, pos = rows[y]
    (g0, mi0, tot0), _, _ = rows[y - 1]
    unit = unit_at(flat, pos, line)
    base = {"unit": unit, "layout": "tableau de variation : part du groupe + minoritaires = total (vérifié)",
            "ambiguous_split": False, "line": line[:220], "pos": pos}
    names = {"equity_group": "part du groupe", "minority_interests": "intérêts minoritaires", "equity_total": "total"}
    vals = {"equity_group": (g, g0), "minority_interests": (mi, mi0), "equity_total": (tot, tot0)}
    return {k: {**base, "current": c, "previous": p,
                "method": f"capitaux propres ({names[k]}) au 31/12/{y} et {y - 1} lus dans le tableau de variation des capitaux propres"}
            for k, (c, p) in vals.items()}


SOCIAL_BANK_EQUITY = [   # passif PCEC (établissements de crédit) : postes de capitaux propres, avec leur signe
    ("reserves", r"R[ée]serves et primes li[ée]es au capital", 1, True),
    ("capital", r"Capital(?!\s*(?:non|appel))", 1, True),
    ("unpaid", r"Actionnaires\s*\.?\s*Capital non vers[ée]\s*\(-\)", -1, False),
    ("retained", r"Report [àa] nouveau\s*\(\+/-\)", 1, False),
    ("pending", r"R[ée]sultats? nets? en instance d'affectation\s*\(\+/-\)", 1, False),
    ("result", r"R[ée]sultat net de l'exercice\s*\(\+/-\)", 1, True),
]


def social_bank_equity(text, net_income):
    """Comptes sociaux d'un établissement de crédit (PCEC) : le passif n'a pas de ligne « total des capitaux propres ».
    Capitaux propres = réserves et primes + capital − capital non versé + report à nouveau + résultats en instance
    d'affectation + résultat de l'exercice, lus dans le bloc qui se termine par « Total du passif ».
    Retenus seulement si le résultat du passif est égal au résultat net du compte de produits et charges (N et N-1)."""
    if not net_income:
        return None
    flat = flatten(text)
    for m in re.finditer(r"^\s*Total du passif", flat, re.M | re.I):
        lo, hi = max(0, m.start() - 4000), m.start()
        parts, ok = {}, True
        for key, pat, sign, required in SOCIAL_BANK_EQUITY:
            f = find(text, [pat], lo, hi, all_matches=True)
            f = f[-1] if f else None   # ligne la plus proche du total
            if not f:
                seg = flat[lo:hi]
                if re.search(r"^\s*(?:\d{1,2}\s*\.\s*)?" + pat + r"[^\n\d]*$", seg, re.M | re.I):
                    f = {"current": 0.0, "previous": 0.0, "unit": None}   # poste présent, sans montant
                elif required:
                    ok = False
                    break
                else:
                    continue
            parts[key] = (f, sign)
        if not ok:
            continue
        res = parts["result"][0]
        if not (_close(res["current"], net_income["current"], 0, 1) and _close(res["previous"], net_income["previous"], 0, 1)):
            continue
        cur = sum(sign * abs(f["current"]) if key == "unpaid" else sign * f["current"] for key, (f, sign) in parts.items())
        prev = sum(sign * abs(f["previous"]) if key == "unpaid" else sign * f["previous"] for key, (f, sign) in parts.items())
        return {"current": cur, "previous": prev, "unit": parts["capital"][0]["unit"] or res["unit"], "layout": "N / N-1",
                "ambiguous_split": False, "pos": m.start(), "line": " + ".join(f"{k} {f['current']:.0f}" for k, (f, _) in parts.items()),
                "method": "comptes sociaux PCEC : capital + réserves et primes + report à nouveau + résultats en instance + résultat de l'exercice − capital non versé (résultat du passif = résultat du CPC)"}
    return None


def social_cost_of_risk(text, anchor=None):
    """PCEC (comptes sociaux ou consolidés) : coût du risque = dotations aux provisions et pertes sur créances
    irrécouvrables − reprises de provisions et récupérations sur créances amorties (charge nette, en négatif).
    Avec une ancre (résultat consolidé), les lignes du compte de résultat le plus proche sont retenues."""
    dots = find(text, [r"DOTATIONS AUX PROVISIONS ET PERTES SUR CR[ÉE]ANCES(?:\s+IRR[ÉE]COUVRABLES)?"], all_matches=True)
    reps = find(text, [r"REPRISES DE PROVISIONS ET R[ÉE]CUP[ÉE]RATIONS SUR(?:\s+CR[ÉE]ANCES AMORTIES)?"], all_matches=True)
    if not dots or not reps:
        return None
    pick = (lambda xs: min(xs, key=lambda x: abs(x["pos"] - anchor))) if anchor is not None else (lambda xs: xs[0])
    dot = pick(dots)
    rep = min(reps, key=lambda x: abs(x["pos"] - dot["pos"]))
    if abs(rep["pos"] - dot["pos"]) > 2000:
        return None
    return {"current": -(dot["current"] - rep["current"]), "previous": -(dot["previous"] - rep["previous"]),
            "unit": dot["unit"] or rep["unit"], "layout": dot["layout"], "ambiguous_split": dot["ambiguous_split"] or rep["ambiguous_split"],
            "pos": dot["pos"], "line": (dot["line"] + " − " + rep["line"])[:440],
            "method": "format PCEC : dotations aux provisions et pertes sur créances − reprises et récupérations"}


def social_loans(text, anchor=None):
    """PCEC : encours financés = créances sur la clientèle + immobilisations données en crédit-bail et en location
    (sociétés de crédit-bail : l'essentiel du risque de crédit est porté par ces immobilisations), lus dans le bloc
    qui se termine par « Total de l'actif »."""
    flat = flatten(text)
    totals = list(re.finditer(r"^\s*TOTAL DE L\s?'\s?ACTIF", flat, re.M | re.I))
    if anchor is not None:   # états consolidés : le bilan le plus proche du compte de résultat retenu
        totals.sort(key=lambda m: abs(m.start() - anchor))
    for m in totals:
        lo, hi = max(0, m.start() - 4000), m.start()
        cl = find(text, [r"Cr[ée]ances sur la client[èe]le"], lo, hi, all_matches=True)
        cb = find(text, [r"Immobilisations donn[ée]es en cr[ée]dit-bail et en location", r"Op[ée]rations de cr[ée]dit-bail et de location"], lo, hi, all_matches=True)
        if not cl:
            continue
        cl, cb = cl[-1], (cb[-1] if cb else None)
        parts = [x for x in (cl, cb) if x]
        return {"current": sum(x["current"] for x in parts), "previous": sum(x["previous"] for x in parts),
                "unit": cl["unit"], "layout": cl["layout"], "ambiguous_split": any(x["ambiguous_split"] for x in parts),
                "pos": cl["pos"], "line": " + ".join(x["line"] for x in parts)[:440],
                "method": "format PCEC : créances sur la clientèle" + (" + crédit-bail et location" if cb else "")}
    return None


def social_equity_from_split_passif(text, net_income):
    """Passif CGNC extrait en deux blocs (montants d'un côté, libellés de l'autre, Cartier Saada) :
    dans le bloc « BILAN - PASSIF », la paire (N, N-1) P suivie de lignes dont la somme vaut P et dont la dernière
    est égale au résultat net du CPC, pour N ET N-1, est le total des capitaux propres (capital … résultat).
    Exige aussi le libellé « Total des capitaux propres » dans la même page."""
    if not net_income or net_income.get("previous") is None:
        return None
    flat = flatten(text)
    for m in re.finditer(r"BILAN\s*-?\s*PASSIF", flat, re.I):
        seg = flat[m.start(): m.start() + 6000]
        if not re.search(r"TOTAL DES CAPITAUX PROPRES", seg, re.I):
            continue
        pairs = []
        for line in seg.split("\n")[1:80]:
            mm = re.fullmatch(r"\s*(-?\d{1,3}(?: \d{3})*,\d{2})\s+(-?\d{1,3}(?: \d{3})*,\d{2})\s*", line)
            pairs.append(tuple(float(g.replace(" ", "").replace(",", ".")) for g in mm.groups()) if mm else None)
        for i, p in enumerate(pairs):
            if not p or p[0] <= 0:
                continue
            acc = [0.0, 0.0]
            for q in pairs[i + 1:]:
                if q is None:
                    break
                acc[0] += q[0]; acc[1] += q[1]
                if (abs(q[0] - net_income["current"]) <= 0.011 and abs(q[1] - net_income["previous"]) <= 0.011
                        and abs(acc[0] - p[0]) <= 0.02 and abs(acc[1] - p[1]) <= 0.02):
                    return {"current": p[0], "previous": p[1], "unit": 1.0, "layout": "N / N-1", "ambiguous_split": False,
                            "pos": m.start(), "line": f"{p[0]:,.2f} {p[1]:,.2f}".replace(",", " "),
                            "method": "passif CGNC extrait sans libellés : total = somme des postes de capitaux propres jusqu'au résultat de l'exercice (égal au résultat du CPC), N et N-1"}
    return None


def extract(text, model):
    """Comptes consolidés si le document contient une ligne « résultat net part du groupe » chiffrée ;
    sinon comptes sociaux (champ scope). Chaque grandeur est prise dans le tableau le plus proche de
    l'ancre (résultat part du groupe pour le compte de résultat, capitaux propres part du groupe pour le bilan),
    pour ne pas mélanger comptes sociaux et consolidés."""
    rn_all = find(text, [RNPG], all_matches=True)
    if not rn_all:
        rn_all = group_share_from_split(text)
    rn_all = [x for x in rn_all if x["unit"]] or rn_all
    flat = flatten(text)
    # ligne chiffrée mentionnant le consolidé / la part du groupe (un en-tête « … CONSOLIDE 31/12/2025 31/12/2024 » ne compte pas)
    has_consolidated = any(not re.search(r"(?:19|20)\d\d\s*\)?[ \t]*$", m.group(0))
                           for m in re.finditer(r"^[^\n]*(?:consolid|part du groupe)[^\n]*\d{3}[ \t]*\)?[ \t]*$", flat, re.I | re.M))
    if not rn_all and has_consolidated:   # ligne « (dont) part du groupe » isolée : retenue seulement si le BPA publié la confirme (contrôlé dans checks)
        alts = [x for x in find(text, [r"(?:Dont\s*:?\s*)?(?:R[ée]sultat\s+(?:net\s+)?)?part (?:du )?groupe",
                                 r"R[ée]sultat (?:net )?de l'exercice", r"R[ée]sultat net des activités maintenues"], all_matches=True)
                if not re.search(r"capitaux|ffo|réserves", x["line"], re.I) and x["current"]]
        if alts:
            d = dict(alts[0], needs_eps_check=True, alternatives=alts,
                     method="résultat sans mention « part du groupe » : retenu car confirmé par le BPA publié × nombre de titres (écart ≤ 3 %)")
            rn_all = [d]
    out = {}
    if rn_all or has_consolidated:
        scope, labels = "consolidated", LABELS[model]
        best = None
        for rn in (rn_all or [None])[:6]:   # ancre retenue : celle dont les autres postes sont les plus proches
            cand = _select_consolidated(text, labels, model, rn)
            found = [k for k in ("revenue", "pnb", "equity_group", "equity_total") if cand.get(k)]
            dist = sum(abs(cand[k]["pos"] - (rn["pos"] if rn else 0)) for k in found)
            key = (-len(found), rn is None or rn["unit"] is None, dist)
            if best is None or key < best[0]:
                best = (key, cand)
        out = best[1]
    else:
        scope, labels = "social", SOCIAL[model]
        for key, pats in labels.items():
            out[key] = find(text, pats)
        if model == "bank":
            if not out.get("equity_total"):
                out["equity_total"] = social_bank_equity(text, out.get("net_income_group"))
            if not out.get("cost_of_risk"):
                out["cost_of_risk"] = social_cost_of_risk(text)
            out["customer_loans"] = social_loans(text)
        if model == "corporate" and not out.get("equity_total"):
            out["equity_total"] = social_equity_from_split_passif(text, out.get("net_income_group"))
        if model == "corporate" and not out.get("revenue"):
            parts = [x for x in (find(text, [r"Ventes de marchandises(?: \(en l'état\))?"]), find(text, [r"Ventes de biens et services produits"])) if x]
            if parts and all(x["current"] == x["previous"] for x in parts):
                parts = []   # lignes « propres à l'exercice / total N » sans N-1 : N-1 inconnu, non recopié
            if not parts:   # « Chiffre(s) d'affaires X 0,00 X » : propres à l'exercice + précédents = total N ; N-1 absent de la ligne
                flat = flatten(text)
                for m in re.finditer(r"^\s*" + PREFIX + r"Chiffres? d'affaires\s+(\d[\d .]*,\d{2})\s+0,00\s+(\d[\d .]*,\d{2})\s*[A-Z]?\s*$", flat, re.M | re.I):
                    a, c = (float(normalize_tail(g).replace(" ", "").replace(",", ".")) for g in m.groups())
                    if a == c and a > 0:
                        out["revenue"] = {"current": c, "previous": None, "unit": unit_at(flat, m.start(), m.group(2)), "layout": "CPC : propres à l'exercice + précédents = total N (N-1 non publié sur la ligne)",
                                          "ambiguous_split": False, "line": m.group(0).strip()[:220], "pos": m.start(),
                                          "method": "chiffre d'affaires de l'exercice seul : N-1 absent de la ligne, croissance non calculée"}
                        break
            if parts:
                out["revenue"] = {"current": sum(x["current"] for x in parts), "previous": sum(x["previous"] for x in parts),
                                  "unit": parts[0]["unit"], "layout": parts[0]["layout"], "ambiguous_split": any(x["ambiguous_split"] for x in parts),
                                  "line": " + ".join(x["line"] for x in parts)[:440], "pos": parts[0]["pos"],
                                  "method": "chiffre d'affaires = ventes de marchandises + ventes de biens et services produits (CPC)"}
    if scope == "consolidated" and not out.get("equity_group"):
        ev = equity_from_variation(text)
        if ev:
            out["equity_group"] = ev["equity_group"]
            for k in ("equity_total", "minority_interests"):   # complétés seulement s'ils manquent, depuis le même tableau
                if not out.get(k):
                    out[k] = ev[k]
    for key in list(LABELS[model]):
        out.setdefault(key, None)
    for key, f in out.items():
        if f:
            f.pop("pos", None)
            _to_mad(f, key)
    out["_scope"] = scope
    return out


def v(x, k="mad"):
    return x.get(k) if x else None


UNITS = (1.0, 1e3, 1e6)


def _set_unit(f, u, why, notes, key):
    f["unit"], f["unit_method"] = u, why
    f["mad"], f["mad_previous"] = f["current"] * u, (None if f["previous"] is None else f["previous"] * u)
    notes.append(f"{key} : unité non indiquée dans le document, déduite ({why}) : {({1.0: 'MAD', 1e3: 'milliers', 1e6: 'millions'})[u]}")


def infer_units(fin, model, shares_now, price, notes):
    """Unités absentes des en-têtes : déduites par cohérence, uniquement si une seule unité est plausible.
    1) résultat / capitaux propres : ROE entre −60 % et +100 % (un facteur 1 000 exclut toute autre unité) ;
    2) à défaut, capitalisation : PER entre 2 et 300 ET P/B entre 0,1 et 40 avec la même unité ;
    3) autres postes : rapport plausible au résultat ou aux capitaux propres."""
    rn = fin.get("net_income_group")
    eq_key = "equity_group" if fin.get("equity_group") else "equity_total"
    eq = fin.get(eq_key)
    ok = lambda us: us[0] if len(us) == 1 else None
    if rn and eq and (rn["unit"] is None) != (eq["unit"] is None) and rn["current"] and eq["current"] > 0:
        known, unk = (eq, rn) if rn["unit"] is None else (rn, eq)
        roe = lambda u: (rn["current"] * (u if unk is rn else rn["unit"])) / (eq["current"] * (u if unk is eq else eq["unit"]))
        us = [u for u in UNITS if 0.002 <= abs(roe(u)) <= 1.0 and roe(u) >= -0.6]
        if ok(us):
            _set_unit(unk, ok(us), "rentabilité des capitaux propres plausible", notes, "net_income_group" if unk is rn else eq_key)
    if rn and eq and rn["unit"] is None and eq["unit"] is None and price and shares_now and rn["current"] > 0 and eq["current"] > 0:
        mcap = price * shares_now
        us = [u for u in UNITS if 2 <= mcap / (rn["current"] * u) <= 300 and 0.1 <= mcap / (eq["current"] * u) <= 40]
        if ok(us):
            _set_unit(rn, ok(us), "capitalisation boursière : PER et P/B plausibles", notes, "net_income_group")
            _set_unit(eq, ok(us), "capitalisation boursière : PER et P/B plausibles", notes, eq_key)
    rn_mad = v(rn)
    eq_mad = v(eq)
    rules = {"revenue": (rn_mad, 1.0, 700), "pnb": (rn_mad, 1.0, 700), "net_income": (rn_mad, 0.8, 1.7),
             "equity_total": (eq_mad, 1.0, 1.7), "equity_group": (v(fin.get("equity_total")), 0.5, 1.0), "total_assets": (eq_mad, 1.0, 40),
             "minority_interests": (v(fin.get("equity_total")), 0.0001, 0.6)}
    for k, (ref, lo, hi) in rules.items():
        f = fin.get(k)
        if f and f.get("unit") is None and ref and f["current"]:
            us = [u for u in UNITS if lo <= abs(f["current"] * u / ref) <= hi]
            if ok(us):
                _set_unit(f, ok(us), "rapport plausible au résultat ou aux capitaux propres", notes, k)
    pnb = v(fin.get("pnb"))   # après le PNB, éventuellement déduit ci-dessus ; fourchettes de largeur < 1 000 : une seule unité possible
    for k, lo, hi in (("operating_expenses", 0.05, 1.5), ("cost_of_risk", 0.005, 1.5)):
        f = fin.get(k)
        if f and f.get("unit") is None and pnb and f["current"]:
            us = [u for u in UNITS if lo <= abs(f["current"] * u / pnb) <= hi]
            if ok(us):
                _set_unit(f, ok(us), "rapport plausible au produit net bancaire", notes, k)
    f, ta = fin.get("customer_loans"), v(fin.get("total_assets"))   # après le total bilan, éventuellement déduit ci-dessus
    if f and f.get("unit") is None and ta and f["current"] > 0:
        us = [u for u in UNITS if 0.1 <= f["current"] * u / ta <= 1.0]
        if ok(us):
            _set_unit(f, ok(us), "rapport plausible au total bilan (10-100 %)", notes, "customer_loans")


def _capital_increase_explains(fin, eps, shares_now, implied, rn):
    """Augmentation de capital dans l'exercice (SGTM 2025 : capital 300 → 1 200 MMAD) : nombre de titres N-1
    = titres actuels × capital N-1 / capital N. Accepté seulement si le BPA publié N se situe entre les titres N-1
    et N (nombre moyen pondéré) ET si le BPA publié N-1 correspond au résultat N-1 / titres N-1 (à 3 %)."""
    cap, e = fin.get("share_capital"), fin.get("eps")
    rn_prev = v(fin.get("net_income_group"), "mad_previous")
    if not (cap and e and cap["current"] > cap["previous"] > 0 and e.get("previous") and rn_prev):
        return False
    shares_prev = shares_now * cap["previous"] / cap["current"]
    return (shares_prev * 0.97 <= implied <= shares_now * 1.03
            and abs(rn_prev / shares_prev / e["previous"] - 1) <= 0.03)


def checks(fin, model, shares_now, price=None):
    """Contrôles croisés ; renvoie (indicateurs dérivés, anomalies bloquantes, notes)."""
    errors, notes, d = [], [], {}
    infer_units(fin, model, shares_now, price, notes)
    scope = fin.get("_scope", "consolidated")
    d["scope"] = scope
    for k, x in fin.items():
        if k.startswith("_"):
            continue
        if x and x.get("ambiguous_split"):
            notes.append(f"{k} : découpage des montants ambigu, valeur retenue selon la cohérence N / N-1")
    g = fin.get("net_income_group")
    if g and g.get("needs_eps_check") and fin.get("eps") and shares_now:
        e = fin["eps"]["current"]
        fits = [a for a in g.get("alternatives", []) if e and a["current"] and abs(a["current"] * (a["unit"] or 0) / e / shares_now - 1) <= 0.03]
        if fits:
            keep = {k: g[k] for k in ("needs_eps_check", "method")}
            g.clear(); g.update(fits[0], **keep); g.pop("alternatives", None)
            g["mad"], g["mad_previous"] = g["current"] * g["unit"], g["previous"] * g["unit"]
    if g:
        g.pop("alternatives", None)
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
                elif 1.03 < ratio <= 1.35 and not (fin.get("net_income_group") or {}).get("needs_eps_check"):
                    # plus de titres aujourd'hui que dans le BPA publié : augmentation de capital probable,
                    # le BPA publié étant calculé sur le nombre moyen pondéré de l'exercice
                    notes.append(f"BPA publié calculé sur {round(implied):,} titres, {shares_now:,} titres aujourd'hui (rapport {ratio:.2f}) : "
                                 f"augmentation de capital probable ; BPA recalculé sur le nombre actuel de titres".replace(",", " "))
                elif _capital_increase_explains(fin, eps, shares_now, implied, rn):
                    cap = fin["share_capital"]
                    notes.append(f"BPA publié calculé sur {round(implied):,} titres (nombre moyen) ; {shares_now:,} titres aujourd'hui : capital porté de ".replace(",", " ") +
                                 f"{cap['previous']:,.0f} à {cap['current']:,.0f} dans l'exercice (bilan publié) ; BPA N-1 cohérent avec le capital N-1".replace(",", " "))
                else:
                    errors.append(f"BPA publié incohérent avec résultat / nombre de titres (rapport {ratio:.2f})")
    if fin.get("net_income_group") and fin["net_income_group"].get("needs_eps_check"):
        if not (rn and eps and shares_now and not any("BPA publié incohérent" in e for e in errors)):
            errors.append("part du groupe lue sous un résultat consolidé, non confirmée par un BPA publié cohérent")
    if shares_now and rn:
        d["eps_current_shares_mad"] = rn / shares_now
    eq_total, minor = v(fin.get("equity_total")), v(fin.get("minority_interests"))
    eq_group = v(fin.get("equity_group"))
    prev_group = v(fin.get("equity_group"), "mad_previous")
    if scope == "social" and eq_group is None and eq_total is not None:
        eq_group, prev_group = eq_total, v(fin.get("equity_total"), "mad_previous")
        d["equity_group_method"] = "comptes sociaux : total des capitaux propres (pas d'intérêts minoritaires)"
    if eq_group is None and eq_total is not None and minor is not None:
        eq_group = eq_total - minor
        pt, pm = v(fin.get("equity_total"), "mad_previous"), v(fin.get("minority_interests"), "mad_previous")
        prev_group = pt - pm if pt is not None and pm is not None else None
        d["equity_group_method"] = "capitaux propres totaux − intérêts minoritaires (" + fin["minority_interests"].get("method", "") + ")"
    nf, gf = fin.get("net_income"), fin.get("net_income_group")
    if (eq_group is None and eq_total is not None and minor is None and scope != "social" and nf and gf
            and nf.get("previous") is not None and gf.get("previous") is not None
            and _close(nf["current"], gf["current"], 0, 0.5) and _close(nf["previous"], gf["previous"], 0, 0.5)):
        # aucun intérêt minoritaire : résultat net consolidé = part du groupe en N et N-1 (Maghreb Oxygène)
        eq_group, prev_group = eq_total, v(fin.get("equity_total"), "mad_previous")
        d["equity_group_method"] = "capitaux propres totaux : pas d'intérêts minoritaires (résultat net consolidé = part du groupe, N et N-1)"
    if eq_group is None:
        errors.append("capitaux propres part du groupe introuvables")
    elif eq_group <= 0:
        errors.append(f"situation nette négative : capitaux propres part du groupe de {eq_group / 1e6:,.1f} M MAD au bilan publié ; ROE et P/B non calculables".replace(",", " ").replace(".", ","))
    elif eq_total and eq_total > 0 and eq_group > eq_total * 1.001:
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
        loans, assets = v(fin.get("customer_loans")), v(fin.get("total_assets"))
        if loans is not None and (loans <= 0 or (assets and not 0.1 <= loans / assets <= 1.0)):
            notes.append(f"encours de crédits à la clientèle écarté ({loans / 1e6:,.0f} M MAD) : ".replace(",", " ") +
                         "négatif ou hors de 10-100 % du total bilan, ligne d'un autre tableau")
            loans = None
        if loans and cor is not None:
            d["cost_of_risk_to_loans_pct"] = 100 * abs(cor) / loans
        pp = v(fin.get("pnb"), "mad_previous")
        if pnb and pp:
            d["pnb_growth_pct"] = 100 * (pnb / pp - 1)
        if pnb is None:
            errors.append("PNB introuvable")
    elif model == "insurance":
        rev, ch = v(fin.get("revenue")), v(fin.get("insurance_expenses"))
        if rev and ch is not None:
            d["insurance_expense_ratio_pct"] = 100 * abs(ch) / rev   # charges / produits des activités d'assurance (brut de réassurance)
        if rev and rn is not None:
            d["net_margin_pct"] = 100 * rn / rev
        rp = v(fin.get("revenue"), "mad_previous")
        if rev and rp:
            d["revenue_growth_pct"] = 100 * (rev / rp - 1)
        ta = v(fin.get("total_assets"))
        if ta and (eq_group or eq_total) and 0 < (eq_total or eq_group) / ta <= 1:
            d["equity_ratio_pct"] = 100 * (eq_total or eq_group) / ta
        if rev is None:
            errors.append("produits des activités d'assurance / primes introuvables")
    else:
        rev, op = v(fin.get("revenue")), v(fin.get("operating_income"))
        opp = v(fin.get("operating_income"), "mad_previous")
        if op and opp and not 0.01 <= abs(op / opp) <= 100:   # colonnes du CPC dispersées (« -47 077 » contre « 106 205 594 »)
            notes.append(f"résultat d'exploitation écarté : N et N-1 d'ordres de grandeur incompatibles ({op:,.0f} / {opp:,.0f} MAD), colonnes mal alignées dans le document".replace(",", " "))
            op = None
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
        if ta and (eq_total or eq_group):
            r = 100 * (eq_total or eq_group) / ta   # autonomie financière : capitaux propres totaux / total bilan
            if 0 < r <= 100:
                d["equity_ratio_pct"] = r
            else:
                notes.append(f"total bilan incohérent avec les capitaux propres (rapport {r:.0f} %) : autonomie financière non calculée")
        if rev is None:
            errors.append("chiffre d'affaires introuvable")
    rp = v(fin.get("net_income_group"), "mad_previous")
    if rn and rp and rp > 0:
        d["net_income_growth_pct"] = 100 * (rn / rp - 1)
    # Plausibilité de marché : détecte une erreur d'unité (milliers / millions / dirhams) ou de périmètre.
    if price and shares_now:
        mcap = price * shares_now
        d["market_cap_mad"] = mcap
        if rn and rn > 0:
            per = mcap / rn
            d["implied_per"] = per
            rnf, eqf = fin.get("net_income_group") or {}, fin.get("equity_group") or fin.get("equity_total") or {}
            same_published_unit = rnf.get("unit") and rnf.get("unit") == eqf.get("unit") and "unit_method" not in rnf and "unit_method" not in eqf
            if per > 300 and same_published_unit and eq_group and 0.1 <= mcap / eq_group <= 40:
                notes.append(f"PER {per:.0f} non significatif : résultat quasi nul (ROE {100 * rn / eq_group:.2f} %)".replace(".", ",") + ", unités publiées identiques pour le résultat et les capitaux propres")
            elif not 2 <= per <= 300:
                errors.append(f"PER implicite {per:.3g} hors bornes [2 ; 300] : unité ou périmètre suspect")
        if eq_group and eq_group > 0:
            pb = mcap / eq_group
            d["implied_pb"] = pb
            if not 0.1 <= pb <= 40:
                errors.append(f"P/B implicite {pb:.3g} hors bornes [0,1 ; 40] : unité ou périmètre suspect")
    if model == "corporate":
        rev = v(fin.get("revenue"))
        if rev and rn and abs(rn) > 1.5 * abs(rev):
            errors.append("résultat net supérieur à 1,5 fois le chiffre d'affaires : lignes de tableaux différents")
    return d, errors, notes
