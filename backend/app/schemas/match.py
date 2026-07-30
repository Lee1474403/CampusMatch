from datetime import date, datetime

from pydantic import BaseModel, Field

from backend.app.schemas.user import PrivateProfile, UserProfile


class MatchingToggleRequest(BaseModel):
    enabled: bool


class HeartDecisionRequest(BaseModel):
    hearted: bool = True


class PairDetail(BaseModel):
    id: int
    status: str
    partner: UserProfile
    scheduled_date: date
    matched_at: datetime
    match_score: float = Field(ge=0, le=100)
    preliminary_score: float = Field(default=0, ge=0, le=100)
    deep_score: float | None = Field(default=None, ge=0, le=100)
    deep_comment: str | None = None
    deep_match_used: bool = False
    shared_interests: list[str] = Field(default_factory=list)
    my_hearted: bool
    partner_hearted: bool
    chat_enabled: bool
    chat_start_time: datetime | None = None
    last_message_time: datetime | None = None
    chat_days: int = 0
    unlock_progress: int = Field(default=0, ge=0, le=100)
    unlock_at: datetime | None = None
    privacy_unlocked: bool = False
    private_profile: PrivateProfile | None = None
    heartbeat_expires_at: datetime | None = None


class MatchingStatus(BaseModel):
    profile_complete: bool
    missing_profile_fields: list[str] = Field(default_factory=list)
    matching_enabled: bool
    has_active_pair: bool
    pair: PairDetail | None = None
    next_release_at: datetime
    server_time: datetime
    message: str


class MatchingToggleResponse(BaseModel):
    matching_enabled: bool
    message: str
    next_release_at: datetime


class HeartDecisionResponse(BaseModel):
    pair: PairDetail
    message: str


class MatchOut(BaseModel):
    id: int
    user: UserProfile
    status: str
    matched_at: datetime
    match_score: float = Field(default=0, ge=0, le=100)
    preliminary_score: float = Field(default=0, ge=0, le=100)
    deep_score: float | None = Field(default=None, ge=0, le=100)
    deep_comment: str | None = None
    deep_match_used: bool = False
    privacy_unlocked: bool = False
    private_profile: PrivateProfile | None = None
    chat_days: int = 0
    unlock_progress: int = 0
    unlock_at: datetime | None = None
    unread_count: int = 0
    last_message: str | None = None
    last_message_at: datetime | None = None
    online: bool = False
