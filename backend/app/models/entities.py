from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class UserInterest(Base):
    __tablename__ = "user_interests"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    interest_id: Mapped[int] = mapped_column(ForeignKey("interests.id", ondelete="CASCADE"), primary_key=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("gender IN ('male', 'female')", name="ck_users_gender"),
        Index("ix_users_gender_active", "gender", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nickname: Mapped[str] = mapped_column(String(40), index=True)
    real_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gender: Mapped[str] = mapped_column(String(8), index=True)
    birth_date: Mapped[date] = mapped_column(Date)
    school: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department: Mapped[str | None] = mapped_column(String(80), nullable=True)
    grade: Mapped[str] = mapped_column(String(24))
    location_province: Mapped[str | None] = mapped_column(String(40), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(40), nullable=True)
    hometown_province: Mapped[str | None] = mapped_column(String(40), nullable=True)
    hometown_city: Mapped[str | None] = mapped_column(String(40), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    real_photos: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    wechat: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_matching_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    matching_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_like_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    daily_like_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    interests: Mapped[list["Interest"]] = relationship(
        secondary="user_interests", back_populates="users", lazy="selectin"
    )


class Interest(Base):
    __tablename__ = "interests"
    __table_args__ = (Index("ix_interests_category_order", "category", "sort_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    emoji: Mapped[str] = mapped_column(String(8), default="✨")
    category: Mapped[str] = mapped_column(String(30), default="其他", server_default="其他")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    users: Mapped[list[User]] = relationship(
        secondary="user_interests", back_populates="interests", lazy="selectin"
    )


class QuestionnaireQuestion(Base):
    __tablename__ = "questionnaire_questions"
    __table_args__ = (Index("ix_questionnaire_questions_active_order", "is_active", "sort_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    dimension: Mapped[str] = mapped_column(String(40), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list, server_default="[]")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class QuestionnaireAnswer(Base):
    __tablename__ = "questionnaire_answers"
    __table_args__ = (Index("ix_questionnaire_answers_user", "user_id"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questionnaire_questions.id", ondelete="CASCADE"), primary_key=True
    )
    answer_key: Mapped[str] = mapped_column(String(1))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_like_direction"),
        CheckConstraint("status IN ('liked', 'skipped', 'matched')", name="ck_likes_status"),
        Index("ix_likes_to_status", "to_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="liked")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("user1_id < user2_id", name="ck_match_order"),
        CheckConstraint(
            "status IN ('pending_heartbeat', 'chatting', 'privacy_unlocked', 'dissolved')",
            name="ck_matches_status",
        ),
        Index("ix_matches_status_date", "status", "scheduled_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user1_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user2_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scheduled_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending_heartbeat", server_default="pending_heartbeat")
    user1_hearted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    user2_hearted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    match_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    preliminary_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    deep_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    deep_comment: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deep_match_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    shared_interests: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    mutual_hearted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chat_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user1_last_message_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user2_last_message_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    privacy_unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dissolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dissolve_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)

    user1: Mapped[User] = relationship(foreign_keys=[user1_id], lazy="selectin")
    user2: Mapped[User] = relationship(foreign_keys=[user2_id], lazy="selectin")
    messages: Mapped[list["Message"]] = relationship(back_populates="match", cascade="all, delete-orphan")


class WeeklyRecommendation(Base):
    __tablename__ = "weekly_recommendations"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "week_start", "rank", name="uq_weekly_recommendation_rank"),
        UniqueConstraint(
            "owner_user_id",
            "candidate_user_id",
            "week_start",
            name="uq_weekly_recommendation_candidate",
        ),
        CheckConstraint("owner_user_id != candidate_user_id", name="ck_weekly_recommendations_not_self"),
        CheckConstraint("rank BETWEEN 1 AND 3", name="ck_weekly_recommendations_rank"),
        Index("ix_weekly_recommendations_owner_week", "owner_user_id", "week_start"),
        Index("ix_weekly_recommendations_candidate_week", "candidate_user_id", "week_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    candidate_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    rank: Mapped[int] = mapped_column(Integer)
    preliminary_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    deep_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    selection_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    repeat_penalty: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    deep_comment: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deep_match_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    shared_interests: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped[User] = relationship(foreign_keys=[owner_user_id], lazy="selectin")
    candidate: Mapped[User] = relationship(foreign_keys=[candidate_user_id], lazy="selectin")


class WeeklyRecommendationRun(Base):
    __tablename__ = "weekly_recommendation_runs"
    __table_args__ = (
        UniqueConstraint("week_start", "batch_index", name="uq_weekly_recommendation_run_batch"),
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_weekly_recommendation_runs_status"),
        Index("ix_weekly_recommendation_runs_week_status", "week_start", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    batch_index: Mapped[int] = mapped_column(Integer)
    batch_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="running", server_default="running")
    eligible_user_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    recommendation_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    deep_calls_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block_direction"),
        CheckConstraint("blocker_id != blocked_id", name="ck_user_blocks_not_self"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    blocker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    blocked_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    blocker: Mapped[User] = relationship(foreign_keys=[blocker_id], lazy="selectin")
    blocked: Mapped[User] = relationship(foreign_keys=[blocked_id], lazy="selectin")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_match_sent", "match_id", "sent_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    match: Mapped[Match] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship(lazy="selectin")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(String(255))
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchingRun(Base):
    __tablename__ = "matching_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    candidates_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pairs_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
