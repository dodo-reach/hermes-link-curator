"""Standalone web app for the link curator archive."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from archive import get_all_entries, get_entries_by_date, get_tags, search_entries, clear_cache, get_graph_data

BASE_DIR = Path(__file__).resolve().parent
# Auto-discover vault path:
# This file lives at <profile>/dashboard/main.py
# Vault lives at <profile>/vault
# Override with $HERMES_ARCHIVE_VAULT env var if needed.
VAULT_PATH = os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    str(Path(__file__).resolve().parent.parent / "vault")
)
PORT = int(os.environ.get("ARCHIVE_PORT", "8090"))
HOST = os.environ.get("ARCHIVE_HOST", "127.0.0.1")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


def build_tags_context() -> dict:
    """Shared tags context for all pages."""
    return {"tags": get_tags()[:30]}


# ─── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(title="Archive", description="Link curator archive")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# ─── Routes ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    days = get_entries_by_date()
    ctx = {
        "request": request,
        "page_title": "Archive",
        "current_page": "archive-list",
        "total_entries": len(get_all_entries()),
        "total_days": len(days),
        "generated_at": "",
        "days": days,
        **build_tags_context(),
    }
    return templates.TemplateResponse(request=request, name="index.html", context=ctx)


@app.get("/calendar", response_class=HTMLResponse)
async def calendar(request: Request) -> HTMLResponse:
    days = get_entries_by_date()
    ctx = {
        "request": request,
        "page_title": "Archive - Calendar",
        "current_page": "calendar",
        "total_entries": len(get_all_entries()),
        "total_days": len(days),
        "generated_at": "",
        "days_json": [
            {"date": d.date, "label": d.label, "count": len(d.entries)}
            for d in days
        ],
        **build_tags_context(),
    }
    return templates.TemplateResponse(request=request, name="calendar.html", context=ctx)


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = "") -> HTMLResponse:
    query = q.strip()
    if query:
        results = search_entries(query)
    else:
        results = get_all_entries()[:50]

    ctx = {
        "request": request,
        "page_title": "Archive - Search",
        "current_page": "search",
        "total_entries": len(get_all_entries()),
        "total_days": len(get_entries_by_date()),
        "generated_at": "",
        "results": results,
        "query": query,
        "is_search": bool(query),
        **build_tags_context(),
    }
    return templates.TemplateResponse(request=request, name="search.html", context=ctx)


@app.get("/tag/{tag}", response_class=HTMLResponse)
async def by_tag(request: Request, tag: str) -> HTMLResponse:
    entries = search_entries(f"#{tag}")
    ctx = {
        "request": request,
        "page_title": f"Archive - #{tag}",
        "current_page": "tag",
        "total_entries": len(get_all_entries()),
        "total_days": len(get_entries_by_date()),
        "generated_at": "",
        "tag": tag,
        "tag_entries": entries,
        **build_tags_context(),
    }
    return templates.TemplateResponse(request=request, name="tag.html", context=ctx)


@app.get("/day/{date}", response_class=HTMLResponse)
async def by_day(request: Request, date: str) -> HTMLResponse:
    all_days = get_entries_by_date()
    day_data = next((d for d in all_days if d.date == date), None)
    ctx = {
        "request": request,
        "page_title": f"Archive - {date}",
        "current_page": "day",
        "total_entries": len(get_all_entries()),
        "total_days": len(all_days),
        "generated_at": "",
        "all_days": all_days,
        "day_entries": day_data.entries if day_data else [],
        "day_date": date,
        "day_label": day_data.label if day_data else date,
        **build_tags_context(),
    }
    return templates.TemplateResponse(request=request, name="day.html", context=ctx)


@app.get("/day-json/{date}", response_class=JSONResponse)
async def day_json(date: str) -> JSONResponse:
    all_days = get_entries_by_date()
    day_data = next((d for d in all_days if d.date == date), None)
    if not day_data:
        return JSONResponse([], status_code=404)
    return JSONResponse([
        {
            "title": e.title,
            "url": e.url,
            "entry_type": e.entry_type,
            "summary": e.summary,
            "tags": e.tags,
        }
        for e in day_data.entries
    ])


@app.get("/stats", response_class=JSONResponse)
async def stats() -> JSONResponse:
    entries = get_all_entries()
    tags = get_tags()
    type_counts: dict[str, int] = {}
    for e in entries:
        type_counts[e.entry_type] = type_counts.get(e.entry_type, 0) + 1
    return JSONResponse({
        "total": len(entries),
        "days": len(set(e.added for e in entries)),
        "by_type": type_counts,
        "top_tags": tags[:15],
    })


@app.get("/graph", response_class=HTMLResponse)
async def graph(request: Request) -> HTMLResponse:
    data = get_graph_data()
    ctx = {
        "request": request,
        "page_title": "Archive - Graph",
        "current_page": "graph",
        "total_entries": len(get_all_entries()),
        "total_days": len(get_entries_by_date()),
        "node_count": len(data["nodes"]),
        "link_count": len(data["links"]),
        **build_tags_context(),
    }
    return templates.TemplateResponse(request=request, name="graph.html", context=ctx)


@app.get("/graph-json", response_class=JSONResponse)
async def graph_json() -> JSONResponse:
    return JSONResponse(get_graph_data())


@app.get("/health", response_class=JSONResponse)
async def health() -> JSONResponse:
    """Health check endpoint."""
    try:
        entries = get_all_entries()
        days = get_entries_by_date()
        return JSONResponse({
            "status": "healthy",
            "vault_path": str(VAULT_PATH),
            "total_entries": len(entries),
            "total_days": len(days),
        })
    except Exception as e:
        return JSONResponse({"status": "unhealthy", "error": str(e)}, status_code=500)

@app.get("/reload-cache")
async def reload_cache() -> JSONResponse:
    """Clear and reload the vault cache. Call this after adding new entries."""
    clear_cache()
    entries = get_all_entries()
    return JSONResponse({"status": "ok", "total_entries": len(entries), "cached": True})


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
