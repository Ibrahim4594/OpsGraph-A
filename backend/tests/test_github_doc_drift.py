"""Tests for the doc-drift checker."""
from __future__ import annotations

from repopulse.github.doc_drift import DocDriftReport, find_broken_refs


def test_no_broken_refs_returns_empty() -> None:
    contents = {"docs/index.md": "[arch](architecture.md)\n"}
    repo_paths = {"docs/index.md", "docs/architecture.md"}
    report = find_broken_refs(
        changed_files=["docs/index.md"],
        repo_paths=repo_paths,
        file_contents=contents,
    )
    assert isinstance(report, DocDriftReport)
    assert report.broken_refs == ()


def test_broken_relative_link_detected() -> None:
    contents = {"docs/index.md": "see [old](old-arch.md) please\n"}
    repo_paths = {"docs/index.md"}
    report = find_broken_refs(
        changed_files=["docs/index.md"],
        repo_paths=repo_paths,
        file_contents=contents,
    )
    assert report.broken_refs == (("docs/index.md", "old-arch.md", 1),)


def test_anchor_only_link_skipped() -> None:
    contents = {"docs/index.md": "[top](#top)\n"}
    report = find_broken_refs(
        changed_files=["docs/index.md"],
        repo_paths={"docs/index.md"},
        file_contents=contents,
    )
    assert report.broken_refs == ()


def test_external_http_link_skipped() -> None:
    contents = {"docs/index.md": "[ext](https://example.com/x.md)\n"}
    report = find_broken_refs(
        changed_files=["docs/index.md"],
        repo_paths={"docs/index.md"},
        file_contents=contents,
    )
    assert report.broken_refs == ()


def test_link_with_anchor_resolves_against_path() -> None:
    contents = {"docs/a.md": "[b](b.md#section)\n"}
    report = find_broken_refs(
        changed_files=["docs/a.md"],
        repo_paths={"docs/a.md", "docs/b.md"},
        file_contents=contents,
    )
    assert report.broken_refs == ()


def test_multiple_broken_refs_with_line_numbers() -> None:
    contents = {"docs/a.md": "header\n[x](x.md)\n[y](y.md)\n"}
    report = find_broken_refs(
        changed_files=["docs/a.md"],
        repo_paths={"docs/a.md"},
        file_contents=contents,
    )
    assert report.broken_refs == (
        ("docs/a.md", "x.md", 2),
        ("docs/a.md", "y.md", 3),
    )


def test_files_outside_changed_set_are_skipped() -> None:
    contents = {
        "docs/a.md": "[bad](missing.md)\n",
        "docs/b.md": "[also-bad](missing.md)\n",
    }
    report = find_broken_refs(
        changed_files=["docs/a.md"],  # b.md is not in the diff
        repo_paths={"docs/a.md", "docs/b.md"},
        file_contents=contents,
    )
    assert report.broken_refs == (("docs/a.md", "missing.md", 1),)


def test_changed_file_with_no_contents_is_skipped() -> None:
    report = find_broken_refs(
        changed_files=["docs/missing.md"],
        repo_paths=set(),
        file_contents={},
    )
    assert report.broken_refs == ()


def test_mailto_link_skipped() -> None:
    contents = {"docs/a.md": "[mail](mailto:foo@bar.com)\n"}
    report = find_broken_refs(
        changed_files=["docs/a.md"],
        repo_paths={"docs/a.md"},
        file_contents=contents,
    )
    assert report.broken_refs == ()


def test_relative_path_resolves_to_repo_root() -> None:
    # `docs/sub/page.md` linking `../top.md` resolves to `docs/top.md`.
    contents = {"docs/sub/page.md": "[up](../top.md)\n"}
    report = find_broken_refs(
        changed_files=["docs/sub/page.md"],
        repo_paths={"docs/sub/page.md", "docs/top.md"},
        file_contents=contents,
    )
    assert report.broken_refs == ()
