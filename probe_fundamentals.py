"""Sonde : communiqués financiers des émetteurs pilotes (page Publications émetteurs de la Bourse)."""
import io, json, os, re, traceback, time
import casablanca_source as cb
from pypdf import PdfReader
os.makedirs("diag/pub", exist_ok=True)
out = {"pages": {}, "candidates": {}}
KEYS = {"ATW": ["attijari"], "BCP": ["bcp", "populaire"], "IAM": ["maroc_telecom", "maroc-telecom", "iam", "itissalat", "maroc telecom"],
        "MSA": ["marsa"], "MNG": ["managem"]}
try:
    links = {}
    for page in range(0, 80):
        h = cb.get_html(f"/apropos/publications/emetteurs?page={page}")
        found = re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', h, re.S | re.I)
        rows = re.findall(r'href="([^"]+\.pdf)"', h, re.I)
        out["pages"][page] = len(rows)
        if not rows:
            break
        # libellé : texte proche du lien
        for u in rows:
            i = h.find(u)
            ctx = re.sub(r"<[^>]+>", " ", h[max(0, i - 600):i + 200])
            links.setdefault(u, re.sub(r"\s+", " ", ctx)[-400:])
        time.sleep(0.15)
    out["total_links"] = len(links)
    for t, keys in KEYS.items():
        c = [(u, l) for u, l in links.items() if any(k in (u + " " + l).lower() for k in keys)]
        out["candidates"][t] = [{"url": u, "ctx": l[-250:]} for u, l in c][:30]
    for t, c in out["candidates"].items():
        for item in c:
            u = item["url"].lower()
            if any(k in u for k in ["fy", "annuel", "2025", "s1_26", "s1-26", "s1_2026", "resultats", "t4", "comptes"]) and len([f for f in os.listdir("diag/pub") if f.startswith(t)]) < 6:
                try:
                    url = item["url"] if item["url"].startswith("http") else cb.BASE + item["url"]
                    b = cb._get(url, accept="application/pdf")
                    txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages[:12])
                    name = f"{t}_{os.path.basename(item['url'])[:80]}.txt"
                    open(f"diag/pub/{name}", "w").write(url + "\n\n" + txt)
                    item["saved"] = name
                except Exception as e:
                    item["error"] = str(e)[:150]
except Exception:
    out["error"] = traceback.format_exc()[-1500:]
finally:
    open("diag/publications_probe.json", "w").write(json.dumps(out, ensure_ascii=False, indent=1))
