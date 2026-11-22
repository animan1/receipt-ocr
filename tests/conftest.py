import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--prepare-fixture", help="Limit image preparation to this fixture ID")
