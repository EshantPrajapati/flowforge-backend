import os
from typing import Optional, List

import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware

from database import get_connection

# -------------------------------------------------
# App
# -------------------------------------------------

app = FastAPI(
    title="FlowForge API",
    version="2.0.0",
    description="Production Backend for FlowForge AI"
)

# -------------------------------------------------
# Admin Auth
# -------------------------------------------------

def admin_auth(x_admin_token: Optional[str] = Header(None)):
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not set")

    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

# -------------------------------------------------
# CORS
# -------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://flowforgeai.netlify.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Startup DB Check
# -------------------------------------------------

@app.on_event("startup")
def startup_check():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1;")
    cur.close()
    conn.close()

# -------------------------------------------------
# Health
# -------------------------------------------------

@app.get("/")
def health():
    return {"status": "ok"}

# -------------------------------------------------
# CORE QUERY (REUSED)
# -------------------------------------------------

PROJECT_QUERY = """
SELECT
    p.id,
    p.title,
    p.slug,
    p.category,
    p.short_desc,
    p.cover_color,
    p.created_at,

    jsonb_build_object(
        'challenge', d.challenge,
        'solution', d.solution,
        'timeline', d.timeline,
        'before', d.before_text,
        'after', d.after_text,
        'code_snippet', d.code_snippet
    ) AS details,

    COALESCE(
        jsonb_agg(DISTINCT t.tech)
        FILTER (WHERE t.tech IS NOT NULL),
        '[]'
    ) AS tech_stack,

    COALESCE(
        jsonb_agg(
            DISTINCT jsonb_build_object(
                'title', s.title,
                'text', s.description,
                'position', s.position
            )
            ORDER BY s.position
        ) FILTER (WHERE s.id IS NOT NULL),
        '[]'
    ) AS steps,

    COALESCE(
        jsonb_agg(
            DISTINCT jsonb_build_object(
                'label', r.label,
                'value', r.value
            )
        ) FILTER (WHERE r.id IS NOT NULL),
        '[]'
    ) AS results,

    COALESCE(
        jsonb_agg(
            DISTINCT jsonb_build_object(
                'label', l.label,
                'url', l.url,
                'icon', l.icon
            )
        ) FILTER (WHERE l.id IS NOT NULL),
        '[]'
    ) AS links

FROM projects p
LEFT JOIN project_details d ON d.project_id = p.id
LEFT JOIN project_tech_stack t ON t.project_id = p.id
LEFT JOIN project_steps s ON s.project_id = p.id
LEFT JOIN project_results r ON r.project_id = p.id
LEFT JOIN project_links l ON l.project_id = p.id
"""

# -------------------------------------------------
# Public: All Projects
# -------------------------------------------------

@app.get("/projects")
def get_projects():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        PROJECT_QUERY +
        " WHERE p.is_published = TRUE "
        " GROUP BY p.id, d.project_id "
        " ORDER BY p.created_at DESC"
    )

    data = cur.fetchall()
    cur.close()
    conn.close()
    return data

# -------------------------------------------------
# Public: Project by slug
# -------------------------------------------------

@app.get("/projects/{slug}")
def get_project(slug: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        PROJECT_QUERY +
        " WHERE p.slug = %s AND p.is_published = TRUE "
        " GROUP BY p.id, d.project_id "
        " LIMIT 1",
        (slug,)
    )

    project = cur.fetchone()
    cur.close()
    conn.close()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project

# -------------------------------------------------
# Admin: Create Project (base only)
# -------------------------------------------------

@app.post("/admin/projects")
def create_project(
    title: str,
    slug: str,
    category: str,
    short_desc: str,
    cover_color: str,
    is_published: bool = False,
    _: None = Depends(admin_auth)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            INSERT INTO projects
            (title, slug, category, short_desc, cover_color, is_published)
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            title,
            slug.lower().strip(),
            category,
            short_desc,
            cover_color,
            is_published
        ))

        project_id = cur.fetchone()["id"]
        conn.commit()
        return {"success": True, "project_id": project_id}

    except errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="Slug already exists")

    finally:
        cur.close()
        conn.close()

# -------------------------------------------------
# Admin: Toggle Publish
# -------------------------------------------------

@app.patch("/admin/projects/{project_id}/publish")
def toggle_publish(
    project_id: str,
    _: None = Depends(admin_auth)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        UPDATE projects
        SET is_published = NOT is_published
        WHERE id = %s
        RETURNING is_published
    """, (project_id,))

    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not result:
        raise HTTPException(status_code=404, detail="Project not found")

    return result
