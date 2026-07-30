"""Initial CampusMatch schema."""

from alembic import op

from backend.app.core.database import Base
from backend.app.models import entities  # noqa: F401


revision = "20260728_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
