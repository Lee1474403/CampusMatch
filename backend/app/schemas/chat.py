from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.schemas.user import UserProfile


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class MessageOut(BaseModel):
    id: int
    match_id: int
    sender_id: int
    sender_nickname: str
    content: str
    is_read: bool
    sent_at: datetime


class ReadReceipt(BaseModel):
    updated: int


class BlockUserRequest(BaseModel):
    reason: Literal["疑似诈骗", "色情或不良信息", "血腥暴力内容", "骚扰", "其他"] = "其他"


class BlockUserResponse(BaseModel):
    blocked_user_id: int
    blocked: bool
    message: str


class BlockedUserOut(BaseModel):
    id: int
    user: UserProfile
    reason: str | None = None
    created_at: datetime
