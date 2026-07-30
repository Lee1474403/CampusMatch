from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "CampusMatch"
    environment: str = "development"
    secret_key: str = "development-only-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    database_url: str = "sqlite+aiosqlite:///./campusmatch.db"
    frontend_url: str = "http://localhost:5173"
    seed_demo_data: bool = True
    upload_dir: Path = BASE_DIR / "backend" / "uploads"
    max_avatar_bytes: int = 2 * 1024 * 1024
    max_real_photo_bytes: int = 5 * 1024 * 1024
    max_real_photos: int = 6
    daily_like_limit: int = 20
    matching_timezone: str = "Asia/Shanghai"
    matching_release_hour: int = 12
    deep_match_candidate_pool_size: int = 10
    deep_match_max_daily_calls: int = 10
    deep_match_min_final_score: float = 60.0
    deep_match_preliminary_weight: float = 0.4
    deep_match_model_weight: float = 0.6
    deep_match_timeout_seconds: float = 45.0
    repeat_match_recent_window_days: int = 30
    repeat_match_recent_penalty: float = 30.0
    repeat_match_medium_window_days: int = 90
    repeat_match_medium_penalty: float = 15.0
    repeat_match_long_window_days: int = 180
    repeat_match_long_penalty: float = 5.0
    dashscope_api_key: str | None = None
    dashscope_model: str = "qwen-max"
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "no-reply@campusmatch.local"
    smtp_start_tls: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("frontend_url")
    @classmethod
    def strip_frontend_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("deep_match_candidate_pool_size", "deep_match_max_daily_calls")
    @classmethod
    def positive_deep_match_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("深度匹配候选数量和每日调用上限必须大于 0")
        return value

    @model_validator(mode="after")
    def validate_deep_match_scoring(self):
        if not 0 <= self.deep_match_min_final_score <= 100:
            raise ValueError("深度匹配最低分必须在 0 到 100 之间")
        if abs(self.deep_match_preliminary_weight + self.deep_match_model_weight - 1.0) > 1e-6:
            raise ValueError("深度匹配初步分数和模型分数权重之和必须为 1")
        windows = (
            self.repeat_match_recent_window_days,
            self.repeat_match_medium_window_days,
            self.repeat_match_long_window_days,
        )
        if not (0 < windows[0] < windows[1] < windows[2]):
            raise ValueError("重复配对惩罚时间窗口必须为递增的正整数")
        penalties = (
            self.repeat_match_recent_penalty,
            self.repeat_match_medium_penalty,
            self.repeat_match_long_penalty,
        )
        if any(not 0 <= penalty <= 100 for penalty in penalties):
            raise ValueError("重复配对惩罚分必须在 0 到 100 之间")
        if not (penalties[0] >= penalties[1] >= penalties[2]):
            raise ValueError("越近期的重复配对惩罚不能低于更早期惩罚")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_url.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
