from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta


class Settings(BaseSettings):
    # ---------- Time window ----------
    START_DATE: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=3)
    )
    END_DATE: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=1)
    )

    # ---------- Networking / scraping ----------
    REQUEST_TIMEOUT_SECONDS: int = Field(320)
    MAX_RETRIES: int = Field(3)
    MAX_PAGES_PER_SOURCE: int = Field(5)
    MIN_BODY_LENGTH: int = Field(200)

    ADVISORY_DOMAINS: List[str] = [
        "msrc.microsoft.com",
        "nvd.nist.gov",
        "cve.mitre.org",
        "kb.cert.org",
        "us-cert.cisa.gov",
    ]
    MIN_BODY_LENGTH_ADVISORY: int = Field(50)

    PDF_PARSING_ENABLED: bool = Field(True)
    MAX_RESOLUTION_DEPTH: int = Field(2)

    DOMAIN_BLACKLIST: List[str] = [
        'linkedin.com', 'facebook.com', 'twitter.com', 'x.com',
        'instagram.com', 'youtube.com', 'discord.gg', 't.me'
    ]

    CTI_KEYWORDS: List[str] = [
        'vulnerability', 'exploit', 'malware', 'ransomware', 'threat', 'attack',
        'cve', 'backdoor', 'phishing', 'spyware', 'trojan', 'zero-day',
        'breach', 'data leak', 'security advisory', 'patch', 'fix',
        'cobalt strike', 'lockbit', 'clop', 'apt', 'infostealer',
        'credential', 'dropper', 'loader', 'ransom', 'extortion',
        'supply chain', 'compromise', 'intrusion', 'cyber espionage',
        'cybercrime', 'malicious', 'hacking', 'data theft',
        'account takeover', 'mfa bypass', 'evasion', 'persistence',
        'lateral movement', 'command and control', 'c2', 'ioc',
        'indicator of compromise'
    ]

    USER_AGENTS: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]

    SOURCES: List[Dict[str, Any]] = [
        {"name": "SecurityAffairs", "base_url": "https://securityaffairs.com/", "rss_url": "https://securityaffairs.com/feed", "use_playwright": False},
        {"name": "BleepingComputer", "base_url": "https://www.bleepingcomputer.com/", "rss_url": "https://www.bleepingcomputer.com/feed/", "use_playwright": False},
        {"name": "JPCERTCC", "base_url": "https://www.jpcert.or.jp/english/at/2024.html", "rss_url": None, "use_playwright": False},
        {"name": "IPA", "base_url": "https://www.ipa.go.jp/en/security/vuln/", "rss_url": None, "use_playwright": False},
        {"name": "CISA", "base_url": "https://www.cisa.gov/news-events/cybersecurity-advisories", "rss_url": "https://www.cisa.gov/cybersecurity-advisories/all.xml", "use_playwright": False},
        {"name": "TheHackerNews", "base_url": "https://thehackernews.com/", "rss_url": "https://feeds.feedburner.com/TheHackerNews", "use_playwright": False},
        {"name": "Symantec", "base_url": "https://symantec-enterprise-blogs.security.com/blogs/threat-intelligence", "rss_url": "https://symantec-enterprise-blogs.security.com/blogs/threat-intelligence/rss.xml", "use_playwright": False},
        {"name": "Trellix", "base_url": "https://www.trellix.com/blogs/", "rss_url": "https://www.trellix.com/blogs/feed/", "use_playwright": False},
        {"name": "BITSIGHT", "base_url": "https://www.bitsight.com/blog", "rss_url": None, "use_playwright": False},
        {"name": "Cloudflare", "base_url": "https://blog.cloudflare.com/tag/security/", "rss_url": "https://blog.cloudflare.com/rss/", "use_playwright": False},
        {"name": "BlackLotusLabs", "base_url": "https://blog.lumen.com/tag/black-lotus-labs/", "rss_url": "https://blog.lumen.com/feed/?tag=black-lotus-labs", "use_playwright": False},
        {"name": "Sekoia", "base_url": "https://blog.sekoia.io/", "rss_url": "https://blog.sekoia.io/feed/", "use_playwright": False},
        {"name": "GoogleTI", "base_url": "https://cloud.google.com/blog/topics/threat-intelligence", "rss_url": "https://cloud.google.com/feeds/blog/topics/threat-intelligence.xml", "use_playwright": False},
        {"name": "ANY.RUN", "base_url": "https://any.run/cybersecurity-blog/", "rss_url": None, "use_playwright": True},
    ]

    # ---------- Persistence ----------
    DATA_DIR: str = Field("./data", env="DATA_DIR")
    DB_PATH: str = Field("./data/ioc_pulse.db", env="DB_PATH")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    # ---------- LLM (Gemini) ----------
    GEMINI_API_KEY: str = Field("", env="GEMINI_API_KEY")
    GEMINI_MODEL_NAME: str = Field("gemini-2.5-flash", env="GEMINI_MODEL_NAME")
    LLM_BATCH_SIZE: int = Field(5, env="LLM_BATCH_SIZE")
    LLM_MAX_NEW_TOKENS: int = Field(2048, env="LLM_MAX_NEW_TOKENS")
    LLM_TEMPERATURE: float = Field(0.0, env="LLM_TEMPERATURE")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()