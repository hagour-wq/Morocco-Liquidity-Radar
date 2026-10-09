"""Sonde : profondeur des archives PDF officielles (résumés de séance, bulletins de la cote) et contenu."""
import json, re, io
import casablanca_source as cb
from pypdf import PdfReader
import os, traceback
os.makedirs("diag", exist_ok=True)
out = {"listing": {}, "pdf": {}}
try:
    links = set()
    for path in ["/market-data/editions-statistiques", "/market-data/bulletins-de-la-cote"]:
        for page in range(0, 40):
            try:
                h = cb.get_html(f"{path}?page={page}")
            except Exception as e:
                out["listing"][f"{path}?page={page}"] = str(e)[:200]; break
            found = set(re.findall(r'href="([^"]+\.pdf)"', h))
            new = found - links
            out["listing"][f"{path}?page={page}"] = len(new)
            links |= found
            if not new:
                break
        # formulaires / filtres de date éventuels
        out["listing"][path + " forms"] = re.findall(r'<(?:select|input)[^>]+name="([^"]+)"', h)[:20]
    seance = sorted(l for l in links if "resume_seance" in l.lower())
    bulletins = sorted(l for l in links if "bcfr" in l.lower() and "_d_" not in l.lower())
    out["counts"] = {"all": len(links), "resume_seance": len(seance), "bulletins": len(bulletins)}
    out["resume_seance_range"] = [seance[:3], seance[-3:]]
    out["bulletins_range"] = [bulletins[:3], bulletins[-3:]]
    out["other_samples"] = sorted(l for l in links if "resume_seance" not in l.lower() and "bcfr" not in l.lower())[:40]
    for name, url in [("resume", seance[-1] if seance else None), ("bulletin", bulletins[-1] if bulletins else None)]:
        if not url:
            continue
        b = cb._get(cb.BASE + url if url.startswith("/") else url, accept="application/pdf")
        txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages[:3])
        out["pdf"][name] = {"url": url, "bytes": len(b), "text_head": txt[:3000]}

except Exception as e:
    out["error"] = traceback.format_exc()[-1500:]
    print("::error::" + repr(e)[:300])
finally:
    open("diag/masi_pdf_probe.json", "w").write(json.dumps(out, ensure_ascii=False, indent=1))
