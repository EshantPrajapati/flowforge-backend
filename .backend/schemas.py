from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime


# -------------------------
# Base Project Schema
# -------------------------
class ProjectBase(BaseModel):
    title: str = Field(..., min_length=3)
    slug: str = Field(..., min_length=3)
    category: Optional[str] = None
    short_desc: Optional[str] = None
    details: Optional[str] = None
    tech_stack: List[str] = []
    cover_color: Optional[str] = None
    is_published: bool = False


# -------------------------
# Create Project (Admin)
# -------------------------
class ProjectCreate(ProjectBase):
    pass


# -------------------------
# Project Response (Public)
# -------------------------
class ProjectResponse(ProjectBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
