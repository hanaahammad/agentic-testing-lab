"""Versioned QA artifacts.

Every test cycle (and every exploratory session) is saved as a NEW numbered version, never overwritten:

  artifacts/<app>/<STORY-ID>/v003/
      manifest.json      who/what/when: version, parent, build tested, brain, code commit, status, file hashes
      story.md           the story exactly as it was tested
      test_cases.json    the approved test cases
      test_script.py     the script that ran
      junit.xml          raw pytest results
      results.json       per-test status
      triage.json        verdicts (product bug / test bug / environment)
      issues.json        what was opened / closed in the tracker
      report.md          human-readable summary
  artifacts/<app>/<STORY-ID>/explore-v002/
      manifest.json, transcript.json, findings.json, screens/step-01.png ...

Two layers of versioning:
  1. Folders: v001, v002, ... each run is immutable, with a sha256 per file in its manifest.
  2. Git: the artifacts/ folder is meant to be committed (commit_to_git), so GitHub keeps the full history.
"""
import datetime as dt
import difflib
import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from .config import ROOT, TARGETS

ARTIFACTS_DIR = ROOT / "artifacts"
SCHEMA = 1


def _git(*args) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def code_version() -> str:
    """The git commit of the lab itself, with '+changes' if there are uncommitted edits."""
    sha = _git("rev-parse", "--short", "HEAD")
    if not sha:
        return "not a git repo"
    dirty = _git("status", "--porcelain", "--", "agent", "tests", "stories")
    return sha + ("+changes" if dirty else "")


def story_dir(app: str, story_id: str) -> Path:
    return ARTIFACTS_DIR / app / story_id


def _next(app: str, story_id: str, prefix: str) -> tuple[str, Path, str]:
    d = story_dir(app, story_id)
    d.mkdir(parents=True, exist_ok=True)
    pat = re.compile(rf"^{re.escape(prefix)}v(\d+)$")
    nums = sorted(int(m.group(1)) for p in d.iterdir() if (m := pat.match(p.name)))
    n = (nums[-1] + 1) if nums else 1
    parent = f"{prefix}v{nums[-1]:03d}" if nums else ""
    name = f"{prefix}v{n:03d}"
    (d / name).mkdir()
    return name, d / name, parent


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _write(folder: Path, name: str, content) -> None:
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    elif isinstance(content, str):
        p.write_text(content, encoding="utf-8")
    else:
        p.write_text(json.dumps(content, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _finish(folder: Path, manifest: dict) -> dict:
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "manifest.json")
    manifest["files"] = {str(p.relative_to(folder)).replace("\\", "/"): _sha(p) for p in files}
    _write(folder, "manifest.json", manifest)
    return manifest


def _base_manifest(kind, app, story, version, parent, build, brain) -> dict:
    return {
        "schema": SCHEMA, "kind": kind, "version": version, "parent": parent,
        "app": app, "app_name": TARGETS[app]["name"], "story": story["id"], "story_title": story["title"],
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "build_tested": build, "brain": brain, "lab_code": code_version(),
    }


def record_cycle(story: dict, result: dict, build: str = "unknown", brain: str = "demo",
                 report_md: str = "", junit: Path | None = None, stage: str = "complete") -> dict:
    """Save one test cycle (full or step by step) as a new version. Returns its manifest."""
    app = result.get("target") or story.get("target", "minibank")
    version, folder, parent = _next(app, story["id"], "")
    _write(folder, "story.md", story["text"])
    if result.get("cases") is not None:
        _write(folder, "test_cases.json", result["cases"])
    if result.get("code"):
        _write(folder, "test_script.py", result["code"])
    run = result.get("run")
    if run:
        _write(folder, "results.json", {"summary": run["summary"], "cases": run["cases"]})
        if junit and Path(junit).exists():
            shutil.copy(junit, folder / "junit.xml")
    if result.get("verdicts") is not None:
        _write(folder, "triage.json", result["verdicts"])
    if result.get("actions") is not None:
        _write(folder, "issues.json", [{"action": a["action"], "number": a["issue"]["number"],
                                        "title": a["issue"]["title"], "url": a["issue"].get("url", "")}
                                       for a in result["actions"]])
    if report_md:
        _write(folder, "report.md", report_md)
    m = _base_manifest("cycle", app, story, version, parent, build, brain)
    m.update(stage=stage, repairs=result.get("repairs", 0),
             summary=(run or {}).get("summary"),
             product_bugs=sorted(v.get("tc_id") for v in result.get("verdicts") or []
                                 if v.get("verdict") == "product_bug"),
             needs_review=any(v.get("needs_review") for v in result.get("verdicts") or []))
    return _finish(folder, m)


def record_exploration(story: dict, res: dict, build: str = "unknown", brain: str = "demo") -> dict:
    app = story.get("target", "minibank")
    version, folder, parent = _next(app, story["id"], "explore-")
    transcript, n = [], 0
    for e in res["events"]:
        e = dict(e)
        shot = e.pop("screenshot", None)
        if shot:
            n += 1
            e["screenshot"] = f"screens/step-{n:02d}.png"
            _write(folder, e["screenshot"], shot)
        transcript.append(e)
    _write(folder, "transcript.json", transcript)
    _write(folder, "findings.json", res["findings"])
    m = _base_manifest("exploration", app, story, version, parent, build, brain)
    m.update(stage="complete", actions_used=res.get("requests_used", 0), findings=len(res["findings"]),
             screenshots=n)
    return _finish(folder, m)


# ---------------------------------------------------------------- reading
def list_versions(app: str | None = None, story_id: str | None = None) -> list[dict]:
    """All manifests, newest first."""
    out = []
    root = ARTIFACTS_DIR / app if app else ARTIFACTS_DIR
    for mf in root.rglob("manifest.json") if root.exists() else []:
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if story_id and m.get("story") != story_id:
            continue
        m["path"] = str(mf.parent)
        out.append(m)
    return sorted(out, key=lambda m: m.get("created", ""), reverse=True)


def read(manifest: dict, name: str):
    p = Path(manifest["path"]) / name
    if not p.exists():
        return None
    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    if p.suffix in (".png", ".jpg"):
        return p.read_bytes()
    return p.read_text(encoding="utf-8")


def verify(manifest: dict) -> list[str]:
    """Files whose content no longer matches the hash recorded when the version was saved."""
    folder = Path(manifest["path"])
    bad = []
    for name, h in manifest.get("files", {}).items():
        p = folder / name
        if not p.exists():
            bad.append(f"{name} (missing)")
        elif _sha(p) != h:
            bad.append(f"{name} (changed)")
    return bad


def diff(a: dict, b: dict, name: str) -> str:
    """Unified diff of one file between two versions (a = older, b = newer)."""
    def lines(m):
        v = read(m, name)
        if v is None:
            return []
        text = v if isinstance(v, str) else json.dumps(v, indent=2, ensure_ascii=False)
        return text.splitlines(keepends=True)
    return "".join(difflib.unified_diff(lines(a), lines(b), f"{a['version']}/{name}", f"{b['version']}/{name}"))


def zip_bytes(manifest: dict) -> bytes:
    folder = Path(manifest["path"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, f"{manifest['app']}-{manifest['story']}-{manifest['version']}/{p.relative_to(folder)}")
    return buf.getvalue()


# ---------------------------------------------------------------- git
def git_status() -> dict:
    """What git knows about artifacts/: not a repo, uncommitted versions, or all committed."""
    if not _git("rev-parse", "--is-inside-work-tree"):
        return {"repo": False, "pending": []}
    lines = _git("status", "--porcelain", "--untracked-files=all", "--", "artifacts").splitlines()
    pending = sorted({"/".join(Path(line[3:].strip().strip('"')).parts[1:4]) for line in lines if line.strip()})
    return {"repo": True, "pending": [p for p in pending if p], "branch": _git("branch", "--show-current")}


def commit_to_git(message: str = "") -> tuple[bool, str]:
    """Commit ONLY the artifacts/ folder (other staged work is left alone). Push stays a human step."""
    st = git_status()
    if not st["repo"]:
        return False, "This folder is not a git repository."
    if not st["pending"]:
        return True, "Nothing new: every artifact version is already committed."
    add = subprocess.run(["git", "add", "--", "artifacts"], cwd=ROOT, capture_output=True, text=True)
    if add.returncode:
        return False, add.stderr.strip()
    msg = message or f"QA artifacts: {len(st['pending'])} new version(s)\n\n" + "\n".join(st["pending"])
    c = subprocess.run(["git", "commit", "-m", msg, "--", "artifacts"], cwd=ROOT, capture_output=True, text=True)
    if c.returncode:
        return False, (c.stderr or c.stdout).strip()
    return True, f"Committed {len(st['pending'])} version(s) as {_git('rev-parse', '--short', 'HEAD')} on " \
                 f"{st.get('branch') or 'current branch'}. Run `git push` to send them to GitHub."
