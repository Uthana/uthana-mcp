"""The README is the PyPI description, so its links must work outside GitHub."""

import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
VERSION = PYPROJECT["project"]["version"]
README = (ROOT / "README.md").read_text(encoding="utf-8")
REPO_BLOB = re.compile(r"^https://github\.com/Uthana/uthana-mcp/blob/([^/]+)/(.+)$")
MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _readme_links():
    return MARKDOWN_LINK.findall(README)


def _check_repo_link(url):
    match = REPO_BLOB.match(url)
    if not match:
        return
    ref, path = match.groups()
    assert ref == f"v{VERSION}", f"{url} should point at the release tag v{VERSION}"
    assert (ROOT / path.split("#", 1)[0]).exists(), f"{url} names a file that is not in the repository"


def test_readme_links_are_absolute():
    relative = [link for link in _readme_links() if not re.match(r"^(https?://|mailto:|#)", link)]
    assert relative == [], f"Relative links break on PyPI: {relative}"


def test_readme_repository_links_match_release():
    for link in _readme_links():
        _check_repo_link(link)


def test_project_urls_are_absolute_and_match_release():
    urls = PYPROJECT["project"]["urls"]
    assert urls["Documentation"] == "https://uthana.com/mcp/setup"
    for url in urls.values():
        assert url.startswith("https://"), url
        _check_repo_link(url)


def test_readme_has_no_preview_status():
    assert "technical preview" not in README.lower()
    assert "not recommended for production" not in README.lower()
