"""Fondamentaux à partir des comptes annuels publiés (registre data/fundamentals_sources.json).

Pour chaque émetteur : téléchargement du PDF officiel, extraction des lignes d'états financiers
(extract_financials.py), contrôles croisés avec le nombre de titres du bulletin de la cote,
indicateurs dérivés. Statuts :
- VERIFIED : grandeurs principales extraites et contrôles réussis ;
- PARTIAL : extraction incomplète (grandeurs manquantes listées) ;
- REJECTED : contrôle bloquant en échec ;
- UNREADABLE : document sans texte exploitable (PDF image).
Sortie : data/company_fundamentals.json — chaque grandeur garde la ligne source, l'unité et l'URL.
"""
import io, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
import casablanca_source as cb
from extract_financials import extract, checks, detach_labels
import ocr_pdf

SOURCES = Path("data/fundamentals_sources.json")
REF = Path("data/issuer_reference.json")
OUT = Path("data/company_fundamentals.json")
REQUIRED = {"bank": ["pnb", "net_income_group", "equity_total", "minority_interests", "cost_of_risk", "operating_expenses"],
            "corporate": ["revenue", "net_income_group", "equity_total|equity_group"],
            "insurance": ["revenue", "net_income_group", "equity_group|equity_total"]}


MIN_TEXT = 2000
RANK = {"UNREADABLE": 0, "REJECTED": 1, "PARTIAL": 2, "VERIFIED": 3}
OCR_CACHE = Path("data/ocr_cache")


def ocr_cached(data):
    """OCR coûteux (~2 min par document) : texte conservé par empreinte SHA-256 du PDF ; un document modifié est relu."""
    import hashlib
    h = hashlib.sha256(data).hexdigest()
    f = OCR_CACHE / f"{h}.json"
    if f.exists():
        c = json.loads(f.read_text(encoding="utf-8"))
        return c["text"], {**c["info"], "cache": "réutilisé", "sha256": h}
    text, info = ocr_pdf.ocr_pdf(data)
    OCR_CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"info": info, "text": text}, ensure_ascii=False) + "\n", encoding="utf-8")
    return text, {**info, "cache": "nouvelle lecture", "sha256": h}


def capital_unit_rescue(text, fin):
    """En-têtes d'unité faux (Aluminium du Maroc : « EN M MAD » sur des montants en milliers) : l'unité du tableau est
    déduite du capital social publié en dirhams (« au capital de 46.595.400 Dirhams ») rapporté à la ligne « Capital »
    du bilan retenu (46 595,40) — rapport exact de 1, 1 000 ou 1 000 000 exigé. Utilisé seulement si les contrôles de
    PER / P/B échouent avec les unités lues, et retenu seulement s'ils réussissent ensuite."""
    import copy
    from extract_financials import flatten, PER_SHARE
    m = re.search(r"au capital (?:social )?de\s+(\d{1,3}(?:[ .]\d{3})+)(?:,00)?\s*(?:de\s+)?(?:dirhams|dhs?|mad)\b", flatten(text), re.I)
    cap = fin.get("share_capital")
    if not m or not cap or not cap.get("current"):
        return None
    published = float(re.sub(r"[ .]", "", m.group(1)))
    u = next((u for u in (1.0, 1e3, 1e6) if abs(published / (cap["current"] * u) - 1) <= 0.001), None)
    if u is None:
        return None
    out = copy.deepcopy(fin)
    for k, f in out.items():
        if isinstance(f, dict) and "current" in f and k not in PER_SHARE and f.get("unit") != u:
            f["unit"], f["unit_method"] = u, "capital social publié"
            f["mad"] = f["current"] * u
            f["mad_previous"] = None if f.get("previous") is None else f["previous"] * u
    fr = lambda x, d: f"{x:,.{d}f}".replace(",", " ").replace(".", ",")
    note = (f"unités des états déduites du capital social publié ({fr(published, 0)} MAD = {fr(cap['current'], 2)} × {fr(u, 0)}) : "
            "en-têtes d'unité du document incohérents avec les montants")
    return out, note


def analyse(src, text, shares, price=None, text_source="pdf_text"):
    if len(text.strip()) < MIN_TEXT:
        return {"status": "UNREADABLE", "text_source": text_source,
                "reason": "document sans texte exploitable (PDF image)" + (" ; OCR également insuffisant" if text_source == "ocr" else "")}
    repaired = []
    if text_source == "ocr":
        text, repaired = ocr_pdf.repair_amounts(ocr_pdf.clean_lines(text))
        text, detached = detach_labels(text, src["model"])
    fin = extract(text, src["model"])
    period = re.search(r"\bdu\s+(\d{1,2})/(\d{1,2})/(20\d\d)\s+au\s+(\d{1,2})/(\d{1,2})/(20\d\d)", text, re.I)
    period_end = f"{period.group(6)}-{int(period.group(5)):02d}-{int(period.group(4)):02d}" if period else None
    derived, errors, notes = checks(fin, src["model"], shares, price)
    if any("hors bornes" in e for e in errors):
        fixed = capital_unit_rescue(text, fin)
        if fixed:
            d2, e2, n2 = checks(fixed[0], src["model"], shares, price)
            if not e2:
                fin, derived, errors, notes = fixed[0], d2, e2, [fixed[1]] + n2
    missing = [k for k in REQUIRED[src["model"]] if not any(fin.get(x) for x in k.split("|"))
               and not (k == "minority_interests" and fin.get("_scope") == "social")]
    status = "REJECTED" if errors else "PARTIAL" if missing else "VERIFIED"
    extra = {}
    if period_end and period_end != src.get("period_end"):
        extra = {"period_end": period_end, "period_end_registry": src.get("period_end")}
        notes.append(f"exercice du {period.group(1)}/{period.group(2)}/{period.group(3)} au {period.group(4)}/{period.group(5)}/{period.group(6)} (lu dans le document)")
    if text_source == "ocr":
        notes.insert(0, "texte obtenu par reconnaissance de caractères (OCR) : PDF publié sans couche texte ; mêmes contrôles croisés appliqués")
    if repaired:
        extra["ocr_amount_repairs"] = repaired
        notes.append(f"{len(repaired)} ligne(s) de montants OCR recomposée(s) (espaces de milliers perdus ou lettre lue pour un chiffre, découpe unique exigée ; détail : ocr_amount_repairs)")
    return {**extra, "text_source": text_source, "status": status, "errors": errors, "notes": notes, "missing": missing,
            "scope": fin.get("_scope"),
            "statements": {k: ({kk: x[kk] for kk in ("current", "previous", "unit", "mad", "mad_previous", "line", "layout", "ambiguous_split", "method") if kk in x} if x else None)
                           for k, x in fin.items() if not k.startswith("_")},
            "derived": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in derived.items()}}


def main():
    from pypdf import PdfReader
    now = datetime.now(timezone.utc).isoformat()
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    ref = json.loads(REF.read_text(encoding="utf-8")).get("issuers", {}) if REF.exists() else {}
    out = {"generated_at": now, "source_registry": str(SOURCES), "listing": sources.get("listing"), "companies": []}
    for src in sources["issuers"]:
        t = src["ticker"]
        r = ref.get(t, {})
        rec = {**src, "isin": r.get("isin"), "shares": r.get("shares"), "shares_source": "bulletin de la cote " + str(json.loads(REF.read_text(encoding="utf-8")).get("bulletin_date")) if r else None,
               "listing_exchange": "Casablanca Stock Exchange", "listing_country": "MA", "collected_at": now}
        if src["model"] not in REQUIRED:
            rec.update(status="SECTOR_MODEL_PENDING", reason=f"modèle sectoriel « {src['model']} » non implémenté : pas de ratios industriels appliqués")
            out["companies"].append(rec)
            continue
        if src.get("no_statements"):   # document vérifié manuellement : pas d'états financiers à extraire
            rec.update(status="NO_STATEMENTS", reason="document publié sans états financiers : " + src["no_statements"])
            out["companies"].append(rec)
            continue
        try:
            b = cb._get(src["url"], accept="application/pdf")
            text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages)
            source = "pdf_text"
            if len(text.strip()) < MIN_TEXT and ocr_pdf.available():
                text, info = ocr_cached(b)
                source = "ocr"
                rec["ocr"] = info
            res = analyse(src, text, r.get("shares"), r.get("reference_price_mad"), source)
            if src.get("force_ocr") and source == "pdf_text" and ocr_pdf.available():
                # couche texte altérée (chiffres coupés) : la page est relue par OCR, et la meilleure lecture est conservée
                otext, info = ocr_cached(b)
                ores = analyse(src, otext, r.get("shares"), r.get("reference_price_mad"), "ocr")
                if RANK.get(ores["status"], 0) > RANK.get(res["status"], 0):
                    ores["notes"] = [n for n in ores.get("notes", []) if "sans couche texte" not in n]
                    ores["notes"].insert(0, f"texte obtenu par reconnaissance de caractères (OCR) : couche texte du PDF altérée ({src['force_ocr']}) ; mêmes contrôles croisés appliqués")
                    res, rec["ocr"] = ores, info
                else:
                    res.setdefault("notes", []).append(f"OCR essayé ({src['force_ocr']}) mais pas meilleur que la couche texte (statut OCR : {ores['status']})")
            rec.update(res)
        except Exception as e:
            rec.update(status="SOURCE_ERROR", reason=f"{type(e).__name__}: {e}"[:200])
        out["companies"].append(rec)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({c["ticker"]: (c["status"], c.get("errors") or c.get("missing") or c.get("reason")) for c in out["companies"]}, ensure_ascii=False))
    for c in out["companies"]:
        if c["status"] not in ("VERIFIED",):
            print(f"::warning title=collect_fundamentals {c['ticker']}::{c['status']} {c.get('reason') or c.get('errors') or c.get('missing')}")
    if not any(c["status"] == "VERIFIED" for c in out["companies"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
