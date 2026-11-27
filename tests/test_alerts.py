import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

def load():
    for name in ("homeassistant","homeassistant.helpers","homeassistant.helpers.aiohttp_client"):
        sys.modules.setdefault(name, MagicMock())
    root = Path(__file__).parents[1] / "custom_components/tiny_liveboard"
    package = ModuleType("alert_fixture")
    package.__path__ = [str(root)]
    sys.modules[package.__name__] = package
    return importlib.import_module("alert_fixture.alerts")

def test_atom_polygon():
    alerts = load()
    data = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2"><entry><id>1</id><title>Wind</title><cap:status>Actual</cap:status><cap:message_type>Alert</cap:message_type><cap:scope>Public</cap:scope><cap:severity>Severe</cap:severity><cap:polygon>55,10 56,10 56,11 55,10</cap:polygon></entry></feed>'''
    result = alerts.parse_alerts(data)
    assert len(result) == 1
    assert result[0]["severity"] == "Severe"
    assert result[0]["geometry"]["coordinates"][0][0][0] == [10,55]

def test_empty_feed():
    assert load().parse_alerts(b'<feed xmlns="http://www.w3.org/2005/Atom"/>') == []


def test_unknown_format_is_not_empty_success():
    import pytest
    with pytest.raises(ValueError):
        load().parse_alerts(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Unknown</title></entry></feed>')
