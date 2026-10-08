# Equity Bourse — sources et règles de classement (V1)

## Sources prioritaires
- AMMC, états financiers des émetteurs: https://www.ammc.ma/fr/liste-etats-financiers-emetteurs
- AMMC, communiqués des émetteurs: https://www.ammc.ma/fr/communiques-presse-emetteurs
- Bourse de Casablanca, publications des émetteurs: https://www.casablanca-bourse.com/fr/publications-des-emetteurs
- Bourse de Casablanca, éditions statistiques et résumés de séance: https://www.casablanca-bourse.com/market-data/editions-statistiques

## Long terme
Renseigner **data/company_fundamentals.json** par émetteur : ticker, nom, secteur, date de référence, URL du rapport et prix, BPA, valeur comptable par action, ROE, croissance du CA, dette nette/EBITDA, dividende par action. Chaque chiffre doit venir d'un rapport vérifiable et compatible avec la période de référence. Le prix doit être daté et cohérent avec l'historique. Ne pas mélanger le BPA annuel avec une période trimestrielle. Exclure les banques et assurances avant ajout d'un modèle sectoriel approprié. Les résultats V1 ne sont pas des projections de rendement.

## Court terme
Renseigner **data/equity_history.json** avec companies: [{ticker,name,rows:[{date,close,volume}]}]. Au moins 25 séances ordonnées et sans grandes interruptions, avec prix et volumes positifs. Ne pas substituer un volume de valeur à un volume de marché; uniformiser les unités et ajustements historiques. La volatilité mesure le risque observé, pas une probabilité de gain.

## Garde-fous
Toute valeur non vérifiée, absente ou périmée reste non classée. **data/equity_rankings.json** affiche séparément les résultats admissibles, les exclus et une watchlist basée sur un seul instantané. Le classement relatif n'est jamais un rendement futur attendu; des backtests hors échantillon, frais, spread, liquidité du carnet et tests de robustesse restent nécessaires avant toute conclusion d'investissement.
