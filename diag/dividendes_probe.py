"""Diagnostic : repère la page « calendrier des dividendes » de la Bourse de Casablanca et son flux de données."""
import json, re, sys
sys.path.insert(0, ".")
import casablanca_source as cb
out = {"pages": {}, "links": []}
seen = set()
for path in ["/fr", "/fr/live-market/marche-actions-listing", "/fr/marche-actions", "/fr/emetteurs", "/fr/market-data", "/fr/live-market/actions"]:
    try:
        h = cb.get_html(path)
    except Exception as e:
        out["pages"][path] = f"ERR {type(e).__name__}: {e}"[:200]; continue
    out["pages"][path] = len(h)
    for href in re.findall(r'href="([^"]+)"', h):
        if re.search(r"dividend|calendrier|agenda|evenement|operations-sur-titres|ost", href, re.I) and href not in seen:
            seen.add(href); out["links"].append(href)
detail = {}
for href in out["links"][:15]:
    p = href if href.startswith("/") else href.replace(cb.BASE, "")
    try:
        h = cb.get_html(p)
    except Exception as e:
        detail[href] = f"ERR {e}"[:200]; continue
    ds = None
    try:
        ds = cb.drupal_settings(h)
    except Exception:
        pass
    text = re.sub(r"<[^>]+>", " ", h)
    text = re.sub(r"\s+", " ", text)
    i = text.lower().find("dividende")
    detail[href] = {"len": len(h), "api": sorted(set(re.findall(r'["\'](/api/[^"\']+)', h)))[:20],
                    "drupal_keys": list(ds.keys())[:30] if isinstance(ds, dict) else None,
                    "excerpt": text[max(0, i - 200): i + 1500] if i >= 0 else text[:800]}
out["detail"] = detail
json.dump(out, open("data/diag_dividendes.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out["links"], ensure_ascii=False))
