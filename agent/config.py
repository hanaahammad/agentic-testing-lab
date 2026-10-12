import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORIES_DIR = ROOT / "stories"
TESTS_ROOT = ROOT / "tests"
REPORTS_DIR = ROOT / "reports"

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

# The applications the agent can test. Each one is a black box: the agent only uses its URL,
# its /openapi.json and (for web apps) its screens. "module" is only used to start it locally.
TARGETS = {
    "minibank": {
        "name": "MiniBank", "kind": "api", "description": "Tiny core-banking REST API (3 stories)",
        "module": "app_under_test.minibank:app", "port": int(os.getenv("MINIBANK_PORT", "8000")),
        "fixed_env": "MINIBANK_FIXED", "health": "/health", "reset": "/reset", "openapi": "/openapi.json",
    },
    "nilebank": {
        "name": "NileBank", "kind": "web", "description": "Online-banking web app with sign-in, screens and API (7 stories)",
        "module": "apps.nilebank.app:app", "port": int(os.getenv("NILEBANK_PORT", "8001")),
        "fixed_env": "NILEBANK_FIXED", "health": "/api/health", "reset": "/api/test/reset",
        "openapi": "/openapi.json", "test_user": ("amira", "Nile@2026"),
    },
}
DEFAULT_TARGET = os.getenv("TARGET_APP", "minibank")


def target(key: str) -> dict:
    return {"key": key, **TARGETS[key]}


def default_url(key: str) -> str:
    env = os.getenv(f"{key.upper()}_URL") or (os.getenv("BASE_URL") if key == DEFAULT_TARGET else None)
    return (env or f"http://127.0.0.1:{TARGETS[key]['port']}").rstrip("/")


def tests_dir(key: str) -> Path:
    return TESTS_ROOT / key / "generated"


def load_stories(key: str = DEFAULT_TARGET) -> list[dict]:
    """Stories are markdown files whose first line is '# STORY-XXX: Title', one folder per application."""
    stories = []
    for path in sorted((STORIES_DIR / key).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"#\s*(STORY-\d+)\s*:\s*(.+)", text.strip().splitlines()[0])
        if m:
            stories.append({"id": m.group(1), "title": m.group(2).strip(), "text": text,
                            "path": str(path), "target": key})
    return stories


def get_story(story_id: str, key: str | None = None) -> dict:
    for k in ([key] if key else list(TARGETS)):
        for s in load_stories(k):
            if s["id"] == story_id:
                return s
    raise KeyError(f"Unknown story {story_id}")
