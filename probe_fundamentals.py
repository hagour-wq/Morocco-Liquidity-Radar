"""Sonde : fiches émetteurs / chiffres clés sur le site de la Bourse ; bulletin de la cote (ISIN, titres, dividendes)."""
import io, json, os, re, traceback
import casablanca_source as cb
os.makedirs("diag", exist_ok=True)
out = {}
try:
    for p in ["/sitemap.xml", "/fr/sitemap.xml", "/robots.txt"]:
        try:
            t = cb._get(cb.BASE + p, accept="*/*").decode("utf-8", "ignore")
            out[p] = {"bytes": len(t), "head": t[:1500], "emetteur_urls": sorted(set(re.findall(r"https?://[^<\s\"]*(?:emetteur|instrument|societe|fiche)[^<\s\"]*", t)))[:40]}
        except Exception as e:
            out[p] = str(e)[:200]
    for p in ["/live-market/actions", "/fr/live-market/emetteurs", "/fr/emetteurs", "/live-market/emetteurs", "/fr/live-market/instruments/ATW", "/fr/live-market/emetteur/attijariwafa-bank",
              "/fr/emetteurs/attijariwafa-bank", "/fr/live-market/instruments/actions/ATW"]:
        try:
            h = cb.get_html(p)
            title = re.search(r"<title>(.*?)</title>", h, re.S)
            out[p] = {"bytes": len(h), "title": title.group(1).strip()[:120] if title else None,
                      "links": sorted(set(re.findall(r'href="([^"]*(?:emetteur|instrument|fiche|societe)[^"]*)"', h, re.I)))[:40]}
        except Exception as e:
            out[p] = str(e)[:200]
    h = cb.get_html("/live-market/actions")
    s = cb.drupal_settings(h).get("live_market", {})
    a = s.get("actions", [{}])[0]
    out["action_keys"] = list(a.keys())
    # bulletin de la cote le plus récent
    h = cb.get_html("/market-data/bulletins-de-la-cote")
    links = sorted(set(re.findall(r'href="([^"]*bcfr_?\d{8}\.pdf)"', h, re.I)))
    url = [l for l in links if "_d_" not in l.lower()][-1]
    from pypdf import PdfReader
    b = cb._get(cb.BASE + url if url.startswith("/") else url, accept="application/pdf")
    open("diag/bulletin_latest.pdf", "wb").write(b)
    txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages)
    open("diag/bulletin_latest.txt", "w").write(txt)
    out["bulletin"] = {"url": url, "bytes": len(b), "chars": len(txt)}
except Exception:
    out["error"] = traceback.format_exc()[-1500:]
finally:
    open("diag/fundamentals_probe.json", "w").write(json.dumps(out, ensure_ascii=False, indent=1))
