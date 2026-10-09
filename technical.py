"""Indicateurs techniques et de liquidité — fonctions pures, sans dépendance externe.

Conventions :
- Les séries sont ordonnées de la plus ancienne à la plus récente.
- Un indicateur dont l'historique est insuffisant vaut None (jamais de valeur partielle).
- Les calculs ne traversent jamais une opération sur titres présumée : on n'utilise
  que le segment postérieur à la dernière séance signalée (cours bruts non ajustés).
"""
import math

TRADING_DAYS = 252


def sma(x, n):
    return sum(x[-n:]) / n if len(x) >= n else None


def ema_series(x, n):
    if len(x) < n:
        return []
    k = 2 / (n + 1)
    out = [sum(x[:n]) / n]
    for v in x[n:]:
        out.append(v * k + out[-1] * (1 - k))
    return out  # aligné sur x[n-1:]


def ret(x, n):
    return 100 * (x[-1] / x[-1 - n] - 1) if len(x) > n and x[-1 - n] else None


def rsi(x, n=14):
    """RSI de Wilder ; exige au moins 3n variations pour que le lissage soit stabilisé."""
    if len(x) < 3 * n + 1:
        return None
    d = [x[i] - x[i - 1] for i in range(1, len(x))]
    g = sum(max(v, 0) for v in d[:n]) / n
    l = sum(max(-v, 0) for v in d[:n]) / n
    for v in d[n:]:
        g = (g * (n - 1) + max(v, 0)) / n
        l = (l * (n - 1) + max(-v, 0)) / n
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


def macd(x, fast=12, slow=26, signal=9):
    """MACD, ligne de signal et histogramme ; exige slow + 3×signal séances."""
    if len(x) < slow + 3 * signal:
        return None
    ef, es = ema_series(x, fast), ema_series(x, slow)
    ef = ef[slow - fast:]
    line = [a - b for a, b in zip(ef, es)]
    sig = ema_series(line, signal)
    return {"macd": line[-1], "signal": sig[-1], "histogram": line[-1] - sig[-1]}


def realized_vol_annual(x, n=20):
    """Écart-type (échantillon) des rendements logarithmiques sur n séances, annualisé, en %."""
    if len(x) < n + 1:
        return None
    r = [math.log(x[i] / x[i - 1]) for i in range(len(x) - n, len(x))]
    m = sum(r) / n
    return 100 * math.sqrt(sum((v - m) ** 2 for v in r) / (n - 1)) * math.sqrt(TRADING_DAYS)


def atr(high, low, close, n=14):
    """ATR de Wilder ; exige des OHLC réels (aucune séance sans plus haut / plus bas)."""
    k = min(len(close), 3 * n + 1)  # fenêtre de calcul : 3n + 1 séances au plus, 2n + 1 au moins
    if k < 2 * n + 1:
        return None
    high, low, close = high[-k:], low[-k:], close[-k:]
    if any(v is None for v in high + low):
        return None
    tr = [max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])) for i in range(1, len(close))]
    a = sum(tr[:n]) / n
    for v in tr[n:]:
        a = (a * (n - 1) + v) / n
    return a


def bollinger(x, n=20, k=2):
    if len(x) < n:
        return None
    w = x[-n:]
    m = sum(w) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in w) / n)
    up, lo = m + k * sd, m - k * sd
    return {"middle": m, "upper": up, "lower": lo, "percent_b": (x[-1] - lo) / (up - lo) if up > lo else None,
            "bandwidth_pct": 100 * (up - lo) / m if m else None}


def support_resistance(high, low, n=20):
    """Méthode explicite : support = plus bas des n dernières séances, résistance = plus haut."""
    if len(high) < n or any(v is None for v in high[-n:] + low[-n:]):
        return None
    return {"support": min(low[-n:]), "resistance": max(high[-n:]), "window_sessions": n}


def mean_known(x, min_count):
    k = [v for v in x if v is not None]
    return sum(k) / len(k) if len(k) >= min_count else None


def liquidity(rows, n=60):
    """Profondeur : montant moyen échangé, titres moyens, séances sans échange.
    Un volume inconnu (None) est exclu des moyennes et compté à part ; il n'est jamais traité comme zéro."""
    w = rows[-n:]
    if len(w) < 20:
        return None
    turn = [r.get("turnover_mad") for r in w]
    vol = [r.get("volume") for r in w]
    zero = sum(1 for v in vol if v == 0)
    missing = sum(1 for v in vol if v is None)
    avg20 = mean_known(turn[-20:], 15)
    avg60 = mean_known(turn, 15)
    if avg20 is None:
        return None
    tier = "élevée" if avg20 >= 5e6 else "moyenne" if avg20 >= 1e6 else "faible"
    return {"avg_turnover_mad_20d": round(avg20), "avg_turnover_mad_60d": round(avg60) if avg60 is not None else None,
            "avg_shares_20d": round(mean_known(vol[-20:], 15)), "zero_volume_sessions": zero,
            "missing_volume_sessions": missing, "window_sessions": len(w),
            "tier": tier,
            "warning": " ; ".join(x for x in (
                "Liquidité faible : montant moyen < 1 M MAD/séance" if tier == "faible" else "",
                f"{zero} séance(s) sans échange sur {len(w)}" if zero else "") if x) or None}
