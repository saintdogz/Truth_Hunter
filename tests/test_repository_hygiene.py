import subprocess
from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {".dockerignore", ".editorconfig", ".gitattributes", "Caddyfile", "Dockerfile"}
FORBIDDEN_TEXT = (
    "\u00e2\u20ac",
    "\u00c2\u00b7",
    "\u00e2\u2020",
    "\u00ef\u00bb\u00bf",
    "\ufffd",
    "'" * 6,
)


def tracked_text_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    paths = result.stdout.decode("utf-8").split("\0")
    return [
        REPOSITORY_ROOT / path
        for path in paths
        if path and (Path(path).suffix.lower() in TEXT_SUFFIXES or Path(path).name in TEXT_NAMES)
    ]


def test_tracked_text_files_are_clean_utf8() -> None:
    failures: list[str] = []
    for path in tracked_text_files():
        if not path.exists():
            continue
        raw = path.read_bytes()
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        if raw.startswith(b"\xef\xbb\xbf"):
            failures.append(f"{relative}: contains a UTF-8 BOM")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            failures.append(f"{relative}: is not valid UTF-8 ({exc})")
            continue
        for marker in FORBIDDEN_TEXT:
            if marker in content:
                failures.append(f"{relative}: contains suspicious text {marker!r}")
    assert not failures, "\n".join(failures)


def test_github_configuration_yaml_is_valid() -> None:
    files = sorted((REPOSITORY_ROOT / ".github").rglob("*.yml"))
    files.extend(sorted((REPOSITORY_ROOT / ".github").rglob("*.yaml")))
    for path in files:
        yaml.safe_load(path.read_text(encoding="utf-8"))


def test_issue_templates_start_with_front_matter() -> None:
    template_dir = REPOSITORY_ROOT / ".github" / "ISSUE_TEMPLATE"
    for path in sorted(template_dir.glob("*.md")):
        assert path.read_text(encoding="utf-8").startswith("---\n"), path.name
