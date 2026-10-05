"""
processor.py – Module 2: LLM-based CTI entity extraction (Gemini backend).

Pipeline
--------
  ArticleProcessor.run()
    → _ping_llm()                 Fail-fast check that Gemini is reachable
    → _fetch_pending()            Pull PENDING rows from staging_raw
    → _clean_html()               HTML → plain text via trafilatura
    → _build_messages()           Prompt construction (system + 1-shot + user)
    → LLMClient.generate()        Gemini batched generation (JSON mode)
    → _attempt_parse()            Robust JSON extraction + normalisation
    → _merge_iocs()               Union of LLM output and regex fallback
    → verify_article()            Confidence scoring against original text
    → _filter_verified_entities() Remove unverifiable values
    → fetch_cve_details()         NVD enrichment (Phase 3, best-effort)
    → _save_and_mark()            Persist to DB with severity/TLP/CVE details
"""

import asyncio
import difflib
import logging
import re
import time
import json
import string
import sys
import os
import html
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup: allow imports from both `src.` and `app.` namespaces.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BACKEND_ROOT = _REPO_ROOT / "backend"
if _BACKEND_ROOT.exists() and str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Fallback: if for any reason backend isn't importable, load cve_api.py
# directly from its file path so the pipeline never hard-fails.
try:
    from app.utils.cve_api import fetch_cve_details
except ImportError:  # pragma: no cover
    import importlib.util as _importlib_util
    _cve_path = _BACKEND_ROOT / "app" / "utils" / "cve_api.py"
    _spec = _importlib_util.spec_from_file_location("cve_api_fallback", _cve_path)
    _cve_mod = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_cve_mod)
    fetch_cve_details = _cve_mod.fetch_cve_details

import trafilatura
from bs4 import BeautifulSoup
from pydantic import ValidationError

from src.shared.database import DatabaseClient
from src.core.config import settings
from src.module_2_llm_processing.models import (
    ProcessedArticle, IOCCollection, ThreatMetadata,
)
from src.module_2_llm_processing.llm_client import LLMClient
from src.module_2_llm_processing.verification import (
    verify_article, VerificationResult,
)

logger = logging.getLogger(__name__)

if os.getenv("DEBUG_WRITE_FILES", "false").lower() == "true":
    Path("logs").mkdir(exist_ok=True)


# --------------------------------------------------------------------------- #
# SYSTEM PROMPT
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = (
    "You are a CTI extraction engine. You receive one cybersecurity article "
    "and return a single JSON object with the exact schema below.\n"
    "\n"
    "Extraction rules:\n"
    "  1. Only extract information explicitly stated in the article.\n"
    "  2. Never invent placeholders (e.g. CVE-2026-XXXXX, 999.1.2.3).\n"
    "  3. Missing fields must be [] or \"\".\n"
    "  4. Do not reuse entities from the format example.\n"
    "  5. Do not output markdown, comments, or prose outside the JSON object.\n"
    "\n"
    "Severity rubric (choose ONE):\n"
    "  - \"Critical\": active exploitation, mass impact, zero-day, or widely\n"
    "    deployed ransomware. Includes CVSS >= 9.0 with known exploitation.\n"
    "  - \"High\": targeted APT activity, known-exploited vulnerability,\n"
    "    significant data breach, or CVSS >= 7.0 with plausible exploitation.\n"
    "  - \"Medium\": proof-of-concept, limited-scope vulnerability, moderate\n"
    "    threat, or CVSS 4.0–6.9.\n"
    "  - \"Low\": informational, low-impact issue, no active exploitation,\n"
    "    or CVSS < 4.0.\n"
    "  - \"Unknown\": insufficient information to judge.\n"
    "\n"
    "TLP rubric (choose ONE, per FIRST TLP v2.0):\n"
    "  - \"TLP:RED\": named recipients only; sharing outside is prohibited.\n"
    "    Use ONLY if the article itself is marked TLP:RED or equivalent.\n"
    "  - \"TLP:AMBER\": limited disclosure; sharing within the recipient org\n"
    "    and its clients only. Use if the article is marked TLP:AMBER.\n"
    "  - \"TLP:GREEN\": community-wide sharing (e.g. sector, country).\n"
    "  - \"TLP:CLEAR\": public / unrestricted. DEFAULT for public advisories.\n"
    "  If the article does not state a TLP, default to TLP:CLEAR.\n"
    "\n"
    "Schema:\n"
    "{\n"
    "  \"summary\": \"...\",\n"
    "  \"severity\": \"Unknown\",\n"
    "  \"tlp_tag\": \"TLP:CLEAR\",\n"
    "  \"iocs\": {\n"
    "    \"ip\":[], \"domain\":[], \"url\":[], \"md5\":[], \"sha1\":[], \"sha256\":[],\n"
    "    \"cve\":[], \"email\":[], \"file_name\":[], \"registry_key\":[], \"mutex\":[], \"malware_family\":[]\n"
    "  },\n"
    "  \"threat_metadata\": {\n"
    "    \"threat_actor\":[], \"malware_name\":[], \"attack_type\":[],\n"
    "    \"target_organization\":[], \"target_industry\":[], \"target_country\":[],\n"
    "    \"mitre_techniques\":[], \"affected_software\":[], \"campaign_name\":[], \"ransomware_family\":[]\n"
    "  }\n"
    "}"
)

FALLBACK_PROMPT = "\n\nOutput ONLY raw JSON with the exact schema. No extra text."


# --------------------------------------------------------------------------- #
# REGEX PATTERNS
# --------------------------------------------------------------------------- #
IPV4_PATTERN = re.compile(
    r'(?<![.\d])'
    r'(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
    r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)'
    r'(?![.\d])'
)
IPV6_PATTERN = re.compile(
    r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'
    r'|\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b'
    r'|\b::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}\b'
    r'|\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b'
)
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')

MD5_PATTERN    = re.compile(r'(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])')
SHA1_PATTERN   = re.compile(r'(?<![0-9a-fA-F])[0-9a-fA-F]{40}(?![0-9a-fA-F])')
SHA256_PATTERN = re.compile(r'(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])')

CVE_PATTERN = re.compile(r'\bCVE-\d{4}-\d{4,7}\b', re.IGNORECASE)
MITRE_PATTERN = re.compile(r'\b[Tt]\d{4}(?:\.\d{3})?\b')

REGISTRY_PATTERN = re.compile(
    r'\b(?:HKEY_LOCAL_MACHINE|HKEY_CURRENT_USER|HKEY_CLASSES_ROOT|'
    r'HKEY_USERS|HKEY_CURRENT_CONFIG|HKLM|HKCU|HKCR|HKU|HKCC)'
    r'\\[A-Za-z0-9_\\\-\.]+\b'
)
MUTEX_PATTERN = re.compile(
    r'\b(?:Global|Local)\\[^\s<>{}\[\]"\'`\\]{3,64}\b'
    r'|\bMutex[A-Za-z0-9_\-]{3,32}\b'
    r'|\b[A-Za-z][A-Za-z0-9_\-]{2,20}Mutex\b'
)
FILE_NAME_PATTERN = re.compile(
    r'\b\w[\w\-\.]{0,64}'
    r'\.(?:exe|dll|sys|bat|cmd|ps1|vbs|js|hta|scr|pif|jar|apk|ipa|sh|py|pl|rb)\b',
    re.IGNORECASE
)
DOMAIN_PATTERN = re.compile(r'\b(?:[a-zA-Z0-9\-]+\.){1,10}[a-zA-Z]{2,}\b')


# --------------------------------------------------------------------------- #
# BLOCKLISTS
# --------------------------------------------------------------------------- #
_DOMAIN_BLOCKLIST = frozenset({
    'python', 'golang', 'rust', 'kotlin', 'swift', 'scala', 'clojure',
    'erlang', 'elixir', 'haskell', 'dart', 'perl', 'ruby', 'lua', 'julia',
    'node.js', 'react', 'angular', 'vue', 'svelte', 'django', 'flask',
    'spring', 'rails', 'laravel', 'express', 'fastapi', 'nextjs', 'nuxt',
    'npm', 'yarn', 'pip', 'cargo', 'maven', 'gradle', 'cmake', 'make',
    'webpack', 'babel', 'vite', 'rollup',
    'example.com', 'localhost', 'test.com',
    'mysql', 'postgresql', 'mongodb', 'redis', 'kafka', 'elasticsearch',
    'fonts.googleapis.com', 'ajax.googleapis.com', 'cdnjs.cloudflare.com',
    'jquery.com', 'bootstrapcdn.com',
})
_FILE_EXTENSIONS = frozenset({
    '.exe', '.dll', '.sys', '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.zip', '.rar', '.7z', '.js', '.vbs', '.ps1', '.bat', '.cmd',
    '.sh', '.py', '.jar', '.apk', '.ipa', '.hta', '.scr',
})
_PRIVATE_IP_PREFIXES = ('10.', '192.168.', '127.', '0.', '255.')
_PRINTABLE = frozenset(string.printable)


# --------------------------------------------------------------------------- #
# Key alias map
# --------------------------------------------------------------------------- #
_KEY_ALIAS: Dict[str, str] = {
    "ioc": "iocs", "iobs": "iocs", "indicators": "iocs",
    "Iocs": "iocs", "IoCs": "iocs", "IOCs": "iocs",
    "metadata": "threat_metadata", "ThreatMetadata": "threat_metadata",
    "threat_meta": "threat_metadata", "threat_metadta": "threat_metadata",
    "threat_metdata": "threat_metadata",
    "summary": "summary",
    "severity": "severity", "Severity": "severity",
    "tlp": "tlp_tag", "tlp_tag": "tlp_tag", "TLP": "tlp_tag", "TLP_Tag": "tlp_tag",
    "IP": "ip", "ipv4": "ip", "ip_v4": "ip", "ipv6": "ip", "ips": "ip",
    "Domain": "domain", "domains": "domain", "hostname": "domain",
    "hostnames": "domain", "domain_fqdn": "domain", "fqdn": "domain",
    "URL": "url", "urls": "url", "uri": "url", "uris": "url",
    "MD5": "md5", "md": "md5", "md5_hash": "md5", "md5hash": "md5",
    "SHA1": "sha1", "sha_1": "sha1", "sha1_hash": "sha1",
    "SHA256": "sha256", "sha_256": "sha256", "sha25": "sha256",
    "sha2": "sha256", "sha256_hash": "sha256",
    "sha512": "sha256", "SHA512": "sha256",
    "CVE": "cve", "cves": "cve",
    "Email": "email", "emails": "email", "email_address": "email",
    "FileName": "file_name", "filenames": "file_name", "file_names": "file_name",
    "file": "file_name", "filename": "file_name", "files": "file_name",
    "RegistryKey": "registry_key", "reg_key": "registry_key",
    "regkey": "registry_key", "registry": "registry_key",
    "registry_keys": "registry_key",
    "Mutex": "mutex", "mutexes": "mutex", "mutices": "mutex",
    "MalwareFamily": "malware_family", "malwares": "malware_family",
    "malware": "malware_family", "malware_families": "malware_family",
    "ThreatActor": "threat_actor", "threatactors": "threat_actor",
    "threat_actors": "threat_actor", "actor": "threat_actor",
    "actors": "threat_actor",
    "MalwareName": "malware_name", "malwarename": "malware_name",
    "malware_names": "malware_name",
    "AttackType": "attack_type", "attacktype": "attack_type",
    "attack_types": "attack_type", "attack": "attack_type",
    "TargetIndustry": "target_industry", "targetindustry": "target_industry",
    "target_industries": "target_industry", "industry": "target_industry",
    "TargetCountry": "target_country", "targetcountry": "target_country",
    "target_countries": "target_country", "country": "target_country",
    "countries": "target_country",
    "TargetOrganization": "target_organization",
    "targetorg": "target_organization",
    "target_org": "target_organization",
    "target_organisation": "target_organization",
    "organisation": "target_organization",
    "organization": "target_organization",
    "org": "target_organization",
    "MitreTechniques": "mitre_techniques", "mitre": "mitre_techniques",
    "techniques": "mitre_techniques", "mitre_technique": "mitre_techniques",
    "mitre_techiques": "mitre_techniques",
    "mitre_tecniques": "mitre_techniques",
    "mitre_technique_ids": "mitre_techniques",
    "mitre_attack": "mitre_techniques",
    "AffectedSoftware": "affected_software", "affectedsoftware": "affected_software",
    "affected_softwares": "affected_software", "software": "affected_software",
    "CampaignName": "campaign_name", "campaign": "campaign_name",
    "campaigns": "campaign_name",
    "RansomwareFamily": "ransomware_family", "ransomware": "ransomware_family",
    "ransom_family": "ransomware_family", "ransomware_families": "ransomware_family",
}

_IOC_LIST_FIELDS = frozenset({
    "ip", "domain", "url", "md5", "sha1", "sha256", "cve", "email",
    "file_name", "registry_key", "mutex", "malware_family",
})
_META_LIST_FIELDS = frozenset({
    "threat_actor", "malware_name", "attack_type", "target_organization",
    "target_industry", "target_country", "mitre_techniques",
    "affected_software", "campaign_name", "ransomware_family",
})
_ALL_LIST_FIELDS = _IOC_LIST_FIELDS | _META_LIST_FIELDS

_FUZZY_CANONICAL_KEYS: List[str] = [
    k for k in (
        list(_IOC_LIST_FIELDS) + list(_META_LIST_FIELDS)
        + ["iocs", "threat_metadata"]
    )
    if len(k) > 4
]

_REGEX_ALWAYS_MERGE  = frozenset({"ip", "cve", "md5", "sha1", "sha256", "url"})
_REGEX_FALLBACK_ONLY = frozenset({
    "domain", "email", "file_name", "registry_key", "mutex", "malware_family",
})


def _fuzzy_resolve_key(key: str) -> Optional[str]:
    if len(key) <= 4:
        return None
    key_lower = key.lower().lstrip("._")
    matches = difflib.get_close_matches(key_lower, _FUZZY_CANONICAL_KEYS, n=1, cutoff=0.6)
    return matches[0] if matches else None


# --------------------------------------------------------------------------- #
# ArticleProcessor
# --------------------------------------------------------------------------- #
class ArticleProcessor:

    def __init__(
        self,
        llm_client: LLMClient,
        db: DatabaseClient,
        batch_size: int = None,
        max_retries: int = 1,
    ):
        self.client = llm_client
        self.db = db
        self.batch_size = batch_size or settings.LLM_BATCH_SIZE
        self.max_retries = max_retries
        self.debug = os.getenv("DEBUG_WRITE_FILES", "false").lower() == "true"

    # ------------------------------------------------------------------ #
    # LLM health check
    # ------------------------------------------------------------------ #
    async def _ping_llm(self) -> None:
        logger.info("Pinging Gemini model '%s'…", getattr(self.client, "model_name", "?"))
        try:
            responses = await self.client.generate(
                [[
                    {"role": "system", "content": "You output only valid JSON."},
                    {"role": "user", "content": 'Return exactly: {"ok": true}'},
                ]],
                max_new_tokens=64,
                temperature=0.0,
            )
            snippet = (responses[0] or "").strip()[:120] if responses else "<empty>"
            if not snippet:
                raise RuntimeError("Gemini ping returned empty text.")
            logger.info("✅ Gemini ping OK: %s", snippet)
        except Exception as exc:
            logger.exception("Gemini ping FAILED — aborting run.")
            raise RuntimeError(
                f"LLM not reachable. Check GEMINI_API_KEY and "
                f"GEMINI_MODEL_NAME='{getattr(self.client, 'model_name', '?')}'. "
                f"Underlying error: {type(exc).__name__}: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    # HTML cleanup
    # ------------------------------------------------------------------ #
    def _clean_html(self, html_content: str) -> str:
        if not html_content:
            return ""
        text = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if text:
            return html.unescape(text).strip()
        soup = BeautifulSoup(html_content, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        lines = [
            ln.strip() for ln in soup.get_text(separator="\n").splitlines()
            if ln.strip()
        ]
        return html.unescape("\n".join(lines))

    def _semantic_truncate(
        self,
        text: str,
        max_chars: int = 16_000,
        head_chars: int = 9_000,
        tail_chars: int = 3_000,
    ) -> str:
        if len(text) <= max_chars:
            return text

        lines = text.splitlines(keepends=True)
        ioc_line_re = re.compile(
            r'(?:[0-9a-fA-F]{32,64})'
            r'|(?:\b(?:25[0-5]|2[0-4]\d|[01]?\d\d?)'
            r'(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)){3}\b)'
            r'|CVE-\d{4}-\d{4,7}'
            r'|[Tt]\d{4}(?:\.\d{3})?'
            r'|https?://'
            r'|\b\w+\.(?:exe|dll|sys|ps1|bat|vbs|js|hta|scr|jar)\b'
            r'|HKEY_(?:LOCAL_MACHINE|CURRENT_USER|CLASSES_ROOT|USERS|CURRENT_CONFIG)'
            r'|\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
            re.IGNORECASE,
        )
        ioc_lines: List[str] = []
        prose_lines: List[str] = []
        for ln in lines:
            (ioc_lines if ioc_line_re.search(ln) else prose_lines).append(ln)

        ioc_block = "".join(ioc_lines)
        prose_text = "".join(prose_lines)

        remaining = max_chars - len(ioc_block) - 60
        if remaining < 0:
            ioc_block = ioc_block[: max_chars - 60]
            remaining = 0

        prose_head_chars = min(head_chars, remaining * 3 // 4)
        prose_tail_chars = min(tail_chars, remaining - prose_head_chars)
        head = prose_text[:prose_head_chars]
        tail = prose_text[-prose_tail_chars:] if prose_tail_chars > 0 else ""

        for sep in ('\n\n', '. ', '! ', '? '):
            idx = head.rfind(sep)
            if idx > prose_head_chars // 2:
                head = head[: idx + len(sep)]
                break

        parts = [head]
        if ioc_block:
            parts.append("\n\n[--- IOC TABLE / INDICATOR SECTION ---]\n")
            parts.append(ioc_block)
            parts.append("[--- END IOC SECTION ---]\n\n")
        if tail:
            parts.append("... [content truncated] ...\n\n")
            parts.append(tail)
        return "".join(parts)

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    def _build_messages(self, article: Dict[str, Any]) -> List[Dict[str, str]]:
        title     = article.get("title", "Untitled")
        source    = article.get("source_domain", "Unknown")
        published = article.get("published_utc", "Unknown")
        body      = article.get("cleaned_text", "") or "No article body extracted."
        body      = self._semantic_truncate(body)

        example_user = (
            "Title: Example\n"
            "Article: Threat actor ExampleActor used malware.exe from 192.0.2.1 "
            "targeting the technology sector. CVE-2023-12345 was exploited (T1001). "
            "The attack affected ExampleOrg, a company in the US."
        )
        example_assistant = json.dumps({
            "summary": "ExampleActor used malware.exe and exploited CVE-2023-12345 to target the technology sector.",
            "severity": "High",
            "tlp_tag": "TLP:CLEAR",
            "iocs": {
                "ip": ["192.0.2.1"],
                "domain": [], "url": [], "md5": [], "sha1": [], "sha256": [],
                "cve": ["CVE-2023-12345"], "email": [], "file_name": ["malware.exe"],
                "registry_key": [], "mutex": [], "malware_family": [],
            },
            "threat_metadata": {
                "threat_actor": ["ExampleActor"], "malware_name": [],
                "attack_type": ["Exploitation"],
                "target_organization": ["ExampleOrg"], "target_industry": ["Technology"],
                "target_country": ["US"], "mitre_techniques": ["T1001"],
                "affected_software": [], "campaign_name": [], "ransomware_family": [],
            },
        }, separators=(",", ":"))

        user_content = (
            f"Title: {title}\nDate: {published}\nSource: {source}\n\nArticle:\n{body}"
        )

        return [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": example_user},
            {"role": "assistant", "content": example_assistant},
            {"role": "user",      "content": user_content},
        ]

    # ------------------------------------------------------------------ #
    # Regex extraction
    # ------------------------------------------------------------------ #
    def _extract_iocs_regex(self, text: str) -> Dict[str, List[str]]:
        text = html.unescape(text)
        urls = self._unique_preserve_order(URL_PATTERN.findall(text))
        text_no_urls = URL_PATTERN.sub(" ", text)

        ipv4_raw = IPV4_PATTERN.findall(text_no_urls)
        ipv4_raw += [m.group() for url in urls for m in IPV4_PATTERN.finditer(url)]
        ipv4 = [
            ip for ip in self._unique_preserve_order(ipv4_raw)
            if not any(ip.startswith(pfx) for pfx in _PRIVATE_IP_PREFIXES)
        ]
        ipv6 = self._unique_preserve_order(IPV6_PATTERN.findall(text_no_urls))

        raw_domains = DOMAIN_PATTERN.findall(text_no_urls)
        domains = self._filter_domains(raw_domains)

        emails = self._unique_preserve_order(EMAIL_PATTERN.findall(text))
        email_domains = {e.split("@", 1)[1].lower() for e in emails}
        domains = [d for d in domains if d.lower() not in email_domains]

        sha256 = self._unique_preserve_order(SHA256_PATTERN.findall(text))
        sha256_set = set(sha256)
        sha1 = self._unique_preserve_order([
            h for h in SHA1_PATTERN.findall(text) if h not in sha256_set
        ])
        sha1_set = set(sha1)
        md5 = self._unique_preserve_order([
            h for h in MD5_PATTERN.findall(text)
            if h not in sha256_set and h not in sha1_set
        ])

        cves = self._unique_preserve_order([c.upper() for c in CVE_PATTERN.findall(text)])
        registry = self._unique_preserve_order(REGISTRY_PATTERN.findall(text))
        mutexes = self._unique_preserve_order([
            m for m in MUTEX_PATTERN.findall(text)
            if not any(bl in m.lower() for bl in _DOMAIN_BLOCKLIST)
        ])
        filenames = self._unique_preserve_order(FILE_NAME_PATTERN.findall(text))

        return {
            "ip":           ipv4 + ipv6,
            "domain":       domains,
            "url":          urls,
            "email":        emails,
            "md5":          md5,
            "sha1":         sha1,
            "sha256":       sha256,
            "cve":          cves,
            "registry_key": registry,
            "mutex":        mutexes,
            "file_name":    filenames,
            "malware_family": [],
        }

    def _filter_domains(self, raw_domains: List[str]) -> List[str]:
        seen: set = set()
        result: List[str] = []
        for d in raw_domains:
            dl = d.lower()
            if dl in seen:
                continue
            if any(dl.endswith(ext) for ext in _FILE_EXTENSIONS):
                continue
            if dl in _DOMAIN_BLOCKLIST or any(bl in dl for bl in _DOMAIN_BLOCKLIST):
                continue
            if "." not in d:
                continue
            parts = dl.split(".")
            if len(parts) < 2 or not parts[0]:
                continue
            if all(p.isdigit() for p in parts):
                continue
            seen.add(dl)
            result.append(d)
        return result

    def _extract_mitre_techniques_regex(self, text: str) -> List[str]:
        raw = MITRE_PATTERN.findall(html.unescape(text))
        return self._unique_preserve_order([t.upper() for t in raw])

    # ------------------------------------------------------------------ #
    # Merge logic
    # ------------------------------------------------------------------ #
    def _merge_iocs(
        self, llm_iocs: Dict[str, List], regex_iocs: Dict[str, List],
    ) -> Dict[str, List]:
        merged: Dict[str, List] = {}
        all_keys = set(llm_iocs.keys()) | set(regex_iocs.keys())
        for key in all_keys:
            llm_vals   = list(llm_iocs.get(key) or [])
            regex_vals = list(regex_iocs.get(key) or [])
            if key in _REGEX_ALWAYS_MERGE:
                combined = regex_vals + [
                    v for v in llm_vals
                    if v.lower() not in {x.lower() for x in regex_vals}
                ]
            elif key in _REGEX_FALLBACK_ONLY:
                combined = llm_vals if llm_vals else regex_vals
            else:
                combined = regex_vals + [
                    v for v in llm_vals
                    if v.lower() not in {x.lower() for x in regex_vals}
                ]
            merged[key] = self._unique_preserve_order_ci(combined)
        return merged

    def _unique_preserve_order(self, values: List) -> List[str]:
        seen: set = set()
        result: List[str] = []
        for v in values:
            if v is None:
                continue
            s = str(v).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            result.append(s)
        return result

    def _unique_preserve_order_ci(self, values: List) -> List[str]:
        seen: set = set()
        result: List[str] = []
        for v in values:
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(s)
        return result

    # ------------------------------------------------------------------ #
    # JSON sanitisation
    # ------------------------------------------------------------------ #
    def _strip_js_comments(self, text: str) -> str:
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        lines = []
        for line in text.splitlines():
            in_str = False
            out = []
            i = 0
            while i < len(line):
                ch = line[i]
                if ch == '"' and (i == 0 or line[i - 1] != '\\'):
                    in_str = not in_str
                if not in_str and ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                    break
                out.append(ch)
                i += 1
            lines.append(''.join(out))
        return '\n'.join(lines)

    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        if not text:
            return None

        stripped = text.strip()
        if stripped.startswith("{"):
            result = self._try_parse_json(stripped)
            if result is not None:
                return result

        fences = re.findall(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if fences:
            candidate = fences[-1].strip()
            result = self._try_parse_json(candidate)
            if result is not None:
                return result
            cleaned = self._strip_js_comments(candidate)
            result = self._try_parse_json(cleaned)
            if result is not None:
                return result

        leak_patterns = [
            r'\bassistant\s*\n',
            r'<\|im_start\|>assistant',
            r'ASSISTANT:\s*\n',
        ]
        last_assistant_pos = -1
        for pat in leak_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                if m.start() > last_assistant_pos:
                    last_assistant_pos = m.start()
        if last_assistant_pos != -1:
            after = text[last_assistant_pos:]
            brace_idx = after.find("{")
            if brace_idx != -1:
                candidate = after[brace_idx:]
                for attempt in (candidate, self._strip_js_comments(candidate)):
                    result = self._try_parse_json(attempt)
                    if result is not None:
                        return result
                    result = self._repair_and_parse(attempt)
                    if result is not None:
                        return result

        cleaned = re.sub(r'```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        cleaned = re.sub(r'```\s*', '', cleaned)
        cleaned = self._strip_js_comments(cleaned)
        starts = [m.start() for m in re.finditer(r'\{', cleaned)]

        for start in reversed(starts):
            candidate = self._extract_balanced_braces(cleaned, start)
            if candidate is None:
                continue
            candidate = self._sanitize_printable(candidate)
            for parsed in (
                self._try_parse_json(candidate),
                self._repair_and_parse(candidate),
            ):
                if parsed is not None and self._looks_like_cti_json(parsed):
                    return parsed

        for start in reversed(starts):
            candidate = self._extract_balanced_braces(cleaned, start)
            if candidate is None:
                continue
            candidate = self._sanitize_printable(candidate)
            for parsed in (
                self._try_parse_json(candidate),
                self._repair_and_parse(candidate),
            ):
                if parsed is not None:
                    return parsed
        return None

    def _try_parse_json(self, text: str) -> Optional[Dict]:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _extract_balanced_braces(self, text: str, start: int) -> Optional[str]:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start: i + 1]
        return None

    def _sanitize_printable(self, text: str) -> str:
        return "".join(ch for ch in text if ch in _PRINTABLE)

    def _repair_and_parse(self, text: str) -> Optional[Dict]:
        text = self._strip_js_comments(text)
        steps = [
            lambda t: re.sub(r',(\s*[}\]])', r'\1', t),
            lambda t: re.sub(r'"\$([^"]+)"(\s*:)', r'"\1"\2', t),
            lambda t: re.sub(r'"@([^"]+)"(\s*:)', r'"\1"\2', t),
            lambda t: re.sub(r'(?<=[{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:', r' "\1":', t),
            lambda t: re.sub(r"'([^']*)'", r'"\1"', t),
            lambda t: t.replace("None", "null").replace("True", "true").replace("False", "false"),
            lambda t: re.sub(r'(?<=\w)\n(?=\w)', ' ', t),
        ]
        current = text
        for step in steps:
            try:
                current = step(current)
                result = self._try_parse_json(current)
                if result is not None:
                    return result
            except Exception:
                continue
        return None

    def _looks_like_cti_json(self, data: Dict) -> bool:
        if not isinstance(data, dict):
            return False
        keys = set(data.keys())
        if keys & {
            "iocs", "threat_metadata", "summary", "ioc", "metadata",
            "threat_meta", "severity", "tlp_tag",
        }:
            return True
        known = keys & (_IOC_LIST_FIELDS | _META_LIST_FIELDS)
        return len(known) >= 2

    def _resolve_key(self, key: str) -> str:
        clean_key = key.lstrip("_$@#.")
        if key in _KEY_ALIAS:
            return _KEY_ALIAS[key]
        if clean_key in _KEY_ALIAS:
            return _KEY_ALIAS[clean_key]
        fuzzy = _fuzzy_resolve_key(clean_key)
        if fuzzy:
            return fuzzy
        return clean_key

    def _normalize_json_keys(self, data: Any) -> Any:
        if isinstance(data, dict):
            new_data: Dict[str, Any] = {}
            for k, v in data.items():
                canonical = self._resolve_key(k)
                new_data[canonical] = self._normalize_json_keys(v)

            if "iocs" in new_data and isinstance(new_data["iocs"], list):
                ioc_list = new_data["iocs"]
                if ioc_list and any(isinstance(i, dict) for i in ioc_list):
                    flat: Dict[str, Any] = {}
                    for item in ioc_list:
                        if not isinstance(item, dict):
                            continue
                        for fk, fv in item.items():
                            rk = self._resolve_key(fk)
                            if rk in flat:
                                e = flat[rk] if isinstance(flat[rk], list) else [flat[rk]]
                                n = fv if isinstance(fv, list) else ([fv] if fv is not None else [])
                                flat[rk] = e + n
                            else:
                                flat[rk] = fv
                    iocs_part, meta_part = {}, {}
                    for fk, fv in flat.items():
                        if fk in _IOC_LIST_FIELDS:
                            iocs_part[fk] = fv
                        elif fk in _META_LIST_FIELDS:
                            meta_part[fk] = fv
                    new_data["iocs"] = iocs_part
                    if meta_part:
                        existing_tm = new_data.get("threat_metadata") or {}
                        if not isinstance(existing_tm, dict):
                            existing_tm = {}
                        for mk, mv in meta_part.items():
                            if mk in existing_tm:
                                e = existing_tm[mk] if isinstance(existing_tm[mk], list) else [existing_tm[mk]]
                                n = mv if isinstance(mv, list) else ([mv] if mv is not None else [])
                                existing_tm[mk] = e + n
                            else:
                                existing_tm[mk] = mv
                        new_data["threat_metadata"] = existing_tm
                else:
                    new_data["iocs"] = {}

            if "threat_metadata" in new_data and isinstance(new_data["threat_metadata"], list):
                tm_list = new_data["threat_metadata"]
                if tm_list and any(isinstance(i, dict) for i in tm_list):
                    merged_tm: Dict[str, Any] = {}
                    for item in tm_list:
                        if not isinstance(item, dict):
                            continue
                        for fk, fv in item.items():
                            rk = self._resolve_key(fk)
                            if rk in merged_tm:
                                e = merged_tm[rk] if isinstance(merged_tm[rk], list) else [merged_tm[rk]]
                                n = fv if isinstance(fv, list) else ([fv] if fv is not None else [])
                                merged_tm[rk] = e + n
                            else:
                                merged_tm[rk] = fv
                    new_data["threat_metadata"] = merged_tm
                else:
                    new_data["threat_metadata"] = {}

            top_ioc_keys  = [k for k in new_data if k in _IOC_LIST_FIELDS]
            top_meta_keys = [k for k in new_data if k in _META_LIST_FIELDS]
            if top_ioc_keys or top_meta_keys:
                iocs_obj = new_data.get("iocs")
                if not isinstance(iocs_obj, dict):
                    iocs_obj = {}
                tm_obj = new_data.get("threat_metadata")
                if not isinstance(tm_obj, dict):
                    tm_obj = {}
                for k in top_ioc_keys:
                    v = new_data.pop(k)
                    if k in iocs_obj:
                        e = iocs_obj[k] if isinstance(iocs_obj[k], list) else [iocs_obj[k]]
                        n = v if isinstance(v, list) else ([v] if v is not None else [])
                        iocs_obj[k] = e + n
                    else:
                        iocs_obj[k] = v
                for k in top_meta_keys:
                    v = new_data.pop(k)
                    if k in tm_obj:
                        e = tm_obj[k] if isinstance(tm_obj[k], list) else [tm_obj[k]]
                        n = v if isinstance(v, list) else ([v] if v is not None else [])
                        tm_obj[k] = e + n
                    else:
                        tm_obj[k] = v
                if top_ioc_keys:
                    new_data["iocs"] = iocs_obj
                if top_meta_keys:
                    new_data["threat_metadata"] = tm_obj
            return new_data

        elif isinstance(data, list):
            return [
                self._normalize_json_keys(item) if isinstance(item, dict) else item
                for item in data
            ]
        return data

    def _normalize_entity_lists(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return data
        normalized: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                normalized[key] = self._normalize_entity_lists(value)
            elif key == "summary":
                normalized[key] = str(value) if value is not None else ""
            elif key in ("severity", "tlp_tag"):
                normalized[key] = value
            elif key in _ALL_LIST_FIELDS:
                if value is None:
                    normalized[key] = []
                elif isinstance(value, list):
                    flat: List = []
                    for item in value:
                        if isinstance(item, list):
                            flat.extend(item)
                        elif item is not None:
                            flat.append(item)
                    normalized[key] = flat
                else:
                    normalized[key] = [value]
            else:
                normalized[key] = value
        return normalized

    def _clean_json_data(self, data: Any) -> Any:
        _NULL_STRINGS = frozenset({
            "null", "none", "n/a", "none provided",
            "not applicable", "unknown", "",
        })
        if isinstance(data, dict):
            return {k: self._clean_json_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            cleaned = [self._clean_json_data(item) for item in data]
            if all(item is None for item in cleaned):
                return []
            return cleaned
        elif isinstance(data, str):
            if data.strip().lower() in _NULL_STRINGS:
                return None
            return data
        return data

    def _validate_ioc_lists(self, iocs: Dict[str, List]) -> Dict[str, List]:
        validated: Dict[str, List] = {}
        for key, values in iocs.items():
            if not isinstance(values, list):
                validated[key] = []
                continue
            clean = []
            for v in values:
                v = str(v).strip()
                if not v:
                    continue
                if v.lower() in ("", "none", "null", "n/a", "unknown", "not applicable"):
                    continue
                if re.match(r'^CVE-\d{4}-XXXXX?$', v, re.IGNORECASE):
                    continue
                if re.match(r'^TXXXX$', v, re.IGNORECASE):
                    continue
                if v.lower() in {
                    "0.0.0.0", "127.0.0.1", "example.com", "example.org",
                    "example.net", "test.com", "sample.com", "dummy.com",
                    "localhost", "sample.exe",
                }:
                    continue

                norm_v = (
                    v.lower()
                     .replace("hxxp", "http")
                     .replace("hxxps", "https")
                     .replace("[.]", ".")
                     .replace("[:]", ":")
                )
                norm_v = re.sub(r'hxxp\s*:', 'http:', norm_v)
                norm_v = re.sub(r'hxxps\s*:', 'https:', norm_v)

                valid = True
                if key == "ip":
                    if not (IPV4_PATTERN.fullmatch(norm_v) or IPV6_PATTERN.fullmatch(norm_v)):
                        valid = False
                elif key == "url":
                    if not URL_PATTERN.fullmatch(norm_v):
                        valid = False
                elif key == "domain":
                    if not re.match(r'^[a-zA-Z0-9.-]+$', norm_v):
                        valid = False
                elif key == "cve":
                    if not CVE_PATTERN.fullmatch(norm_v):
                        valid = False
                elif key == "md5":
                    if not MD5_PATTERN.fullmatch(norm_v):
                        valid = False
                elif key == "sha1":
                    if not SHA1_PATTERN.fullmatch(norm_v):
                        valid = False
                elif key == "sha256":
                    if not SHA256_PATTERN.fullmatch(norm_v):
                        valid = False
                elif key == "email":
                    if not EMAIL_PATTERN.fullmatch(norm_v):
                        valid = False
                elif key == "file_name":
                    if not re.match(r'^[\w\-\.]+\.[a-zA-Z0-9]+$', norm_v):
                        valid = False
                elif key == "registry_key":
                    if not REGISTRY_PATTERN.fullmatch(norm_v):
                        valid = False
                elif key == "mutex":
                    if not MUTEX_PATTERN.fullmatch(norm_v):
                        valid = False

                if valid:
                    clean.append(v)
                else:
                    logger.debug("Removed invalid IOC %s: %s", key, v)
            validated[key] = clean
        return validated

    # ------------------------------------------------------------------ #
    # Parse orchestration
    # ------------------------------------------------------------------ #
    def _attempt_parse(self, raw_response: str) -> Optional[ProcessedArticle]:
        if not raw_response or not raw_response.strip():
            return None

        data = self._extract_json_from_text(raw_response)
        if data is None:
            logger.debug("JSON extraction failed for response: %.200s", raw_response)
            if self.debug:
                with open("logs/parse_failure_raw.txt", "w", encoding="utf-8") as f:
                    f.write(raw_response)
            return None

        data = self._clean_json_data(data)
        data = self._normalize_json_keys(data)
        data = self._normalize_entity_lists(data)

        if "summary" not in data or not isinstance(data["summary"], str):
            data["summary"] = ""
        if not isinstance(data.get("iocs"), dict):
            data["iocs"] = {}
        if not isinstance(data.get("threat_metadata"), dict):
            data["threat_metadata"] = {}

        if isinstance(data.get("iocs"), dict):
            data["iocs"] = self._validate_ioc_lists(data["iocs"])

        logger.info("=" * 80)
        logger.info("PARSED JSON")
        logger.info("=" * 80)
        logger.info(json.dumps(data, indent=2, default=str))
        logger.info("=" * 80)
        if self.debug:
            with open("logs/parsed_json.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)

        try:
            return ProcessedArticle(**data)
        except ValidationError as exc:
            logger.warning("Pydantic validation error (field-by-field retry): %s", exc)
            try:
                iocs = IOCCollection(**data.get("iocs", {}))
                metadata = ThreatMetadata(**data.get("threat_metadata", {}))
                return ProcessedArticle(
                    summary=str(data.get("summary", "")),
                    severity=data.get("severity", "Unknown"),
                    tlp_tag=data.get("tlp_tag", "TLP:CLEAR"),
                    iocs=iocs,
                    threat_metadata=metadata,
                )
            except Exception as exc2:
                logger.warning("Field-by-field construction also failed: %s", exc2)
                return None

    # ------------------------------------------------------------------ #
    # Regex fallback builder (manual tooling only)
    # ------------------------------------------------------------------ #
    def _create_llm_fallback_article(
        self, raw_response: str, cleaned_text: str, title: str,
    ) -> ProcessedArticle:
        full_text = cleaned_text + "\n" + (raw_response or "")
        regex_iocs = self._extract_iocs_regex(full_text)
        mitre = self._extract_mitre_techniques_regex(full_text)
        iocs = IOCCollection(**regex_iocs)
        metadata = ThreatMetadata(mitre_techniques=mitre)
        return ProcessedArticle(
            summary="",
            severity="Unknown",
            tlp_tag="TLP:CLEAR",
            iocs=iocs,
            threat_metadata=metadata,
        )

    # ------------------------------------------------------------------ #
    # Verification filtering
    # ------------------------------------------------------------------ #
    def _filter_verified_entities(
        self,
        provisional: ProcessedArticle,
        verification: VerificationResult,
    ) -> ProcessedArticle:
        new_iocs = {}
        iocs = provisional.iocs
        for field in IOCCollection.model_fields:
            values = getattr(iocs, field, [])
            verified = verification.ioc_verification.get(field, [])
            filtered = (
                [v for v, ok in zip(values, verified) if ok]
                if len(verified) == len(values)
                else values
            )
            new_iocs[field] = filtered
        filtered_iocs = IOCCollection(**new_iocs)

        soft_fields = {"attack_type", "target_industry"}
        meta = provisional.threat_metadata
        new_meta: Dict[str, Any] = {}

        meta_fields = [
            "threat_actor", "malware_name", "attack_type",
            "target_organization", "target_industry", "target_country",
            "campaign_name", "ransomware_family", "affected_software",
        ]
        for field in meta_fields:
            values = getattr(meta, field, [])
            if field in soft_fields:
                new_meta[field] = values
                continue
            verified = verification.metadata_verification.get(field, [])
            new_meta[field] = (
                [v for v, ok in zip(values, verified) if ok]
                if len(verified) == len(values)
                else values
            )

        mitre_values = meta.mitre_techniques
        mitre_valid = verification.mitre_valid
        new_meta["mitre_techniques"] = (
            [t for t, ok in zip(mitre_values, mitre_valid) if ok]
            if len(mitre_valid) == len(mitre_values)
            else mitre_values
        )

        filtered_meta = ThreatMetadata(**new_meta)

        return ProcessedArticle(
            summary=provisional.summary,
            severity=provisional.severity,
            tlp_tag=provisional.tlp_tag,
            cve_details=provisional.cve_details,   # preserved through filtering
            iocs=filtered_iocs,
            threat_metadata=filtered_meta,
        )

    # ------------------------------------------------------------------ #
    # Batch processing
    # ------------------------------------------------------------------ #
    async def _process_batch(self, articles: List[Dict[str, Any]]) -> int:
        if not articles:
            return 0

        messages_batch = [self._build_messages(art) for art in articles]
        success = 0

        if messages_batch and self.debug:
            first_prompt = messages_batch[0]
            logger.info("=" * 80)
            logger.info("FINAL PROMPT (first article)")
            logger.info("=" * 80)
            logger.info(json.dumps(first_prompt, indent=2, default=str))
            logger.info("=" * 80)
            with open("logs/final_prompt.txt", "w", encoding="utf-8") as f:
                json.dump(first_prompt, f, indent=2, default=str)

        # NOTE: no do_sample, no json_mode — LLMClient handles JSON internally.
        try:
            raw_responses = await self.client.generate(
                messages_batch,
                max_new_tokens=settings.LLM_MAX_NEW_TOKENS,
                temperature=settings.LLM_TEMPERATURE,
            )
        except Exception as exc:
            logger.exception(
                "LLM batch call failed on %d articles — marking all as FAILED. "
                "Reason: %s: %s",
                len(articles), type(exc).__name__, exc,
            )
            for art in articles:
                await self._mark_failed(
                    art["metadata_hash"],
                    f"LLM unavailable: {type(exc).__name__}: {exc}",
                )
            raise

        if len(raw_responses) != len(articles):
            logger.warning(
                "Response count mismatch: got %d for %d articles; "
                "falling back to sequential.",
                len(raw_responses), len(articles),
            )
            return await self._process_sequential(articles)

        for art, raw in zip(articles, raw_responses):
            logger.info("=" * 80)
            logger.info("RAW LLM RESPONSE")
            logger.info("=" * 80)
            logger.info(raw)
            logger.info("=" * 80)
            if self.debug:
                with open("logs/raw_response.txt", "w", encoding="utf-8") as f:
                    f.write(raw)

            parsed = self._attempt_parse(raw)
            if parsed:
                try:
                    await self._save_and_mark(art, parsed, raw)
                    success += 1
                    logger.info(
                        "✅ Processed: %s (%s)",
                        art["title"], art["metadata_hash"][:8],
                    )
                except Exception as exc:
                    logger.error(
                        "Save failed for %s: %s",
                        art["metadata_hash"][:8], exc,
                    )
                    await self._mark_failed(
                        art["metadata_hash"], f"Save error: {exc}",
                    )
            else:
                logger.error(
                    "LLM output not parseable for %s — marking FAILED. "
                    "Raw (first 300 chars): %.300s",
                    art["metadata_hash"][:8], raw or "<empty>",
                )
                await self._mark_failed(
                    art["metadata_hash"],
                    "LLM returned no parseable JSON output",
                )

        return success

    async def _process_sequential(self, articles: List[Dict[str, Any]]) -> int:
        success = 0
        for art in articles:
            raw: Optional[str] = None
            parsed: Optional[ProcessedArticle] = None
            messages = self._build_messages(art)

            if messages and self.debug:
                logger.info("=" * 80)
                logger.info("FINAL PROMPT (sequential)")
                logger.info("=" * 80)
                logger.info(json.dumps(messages, indent=2, default=str))
                logger.info("=" * 80)
                with open("logs/final_prompt_seq.txt", "w", encoding="utf-8") as f:
                    json.dump(messages, f, indent=2, default=str)

            try:
                responses = await self.client.generate(
                    messages,
                    max_new_tokens=settings.LLM_MAX_NEW_TOKENS,
                    temperature=settings.LLM_TEMPERATURE,
                )
                raw = responses[0] if responses else None

                if raw:
                    logger.info("=" * 80)
                    logger.info("RAW LLM RESPONSE (seq)")
                    logger.info("=" * 80)
                    logger.info(raw)
                    logger.info("=" * 80)
                    if self.debug:
                        with open("logs/raw_response_seq.txt", "w", encoding="utf-8") as f:
                            f.write(raw)
                    parsed = self._attempt_parse(raw)
            except Exception as exc:
                logger.error(
                    "LLM call (sequential) FAILED for %s [%s]: %s",
                    art["metadata_hash"][:8],
                    type(exc).__name__,
                    exc,
                )

            if parsed:
                try:
                    await self._save_and_mark(art, parsed, raw or "")
                    success += 1
                    logger.info(
                        "✅ Processed (seq): %s (%s)",
                        art["title"], art["metadata_hash"][:8],
                    )
                    continue
                except Exception as exc:
                    logger.error(
                        "Save failed for %s: %s",
                        art["metadata_hash"][:8], exc,
                    )
                    await self._mark_failed(
                        art["metadata_hash"], f"Save error: {exc}",
                    )
                    continue

            logger.error(
                "LLM produced no parseable output for %s — marking FAILED. "
                "Raw (first 300 chars): %.300s",
                art["metadata_hash"][:8], raw or "<empty>",
            )
            await self._mark_failed(
                art["metadata_hash"],
                "LLM returned no parseable JSON output",
            )

        return success

    async def _handle_parse_failure(
        self, art: Dict[str, Any], raw: Optional[str],
    ) -> None:
        """Kept for manual tooling only; not on the automatic path."""
        cleaned_text = art.get("cleaned_text", "")
        fallback = self._create_llm_fallback_article(
            raw or "", cleaned_text, art.get("title", "Untitled"),
        )
        try:
            await self._save_and_mark(art, fallback, raw or "REGEX_FALLBACK")
            logger.info(
                "Regex fallback saved: %s (%s)",
                art["title"], art["metadata_hash"][:8],
            )
        except Exception as exc:
            logger.error(
                "Regex fallback save failed for %s: %s",
                art["metadata_hash"][:8], exc,
            )
            await self._mark_failed(
                art["metadata_hash"], f"Fallback save error: {exc}",
            )

    # ------------------------------------------------------------------ #
    # Save pipeline
    # ------------------------------------------------------------------ #
    async def _save_and_mark(
        self,
        article: Dict[str, Any],
        parsed_article: ProcessedArticle,
        raw_response: str,
    ) -> None:
        cleaned_text = article.get("cleaned_text", "")

        # Merge LLM IOCs with regex safety net
        regex_iocs  = self._extract_iocs_regex(cleaned_text)
        llm_iocs    = parsed_article.iocs.model_dump()
        merged_dict = self._merge_iocs(llm_iocs, regex_iocs)
        merged_dict = self._validate_ioc_lists(merged_dict)
        merged_iocs = IOCCollection(**merged_dict)

        # Merge MITRE techniques
        regex_mitre = self._extract_mitre_techniques_regex(cleaned_text)
        merged_meta = parsed_article.threat_metadata.model_copy(deep=True)
        merged_meta.mitre_techniques = self._unique_preserve_order_ci(
            merged_meta.mitre_techniques + regex_mitre,
        )
        merged_meta.mitre_techniques = [
            t for t in merged_meta.mitre_techniques if MITRE_PATTERN.fullmatch(t)
        ]

        provisional = ProcessedArticle(
            summary=parsed_article.summary,
            severity=parsed_article.severity,
            tlp_tag=parsed_article.tlp_tag,
            iocs=merged_iocs,
            threat_metadata=merged_meta,
        )

        verification = verify_article(cleaned_text, provisional)
        final_article = self._filter_verified_entities(provisional, verification)

        # ---- Phase 3: CVE enrichment (best-effort, NEVER crashes) ----
        # We enrich the *verified* CVE list only — this avoids wasted NVD calls
        # on hallucinated CVEs that were already culled by verification.
        if final_article.iocs.cve:
            try:
                enriched = await fetch_cve_details(final_article.iocs.cve)
                if enriched:
                    final_article.cve_details = enriched
                    resolved = sum(1 for v in enriched.values() if v)
                    logger.info(
                        "CVE enrichment: %d/%d resolved for %s",
                        resolved, len(final_article.iocs.cve),
                        article["metadata_hash"][:8],
                    )
                else:
                    logger.info(
                        "CVE enrichment: no data returned for %s",
                        article["metadata_hash"][:8],
                    )
            except Exception as exc:
                # Enrichment failure must never block the article save.
                logger.warning(
                    "CVE enrichment failed (non-fatal) for %s: %s",
                    article["metadata_hash"][:8], exc,
                )

        logger.info("=" * 80)
        logger.info("FINAL ARTICLE")
        logger.info("=" * 80)
        logger.info(final_article.model_dump_json(indent=2))
        logger.info("=" * 80)
        if self.debug:
            with open("logs/final_article.json", "w", encoding="utf-8") as f:
                f.write(final_article.model_dump_json(indent=2))

        await self._save_processed(
            article["metadata_hash"],
            final_article,
            raw_response,
            verification.confidence_score,
            verification.verification_status,
            verification.hallucination_count,
            verification.evidence,
        )
        await self._mark_processed(article["metadata_hash"])

    async def _save_processed(
        self,
        metadata_hash: str,
        article: ProcessedArticle,
        raw_response: str,
        confidence_score: int,
        verification_status: str,
        hallucination_count: int,
        evidence: Dict[str, str],
    ) -> None:
        iocs_json        = article.iocs.model_dump_json()
        threat_json      = article.threat_metadata.model_dump_json()
        mitre_json       = json.dumps(article.threat_metadata.mitre_techniques)
        evidence_json    = json.dumps(evidence)
        target_org_json  = json.dumps(article.threat_metadata.target_organization)
        cve_details_json = json.dumps(article.cve_details or {})

        await self.db.insert_processed_article(
            metadata_hash,
            article.summary,
            iocs_json,
            threat_json,
            mitre_json,
            raw_response,
            confidence_score,
            verification_status,
            hallucination_count,
            evidence_json,
            target_org_json,
            severity=article.severity,
            tlp_tag=article.tlp_tag,
            cve_details_json=cve_details_json,
        )

    async def _mark_processed(self, metadata_hash: str) -> None:
        await self.db.update_article_status(metadata_hash, "PROCESSED", None)

    async def _mark_failed(self, metadata_hash: str, error: str) -> None:
        await self.db.update_article_status(metadata_hash, "FAILED", error)

    # ------------------------------------------------------------------ #
    # Runner
    # ------------------------------------------------------------------ #
    async def run(self, limit: Optional[int] = None) -> int:
        await self._ping_llm()

        start_time = time.time()
        articles = await self._fetch_pending(limit)
        if not articles:
            logger.info("No pending articles to process.")
            return 0

        logger.info("Fetched %d pending articles.", len(articles))
        total = len(articles)

        cleaned_articles: List[Dict[str, Any]] = []
        for art in articles:
            try:
                cleaned = self._clean_html(art.get("raw_html", ""))
                if not cleaned:
                    logger.warning("No content extracted for %s", art["metadata_hash"][:8])
                    await self._mark_failed(art["metadata_hash"], "Empty content after cleaning")
                    continue
                art["cleaned_text"] = cleaned
                cleaned_articles.append(art)
            except Exception as exc:
                logger.error("Cleaning failed for %s: %s", art["metadata_hash"][:8], exc)
                await self._mark_failed(art["metadata_hash"], f"Cleaning error: {exc}")

        if not cleaned_articles:
            logger.info("No articles with extractable content.")
            return 0

        success_count = 0
        for i in range(0, len(cleaned_articles), self.batch_size):
            batch = cleaned_articles[i: i + self.batch_size]
            batch_num = i // self.batch_size + 1
            logger.info(
                "Processing batch %d/%d (%d articles).",
                batch_num,
                -(-len(cleaned_articles) // self.batch_size),
                len(batch),
            )
            batch_success = await self._process_batch(batch)
            success_count += batch_success

        elapsed = time.time() - start_time
        logger.info(
            "Finished. Success: %d/%d in %.2fs (%.1f art/min).",
            success_count, total, elapsed,
            (total / elapsed * 60) if elapsed > 0 else 0,
        )
        return success_count

    async def _fetch_pending(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return await self.db.get_pending_articles(limit)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
async def main(limit: Optional[int] = None) -> None:
    from src.shared.database import DatabaseClient
    from src.core.config import settings

    client = LLMClient(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.GEMINI_MODEL_NAME,
        timeout=settings.REQUEST_TIMEOUT_SECONDS,
    )
    db = DatabaseClient(settings.DB_PATH)
    async with db:
        processor = ArticleProcessor(client, db, batch_size=settings.LLM_BATCH_SIZE)
        count = await processor.run(limit)
        print(f"✅ Processed {count} articles.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CTI Article Processor — Module 2")
    parser.add_argument("--limit", type=int, default=None, help="Max articles to process")
    args = parser.parse_args()
    asyncio.run(main(args.limit))