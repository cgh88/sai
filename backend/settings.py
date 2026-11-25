# -*- coding: utf-8 -*-
"""설정 — `.env` 에서 LINER_API_KEY 등을 읽는다. 키는 화면·로그·응답 어디에도 노출하지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
APP_DIR = BACKEND_DIR.parent


def _load_env_files() -> list[str]:
    """sai-app/.env → sai-app/backend/.env → 현재 디렉터리/.env 순으로 읽는다(이미 있는 환경변수 우선)."""
    loaded = []
    for path in (APP_DIR / ".env", BACKEND_DIR / ".env", Path.cwd() / ".env"):
        if not path.is_file():
            continue
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
            loaded.append(str(path))
        except OSError:
            continue
    return loaded


def _flag(name: str, default: str) -> str:
    return (os.environ.get(name) or default).strip().lower()


@dataclass
class Settings:
    api_key: str = ""
    base_url: str = "https://platform.liner.com"
    chat_model: str = "liner-gpt-router"
    routing_letter: str = "balanced"
    routing_report: str = "cost"
    demo_mode: str = "auto"            # auto | on | off
    stream_speed: float = 1.0          # 시드 스트림 배속(1.0 = 기본, 0 = 즉시)
    host: str = "127.0.0.1"
    port: int = 8000
    env_files: list[str] = field(default_factory=list)

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    @property
    def use_seed(self) -> bool:
        """시드 모드로 시작할지 — 실제 호출이 실패하면 런타임에 폴백한다."""
        if self.demo_mode == "on":
            return True
        if self.demo_mode == "off":
            return False
        return not self.has_key

    def public(self) -> dict:
        """화면·API 로 내보내도 되는 설정만(키 자체는 절대 포함하지 않는다)."""
        return {
            "liner_base_url": self.base_url,
            "liner_key_configured": self.has_key,
            "chat_model": self.chat_model,
            "routing_letter": self.routing_letter,
            "routing_report": self.routing_report,
            "demo_mode": self.demo_mode,
            "seed_mode": self.use_seed,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    loaded = _load_env_files()
    try:
        speed = float(os.environ.get("SAI_STREAM_SPEED", "1") or 1)
    except ValueError:
        speed = 1.0
    try:
        port = int(os.environ.get("SAI_PORT", "8000") or 8000)
    except ValueError:
        port = 8000
    demo_mode = _flag("SAI_DEMO_MODE", "auto")
    if demo_mode not in ("auto", "on", "off"):
        demo_mode = "auto"
    return Settings(
        api_key=(os.environ.get("LINER_API_KEY") or "").strip(),
        base_url=(os.environ.get("LINER_BASE_URL") or "https://platform.liner.com").rstrip("/"),
        chat_model=(os.environ.get("LINER_CHAT_MODEL") or "liner-gpt-router").strip(),
        routing_letter=(os.environ.get("LINER_ROUTING_LETTER") or "balanced").strip(),
        routing_report=(os.environ.get("LINER_ROUTING_REPORT") or "cost").strip(),
        demo_mode=demo_mode,
        stream_speed=max(0.0, speed),
        host=(os.environ.get("SAI_HOST") or "127.0.0.1").strip(),
        port=port,
        env_files=loaded,
    )
