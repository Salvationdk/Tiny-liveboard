"""Bounded, independent RSS cache and conservative breaking-news policy."""
import asyncio
import aiohttp
import hashlib
import json
import base64
import socket
import ipaddress
import time
import logging
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, quote_plus
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from defusedxml import ElementTree

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

def parse_feed(payload, base_url=""):
    root = ElementTree.fromstring(payload)
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    if root.tag not in ("rss", "feed", "RDF"):
        raise ValueError("Unrecognized news feed")
    if root.tag == "rss" and root.find("channel") is None:
        raise ValueError("Missing RSS channel")
    items = []
    for item in (root.findall(".//item") + root.findall(".//entry"))[:100]:
        title = " ".join((item.findtext("title") or "").split())
        if not title:
            continue
        categories = [(c.get("term") or c.text or "").strip().casefold() for c in item.findall("category")]
        published = timestamp(item.findtext("pubDate") or item.findtext("published") or item.findtext("date"))
        publisher = item.findtext("source/name") or item.findtext("source/title") or item.findtext("source") or ""
        body = news_text(item.findtext("encoded") or item.findtext("content") or item.findtext("description") or item.findtext("summary"))
        link = item.findtext("link") or next((n.get("href", "") for n in item.findall("link") if n.get("rel", "alternate") == "alternate"), "")
        link = urljoin(base_url, link.strip()) if link.strip() else ""
        try:
            u = urlsplit(link.strip())
            link = link.strip() if len(link.strip()) <= 2048 and u.scheme in ("https", "http") and u.hostname and not u.username and not u.password else ""
        except ValueError:
            link = ""
        image = next((n.get("url", "") for n in item.iter() if n.tag in ("thumbnail", "enclosure", "content") and (n.tag == "thumbnail" or (n.get("type") or "").startswith("image/") or n.get("medium") == "image")), "")
        image = public_url(urljoin(base_url, image)) if image else ""
        items.append({"image": image, "url": link, "publisher": publisher[:100], "body": body, "title": title[:300], "breaking": bool(set(categories) & {"breaking news", "breaking"}), "published": published})
    return items[:50]

def public_url(value):
    """Accept public HTTPS URLs without credentials or unusual ports."""
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        return ""
    try:
        url = urlsplit(value)
        host = url.hostname
        if url.scheme != "https" or not host or url.username or url.password or url.port not in (None, 443):
            return ""
        if "." not in host or host.rstrip(".").endswith((".local", ".localhost", ".internal", ".home.arpa")):
            return ""
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return value
    except ValueError:
        pass
    return ""


def routable(address):
    ip = ipaddress.ip_address(address)
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


class PublicResolver(aiohttp.abc.AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        records = await asyncio.get_running_loop().getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
        if not records or any(not routable(r[4][0]) for r in records):
            raise ValueError("Non-public feed address")
        return [{"hostname":host,"host":r[4][0],"port":port,"family":r[0],"proto":r[2],"flags":socket.AI_NUMERICHOST} for r in records]
    async def close(self):
        pass

def custom_sources(config):
    result = {}
    for line in str(config.get("customNewsFeeds", "")).splitlines()[:20]:
        name, sep, url = line.partition("|")
        name, url = name.strip(), url.strip()
        if sep and name and len(name) <= 80 and public_url(url):
            result["Egen: " + name + " · " + hashlib.sha256(url.encode()).hexdigest()[:10]] = url
    return result

def settings(config):
    sources = config.get("sources", DEFAULT_SOURCES)
    if not isinstance(sources, list):
        sources = DEFAULT_SOURCES
    return {**{name: SOURCES[name] for name in SOURCES if name in sources}, **custom_sources(config)}

class NewsEngine:
    def __init__(self, hass):
        self.hass = hass
        self.items = {}
        self.updated = {}
        self.status = {}
        self.urls = {}
        self.lock = asyncio.Lock()
        self.fetch_slots = asyncio.Semaphore(8)
        self.metadata_slots = asyncio.Semaphore(4)

    def find(self, url, selected):
        return next((item for name in selected for item in self.items.get(name, []) if item.get("url") == url and url), None)

    async def get(self, selected=None):
        selected = {s:SOURCES[s] for s in DEFAULT_SOURCES} if selected is None else selected
        if not isinstance(selected, dict):
            selected = {s:SOURCES[s] for s in selected if s in SOURCES}
        async with self.lock:
            now = time.monotonic()
            for name, url in selected.items():
                if self.urls.get(name) != url:
                    self.items.pop(name, None)
                    self.updated.pop(name, None)
                    self.urls[name] = url
            await asyncio.gather(*(self.fetch(name, selected[name]) for name in selected
                                   if now - self.updated.get(name, -TTL) >= (TTL if self.status.get(name, {}).get("ok", True) else FAILURE_TTL)))
            for name in sorted(self.updated, key=self.updated.get):
                if len(self.updated) <= max(96, len(selected)):
                    break
                if name not in selected:
                    for cache in (self.items, self.updated, self.status, self.urls):
                        cache.pop(name, None)
            return self.combined(selected)

    def combined(self, selected, now=None):
        now = time.time() if now is None else now
        result = []
        seen = set()
        seen_urls = set()
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
                url = item.get("url", "").partition("#")[0]
                if key in seen or (url and url in seen_urls):
                    continue
                seen.add(key)
                if url:
                    seen_urls.add(url)
                public = {key: value for key, value in item.items() if key != "_metadata"}
                result.append(dict(public, breaking=bool(self.status.get(source, {}).get("ok", True) and item["breaking"] and item["published"] is not None and 0 <= age <= BREAKING_TTL)))
        return sorted(result, key=lambda item: (not item["breaking"], -(item["published"] if item["published"] is not None else item["received"])))[:60]

    async def metadata(self, item, selected):
        if "_metadata" in item:
            return item["_metadata"]
        async with self.metadata_slots:
            if "_metadata" not in item:
                item["_metadata"] = await article_metadata(self.hass, item["url"], selected.values())
        return item["_metadata"]

    async def fetch(self, name, url):
        async with self.fetch_slots:
            await self._fetch(name, url)

    async def _fetch(self, name, url):
        self.updated[name] = time.monotonic()
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False), trust_env=False) as session, asyncio.timeout(15):
                for redirect in range(4):
                    async with session.get(url, allow_redirects=False) as response:
                        if response.status in (301,302,303,307,308):
                            target = urljoin(url, response.headers.get("Location", ""))
                            old, new = urlsplit(url), urlsplit(target)
                            if not public_url(target) or new.hostname != old.hostname or target == url:
                                raise ValueError("Unsafe feed redirect")
                            url = target
                            continue
                        if response.status != 200:
                            raise ValueError(f"HTTP {response.status}")
                        content_type = response.content_type
                        chunks = bytearray()
                        async for chunk in response.content.iter_chunked(16384):
                            chunks.extend(chunk)
                            if len(chunks) > MAX_BYTES:
                                raise ValueError("Feed too large")
                        break
                else:
                    raise ValueError("Too many feed redirects")
            parser = parse_html_source if content_type in ("text/html", "application/xhtml+xml") else parse_feed
            parsed = await self.hass.async_add_executor_job(parser, bytes(chunks), url)
            previous = {item["title"]: item for item in self.items.get(name, [])}
            self.items[name] = [dict(item, source=name.split(" · ")[0] if name.startswith("Egen: ") else name, received=previous.get(item["title"], {}).get("received", time.time())) for item in parsed]
            self.status[name] = {"ok": True, "count": len(parsed), "checked": time.time(), "last_success": time.time()}
        except Exception as exc:
            self.status[name] = {"ok": False, "checked": time.time(), "error": str(exc)[:100] if type(exc) is ValueError else type(exc).__name__, "last_success": self.status.get(name, {}).get("last_success"), "cached_count": len(self.items.get(name, []))}
            _LOGGER.debug("News source %s unavailable: %s", name, type(exc).__name__)

class ArticleMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = {}
        self.article_depth = 0
        self.paragraph = None
        self.paragraphs = []
        self.restricted = False
        self.explicit_free = False
        self.skip_tags = []
        self.ld_parts = None
        self.ld_documents = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self.ld_parts = []
        if a.get("itemprop") == "isAccessibleForFree":
            value = (a.get("content") or "").lower()
            self.explicit_free |= value == "true"
            self.restricted |= value == "false"
        if re.search(r"paywall|subscriber.only|premium.content", " ".join((a.get("class") or "", a.get("id") or "")), re.I):
            self.restricted = True
        if self.skip_tags:
            if tag not in ("area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"):
                self.skip_tags.append(tag)
            return
        if tag in ("script","style","nav","aside","footer","template","noscript") or "hidden" in a or a.get("aria-hidden") == "true" or re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", a.get("style") or "", re.I):
            if tag not in ("img","input","meta","link","br","hr","source"):
                self.skip_tags.append(tag)
            return
        if tag == "article":
            self.article_depth += 1
        if self.article_depth and tag in ("p", "h2", "h3"):
            self.paragraph = []
        if "paywall" in (a.get("class") or "").lower() or a.get("itemprop") == "isAccessibleForFree" and a.get("content", "").lower() == "false":
            self.restricted = True
        if tag != "meta":
            return
        key = a.get("property") or a.get("name")
        if key in ("og:description", "description", "twitter:description", "og:image", "og:title", "og:site_name", "article:published_time"):
            self.values.setdefault(key, a.get("content", "")[:4000])

    def handle_data(self, data):
        if self.ld_parts is not None:
            self.ld_parts.append(data)
        if not self.skip_tags and self.paragraph is not None:
            self.paragraph.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.ld_parts is not None:
            try:
                self.ld_documents.append(json.loads("".join(self.ld_parts)))
            except (ValueError, RecursionError):
                pass
            self.ld_parts = None
        if self.skip_tags:
            if tag in self.skip_tags:
                while self.skip_tags.pop() != tag:
                    pass
            return
        if tag in ("p", "h2", "h3") and self.paragraph is not None:
            value = " ".join("".join(self.paragraph).split())
            if value:
                self.paragraphs.append(value)
            self.paragraph = None
        if tag == "article":
            self.article_depth = max(0, self.article_depth - 1)

def article_nodes(documents):
    pending = list(documents)
    for _ in range(1000):
        if not pending:
            break
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(node[:100])
        elif isinstance(node, dict):
            kinds = node.get("@type", [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if isinstance(kinds, list) and any(k in ("Article", "NewsArticle", "ReportageNewsArticle", "BlogPosting", "AnalysisNewsArticle") for k in kinds):
                yield node
            for key in ("@graph", "mainEntity", "hasPart", "itemListElement", "item"):
                if key in node:
                    pending.append(node[key])

def parse_article_metadata(payload):
    parser = ArticleMetadata()
    parser.feed(payload.decode("utf-8", errors="replace"))
    nodes = list(article_nodes(parser.ld_documents))
    def access(value):
        return str(value).lower()
    restricted = parser.restricted or any(access(n.get("isAccessibleForFree")) == "false" for n in nodes)
    for n in nodes:
        parts = n.get("hasPart", [])
        parts = [parts] if isinstance(parts, dict) else parts
        if isinstance(parts, list) and any(isinstance(p, dict) and access(p.get("isAccessibleForFree")) == "false" for p in parts):
            restricted = True
    explicit_free = parser.explicit_free or any(access(n.get("isAccessibleForFree")) == "true" for n in nodes)
    description = news_text(parser.values.get("og:description") or parser.values.get("description") or parser.values.get("twitter:description"))
    image = parser.values.get("og:image", "")
    published = timestamp(parser.values.get("article:published_time"))
    visible = "\n\n".join(dict.fromkeys(parser.paragraphs))[:40000]
    candidates = [(visible, "html")]
    title = parser.values.get("og:title", "")
    publisher = parser.values.get("og:site_name", "")
    for n in nodes:
        if not title and isinstance(n.get("headline"), str):
            title = n["headline"]
        if not publisher and isinstance(n.get("publisher"), dict) and isinstance(n["publisher"].get("name"), str):
            publisher = n["publisher"]["name"]
        if not description and isinstance(n.get("description"), str):
            description = news_text(n["description"])
        if published is None and isinstance(n.get("datePublished"), str):
            published = timestamp(n["datePublished"])
        if not image:
            value = n.get("image")
            if isinstance(value, list):
                value = next(iter(value), "")
            if isinstance(value, dict):
                value = value.get("url") or value.get("contentUrl")
            if isinstance(value, str):
                image = value
        if not restricted and access(n.get("isAccessibleForFree")) == "true" and isinstance(n.get("articleBody"), str):
            candidates.append((news_text(n["articleBody"]), "json-ld"))
    article, source = max(candidates, key=lambda pair: len(pair[0]))
    return {"title": news_text(title)[:300], "publisher": news_text(publisher)[:100], "body": description, "article": "" if restricted else article, "image": image, "published": published, "explicit_free": explicit_free, "article_source": source if article and not restricted else "summary"}

def parse_html_source(payload, base_url):
    """Read published metadata from an article or a structured article listing."""
    parser = ArticleMetadata()
    parser.feed(payload.decode("utf-8", errors="replace"))
    items = []
    for node in article_nodes(parser.ld_documents):
        title = node.get("headline") or node.get("name")
        link = node.get("url") or node.get("mainEntityOfPage") or node.get("@id")
        if isinstance(link, dict):
            link = link.get("@id") or link.get("url")
        if not isinstance(title, str) or not isinstance(link, str):
            continue
        url = public_url(urljoin(base_url, link))
        if not url or urlsplit(url).hostname != urlsplit(base_url).hostname:
            continue
        description = node.get("description")
        image = node.get("image")
        if isinstance(image, list):
            image = next(iter(image), "")
        if isinstance(image, dict):
            image = image.get("url") or image.get("contentUrl")
        publisher = node.get("publisher")
        publisher = publisher.get("name", "") if isinstance(publisher, dict) else ""
        published = node.get("datePublished")
        items.append({
            "title": news_text(title)[:300], "url": url,
            "image": public_url(urljoin(base_url, image)) if isinstance(image, str) and image else "",
            "body": news_text(description) if isinstance(description, str) else "",
            "publisher": news_text(publisher)[:100] if isinstance(publisher, str) else "",
            "published": timestamp(published) if isinstance(published, str) else None,
            "breaking": False,
        })
        if len(items) >= 50:
            break
    if not items:
        metadata = parse_article_metadata(payload)
        if not metadata["title"] or metadata["published"] is None:
            raise ValueError("No structured article data")
        items.append({
            "title": metadata["title"], "url": base_url, "body": metadata["body"],
            "image": public_url(urljoin(base_url, metadata["image"])) if metadata["image"] else "",
            "publisher": metadata["publisher"], "published": metadata["published"], "breaking": False,
        })
    return items


ARTICLE_DOMAINS = frozenset(("dr.dk","tv2.dk","tv2east.dk","tv2fyn.dk","tv2nord.dk","tv2ostjylland.dk","tvmidtvest.dk","tvsyd.dk","videnskab.dk","politi.dk","dst.dk","via.ritzau.dk","ekstrabladet.dk","bt.dk","politiken.dk","berlingske.dk","jyllands-posten.dk","information.dk","sn.dk","version2.dk","ing.dk","computerworld.dk","recordere.dk","beredskabsinfo.dk"))
PUBLIC_ARTICLE_DOMAINS = frozenset(("dr.dk","politi.dk","dst.dk"))

async def article_metadata(hass, url, sources=()):
    if not public_url(url):
        return {}
    allowed = ARTICLE_DOMAINS | {(urlsplit(source).hostname or "").removeprefix("www.") for source in sources if public_url(source)}
    u = urlsplit(url)
    # Older Google News IDs contain a literal publisher URL. Do not use
    # undocumented RPCs, authentication or subscription bypasses.
    if u.hostname == "news.google.com":
        token = u.path.rstrip("/").rsplit("/", 1)[-1]
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            match = re.search(rb"https://[\x21-\x7e]+", raw)
            if match:
                candidate = match.group().decode("ascii")
                parsed = urlsplit(candidate)
                if (parsed.hostname or "").removeprefix("www.") in ARTICLE_DOMAINS:
                    url, u = candidate, parsed
        except (ValueError, UnicodeError):
            pass
    if u.scheme == "https" and u.hostname == "news.google.com" and not u.username and not u.password and u.port in (None,443):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False), trust_env=False) as session, asyncio.timeout(8):
            async with session.get(url, allow_redirects=False) as response:
                if response.status not in (301,302,303,307,308):
                    return {}
                url = urljoin(url, response.headers.get("Location", ""))
        u = urlsplit(url)
    domain = (u.hostname or "").removeprefix("www.")
    if domain == "nyheder.tv2.dk":
        domain = "tv2.dk"
    if u.scheme != "https" or domain not in allowed or not public_url(url):
        return {}
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False), trust_env=False) as session, asyncio.timeout(10):
        for _ in range(5):
            async with session.get(url, allow_redirects=False) as response:
                if response.status in (301,302,303,307,308):
                    target = urljoin(url, response.headers.get("Location", ""))
                    parsed = urlsplit(target)
                    target_domain = (parsed.hostname or "").removeprefix("www.")
                    if target_domain == "nyheder.tv2.dk":
                        target_domain = "tv2.dk"
                    if not public_url(target) or target_domain != domain or target == url:
                        return {}
                    url = target
                    continue
                if response.status != 200 or "text/html" not in response.headers.get("Content-Type", ""):
                    return {}
                chunks = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    chunks.extend(chunk)
                    if len(chunks) > MAX_BYTES:
                        return {}
                break
        else:
            return {}
    result = await hass.async_add_executor_job(parse_article_metadata, bytes(chunks))
    if domain not in PUBLIC_ARTICLE_DOMAINS and not result.get("explicit_free"):
        result.pop("article", None)
    image = urljoin(url, result.get("image") or "") if result.get("image") else ""
    result["image"] = public_url(image)
    result.pop("explicit_free", None)
    result["url"] = url
    return result
