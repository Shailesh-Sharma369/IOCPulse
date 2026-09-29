import aiohttp
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Set, Optional, Tuple, Dict, Any
import re
import feedparser
import asyncio
from src.utils.retry import retry_network
from src.core.exceptions import IngestionError
from src.core.config import settings
import random

logger = logging.getLogger(__name__)

@retry_network
async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    user_agent = random.choice(settings.USER_AGENTS)
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "Sec-Ch-Ua": '"Chromium";v="120", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "DNT": "1",
    }
    async with session.get(url, headers=headers, timeout=settings.REQUEST_TIMEOUT_SECONDS) as resp:
        if resp.status != 200:
            raise IngestionError(f"Fetch failed: {resp.status} for {url}")
        charset = resp.charset or 'utf-8'
        try:
            return await resp.text(encoding=charset)
        except UnicodeDecodeError:
            raw = await resp.read()
            return raw.decode('utf-8', errors='replace')


def fetch_rss_sync(url: str) -> Optional[List[Dict[str, str]]]:
    """Fetch and parse RSS feed, return list of items with link, title, pub_date, author, content."""
    try:
        # feedparser.parse is blocking; caller must run in executor with a timeout
        feed = feedparser.parse(url, request_headers={"User-Agent": random.choice(settings.USER_AGENTS)})
        if feed.get('bozo') and not feed.entries:
            logger.warning(f"RSS parse error for {url}: {feed.get('bozo_exception')}")
            return None
        items = []
        for entry in feed.entries:
            link = entry.get('link')
            if not link:
                continue

            author = ''
            if hasattr(entry, 'author_detail') and entry.author_detail:
                author = entry.author_detail.get('name', '')
            if not author:
                author = entry.get('author', '')

            # Prefer full content over summary
            content_value = ''
            content_list = entry.get('content', [])
            if content_list and isinstance(content_list, list):
                content_value = content_list[0].get('value', '')
            if not content_value:
                content_value = entry.get('summary', '')

            items.append({
                'link': link,
                'title': entry.get('title', ''),
                'pub_date': entry.get('published') or entry.get('updated', ''),
                'author': author,
                'summary': entry.get('summary', ''),
                'content': content_value,
            })
        return items
    except Exception as e:
        logger.error(f"RSS fetch failed for {url}: {e}")
        return None


# Updated _SKIP_PATTERNS with exact segment matching for listing paths
_SKIP_PATTERNS = re.compile(
    r'(/page/\d|/tag/|/category/|/author/|/feed/|/assets/|/wp-content/|/cdn-cgi/|'
    r'\.(pdf|jpg|jpeg|png|gif|svg|xml|rss|json|js|css)(\?|$)|'
    r'/resource-library/?$|/platforms/?$|/brand/?$|'
    r'/about/?$|/contact/?$|/privacy/?$|/terms/?$|/sitemap|/rss/?$|'
    r'/submit/?$|/newsletter/?$|/subscribe/?$|/unsubscribe/?$|'
    r'/login/?$|/register/?$|/signup/?$|/account/?$|/profile/?$|'
    r'/search/?$|/advertise/?$|/sponsor/?$|'
    r'/information-communications-technology-|'
    r'/(?:search|label|archive|index|home)(?:/|$))',   # exact segment match
    re.IGNORECASE
)

# Positive path signals — date in path OR known article-like segments
# NOTE: kept permissive so advisory sites (CISA, JPCERT, IPA) with flat paths still pass
_ARTICLE_PATH_KEYWORDS = re.compile(
    r'/\d{4}/\d{1,2}/|'          # date in path
    r'/blog/|/news/|/post/|/posts/|/article/|/articles/|'
    r'/advisory/|/advisories/|/vuln/|/alert/|/alerts/|'
    r'/threat|/malware|/ransomware|/vulnerability|/vulnerabilit|'
    r'/cve-?\d|/exploit|/apt/|/campaign/|'
    r'/intel/|/intelligence/|/research/|/analysis/|/report/|/reports/|'
    r'/security-|/cyber-|/attack-|/incident-|/breach-|/ioc|'
    r'/pulse/|/insight/|/finding/|/disclosure/|'
    r'/at/\d{4}|'                # JPCERT advisory paths like /at/2024/
    r'/en/security/',             # IPA English security paths
    re.IGNORECASE
)


def _is_likely_article_link(a_tag, parsed_url: 'ParseResult', base_parsed: 'ParseResult') -> bool:
    """Heuristic: does an <a> tag look like a link to a real article?"""
    path = parsed_url.path

    if _SKIP_PATTERNS.search(path):
        return False

    # Require at least 2 path segments (rejects /, /blog, /news)
    segments = [s for s in path.split('/') if s]
    if len(segments) < 2:
        return False

    # If positive path keyword present, accept
    if _ARTICLE_PATH_KEYWORDS.search(path):
        return True

    # Otherwise accept only if link text is substantial AND path is deep enough (>=3 segments)
    # This catches advisory/vendor sites with non-standard URL structures
    link_text = a_tag.get_text(strip=True)
    if len(link_text) >= 20 and len(segments) >= 3:
        return True

    return False


def extract_article_links(html: str, base_url: str, max_links: int = 200) -> List[str]:
    """Extract likely article links from HTML using heuristics."""
    soup = BeautifulSoup(html, "lxml")
    links: Set[str] = set()
    blacklist_domains = settings.DOMAIN_BLACKLIST
    base_parsed = urlparse(base_url)

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(('#', 'mailto:', 'javascript:')):
            continue

        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)

        if parsed.scheme not in ('http', 'https'):
            continue

        # Only follow same-domain links
        if parsed.netloc != base_parsed.netloc:
            continue

        if any(b in parsed.netloc.lower() for b in blacklist_domains):
            continue

        link_text = a.get_text(strip=True)
        if not link_text or len(link_text) < 5:
            continue

        if _is_likely_article_link(a, parsed, base_parsed):
            links.add(absolute_url)

    result = list(links)[:max_links]
    logger.info(f"Extracted {len(result)} article links from {base_url}")
    return result