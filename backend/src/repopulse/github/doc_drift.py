"""Doc-drift checker.

Scans markdown files in a PR diff for relative links whose target is missing
from the post-change repo path set. Pure function; the caller is responsible
for providing the right ``repo_paths`` (post-change tree) and ``file_contents``.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

_LINK = re.compile(r"\[(?P<text>[^\]]+)\]\((?P<target>[^)\s]+)\)")


@dataclass(frozen=True)
class DocDriftReport:
    broken_refs: tuple[tuple[str, str, int], ...]


def _is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:"))


def _is_anchor_only(target: str) -> bool:
    return target.startswith("#")


def _resolve(source_file: str, target: str) -> str:
    raw = target.split("#", 1)[0]
    if not raw:
        return ""
    base = posixpath.dirname(source_file)
    joined = posixpath.join(base, raw) if base else raw
    return posixpath.normpath(joined)


def find_broken_refs(
    *,
    changed_files: list[str],
    repo_paths: set[str],
    file_contents: dict[str, str],
) -> DocDriftReport:
    broken: list[tuple[str, str, int]] = []
    for path in changed_files:
        text = file_contents.get(path)
        if text is None:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in _LINK.finditer(line):
                target = match.group("target")
                if _is_external(target) or _is_anchor_only(target):
                    continue
                resolved = _resolve(path, target)
                if not resolved or resolved in repo_paths:
                    continue
                broken.append((path, target, line_no))
    return DocDriftReport(broken_refs=tuple(broken))
