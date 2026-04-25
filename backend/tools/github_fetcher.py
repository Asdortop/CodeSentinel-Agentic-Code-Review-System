"""GitHub REST API utility — fetches repo file tree and file contents."""
from __future__ import annotations

import base64
import re
from typing import Dict, List, Optional, Tuple
import httpx

from config import (
    GITHUB_TOKEN,
    MAX_FILES,
    MAX_LINES,
    RELEVANT_EXTENSIONS,
    RELEVANT_FILENAMES,
)


def _headers() -> Dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def parse_repo_url(url: str) -> Tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL."""
    url = url.rstrip("/")
    # Handle various formats: https://github.com/owner/repo[.git][/...]
    match = re.search(r"github\.com[/:]([^/]+)/([^/\s.]+)", url)
    if not match:
        raise ValueError(f"Cannot parse GitHub URL: {url}")
    owner, repo = match.group(1), match.group(2)
    repo = repo.removesuffix(".git")
    return owner, repo


def _is_relevant(path: str) -> bool:
    import os
    basename = os.path.basename(path)
    _, ext = os.path.splitext(basename)
    if basename in RELEVANT_FILENAMES:
        return True
    if ext.lower() in RELEVANT_EXTENSIONS:
        return True
    # .env variants
    if basename.startswith(".env"):
        return True
    return False


async def fetch_repo_tree(repo_url: str) -> Tuple[str, str, List[str]]:
    """
    Returns (owner, repo, list_of_relevant_file_paths).
    Tries main → master → HEAD for the default branch.
    """
    owner, repo = parse_repo_url(repo_url)

    async with httpx.AsyncClient(timeout=30) as client:
        # Get default branch
        repo_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=_headers(),
        )
        if repo_resp.status_code == 404:
            raise ValueError(f"Repository not found or is private: {repo_url}")
        if repo_resp.status_code == 403:
            raise ValueError("GitHub API rate limit exceeded. Set GITHUB_TOKEN in .env to increase limit.")
        repo_resp.raise_for_status()
        default_branch = repo_resp.json().get("default_branch", "main")

        # Fetch recursive tree
        tree_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1",
            headers=_headers(),
        )
        tree_resp.raise_for_status()
        tree_data = tree_resp.json()

    if tree_data.get("truncated"):
        pass  # Large repos — we filter anyway

    blobs = [
        item["path"]
        for item in tree_data.get("tree", [])
        if item["type"] == "blob" and _is_relevant(item["path"])
    ]

    # ── Priority sort ────────────────────────────────────────────────────
    # Priority 0 = most important, 3 = least
    HIGH_PRIORITY_NAMES = {
        "auth", "login", "password", "secret", "token", "key", "credential",
        "config", "settings", "db", "database", "query", "sql", "session",
        "middleware", "security", "api", "admin", "user", "account",
    }

    def _priority(path: str) -> int:
        import os
        basename = os.path.basename(path).lower()
        name_no_ext = os.path.splitext(basename)[0]
        # Priority 0: dep files and .env always first
        if basename in RELEVANT_FILENAMES or basename.startswith(".env"):
            return 0
        # Priority 1: security-sensitive names anywhere in the path
        path_lower = path.lower()
        if any(kw in path_lower for kw in HIGH_PRIORITY_NAMES):
            return 1
        # Priority 2: root-level files
        if path.count("/") <= 1:
            return 2
        # Priority 3: nested files
        return 3

    blobs.sort(key=lambda p: (_priority(p), p.count("/"), p))
    blobs = blobs[:MAX_FILES]

    return owner, repo, blobs


async def fetch_file_contents(owner: str, repo: str, file_paths: List[str]) -> Dict[str, str]:
    """
    Fetches file contents from GitHub API concurrently (asyncio.gather).
    Returns {path: content_string}.
    Truncates each file to MAX_LINES lines.
    """
    import asyncio

    async def _fetch_one(client: httpx.AsyncClient, path: str) -> Optional[tuple]:
        try:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                headers=_headers(),
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("encoding") == "base64":
                raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            else:
                raw = data.get("content", "")
            lines = raw.splitlines()
            if len(lines) > MAX_LINES:
                lines = lines[:MAX_LINES]
                lines.append(f"# [TRUNCATED — file has more lines, showing first {MAX_LINES}]")
            return (path, "\n".join(lines))
        except Exception:
            return None

    async with httpx.AsyncClient(timeout=30) as client:
        results = await asyncio.gather(
            *[_fetch_one(client, path) for path in file_paths],
            return_exceptions=True,
        )

    contents: Dict[str, str] = {}
    for result in results:
        if result and not isinstance(result, Exception):
            path, content = result
            contents[path] = content

    return contents


async def fetch_repository(repo_url: str) -> Tuple[str, str, Dict[str, str]]:
    """
    Convenience function: fetches tree + all file contents.
    Returns (owner, repo_name, files_dict).
    """
    owner, repo, file_paths = await fetch_repo_tree(repo_url)
    files_dict = await fetch_file_contents(owner, repo, file_paths)
    return owner, repo, files_dict
