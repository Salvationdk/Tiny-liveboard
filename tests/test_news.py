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
    assert news.parse_feed(b"<rss><channel><item><title>Test</title><category>Breaking News</category></item></channel></rss>") == [{"title": "Test", "breaking": True}]

def test_no_false_breaking():
    assert news.parse_feed(b"<rss><channel><item><title>Breaking records</title></item><item/></channel></rss>") == [{"title": "Breaking records", "breaking": False}]
