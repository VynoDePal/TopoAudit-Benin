"""baseline schema (users, projects+owner_id, documents, levees, parcels, survey_points, audit_inputs)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-22
"""

from alembic import op

from app.models import Base
from app.workflow import AUDIT_INPUTS_DDL

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Schéma de base, source de vérité = les modèles ORM + la table audit_inputs.

    geom (POINT/POLYGON) est déjà nullable et projects.owner_id présent dans les modèles,
    donc create_all produit directement le schéma cible (plus d'ALTER au runtime).
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind=bind)
    op.execute(AUDIT_INPUTS_DDL)


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP TABLE IF EXISTS audit_inputs")
    Base.metadata.drop_all(bind=bind)
