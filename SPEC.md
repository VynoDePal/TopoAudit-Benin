# TopoAudit-Benin Prototype Hardening

Mission de durcissement du prototype SaaS TopoAudit-Benin pour préparer une démonstration réelle. L'objectif est de transformer le prototype en une version fiable, vérifiable et cohérente sans ajouter de nouvelles fonctionnalités.

## Objectifs
- Standardiser la configuration du modèle Gemini (gemma-4-31b-it) sur l'ensemble de la stack
- Sécuriser et fiabiliser la logique de fallback OCR selon l'environnement (local vs staging/prod)
- Garantir la synchronisation parfaite entre le code FastAPI et la documentation OpenAPI
- Remplacer les scores d'audit statiques par un moteur de calcul dynamique basé sur les données extraites
- Renforcer la validation des uploads de fichiers (taille et type)
- Documenter le projet et les services externes pour permettre un onboarding rapide (< 15 min)
- Mettre en place un framework d'évaluation automatisé de la précision OCR

## Périmètre
inclus: Alignement config Gemini, logique de fallback OCR, génération/validation OpenAPI, moteur de calcul de score, validation upload, README racine, dataset de test/script d'évaluation, documentation des services externes.; exclus: Développement de nouvelles fonctionnalités métier, refonte de l'interface utilisateur (UI), migration de base de données majeure, intégration de nouveaux fournisseurs OCR.

## Contraintes
- Modèle par défaut obligatoire : gemma-4-31b-it
- Interdiction de fallback silencieux en staging/production (erreur 503 requise)
- Interdiction de logger les clés API
- Aucun appel réseau autorisé lors de l'exécution des tests OCR
- Respect strict de la stack : FastAPI, Next.js, PostgreSQL/PostGIS, Gemini Vision

## Hypothèses
- L'environnement APP_ENV est correctement injecté via Docker/CI
- Les données nécessaires au calcul du score (coordonnées, surface, CRS) sont présentes dans les résultats OCR
- Le développeur dispose d'un environnement Docker et Node/Python fonctionnel

## Critères d'acceptation
- [ ] La commande 'docker compose up' lance avec succès la DB, l'API et le Web sans erreur
- [ ] L'exécution de 'pytest' et 'npm test/build' renvoie un code de sortie 0
- [ ] Le fichier 'docs/openapi.json' contient les endpoints obligatoires et passe le test de synchronisation avec FastAPI
- [ ] En mode staging/production, l'absence de credentials OCR provoque une erreur HTTP 503 explicite
- [ ] La réponse JSON de l'OCR contient les champs 'configured_provider', 'actual_provider' et 'is_mock_result'
- [ ] Le score d'audit varie dynamiquement en fonction de la qualité des données extraites (plus de valeur codée en dur)
- [ ] Un fichier dépassant 'MAX_UPLOAD_MB' ou d'un type non autorisé (hors PDF/PNG/JPG/JPEG) est rejeté avec une erreur API propre
- [ ] Un nouveau développeur peut lancer la démo complète en suivant le README en moins de 15 minutes
- [ ] Le script 'apps/api/scripts/evaluate_ocr.py' valide le dataset de test sans erreur
