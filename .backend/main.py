import os
from typing import Optional, List

import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware

from database import get_connection
from schemas import ProjectCreate, ProjectResponse

# -------------------------------------------------
# App initialization
# -------------------------------------------------

app = FastAPI(
    title="FlowForge API",
    version="1.0.0",
    description="Backend API for FlowForge AI Solutions"
)

# -------------------------------------------------
# Admin Auth (MUST BE ABOVE ROUTES)
# -------------------------------------------------

def admin_auth(x_admin_token: Optional[str] = Header(None)):
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Admin token not configured"
        )

    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized"
        )

# -------------------------------------------------
# CORS
# -------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Startup DB check
# -------------------------------------------------

@app.on_event("startup")
def startup_db_check():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1;")
    cur.fetchone()
    cur.close()
    conn.close()

# -------------------------------------------------
# Health
# -------------------------------------------------

@app.get("/")
def health_check():
    return {"status": "ok"}

# -------------------------------------------------
# Public: All projects
# -------------------------------------------------

@app.get("/projects", response_model=List[ProjectResponse])
def get_projects():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT id, title, slug, category, short_desc,
               tech_stack, cover_color, created_at
        FROM projects
        WHERE is_published = TRUE
        ORDER BY created_at DESC
    """)

    data = cur.fetchall()
    cur.close()
    conn.close()
    return data

# -------------------------------------------------
# Public: Project by slug
# -------------------------------------------------

@app.get("/projects/{slug}", response_model=ProjectResponse)
def get_project(slug: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT *
        FROM projects
        WHERE slug = %s AND is_published = TRUE
        LIMIT 1
    """, (slug,))

    project = cur.fetchone()
    cur.close()
    conn.close()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project

# -------------------------------------------------
# Admin: Create project
# -------------------------------------------------

@app.post("/admin/projects")
def create_project(
    data: ProjectCreate,
    _: None = Depends(admin_auth)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            INSERT INTO projects (
                title, slug, category, short_desc,
                details, tech_stack, cover_color, is_published
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            data.title,
            data.slug.lower().strip(),
            data.category,
            data.short_desc,
            data.details,
            data.tech_stack,  # text[]
            data.cover_color,
            data.is_published
        ))

        project_id = cur.fetchone()["id"]
        conn.commit()
        return {"success": True, "project_id": project_id}

    except errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail="Project with this slug already exists"
        )

    finally:
        cur.close()
        conn.close()

# -------------------------------------------------
# Admin: Toggle publish
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
