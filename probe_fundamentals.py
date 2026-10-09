"""Sonde : liste complète des publications émetteurs + test d'extraction des comptes annuels 2025 candidats."""
import io, json, os, re, traceback, time
import casablanca_source as cb
from pypdf import PdfReader
os.makedirs("diag/pub", exist_ok=True)
out = {"pages": 0, "links": {}}
try:
    for page in range(0, 200):
        h = cb.get_html(f"/apropos/publications/emetteurs?page={page}")
        rows = re.findall(r'href="([^"]+\.pdf)"', h, re.I)
        if not rows:
            break
        out["pages"] = page + 1
        for u in rows:
            i = h.find(u)
            ctx = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h[max(0, i - 500):i]))
            out["links"].setdefault(u, ctx[-200:])
        time.sleep(0.1)
    annual = {u: c for u, c in out["links"].items() if re.search(r"_20(25|26)(_\d)?\.pdf$|rfa_?2025|rapport_financier_annuel_2025|_fy_?2025", u, re.I) and not re.search(r"/cp[_-]", u, re.I)}
    out["annual_candidates"] = annual
    out["probe"] = {}
    for u in list(annual)[:120]:
        try:
            url = u if u.startswith("http") else cb.BASE + u
            b = cb._get(url, accept="application/pdf")
            txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages[:30])
            name = os.path.basename(u)[:90]
            open(f"diag/pub/A_{name}.txt", "w").write(url + "\n\n" + txt)
            out["probe"][u] = {"chars": len(txt), "pages": len(PdfReader(io.BytesIO(b)).pages)}
            time.sleep(0.2)
        except Exception as e:
            out["probe"][u] = {"error": str(e)[:150]}
except Exception:
    out["error"] = traceback.format_exc()[-1500:]
finally:
    open("diag/publications_all.json", "w").write(json.dumps(out, ensure_ascii=False, indent=1))
