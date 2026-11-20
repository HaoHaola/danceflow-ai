from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    __table_args__ = (
        Index("ix_training_plans_user_id_id", "user_id", "id"),
        CheckConstraint("level IN ('beginner', 'intermediate', 'advanced')", name="ck_training_plans_level"),
        CheckConstraint(
            "JSON_TYPE(goals) = 'ARRAY' AND JSON_LENGTH(goals) BETWEEN 1 AND 10",
            name="ck_training_plans_goals",
        ),
        {"mysql_engine": "InnoDB"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", name="fk_training_plans_user"))
    title: Mapped[str] = mapped_column(String(120))
    dance_style: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(12))
    goals: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=text("CURRENT_TIMESTAMP"))
    sessions: Mapped[list["TrainingSession"]] = relationship(
        back_populates="plan", order_by="TrainingSession.position"
    )


class TrainingSession(Base):
    __tablename__ = "training_sessions"
    __table_args__ = (
        UniqueConstraint("plan_id", "position", name="uq_training_sessions_plan_position"),
        CheckConstraint("position BETWEEN 0 AND 27", name="ck_training_sessions_position"),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_training_sessions_day"),
        CheckConstraint("duration_minutes > 0", name="ck_training_sessions_duration"),
        {"mysql_engine": "InnoDB"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("training_plans.id", name="fk_training_sessions_plan")
    )
    position: Mapped[int]
    day_of_week: Mapped[int]
    duration_minutes: Mapped[int]
    focus: Mapped[str] = mapped_column(String(120))
    instructions: Mapped[str] = mapped_column(String(1000))
    plan: Mapped[TrainingPlan] = relationship(back_populates="sessions")
