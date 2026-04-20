from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectSnapshotIdentity:
    root_path: str = ""
    snapshot_slug: str = ""
    snapshot_date: str | None = None

    def authorized_start_date(self, explicit_start_date: str | None = None) -> str | None:
        explicit = str(explicit_start_date or "").strip() or None
        if explicit:
            return explicit
        return self.snapshot_date

    def explicit_start_date(self, explicit_start_date: str | None = None) -> str | None:
        explicit = str(explicit_start_date or "").strip() or None
        return explicit

    @property
    def version_marker(self) -> str | None:
        return self.snapshot_date

    @property
    def is_snapshot_derived(self) -> bool:
        return bool(self.snapshot_date or self.snapshot_slug)


def _parse_iso_date(value: object) -> str | None:
    text = str(value or "").strip()
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None


@dataclass(frozen=True, slots=True)
class ProjectVersionIdentity:
    explicit_start_date: str | None = None
    snapshot_identity: ProjectSnapshotIdentity = ProjectSnapshotIdentity()

    @property
    def is_authoritative(self) -> bool:
        return self.explicit_start_date is not None

    @property
    def authoritative_start_date(self) -> str | None:
        return self.explicit_start_date

    @property
    def version_marker(self) -> str | None:
        return self.snapshot_identity.snapshot_date

    @property
    def effective_start_date(self) -> str | None:
        if self.explicit_start_date:
            return self.explicit_start_date
        return self.snapshot_identity.snapshot_date

    @property
    def provenance(self) -> str:
        if self.explicit_start_date:
            return "explicit"
        if self.snapshot_identity.snapshot_date:
            return "snapshot"
        return "unknown"


def build_project_version_identity(
    *,
    explicit_start_date: object = None,
    snapshot_identity: ProjectSnapshotIdentity | None = None,
) -> ProjectVersionIdentity:
    return ProjectVersionIdentity(
        explicit_start_date=_parse_iso_date(explicit_start_date),
        snapshot_identity=snapshot_identity or ProjectSnapshotIdentity(),
    )


def parse_project_snapshot_identity(*paths: object) -> ProjectSnapshotIdentity:
    for candidate in paths:
        text = str(candidate or "").strip().replace("\\", "/")
        if not text:
            continue
        match = re.search(r"(40_projects/\d{4}_\d{2}_\d{2}_([^/]+))(?:/|$)", text)
        if match is None:
            continue
        root_path, slug = match.groups()
        date_match = re.search(r"(\d{4})_(\d{2})_(\d{2})_", root_path)
        snapshot_date = None
        if date_match is not None:
            year, month, day = date_match.groups()
            snapshot_date = f"{year}-{month}-{day}"
        return ProjectSnapshotIdentity(
            root_path=root_path,
            snapshot_slug=slug,
            snapshot_date=snapshot_date,
        )
    return ProjectSnapshotIdentity()
