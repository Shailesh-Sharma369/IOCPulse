import asyncio
import aiohttp
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

from src.core.config import settings
from src.core.exceptions import IngestionError
from src.shared.database import DatabaseClient
from src.module_1_ingestion.models import RawArticle
from src.module_1_ingestion.temporal_filter import is_within_date_range, parse_article_timestamp
from src.module_1_ingestion.index_parser import fetch_html, extract_article_links, fetch_rss_sync
from src.module_1_ingestion.article_parser import (
    fetch_article_html,
    extract_article_data,
    extract_original_source_url,
    is_cti_relevant,
    _is_authoritative,
    _is_generic_url,
    _extract_body_trafilatura,
    _extract_body_semantic,
    parse_json_ld,
    _extract_author_name,
)
from src.module_1_ingestion.dynamic_renderer import render_and_extract_article, fetch_index_with_playwright

logger = logging.getLogger(__name__)

_RSS_EXECUTOR_TIMEOUT = 30

class ResolutionReason:
    NOT_AUTHORITATIVE = "NOT_AUTHORITATIVE"
    FETCH_FAILED = "FETCH_FAILED"
    BODY_TOO_SHORT = "BODY_TOO_SHORT"
    NON_CTI = "NON_CTI"
    GENERIC_PAGE = "GENERIC_PAGE"
    PDF_NOT_SUPPORTED = "PDF_NOT_SUPPORTED"
    TIMEOUT = "TIMEOUT"
    DEPTH_LIMIT = "DEPTH_LIMIT"
    LOOP_DETECTED = "LOOP_DETECTED"

def _domain_label(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower().lstrip("www.")
        parts = netloc.split(".")
        return parts[0].capitalize() if parts else netloc
    except Exception:
        return url

async def _fetch_original_source(
    session: aiohttp.ClientSession,
    original_url: str,
    publisher_article: RawArticle,
    publisher_name: str,
    publisher_url: str,
    depth: int = 1,
    visited: Optional[set] = None,
) -> Tuple[Optional[RawArticle], Optional[str]]:
    """
    Fetch the original source page. Returns (article, deeper_url) where deeper_url
    is a new original source URL found in this page (for one-hop resolution).
    """
    if visited is None:
        visited = set()
    if original_url in visited:
        logger.warning(f"Loop detected: {original_url} already visited.")
        return None, None
    visited.add(original_url)

    logger.info(f"Resolving original source: {original_url} (via {publisher_url})")

    # Handle PDF
    if settings.PDF_PARSING_ENABLED and original_url.lower().endswith('.pdf'):
        try:
            import pypdf
            async with session.get(original_url, timeout=settings.REQUEST_TIMEOUT_SECONDS) as resp:
                if resp.status != 200:
                    logger.warning(f"PDF download failed: {resp.status}")
                    return None, None
                pdf_data = await resp.read()
            from io import BytesIO
            reader = pypdf.PdfReader(BytesIO(pdf_data))
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            if not text:
                logger.warning(f"No text extracted from PDF: {original_url}")
                return None, None
            # Wrap in minimal HTML for consistency
            html = f"<html><body><pre>{text}</pre></body></html>"
            # Use publisher metadata but replace source
            title = publisher_article.title
            author = publisher_article.author
            published = publisher_article.published_datetime_utc
            source_domain = _domain_label(original_url)
            original_article = RawArticle.from_metadata(
                source_domain=source_domain,
                source_url=original_url,
                title=title,
                author=author,
                published=published,
                html=html,
                original_source_url=publisher_url,
                source_status="ORIGINAL",
                publisher_domain=publisher_name,
                publisher_url=publisher_url,
            )
            logger.info(f"✅ Resolved PDF original source: [{source_domain}] {original_url}")
            return original_article, None
        except ImportError:
            logger.warning("pypdf not installed; PDF parsing disabled.")
            return None, None
        except Exception as e:
            logger.warning(f"PDF parsing failed: {e}")
            return None, None

    # Regular HTML fetch
    try:
        html = await fetch_article_html(session, original_url)
    except Exception as e:
        logger.warning(f"Could not fetch original source {original_url}: {e}")
        return None, None

    if not html:
        return None, None

    # Extract body
    body_html: Optional[str] = _extract_body_trafilatura(html, original_url)
    if not body_html or len(body_html) < settings.MIN_BODY_LENGTH:
        try:
            soup_orig = BeautifulSoup(html, "lxml")
            body_html = _extract_body_semantic(soup_orig)
        except Exception:
            pass

    # Advisory domain exception
    parsed = urlparse(original_url)
    domain = parsed.netloc.lower().lstrip("www.")
    is_advisory = any(adv in domain for adv in settings.ADVISORY_DOMAINS)

    if not body_html:
        if is_advisory:
            # Try to extract even a short snippet
            soup_orig = BeautifulSoup(html, "lxml")
            body_html = soup_orig.get_text(separator='\n', strip=True)
            if len(body_html) < settings.MIN_BODY_LENGTH_ADVISORY:
                logger.info(f"Advisory page body too short: {len(body_html)} chars")
                return None, None
        else:
            logger.warning(f"No body extracted from {original_url}")
            return None, None
    else:
        body_len = len(body_html)
        if is_advisory:
            if body_len < settings.MIN_BODY_LENGTH_ADVISORY:
                logger.info(f"Advisory page body too short: {body_len} chars")
                return None, None
        else:
            if body_len < settings.MIN_BODY_LENGTH:
                logger.warning(f"Original source body too short for {original_url} ({body_len} chars) — falling back to publisher article")
                return None, None

    # Validate CTI relevance
    title = publisher_article.title
    if not is_cti_relevant(title, body_html):
        logger.info(f"Original source not CTI-relevant: {original_url}")
        return None, None

    # Build article
    source_domain = _domain_label(original_url)

    # Extract metadata from original page (JSON-LD) for better title/author/date
    try:
        soup_orig = BeautifulSoup(html, "lxml")
        json_ld = parse_json_ld(soup_orig)
        orig_title = json_ld.get("headline") or json_ld.get("name")
        if orig_title and len(orig_title.strip()) > 10:
            title = orig_title.strip()
        orig_author = _extract_author_name(json_ld.get("author"))
        if orig_author:
            author = orig_author
        orig_date = json_ld.get("datePublished")
        if orig_date:
            try:
                published = parse_article_timestamp(orig_date)
            except Exception:
                published = publisher_article.published_datetime_utc
        else:
            published = publisher_article.published_datetime_utc
    except Exception as e:
        logger.debug(f"JSON-LD extraction failed for original source {original_url}: {e}")
        published = publisher_article.published_datetime_utc
        author = publisher_article.author

    original_article = RawArticle.from_metadata(
        source_domain=source_domain,
        source_url=original_url,
        title=title,
        author=author,
        published=published,
        html=body_html,
        original_source_url=publisher_url,
        source_status="ORIGINAL",
        publisher_domain=publisher_name,
        publisher_url=publisher_url,
    )

    # One-hop resolution: if this page is a vendor blog and we are within depth limit, detect deeper original source
    deeper_url = None
    if depth < settings.MAX_RESOLUTION_DEPTH:
        # Check if this page itself references an even deeper original source
        try:
            soup_deeper = BeautifulSoup(html, "lxml")
            deeper_candidate = extract_original_source_url(soup_deeper, original_url)
            if deeper_candidate and deeper_candidate != original_url and deeper_candidate not in visited:
                # Validate that the deeper candidate is authoritative or has high confidence
                # We'll attempt to fetch it recursively
                logger.info(f"Found deeper original source from {original_url}: {deeper_candidate}")
                deeper_url = deeper_candidate
        except Exception as e:
            logger.debug(f"Error detecting deeper source from {original_url}: {e}")

    logger.info(f"✅ Resolved original source: [{source_domain}] {original_url} (publisher: {publisher_name})")
    return original_article, deeper_url

async def _resolve_original_source(
    self,
    session: aiohttp.ClientSession,
    mirror_article: RawArticle,
    detected_original_url: Optional[str],
    publisher_name: str,
    publisher_url: str,
    depth: int = 0,
    visited: Optional[set] = None,
) -> RawArticle:
    """
    Attempt to fetch and return an ORIGINAL source article.
    Falls back to mirror_article on failure.
    Supports one extra hop (depth up to MAX_RESOLUTION_DEPTH).
    """
    if visited is None:
        visited = set()

    if not detected_original_url:
        logger.debug(f"No detected original URL for {publisher_url}")
        return mirror_article

    if not _is_authoritative(detected_original_url):
        logger.info(f"Reason: {ResolutionReason.NOT_AUTHORITATIVE} - {detected_original_url}")
        return mirror_article

    if _is_generic_url(detected_original_url):
        logger.info(f"Reason: {ResolutionReason.GENERIC_PAGE} - {detected_original_url}")
        return mirror_article

    if detected_original_url in visited:
        logger.info(f"Reason: {ResolutionReason.LOOP_DETECTED} - {detected_original_url}")
        return mirror_article

    if depth >= settings.MAX_RESOLUTION_DEPTH:
        logger.info(f"Reason: {ResolutionReason.DEPTH_LIMIT} - {detected_original_url}")
        return mirror_article

    visited.add(detected_original_url)

    # Fetch the original source
    original, deeper_url = await _fetch_original_source(
        session=session,
        original_url=detected_original_url,
        publisher_article=mirror_article,
        publisher_name=publisher_name,
        publisher_url=publisher_url,
        depth=depth + 1,
        visited=visited,
    )

    if original is not None:
        # If we have a deeper URL, try to resolve it (one more hop)
        if deeper_url and depth + 1 < settings.MAX_RESOLUTION_DEPTH:
            logger.info(f"Attempting second hop to {deeper_url}")
            deeper_original, _ = await _fetch_original_source(
                session=session,
                original_url=deeper_url,
                publisher_article=original,  # pass the current original as publisher context
                publisher_name=original.source_domain,
                publisher_url=original.source_url,
                depth=depth + 2,
                visited=visited,
            )
            if deeper_original is not None:
                # Prefer the deeper original
                return deeper_original
            else:
                logger.info(f"Second hop failed; keeping first-hop original.")
        return original

    # Fetch failed or body too thin — keep the publisher article
    logger.info(f"Reason: {ResolutionReason.FETCH_FAILED} - {detected_original_url}")
    return mirror_article

# ---------------------------------------------------------------------------
# Original-source resolution helpers
# ---------------------------------------------------------------------------

def _domain_label(url: str) -> str:
    """Return a human-readable organisation label from a URL netloc."""
    try:
        netloc = urlparse(url).netloc.lower().lstrip("www.")
        # Strip common TLDs for readability
        parts = netloc.split(".")
        return parts[0].capitalize() if parts else netloc
    except Exception:
        return url


async def _fetch_original_source(
    session: aiohttp.ClientSession,
    original_url: str,
    publisher_article: RawArticle,
    publisher_name: str,
    publisher_url: str,
) -> Optional[RawArticle]:
    """
    Fetch the original-source page and build a RawArticle whose raw_html is
    the content of that page.

    Returns None on any failure so the caller can fall back gracefully.

    The returned RawArticle has:
      source_domain   = org label derived from original_url (e.g. "Socket", "Cisa")
      source_url      = original_url
      raw_html        = extracted body of the original-source page
      original_source_url = publisher_url  (so Module 2 knows the referrer)
      source_status   = 'ORIGINAL'
      publisher_domain = publisher_name
      publisher_url   = publisher_url
      title / author / published = from publisher article (preserved as ground truth,
                        since the original page may have a different or missing date)
    """
    logger.info(f"Resolving original source: {original_url} (via {publisher_url})")
    try:
        html = await fetch_article_html(session, original_url)
    except Exception as e:
        logger.warning(f"Could not fetch original source {original_url}: {e}")
        return None

    if not html:
        return None

    # Extract body from the original-source page
    body_html: Optional[str] = _extract_body_trafilatura(html, original_url)
    if not body_html or len(body_html) < settings.MIN_BODY_LENGTH:
        try:
            soup_orig = BeautifulSoup(html, "lxml")
            body_html = _extract_body_semantic(soup_orig)
        except Exception:
            pass

    if not body_html or len(body_html) < settings.MIN_BODY_LENGTH:
        logger.warning(
            f"Original source body too short for {original_url} "
            f"({len(body_html) if body_html else 0} chars) — falling back to publisher article"
        )
        return None

    # Try to get a better title/author from the original page
    title = publisher_article.title
    author = publisher_article.author
    published = publisher_article.published_datetime_utc

    try:
        soup_orig = BeautifulSoup(html, "lxml")
        json_ld = parse_json_ld(soup_orig)

        orig_title = json_ld.get("headline") or json_ld.get("name")
        if orig_title and len(orig_title.strip()) > 10:
            title = orig_title.strip()

        orig_author = _extract_author_name(json_ld.get("author"))
        if orig_author:
            author = orig_author

        # Use original-source date only if publisher date is missing
        if not published and json_ld.get("datePublished"):
            try:
                published = parse_article_timestamp(json_ld["datePublished"])
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"JSON-LD extraction failed for original source {original_url}: {e}")

    # Validate CTI relevance against the original body (belt-and-suspenders)
    if not is_cti_relevant(title, body_html):
        logger.info(f"Original source not CTI-relevant, keeping publisher article: {original_url}")
        return None

    source_domain = _domain_label(original_url)

    original_article = RawArticle.from_metadata(
        source_domain=source_domain,
        source_url=original_url,
        title=title,
        author=author,
        published=published,
        html=body_html,
        original_source_url=publisher_url,   # publisher article is the referrer
        source_status="ORIGINAL",
        publisher_domain=publisher_name,
        publisher_url=publisher_url,
    )
    logger.info(
        f"✅ Resolved original source: [{source_domain}] {original_url} "
        f"(publisher: {publisher_name})"
    )
    return original_article


# ---------------------------------------------------------------------------
# SourceManager
# ---------------------------------------------------------------------------

class SourceManager:
    def __init__(self):
        self.sources = settings.SOURCES

    def _extract_date_from_url(self, url: str) -> Optional[datetime]:
        match = re.search(r'/(\d{4})/(\d{1,2})(?:/(\d{1,2}))?/', url)
        if match:
            year, month, day = match.groups()
            day = day or '1'
            try:
                return datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
            except Exception:
                pass
        return None

    async def _resolve_original_source(
        self,
        session: aiohttp.ClientSession,
        mirror_article: RawArticle,
        detected_original_url: Optional[str],
        publisher_name: str,
        publisher_url: str,
    ) -> RawArticle:
        """
        Attempt to fetch and return an ORIGINAL source article.
        Falls back to the mirror_article unchanged on any failure.

        Decision tree:
          1. Use detected_original_url if available and authoritative.
          2. Otherwise return mirror_article as-is (MIRROR status).
        """
        if not detected_original_url:
            return mirror_article

        if not _is_authoritative(detected_original_url):
            logger.debug(
                f"Detected URL is not authoritative, keeping mirror: {detected_original_url}"
            )
            return mirror_article

        if _is_generic_url(detected_original_url):
            logger.debug(
                f"Detected URL is generic/listing, keeping mirror: {detected_original_url}"
            )
            return mirror_article

        original = await _fetch_original_source(
            session=session,
            original_url=detected_original_url,
            publisher_article=mirror_article,
            publisher_name=publisher_name,
            publisher_url=publisher_url,
        )
        if original is not None:
            return original

        # Fetch failed or body too thin — keep the publisher article
        logger.info(
            f"Original source resolution failed for {detected_original_url}, "
            f"keeping publisher article: {publisher_url}"
        )
        return mirror_article

    async def _process_single_source(
        self, session: aiohttp.ClientSession, source: Dict[str, Any]
    ) -> List[RawArticle]:
        source_name = source["name"]
        base_url = source["base_url"]
        rss_url = source.get("rss_url")
        use_playwright = source.get("use_playwright", False)

        articles: List[RawArticle] = []
        article_url_meta: Dict[str, Dict[str, str]] = {}

        # 1. RSS feed (preferred)
        if rss_url:
            try:
                loop = asyncio.get_event_loop()
                items = await asyncio.wait_for(
                    loop.run_in_executor(None, fetch_rss_sync, rss_url),
                    timeout=_RSS_EXECUTOR_TIMEOUT,
                )
                if items:
                    for item in items:
                        link = item.get('link')
                        if not link:
                            continue
                        article_url_meta[link] = {
                            'title': item.get('title', ''),
                            'pub_date': item.get('pub_date', ''),
                            'author': item.get('author', ''),
                            'content': item.get('content', ''),
                        }
                    logger.info(f"RSS for {source_name} yielded {len(article_url_meta)} articles")
                else:
                    logger.warning(f"RSS for {source_name} returned no items")
            except asyncio.TimeoutError:
                logger.warning(f"RSS fetch timed out for {source_name} ({rss_url})")
            except Exception as e:
                logger.warning(f"RSS error for {source_name}: {e}")

        # 2. Index scraping fallback (only if RSS produced nothing)
        if not article_url_meta:
            current_url = base_url
            page_count = 0
            while current_url and page_count < settings.MAX_PAGES_PER_SOURCE:
                page_count += 1
                try:
                    if use_playwright:
                        html = await fetch_index_with_playwright(current_url)
                    else:
                        html = await fetch_html(session, current_url)
                    urls = extract_article_links(html, current_url)
                    for u in urls:
                        if u not in article_url_meta:
                            article_url_meta[u] = {}
                    logger.info(f"Page {page_count} for {source_name}: found {len(urls)} URLs")

                    soup = BeautifulSoup(html, "lxml")
                    next_link = (
                        soup.find('a', {'rel': 'next'})
                        or soup.find('a', string=re.compile(r'Next|Older', re.I))
                    )
                    if next_link and next_link.get('href'):
                        current_url = urljoin(current_url, next_link['href'])
                        await asyncio.sleep(0.5)
                    else:
                        break
                except Exception as e:
                    logger.error(f"Error fetching page {current_url} for {source_name}: {e}")
                    break

        logger.info(f"Total unique article URLs for {source_name}: {len(article_url_meta)}")

        # 3. Process each article URL
        old_article_streak = 0
        for url, meta in list(article_url_meta.items())[:200]:
            try:
                url_date = self._extract_date_from_url(url)
                if url_date and url_date < settings.START_DATE:
                    old_article_streak += 1
                    if not rss_url and old_article_streak >= 5:
                        logger.info(f"URL date streak too old for {source_name}, stopping index scrape")
                        break
                    logger.debug(f"URL {url} indicates old date {url_date}, skipping")
                    continue
                else:
                    old_article_streak = 0

                rss_title = meta.get('title') or None
                rss_date = meta.get('pub_date') or None
                rss_author = meta.get('author') or None
                rss_content = meta.get('content') or None

                if rss_date:
                    try:
                        rss_dt = parse_article_timestamp(rss_date)
                        if not is_within_date_range(rss_dt):
                            if rss_dt < settings.START_DATE:
                                old_article_streak += 1
                                logger.debug(f"RSS date {rss_dt} too old, skipping {url}")
                                continue
                            logger.debug(f"RSS date {rss_dt} out of range, skipping {url}")
                            continue
                        else:
                            old_article_streak = 0
                    except Exception:
                        pass

                # --- Step A: Fetch and parse the publisher article ---
                if use_playwright:
                    mirror_article, detected_original_url = await render_and_extract_article(
                        url, source_name,
                        rss_title=rss_title, rss_date=rss_date,
                        rss_author=rss_author, rss_content=rss_content,
                    )
                else:
                    full_html = await fetch_article_html(session, url)
                    mirror_article, detected_original_url = extract_article_data(
                        full_html, url, source_name,
                        rss_title=rss_title,
                        rss_date=rss_date,
                        rss_author=rss_author,
                        rss_content=rss_content,
                    )

                if not mirror_article:
                    continue

                # Last-resort: fill in URL-based date if still None
                if mirror_article.published_datetime_utc is None and url_date:
                    mirror_article.published_datetime_utc = url_date

                if not is_within_date_range(mirror_article.published_datetime_utc):
                    logger.info(
                        f"❌ Skipped (date out of range): {mirror_article.title} "
                        f"({mirror_article.published_datetime_utc})"
                    )
                    continue

                # --- Step B: Resolve original source (NEW) ---
                # If the publisher article links to an authoritative primary-research
                # page, fetch that page and store its content instead.
                final_article = await self._resolve_original_source(
                    session=session,
                    mirror_article=mirror_article,
                    detected_original_url=detected_original_url,
                    publisher_name=source_name,
                    publisher_url=url,
                )

                articles.append(final_article)
                logger.info(
                    f"✅ Accepted [{final_article.source_status}]: "
                    f"{final_article.title} | source={final_article.source_domain} "
                    f"({final_article.published_datetime_utc})"
                )

            except Exception as e:
                logger.error(f"Failed to process {url} for {source_name}: {e}")
                continue  # Never let one URL failure abort the whole source

        return articles

    async def ingest_all(self) -> List[RawArticle]:
        all_articles: List[RawArticle] = []
        async with aiohttp.ClientSession() as session:
            tasks = [self._process_single_source(session, src) for src in self.sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for src, res in zip(self.sources, results):
                if isinstance(res, Exception):
                    logger.error(f"Source '{src['name']}' failed entirely: {res}")
                else:
                    all_articles.extend(res)

        # Deduplicate by hash
        seen = set()
        unique = []
        for art in all_articles:
            if art.metadata_hash not in seen:
                seen.add(art.metadata_hash)
                unique.append(art)
        logger.info(f"Total unique articles: {len(unique)}")
        return unique

    async def ingest_and_persist(self) -> int:
        articles = await self.ingest_all()
        if not articles:
            return 0
        inserted = 0
        async with DatabaseClient() as db:
            for art in articles:
                rowid = await db.insert_raw_article(art.to_db_dict())
                if rowid > 0:
                    inserted += 1
        logger.info(f"Inserted {inserted} new articles")
        return inserted