"""Desktop inspector backend: proxies GET /memory/stats from the agent-memory-es
service using the plugin's configured url/api_key (same env/config as the
memory provider). Read-only."""
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException

router = APIRouter()


def _cfg() -> tuple:
    base = os.environ.get("AMES_SERVICE_URL", "http://localhost:8123").rstrip("/")
    key = os.environ.get("AMES_SERVICE_KEY", "")
    return base, key


@router.get("/stats")
async def stats() -> dict:
    base, key = _cfg()
    if not key:
        raise HTTPException(503, "AMES_SERVICE_KEY not set")
    req = urllib.request.Request(
        f"{base}/memory/stats", headers={"X-API-Key": key})
    try:
        import json
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise HTTPException(e.code, f"ames: {e.read().decode()[:200]}") from e
    except Exception as e:
        raise HTTPException(502, f"ames unreachable: {e}") from e
