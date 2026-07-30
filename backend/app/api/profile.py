from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.security import hash_password, verify_password
from backend.app.models.entities import Interest, Match, User
from backend.app.schemas.auth import ChangePasswordRequest
from backend.app.schemas.user import InterestOut, OwnProfile, ProfileUpdate, UserProfile
from backend.app.services.pairing import ACTIVE_PAIR_STATUSES
from backend.app.services.users import is_profile_complete, own_profile_from_user, profile_from_user


router = APIRouter(tags=["资料"])


async def read_valid_image(upload: UploadFile, max_bytes: int, label: str) -> tuple[bytes, str]:
    allowed = {"image/jpeg": ".jpg", "image/png": ".png"}
    if upload.content_type not in allowed:
        raise HTTPException(status_code=415, detail=f"{label}仅支持 JPG 或 PNG")
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{label}文件过大")
    if not content:
        raise HTTPException(status_code=422, detail=f"{label}文件为空")
    is_jpeg = upload.content_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff")
    is_png = upload.content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n")
    if not (is_jpeg or is_png):
        raise HTTPException(status_code=415, detail=f"文件内容不是有效的 JPG 或 PNG {label}")
    return content, allowed[upload.content_type]


@router.get("/interests", response_model=list[InterestOut])
async def list_interests(
    _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[InterestOut]:
    interests = (await db.scalars(select(Interest).order_by(Interest.sort_order, Interest.id))).all()
    return [InterestOut.model_validate(item) for item in interests]


@router.get("/profile/me", response_model=OwnProfile)
async def get_my_profile(user: User = Depends(get_current_user)) -> OwnProfile:
    return own_profile_from_user(user)


@router.patch("/profile/me", response_model=OwnProfile)
async def update_my_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OwnProfile:
    values = payload.model_dump(exclude_unset=True, exclude={"interest_ids"})
    if "email" in values and values["email"]:
        values["email"] = str(values["email"]).lower()
    if "phone" in values or "email" in values:
        conditions = []
        if values.get("phone"):
            conditions.append(User.phone == values["phone"])
        if values.get("email"):
            conditions.append(User.email == values["email"])
        if conditions:
            conflict = await db.scalar(select(User).where(User.id != user.id, or_(*conditions)))
            if conflict:
                raise HTTPException(status_code=409, detail="手机号或邮箱已被其他账号使用")
    for field, value in values.items():
        setattr(user, field, value)

    if payload.interest_ids is not None:
        unique_ids = list(dict.fromkeys(payload.interest_ids))
        if len(unique_ids) > 12:
            raise HTTPException(status_code=422, detail="最多选择 12 个兴趣标签")
        interests = (await db.scalars(select(Interest).where(Interest.id.in_(unique_ids)))).all() if unique_ids else []
        if len(interests) != len(unique_ids):
            raise HTTPException(status_code=422, detail="包含不存在的兴趣标签")
        user.interests = list(interests)

    if not is_profile_complete(user):
        user.is_matching_enabled = False
        user.matching_enabled_at = None

    await db.commit()
    await db.refresh(user, attribute_names=["interests"])
    return own_profile_from_user(user)


@router.post("/profile/avatar", response_model=OwnProfile)
async def upload_avatar(
    avatar: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OwnProfile:
    content, extension = await read_valid_image(avatar, settings.max_avatar_bytes, "头像")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{user.id}-{uuid4().hex}{extension}"
    path = settings.upload_dir / filename
    path.write_bytes(content)
    previous = user.avatar_url
    user.avatar_url = f"/uploads/{filename}"
    await db.commit()
    if previous and previous.startswith("/uploads/"):
        previous_path = settings.upload_dir / Path(previous).name
        if previous_path.exists() and previous_path != path:
            previous_path.unlink(missing_ok=True)
    return own_profile_from_user(user)


@router.post("/profile/real-photos", response_model=OwnProfile)
async def upload_real_photos(
    photos: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OwnProfile:
    existing = list(user.real_photos or [])
    if not photos:
        raise HTTPException(status_code=422, detail="请选择至少一张真实照片")
    if len(existing) + len(photos) > settings.max_real_photos:
        raise HTTPException(status_code=422, detail=f"真实照片最多上传 {settings.max_real_photos} 张")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    created_paths: list[Path] = []
    try:
        for photo in photos:
            content, extension = await read_valid_image(photo, settings.max_real_photo_bytes, "真实照片")
            filename = f"real-{user.id}-{uuid4().hex}{extension}"
            path = settings.upload_dir / filename
            path.write_bytes(content)
            created_paths.append(path)
            existing.append(f"/uploads/{filename}")
    except Exception:
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise
    user.real_photos = existing
    await db.commit()
    return own_profile_from_user(user)


@router.delete("/profile/real-photos", response_model=OwnProfile)
async def delete_real_photo(
    url: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OwnProfile:
    photos = list(user.real_photos or [])
    if url not in photos:
        raise HTTPException(status_code=404, detail="照片不存在")
    photos.remove(url)
    user.real_photos = photos
    await db.commit()
    if url.startswith("/uploads/real-"):
        path = settings.upload_dir / Path(url).name
        path.unlink(missing_ok=True)
    return own_profile_from_user(user)


@router.post("/profile/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return {"message": "密码已修改"}


@router.get(
    "/users/{user_id}",
    response_model=UserProfile,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
async def get_user_profile(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    target = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == current_user.id:
        return profile_from_user(target)
    if target.gender == current_user.gender:
        return profile_from_user(target, full=False)
    pair = sorted((target.id, current_user.id))
    matched = await db.scalar(
        select(Match.id).where(
            Match.user1_id == pair[0],
            Match.user2_id == pair[1],
            Match.status.in_(ACTIVE_PAIR_STATUSES),
        )
    )
    if not matched:
        raise HTTPException(status_code=403, detail="仅可通过推荐查看候选资料，配对后可再次访问完整主页")
    return profile_from_user(target)
