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
    print(f"[api] fetching pending items from {url}")
    data = _json_request(url, ctx=_context(cfg))
    if data is None:
        return []
    if not isinstance(data, list):
        print(f"[api] unexpected response shape: {type(data).__name__}")
        return []
    print(f"[api] found {len(data)} item(s) pending processing")
    return data


def mark_ready(cfg: AppConfig, content_id: str) -> bool:
    return _patch_status(cfg, content_id, "ready")


def mark_failed(cfg: AppConfig, content_id: str) -> bool:
    return _patch_status(cfg, content_id, "failed")


def _patch_status(cfg: AppConfig, content_id: str, status: str) -> bool:
    url = f"{cfg.api_base_url}/api/content/{content_id}/status"
    headers = {"X-Api-Key": cfg.s3_access_key}
    body = {"status": status}

    print(f"[api] PATCH {url} -> {status}")
    result = _json_request(url, method="PATCH", headers=headers, body=body,
                           ctx=_context(cfg))
    if result is None:
        return False
    print(f"[api] response: {result}")
    return result.get("ok", False)
