"""OCR : un PDF image (sans couche texte) est lu par tesseract puis analysé avec les mêmes contrôles."""
import io, shutil, unittest
import ocr_pdf
from extract_financials import extract, checks

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
