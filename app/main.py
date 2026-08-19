from __future__ import annotations

import json
import sys

from app.config import ConfigError, load_config
from app.state import load_processed_ids, mark_processed
from app.summarizer import format_telegram_message, summarize_business_news
from app.telegram_sender import TelegramError, send_telegram_message
from app.transcribe import TranscriptionError, transcribe_telugu, translate_to_english
from app.youtube import YouTubeError, download_audio, format_video_list, get_recent_videos


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        print("Copy .env.example to .env and fill in the required values.", file=sys.stderr)
        return 1

    print("Loaded configuration:")
    print(json.dumps(config.safe_summary(), indent=2))

    try:
        videos = get_recent_videos(
            channel_id=config.youtube_channel_id,
            limit=config.max_videos,
            keyword=config.video_title_keyword,
        )
    except YouTubeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not videos:
        print("No matching videos found in the latest uploads.")
        return 0

    print("Matching recent videos:")
    print(format_video_list(videos))

    processed_ids = load_processed_ids(config.state_file)
    pending_videos = [video for video in videos if video.video_id not in processed_ids]

    if not pending_videos:
        print("All matching videos are already processed.")
        return 0

    failures = 0
    for index, video in enumerate(pending_videos, start=1):
        print(f"\n[{index}/{len(pending_videos)}] Processing: {video.title}")
        try:
            audio_path = download_audio(video, config.downloads_dir, config.max_audio_minutes)
            print(f"Prepared audio: {audio_path}")

            telugu_transcript = transcribe_telugu(audio_path, config.openai_api_key, config.transcribe_model)
            print_block("Telugu transcript", telugu_transcript)

            english_translation = translate_to_english(
                telugu_transcript,
                config.openai_api_key,
                config.summarizer_model,
            )
            print_block("English translation", english_translation)

            summary = summarize_business_news(
                english_text=english_translation,
                api_key=config.openai_api_key,
                model=config.summarizer_model,
            )
            print_block("English summary", summary)

            message = format_telegram_message(video.title, video.url, summary)
            send_telegram_message(config.telegram_bot_token, config.telegram_chat_id, message)
            mark_processed(config.state_file, video.video_id)
            print("Telegram send succeeded and video was marked as processed.")
        except (YouTubeError, TranscriptionError, TelegramError, OSError) as exc:
            failures += 1
            print(f"Failed to process {video.video_id}: {exc}", file=sys.stderr)

    if failures:
        print(f"Completed with {failures} failure(s).", file=sys.stderr)
        return 1

    print("Completed successfully.")
    return 0


def print_block(title: str, content: str) -> None:
    print(f"\n--- {title} ---")
    body = content.strip()
    try:
        print(body)
    except UnicodeEncodeError:
        # Fallback for Windows terminals with non-UTF code pages.
        print(body.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
    print(f"--- end {title} ---\n")


if __name__ == "__main__":
    raise SystemExit(main())
