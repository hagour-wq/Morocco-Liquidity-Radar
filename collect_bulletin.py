"""Référentiel émetteurs à partir du « Bulletin de la cote » PDF (Bourse de Casablanca).

Par action : code ISIN, nombre de titres, valeur nominale, code secteur, dernier dividende
(montant ajusté des opérations sur titres, exercice, date de détachement), cours de référence.
Rapprochement avec les tickers : nombre de titres identique à « nombreTitres » de la liste
officielle live-market (clé exacte), puis contrôle du cours. Les droits d'attribution (DA) et
les obligations sont ignorés.

Sortie : data/issuer_reference.json (un enregistrement par ticker, source et date du bulletin).
"""
import io, json, re, sys
from datetime import date, datetime, timezone
from pathlib import Path
import casablanca_source as cb

OUT = Path("data/issuer_reference.json")
LISTING = "/market-data/bulletins-de-la-cote"
N = r"\d{1,3}(?: \d{3})*,\d{2}"
LINE = re.compile(
    r"^(?P<shares>\d{1,3}(?: \d{3})+)(?P<nominal>\d+(?:,\d+)?)\s+(?P<sector>[A-Z]{2,3})\s+(?P<cycle>[A-Z])\s+"
    r"(?P<div>" + N + r")?(?P<year>(?:19|20)\d\d)?(?P<ex>\d\d/\d\d/\d\d)?\s*(?P<ref>" + N + r")(?P<refdate>\d\d/\d\d/\d\d)\s*"
    r"(?P<close>" + N + r")?\s*(?P<isin>MA\d{10})(?P<name>.+?)\s+(?:\d|-)")


def fr(s):
    return float(s.replace(" ", "").replace(",", ".")) if s else None


def ddmmyy(s):
    if not s:
        return None
    d, m, y = s.split("/")
    return date(2000 + int(y), int(m), int(d)).isoformat()


def parse_bulletin(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not re.search(r"MA\d{10}", line) or re.search(r"\sDA\s", line):
            continue
        m = LINE.search(line)
        if not m:
            continue
        g = m.groupdict()
        out.append({"isin": g["isin"], "name_bulletin": g["name"].strip(), "shares": int(g["shares"].replace(" ", "")),
                    "nominal_mad": fr(g["nominal"]), "sector_code": g["sector"], "quotation_cycle": g["cycle"],
                    "last_dividend_mad": fr(g["div"]), "dividend_fiscal_year": int(g["year"]) if g["year"] else None,
                    "dividend_ex_date": ddmmyy(g["ex"]), "reference_price_mad": fr(g["ref"]), "reference_date": ddmmyy(g["refdate"])})
    return out


def latest_bulletin_url():
    h = cb.get_html(LISTING)
    links = re.findall(r'href="([^"]*bcfr_?(\d{8})\.pdf)"', h, re.I)
    links = [(d, u) for u, d in links if "_d_" not in u.lower()]
    d, u = max(links)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}", (u if u.startswith("http") else cb.BASE + u)


def close_enough(a, r, tol):
    price = a.get("reference") or a.get("dernierCours")
    return bool(price and r["reference_price_mad"] and abs(price / r["reference_price_mad"] - 1) <= tol)


def match(records, live):
    by_shares = {}
    for t, a in live.items():
        if a.get("nombreTitres"):
            by_shares.setdefault(int(a["nombreTitres"]), []).append(t)
    out, unmatched = {}, []
    for r in records:
        cands = by_shares.get(r["shares"], [])
        if len(cands) > 1:  # même nombre de titres : départage par le cours (écart ≤ 5 %)
            near = [t for t in cands if close_enough(live[t], r, 0.05)]
            cands = near if len(near) == 1 else cands
        if len(cands) == 1:
            t = cands[0]
            price = live[t].get("reference") or live[t].get("dernierCours")
            r["price_check"] = ("cours indisponible (titre vraisemblablement suspendu)" if not price else
                                "ok" if close_enough(live[t], r, 0.25) else "écart de cours à vérifier")
            r["match_method"] = "nombre de titres" + (" + cours" if len(by_shares.get(r["shares"], [])) > 1 else "")
            out[t] = r
        else:
            unmatched.append({"isin": r["isin"], "name": r["name_bulletin"], "candidates": cands})
    return out, unmatched


def main():
    from pypdf import PdfReader
    now = datetime.now(timezone.utc).isoformat()
    bdate, url = latest_bulletin_url()
    b = cb._get(url, accept="application/pdf")
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages)
    records = parse_bulletin(text)
    live = {a["symbol"].strip(): a for a in cb.live_snapshot()["actions"] if a.get("symbol")}
    matched, unmatched = match(records, live)
    res = {"generated_at": now, "source": "Bourse de Casablanca — Bulletin de la cote", "source_url": url, "bulletin_date": bdate,
           "fields": {"last_dividend_mad": "dernier dividende ajusté (MAD par action)", "dividend_fiscal_year": "exercice",
                      "dividend_ex_date": "date de détachement", "shares": "nombre de titres composant le capital"},
           "parsed_equities": len(records), "matched": len(matched), "unmatched": unmatched,
           "listed_without_bulletin_line": sorted(set(live) - set(matched)), "issuers": matched}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("bulletin_date", "parsed_equities", "matched", "unmatched", "listed_without_bulletin_line")}, ensure_ascii=False))
    if not matched:
        sys.exit(1)


if __name__ == "__main__":
    main()
