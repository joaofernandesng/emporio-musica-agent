import pytest

from emporio.build_db import build, connect


@pytest.fixture(scope="session")
def conn(tmp_path_factory):
    """A store database built from the raw CSVs into a temporary file."""
    path = build(tmp_path_factory.mktemp("db") / "store.db")
    connection = connect(path)
    yield connection
    connection.close()
