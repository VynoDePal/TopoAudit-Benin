# Cadastre Bénin — ANDF (référence cadastrale officielle)

## Usage prévu
Référence cadastrale officielle (ANDF — Agence Nationale du Domaine et du Foncier ;
portail Cadastre.bj) à laquelle on **souhaiterait** comparer un levé pour confirmer
l'emprise/les limites. **Non intégré** dans le prototype : l'audit est PRÉLIMINAIRE et
ne compare PAS le levé à une référence cadastrale officielle.

## Endpoints / API
- **Aucune API publique documentée confirmée** à ce jour pour une comparaison
  automatisée des parcelles (TF/QIP) via ANDF/Cadastre.bj.
- Le portail Cadastre.bj est principalement une consultation web ; toute intégration
  nécessiterait une convention/accès officiel avec l'ANDF.
- Tant qu'aucun accès officiel n'est établi, l'audit affiche explicitement
  « Aucune comparaison cadastrale officielle effectuée ».

## Variables d'environnement
| Variable | Rôle |
|---|---|
| `ANDF_API_BASE_URL` | (réservé) base d'une future API ANDF — non utilisée |
| `ANDF_API_KEY` | (réservé) credential officiel — non utilisé |

## Limites
- Pas de vérification automatique TF/QIP ni de superposition cadastrale officielle.
- Le levé n'est pas confronté à la matrice cadastrale ; l'audit reste indicatif.

## Risques légaux / conformité
- **Ne pas** présenter l'audit comme une certification juridique ou un titre foncier.
- Toute intégration future doit passer par un accord officiel avec l'ANDF et respecter
  la réglementation foncière béninoise (données personnelles et foncières sensibles).
- Recommandation produit : vérifier le TF/QIP et demander un extrait cadastral officiel
  avant toute transaction.
