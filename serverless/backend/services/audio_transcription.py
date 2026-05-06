"""Groq Whisper transcription wrapper for serverless audio answers."""

from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.request
from typing import Any


def transcribe_audio_bytes(audio_bytes: bytes, *, filename: str, content_type: str, prompt: str = "") -> str:
    if not audio_bytes:
        raise ValueError("Audio file is empty.")
    api_key = _get_groq_api_key()
    if not api_key:
        raise RuntimeError("Groq API key is not configured.")

    boundary = f"----psysense-{uuid.uuid4().hex}"
    body = _multipart_body(
        boundary=boundary,
        fields={
            "model": os.environ.get("GROQ_TRANSCRIPTION_MODEL", "whisper-large-v3"),
            "response_format": "json",
            "prompt": prompt[:800],
        },
        file_field="file",
        filename=filename,
        content_type=content_type,
        file_bytes=audio_bytes,
    )
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Audio transcription provider request failed.") from exc
    return str(payload.get("text", "")).strip()


def _get_groq_api_key() -> str:
    env_key = os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY_2")
    if env_key:
        return env_key.strip()

    parameter_name = os.environ.get("GROQ_API_KEY_PARAMETER_NAME", "").strip()
    if not parameter_name:
        return ""

    try:
        import boto3  # type: ignore
    except ImportError:
        return ""
    response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
    return str(response.get("Parameter", {}).get("Value", "")).strip()


def _multipart_body(
    *,
    boundary: str,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> bytes:
    parts: list[bytes] = []
    for name, value in fields.items():
        if value == "":
            continue
        parts.extend([
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
            str(value).encode("utf-8"),
            b"\r\n",
        ])
    parts.extend([
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ])
    return b"".join(parts)
