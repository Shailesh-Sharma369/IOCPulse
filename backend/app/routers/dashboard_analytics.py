from fastapi import APIRouter, Depends
from src.shared.database import DatabaseClient
from app.dependencies import get_db
from app.services.database_service import DatabaseService
from app.services.job_service import job_service
from app.utils.response import success_response
import json
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

@router.get("/analytics")
async def get_analytics(db: DatabaseClient = Depends(get_db)):
    db_service = DatabaseService(db)

    # 1. Metrics (existing)
    stats = await db_service.get_dashboard_stats()

    # 2. Articles by source
    cursor = await db._conn.execute("""
        SELECT source_domain, COUNT(*) as count
        FROM staging_raw
        GROUP BY source_domain
        ORDER BY count DESC
    """)
    rows = await cursor.fetchall()
    articles_by_source = [{"source": row[0], "count": row[1]} for row in rows]

    # 3. IOC Distribution (from processed_articles)
    cursor = await db._conn.execute("""
        SELECT iocs_json, processing_timestamp FROM processed_articles
    """)
    ioc_rows = await cursor.fetchall()
    ioc_distribution = {
        "ip": 0, "domain": 0, "url": 0, "md5": 0, "sha1": 0, "sha256": 0,
        "cve": 0, "email": 0, "file_name": 0, "registry_key": 0, "mutex": 0,
        "malware_family": 0
    }
    # Also compute iocs_this_month
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    iocs_this_month = 0

    for row in ioc_rows:
        iocs_json = row[0]
        proc_time = row[1]
        if iocs_json:
            try:
                iocs = json.loads(iocs_json)
                for key in ioc_distribution.keys():
                    if key in iocs and iocs[key]:
                        count = len(iocs[key])
                        ioc_distribution[key] += count
                        # Check if processing timestamp is within current month
                        if proc_time and proc_time >= month_start:
                            iocs_this_month += count
            except:
                pass

    # 4. Threat Summary (top malware, threat actors, target industries)
    cursor = await db._conn.execute("""
        SELECT threat_metadata_json FROM processed_articles
    """)
    meta_rows = await cursor.fetchall()
    malware_count = {}
    actor_count = {}
    industry_count = {}
    for row in meta_rows:
        meta_json = row[0]
        if meta_json:
            try:
                meta = json.loads(meta_json)
                for malware in meta.get("malware_name", []):
                    malware_count[malware] = malware_count.get(malware, 0) + 1
                for actor in meta.get("threat_actor", []):
                    actor_count[actor] = actor_count.get(actor, 0) + 1
                for industry in meta.get("target_industry", []):
                    industry_count[industry] = industry_count.get(industry, 0) + 1
            except:
                pass

    threat_summary = {
        "top_malware": sorted(malware_count.items(), key=lambda x: x[1], reverse=True)[:5],
        "top_actors": sorted(actor_count.items(), key=lambda x: x[1], reverse=True)[:5],
        "top_industries": sorted(industry_count.items(), key=lambda x: x[1], reverse=True)[:5],
    }

    # 5. Recent Activity (jobs)
    jobs = await job_service.list_jobs(10)
    recent_activity = [job.dict() for job in jobs]

    # 6. Recent Articles (with IOC count if processed)
    cursor = await db._conn.execute("""
        SELECT s.id, s.title, s.source_domain, s.published_utc, s.status,
               (SELECT COUNT(*) FROM processed_articles p WHERE p.metadata_hash = s.metadata_hash) as has_processed
        FROM staging_raw s
        ORDER BY s.retrieved_utc DESC
        LIMIT 10
    """)
    article_rows = await cursor.fetchall()
    recent_articles = []
    for row in article_rows:
        article = dict(row)
        if article["has_processed"] > 0:
            cursor2 = await db._conn.execute("""
                SELECT iocs_json FROM processed_articles WHERE metadata_hash = (
                    SELECT metadata_hash FROM staging_raw WHERE id = ?
                )
            """, (article["id"],))
            ioc_row = await cursor2.fetchone()
            if ioc_row and ioc_row[0]:
                try:
                    iocs = json.loads(ioc_row[0])
                    article["ioc_count"] = sum(len(v) for v in iocs.values())
                except:
                    article["ioc_count"] = 0
            else:
                article["ioc_count"] = 0
        else:
            article["ioc_count"] = 0
        recent_articles.append(article)

    return success_response(data={
        "metrics": stats,
        "articles_by_source": articles_by_source,
        "ioc_distribution": ioc_distribution,
        "iocs_this_month": iocs_this_month,
        "threat_summary": threat_summary,
        "recent_activity": recent_activity,
        "recent_articles": recent_articles,
    })