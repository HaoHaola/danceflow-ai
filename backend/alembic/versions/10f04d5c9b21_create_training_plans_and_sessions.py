"""Create training plans and sessions."""

from alembic import op
import sqlalchemy as sa


revision = "10f04d5c9b21"
down_revision = "472cb4adbf8b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("dance_style", sa.String(64), nullable=False),
        sa.Column("level", sa.String(12), nullable=False),
        sa.Column("goals", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_training_plans_user"),
        sa.CheckConstraint("level IN ('beginner', 'intermediate', 'advanced')", name="ck_training_plans_level"),
        sa.CheckConstraint(
            "JSON_TYPE(goals) = 'ARRAY' AND JSON_LENGTH(goals) BETWEEN 1 AND 10",
            name="ck_training_plans_goals",
        ),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_training_plans_user_id_id", "training_plans", ["user_id", "id"])
    op.create_table(
        "training_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("focus", sa.String(120), nullable=False),
        sa.Column("instructions", sa.String(1000), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["training_plans.id"], name="fk_training_sessions_plan"),
        sa.UniqueConstraint("plan_id", "position", name="uq_training_sessions_plan_position"),
        sa.CheckConstraint("position BETWEEN 0 AND 27", name="ck_training_sessions_position"),
        sa.CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_training_sessions_day"),
        sa.CheckConstraint("duration_minutes > 0", name="ck_training_sessions_duration"),
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    op.drop_table("training_sessions")
    op.drop_table("training_plans")
