import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.modules["homeassistant"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.aiohttp_client"] = MagicMock()
spec = importlib.util.spec_from_file_location("news", Path(__file__).parents[1] / "custom_components/tiny_liveboard/news.py")
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)

def test_explicit_breaking():
    assert news.parse_feed(b"<rss><channel><item><title>Test</title><category>Breaking News</category></item></channel></rss>")[0]["breaking"]

def test_no_false_breaking():
    items = news.parse_feed(b"<rss><channel><item><title>Breaking records</title></item><item/></channel></rss>")
    assert len(items) == 1 and not items[0]["breaking"]

def test_atom():
    items = news.parse_feed(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Test</title><category term="breaking"/><published>2026-01-01T00:00:00Z</published></entry></feed>')
    assert items[0]["breaking"] and items[0]["published"]

def test_expiry_and_deduplication():
    engine = news.NewsEngine(None)
    engine.items = {"DR": [{"title": "Test!", "breaking": True, "published": 1000, "received": 1000}], "TV 2": [{"title": "Test", "breaking": False, "published": 1000, "received": 1000}]}
    assert len(engine.combined(["DR", "TV 2"], 1100)) == 1
    assert engine.combined(["DR"], 1100)[0]["breaking"]
    assert not engine.combined(["DR"], 4700)[0]["breaking"]
    assert not engine.combined(["DR"], 200000)

def test_undated_never_breaking():
    engine = news.NewsEngine(None)
    engine.items = {"DR": [{"title": "Test", "breaking": True, "published": None, "received": 1000}]}
    assert not engine.combined(["DR"], 1100)[0]["breaking"]


def test_failed_source_never_breaking():
    engine = news.NewsEngine(None)
    engine.items = {"DR": [{"source": "DR", "title": "Test", "breaking": True, "published": 1000, "received": 1000}]}
    engine.status = {"DR": {"ok": False}}
    assert not engine.combined(["DR"], 1100)[0]["breaking"]

def test_distinct_unicode_headlines():
    engine = news.NewsEngine(None)
    engine.items = {"DR": [{"title": title, "breaking": False, "published": 1000, "received": 1000} for title in ["Ændring i Kalundborg", "Nyhed i Roskilde"]]}
    assert len(engine.combined(["DR"], 1100)) == 2
