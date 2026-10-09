import pytest

from pm_agents.store import Store, set_store


@pytest.fixture
def store(tmp_path):
    """Store en una base temporal, registrado como el store global de las tools."""
    s = Store(tmp_path / "test.db")
    set_store(s)
    yield s
    set_store(None)
    s.cerrar()
