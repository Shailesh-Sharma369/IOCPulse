import aiohttp
from bs4 import BeautifulSoup
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, List, Set
from urllib.parse import urlparse, urljoin, parse_qs, urlunparse
import re
import json
import trafilatura
from src.utils.retry import retry_network
from src.core.exceptions import IngestionError
from src.module_1_ingestion.temporal_filter import parse_article_timestamp
from src.module_1_ingestion.models import RawArticle
from src.core.config import settings
import random
import dateparser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Known authoritative / primary-research domains.
# Publisher articles (BleepingComputer, SecurityAffairs, THN, etc.) often
# cite these as the original source.  When we find an outbound link to any
# of these domains we treat it as a candidate original-source URL.
# ---------------------------------------------------------------------------
_AUTHORITATIVE_DOMAINS: Set[str] = {
    # Government / CERT
    "cisa.gov",
    "us-cert.cisa.gov",
    "jpcert.or.jp",
    "ipa.go.jp",
    "ncsc.gov.uk",
    "bsi.bund.de",
    "cert.be",
    "anssi.fr",
    "enisa.europa.eu",
    "nist.gov",
    "nvd.nist.gov",
    "kb.cert.org",
    # Vendor security research / threat intel
    "microsoft.com",
    "security.microsoft.com",
    "msrc.microsoft.com",
    "techcommunity.microsoft.com",
    "google.com",
    "cloud.google.com",
    "blog.google",
    "googleprojectzero.blogspot.com",
    "research.google",
    "mandiant.com",
    "unit42.paloaltonetworks.com",
    "paloaltonetworks.com",
    "talos-security.com",
    "blog.talosintelligence.com",
    "talosintelligence.com",
    "cisco.com",
    "blog.cisco.com",
    "crowdstrike.com",
    "adversary.crowdstrike.com",
    "sentinelone.com",
    "labs.sentinelone.com",
    "trendmicro.com",
    "research.checkpoint.com",
    "checkpoint.com",
    "securelist.com",
    "kaspersky.com",
    "eset.com",
    "welivesecurity.com",
    "proofpoint.com",
    "threatpost.com",
    "fortinet.com",
    "fortiguard.com",
    "symantec-enterprise-blogs.security.com",
    "broadcom.com",
    "trellix.com",
    "fireeye.com",
    "mcafee.com",
    "malwarebytes.com",
    "sophos.com",
    "news.sophos.com",
    "rapid7.com",
    "attackerkb.com",
    "tenable.com",
    "qualys.com",
    "secureworks.com",
    "ibm.com",
    "securityintelligence.com",
    "akamai.com",
    "lumen.com",
    "blog.lumen.com",
    "netscout.com",
    "recorded-future.com",
    "recordedfuture.com",
    "domaintools.com",
    "virustotal.com",
    "any.run",
    "hybrid-analysis.com",
    "intezer.com",
    "elastic.co",
    "blog.xpnsec.com",
    "sekoia.io",
    "blog.sekoia.io",
    "orangecyberdefense.com",
    "cybereason.com",
    "darktrace.com",
    "vectra.ai",
    "abnormalsecurity.com",
    "cofense.com",
    "ironnet.com",
    "groupib.com",
    "group-ib.com",
    "krebsonsecurity.com",
    "bitsight.com",
    "silentpush.com",
    "eclecticiq.com",
    "team-cymru.com",
    "shadowserver.org",
    "spamhaus.org",
    "abuse.ch",
    "urlhaus.abuse.ch",
    "bazaar.abuse.ch",
    # Code / supply-chain
    "github.com",
    "github.blog",
    "securitylab.github.com",
    "socket.dev",
    "snyk.io",
    "jfrog.com",
    "checkmarx.com",
    "aquasec.com",
    "sysdig.com",
    "lacework.com",
    # CVE / Vuln DBs
    "cve.mitre.org",
    "nvd.nist.gov",
    "vuldb.com",
    "exploit-db.com",
    "packetstormsecurity.com",
    "zerodayinitiative.com",
    "portswigger.net",
    # Cloud providers
    "aws.amazon.com",
    "cloudflare.com",
    "blog.cloudflare.com",
}

# Publisher / aggregator domains that should NOT be treated as authoritative
# sources (these are the sites we scrape as entry points).
_PUBLISHER_DOMAINS: Set[str] = {
    "bleepingcomputer.com",
    "securityaffairs.com",
    "thehackernews.com",
    "hackernews.com",
    "feeds.feedburner.com",
    "theregister.com",
    "darkreading.com",
    "infosecurity-magazine.com",
    "cyberscoop.com",
    "wired.com",
    "arstechnica.com",
    "techcrunch.com",
    "zdnet.com",
    "threatintelligence.com",
}

# Enhanced patterns for “via / source / original” phrases
# Added: researchers at, experts at, team at, security firm
_VIA_PATTERNS = re.compile(
    r'\b(?:via|source[d]?|original(?:ly)?|reported\s+by|according\s+to|credited\s+to|'
    r'discovered\s+by|found\s+by|published\s+(?:by|at|on)|read\s+(?:more|the\s+full)|'
    r'full\s+(?:report|advisory|disclosure|details|analysis|post|article|write-up|writeup)|'
    r'technical\s+(?:report|analysis|details|writeup|write-up)|'
    r'research(?:ed)?\s+by|analyzed\s+by|investigation\s+by|'
    r'report\s+(?:here|available|published)|advisory|disclosure|'
    r'original\s+report|original\s+analysis|original\s+research|'
    r'full\s+story|complete\s+report|full\s+disclosure|'
    r'threat\s+advisory|security\s+advisory|incident\s+report|'
    r'researchers\s+at|experts\s+at|team\s+at|security\s+firm\s+)',
    re.IGNORECASE,
)

# Explicit source‑section markers (e.g. "Source:", "Original Report:", etc.)
_SOURCE_SECTION_PATTERNS = re.compile(
    r'^\s*(?:source|original|full\s+report|technical\s+report|advisory|analysis|research)'
    r'\s*[:;]',
    re.IGNORECASE,
)

# URL path patterns that strongly indicate a primary-research document
# Added: news-events, cybersecurity-advisories, threat-intelligence, security-advisory, security-bulletin
_SOURCE_PATH_PATTERNS = re.compile(
    r'/(advisory|advisories|vuln|vulnerability|vulnerabilities|'
    r'cve-?\d|exploit|malware|threat|apt|campaign|report|reports|'
    r'research|analysis|disclosure|intel|intelligence|blog|post|posts|'
    r'security-?advisory|security-?bulletin|security-?alert|bulletin|'
    r'white-?paper|technical-?report|threat-?report|threat-?advisory|'
    r'news-events|cybersecurity-advisories|threat-intelligence|security-advisory|security-bulletin)/',
    re.IGNORECASE,
)

# Path patterns that indicate a generic page (homepage, category, tag, etc.)
_PATH_BAD_PATTERN = re.compile(
    r'/(?:tag|category|author|about|contact|privacy|terms|sitemap|rss|feed|login|register|'
    r'careers|support|home|search|newsletter|subscribe|unsubscribe|account|profile|'
    r'resources|brand|advertise|sponsor|information-communications-technology)'
    r'(?:/|$|\?)',
    re.IGNORECASE,
)

# Path patterns that are good (research content) - enhanced with additional paths
_PATH_GOOD_PATTERN = re.compile(
    r'/(?:blog|research|advisory|report|analysis|campaign|security|threat|intel|malware|'
    r'incident|vulnerability|cve|exploit|post|writeup|write-up|disclosure|technical|'
    r'news-events|cybersecurity-advisories|threat-intelligence|security-advisory|security-bulletin)(?:/|$|[?#])',
    re.IGNORECASE,
)

_ORIGINAL_SOURCE_BAD_PATH_PATTERN = re.compile(
    r'/(?:docs?|documentation|doc|product|products|solution|solutions|'
    r'landing|practice|practices|guide|guides|overview|learn|help|support|'
    r'index|indices|search|tag|tags|category|categories|archive|archives|'
    r'home|about|contact|press|newsroom|release|releases)(?:/|$|[?#])',
    re.IGNORECASE,
)

_PROMOTIONAL_PATTERNS = re.compile(
    r'\b(?:sponsored|sponsorship|promoted(?:\s+content)?|advertorial|partner\s+content|'
    r'paid\s+post|paid\s+content|native\s+advertising|advertisement|advertising|'
    r'brought\s+to\s+you\s+by|in\s+partnership\s+with|promo|promotional)\b',
    re.IGNORECASE,
)

_LISTING_TITLE_PATTERNS = re.compile(
    r'\b(?:news\s+in\s+the\s+.+\s+category|category|categories|tag|tags|archive|archives|'
    r'search\s+results?|browse\s+by\s+category|all\s+posts|latest\s+news)\b',
    re.IGNORECASE,
)

# New: Attribution phrases for text-based detection
_ATTRIBUTION_PHRASES = re.compile(
    r'\b(?:according\s+to|researchers\s+at|report(?:ed)?\s+by|'
    r'published\s+by|original\s+(?:report|analysis|research|source)|'
    r'full\s+(?:report|analysis|details|writeup)|'
    r'technical\s+(?:report|analysis)|'
    r'read\s+the\s+(?:full|complete)|'
    r'via\s+|source\s*[:;]\s*)',
    re.IGNORECASE,
)

# New: Confidence threshold for non-whitelisted domains
_HIGH_CONFIDENCE_THRESHOLD = 6.0
# Parent elements that indicate a citation or blockquote
_BLOCKQUOTE_PARENTS = {'blockquote', 'cite', 'figure', 'figcaption'}

def _extract_urls_from_attribution_text(soup: BeautifulSoup, body_text: str) -> List[Tuple[str, float]]:
    """
    Scan the body text for attribution phrases and extract any URLs
    that appear within a short window (e.g., within the same sentence or paragraph).
    Returns a list of (url, confidence_score) tuples.
    """
    candidates = []
    # We'll look for <a> tags that are near the attribution phrase.
    # Simpler: find all <a> tags and check if their surrounding text contains attribution phrases.
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        if not href or not href.startswith(('http://', 'https://')):
            continue
        # Get text of the link and its parent's text
        parent_text = a.parent.get_text(' ', strip=True) if a.parent else ''
        # Check if attribution phrase appears within the parent or the link text
        combined = f"{a.get_text(strip=True)} {parent_text}"
        if _ATTRIBUTION_PHRASES.search(combined):
            # Bonus: if the link text itself contains "report", "advisory", etc.
            bonus = 0.0
            if re.search(r'\b(report|advisory|analysis|research|blog|writeup|disclosure)\b', a.get_text(strip=True), re.I):
                bonus += 1.0
            # Closer proximity to phrase adds confidence (crude: if phrase in parent, it's good)
            if _ATTRIBUTION_PHRASES.search(parent_text):
                bonus += 1.5
            score = 2.0 + bonus   # base 2.0 for attribution context
            candidates.append((href, score))
    return candidates

def _extract_original_source_from_json_ld(soup: BeautifulSoup) -> Optional[str]:
    """Extract a 'citation' or 'source' URL from JSON-LD if present."""
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            raw = script.string
            if not raw:
                continue
            data = json.loads(raw)
            # Unwrap @graph
            if isinstance(data, dict) and '@graph' in data:
                graph = data['@graph']
                if isinstance(graph, list):
                    data = graph
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Check for citation or source
                for key in ['citation', 'source', 'sameAs', 'url']:
                    if key in item:
                        val = item[key]
                        if isinstance(val, str) and val.startswith(('http://', 'https://')):
                            return val
                        elif isinstance(val, list):
                            for v in val:
                                if isinstance(v, str) and v.startswith(('http://', 'https://')):
                                    return v
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    return None

def extract_original_source_url(soup: BeautifulSoup, publisher_url: str) -> Optional[str]:
    """
    Enhanced version: scan the article for links to authoritative primary-research
    pages, using both anchor scoring and text-based attribution detection.
    """
    # 1. Existing anchor-based scoring (keep unchanged)
    body_container = _get_body_container(soup)
    if body_container is None:
        body_container = soup

    # Collect candidates with their scores
    candidates = []

    # Existing logic: iterate over all <a> tags (original code)
    base_parsed = urlparse(publisher_url)
    publisher_root = _netloc_root(base_parsed.netloc) if base_parsed.netloc else ''

    for a in body_container.find_all('a', href=True):
        href = a.get('href', '').strip()
        if not href or href.startswith(('#', 'mailto:', 'javascript:')):
            continue

        absolute_url = urljoin(publisher_url, href)
        parsed = urlparse(absolute_url)
        if parsed.scheme not in ('http', 'https'):
            continue

        # Only follow outbound links (different domain)
        if parsed.netloc == base_parsed.netloc:
            continue

        # Skip blacklisted domains
        if any(b in parsed.netloc.lower() for b in settings.DOMAIN_BLACKLIST):
            continue

        anchor_text = a.get_text(strip=True)
        surrounding_text = a.parent.get_text(' ', strip=True) if a.parent else ''

        # Compute score using existing scoring function (we keep it)
        score = _score_candidate(
            absolute_url, anchor_text, surrounding_text,
            soup, a, body_container, publisher_root
        )

        # New: Additional bonus if attribution phrase is near the link
        if _ATTRIBUTION_PHRASES.search(surrounding_text) or _ATTRIBUTION_PHRASES.search(anchor_text):
            score += 2.0

        candidates.append((absolute_url, score))

    # 2. New: Detect URLs from attribution phrases (text-based)
    body_text = body_container.get_text(' ', strip=True) if body_container else ''
    for url, score in _extract_urls_from_attribution_text(soup, body_text):
        # Avoid duplicates
        if not any(url == c[0] for c in candidates):
            candidates.append((url, score))

    # 3. New: Extract from JSON-LD
    json_ld_url = _extract_original_source_from_json_ld(soup)
    if json_ld_url:
        # Give it a high score if it's a citation
        candidates.append((json_ld_url, 5.0))

    if not candidates:
        return None

    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)

    # Filter out generic pages (use existing _is_generic_url)
    filtered = [(url, score) for url, score in candidates if not _is_generic_url(url)]

    if not filtered:
        # If all are generic, try best of all
        filtered = candidates

    best_url, best_score = filtered[0]

    # Decision: accept if authoritative OR score above threshold
    if _is_authoritative(best_url):
        return best_url
    elif best_score >= _HIGH_CONFIDENCE_THRESHOLD:
        logger.info(f"Accepting non-whitelisted URL with high score {best_score}: {best_url}")
        return best_url
    else:
        logger.debug(f"Rejected original source candidate: {best_url} (score {best_score})")
        return None


def _netloc_root(netloc: str) -> str:
    """Return the registrable domain (last two labels), e.g. 'blog.foo.com' → 'foo.com'."""
    parts = netloc.lower().lstrip("www.").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else netloc.lower()


def _is_authoritative(url: str) -> bool:
    """Return True if *url* belongs to a known authoritative / primary-research domain."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().lstrip("www.")
        # Exact match first
        if netloc in _AUTHORITATIVE_DOMAINS:
            return True
        # Suffix match (catches subdomains like 'unit42.paloaltonetworks.com')
        root = _netloc_root(netloc)
        return root in _AUTHORITATIVE_DOMAINS
    except Exception:
        return False


def _is_publisher(url: str) -> bool:
    """Return True if *url* belongs to a known publisher / aggregator site."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().lstrip("www.")
        root = _netloc_root(netloc)
        return root in _PUBLISHER_DOMAINS
    except Exception:
        return False


def _path_has_publication_tokens(path: str) -> bool:
    """Return True when the path contains article-like tokens in its slug or segments."""
    tokens = [token for token in re.split(r'[^a-z0-9]+', (path or '').lower()) if token]
    if not tokens:
        return False

    publication_tokens = {
        'blog', 'research', 'advisory', 'advisories', 'report', 'reports',
        'analysis', 'campaign', 'security', 'threat', 'intel', 'intelligence',
        'malware', 'incident', 'vulnerability', 'vulnerabilities', 'cve',
        'exploit', 'post', 'posts', 'writeup', 'writeups', 'write',
        'disclosure', 'technical', 'news', 'events', 'cybersecurity',
        'bulletin', 'white', 'paper', 'paper', 'tech', 'article', 'articles',
    }
    return any(token in publication_tokens for token in tokens)


def _is_valid_original_source_url(url: str) -> bool:
    """Return True for genuine CTI publication URLs suitable for original-source promotion."""
    try:
        parsed = urlparse(url)
        path = parsed.path or ""
        if _is_generic_url(url):
            return False
        if _ORIGINAL_SOURCE_BAD_PATH_PATTERN.search(path):
            return False
        return _path_has_publication_tokens(path)
    except Exception:
        return False


def _normalize_url(url: str) -> str:
    """Remove common tracking parameters and fragments for scoring."""
    try:
        parsed = urlparse(url)
        # Drop fragments
        parsed = parsed._replace(fragment="")
        # Remove known tracking query parameters
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        # Common tracking params
        to_remove = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
                     'fbclid', 'gclid', 'msclkid', 'ref', 'source', 'from', 'si', 'mtm_source',
                     'mtm_medium', 'mtm_campaign', 'mtm_keyword', 'mtm_content'}
        for key in to_remove:
            query_params.pop(key, None)
        # Rebuild query string
        new_query = "&".join(f"{k}={v[0]}" if v else k for k, v in query_params.items())
        parsed = parsed._replace(query=new_query)
        return urlunparse(parsed)
    except Exception:
        return url


def _is_generic_url(url: str) -> bool:
    """Return True if URL points to a homepage, category, tag, author, etc."""
    try:
        parsed = urlparse(_normalize_url(url))
        path = parsed.path.lower()
        # If path is empty or just '/' it's homepage
        if path in ('', '/') or path == '/index.html':
            return True
        # Check bad path patterns
        if _PATH_BAD_PATTERN.search(path):
            return True
        # Also check if path has only one segment (like /blog, /news) – often category
        segments = [s for s in path.split('/') if s]
        if len(segments) == 1 and segments[0] in ('blog', 'news', 'articles', 'posts', 'reports', 'advisories'):
            return True
        return False
    except Exception:
        return False


def _get_position_score(soup: BeautifulSoup, link_tag, body_container) -> float:
    """Return a bonus based on link position in the article body."""
    try:
        # Get all text in body_container before the link's parent element
        # We'll find the index of the link tag among all tags in the container
        all_tags = body_container.find_all(recursive=True)
        try:
            link_index = all_tags.index(link_tag)
            total = len(all_tags)
            if total == 0:
                return 0.0
            position = link_index / total
        except ValueError:
            # Fallback: use text length
            full_text = body_container.get_text(" ", strip=True)
            link_parent = link_tag.parent
            text_before = ''
            for element in body_container.descendants:
                if element == link_parent:
                    break
                if hasattr(element, 'get_text'):
                    text_before += element.get_text(" ", strip=True)
                elif isinstance(element, str):
                    text_before += element
            if not full_text:
                return 0.0
            position = len(text_before) / len(full_text)
        # First 40%: bonus +1.5
        if position <= 0.4:
            return 1.5
        # Last 25%: bonus +1.0
        elif position >= 0.75:
            return 1.0
        return 0.0
    except Exception:
        return 0.0


def _score_candidate(href: str, anchor_text: str, surrounding_text: str,
                     soup: BeautifulSoup, link_tag, body_container, publisher_root: str) -> float:
    """
    Compute a composite score for a candidate original source URL.
    Returns a float; higher is better.
    """
    # Start with base score: 1 if authoritative, else 0 (we already filter)
    score = 1.0

    # Normalize URL for scoring
    norm_url = _normalize_url(href)

    # ---- 1. Source section detection ----
    # Check if the link is inside a source section (e.g. "Source:" or "Original Report:")
    parent_text = link_tag.parent.get_text(" ", strip=True) if link_tag.parent else ""
    if _SOURCE_SECTION_PATTERNS.search(parent_text):
        score += 5.0  # high priority

    # ---- 2. Via/Original patterns in surrounding text ----
    if _VIA_PATTERNS.search(surrounding_text) or _VIA_PATTERNS.search(anchor_text):
        score += 3.0

    # ---- 3. Path quality ----
    try:
        parsed = urlparse(norm_url)
        path = parsed.path
        if _PATH_GOOD_PATTERN.search(path):
            score += 2.0
        if _PATH_BAD_PATTERN.search(path):
            score -= 3.0  # strong penalty
    except Exception:
        pass

    # ---- 4. Generic page (homepage, category, etc.) ----
    if _is_generic_url(norm_url):
        score -= 5.0

    # ---- 5. Position bonus ----
    score += _get_position_score(soup, link_tag, body_container)

    # ---- 6. Inside blockquote/citation ----
    parent = link_tag.parent
    while parent:
        if parent.name and parent.name.lower() in _BLOCKQUOTE_PARENTS:
            score += 2.0
            break
        parent = parent.parent

    # ---- 7. Anchor text quality ----
    anchor = anchor_text.strip().lower()
    if len(anchor) >= 10:  # longer descriptive text
        score += 1.0
    if "report" in anchor or "advisory" in anchor or "analysis" in anchor or "research" in anchor:
        score += 1.5
    if "here" in anchor or "this" in anchor or "link" in anchor:
        score -= 1.0  # generic link text

    # ---- 8. Surrounding text keywords ----
    if re.search(r'\b(research|analysis|report|technical|writeup|disclosure|advisory|campaign|blog|details)\b',
                 surrounding_text, re.I):
        score += 2.0

    # ---- 9. URL depth: prefer deeper paths (more specific) ----
    depth = len([s for s in parsed.path.split('/') if s]) if parsed.path else 0
    if depth >= 3:
        score += 1.0
    elif depth == 0:
        score -= 2.0

    # ---- 10. Avoid social media ----
    if any(dom in parsed.netloc for dom in ['twitter.com', 'x.com', 'facebook.com', 'linkedin.com', 'youtube.com']):
        score -= 10.0

    # Ensure score is not negative (we'll use threshold later)
    return score


# ------------------------------------------------------------
# Enhanced body container detection (shared)
# ------------------------------------------------------------
def _get_body_container(soup: BeautifulSoup) -> Optional[BeautifulSoup]:
    """
    Return the main article body container, excluding sidebars, footers, etc.
    Uses a broad set of selectors to catch common CMS patterns.
    """
    # Comprehensive list of selectors used by _extract_body_semantic plus additional ones
    selectors = [
        {'tag': 'article'},
        {'tag': 'main'},
        {'class_': 'entry-content'},
        {'class_': 'post-content'},
        {'class_': 'article-content'},
        {'class_': 'article-body'},
        {'class_': 'blog-content'},
        {'class_': 'content-body'},
        {'id': 'article-body'},
        {'id': 'main-content'},
        {'class_': 'td-post-content'},          # SecurityAffairs
        {'class_': 'bc_article'},              # BleepingComputer
        {'class_': 'post-content'},            # general
    ]
    for sel in selectors:
        tag = sel.pop('tag', None)
        el = soup.find(tag or True, **sel) if sel else soup.find(tag)
        if el:
            # Remove unwanted elements (sidebar, footer, nav, related, etc.)
            for unwanted in el.find_all(class_=re.compile(r"(sidebar|footer|nav|navigation|related|share|comment|bio)", re.I)):
                unwanted.decompose()
            for unwanted in el.find_all(id=re.compile(r"(sidebar|footer|nav|navigation|related|share|comment|bio)", re.I)):
                unwanted.decompose()
            return el
    return None


def extract_original_source_url(soup: BeautifulSoup, publisher_url: str) -> Optional[str]:
    """
    Scan the article body for outbound links to known authoritative / primary-research
    domains and return the best candidate URL, or None if nothing qualitative is found.

    Strategy (in priority order):
    1. Explicit "via / source / original report" anchor patterns pointing to authoritative domains.
    2. Any outbound authoritative link found inside the article body containers
       (scored by path pattern + anchor text quality).
    3. Fallback: first authoritative outbound link found anywhere in <article>/<main>.
    """
    publisher_root = _netloc_root(urlparse(publisher_url).netloc.lower().lstrip("www."))

    # Use the enhanced container detection
    body_container = _get_body_container(soup) or soup

    # Now collect all candidate links from the body container
    candidates: List[Tuple[float, str]] = []  # (score, url)

    for a_tag in body_container.find_all("a", href=True):
        href = a_tag.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue

        # Resolve relative URLs
        try:
            href = urljoin(publisher_url, href)
            parsed = urlparse(href)
        except Exception:
            continue

        if parsed.scheme not in ("http", "https"):
            continue

        # Skip self-links and same-domain links
        link_root = _netloc_root(parsed.netloc.lower().lstrip("www."))
        if link_root == publisher_root:
            continue

        # Skip other known publisher aggregators as "original" sources
        if _is_publisher(href):
            continue

        # Must be authoritative (primary research domain)
        if not _is_authoritative(href):
            continue

        if _is_generic_url(href):
            continue

        anchor_text = a_tag.get_text(strip=True)
        # Gather surrounding text: parent element up to 300 chars
        parent = a_tag.parent
        surrounding = parent.get_text(separator=" ", strip=True)[:300] if parent else ""

        parent_text = parent.get_text(" ", strip=True) if parent else ""
        explicit_source_signal = bool(
            _SOURCE_SECTION_PATTERNS.search(parent_text)
            or _VIA_PATTERNS.search(surrounding)
            or _VIA_PATTERNS.search(anchor_text)
            or _is_valid_original_source_url(href)
        )

        if not explicit_source_signal:
            continue

        score = _score_candidate(href, anchor_text, surrounding, soup, a_tag, body_container, publisher_root)
        # Only consider if score positive (we have a threshold later)
        if score > 0:
            # Use normalized URL for storage (remove tracking)
            norm = _normalize_url(href)
            candidates.append((score, norm))

    if not candidates:
        return None

    # Sort by score descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_url = candidates[0]

    # Confidence threshold: lowered to 4.0 to catch valid links that are not in
    # the top/bottom 40% of the article (e.g., links in the middle).
    # We already filter authoritative domains and reject generic pages,
    # so a score >= 4.0 is a strong signal.
    if best_score < 4.0:
        logger.debug(f"Best candidate score {best_score:.2f} below threshold for {publisher_url}")
        return None

    logger.debug(f"Original source candidate: {best_url} (score={best_score:.2f}) for {publisher_url}")
    return best_url


# ---------------------------------------------------------------------------
# Listing page detection helpers (using the enhanced container)
# ---------------------------------------------------------------------------

def _has_article_schema(soup: BeautifulSoup) -> bool:
    """
    Check if meta tags or JSON‑LD indicate this is an article.
    Returns True if there is strong evidence.
    """
    # Open Graph
    og_type = soup.find('meta', {'property': 'og:type'})
    if og_type and og_type.get('content', '').lower() in ('article', 'newsarticle', 'blogposting'):
        return True

    # JSON‑LD
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            raw = script.get_text(strip=True)
            if not raw:
                continue
            data = json.loads(raw)
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                types = item.get('@type')
                if isinstance(types, list):
                    if any('article' in t.lower() for t in types if isinstance(t, str)):
                        return True
                elif isinstance(types, str) and 'article' in types.lower():
                    return True
        except Exception:
            pass
    return False


def _is_listing_page(title: str, body_html: str, soup: BeautifulSoup, url: str) -> bool:
    """
    Heuristically detect category / tag / archive / search / index pages.
    Returns True if score >= 6, meaning we should reject this page.
    """
    score = 0

    # 1. Title phrases (only safe, explicit ones)
    if title:
        title_lower = title.lower()
        safe_phrases = [
            'latest news', 'reports & analysis', 'category archives',
            'tag archives', 'search results', 'browse by category',
            'all posts', 'archive'
        ]
        for phrase in safe_phrases:
            if phrase in title_lower:
                score += 3
                break

    # 2. URL path patterns (exact segments)
    parsed = urlparse(url)
    path = parsed.path
    if re.search(r'/(?:category|tag|archive|search|index|home)(?:/|$)', path, re.IGNORECASE):
        score += 2

    # 3. Body analysis (use the same container as the parser)
    container = _get_body_container(soup)
    if container:
        body_text = container.get_text(separator=" ", strip=True)
        word_count = len(body_text.split())
        if word_count < 80:
            score += 2

        # Link density and count (only inside container)
        links = container.find_all('a', href=True)
        if links:
            link_chars = sum(len(a.get_text(strip=True)) for a in links)
            total_chars = len(body_text)
            if total_chars > 0:
                density = link_chars / total_chars
                if density > 0.15 and len(links) >= 5:
                    score += 2

    # 4. Strong anti‑reject signal: article schema
    if _has_article_schema(soup):
        score -= 3  # gentle reduction, not a hard block

    return score >= 6


# ---------------------------------------------------------------------------
# Existing helpers (unchanged except for integration)
# ---------------------------------------------------------------------------

@retry_network
async def fetch_article_html(session: aiohttp.ClientSession, url: str) -> str:
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
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "Sec-Ch-Ua": '"Chromium";v="120", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "DNT": "1",
        "Referer": "https://www.google.com/",
    }
    async with session.get(url, headers=headers, timeout=settings.REQUEST_TIMEOUT_SECONDS) as resp:
        if resp.status != 200:
            raise IngestionError(f"Article fetch failed: {resp.status} for {url}")
        charset = resp.charset or 'utf-8'
        try:
            return await resp.text(encoding=charset)
        except UnicodeDecodeError:
            raw = await resp.read()
            return raw.decode('utf-8', errors='replace')


_ARTICLE_TYPES = {
    'Article', 'NewsArticle', 'BlogPosting', 'TechArticle',
    'Report', 'ScholarlyArticle', 'AnalysisNewsArticle'
}

def _extract_author_name(author_field) -> Optional[str]:
    """Normalize author: str, dict, or list."""
    if not author_field:
        return None
    if isinstance(author_field, str):
        return author_field.strip() or None
    if isinstance(author_field, dict):
        return (author_field.get('name') or '').strip() or None
    if isinstance(author_field, list):
        names = []
        for a in author_field:
            if isinstance(a, dict):
                n = a.get('name', '')
            else:
                n = str(a)
            if n.strip():
                names.append(n.strip())
        return ', '.join(names) if names else None
    return None

def parse_json_ld(soup: BeautifulSoup) -> Dict[str, Any]:
    data = {}
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            raw = script.string
            if not raw:
                continue
            content = json.loads(raw)

            # Unwrap @graph
            if isinstance(content, dict) and '@graph' in content:
                graph = content['@graph']
                if isinstance(graph, list):
                    content = graph

            candidates = content if isinstance(content, list) else [content]

            for item in candidates:
                if not isinstance(item, dict):
                    continue
                item_type = item.get('@type', '')
                if isinstance(item_type, list):
                    matched = any(t in _ARTICLE_TYPES for t in item_type)
                else:
                    matched = item_type in _ARTICLE_TYPES

                if not matched:
                    continue

                data['headline'] = item.get('headline') or item.get('name')
                data['author'] = _extract_author_name(item.get('author'))
                data['datePublished'] = item.get('datePublished')
                data['dateModified'] = item.get('dateModified')
                data['description'] = item.get('description')
                article_body = item.get('articleBody')
                if article_body:
                    data['body'] = article_body
                break
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    return data


def extract_date_from_text(text: str) -> Optional[datetime]:
    patterns = [
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b',
        r'\b\d{4}-\d{1,2}-\d{1,2}\b',
        r'\b\d{1,2}/\d{1,2}/\d{4}\b',
        r'\b\d{4}\.\d{2}\.\d{2}\b',
        r'\b\d{4}/\d{1,2}/\d{1,2}\b',
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            try:
                dt = dateparser.parse(
                    match.group(),
                    settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True, 'PREFER_DATES_FROM': 'past'}
                )
                if dt:
                    return dt
            except Exception:
                pass
    return None


def is_cti_relevant(title: str, body: str) -> bool:
    title_text = (title or "").lower()
    body_text = (body or "").lower()
    combined = f"{title_text} {body_text[:1500]}"

    if _PROMOTIONAL_PATTERNS.search(combined):
        return False

    matched_keywords = {kw for kw in settings.CTI_KEYWORDS if kw in combined}
    if not matched_keywords:
        return False

    if len(matched_keywords) >= 2:
        return True

    if re.search(r'\bcve-\d{4}-\d{4,7}\b', combined):
        return True

    single_hit = next(iter(matched_keywords))
    strong_single_hits = {
        'vulnerability', 'exploit', 'malware', 'ransomware', 'phishing',
        'breach', 'incident', 'threat', 'attack', 'intrusion', 'advisory', 'cve',
    }
    if single_hit in strong_single_hits and len(body_text.split()) >= 200:
        return True

    return False


def is_title_generic(title: str) -> bool:
    if not title:
        return True
    t = title.lower().strip()
    generic = {
        'home', 'blog', 'news', 'contact', 'about', 'privacy policy',
        'terms of service', 'sitemap', 'resources', 'search', 'archive',
        'newsletter', 'subscribe', 'login', 'register',
    }
    if t in generic:
        return True
    if len(t) <= 3:
        return True
    if re.match(r'^(home|blog|news|resources|about|contact|security|sitemap)$', t):
        return True
    if _LISTING_TITLE_PATTERNS.search(t):
        return True
    return False


def _extract_body_trafilatura(html: str, url: str) -> Optional[str]:
    """Try trafilatura with precision first, then recall, to handle thin advisory pages."""
    for favor_precision in (True, False):
        try:
            extracted = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                include_images=False,
                favor_precision=favor_precision,
                deduplicate=True,
            )
            if extracted and len(extracted) >= settings.MIN_BODY_LENGTH:
                return f"<p>{extracted.replace(chr(10), '</p><p>')}</p>"
        except Exception as e:
            logger.debug(f"trafilatura error (precision={favor_precision}) for {url}: {e}")
    return None


def _extract_body_semantic(soup: BeautifulSoup) -> Optional[str]:
    """Fallback: pull text from semantic HTML containers."""
    for selector in (
        {'tag': 'article'},
        {'tag': 'main'},
        {'class_': 'entry-content'},
        {'class_': 'post-content'},
        {'class_': 'article-content'},
        {'class_': 'article-body'},
        {'class_': 'blog-content'},
        {'class_': 'content-body'},
        {'id': 'article-body'},
        {'id': 'main-content'},
    ):
        tag = selector.pop('tag', None)
        el = soup.find(tag or True, **selector) if selector else soup.find(tag)
        if el:
            text = el.get_text(separator='\n', strip=True)
            if len(text) >= 200:
                paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 20]
                if paragraphs:
                    return '<p>' + '</p><p>'.join(paragraphs) + '</p>'
    return None


def extract_article_data(
    html: str,
    url: str,
    source_name: str,
    rss_title: Optional[str] = None,
    rss_date: Optional[str] = None,
    rss_author: Optional[str] = None,
    rss_content: Optional[str] = None,
) -> Tuple[Optional[RawArticle], Optional[str]]:
    """
    Parse a publisher article page.

    Returns:
        (RawArticle, detected_original_source_url)

    The returned RawArticle always reflects the *publisher* article at this
    stage.  Resolution and fetching of the original source is handled by
    SourceManager so that network I/O stays in one place.

    detected_original_source_url is the best candidate URL found in the body
    pointing to an authoritative primary-research page (or None).
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        logger.error(f"HTML parse failed for {url}: {e}")
        return None, None

    # 1. JSON-LD (highest fidelity)
    json_ld = parse_json_ld(soup)
    title = json_ld.get('headline')
    author = json_ld.get('author')
    published_str = json_ld.get('datePublished')
    published: Optional[datetime] = None
    if published_str:
        try:
            published = parse_article_timestamp(published_str)
        except Exception:
            pass
    body_html = json_ld.get('body', '')

    # 2. OpenGraph / meta
    if not title:
        for meta_sel in [
            {'property': 'og:title'},
            {'name': 'twitter:title'},
        ]:
            meta = soup.find('meta', meta_sel)
            if meta and meta.get('content', '').strip():
                title = meta['content'].strip()
                break
    if not author:
        for meta_sel in [
            {'name': 'author'},
            {'property': 'article:author'},
            {'name': 'byl'},
        ]:
            meta = soup.find('meta', meta_sel)
            if meta and meta.get('content', '').strip():
                author = meta['content'].strip()
                break

    # 3. RSS metadata (reliable, prefer over fragile HTML)
    if not title and rss_title:
        title = rss_title.strip()
    if not author and rss_author:
        author = rss_author.strip()
    if not published and rss_date:
        try:
            published = parse_article_timestamp(rss_date)
        except Exception:
            pass

    # 4. HTML semantic title fallbacks
    if not title:
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        title_tag = soup.find('title')
        if title_tag:
            raw_title = title_tag.get_text(strip=True)
            title = raw_title
            for sep in ['|', '-', '»', '–', ':']:
                if sep in raw_title:
                    parts = raw_title.split(sep)
                    if len(parts[0].strip()) > 10:
                        title = parts[0].strip()
                        break

    # 5. Date fallbacks (meta tags → <time> → URL → text scan)
    if not published:
        date_meta_props = [
            'article:published_time', 'og:published_time', 'datePublished',
            'article:modified_time', 'og:updated_time', 'DC.date',
            'date', 'pubdate',
        ]
        for meta in soup.find_all('meta'):
            prop = meta.get('property') or meta.get('name') or ''
            if prop.lower() in [p.lower() for p in date_meta_props]:
                try:
                    published = parse_article_timestamp(meta.get('content', ''))
                    break
                except Exception:
                    pass

    if not published:
        for time_tag in soup.find_all('time'):
            dt_attr = (
                time_tag.get('datetime')
                or time_tag.get('data-datetime')
                or time_tag.get('data-time')
            )
            if dt_attr:
                try:
                    published = parse_article_timestamp(dt_attr)
                    break
                except Exception:
                    pass
            if not published:
                dt = extract_date_from_text(time_tag.get_text(strip=True))
                if dt:
                    published = dt
                    break

    if not published:
        match = re.search(r'/(\d{4})/(\d{1,2})(?:/(\d{1,2}))?/', url)
        if match:
            year, month, day = match.groups()
            day = day or '1'
            try:
                published = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
            except Exception:
                pass

    if not published:
        date_match = re.search(r'[?&](?:date|published|pub)[_-]?(?:date)?=(\d{4}-\d{2}-\d{2})', url, re.I)
        if date_match:
            try:
                published = parse_article_timestamp(date_match.group(1))
            except Exception:
                pass

    if not published:
        main_text = soup.get_text()
        dt = extract_date_from_text(main_text[:3000])
        if dt:
            published = dt

    # 6. Author fallbacks
    if not author:
        for cls in ['author', 'byline', 'post-author', 'article-author', 'entry-author', 'author-name']:
            el = soup.find(class_=cls)
            if el:
                author = el.get_text(strip=True)
                break
    if not author:
        rel_author = soup.find('a', {'rel': 'author'})
        if rel_author:
            author = rel_author.get_text(strip=True)
    if not author:
        author = "Unknown"

    if _is_generic_url(url):
        logger.info(f"Skipping generic/listing URL: {title} ({url})")
        return None, None

    # 7. Body extraction
    if rss_content and len(rss_content) >= settings.MIN_BODY_LENGTH:
        body_html = rss_content

    if not body_html or len(body_html) < settings.MIN_BODY_LENGTH:
        extracted = _extract_body_trafilatura(html, url)
        if extracted:
            body_html = extracted

    if not body_html or len(body_html) < settings.MIN_BODY_LENGTH:
        extracted = _extract_body_semantic(soup)
        if extracted:
            body_html = extracted

    if not body_html or len(body_html) < settings.MIN_BODY_LENGTH:
        og_desc = soup.find('meta', {'property': 'og:description'}) or soup.find('meta', {'name': 'description'})
        if og_desc and og_desc.get('content', '').strip():
            body_html = f"<p>{og_desc['content'].strip()}</p>"

    if not body_html or len(body_html.strip()) < settings.MIN_BODY_LENGTH:
        logger.warning(f"Could not extract article body for {url}")
        return None, None

    # 8. Validate
    if not title or is_title_generic(title):
        logger.info(f"Skipping article with invalid title: '{title}' ({url})")
        return None, None
    if not published:
        logger.info(f"Skipping article without date: {title} ({url})")
        return None, None
    if not is_cti_relevant(title, body_html):
        logger.info(f"Skipping non-CTI article: {title} ({url})")
        return None, None
    if len(body_html.strip()) < settings.MIN_BODY_LENGTH:
        logger.warning(f"Extracted body too short ({len(body_html.strip())} chars) for {url} – skipping")
        return None, None

    # ------------------------------------------------------------------
    # Reject category / listing pages before creating RawArticle
    # ------------------------------------------------------------------
    if _is_listing_page(title, body_html, soup, url):
        logger.info(f"Skipping listing page: {title} ({url})")
        return None, None

    # 9. Detect original source URL from the publisher article body.
    detected_original_source_url = extract_original_source_url(soup, url)

    # Also check canonical tag as a secondary signal (only if it points to a
    # different domain, which can happen when a vendor posts a cross-site canonical).
    if not detected_original_source_url:
        canonical = soup.find('link', {'rel': 'canonical'})
        if canonical and canonical.get('href'):
            cand = canonical['href'].strip()
            if (
                cand != url
                and _is_authoritative(cand)
                and not _is_publisher(cand)
                and _is_valid_original_source_url(cand)
            ):
                detected_original_source_url = cand

    raw_article = RawArticle.from_metadata(
        source_domain=source_name,
        source_url=url,
        title=title,
        author=author,
        published=published,
        html=body_html,
        original_source_url=detected_original_source_url,
    )
    return raw_article, detected_original_source_url