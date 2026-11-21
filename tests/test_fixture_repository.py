import subprocess
from pathlib import Path

import pytest

from tests.fixture_repository import (
    CONFIG_KEY,
    FIXTURE_PATH,
    FixtureRepositoryError,
    configured_repository,
    require_clean_repository,
)


def git(repository: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *args],
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def library(tmp_path: Path) -> Path:
    project = tmp_path / "library"
    project.mkdir()
    git(project, "init", "-q", "-b", "test-library")
    return project


@pytest.fixture
def companion(library: Path) -> Path:
    repository = library.parent / "fixture repository"
    repository.mkdir()
    git(repository, "init", "-q", "-b", "test-fixtures")
    fixtures = repository / FIXTURE_PATH
    fixtures.mkdir(parents=True)
    (fixtures / "fixture.txt").write_text("original", encoding="utf-8")
    git(repository, "add", str(FIXTURE_PATH / "fixture.txt"))
    git(
        repository,
        "-c",
        "user.name=Fixture Tests",
        "-c",
        "user.email=fixtures@example.invalid",
        "commit",
        "-qm",
        "Add test fixture",
    )
    git(library, "config", "--local", CONFIG_KEY, "../fixture repository")
    return repository


def test_unconfigured_checkout_allows_push(library: Path) -> None:
    assert configured_repository(library) is None
    require_clean_repository(library)


def test_clean_configured_checkout_allows_push(
    library: Path, companion: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_DIR", str(library / ".git"))
    assert configured_repository(library) == companion.resolve()
    require_clean_repository(library)


@pytest.mark.parametrize("change", ["unstaged", "staged", "untracked"])
def test_dirty_fixture_checkout_blocks_push(library: Path, companion: Path, change: str) -> None:
    fixture = FIXTURE_PATH / ("new.txt" if change == "untracked" else "fixture.txt")
    (companion / fixture).write_text("changed", encoding="utf-8")
    if change == "staged":
        git(companion, "add", str(fixture))

    with pytest.raises(FixtureRepositoryError, match="uncommitted changes"):
        require_clean_repository(library)


def test_configured_path_must_be_checkout_root(library: Path, companion: Path) -> None:
    git(library, "config", "--local", CONFIG_KEY, str(companion / FIXTURE_PATH))

    with pytest.raises(FixtureRepositoryError, match="Git worktree root"):
        require_clean_repository(library)
