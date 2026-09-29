import asyncio
import logging
from typing import Optional, Tuple
from playwright.async_api import async_playwright
from src.core.exceptions import IngestionError, PlaywrightNotInstalledError
from src.module_1_ingestion.article_parser import extract_article_data
from src.module_1_ingestion.models import RawArticle
from src.core.config import settings

logger = logging.getLogger(__name__)

async def render_and_extract_article(
    url: str,
    source_name: str,
    rss_title: Optional[str] = None,
    rss_date: Optional[str] = None,
    rss_author: Optional[str] = None,
    rss_content: Optional[str] = None,
) -> Tuple[Optional[RawArticle], Optional[str]]:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = await browser.new_page(
                user_agent=settings.USER_AGENTS[0],
                viewport={"width": 1920, "height": 1080}
            )
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                html = await page.content()
            except Exception as e:
                raise IngestionError(f"Playwright navigation error: {e}") from e
            finally:
                await browser.close()

        raw_article, source_url = extract_article_data(
            html, url, source_name,
            rss_title=rss_title,
            rss_date=rss_date,
            rss_author=rss_author,
            rss_content=rss_content,
        )
        return raw_article, source_url

    except Exception as e:
        if "Executable doesn't exist" in str(e):
            raise PlaywrightNotInstalledError("Run: playwright install")
        logger.error(f"Playwright extraction failed for {url}: {e}")
        raise


async def fetch_index_with_playwright(url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=settings.USER_AGENTS[0])
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        html = await page.content()
        await browser.close()
        return html