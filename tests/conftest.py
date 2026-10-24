import pytest

from legacyagents.gateway import LegacyGateway
from legacyagents.tools import LegacyTools


@pytest.fixture
def gw(tmp_path):
    return LegacyGateway(tmp_path, rate=10000, burst=10000)


@pytest.fixture
def tools(gw):
    with LegacyTools(gw) as t:
        yield t
