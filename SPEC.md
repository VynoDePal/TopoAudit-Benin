# TopoAudit Bénin Prototype

Développement d'un prototype SaaS dockerisé pour l'audit préliminaire de risques fonciers au Bénin à partir de plans topographiques scannés. Le système automatise l'extraction OCR, la validation géométrique et la génération de rapports de risque technique sans valeur juridique.

## Objectifs
- Implémenter un flux end-to-end : Upload -> OCR -> Validation humaine -> Calcul géométrique -> Audit -> Rapport PDF.
- Développer des parsers robustes pour les surfaces (ha/are/ca) et les coordonnées variables.
- Automatiser la détection de CRS et la conversion géospatiale (EPSG:32631 vers EPSG:4326).
- Calculer des scores de risque basés sur la cohérence technique et l'extraction.
- Fournir une API FastAPI documentée et une interface Next.js interactive avec visualisation cartographique.

## Périmètre
inclus: Monorepo (FastAPI/Next.js), Docker Compose, OCR (Azure + Mock fallback), Moteur géométrique (Shapely), Gestion de fichiers (max 25Mo), Export PDF (WeasyPrint/ReportLab), Base de données PostGIS.; exclus: Verdict juridique, Scraping de Cadastre.bj (utilisation d'un provider uniquement), Gestion de rôles complexes, Stockage cloud public.

## Contraintes
- Stack technique stricte : Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL/PostGIS, Next.js, TypeScript, MapLibre GL JS.
- Sécurité : Pas de clés API hardcodées, rate limiting, isolation des fichiers par projet, pas de logging de secrets.
- Format de sortie GeoJSON : Strictement EPSG:4326 avec ordre [longitude, latitude].
- Limites de fichiers : Documents JPG/PNG/PDF limités à 25 Mo.
- Interdiction de scraping direct de Cadastre.bj.

## Hypothèses
- L'utilisateur effectue obligatoirement la validation humaine des coordonnées avant tout calcul.
- Le fallback OCR Mock est utilisé par défaut si aucune clé Azure n'est configurée.
- Le stockage des documents est local et isolé par projet au sein du conteneur.
- La visualisation cartographique utilise MapLibre avec des tuiles standards (OSM/Esri/Google).

## Critères d'acceptation
- [ ] Le déploiement via `docker compose up --build` est fonctionnel et expose l'API et le Frontend.
- [ ] L'exécution de `pytest` (backend) et des tests frontend (npm test) est totalement réussie.
- [ ] Le parser `parse_surface_to_m2` convertit correctement '05a 49ca' en 549 et '29ha 95a 38ca' en 299538.
- [ ] Le système détecte correctement l'EPSG:32631 et propose une inversion X/Y si les coordonnées sont permutées.
- [ ] L'écart de surface est classé selon les seuils : $\le 2m^2$ (faible), $\le 5\%$ (modéré), $> 5\%$ (élevé).
- [ ] Le rapport PDF généré contient l'avertissement de non-responsabilité juridique et les scores de risque.
- [ ] Le système traite avec succès les 7 cas de test : image nette WGS84, image floue, coordonnées locales, écart de surface, polygone auto-intersecté, inversion X/Y, et multi-parcelles.
