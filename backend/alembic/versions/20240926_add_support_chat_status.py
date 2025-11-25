"""add support chat status table

Revision ID: 20240926_add_support_chat_status
Revises: 
Create Date: 2024-09-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240926_add_support_chat_status"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_chat_statuses",
        sa.Column("conversation_id", sa.String(length=128), primary_key=True),
        sa.Column("peer_user_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("updated_by_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_support_chat_statuses_peer_user_id", "support_chat_statuses", ["peer_user_id"], unique=False)
    op.create_index("ix_support_chat_statuses_status", "support_chat_statuses", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_support_chat_statuses_status", table_name="support_chat_statuses")
    op.drop_index("ix_support_chat_statuses_peer_user_id", table_name="support_chat_statuses")
    op.drop_table("support_chat_statuses")
