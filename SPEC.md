# TopoAudit-Benin: Intégration OCR Vision & Support Multi-Parcelles

Évolution du MVP pour remplacer l'OCR mock par une extraction réelle via Gemini Vision LLM et permettre la gestion de levées contenant plusieurs parcelles distinctes. Le projet inclut également la mise en place de tests frontend et la documentation technique standardisée.

## Objectifs
- Implémenter un moteur d'OCR basé sur Gemini Vision (gemini-2.5-flash) pour extraire coordonnées (UTM 31N) et surfaces.
- Permettre la sélection dynamique du fournisseur OCR (Mock, Azure, Gemini) via configuration.
- Développer la logique métier pour traiter et auditer plusieurs parcelles indépendantes au sein d'un même document.
- Garantir la fiabilité du frontend via des tests automatisés.
- Produire une documentation technique complète (OpenAPI et services externes).

## Périmètre
inclus: Extension du backend FastAPI pour le nouveau provider OCR et le modèle de données multi-parcelles.; Intégration de l'API Gemini dans le workflow d'upload.; Refonte de la logique d'audit pour traiter chaque parcelle séparément.; Mise à jour du rapport PDF (WeasyPrint) pour l'agrégation multi-parcelles.; Écriture de tests unitaires (avec mocks réseau) et tests frontend (apps/web).; Génération de la spec OpenAPI et de la doc des services externes.; exclus: Reconstruction de la stack existante.; Entraînement de modèles de Deep Learning propriétaires (utilisation de LLM existants).; Refonte complète de l'interface utilisateur (UI).

## Contraintes
- Stack technique imposée : FastAPI, Next.js, PostgreSQL/PostGIS, Shapely/pyproj, WeasyPrint.
- Système de coordonnées strict : UTM 31N / EPSG:32631.
- Format de données cible : Table de coordonnées (Borne/X/Y) et surface (ha/a/ca).
- Architecture : Monorepo dockerisé.
- Contrainte de test : Interdiction d'appels réseau réels lors de l'exécution des tests unitaires OCR.

## Hypothèses
- La clé API Gemini est déjà disponible et injectée dans les variables d'environnement.
- Le schéma de base de données actuel peut être étendu pour supporter une relation 1:N entre une levée et ses parcelles.
- Le modèle gemini-2.5-flash est capable de parser correctement les tableaux de coordonnées sur des scans de qualité moyenne.

## Critères d'acceptation
- [ ] L'OCR Gemini extrait avec succès au moins 95% des bornes et la surface correcte d'un plan test standard.
- [ ] Le sélecteur de provider dans la configuration permet de basculer entre Mock, Azure et Gemini sans crash.
- [ ] Un upload contenant deux groupes de coordonnées distincts génère deux objets 'parcelle' séparés en base de données.
- [ ] Le rapport PDF final affiche les audits et surfaces de chaque parcelle individuellement sans fusionner les géométries.
- [ ] La commande de test unitaire backend passe avec succès en utilisant des mocks pour les appels API Gemini/Azure.
- [ ] La suite de tests frontend (apps/web) s'exécute sans erreur sur l'environnement de CI.
- [ ] Le fichier docs/openapi.json est présent et correspond à l'implémentation réelle des endpoints.
- [ ] Le fichier docs/external_services est présent et détaille les endpoints et formats attendus de Gemini.
