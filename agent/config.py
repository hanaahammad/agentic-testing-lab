import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORIES_DIR = ROOT / "stories"
TESTS_DIR = ROOT / "tests" / "generated"
REPORTS_DIR = ROOT / "reports"

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
DEFAULT_PORT = int(os.getenv("MINIBANK_PORT", "8000"))
DEFAULT_BASE_URL = os.getenv("BASE_URL", f"http://127.0.0.1:{DEFAULT_PORT}")


def load_stories() -> list[dict]:
    """Stories are markdown files whose first line is '# STORY-XXX: Title'."""
    stories = []
    for path in sorted(STORIES_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"#\s*(STORY-\d+)\s*:\s*(.+)", text.strip().splitlines()[0])
        if m:
            stories.append({"id": m.group(1), "title": m.group(2).strip(), "text": text, "path": str(path)})
    return stories


def get_story(story_id: str) -> dict:
    for s in load_stories():
        if s["id"] == story_id:
            return s
    raise KeyError(f"Unknown story {story_id}")
