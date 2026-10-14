"""import_logs.status gains 'running' so a collector run is visible while it is in progress

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

OLD = "status IN ('ok','conflict','error','unreachable')"
NEW = "status IN ('running','ok','conflict','error','unreachable')"


def upgrade() -> None:
    op.drop_constraint("ck_import_logs_status", "import_logs", type_="check")
    op.create_check_constraint("ck_import_logs_status", "import_logs", NEW)


def downgrade() -> None:
    # Any in-flight rows would violate the old constraint; they are finished by definition.
    op.execute("UPDATE import_logs SET status = 'error' WHERE status = 'running'")
    op.drop_constraint("ck_import_logs_status", "import_logs", type_="check")
    op.create_check_constraint("ck_import_logs_status", "import_logs", OLD)
