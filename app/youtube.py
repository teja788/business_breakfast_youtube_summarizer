from __future__ import annotations

from pathlib import Path
from typing import Iterable
import subprocess

import imageio_ffmpeg
from yt_dlp import YoutubeDL

from app.models import Video


SUPPORTED_AUDIO_EXTENSIONS = {".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".ogg", ".wav", ".webm"}
DISCOVERY_WINDOW = 100


class YouTubeError(RuntimeError):
    """Raised when video discovery or audio download fails."""


def get_recent_videos(channel_id: str, limit: int, keyword: str) -> list[Video]:
    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
    options = {
        "extract_flat": True,
        "playlistend": max(limit, DISCOVERY_WINDOW),
        "quiet": True,
        "noprogress": True,
        "skip_download": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(channel_url, download=False)
    except Exception as exc:
        raise YouTubeError(f"Failed to fetch channel videos for {channel_id}: {exc}") from exc

    entries = info.get("entries") or []
    matches: list[Video] = []
    keyword_lower = keyword.lower()

    for entry in entries:
        title = str(entry.get("title") or "").strip()
        if keyword_lower not in title.lower():
            continue

        video_id = str(entry.get("id") or "").strip()
        if not video_id:
            continue

        url = str(entry.get("url") or "").strip()
        if not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={video_id}"

        published_at = str(entry.get("upload_date") or "").strip()
        matches.append(Video(video_id=video_id, title=title, url=url, published_at=published_at))
        if len(matches) >= limit:
            break

    return matches


def download_audio(video: Video, downloads_dir: Path, max_minutes: int) -> Path:
    downloads_dir.mkdir(parents=True, exist_ok=True)
    clipped_output_path = downloads_dir / f"{video.video_id}_first_{max_minutes}m.mp3"
    if clipped_output_path.exists():
        return clipped_output_path

    output_template = str(downloads_dir / f"{video.video_id}.%(ext)s")
    options = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "noprogress": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            ydl.download([video.url])
    except Exception as exc:
        raise YouTubeError(f"Failed to download audio for {video.url}: {exc}") from exc

    source_path = find_downloaded_audio(downloads_dir, video.video_id)
    if source_path is None:
        raise YouTubeError(f"Audio download did not create a supported file for {video.url}")

    return trim_audio_for_transcription(source_path, clipped_output_path, max_minutes)


def trim_audio_for_transcription(source_path: Path, output_path: Path, max_minutes: int) -> Path:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg_exe,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "22050",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "64k",
        "-t",
        str(max_minutes * 60),
        str(output_path),
    ]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not output_path.exists():
        error_text = result.stderr.strip() or result.stdout.strip() or "unknown ffmpeg error"
        raise YouTubeError(f"Failed to trim audio to first {max_minutes} minutes: {error_text}") from exc
    return output_path


def find_downloaded_audio(downloads_dir: Path, video_id: str) -> Path | None:
    for path in sorted(downloads_dir.glob(f"{video_id}.*")):
        if path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS and "_first_" not in path.stem:
            return path
    return None


def format_video_list(videos: Iterable[Video]) -> str:
    lines: list[str] = []
    for video in videos:
        published = video.published_at or "unknown-date"
        lines.append(f"- {video.title} ({published})")
        lines.append(f"  {video.url}")
    return "\n".join(lines)

