from adp.core.base import DataSource
from adp.core.registry import get_source, list_sources


def test_posoco_is_registered_and_constructs():
    assert "posoco" in list_sources()
    src = get_source("posoco")
    assert isinstance(src, DataSource)
    assert src.name == "posoco"


def test_unknown_source_raises():
    try:
        get_source("does-not-exist")
    except KeyError as e:
        assert "unknown source" in str(e)
    else:
        raise AssertionError("expected KeyError")
