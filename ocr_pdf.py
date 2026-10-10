"""Reconnaissance de caractères (OCR) pour les PDF publiés sous forme d'images (sans couche texte).

Outils : pdftoppm (poppler-utils) pour rasteriser, tesseract (langue fra, à défaut eng) pour lire.
Mode --psm 6 : bloc de texte uniforme, qui conserve une ligne de tableau par ligne de texte
(libellé puis montants), format attendu par extract_financials.py.
Le texte OCR est marqué comme tel : les mêmes contrôles croisés s'appliquent ensuite, sans tolérance supplémentaire.
"""
import os, re, shutil, subprocess, tempfile

MAX_PAGES = int(os.environ.get("OCR_MAX_PAGES", "40"))
DPI = int(os.environ.get("OCR_DPI", "300"))


def available():
    return bool(shutil.which("pdftoppm") and shutil.which("tesseract"))


def languages():
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=30).stdout
        return [l.strip() for l in out.splitlines()[1:] if l.strip()]
    except Exception:
        return []


def ocr_pdf(data, max_pages=MAX_PAGES, dpi=DPI):
    """Renvoie (texte, informations). Lève RuntimeError si les outils sont absents."""
    if not available():
        raise RuntimeError("OCR indisponible : pdftoppm / tesseract non installés")
    langs = languages()
    lang = "fra" if "fra" in langs else "eng"
    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "doc.pdf")
        with open(pdf, "wb") as f:
            f.write(data)
        subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-l", str(max_pages), pdf, os.path.join(tmp, "p")],
                       check=True, capture_output=True, timeout=600)
        pages = sorted(x for x in os.listdir(tmp) if x.endswith(".png"))
        texts = []
        for p in pages:
            r = subprocess.run(["tesseract", os.path.join(tmp, p), "stdout", "-l", lang, "--psm", "6"],
                               capture_output=True, text=True, timeout=300)
            texts.append(r.stdout)
    return "\n".join(texts), {"engine": "tesseract", "language": lang, "pages": len(pages), "dpi": dpi}


_LINE = re.compile(r"^(?P<keep>.*?[A-Za-zÀ-ÿ)].*?\s(?:[-(–]?\s?\d[\d,.()]*\s+){1,7}[-(–]?\d[\d,.()]*%?)(?=\s+(?:\S\s+)?\S*[A-Za-zÀ-ÿ]{2,})")


def clean_lines(text):
    """Page à deux colonnes lue d'une traite (« Chiffre d'affaires 36 699 36 681 s'élèvent à… ») :
    la ligne est coupée après la zone numérique pour que le libellé et ses montants forment une ligne de tableau."""
    out = []
    lines = []
    for line in text.splitlines():   # « … | Chiffre d'affaires 188 069 … » : libellé repris après un séparateur de colonne
        lines += re.split(r"\s\|\s+(?=[A-Za-zÀ-ÿ'][A-Za-zÀ-ÿ']{3,})", line)
    for line in lines:
        m = _LINE.match(line)
        keep = m.group("keep") if m else line
        out.append(re.sub(r"(\d)\.(?=\s|$)", r"\1", keep))   # « 72656. » : point final parasite
    return "\n".join(out)


# --- Montants mal découpés par l'OCR ------------------------------------------------------------
# Tesseract perd parfois l'espace des milliers (« 3813 552 » pour 3 813 552, « 4 976106 » pour 4 976 106)
# ou lit une lettre à la place d'un chiffre (« AO 426 437 » pour 40 426 437).
# Règles (aucune valeur n'est devinée) :
# - la zone numérique finale d'une ligne doit se lire comme exactement deux montants (N, N-1) ;
# - une ligne déjà lisible selon la présentation standard (1 à 3 chiffres, puis groupes de 3) n'est pas modifiée ;
# - sinon, un groupe peut avoir perdu ses espaces (longueur libre en tête de montant, multiple de 3 ensuite) :
#   la correction n'est appliquée que si UNE SEULE découpe en deux montants est possible ;
# - lettre lue pour un chiffre (O/o/D → 0, l/I/| → 1, A → 4) : acceptée seulement si le montant corrigé
#   figure ailleurs dans le document (par exemple dans l'attestation des commissaires aux comptes).
_LETTER = str.maketrans({"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "A": "4"})
_TOK = re.compile(r"^-?[\dOoDlI|A]{1,9}$")


def _split_two(tokens, fused):
    """Découpes possibles des jetons en deux montants (listes de jetons)."""
    def ok(seq):
        head, rest = seq[0].lstrip("-"), seq[1:]
        if not head or any(t.startswith("-") for t in rest) or (head.startswith("0") and (len(head) > 1 or rest)):
            return False
        if not fused:
            return len(head) <= 3 and all(len(t) == 3 for t in rest)
        return all(len(t) % 3 == 0 for t in rest)
    return [(tokens[:i], tokens[i:]) for i in range(1, len(tokens)) if ok(tokens[:i]) and ok(tokens[i:])]


def _fmt(seq):
    digits = "".join(t.lstrip("-") for t in seq)
    sign = "-" if seq[0].startswith("-") else ""
    groups = [digits[max(0, i - 3):i] for i in range(len(digits), 0, -3)][::-1]
    return sign + " ".join(groups), int(digits)


def repair_amounts(text):
    """Renvoie (texte corrigé, liste des corrections : ligne avant → après)."""
    digits_only = re.sub(r"(?<=\d)[ . ](?=\d{3}\b)", "", text)
    lines, fixes = text.split("\n"), []
    for i, line in enumerate(lines):
        words = line.rstrip().split(" ")
        k = len(words)
        while k > 0 and _TOK.match(words[k - 1]) and (any(c.isdigit() for c in words[k - 1]) or len(words[k - 1]) <= 2):
            k -= 1
        tail = [w for w in words[k:] if w]
        if len(tail) < 2 or not any(c.isdigit() for c in "".join(tail)):
            continue
        letters = any(re.search(r"[^\d-]", t) for t in tail)
        if not letters and _split_two(tail, fused=False):
            continue                                   # présentation standard : laissée au lecteur habituel
        fixed = [t.translate(_LETTER) for t in tail]
        if not all(re.fullmatch(r"-?\d+", t) for t in fixed):
            continue
        cands = _split_two(fixed, fused=False) if letters else []
        cands = cands or _split_two(fixed, fused=True)
        if len(cands) != 1:
            continue                                   # aucune ou plusieurs découpes : ligne laissée telle quelle
        (a, va), (b, vb) = _fmt(cands[0][0]), _fmt(cands[0][1])
        if all(1990 <= v <= 2100 for v in (va, vb)):
            continue                                   # en-tête d'années (« 2025 2024 ») : pas un montant
        if letters:   # chiffre reconstitué : confirmation exigée ailleurs dans le document
            n1 = len(cands[0][0])
            need = [va] if any(re.search(r"[^\d-]", t) for t in tail[:n1]) else []
            need += [vb] if any(re.search(r"[^\d-]", t) for t in tail[n1:]) else []
            if not all(re.search(rf"(?<!\d){v}(?!\d)", digits_only) for v in need):
                continue
        new = " ".join(w for w in words[:k]) + (" " if k else "") + a + " " + b
        fixes.append({"before": line.strip()[-120:], "after": new.strip()[-120:]})
        lines[i] = new
    return "\n".join(lines), fixes
