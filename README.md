# Equity Bourse · Morocco Liquidity Radar

Terminal de recherche centré sur la transmission de la liquidité vers la Bourse de Casablanca.

## Chaîne d'analyse
**BAM → marché monétaire → obligations → OPCVM → actions → MASI → secteurs → valeurs**

## État fonctionnel
- Historique MASI et graphique.
- Market Flow Score à données partielles, avec couverture et niveau de confiance.
- Momentum 1D / 5D / 20D et drawdown.
- Breadth et volume intégrés uniquement lorsqu'ils existent.
- Rotation sectorielle, leaders, baisses et valeurs actives.
- Backtest directionnel 1D / 5D / 10D, marqué expérimental tant que l'échantillon est court.
- Framework Liquidity Score : OPCVM AMMC, liquidité bancaire, marché monétaire, taux directeur.
- MLR Composite : 50% Liquidity / 35% Market Flow / 15% Global, activé en régime uniquement à couverture suffisante.
- Traçabilité des sources et dates de référence.
- GitHub Actions quotidien + GitHub Pages.

## Politique de données
1. Source officielle prioritaire : Bank Al-Maghrib, AMMC, Bourse de Casablanca.
2. Une source secondaire peut alimenter une série lorsqu'elle est explicitement identifiée comme telle.
3. Une donnée manquante reste `null`.
4. Volume ≠ flux net.
5. Variation d'actif OPCVM ≠ souscription nette sans correction de l'effet marché.
6. Aucun score ne doit créer une fausse précision à partir d'une donnée absente.

## Fichiers
- `index.html` : terminal web autonome.
- `data/dashboard.json` : état normalisé.
- `data/market_history.json` : historique de marché traçable.
- `update.py` : moteur Market Flow + composite.
- `backtest.py` : diagnostic historique reproductible.
- `collect_market.py` : collecteur quotidien fail-closed.
- `.github/workflows/update.yml` : recalcul quotidien.

## Limites actuelles
Le Liquidity Score complet reste en calibration tant que les agrégats OPCVM par classe et les séries BAM 2026 ne sont pas normalisés. Le backtest disponible est trop court pour être interprété comme validation d'une stratégie.

## Extension
La même architecture pourra accueillir CAC 40, S&P 500 et Nasdaq après stabilisation du module Maroc.
