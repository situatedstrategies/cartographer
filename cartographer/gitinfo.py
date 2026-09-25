"""Git identity for a session's working directory.

A project is a repository. Its id is the normalized remote URL when there is
one (so the same repo cloned twice is one project) and otherwise the
repository root path. Branches are recorded per session and per step.
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Dict, List, Optional

_cache: Dict[str, Dict[str, Any]] = {}


def _git(cwd: str, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def normalize_remote(url: str) -> str:
    """git@github.com:me/app.git, https://github.com/me/app.git and
    ssh://git@github.com/me/app all become github.com/me/app."""
    u = url.strip()
    u = re.sub(r"^[a-z+]+://", "", u)          # scheme
    u = re.sub(r"^[^@/]+@", "", u)              # user@
    u = u.replace(":", "/", 1) if re.match(r"^[^/]+:[^/]", u) else u
    u = re.sub(r"\.git/?$", "", u)
    return u.lower().rstrip("/")


def inspect(cwd: Optional[str], identity: str = "git") -> Dict[str, Any]:
    """Describe the project a directory belongs to. Works for directories
    that no longer exist (retrospective maps) by falling back to the path."""
    key = "%s|%s" % (cwd or "", identity)
    if key in _cache:
        return _cache[key]
    info: Dict[str, Any] = {"root": None, "name": None, "remote": None, "id": None, "branch": None,
                            "branches": [], "exists": bool(cwd and os.path.isdir(cwd)), "kind": "folder"}
    if cwd:
        root = _git(cwd, "rev-parse", "--show-toplevel") if info["exists"] and identity == "git" else None
        if root:
            info.update(root=root, kind="git", name=os.path.basename(root.rstrip("/")))
            remote = _git(root, "config", "--get", "remote.origin.url")
            if remote:
                info["remote"] = remote
                info["id"] = normalize_remote(remote)
                info["name"] = info["id"].rsplit("/", 1)[-1]
            else:
                info["id"] = "local:" + root
            info["branch"] = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
            branches = _git(root, "branch", "--format=%(refname:short)", "--sort=-committerdate")
            info["branches"] = [b for b in (branches or "").splitlines() if b][:20]
        else:
            path = os.path.abspath(cwd)
            info.update(root=path, name=os.path.basename(path.rstrip("/")) or path, id="local:" + path)
    _cache[key] = info
    return info


def project_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "project").lower()).strip("-")
    return slug or "project"
