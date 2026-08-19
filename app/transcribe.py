from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
from openai import OpenAI


DEFAULT_CHUNK_SECONDS = 10 * 60


class TranscriptionError(RuntimeError):
    """Raised when transcription or translation fails."""


def transcribe_telugu(audio_path: Path, api_key: str, model: str) -> str:
    client = OpenAI(api_key=api_key)

    try:
        return transcribe_single_audio(audio_path, client, model)
    except Exception as exc:
        if not should_chunk_retry(exc):
            raise TranscriptionError(f"Telugu transcription failed: {exc}") from exc

    chunk_dir = prepare_chunk_dir(audio_path)
    chunk_paths = split_audio_into_chunks(audio_path, chunk_dir, DEFAULT_CHUNK_SECONDS)
    if not chunk_paths:
        raise TranscriptionError("Telugu transcription failed: chunking produced no audio segments")

    transcript_parts: list[str] = []
    for index, chunk_path in enumerate(chunk_paths, start=1):
        try:
            part = transcribe_single_audio(chunk_path, client, model)
        except Exception as exc:
            raise TranscriptionError(f"Chunk transcription failed ({index}/{len(chunk_paths)}): {exc}") from exc
        transcript_parts.append(part)

    return "\n".join(part.strip() for part in transcript_parts if part.strip())


def transcribe_single_audio(audio_path: Path, client: OpenAI, model: str) -> str:
    with audio_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            response_format="text",
            prompt="This is Telugu business news. Transcribe exactly what is spoken. Keep names, numbers, and punctuation accurate.",
        )
    return extract_text(response)


def should_chunk_retry(exc: Exception) -> bool:
    message = str(exc).lower()
    return ("input_too_large" in message or "total number of tokens" in message or ("audio duration" in message and "maximum for this model" in message) or "longer than" in message and "maximum" in message)


def prepare_chunk_dir(audio_path: Path) -> Path:
    chunk_dir = audio_path.parent / f"{audio_path.stem}_chunks"
    if chunk_dir.exists():
        shutil.rmtree(chunk_dir)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    return chunk_dir


def split_audio_into_chunks(audio_path: Path, chunk_dir: Path, chunk_seconds: int) -> list[Path]:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    out_pattern = str(chunk_dir / "chunk_%03d.mp3")
    command = [
        ffmpeg_exe,
        "-y",
        "-i",
        str(audio_path),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-ac",
        "1",
        "-ar",
        "22050",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "64k",
        out_pattern,
    ]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        error_text = result.stderr.strip() or result.stdout.strip() or "unknown ffmpeg error"
        raise TranscriptionError(f"Failed to split audio for chunking: {error_text}")

    return sorted(chunk_dir.glob("chunk_*.mp3"))


def translate_to_english(transcript_text: str, api_key: str, model: str) -> str:
    client = OpenAI(api_key=api_key)
    prompt = (
        "Translate this Telugu business news transcript into clear English. "
        "Preserve names, companies, currencies, dates, percentages, and figures accurately. "
        "Return only the English translation."
    )
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": transcript_text},
            ],
        )
    except Exception as exc:
        raise TranscriptionError(f"English translation failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise TranscriptionError("OpenAI returned an empty translation")
    return content.strip()


def extract_text(response: object) -> str:
    if isinstance(response, str):
        return response.strip()

    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text.strip()

    result = str(response).strip()
    if not result:
        raise TranscriptionError("OpenAI returned an empty transcription response")
    return result

