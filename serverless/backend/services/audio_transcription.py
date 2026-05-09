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
    api_keys = _get_groq_api_keys()
    if not api_keys:
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
    last_error: Exception | None = None
    for api_key in api_keys:
        request = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
                "User-Agent": "TalentryxAIServerless/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return str(payload.get("text", "")).strip()
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
    raise RuntimeError("Audio transcription provider request failed.") from last_error


def _get_groq_api_keys() -> list[str]:
    keys: list[str] = []
    for env_name in ("GROQ_API_KEY", "GROQ_API_KEY_2"):
        env_key = os.environ.get(env_name, "").strip()
        if env_key and env_key not in keys:
            keys.append(env_key)

    parameter_name = os.environ.get("GROQ_API_KEY_PARAMETER_NAME", "").strip()
    if not parameter_name:
        return keys

    try:
        import boto3  # type: ignore
    except ImportError:
        return keys
    response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
    ssm_key = str(response.get("Parameter", {}).get("Value", "")).strip()
    if ssm_key and ssm_key not in keys:
        keys.append(ssm_key)
    return keys


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
