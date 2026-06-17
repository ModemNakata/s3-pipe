from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

from config import AppConfig


def _context(cfg: AppConfig) -> ssl.SSLContext:
    if cfg.api_verify_ssl:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _json_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    body: Optional[dict[str, Any]] = None,
    ctx: Optional[ssl.SSLContext] = None,
) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        print(f"[api] HTTP {e.code} from {method} {url}: {body_text}")
        return None
    except urllib.error.URLError as e:
        print(f"[api] connection error {method} {url}: {e.reason}")
        return None


def get_pending_items(cfg: AppConfig) -> list[dict[str, Any]]:
    url = f"{cfg.api_base_url}/api/pending-processing"
    if cfg.dev_mode:
        url += "?all=true"
    print(f"[api] fetching pending items from {url}")
    data = _json_request(url, ctx=_context(cfg))
    if data is None:
        return []
    if not isinstance(data, list):
        print(f"[api] unexpected response shape: {type(data).__name__}")
        return []
    label = "all" if cfg.dev_mode else "pending"
    print(f"[api] found {len(data)} item(s) ({label})")
    return data


def get_content(cfg: AppConfig, content_id: str) -> Optional[dict[str, Any]]:
    """GET /api/content/{id} — returns content item or None if not found."""
    url = f"{cfg.api_base_url}/api/content/{content_id}"
    print(f"[api] fetching content from {url}")
    data = _json_request(url, ctx=_context(cfg))
    if data is None or not isinstance(data, dict):
        return None
    return data


def mark_ready(cfg: AppConfig, content_id: str,
               thumbnail_url: str = "", preview_path: str = "",
               duration: float = 0,
               processed_files: Optional[list[str]] = None,
               free_preview_path: str = "",
               blurred_files: Optional[list[str]] = None,
               source_quality: str = "") -> bool:
    body: dict[str, Any] = {"status": "ready"}
    if thumbnail_url:
        body["thumbnail_url"] = thumbnail_url
    if preview_path:
        body["preview_path"] = preview_path
    if duration > 0:
        body["duration"] = round(duration, 2)
    if processed_files:
        body["processed_files"] = processed_files
    if free_preview_path:
        body["free_preview_path"] = free_preview_path
    if blurred_files:
        body["blurred_files"] = blurred_files
    if source_quality:
        body["source_quality"] = source_quality
    return _patch(cfg, content_id, body)


def mark_failed(cfg: AppConfig, content_id: str) -> bool:
    return _patch(cfg, content_id, {"status": "failed"})


def _patch(cfg: AppConfig, content_id: str, body: dict[str, Any]) -> bool:
    url = f"{cfg.api_base_url}/api/content/{content_id}/status"
    headers = {"X-Api-Key": cfg.s3_access_key}

    print(f"[api] PATCH {url} -> {json.dumps(body)}")
    result = _json_request(url, method="PATCH", headers=headers, body=body,
                           ctx=_context(cfg))
    if result is None:
        return False
    print(f"[api] response: {result}")
    return result.get("ok", False)
