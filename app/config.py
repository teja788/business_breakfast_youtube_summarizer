from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_VIDEO_KEYWORD = "Business Breakfast"
DEFAULT_MAX_VIDEOS = 10
DEFAULT_SUMMARIZER_MODEL = "gpt-4.1-mini"
DEFAULT_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_MAX_AUDIO_MINUTES = 60


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    youtube_channel_id: str
    video_title_keyword: str
    openai_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    max_videos: int
    summarizer_model: str
    transcribe_model: str
    max_audio_minutes: int
    state_file: Path
    downloads_dir: Path

    def safe_summary(self) -> dict[str, str | int]:
        return {
            "youtube_channel_id": self.youtube_channel_id,
            "video_title_keyword": self.video_title_keyword,
            "telegram_chat_id": self.telegram_chat_id,
            "max_videos": self.max_videos,
            "summarizer_model": self.summarizer_model,
            "transcribe_model": self.transcribe_model,
            "max_audio_minutes": self.max_audio_minutes,
            "state_file": str(self.state_file),
            "downloads_dir": str(self.downloads_dir),
            "openai_api_key": mask_secret(self.openai_api_key),
            "telegram_bot_token": mask_secret(self.telegram_bot_token),
        }


def load_config(env_file: str | Path = ".env") -> AppConfig:
    env_path = Path(env_file)
    load_dotenv_file(env_path)

    root_dir = Path.cwd()
    downloads_dir = root_dir / "data" / "downloads"
    state_file = root_dir / "data" / "processed_videos.json"

    return AppConfig(
        youtube_channel_id=read_required("YOUTUBE_CHANNEL_ID"),
        video_title_keyword=os.getenv("VIDEO_TITLE_KEYWORD", DEFAULT_VIDEO_KEYWORD).strip() or DEFAULT_VIDEO_KEYWORD,
        openai_api_key=read_required("OPENAI_API_KEY"),
        telegram_bot_token=read_required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=read_required("TELEGRAM_CHAT_ID"),
        max_videos=parse_int_in_range("MAX_VIDEOS", os.getenv("MAX_VIDEOS", str(DEFAULT_MAX_VIDEOS)), 1, 50),
        summarizer_model=os.getenv("OPENAI_SUMMARIZER_MODEL", DEFAULT_SUMMARIZER_MODEL).strip() or DEFAULT_SUMMARIZER_MODEL,
        transcribe_model=os.getenv("OPENAI_TRANSCRIBE_MODEL", DEFAULT_TRANSCRIBE_MODEL).strip() or DEFAULT_TRANSCRIBE_MODEL,
        max_audio_minutes=parse_int_in_range(
            "MAX_AUDIO_MINUTES",
            os.getenv("MAX_AUDIO_MINUTES", str(DEFAULT_MAX_AUDIO_MINUTES)),
            1,
            240,
        ),
        state_file=state_file,
        downloads_dir=downloads_dir,
    )


def load_dotenv_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def parse_int_in_range(name: str, raw_value: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc

    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def mask_secret(value: str) -> str:
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}{'*' * (len(value) - 6)}{value[-3:]}"
