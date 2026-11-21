"""Locate the optional private fixture checkout and guard library pushes."""

import os
import shlex
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path("tests") / "fixtures"
CONFIG_KEY = "receipt-ocr.fixturesRepo"


class FixtureRepositoryError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # A hook can inherit Git variables that bind commands to the library's index and worktree.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def configured_repository(project: Path = PROJECT_ROOT) -> Path | None:
    if not (project / ".git").exists():
        return None
    config = _git(project, "config", "--local", "--get", CONFIG_KEY)
    if config.returncode == 1:
        return None
    if config.returncode:
        raise FixtureRepositoryError(f"Cannot read {CONFIG_KEY}: {config.stderr.strip()}")
    value = config.stdout.rstrip("\n")
    if not value:
        raise FixtureRepositoryError(f"{CONFIG_KEY} is set but empty.")
    repository = (project / Path(value).expanduser()).resolve()
    top = _git(repository, "rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.rstrip("\n")).resolve() != repository:
        raise FixtureRepositoryError(
            f"{CONFIG_KEY} must point to a Git worktree root: {repository}"
        )
    if repository == project.resolve():
        raise FixtureRepositoryError(f"{CONFIG_KEY} must point to a separate Git worktree.")
    return repository


def private_fixture_root(*, require_existing: bool = True) -> Path:
    repository = configured_repository()
    if repository is None:
        return PROJECT_ROOT / ".local" / FIXTURE_PATH
    root = repository / FIXTURE_PATH
    if require_existing and not root.is_dir():
        raise FixtureRepositoryError(f"Configured fixture checkout is missing {root}.")
    return root


def require_clean_repository(project: Path = PROJECT_ROOT) -> None:
    repository = configured_repository(project)
    if repository is None:
        return
    if not (repository / FIXTURE_PATH).is_dir():
        raise FixtureRepositoryError(f"Configured fixture checkout is missing {FIXTURE_PATH}.")
    status = _git(
        repository, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"
    )
    if status.returncode:
        raise FixtureRepositoryError(
            f"Cannot inspect the fixture checkout: {status.stderr.strip()}"
        )
    if status.stdout:
        raise FixtureRepositoryError(
            "The fixture checkout has uncommitted changes. Review and resolve them before pushing.\n"
            f"Inspect with: git -C {shlex.quote(str(repository))} status --short"
        )


def main() -> int:
    try:
        require_clean_repository()
    except (FixtureRepositoryError, OSError) as error:
        print(f"pre-push: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
