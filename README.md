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
- **Univers** : toutes les actions de la liste officielle (81 au 9 octobre 2026), validé d'abord sur 5 titres pilotes (ATW, BCP, IAM, MSA, MNG). `EQUITY_UNIVERSE=pilot` restreint aux pilotes.
- **Stockage** : `data/equities/<TICKER>.json`, une séance par ligne, provenance au niveau du fichier, `collected_at` par séance ; `data/equities/index.json` résume la couverture. Collecte incrémentale (45 derniers jours) une fois l'historique constitué ; `EQUITY_FULL_REFRESH=1` force un rechargement complet.
- Les scripts `backfill_equities*.py` (Yahoo, Investing, archives) ne sont plus exécutés quotidiennement : aucune de ces sources n'a produit de données validées.

## Méthodologie — analyse technique court terme (`technical.py`, `rank_equities.py`)

| Indicateur | Définition | Historique minimal |
|---|---|---|
| Variation 5J / 20J / 60J | (clôture / clôture n séances avant − 1) × 100 | n + 1 séances |
| MM20 / MM50 / MM200 | moyenne arithmétique des clôtures | 20 / 50 / 200 séances |
| RSI 14 | lissage de Wilder (vérifié identique à pandas `ewm(alpha=1/14)`) | 43 séances |
| MACD 12/26/9 | EMA12 − EMA26, signal EMA9 | 53 séances |
| Volatilité réalisée | écart-type (échantillon) des rendements log sur 20 séances × √252 | 21 séances |
| ATR 14 | true range lissé de Wilder, OHLC réels uniquement | 29 séances |
| Bollinger 20/2 | MM20 ± 2 écarts-types, %B et largeur | 20 séances |
| Support / résistance | plus bas / plus haut des 20 dernières séances | 20 séances |
| Liquidité | montant moyen échangé 20 j et 60 j, séances sans échange | 20 séances |

Un indicateur dont l'historique est insuffisant vaut `null` et figure dans `unavailable`.

**Score technique /100** : momentum 5 séances 35 %, 20 séances 25 %, position clôture / MM50 20 % (MM20 si moins de 50 séances), volume relatif 10 %, volatilité annualisée 10 % (inverse). Chaque composante est ramenée linéairement sur 0–100 entre des bornes fixes (5J : ±8 % ; 20J : ±15 % ; clôture / MM : 0,9–1,1 ; volume relatif : 0,5–2 ; volatilité : 10–60 %).

**Catégories**
- *Éligible* : score calculé, montant moyen 20 j ≥ 1 M MAD, aucune séance sans échange sur 60 j.
- *À surveiller* : score calculé mais liquidité faible ou séances sans échange.
- *Non analysable* : moins de 25 séances (après toute opération sur titres présumée), données de plus de 5 jours, trou de cotation, anomalie dans la fenêtre, ou volume de la dernière séance inconnu.

**Volumes** : une séance sans échange (aucun OHLC, cours de référence reporté) a un volume de 0. Un enregistrement incomplet de la source (plus haut / plus bas publiés mais volume 0, ex. 17/09/2026) a un volume `null`, exclu des moyennes et jamais compté comme zéro.

## Backtest du score technique (`backtest_technical.py`, `data/technical_backtest.json`)

- **Sans regard vers le futur** : à chaque date de rebalancement, `evaluate_technical(..., as_of=t)` ne voit que les séances ≤ t (test `test_score_ignores_sessions_after_as_of`).
- **Portefeuille** : 10 meilleures valeurs éligibles (liquidité ≥ 1 M MAD/séance), équipondérées, achetées à la clôture de la séance suivante, détenues 5, 10 ou 20 séances. Aucune période sautée.
- **Frais** : 0,6 % par aller simple (hypothèse courtage + commission Bourse + TVA), appliqués à la rotation effective.
- **Références** : univers éligible équipondéré ; proxy MASI pondéré par la capitalisation publiée (corrélation 0,994 avec les clôtures MASI disponibles).
- **Analyse par quintiles** : écart Q1 − Q5 avant frais et t-stat, pour mesurer l'information du score indépendamment des frais.
- **Calendrier** : tolérance de 7 jours calendaires entre séances (fermetures légales observées jusqu'à 6 jours).
- **Limites** : rendements de prix (dividendes exclus), biais de survivance (titres cotés au 09/10/2026), ~2,7 ans d'historique, plusieurs horizons présentés côte à côte (biais de sélection si l'on retient le meilleur a posteriori). Performances passées : elles ne préjugent pas des performances futures.

## Historique officiel du MASI (`collect_masi_history.py`, workflow « Historique officiel du MASI »)

- **Source** : « Résumés de séance » PDF publiés sur `/market-data/editions-statistiques` (archive depuis le 01/08/2016, ~2 500 documents).
- **Extraits** : clôture du MASI, performance journalière publiée, montant du marché central actions (`volume_mad`), montant global, hausses / baisses (`breadth`).
- **Contrôles** : date du fichier = date imprimée ; MASI(t)/MASI(t−1) − 1 ≈ performance publiée (≤ 0,02 point), sauf si la séance précédente manque dans l'archive (`previous_session_missing_in_archive`, calendrier tiré des cotations ATW) ; valeurs douteuses non fusionnées et listées dans `data/masi_history_report.json`.
- **Reprise** : `data/masi_official.json` mémorise la liste des PDF et les séances lues ; chaque exécution lit au plus 700 PDF en 25 minutes, les plus récents d'abord. Exécution quotidienne à 20:00 UTC.
- **Fusion** : `data/market_history.json` reçoit le MASI officiel (`masi_source`), le montant du marché central et la largeur du marché ; toute valeur antérieure divergente (> 0,05 %) est journalisée dans `corrections`.

## Référentiel émetteurs (`collect_bulletin.py`, `data/issuer_reference.json`)

- **Source** : dernier « Bulletin de la cote » PDF (`/market-data/bulletins-de-la-cote`).
- **Par action** : ISIN, nombre de titres, nominal, code secteur, dernier dividende ajusté (montant, exercice, date de détachement), cours de référence.
- **Rapprochement** : nombre de titres identique à `nombreTitres` de la liste officielle (départage par le cours si deux titres ont le même nombre de titres) ; contrôle d'écart de cours. Essai sur le bulletin du 05/10/2026 : 81 actions sur 81 rapprochées.
- **Rendement du dividende** : dernier dividende détaché / dernier cours, uniquement si le détachement date de moins de 15 mois.
