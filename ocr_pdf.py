"""Reconnaissance de caractères (OCR) pour les PDF publiés sous forme d'images (sans couche texte).

Outils : pdftoppm (poppler-utils) pour rasteriser, tesseract (langue fra, à défaut eng) pour lire.
Mode --psm 6 : bloc de texte uniforme, qui conserve une ligne de tableau par ligne de texte
(libellé puis montants), format attendu par extract_financials.py.
Le texte OCR est marqué comme tel : les mêmes contrôles croisés s'appliquent ensuite, sans tolérance supplémentaire.
"""
import os, shutil, subprocess, tempfile

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
