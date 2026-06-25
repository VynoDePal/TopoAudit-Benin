# Contrôle territorial Bénin

## Objectif

Un levé peut être lisible et géométriquement cohérent mais, une fois **géoréférencé**,
tomber **hors du territoire béninois** (pays voisin, ou océan dans le golfe de Guinée).
Le contrôle territorial détecte ce cas **automatiquement, avant même l'affichage carte**,
pour alerter l'utilisateur sur une probable erreur de CRS / projection / saisie.

Module : `apps/api/app/territory_check.py` · Endpoint : `POST /api/territory/benin/check`
· Intégré à l'audit (`workflow.py`) et au rapport PDF.

## Source de la frontière

Natural Earth Admin 0 (1:50m), entité `BEN` — voir
[external_services/benin_boundary.md](external_services/benin_boundary.md). Contrôle
**grossier de prototype**, **non cadastral**.

## Statuts

| `status` | `risk_level` | Sens |
| --- | --- | --- |
| `inside_benin` | low | Tracé dans le Bénin (≥ 95 % de l'aire + centroïde dedans). |
| `near_border_partial` | high | Chevauche la frontière (partiellement hors). À vérifier. |
| `outside_benin` | critical | Entièrement hors Bénin (intersection nulle). |
| `not_applicable_local_crs` | not_applicable | CRS local/inconnu : contrôle impossible. |
| `invalid_geometry` | high | < 3 bornes ou polygone dégénéré. |

`covers` (et non `contains`) est utilisé pour accepter les points exactement sur la frontière.

## Statut NON juridique

Le contrôle est un **indice de cohérence**, jamais une preuve. Formulations :

- **Hors Bénin** : « Le tracé géoréférencé est hors du territoire béninois. Le levé est
  probablement mal géoréférencé, mal projeté ou incohérent avec le contexte Bénin. »
  → On ne dit **jamais** « fraude ».
- **CRS local/inconnu** : « Contrôle territorial impossible sans géoréférencement. »
  → On ne classe **pas** comme faux levé.

## Différencier les cas

- **Hors Bénin** : coordonnées géoréférencées valides mais qui tombent ailleurs (souvent
  un mauvais CRS, des axes X/Y inversés, ou une mauvaise zone UTM).
- **CRS incorrect** : sous-cas fréquent du « hors Bénin » — corriger le CRS/projection
  ramène souvent le tracé dans le Bénin.
- **Coordonnées locales** (`LOCAL_ONLY`) : repère relatif/chantier, non géoréférencé →
  contrôle **non applicable** (on ne transforme jamais un LOCAL_ONLY comme de l'UTM).
- **Fraude non prouvée** : un tracé hors Bénin peut résulter d'une simple erreur
  technique. Le contrôle **signale un risque**, il ne **prouve** rien — la décision reste
  humaine et juridique.

## Limites

- Frontière simplifiée (1:50m) → imprécision near-border de l'ordre de quelques centaines
  de mètres ; un tracé très proche de la frontière peut être classé `near_border_partial`.
- Contrôle **2D** WGS84, sans tolérance topographique fine.
- Pour la production : frontière officielle + seuils à calibrer.
- L'OCR et le géoréférencement restent soumis à **validation humaine obligatoire**.
