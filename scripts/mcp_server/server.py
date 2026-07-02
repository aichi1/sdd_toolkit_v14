"""MCP Server - Knowledge Base REST API.

FastAPI application providing programmatic access to the SDD knowledge base.
Binds to localhost only for security.
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query, status
from fastapi.responses import JSONResponse

from . import handlers, schemas

# Configuration from environment
KB_DIR = os.getenv("SDD_KB_DIR", os.path.expanduser("~/.sdd-knowledge"))
API_TOKEN = os.getenv("SDD_API_TOKEN")  # Optional API token for auth

# FastAPI app
app = FastAPI(
    title="SDD Knowledge Base",
    version="1.0.0",
    description="Knowledge base API for SDD Toolkit with search and recommendation",
)


def verify_token(authorization: Optional[str] = Header(None)) -> None:
    """Verify API token if configured.

    Raises:
        HTTPException: If token is required but missing or invalid
    """
    if API_TOKEN:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required",
            )
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization format. Use 'Bearer <token>'",
            )
        token = authorization[7:]  # Remove "Bearer " prefix
        if token != API_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token"
            )


@app.get("/health", response_model=schemas.HealthResponse)
async def health_check() -> dict:
    """Health check endpoint."""
    registry_path = os.path.join(KB_DIR, "registry.json")
    from .handlers import load_json_safe

    registry = load_json_safe(registry_path)
    component_count = len(registry.get("components", [])) if registry else 0

    return {
        "status": "ok",
        "version": "1.0.0",
        "kb_dir": KB_DIR,
        "components_count": component_count,
    }


@app.get("/search", response_model=schemas.SearchResponse)
async def search(
    q: str = Query(..., description="Search query string"),
    top_k: int = Query(10, ge=1, le=100, description="Max results"),
    type: Optional[str] = Query(None, description="Filter by component type"),
    authorization: Optional[str] = Header(None),
) -> dict:
    """Search knowledge base components.

    Uses BM25 search with fallback to tag matching if index not available.
    """
    verify_token(authorization)

    # Validate type filter
    if type and type not in ["skill", "agent", "doc", "hook", "rule"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid type filter: {type}",
        )

    try:
        results = handlers.search_components(q, KB_DIR, top_k, type)
        return {"query": q, "results": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@app.get("/component/{component_id}", response_model=schemas.ComponentResponse)
async def get_component(
    component_id: str, authorization: Optional[str] = Header(None)
) -> dict:
    """Get full component details by ID."""
    verify_token(authorization)

    component = handlers.get_component(component_id, KB_DIR)
    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component '{component_id}' not found",
        )

    return component


@app.post(
    "/component",
    response_model=schemas.ComponentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_component(
    component: schemas.ComponentCreate, authorization: Optional[str] = Header(None)
) -> dict:
    """Create a new component."""
    verify_token(authorization)

    try:
        created = handlers.create_component(component.dict(), KB_DIR)
        return created
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create component: {str(e)}",
        ) from e


@app.put("/component/{component_id}", response_model=schemas.ComponentResponse)
async def update_component(
    component_id: str,
    component: schemas.ComponentUpdate,
    authorization: Optional[str] = Header(None),
) -> dict:
    """Update an existing component (partial update)."""
    verify_token(authorization)

    try:
        # Filter out None values for partial update
        update_data = {k: v for k, v in component.dict().items() if v is not None}
        updated = handlers.update_component(component_id, update_data, KB_DIR)

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Component '{component_id}' not found",
            )

        return updated
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update component: {str(e)}",
        ) from e


@app.get("/recommend", response_model=schemas.RecommendResponse)
async def recommend(
    task_description: str = Query(..., description="Task description"),
    max_results: int = Query(5, ge=1, le=20, description="Max recommendations"),
    authorization: Optional[str] = Header(None),
) -> dict:
    """Get component recommendations based on task description."""
    verify_token(authorization)

    try:
        recommendations = handlers.recommend_components(
            task_description, KB_DIR, max_results
        )
        return {"task_description": task_description, "recommendations": recommendations}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recommendation failed: {str(e)}",
        ) from e


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unexpected errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


if __name__ == "__main__":
    import uvicorn

    # Bind to localhost only for security
    uvicorn.run(app, host="127.0.0.1", port=8741, log_level="info")
