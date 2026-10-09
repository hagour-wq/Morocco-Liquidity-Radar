"""Accès aux données officielles de la Bourse de Casablanca (www.casablanca-bourse.com).

Le serveur n'envoie pas son certificat intermédiaire (Sectigo Public Server
Authentication CA DV R36). On l'ajoute au magasin certifi : la vérification TLS
reste complète (chaîne vérifiée jusqu'à la racine Sectigo R46), rien n'est désactivé.

Services utilisés (ceux qu'appelle le site public lui-même) :
- /api/boursenova/stock-historical : séances OHLCV par action (≈ 3 ans glissants,
  fenêtre de requête ≤ 1 an).
- /api/live-market/indices/historical : historique d'un indice.
- /live-market/actions : instantané de toutes les actions + statut de séance
  (drupalSettings.live_market).
"""
import json, re, ssl, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import certifi

BASE = "https://www.casablanca-bourse.com"
TZ = ZoneInfo("Africa/Casablanca")
INTERMEDIATE = Path(__file__).with_name("certs") / "sectigo_public_server_auth_ca_dv_r36.pem"
UA = "Mozilla/5.0 (compatible; MoroccoLiquidityRadar/2.0; +https://github.com/hagour-wq/Morocco-Liquidity-Radar)"
SOURCE_NAME = "Bourse de Casablanca"


def tls_context():
    ctx = ssl.create_default_context(cafile=certifi.where())
    if INTERMEDIATE.exists():
        ctx.load_verify_locations(cafile=str(INTERMEDIATE))
    return ctx


_CTX = None


def _get(url, accept="application/json, text/plain, */*", retries=3):
    global _CTX
    _CTX = _CTX or tls_context()
    headers = {"User-Agent": UA, "Accept": accept, "Accept-Language": "fr-FR,fr;q=0.9",
               "Referer": BASE + "/market-data/cours"}
    last = None
    for i in range(retries):
        try:
            with urlopen(Request(url, headers=headers), timeout=45, context=_CTX) as r:
                return r.read()
        except Exception as e:  # retry réseau, l'erreur finale est remontée telle quelle
            last = e
            time.sleep(2 * (i + 1))
    raise last


def get_json(path, params=None):
    url = BASE + path + ("?" + urlencode(params) if params else "")
    return json.loads(_get(url))


def get_html(path):
    return _get(BASE + path, accept="text/html,*/*").decode("utf-8", "ignore")


def drupal_settings(html):
    m = re.search(r'data-drupal-selector="drupal-settings-json">(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("drupalSettings introuvable dans la page")
    return json.loads(m.group(1))


def parse_seance(s):
    d, m, y = s.strip().split("/")
    return date(int(y), int(m), int(d))


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stock_history(symbol, start, end, window_days=360):
    """Séances brutes (non ajustées) entre start et end, par fenêtres ≤ 1 an.
    Remonte dans le temps et s'arrête à la première fenêtre vide."""
    out = {}
    hi = end
    while hi >= start:
        lo = max(start, hi - timedelta(days=window_days))
        d = get_json("/api/boursenova/stock-historical", {
            "instrument": symbol, "market": "comptant", "type": "actions",
            "startDate": lo.isoformat(), "endDate": hi.isoformat(), "pageNumber": 1, "pageSize": 1000})
        items = d.get("items", []) if isinstance(d, dict) else []
        if isinstance(d, dict) and d.get("totalCount", 0) > len(items):
            raise ValueError(f"{symbol}: pagination non gérée ({d.get('totalCount')} > {len(items)})")
        for it in items:
            try:
                out[parse_seance(it["seance"]).isoformat()] = it
            except (KeyError, ValueError):
                continue
        if not items:
            break
        hi = lo - timedelta(days=1)
    return [out[k] for k in sorted(out)]


def session_day(ts_seconds):
    """Jour de séance d'un horodatage. La source encode minuit heure locale (UTC+1 → 23:00Z la veille)
    ou une heure de séance ; on évite toute dépendance à la base de fuseaux : ≥ 20:00Z = lendemain."""
    dt = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
    return (dt + timedelta(hours=4)).date() if dt.hour >= 20 else dt.date()


def index_history(symbol="MASI"):
    d = get_json("/api/live-market/indices/historical", {"symbol": symbol, "v": "4.0.0"})
    items = d.get("items", []) if isinstance(d, dict) else d
    rows = {}
    for it in items:
        t = it.get("time")
        if t is None:
            continue
        t = float(t)
        if t > 1e11:  # millisecondes
            t /= 1000
        day = session_day(t).isoformat()
        close = num(it.get("close"))
        if close:
            rows[day] = {"date": day, "close": close, "open": num(it.get("open")), "high": num(it.get("high")),
                         "low": num(it.get("low")), "volume": num(it.get("volume"))}
    return [rows[k] for k in sorted(rows)], (d.get("meta") if isinstance(d, dict) else None)


def live_snapshot():
    """Instantané officiel : actions, indice MASI, statut de séance."""
    s = drupal_settings(get_html("/live-market/actions")).get("live_market", {})
    idx = drupal_settings(get_html("/live-market/indices/cours?symbol=MASI")).get("live_market", {})
    session = idx.get("session") or s.get("session") or {}
    ts = session.get("timestamp")
    session_date = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(TZ).date().isoformat() if ts else None
    return {"actions": s.get("actions", []), "index": idx.get("index_data"), "session_status": session.get("status"),
            "session_date": session_date}
