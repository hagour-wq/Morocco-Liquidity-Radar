"""OCR : un PDF image (sans couche texte) est lu par tesseract puis analysé avec les mêmes contrôles."""
import io, shutil, unittest
import ocr_pdf
from extract_financials import extract, checks, detach_labels

LINES = ["COMPTE DE RESULTAT CONSOLIDE (en milliers de dirhams) 2025 2024",
         "Chiffre d'affaires 3 251 072 2 940 457",
         "Resultat net part du groupe 112 330 57 886",
         "Capitaux propres part du groupe 788 101 720 476"]


def image_pdf(lines):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("L", (2480, 900), 255)
    d = ImageDraw.Draw(img)
    import glob
    paths = glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True) + glob.glob("/usr/share/fonts/**/LiberationSans-Regular.ttf", recursive=True)
    try:
        font = ImageFont.truetype(paths[0] if paths else "DejaVuSans.ttf", 44)
    except OSError:
        font = ImageFont.load_default(size=44)
    for i, l in enumerate(lines):
        d.text((120, 120 + i * 110), l, fill=0, font=font)
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=300)
    return buf.getvalue()


class CleanLinesTests(unittest.TestCase):
    """Lignes OCR réelles (pages à deux colonnes, séparateurs, points parasites)."""
    def test_two_column_pages(self):
        c = ocr_pdf.clean_lines("Chiffre d'affaires 36 699 36 681 s'élèvent à un montant de Dirhams 1 593 millions.\n"
                                "Ecarts d'acquisition m4 995 | nas | Chiffre d'affaires 188 069 172 249 15 820\n"
                                "Résultats net part du groupe 73 801 66 626 E Fidaroc\nRÉSULTAT NET - PART DU GROUPE 72656. 72354")
        self.assertIn("Chiffre d'affaires 36 699 36 681", c.splitlines())
        self.assertIn("Chiffre d'affaires 188 069 172 249 15 820", c.splitlines())
        self.assertIn("Résultats net part du groupe 73 801 66 626", c.splitlines())
        self.assertIn("RÉSULTAT NET - PART DU GROUPE 72656 72354", c.splitlines())


class CacheTests(unittest.TestCase):
    def test_ocr_text_reused_for_same_pdf(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import collect_fundamentals as cf
        calls = []
        with tempfile.TemporaryDirectory() as d, patch.object(cf, "OCR_CACHE", Path(d)), \
                patch.object(cf.ocr_pdf, "ocr_pdf", lambda b: (calls.append(1) or "texte", {"pages": 1})):
            a = cf.ocr_cached(b"%PDF-1 a")
            b = cf.ocr_cached(b"%PDF-1 a")
            c = cf.ocr_cached(b"%PDF-1 b")
        self.assertEqual(len(calls), 2)                       # même PDF : une seule lecture
        self.assertEqual((a[1]["cache"], b[1]["cache"]), ("nouvelle lecture", "réutilisé"))
        self.assertEqual(c[1]["cache"], "nouvelle lecture")


class RepairAmountsTests(unittest.TestCase):
    """Lignes réelles de l'OCR des comptes consolidés 2025 de Bank of Africa."""
    def fix(self, text):
        return ocr_pdf.repair_amounts(text)[0].splitlines()

    def test_lost_thousands_spaces_with_unique_split(self):
        out = self.fix("RÉSULTAT NET - PART DU GROUPE 3813 552 3 427 420\nFidaroc BD RÉSULTAT NET 5 514 079 4 976106\n"
                       "PRODUIT NET BANCAIRE 20338747 18716574")
        self.assertEqual(out[0], "RÉSULTAT NET - PART DU GROUPE 3 813 552 3 427 420")
        self.assertEqual(out[1], "Fidaroc BD RÉSULTAT NET 5 514 079 4 976 106")
        self.assertEqual(out[2], "PRODUIT NET BANCAIRE 20 338 747 18 716 574")

    def test_standard_and_ambiguous_lines_untouched(self):
        for line in ("Coût du risque -3 287 621 -3 177 600", "En milliers de DH 2025 2024", "Total 1 234 567 890"):
            self.assertEqual(self.fix(line)[0], line)

    def test_letter_digit_needs_confirmation_elsewhere(self):
        line = "TOTAL CAPITAUX PROPRES CONSOLIDES AO 426 437 36 814 698"
        self.assertEqual(self.fix(line)[0], line)                                   # non confirmé : laissé tel quel
        att = "\ncapitaux propres consolidés totalisant KMAD 40.426.437, dont un bénéfice"
        self.assertEqual(self.fix(line + att)[0], "TOTAL CAPITAUX PROPRES CONSOLIDES 40 426 437 36 814 698")


class DetachLabelsTests(unittest.TestCase):
    def test_label_after_other_column_text_is_detached(self):
        t, n = detach_labels("couvrir les risques de pertes et PRODUIT NET BANCAIRE 20 338 747 18 716 574", "bank")
        self.assertEqual(n, 1)
        self.assertEqual(t.splitlines()[1], "PRODUIT NET BANCAIRE 20 338 747 18 716 574")

    def test_lowercase_fragment_of_longer_label_not_detached(self):
        line = "Dépréciations sur prêts et créances sur la clientèle -21 886 409 -19 952 451"
        self.assertEqual(detach_labels(line, "bank"), (line, 0))


@unittest.skipUnless(ocr_pdf.available(), "tesseract / pdftoppm absents")
class OcrTests(unittest.TestCase):
    def test_image_pdf_is_read_and_checked(self):
        text, info = ocr_pdf.ocr_pdf(image_pdf(LINES))
        self.assertEqual(info["pages"], 1)
        f = extract(text, "corporate")
        self.assertEqual(f["revenue"]["mad"], 3251072e3)
        self.assertEqual(f["net_income_group"]["mad"], 112330e3)
        d, e, n = checks(f, "corporate", 1980000, 1225.0)
        self.assertEqual(e, [])


if __name__ == "__main__":
    unittest.main()
