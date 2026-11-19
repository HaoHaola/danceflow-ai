from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
