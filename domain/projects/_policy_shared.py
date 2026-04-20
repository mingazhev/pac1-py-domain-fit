from __future__ import annotations

import re

from .project import Project

def normalize_repo_path(path: object) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text.startswith("/"):
        text = f"/{text}"
    text = re.sub(r"/+", "/", text)
    if text.lower().endswith("/readme.md"):
        text = re.sub(r"/readme\.md$", "/README.MD", text, flags=re.IGNORECASE)
    return text.rstrip("/") or "/"


def project_start_date(project: Project) -> str:
    if project.start_date:
        return project.start_date
    match = re.search(
        r"/?40_projects/(\d{4})_(\d{2})_(\d{2})_[^/]+(?:/|$)",
        str(project.path or "").strip(),
    )
    if match is None:
        return ""
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


__all__ = [
    "normalize_repo_path",
    "project_start_date",
]
