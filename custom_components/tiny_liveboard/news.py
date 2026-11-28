"""Bounded, independent RSS cache and conservative breaking-news policy."""
import asyncio
import time
import logging
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, quote_plus
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from defusedxml import ElementTree
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
SOURCES = {
    "DR": "https://www.dr.dk/nyheder/service/feeds/allenyheder",
    "TV 2": "https://feeds.services.tv2.dk/api/feeds/nyheder/rss",
    "TV2 ØST": "https://news.google.com/rss/search?q=site%3Atv2east.dk+OR+site%3Atv2%C3%B8st.dk&hl=da&gl=DK&ceid=DK:da",
    "Kalundborg": "https://news.google.com/rss/search?q=Kalundborg&hl=da&gl=DK&ceid=DK:da",
    "P4 Sjælland": "https://www.dr.dk/nyheder/service/feeds/regionale/sjaelland",
    "Lokale medier": "https://news.google.com/rss/search?q=Kalundborg+%28site%3Asn.dk+OR+site%3Akalundborgnetavis.dk%29&hl=da&gl=DK&ceid=DK:da",
}
DEFAULT_SOURCES = list(SOURCES)[:4]
# Google News discovery feeds, not publisher-operated RSS endpoints.
for name, domain in {
    "Ekstra Bladet": "ekstrabladet.dk", "B.T.": "bt.dk",
    "Politiken": "politiken.dk", "Berlingske": "berlingske.dk",
    "Jyllands-Posten": "jyllands-posten.dk", "Information": "information.dk",
    "TV 2 Fyn": "tv2fyn.dk", "TV 2 Nord": "tv2nord.dk",
    "TV 2 Østjylland": "tv2ostjylland.dk", "TV MIDTVEST": "tvmidtvest.dk",
    "TV SYD": "tvsyd.dk", "SN.dk": "sn.dk", "Version2": "version2.dk",
    "Ingeniøren": "ing.dk", "Computerworld": "computerworld.dk",
    "Recordere.dk": "recordere.dk", "Videnskab.dk": "videnskab.dk",
    "Politiet": "politi.dk", "Via Ritzau": "via.ritzau.dk",
    "BeredskabsInfo": "beredskabsinfo.dk", "Danmarks Statistik": "dst.dk",
}.items():
    SOURCES[name] = "https://news.google.com/rss/search?q=" + quote_plus("site:" + domain) + "&hl=da&gl=DK&ceid=DK:da"
for label, query in {"DR Politik":"politik","DR Indland":"indland","DR Udland":"udland","DR Viden":"viden"}.items():
    SOURCES[label] = "https://news.google.com/rss/search?q=" + quote_plus("site:dr.dk/nyheder/" + query) + "&hl=da&gl=DK&ceid=DK:da"

TTL = 300
FAILURE_TTL = 60
BREAKING_TTL = 3600
MAX_AGE = 48 * 3600
MAX_BYTES = 1024 * 1024

def timestamp(value):
    if not value:
        return None
    try:
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None

class NewsText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ("p", "br", "div", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def news_text(value):
    parser = NewsText()
    parser.feed((value or "")[:40000])
    return "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip())[:12000]

def parse_feed(payload):
    root = ElementTree.fromstring(payload)
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    if root.tag not in ("rss", "feed", "RDF"):
        raise ValueError("Unrecognized news feed")
    if root.tag == "rss" and root.find("channel") is None:
        raise ValueError("Missing RSS channel")
    items = []
    for item in root.findall(".//item") + root.findall(".//entry"):
        title = " ".join((item.findtext("title") or "").split())
        if not title:
            continue
        categories = [(c.get("term") or c.text or "").strip().casefold() for c in item.findall("category")]
        published = timestamp(item.findtext("pubDate") or item.findtext("published") or item.findtext("updated"))
        publisher = item.findtext("source") or ""
        body = news_text(item.findtext("encoded") or item.findtext("content") or item.findtext("description") or item.findtext("summary"))
        link = item.findtext("link") or next((n.get("href", "") for n in item.findall("link") if n.get("rel", "alternate") == "alternate"), "")
        try:
            u = urlsplit(link.strip())
            link = link.strip()[:2048] if u.scheme in ("https", "http") and u.hostname and not u.username and not u.password else ""
        except ValueError:
            link = ""
        items.append({"url": link, "publisher": publisher[:100], "body": body, "title": title[:300], "breaking": bool(set(categories) & {"breaking news", "breaking"}), "published": published})
    return items[:50]

def settings(config):
    sources = config.get("sources", DEFAULT_SOURCES)
    if not isinstance(sources, list):
        sources = DEFAULT_SOURCES
    return [name for name in SOURCES if name in sources]

class NewsEngine:
    def __init__(self, hass):
        self.hass = hass
        self.items = {}
        self.updated = {}
        self.status = {}
        self.lock = asyncio.Lock()

    async def get(self, selected=None):
        selected = DEFAULT_SOURCES if selected is None else [s for s in SOURCES if s in selected]
        async with self.lock:
            now = time.monotonic()
            await asyncio.gather(*(self.fetch(name, SOURCES[name]) for name in selected
                                   if now - self.updated.get(name, -TTL) >= (TTL if self.status.get(name, {}).get("ok", True) else FAILURE_TTL)))
            return self.combined(selected)

    def combined(self, selected, now=None):
        now = time.time() if now is None else now
        result = []
        seen = set()
        groups = [self.items.get(name, []) for name in selected]
        for i in range(50):
            for source, group in zip(selected, groups):
                if i >= len(group):
                    continue
                item = group[i]
                age = now - (item["published"] if item["published"] is not None else item["received"])
                if age > MAX_AGE or age < -300:
                    continue
                key = re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", item["title"]).casefold()).strip()
                if key in seen:
                    continue
                seen.add(key)
                result.append(dict(item, breaking=bool(self.status.get(item.get("source") or source, {}).get("ok", True) and item["breaking"] and item["published"] is not None and 0 <= age <= BREAKING_TTL)))
        return sorted(result, key=lambda item: (not item["breaking"], -(item["published"] if item["published"] is not None else item["received"])))[:60]

    async def fetch(self, name, url):
        self.updated[name] = time.monotonic()
        try:
            session = async_get_clientsession(self.hass)
            async with asyncio.timeout(15):
                for redirect in range(4):
                    async with session.get(url, allow_redirects=False) as response:
                        if response.status in (301,302,303,307,308):
                            target = urljoin(url, response.headers.get("Location", ""))
                            old, new = urlsplit(url), urlsplit(target)
                            if new.scheme != "https" or new.hostname != old.hostname or new.username or new.password or new.port not in (None,443):
                                raise ValueError("Unsafe feed redirect")
                            url = target
                            continue
                        if response.status != 200:
                            raise ValueError(f"HTTP {response.status}")
                        chunks = bytearray()
                        async for chunk in response.content.iter_chunked(16384):
                            chunks.extend(chunk)
                            if len(chunks) > MAX_BYTES:
                                raise ValueError("Feed too large")
                        break
                else:
                    raise ValueError("Too many feed redirects")
            parsed = await self.hass.async_add_executor_job(parse_feed, bytes(chunks))
            previous = {item["title"]: item["received"] for item in self.items.get(name, [])}
            self.items[name] = [dict(item, source=name, received=previous.get(item["title"], time.time())) for item in parsed]
            self.status[name] = {"ok": True, "count": len(parsed), "checked": time.time(), "last_success": time.time()}
        except Exception as exc:
            self.status[name] = {"ok": False, "checked": time.time(), "error": str(exc)[:160] or type(exc).__name__, "last_success": self.status.get(name, {}).get("last_success"), "cached_count": len(self.items.get(name, []))}
            _LOGGER.debug("News source %s unavailable: %s", name, type(exc).__name__)

class ArticleMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = {}
        self.article_depth = 0
        self.paragraph = None
        self.paragraphs = []
        self.restricted = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article":
            self.article_depth += 1
        if self.article_depth and tag in ("p", "h2", "h3"):
            self.paragraph = []
        if "paywall" in (a.get("class") or "").lower() or a.get("itemprop") == "isAccessibleForFree" and a.get("content", "").lower() == "false":
            self.restricted = True
        if tag != "meta":
            return
        key = a.get("property") or a.get("name")
        if key in ("og:description", "description", "twitter:description", "og:image"):
            self.values.setdefault(key, a.get("content", "")[:4000])

    def handle_data(self, data):
        if self.paragraph is not None:
            self.paragraph.append(data)

    def handle_endtag(self, tag):
        if tag in ("p", "h2", "h3") and self.paragraph is not None:
            value = " ".join("".join(self.paragraph).split())
            if value:
                self.paragraphs.append(value)
            self.paragraph = None
        if tag == "article":
            self.article_depth = max(0, self.article_depth - 1)

def parse_article_metadata(payload):
    parser = ArticleMetadata()
    parser.feed(payload.decode("utf-8", errors="replace"))
    description = news_text(parser.values.get("og:description") or parser.values.get("description") or parser.values.get("twitter:description"))
    # Extract only visible article markup on the public broadcaster.
    # Do not extract hidden JSON article bodies or subscription content.
    return {"body": description, "article": "" if parser.restricted else "\n\n".join(parser.paragraphs)[:40000], "image": parser.values.get("og:image", "")}

async def article_metadata(hass, url):
    # Only explicitly trusted public publisher hosts; never follow redirects.
    u = urlsplit(url)
    if u.scheme != "https" or u.hostname not in ("www.dr.dk", "dr.dk", "nyheder.tv2.dk", "www.tv2.dk", "tv2.dk") or u.username or u.password or u.port not in (None, 443):
        return {}
    session = async_get_clientsession(hass)
    async with asyncio.timeout(10):
        async with session.get(url, allow_redirects=False) as response:
            if response.status != 200 or "text/html" not in response.headers.get("Content-Type", ""):
                return {}
            chunks = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                chunks.extend(chunk)
                if len(chunks) >= MAX_BYTES:
                    break
    result = await hass.async_add_executor_job(parse_article_metadata, bytes(chunks))
    if u.hostname not in ("www.dr.dk", "dr.dk"):
        result.pop("article", None)
    return result
