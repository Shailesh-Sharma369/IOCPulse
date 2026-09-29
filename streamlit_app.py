import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import threading
import time
import queue
import json
import copy
import pandas as pd
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO

import streamlit as st

# Existing backend imports (unchanged)
from src.shared.database import DatabaseClient
from src.core.config import settings
from src.module_1_ingestion.source_manager import SourceManager
from src.module_2_llm_processing.processor import ArticleProcessor
from src.module_2_llm_processing.llm_client import LLMClient

# =============================================================================
# PAGE CONFIG & STYLING (same as before)
# =============================================================================
st.set_page_config(
    page_title="CTI Pipeline Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* ... same CSS as previous ... */
    /* (I will include the full CSS again to be safe) */
    .stApp {
        background: #0b0e14;
        color: #e8edf5;
    }
    section[data-testid="stSidebar"] {
        background: rgba(20, 28, 40, 0.85);
        backdrop-filter: blur(12px);
        border-right: 1px solid rgba(255,255,255,0.06);
    }
    section[data-testid="stSidebar"] .stRadio label {
        font-weight: 500;
        color: #c8d0dc;
    }
    section[data-testid="stSidebar"] .stRadio label:hover {
        color: #a29bfe;
    }
    .card {
        background: rgba(255,255,255,0.04);
        backdrop-filter: blur(8px);
        border-radius: 16px;
        padding: 1.2rem 1.5rem;
        border: 1px solid rgba(255,255,255,0.06);
        box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: rgba(255,255,255,0.05);
        backdrop-filter: blur(6px);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        border: 1px solid rgba(255,255,255,0.04);
        text-align: center;
        transition: 0.2s;
    }
    .metric-card:hover {
        background: rgba(255,255,255,0.08);
        border-color: rgba(162,155,254,0.3);
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #a29bfe;
        line-height: 1.2;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #8f9bb3;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 0.2rem;
    }
    .badge {
        display: inline-block;
        padding: 0.2rem 0.7rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.3px;
        text-transform: uppercase;
    }
    .badge-success { background: #00b894; color: #fff; }
    .badge-pending { background: #fdcb6e; color: #2d3436; }
    .badge-failed  { background: #e17055; color: #fff; }
    .badge-processing { background: #6c5ce7; color: #fff; }
    .badge-mitre {
        background: #2d3436;
        color: #dfe6e9;
        border: 1px solid #636e72;
        border-radius: 4px;
        padding: 0.1rem 0.5rem;
        font-size: 0.7rem;
        margin: 0.1rem;
    }
    .badge-mitre:hover {
        background: #6c5ce7;
        border-color: #6c5ce7;
    }
    .stage-container {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        margin: 1rem 0;
    }
    .stage-row {
        display: flex;
        align-items: center;
        gap: 0.8rem;
        padding: 0.3rem 0.6rem;
        border-radius: 8px;
        transition: background 0.3s;
    }
    .stage-row.active {
        background: rgba(108,92,231,0.2);
        border-left: 3px solid #6c5ce7;
    }
    .stage-row.done {
        opacity: 0.6;
    }
    .stage-icon {
        font-size: 1.2rem;
        width: 2rem;
        text-align: center;
    }
    .stage-label {
        font-size: 0.9rem;
        color: #c8d0dc;
    }
    .stage-label.active {
        color: #a29bfe;
        font-weight: 600;
    }
    .stage-label.done {
        color: #8f9bb3;
    }
    .ai-pulse {
        display: inline-block;
        width: 12px;
        height: 12px;
        background: #a29bfe;
        border-radius: 50%;
        animation: pulse 1.2s ease-in-out infinite;
        margin-right: 10px;
    }
    @keyframes pulse {
        0% { opacity: 0.3; transform: scale(0.9); }
        50% { opacity: 1; transform: scale(1.2); }
        100% { opacity: 0.3; transform: scale(0.9); }
    }
    .status-text {
        font-size: 0.9rem;
        color: #b0b9c9;
    }
    .stDataFrame {
        background: rgba(255,255,255,0.02);
        border-radius: 12px;
        padding: 0.5rem;
    }
    .stDataFrame table {
        font-size: 0.9rem;
    }
    .stDataFrame th {
        color: #a29bfe;
        font-weight: 600;
    }
    .streamlit-expanderHeader {
        background: rgba(255,255,255,0.04);
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.05);
    }
    .streamlit-expanderHeader:hover {
        background: rgba(255,255,255,0.08);
    }
    .stButton button {
        background: linear-gradient(135deg, #6c5ce7, #a29bfe);
        border: none;
        border-radius: 30px;
        color: white;
        font-weight: 600;
        padding: 0.4rem 1.2rem;
        transition: 0.2s;
    }
    .stButton button:hover {
        background: linear-gradient(135deg, #5a4bd1, #8b83e6);
        box-shadow: 0 4px 14px rgba(108,92,231,0.4);
    }
    .stButton button:disabled {
        opacity: 0.5;
    }
    .stButton button.secondary {
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.15);
    }
    .stButton button.secondary:hover {
        background: rgba(255,255,255,0.15);
    }
    input, select, textarea {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #e8edf5 !important;
        border-radius: 8px !important;
    }
    .footer {
        position: fixed;
        bottom: 1rem;
        left: 1rem;
        font-size: 0.7rem;
        color: #636e72;
    }
    .ingestion-overlay {
        background: rgba(0,0,0,0.6);
        backdrop-filter: blur(4px);
        padding: 2rem;
        border-radius: 20px;
        margin: 1rem 0;
        border: 1px solid rgba(255,255,255,0.05);
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# SESSION STATE INIT
# =============================================================================
if 'ingestion_running' not in st.session_state:
    st.session_state.ingestion_running = False
if 'processing_running' not in st.session_state:
    st.session_state.processing_running = False
if 'page' not in st.session_state:
    st.session_state.page = "Dashboard"
if 'article_page' not in st.session_state:
    st.session_state.article_page = 1
if 'processed_page' not in st.session_state:
    st.session_state.processed_page = 1
if 'ingestion_progress_queue' not in st.session_state:
    st.session_state.ingestion_progress_queue = None
if 'processing_progress_queue' not in st.session_state:
    st.session_state.processing_progress_queue = None
if 'show_ingestion' not in st.session_state:
    st.session_state.show_ingestion = False
if 'selected_sources' not in st.session_state:
    st.session_state.selected_sources = []
if 'ingestion_date_from' not in st.session_state:
    st.session_state.ingestion_date_from = datetime.now() - timedelta(days=7)
if 'ingestion_date_to' not in st.session_state:
    st.session_state.ingestion_date_to = datetime.now()

# =============================================================================
# PROGRESS-AWARE BACKGROUND TASKS (Robust version)
# =============================================================================
# We'll use a lock to protect the settings global during modification.
_settings_lock = threading.Lock()

def run_ingestion_with_progress(progress_queue, selected_source_configs, start_date, end_date):
    """
    Runs ingestion only for selected sources, with custom date range.
    This function is executed in a separate thread.
    """
    try:
        # Import here to avoid circular imports
        import asyncio
        from src.module_1_ingestion.source_manager import SourceManager
        from src.core.config import settings
        import copy

        # Make a deep copy of the selected sources to avoid reference issues
        sources_to_use = copy.deepcopy(selected_source_configs)

        # Store original settings
        original_sources = settings.SOURCES
        original_start = settings.START_DATE
        original_end = settings.END_DATE

        try:
            # Acquire lock to modify settings
            with _settings_lock:
                # Override with user-selected values
                settings.SOURCES = sources_to_use
                settings.START_DATE = start_date
                settings.END_DATE = end_date

                # Instantiate SourceManager
                manager = SourceManager()

            # Run ingestion asynchronously using asyncio.run() in the thread
            # This creates a new event loop isolated from the main thread.
            async def ingest():
                progress_queue.put(("status", "Connecting to sources..."))
                count = await manager.ingest_and_persist()
                return count

            count = asyncio.run(ingest())
            progress_queue.put(("status", f"✅ Ingestion completed. {count} articles added."))

        finally:
            # Restore original settings (still protected by lock)
            with _settings_lock:
                settings.SOURCES = original_sources
                settings.START_DATE = original_start
                settings.END_DATE = original_end

        progress_queue.put(("done", None))

    except Exception as e:
        import traceback
        error_msg = f"❌ Fatal error: {e}\n{traceback.format_exc()}"
        progress_queue.put(("status", error_msg))
        progress_queue.put(("done", None))

def run_processing_with_progress(progress_queue, limit=50):
    """Runs processing in a thread with progress updates."""
    try:
        import asyncio
        from src.shared.database import DatabaseClient
        from src.core.config import settings
        from src.module_2_llm_processing.processor import ArticleProcessor
        from src.module_2_llm_processing.llm_client import LLMClient

        async def run_with_polling():
            client = LLMClient(settings.LLM_SERVER_URL, timeout=settings.REQUEST_TIMEOUT_SECONDS)
            async with DatabaseClient() as db:
                pending = await db.get_pending_articles(limit=None)
                total_pending = len(pending) if limit is None else min(len(pending), limit)
                progress_queue.put(("total", total_pending))
                processor = ArticleProcessor(client, db, batch_size=settings.LLM_BATCH_SIZE)
                original_save = processor._save_and_mark
                processed_count = 0
                async def save_with_progress(article, parsed_article, raw_response):
                    nonlocal processed_count
                    await original_save(article, parsed_article, raw_response)
                    processed_count += 1
                    progress_queue.put(("progress", processed_count))
                    title = article.get('title', 'Untitled')
                    progress_queue.put(("status", f"Processed {processed_count}/{total_pending}: {title[:50]}..."))
                processor._save_and_mark = save_with_progress
                progress_queue.put(("status", "Reading Articles..."))
                count = await processor.run(limit=limit)
                progress_queue.put(("status", "✅ Processing completed."))
                progress_queue.put(("done", None))

        asyncio.run(run_with_polling())
    except Exception as e:
        import traceback
        error_msg = f"❌ Fatal error: {e}\n{traceback.format_exc()}"
        progress_queue.put(("status", error_msg))
        progress_queue.put(("done", None))

def start_ingestion_with_progress(source_configs, start_date, end_date):
    q = queue.Queue()
    st.session_state.ingestion_progress_queue = q
    st.session_state.ingestion_running = True
    def target():
        run_ingestion_with_progress(q, source_configs, start_date, end_date)
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return q

def start_processing_with_progress(limit=50):
    q = queue.Queue()
    st.session_state.processing_progress_queue = q
    st.session_state.processing_running = True
    def target():
        run_processing_with_progress(q, limit)
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return q

# =============================================================================
# STAGE DISPLAY FOR PROGRESS (same as before)
# =============================================================================
def show_pipeline_stages(stage_list, current_stage_idx):
    html = '<div class="stage-container">'
    icons = ["🔗", "📥", "📄", "⏳", "💾", "✅"]
    for idx, stage in enumerate(stage_list):
        if idx < current_stage_idx:
            cls = "done"
            icon = "✅"
        elif idx == current_stage_idx:
            cls = "active"
            icon = icons[idx % len(icons)]
        else:
            cls = ""
            icon = "⏳"
        html += f'''
        <div class="stage-row {cls}">
            <span class="stage-icon">{icon}</span>
            <span class="stage-label {cls}">{stage}</span>
        </div>
        '''
    html += '</div>'
    return html

def show_progress_display(progress_queue, task_name="Operation"):
    if progress_queue is None:
        return False
    total = st.session_state.get(f"{task_name}_total", None)
    progress = st.session_state.get(f"{task_name}_progress", 0)
    status_msgs = st.session_state.get(f"{task_name}_status", [])
    new_status = None
    while not progress_queue.empty():
        try:
            item = progress_queue.get_nowait()
            if item[0] == "total":
                total = item[1]
                st.session_state[f"{task_name}_total"] = total
            elif item[0] == "progress":
                progress = item[1]
                st.session_state[f"{task_name}_progress"] = progress
            elif item[0] == "status":
                new_status = item[1]
                if new_status:
                    status_msgs.append(new_status)
                    st.session_state[f"{task_name}_status"] = status_msgs
            elif item[0] == "done":
                st.session_state[f"{task_name}_running"] = False
                return False
        except queue.Empty:
            break

    if "Ingestion" in task_name or "Scraping" in task_name:
        stages = [
            "Connecting to sources",
            "Downloading articles",
            "Extracting content",
            "Filtering by selected dates",
            "Saving into database",
            "Ingestion completed",
        ]
    else:
        stages = [
            "Reading Articles",
            "Calling LLM",
            "Extracting Entities",
            "Extracting IOCs",
            "MITRE Mapping",
            "Saving Results",
            "Processing completed",
        ]

    current_stage_idx = 0
    if status_msgs:
        last_status = status_msgs[-1]
        for idx, stage in enumerate(stages):
            if stage.lower() in last_status.lower():
                current_stage_idx = idx
                break

    st.markdown(show_pipeline_stages(stages, current_stage_idx), unsafe_allow_html=True)

    if total is not None:
        percent = min(progress / total * 100, 100) if total > 0 else 0
        st.progress(percent / 100, text=f"Progress: {percent:.0f}% ({progress}/{total})")
    else:
        st.markdown(f'<div class="ai-pulse"></div><span class="status-text">{task_name} in progress...</span>', unsafe_allow_html=True)

    if status_msgs:
        for msg in status_msgs[-3:]:
            st.markdown(f"<div style='color:#b0b9c9; font-size:0.85rem;'>• {msg}</div>", unsafe_allow_html=True)

    return True

# =============================================================================
# DATABASE HELPERS (UI only) - unchanged
# =============================================================================
async def get_kpi_counts():
    async with DatabaseClient() as db:
        cur = await db._conn.execute("SELECT COUNT(*) FROM staging_raw")
        total = (await cur.fetchone())[0]
        cur = await db._conn.execute("SELECT COUNT(*) FROM staging_raw WHERE status='PENDING'")
        pending = (await cur.fetchone())[0]
        cur = await db._conn.execute("SELECT COUNT(*) FROM processed_articles")
        processed = (await cur.fetchone())[0]
        cur = await db._conn.execute("SELECT COUNT(*) FROM staging_raw WHERE status='FAILED'")
        failed = (await cur.fetchone())[0]
        cur = await db._conn.execute("SELECT COUNT(DISTINCT source_domain) FROM staging_raw")
        sources = (await cur.fetchone())[0]
        return {"total": total, "pending": pending, "processed": processed, "failed": failed, "sources": sources}

async def get_recent_articles(limit=5):
    async with DatabaseClient() as db:
        cur = await db._conn.execute("""
            SELECT id, source_domain, title, author, published_utc, status
            FROM staging_raw
            ORDER BY published_utc DESC LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
        return [dict(row) for row in rows]

async def fetch_articles_with_filters(
    source=None, status=None, date_from=None, date_to=None, search=None,
    page=1, per_page=20
):
    async with DatabaseClient() as db:
        where_clauses = []
        params = []
        if source:
            where_clauses.append("source_domain = ?")
            params.append(source)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if date_from:
            where_clauses.append("published_utc >= ?")
            params.append(date_from.isoformat())
        if date_to:
            where_clauses.append("published_utc <= ?")
            params.append(date_to.isoformat())
        if search:
            where_clauses.append("(title LIKE ? OR author LIKE ?)")
            params.append(f"%{search}%")
            params.append(f"%{search}%")
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        offset = (page - 1) * per_page
        query = f"""
            SELECT id, source_domain, title, author, published_utc, source_url,
                   original_source_url, source_status, status
            FROM staging_raw
            WHERE {where_sql}
            ORDER BY published_utc DESC
            LIMIT ? OFFSET ?
        """
        params.extend([per_page, offset])
        cur = await db._conn.execute(query, params)
        rows = await cur.fetchall()
        articles = [dict(row) for row in rows]
        count_query = f"SELECT COUNT(*) FROM staging_raw WHERE {where_sql}"
        cur_count = await db._conn.execute(count_query, params[:-2])
        total = (await cur_count.fetchone())[0]
        return articles, total

async def fetch_processed_with_filters(
    source=None, date_from=None, date_to=None, search=None,
    page=1, per_page=20
):
    async with DatabaseClient() as db:
        where_clauses = []
        params = []
        if source:
            where_clauses.append("s.source_domain = ?")
            params.append(source)
        if date_from:
            where_clauses.append("s.published_utc >= ?")
            params.append(date_from.isoformat())
        if date_to:
            where_clauses.append("s.published_utc <= ?")
            params.append(date_to.isoformat())
        if search:
            where_clauses.append("(s.title LIKE ? OR p.summary LIKE ?)")
            params.append(f"%{search}%")
            params.append(f"%{search}%")
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        offset = (page - 1) * per_page
        query = f"""
            SELECT s.id, s.source_domain, s.title, s.author, s.published_utc,
                   s.source_url, p.summary, p.iocs_json, p.threat_metadata_json,
                   p.mitre_techniques_json, p.confidence_score, p.verification_status,
                   p.processing_status, p.processing_timestamp
            FROM staging_raw s
            JOIN processed_articles p ON s.metadata_hash = p.metadata_hash
            WHERE {where_sql}
            ORDER BY p.processing_timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([per_page, offset])
        cur = await db._conn.execute(query, params)
        rows = await cur.fetchall()
        articles = [dict(row) for row in rows]
        count_query = f"""
            SELECT COUNT(*)
            FROM staging_raw s
            JOIN processed_articles p ON s.metadata_hash = p.metadata_hash
            WHERE {where_sql}
        """
        cur_count = await db._conn.execute(count_query, params[:-2])
        total = (await cur_count.fetchone())[0]
        return articles, total

async def get_distinct_sources():
    async with DatabaseClient() as db:
        cur = await db._conn.execute("SELECT DISTINCT source_domain FROM staging_raw ORDER BY source_domain")
        rows = await cur.fetchall()
        return [row[0] for row in rows]

async def fetch_article_full(article_id):
    async with DatabaseClient() as db:
        query = """
            SELECT s.id, s.source_domain, s.title, s.author, s.published_utc,
                   s.source_url, s.original_source_url, s.source_status, s.status,
                   p.summary, p.iocs_json, p.threat_metadata_json,
                   p.mitre_techniques_json, p.confidence_score, p.verification_status,
                   p.processing_status, p.processing_timestamp,
                   p.llm_raw_response, p.evidence_json, p.target_organization
            FROM staging_raw s
            JOIN processed_articles p ON s.metadata_hash = p.metadata_hash
            WHERE s.id = ?
        """
        cur = await db._conn.execute(query, (article_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

# =============================================================================
# EXPORT FUNCTIONS (unchanged)
# =============================================================================
async def fetch_all_processed_for_export():
    async with DatabaseClient() as db:
        query = """
            SELECT s.id, s.source_domain, s.title, s.author, s.published_utc,
                   s.source_url, s.original_source_url, s.source_status,
                   p.summary, p.iocs_json, p.threat_metadata_json,
                   p.mitre_techniques_json, p.confidence_score, p.verification_status,
                   p.processing_status, p.processing_timestamp,
                   p.llm_raw_response, p.evidence_json, p.target_organization
            FROM staging_raw s
            JOIN processed_articles p ON s.metadata_hash = p.metadata_hash
            ORDER BY p.processing_timestamp DESC
        """
        cur = await db._conn.execute(query)
        rows = await cur.fetchall()
        return [dict(row) for row in rows]

def generate_csv(data):
    df = pd.DataFrame(data)
    for col in ['iocs_json', 'threat_metadata_json', 'mitre_techniques_json', 'evidence_json', 'target_organization']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: json.dumps(json.loads(x) if x else {}) if x else '')
    return df.to_csv(index=False).encode('utf-8')

def generate_json(data):
    return json.dumps(data, indent=2, default=str).encode('utf-8')

def generate_stix(data):
    try:
        from stix2 import Bundle, Indicator, ThreatActor, Malware, Relationship, Identity
        from stix2 import DomainName, URL, IPv4Address, IPv6Address, File, EmailAddress, Vulnerability
        import uuid
        from datetime import datetime, timezone
    except ImportError:
        return json.dumps({"error": "stix2 library not installed. Install with 'pip install stix2'."}).encode('utf-8')
    now = datetime.now(timezone.utc)
    objects = []
    created_by = Identity(
        id="identity--" + str(uuid.uuid4()),
        name="CTI Pipeline",
        identity_class="organization"
    )
    objects.append(created_by)
    for record in data:
        try:
            iocs = json.loads(record.get('iocs_json', '{}')) if record.get('iocs_json') else {}
        except:
            iocs = {}
        for ioc_type, values in iocs.items():
            for val in values:
                if not val:
                    continue
                if ioc_type in ['md5', 'sha1', 'sha256']:
                    hashes = {ioc_type.upper(): val}
                    ind = Indicator(
                        id="indicator--" + str(uuid.uuid4()),
                        name=f"File hash {ioc_type.upper()}",
                        pattern=f"[file:hashes.'{ioc_type.upper()}' = '{val}']",
                        pattern_type="stix",
                        valid_from=now,
                        created_by_ref=created_by.id,
                        object_refs=[File(hashes=hashes).id]
                    )
                elif ioc_type == 'cve':
                    ind = Indicator(
                        id="indicator--" + str(uuid.uuid4()),
                        name=f"CVE {val}",
                        pattern=f"[vulnerability:cve_id = '{val}']",
                        pattern_type="stix",
                        valid_from=now,
                        created_by_ref=created_by.id,
                        object_refs=[Vulnerability(name=val, cve_id=val).id]
                    )
                else:
                    if ioc_type == 'ip':
                        pattern = f"[ipv4-addr:value = '{val}']" if '.' in val else f"[ipv6-addr:value = '{val}']"
                    elif ioc_type == 'domain':
                        pattern = f"[domain-name:value = '{val}']"
                    elif ioc_type == 'url':
                        pattern = f"[url:value = '{val}']"
                    elif ioc_type == 'email':
                        pattern = f"[email-addr:value = '{val}']"
                    else:
                        continue
                    ind = Indicator(
                        id="indicator--" + str(uuid.uuid4()),
                        name=f"{ioc_type} {val}",
                        pattern=pattern,
                        pattern_type="stix",
                        valid_from=now,
                        created_by_ref=created_by.id,
                    )
                objects.append(ind)
        try:
            meta = json.loads(record.get('threat_metadata_json', '{}')) if record.get('threat_metadata_json') else {}
        except:
            meta = {}
        for ta in meta.get('threat_actor', []):
            if ta:
                actor = ThreatActor(
                    id="threat-actor--" + str(uuid.uuid4()),
                    name=ta,
                    created_by_ref=created_by.id,
                )
                objects.append(actor)
        for malware in meta.get('malware_name', []):
            if malware:
                mal = Malware(
                    id="malware--" + str(uuid.uuid4()),
                    name=malware,
                    is_family=False,
                    created_by_ref=created_by.id,
                )
                objects.append(mal)
    bundle = Bundle(objects, created_by_ref=created_by.id)
    return bundle.serialize(pretty=True).encode('utf-8')

# =============================================================================
# UI PAGES (Dashboard, Ingestion, Articles, Processed)
# =============================================================================
def page_dashboard():
    if st.session_state.show_ingestion:
        page_ingestion()
        return

    st.markdown("<h1 style='color:#a29bfe;'>🛡️ Threat Intelligence Dashboard</h1>", unsafe_allow_html=True)
    st.markdown("Overview of the CTI pipeline status and recent activity.")

    with st.spinner("Loading metrics..."):
        counts = asyncio.run(get_kpi_counts())
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{counts['total']}</div>
            <div class="metric-label">Total Articles</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color:#fdcb6e;">{counts['pending']}</div>
            <div class="metric-label">Pending</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color:#00b894;">{counts['processed']}</div>
            <div class="metric-label">Processed</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color:#e17055;">{counts['failed']}</div>
            <div class="metric-label">Failed</div>
        </div>
        """, unsafe_allow_html=True)
    with col5:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color:#74b9ff;">{counts['sources']}</div>
            <div class="metric-label">Sources</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    col1, col2, col3 = st.columns([1,1,2])
    with col1:
        if st.button("📥 Run Ingestion", disabled=st.session_state.ingestion_running, use_container_width=True):
            st.session_state.show_ingestion = True
            st.rerun()
    with col2:
        if st.button("🧠 Run Processing", disabled=st.session_state.processing_running, use_container_width=True):
            q = start_processing_with_progress()
            st.success("Processing started in background.")
    with col3:
        status_text = ""
        if st.session_state.ingestion_running:
            status_text = "⏳ Ingestion running..."
        elif st.session_state.processing_running:
            status_text = "⏳ Processing running..."
        else:
            status_text = "✅ Idle"
        st.markdown(f"<div style='text-align:right; padding-top:0.5rem; color:#8f9bb3;'>{status_text}</div>", unsafe_allow_html=True)

    if st.session_state.ingestion_running and st.session_state.ingestion_progress_queue:
        st.markdown("---")
        st.markdown("### Ingestion Progress")
        if not show_progress_display(st.session_state.ingestion_progress_queue, "Ingestion"):
            st.session_state.ingestion_running = False
            st.rerun()
    if st.session_state.processing_running and st.session_state.processing_progress_queue:
        st.markdown("---")
        st.markdown("### Processing Progress")
        if not show_progress_display(st.session_state.processing_progress_queue, "Processing"):
            st.session_state.processing_running = False
            st.rerun()

    st.subheader("📰 Recent Articles")
    with st.spinner("Loading recent articles..."):
        recent = asyncio.run(get_recent_articles(5))
    if recent:
        df = pd.DataFrame(recent)
        df['published_utc'] = pd.to_datetime(df['published_utc'], format='ISO8601', utc=True, errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
        df = df[['id', 'source_domain', 'title', 'author', 'published_utc', 'status']]
        def status_badge(s):
            cls = "badge-pending" if s=="PENDING" else "badge-success" if s=="PROCESSED" else "badge-failed"
            return f'<span class="badge {cls}">{s}</span>'
        df['status'] = df['status'].apply(status_badge)
        st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.info("No articles found. Run ingestion first.")

def page_ingestion():
    st.markdown("<div class='ingestion-overlay'>", unsafe_allow_html=True)

    if st.button("← Back to Dashboard", key="back_dash", use_container_width=True):
        st.session_state.show_ingestion = False
        st.rerun()

    st.markdown("<h1 style='color:#a29bfe;'>📥 Configure Ingestion</h1>", unsafe_allow_html=True)
    st.markdown("Select sources, set date range, and start scraping.")

    # --- Source selection ---
    st.subheader("Sources")
    builtin_sources = settings.SOURCES
    async def get_user_sources():
        async with DatabaseClient() as db:
            await db._conn.execute("""
                CREATE TABLE IF NOT EXISTS user_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    base_url TEXT NOT NULL,
                    rss_url TEXT,
                    use_playwright INTEGER DEFAULT 0
                )
            """)
            await db._conn.commit()
            cur = await db._conn.execute("SELECT * FROM user_sources ORDER BY name")
            rows = await cur.fetchall()
            return [dict(row) for row in rows]
    user_sources = asyncio.run(get_user_sources())

    all_sources = []
    for src in builtin_sources:
        all_sources.append({
            "name": src.get("name", "Unnamed"),
            "base_url": src.get("base_url"),
            "rss_url": src.get("rss_url"),
            "use_playwright": src.get("use_playwright", False),
            "is_user": False
        })
    for us in user_sources:
        all_sources.append({
            "name": us["name"],
            "base_url": us["base_url"],
            "rss_url": us.get("rss_url"),
            "use_playwright": bool(us.get("use_playwright", 0)),
            "is_user": True,
            "id": us["id"]
        })

    selected_indices = st.multiselect(
        "Select sources to scrape",
        options=range(len(all_sources)),
        format_func=lambda i: f"{'⭐ ' if all_sources[i]['is_user'] else ''}{all_sources[i]['name']} ({all_sources[i]['base_url']})",
        default=list(range(len(all_sources)))
    )
    selected_sources = [all_sources[i] for i in selected_indices]

    with st.expander("➕ Add New Source", expanded=False):
        with st.form("add_source_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Source name", placeholder="e.g. MyBlog")
                base_url = st.text_input("Base URL", placeholder="https://example.com/blog")
            with col2:
                rss_url = st.text_input("RSS feed URL (optional)", placeholder="https://example.com/feed")
                use_playwright = st.checkbox("Use Playwright (for JavaScript heavy sites)")
            submitted = st.form_submit_button("➕ Add Source")
            if submitted:
                if name and base_url:
                    async def add():
                        async with DatabaseClient() as db:
                            await db._conn.execute(
                                "INSERT OR REPLACE INTO user_sources (name, base_url, rss_url, use_playwright) VALUES (?, ?, ?, ?)",
                                (name, base_url, rss_url or None, 1 if use_playwright else 0)
                            )
                            await db._conn.commit()
                    asyncio.run(add())
                    st.success(f"Added {name}")
                    st.rerun()
                else:
                    st.error("Name and Base URL are required.")

    st.subheader("Date Range")
    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input("From", value=datetime.now() - timedelta(days=7), key="ingest_from")
    with col2:
        date_to = st.date_input("To", value=datetime.now(), key="ingest_to")

    with st.expander("⚙️ Advanced Settings (optional)"):
        max_pages = st.number_input("Max pages per source", min_value=1, value=settings.MAX_PAGES_PER_SOURCE)

    if st.button("🚀 Start Scraping", disabled=st.session_state.ingestion_running or len(selected_sources)==0, use_container_width=True):
        start_dt = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(date_to, datetime.max.time()).replace(tzinfo=timezone.utc)
        source_configs = []
        for src in selected_sources:
            config = {
                "name": src["name"],
                "base_url": src["base_url"],
                "rss_url": src.get("rss_url"),
                "use_playwright": src.get("use_playwright", False)
            }
            source_configs.append(config)
        q = start_ingestion_with_progress(source_configs, start_dt, end_dt)
        st.success("Ingestion started. You can close this form and monitor progress on the Dashboard.")
        # Optionally close form after start? We'll keep it open to show progress.

    if st.session_state.ingestion_running and st.session_state.ingestion_progress_queue:
        st.markdown("---")
        st.markdown("### Ingestion Progress")
        if not show_progress_display(st.session_state.ingestion_progress_queue, "Ingestion"):
            st.session_state.ingestion_running = False
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

def page_articles():
    st.markdown("<h1 style='color:#a29bfe;'>📰 Ingested Articles</h1>", unsafe_allow_html=True)

    with st.expander("🔍 Filters", expanded=False):
        col1, col2, col3 = st.columns(3)
        sources = asyncio.run(get_distinct_sources())
        with col1:
            source_filter = st.selectbox("Source", options=["All"] + sources)
        with col2:
            status_filter = st.selectbox("Status", options=["All", "PENDING", "PROCESSED", "FAILED"])
        with col3:
            search_filter = st.text_input("Search (title/author)", placeholder="Keyword...")
        col1, col2 = st.columns(2)
        with col1:
            date_from = st.date_input("From", value=None)
        with col2:
            date_to = st.date_input("To", value=None)

    per_page = 20
    page = st.session_state.article_page
    filters = {
        "source": source_filter if source_filter != "All" else None,
        "status": status_filter if status_filter != "All" else None,
        "date_from": date_from if date_from else None,
        "date_to": date_to if date_to else None,
        "search": search_filter if search_filter.strip() else None,
    }
    with st.spinner("Loading articles..."):
        articles, total = asyncio.run(fetch_articles_with_filters(
            source=filters["source"],
            status=filters["status"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            search=filters["search"],
            page=page,
            per_page=per_page
        ))
    if not articles:
        st.info("No articles found matching the filters.")
        return

    for art in articles:
        with st.expander(f"📄 {art['title']} (ID: {art['id']})"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Source:** {art['source_domain']}")
                st.markdown(f"**Author:** {art['author'] or 'Unknown'}")
                try:
                    pub_date = pd.to_datetime(art['published_utc'], format='ISO8601', utc=True, errors='coerce')
                    st.markdown(f"**Published:** {pub_date.strftime('%Y-%m-%d %H:%M') if pub_date else art['published_utc']}")
                except:
                    st.markdown(f"**Published:** {art['published_utc']}")
                st.markdown(f"**Source URL:** {art['source_url']}")
                if art['original_source_url']:
                    st.markdown(f"**Original URL:** {art['original_source_url']}")
            with col2:
                status_badge = {
                    "PENDING": '<span class="badge badge-pending">PENDING</span>',
                    "PROCESSED": '<span class="badge badge-success">PROCESSED</span>',
                    "FAILED": '<span class="badge badge-failed">FAILED</span>',
                }.get(art['status'], art['status'])
                st.markdown(f"**Status:** {status_badge}", unsafe_allow_html=True)
                st.markdown(f"**Source status:** {art['source_status']}")
            with st.expander("View raw HTML (truncated)"):
                async def get_raw():
                    async with DatabaseClient() as db:
                        cur = await db._conn.execute("SELECT raw_html FROM staging_raw WHERE id=?", (art['id'],))
                        row = await cur.fetchone()
                        return row[0] if row else ""
                raw = asyncio.run(get_raw())
                st.code(raw[:2000] + ("..." if len(raw)>2000 else ""), language="html")
    total_pages = (total + per_page - 1) // per_page
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("◀ Previous", disabled=(page <= 1)):
            st.session_state.article_page = page - 1
            st.rerun()
    with col2:
        st.markdown(f"<div style='text-align:center;'>Page {page} of {total_pages} ({total} total)</div>", unsafe_allow_html=True)
    with col3:
        if st.button("Next ▶", disabled=(page >= total_pages)):
            st.session_state.article_page = page + 1
            st.rerun()

def page_processed():
    st.markdown("<h1 style='color:#a29bfe;'>🧠 Processed Articles</h1>", unsafe_allow_html=True)

    with st.expander("🔍 Filters", expanded=False):
        col1, col2, col3 = st.columns(3)
        sources = asyncio.run(get_distinct_sources())
        with col1:
            source_filter = st.selectbox("Source", options=["All"] + sources, key="proc_source")
        with col2:
            search_filter = st.text_input("Search (title/summary)", placeholder="Keyword...", key="proc_search")
        col1, col2 = st.columns(2)
        with col1:
            date_from = st.date_input("From", value=None, key="proc_from")
        with col2:
            date_to = st.date_input("To", value=None, key="proc_to")

    per_page = 20
    page = st.session_state.processed_page
    filters = {
        "source": source_filter if source_filter != "All" else None,
        "date_from": date_from if date_from else None,
        "date_to": date_to if date_to else None,
        "search": search_filter if search_filter.strip() else None,
    }
    with st.spinner("Loading processed articles..."):
        articles, total = asyncio.run(fetch_processed_with_filters(
            source=filters["source"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            search=filters["search"],
            page=page,
            per_page=per_page
        ))
    if not articles:
        st.info("No processed articles found.")
        return

    for art in articles:
        expander = st.expander(f"🧾 {art['title']} (ID: {art['id']})")
        with expander:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Source:** {art['source_domain']}")
                st.markdown(f"**Author:** {art['author'] or 'Unknown'}")
                try:
                    pub_date = pd.to_datetime(art['published_utc'], format='ISO8601', utc=True, errors='coerce')
                    st.markdown(f"**Published:** {pub_date.strftime('%Y-%m-%d %H:%M') if pub_date else art['published_utc']}")
                except:
                    st.markdown(f"**Published:** {art['published_utc']}")
                st.markdown(f"**Processing status:** {art['processing_status']}")
                if art['confidence_score']:
                    st.markdown(f"**Confidence:** {art['confidence_score']}%")
                if art['verification_status']:
                    st.markdown(f"**Verification:** {art['verification_status']}")
                st.markdown(f"**Summary:** {art['summary'][:300] + '...' if len(art['summary'])>300 else art['summary']}")
            with col2:
                try:
                    iocs = json.loads(art['iocs_json']) if art['iocs_json'] else {}
                    ioc_count = sum(len(v) for v in iocs.values())
                    st.markdown(f"**IOCs:** {ioc_count}")
                except:
                    pass
                try:
                    mitre = json.loads(art['mitre_techniques_json']) if art['mitre_techniques_json'] else []
                    if mitre:
                        st.markdown("**MITRE ATT&CK:**")
                        badges = " ".join([f'<span class="badge badge-mitre">{t}</span>' for t in mitre])
                        st.markdown(badges, unsafe_allow_html=True)
                except:
                    pass

            report_key = f"report_{art['id']}"
            if st.button("📄 View Full Report", key=report_key):
                st.session_state[f"show_report_{art['id']}"] = not st.session_state.get(f"show_report_{art['id']}", False)

            if st.session_state.get(f"show_report_{art['id']}", False):
                with st.container():
                    st.markdown("---")
                    st.markdown("### Full Report")
                    full = asyncio.run(fetch_article_full(art['id']))
                    if full:
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Title:** {full['title']}")
                            st.markdown(f"**Source:** {full['source_domain']}")
                            st.markdown(f"**Author:** {full['author'] or 'Unknown'}")
                            st.markdown(f"**Published:** {full['published_utc']}")
                            st.markdown(f"**Processing Status:** {full['processing_status']}")
                            st.markdown(f"**Confidence:** {full['confidence_score']}%")
                            st.markdown(f"**Verification:** {full['verification_status']}")
                        with col2:
                            try:
                                mitre = json.loads(full['mitre_techniques_json']) if full['mitre_techniques_json'] else []
                                if mitre:
                                    st.markdown("**MITRE ATT&CK:**")
                                    badges = " ".join([f'<span class="badge badge-mitre">{t}</span>' for t in mitre])
                                    st.markdown(badges, unsafe_allow_html=True)
                            except:
                                pass
                        st.markdown("**Summary:**")
                        st.write(full['summary'])
                        st.markdown("**Threat Metadata:**")
                        try:
                            meta = json.loads(full['threat_metadata_json']) if full['threat_metadata_json'] else {}
                            if meta:
                                for k, v in meta.items():
                                    if v:
                                        st.markdown(f"- **{k.replace('_', ' ').title()}:** {', '.join(v) if isinstance(v, list) else v}")
                        except:
                            st.write(full['threat_metadata_json'])
                        st.markdown("**IOCs:**")
                        try:
                            iocs = json.loads(full['iocs_json']) if full['iocs_json'] else {}
                            if iocs:
                                ioc_df = pd.DataFrame([(k, v) for k, v in iocs.items() if v], columns=["Type", "Values"])
                                ioc_df["Values"] = ioc_df["Values"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
                                st.dataframe(ioc_df, use_container_width=True)
                        except:
                            st.write(full['iocs_json'])
                        st.markdown("**Raw JSON:**")
                        st.json({
                            "summary": full['summary'],
                            "iocs": json.loads(full['iocs_json']) if full['iocs_json'] else {},
                            "threat_metadata": json.loads(full['threat_metadata_json']) if full['threat_metadata_json'] else {},
                            "mitre_techniques": json.loads(full['mitre_techniques_json']) if full['mitre_techniques_json'] else [],
                            "confidence": full['confidence_score'],
                            "verification": full['verification_status']
                        })
                    else:
                        st.warning("Unable to fetch full details.")

    total_pages = (total + per_page - 1) // per_page
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("◀ Previous", disabled=(page <= 1), key="proc_prev"):
            st.session_state.processed_page = page - 1
            st.rerun()
    with col2:
        st.markdown(f"<div style='text-align:center;'>Page {page} of {total_pages} ({total} total)</div>", unsafe_allow_html=True)
    with col3:
        if st.button("Next ▶", disabled=(page >= total_pages), key="proc_next"):
            st.session_state.processed_page = page + 1
            st.rerun()

    st.markdown("---")
    st.subheader("📥 Export Processed Data")
    with st.expander("Export Options", expanded=False):
        export_format = st.selectbox("Format", ["CSV", "JSON", "STIX 2.1"])
        export_all = st.checkbox("Export all processed articles (ignores current filters)", value=False)
        if st.button("Generate Download"):
            with st.spinner("Preparing export..."):
                data = asyncio.run(fetch_all_processed_for_export())
                if not data:
                    st.warning("No processed articles available for export.")
                else:
                    if export_format == "CSV":
                        file_content = generate_csv(data)
                        mime = "text/csv"
                        ext = "csv"
                    elif export_format == "JSON":
                        file_content = generate_json(data)
                        mime = "application/json"
                        ext = "json"
                    elif export_format == "STIX 2.1":
                        file_content = generate_stix(data)
                        mime = "application/json"
                        ext = "json"
                    else:
                        st.error("Unsupported format")
                        file_content = None
                    if file_content:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"processed_export_{timestamp}.{ext}"
                        st.download_button(
                            label=f"⬇️ Download {export_format}",
                            data=file_content,
                            file_name=filename,
                            mime=mime,
                            use_container_width=True
                        )

# =============================================================================
# SIDEBAR NAVIGATION (simplified)
# =============================================================================
st.sidebar.markdown("<h1 style='color:#a29bfe; font-size:1.8rem;'>🛡️ CTI Pipeline</h1>", unsafe_allow_html=True)
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Articles", "Processed"],
    index=0,
    key="nav",
)
if page != "Dashboard":
    st.session_state.show_ingestion = False
st.session_state.page = page

if st.sidebar.button("🔄 Refresh Data"):
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### Pipeline Status")
status_text = ""
if st.session_state.ingestion_running:
    status_text = "⏳ Ingestion running..."
elif st.session_state.processing_running:
    status_text = "⏳ Processing running..."
else:
    status_text = "✅ Idle"
st.sidebar.markdown(f"<div style='color:#8f9bb3;'>{status_text}</div>", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style='font-size:0.7rem; color:#636e72;'>
    SOC Dashboard v3.1<br>
    Data source: raw_repository.db
</div>
""", unsafe_allow_html=True)

# =============================================================================
# PAGE ROUTING
# =============================================================================
if st.session_state.page == "Dashboard":
    page_dashboard()
elif st.session_state.page == "Articles":
    page_articles()
elif st.session_state.page == "Processed":
    page_processed()