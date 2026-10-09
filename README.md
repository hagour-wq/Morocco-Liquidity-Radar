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

## Source officielle des cours (depuis le 9 octobre 2026)

| Donnée | Service officiel (www.casablanca-bourse.com) | Profondeur | Champs | Script |
|---|---|---|---|---|
| Historique des actions | `/api/boursenova/stock-historical` (appelé par la page « Cours ») | ≈ 3 ans glissants, requêtes par fenêtres ≤ 1 an | séance, ouverture, plus haut, plus bas, dernier cours, titres échangés, montant MAD, nb transactions, capitalisation | `collect_equities.py` |
| Instantané et statut de séance | page `/live-market/actions` et `/live-market/indices/cours?symbol=MASI` (drupalSettings) | jour courant | 81 actions : secteur, compartiment, OHLC, variation, volume MAD, nombre de titres ; MASI, veille, plus haut / bas ; statut open/closed | `collect_market.py` |

- **TLS** : le serveur n'envoie pas son certificat intermédiaire. `certs/sectigo_public_server_auth_ca_dv_r36.pem` (Sectigo Public Server Authentication CA DV R36, SHA-256 `8C:54:C3:34:…:EF:22:E0`, expire en 2036) est ajouté au magasin certifi ; la vérification TLS reste active.
- **Cours bruts** : non ajustés des dividendes ni des opérations sur titres (`adj_close` = null). Les ruptures de type division du nominal sont détectées (`corporate_action_suspected`, ex. MNG le 27/07/2026) et bloquent tout score technique dont la fenêtre les traverse.
- **MASI** : aucune API ne fournit l'historique quotidien (le service `indices/historical` ne renvoie que l'intraday). La clôture officielle est enregistrée chaque soir, confirmée par la présence d'une cotation ATW ce jour-là. Les séances antérieures conservent leur source d'origine (`source`).
- **Univers** : 5 titres pilotes (ATW, BCP, IAM, MSA, MNG). `EQUITY_UNIVERSE=all` étend aux 81 actions cotées.
- Les scripts `backfill_equities*.py` (Yahoo, Investing, archives) ne sont plus exécutés quotidiennement : aucune de ces sources n'a produit de données validées.
