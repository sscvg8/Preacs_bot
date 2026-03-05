from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)

    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)

    # 'male' / 'female'
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    # 'male' / 'female' / 'all' - опционально, если None, показываем всех рандомно
    looking_for: Mapped[str | None] = mapped_column(String(10), nullable=True)

    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workplace: Mapped[str | None] = mapped_column(String(160), nullable=True)
    useful_for: Mapped[str | None] = mapped_column(String(400), nullable=True)
    bio: Mapped[str] = mapped_column(String(700), nullable=False)
    photo_id: Mapped[str | None] = mapped_column(String(300), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Связи (не обязателен eager-load, но удобно для навигации)
    likes_sent: Mapped[list["Like"]] = relationship(
        back_populates="from_user", foreign_keys="Like.from_user_id", cascade="all, delete-orphan"
    )
    likes_received: Mapped[list["Like"]] = relationship(
        back_populates="to_user", foreign_keys="Like.to_user_id", cascade="all, delete-orphan"
    )


class Like(Base):
    __tablename__ = "likes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # True = лайк, False = дизлайк
    is_like: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    from_user: Mapped["User"] = relationship(back_populates="likes_sent", foreign_keys=[from_user_id])
    to_user: Mapped["User"] = relationship(back_populates="likes_received", foreign_keys=[to_user_id])

    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_like_from_to"),
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user1_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user2_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Уникальность пары в одном направлении (мы будем сохранять упорядоченно: min, max)
        UniqueConstraint("user1_id", "user2_id", name="uq_match_pair"),
    )

