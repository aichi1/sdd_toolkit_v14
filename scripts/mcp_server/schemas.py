"""Pydantic schemas for MCP server API request/response models."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ComponentType(str, Enum):
    """Component type enumeration."""

    skill = "skill"
    agent = "agent"
    doc = "doc"
    hook = "hook"
    rule = "rule"


class ComponentBase(BaseModel):
    """Base component fields shared across requests."""

    id: str = Field(..., description="Unique component identifier")
    name: str = Field(..., description="Human-readable component name")
    type: ComponentType = Field(..., description="Component type")
    version: str = Field(..., description="Semver version string")
    description: str = Field(..., description="Short description of the component")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")


class Placeholder(BaseModel):
    """Placeholder definition for templated components."""

    key: str
    description: str
    example: str


class Provenance(BaseModel):
    """Component origin and update history."""

    created_from: str = Field(..., description="Source project name")
    created_at: str = Field(..., description="Creation date (YYYY-MM-DD)")
    updated_from: list[str] = Field(default_factory=list, description="Update sources")
    updated_at: Optional[str] = Field(None, description="Last update date (YYYY-MM-DD)")


class ComponentCreate(BaseModel):
    """Request model for creating a new component."""

    id: str
    name: str
    type: ComponentType
    version: str
    description: str
    tags: list[str] = Field(default_factory=list)
    content: str = Field(..., description="Markdown content of the component")
    placeholders: Optional[list[Placeholder]] = None
    quality_criteria: Optional[list[str]] = None
    provenance: Provenance
    adaptation_notes: Optional[str] = None
    category_origin: str = Field(..., description="Original category")
    dependencies: Optional[dict[str, list[str]]] = Field(
        default_factory=lambda: {"required": [], "recommended": []}
    )


class ComponentUpdate(BaseModel):
    """Request model for updating an existing component."""

    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    content: Optional[str] = None
    placeholders: Optional[list[Placeholder]] = None
    quality_criteria: Optional[list[str]] = None
    adaptation_notes: Optional[str] = None
    dependencies: Optional[dict[str, list[str]]] = None


class Metrics(BaseModel):
    """Component usage metrics."""

    used_in_projects: int
    avg_effectiveness: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    last_used: str = Field(..., description="Last usage date (YYYY-MM-DD)")


class Dependencies(BaseModel):
    """Component dependencies."""

    required: list[str] = Field(default_factory=list)
    recommended: list[str] = Field(default_factory=list)


class ComponentResponse(BaseModel):
    """Full component detail response."""

    id: str
    name: str
    type: ComponentType
    version: str
    description: str
    tags: list[str]
    category_origin: str
    content: str
    placeholders: Optional[list[Placeholder]] = None
    quality_criteria: Optional[list[str]] = None
    provenance: Provenance
    adaptation_notes: Optional[str] = None
    dependencies: Dependencies
    metrics: Metrics
    path: str


class SearchRequest(BaseModel):
    """Search query request."""

    q: str = Field(..., description="Search query string")
    top_k: int = Field(10, ge=1, le=100, description="Maximum results to return")
    type_filter: Optional[ComponentType] = None


class SearchResult(BaseModel):
    """Individual search result."""

    id: str
    name: str
    type: ComponentType
    description: str
    score: float = Field(..., description="Relevance score")


class SearchResponse(BaseModel):
    """Search results response."""

    query: str
    results: list[SearchResult]
    total: int = Field(..., description="Total results found")


class RecommendRequest(BaseModel):
    """Recommendation request."""

    task_description: str = Field(..., description="Task description for recommendation")
    max_results: int = Field(5, ge=1, le=20, description="Maximum recommendations")


class Recommendation(BaseModel):
    """Individual recommendation result."""

    id: str
    name: str
    type: ComponentType
    description: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="Recommendation confidence")
    reason: str = Field(..., description="Why this component was recommended")


class RecommendResponse(BaseModel):
    """Recommendation results response."""

    task_description: str
    recommendations: list[Recommendation]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str = "1.0.0"
    kb_dir: str
    components_count: int
