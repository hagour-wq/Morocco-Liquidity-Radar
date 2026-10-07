# Morocco Liquidity Radar

V1 du radar de liquidité centré sur la Bourse de Casablanca.

## Objectif
Mesurer le régime de liquidité marocain et suivre la transmission : **BAM → taux/obligations → OPCVM/institutionnels → Bourse → secteurs → actions**.

## Principes
- Sources officielles prioritaires : Bank Al-Maghrib, AMMC, Bourse de Casablanca.
- Chaque donnée conserve sa date de référence et sa source.
- Une donnée absente reste absente : aucune estimation silencieuse.
- Les scores ne sont activés qu'après validation des séries et backtest.

## Architecture V1
- `index.html` : dashboard GitHub Pages.
- `data/dashboard.json` : état normalisé lu par l'interface.
- `update.py` : moteur de normalisation/scoring (progressif).
- `.github/workflows/update.yml` : actualisation automatique.

## Extensions prévues
CAC 40, S&P 500 et Nasdaq utiliseront la même architecture de marché.
