"""Calendrier financier officiel de la Bourse de Casablanca : dividendes (2013 →) et assemblées générales (2011 →).

Source : https://www.casablanca-bourse.com/emetteurs/calendrier-financier — les données de la page sont
publiées dans drupalSettings.boursenova (dividendesData, agData), sans saisie manuelle.
Contrôles :
- émetteur rapproché d'un ticker coté par son nom normalisé (sinon : « non rapproché », conservé à part —
  sociétés radiées, par exemple) ;
- montant > 0 et en MAD, dates valides, détachement ≤ paiement, doublons supprimés ;
- recoupement du dernier dividende avec le bulletin de la cote (data/issuer_reference.json).
Sortie : data/dividends.json (par ticker : dividendes et assemblées, du plus récent au plus ancien).
"""
import html, json, re, sys, unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
import casablanca_source as cb

PAGE = "/emetteurs/calendrier-financier"
OUT = Path("data/dividends.json")
INDEX = Path("data/equities/index.json")
REF = Path("data/issuer_reference.json")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(SA|S A|STE|SOCIETE)\b", " ", s)
    return " ".join(s.split())


def name_map():
    m = {}
    if INDEX.exists():
        for c in json.loads(INDEX.read_text(encoding="utf-8"))["companies"]:
            m[norm(c["name"])] = c["ticker"]
    if REF.exists():
        for t, r in json.loads(REF.read_text(encoding="utf-8")).get("issuers", {}).items():
            m.setdefault(norm(r.get("name_bulletin")), t)
    m.pop("", None)
    return m


def amount(s):
    m = re.fullmatch(r"\s*(\d[\d\s]*(?:,\d+)?)\s*MAD\s*", s or "")
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def day(s):
    try:
        return datetime.fromisoformat(s).date().isoformat() if s else None
    except ValueError:
        return None


def parse(settings, names):
    """Renvoie (par_ticker, non_rapprochés, anomalies)."""
    by, unmatched, issues, seen = {}, {}, [], set()
    for year, rows in sorted((settings.get("dividendesData") or {}).items()):
        for r in rows:
            em, amt = (r.get("emetteur") or "").strip(), amount(r.get("dividende"))
            ex, pay = day(r.get("dateDetachement")), day(r.get("datePaiement"))
            rec = {"ex_date": ex, "payment_date": pay, "type": r.get("typeDividende"), "amount_mad": amt,
                   "calendar_year": int(year), "published": r.get("dividende")}
            if not em or amt is None or amt <= 0 or not ex:
                issues.append({"reason": "ligne incomplète ou montant invalide", **rec, "emetteur": em})
                continue
            if pay and pay < ex:
                issues.append({"reason": "paiement antérieur au détachement", **rec, "emetteur": em})
            t = names.get(norm(em))
            key = (t or em, ex, amt, rec["type"])
            if key in seen:
                continue
            seen.add(key)
            if t:
                by.setdefault(t, {"dividends": [], "meetings": []})["dividends"].append(rec)
            else:
                unmatched.setdefault(em, []).append(rec)
    for year, rows in sorted((settings.get("agData") or {}).items()):
        for r in rows:
            em, d = (r.get("emetteur") or "").strip(), day(r.get("date"))
            t = names.get(norm(em))
            if not t or not d:
                continue
            objets = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", o)) for o in r.get("objets") or [])
            by.setdefault(t, {"dividends": [], "meetings": []})["meetings"].append(
                {"date": d, "nature": r.get("nature"), "objets": " ".join(objets.split())})
    for v in by.values():
        v["dividends"].sort(key=lambda x: x["ex_date"], reverse=True)
        v["meetings"].sort(key=lambda x: x["date"], reverse=True)
    return by, unmatched, issues


def cross_check(by, ref, first_year=2013):
    """Dernier dividende du bulletin de la cote (montant ajusté) comparé au calendrier (couvert depuis first_year)."""
    out = {}
    for t, r in ref.items():
        if not r.get("dividend_ex_date") or r["dividend_ex_date"][:4] < str(first_year) or t not in by:
            continue
        same = [d for d in by[t]["dividends"] if d["ex_date"] == r["dividend_ex_date"]]
        if not same:
            out[t] = "date de détachement du bulletin absente du calendrier"
        elif not any(abs(d["amount_mad"] - (r.get("last_dividend_mad") or 0)) <= 0.011 for d in same):
            out[t] = f"montant différent : calendrier {same[0]['amount_mad']} MAD, bulletin {r.get('last_dividend_mad')} MAD (ajusté)"
    return out


def trailing_dividends(divs, as_of, days=365):
    """Dividendes détachés dans les `days` jours précédant as_of (ordinaires et optionnels ; exceptionnels à part)."""
    lo = date.fromordinal(as_of.toordinal() - days).isoformat()
    win = [d for d in divs if lo < d["ex_date"] <= as_of.isoformat()]
    return (sum(d["amount_mad"] for d in win if d["type"] != "Exceptionnel"),
            sum(d["amount_mad"] for d in win if d["type"] == "Exceptionnel"), win)


def main():
    now = datetime.now(timezone.utc).isoformat()
    h = cb.get_html(PAGE)
    settings = cb.drupal_settings(h).get("boursenova") or {}
    if not settings.get("dividendesData"):
        print("::error title=collect_dividends::dividendesData absent de la page")
        sys.exit(1)
    by, unmatched, issues = parse(settings, name_map())
    ref = json.loads(REF.read_text(encoding="utf-8")).get("issuers", {}) if REF.exists() else {}
    checks = cross_check(by, ref, min(int(y) for y in settings["dividendesData"]))
    for t, msg in checks.items():
        by[t]["bulletin_check"] = msg
    out = {"generated_at": now, "source": "Bourse de Casablanca — Calendrier financier", "source_url": cb.BASE + PAGE,
           "years_dividends": sorted(settings["dividendesData"]), "years_meetings": sorted(settings.get("agData") or {}),
           "fields": {"amount_mad": "dividende unitaire publié (MAD, non ajusté des opérations sur titres)",
                      "ex_date": "date de détachement", "payment_date": "date de mise en paiement"},
           "companies": by, "unmatched_issuers": unmatched, "issues": issues, "bulletin_mismatches": checks}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(v["dividends"]) for v in by.values())
    print(json.dumps({"tickers": len(by), "dividends": n, "unmatched_issuers": len(unmatched), "issues": len(issues),
                      "bulletin_mismatches": len(checks)}, ensure_ascii=False))
    for t, msg in list(checks.items())[:10]:
        print(f"::warning title=collect_dividends {t}::{msg}")


if __name__ == "__main__":
    main()
