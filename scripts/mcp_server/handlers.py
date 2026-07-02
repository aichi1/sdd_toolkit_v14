"""Request handlers for MCP server API endpoints.

These are pure functions that handle business logic without FastAPI dependencies.
"""

import os
import sys
from datetime import datetime
from typing import Optional

# scripts/ ディレクトリをパスに追加（registry_utils 等のインポート用）
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)

from registry_utils import (
    check_duplicate,
    load_json_safe,
    save_json,
    validate_component,
    validate_registry_entry,
)


def _safe_bm25_search(
    query: str, kb_dir: str, top_k: int = 10, type_filter: Optional[str] = None
) -> list[dict]:
    """Safely perform BM25 search with fallback to tag matching.

    Returns:
        List of search results with id, name, type, description, score.
    """
    try:
        import bm25s
    except ImportError:
        # BM25 not available, fall back to tag matching
        return _fallback_tag_search(query, kb_dir, top_k, type_filter)

    index_dir = os.path.join(kb_dir, "search-index")
    meta_path = os.path.join(index_dir, "corpus_meta.json")

    if not os.path.isdir(index_dir) or not os.path.exists(meta_path):
        # Index not built yet, fall back to tag matching
        return _fallback_tag_search(query, kb_dir, top_k, type_filter)

    try:
        # Load BM25 index
        retriever = bm25s.BM25.load(index_dir)
        corpus_meta = load_json_safe(meta_path)
        if not corpus_meta:
            return _fallback_tag_search(query, kb_dir, top_k, type_filter)

        # Perform search
        tokens = bm25s.tokenize([query])
        results, scores = retriever.retrieve(tokens, k=min(top_k * 2, len(corpus_meta)))

        # Format results
        search_results = []
        for idx, score in zip(results[0], scores[0]):
            if score <= 0:
                continue
            meta = corpus_meta[idx]
            if type_filter and meta.get("type") != type_filter:
                continue
            search_results.append(
                {
                    "id": meta["id"],
                    "name": meta.get("name", ""),
                    "type": meta.get("type", ""),
                    "description": meta.get("description", ""),
                    "score": round(float(score), 4),
                }
            )
            if len(search_results) >= top_k:
                break

        return search_results

    except Exception:
        # Any error in BM25 search, fall back to tag matching
        return _fallback_tag_search(query, kb_dir, top_k, type_filter)


def _fallback_tag_search(
    query: str, kb_dir: str, top_k: int = 10, type_filter: Optional[str] = None
) -> list[dict]:
    """Fallback search using simple tag and description matching."""
    registry_path = os.path.join(kb_dir, "registry.json")
    registry = load_json_safe(registry_path)
    if not registry:
        return []

    query_lower = query.lower()
    query_words = set(query_lower.split())

    results = []
    for comp in registry.get("components", []):
        if type_filter and comp.get("type") != type_filter:
            continue

        # Calculate simple relevance score
        score = 0.0
        tags = [t.lower() for t in comp.get("tags", [])]
        name_lower = comp.get("name", "").lower()
        desc_lower = comp.get("description", "").lower()

        # Exact tag match: +2.0
        for tag in tags:
            if tag in query_lower:
                score += 2.0

        # Tag word match: +1.0
        for tag in tags:
            if any(word in tag for word in query_words):
                score += 1.0

        # Name match: +1.5
        if query_lower in name_lower:
            score += 1.5

        # Description match: +0.5
        if query_lower in desc_lower:
            score += 0.5

        if score > 0:
            results.append(
                {
                    "id": comp["id"],
                    "name": comp.get("name", ""),
                    "type": comp.get("type", ""),
                    "description": comp.get("description", ""),
                    "score": round(score, 4),
                }
            )

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def search_components(
    q: str, kb_dir: str, top_k: int = 10, type_filter: Optional[str] = None
) -> list[dict]:
    """Search components using BM25 (with tag fallback).

    Args:
        q: Search query string
        kb_dir: Knowledge base directory path
        top_k: Maximum number of results
        type_filter: Optional component type filter

    Returns:
        List of search results
    """
    return _safe_bm25_search(q, kb_dir, top_k, type_filter)


def get_component(component_id: str, kb_dir: str) -> Optional[dict]:
    """Get full component details by ID.

    Args:
        component_id: Component ID
        kb_dir: Knowledge base directory path

    Returns:
        Full component dict or None if not found
    """
    # Load registry to get component metadata
    registry_path = os.path.join(kb_dir, "registry.json")
    registry = load_json_safe(registry_path)
    if not registry:
        return None

    # Find component in registry
    comp_entry = None
    for comp in registry.get("components", []):
        if comp["id"] == component_id:
            comp_entry = comp
            break

    if not comp_entry:
        return None

    # Load full component content
    comp_path = os.path.join(kb_dir, comp_entry["path"])
    comp_data = load_json_safe(comp_path)
    if not comp_data:
        return None

    # Merge registry metadata with component content
    result = {**comp_entry, **comp_data}
    return result


def create_component(data: dict, kb_dir: str) -> dict:
    """Create a new component.

    Args:
        data: Component data (from ComponentCreate schema)
        kb_dir: Knowledge base directory path

    Returns:
        Created component dict

    Raises:
        ValueError: If validation fails or duplicate exists
    """
    # Load registry
    registry_path = os.path.join(kb_dir, "registry.json")
    registry = load_json_safe(registry_path)
    if not registry:
        # Initialize empty registry
        registry = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "stats": {"total_components": 0, "by_type": {}},
            "components": [],
        }

    # Check for duplicates
    if check_duplicate(registry, data["id"]):
        raise ValueError(f"Component with id '{data['id']}' already exists")

    # Validate component content
    comp_data = {
        "id": data["id"],
        "type": data["type"],
        "version": data["version"],
        "content": data["content"],
        "placeholders": data.get("placeholders", []),
        "quality_criteria": data.get("quality_criteria", []),
        "provenance": data["provenance"],
        "adaptation_notes": data.get("adaptation_notes", ""),
    }
    errors = validate_component(comp_data)
    if errors:
        raise ValueError(f"Component validation failed: {', '.join(errors)}")

    # Save component file
    components_dir = os.path.join(kb_dir, "components")
    os.makedirs(components_dir, exist_ok=True)
    comp_path = os.path.join(components_dir, f"{data['id']}.json")
    save_json(comp_data, comp_path)

    # Create registry entry
    registry_entry = {
        "id": data["id"],
        "name": data["name"],
        "type": data["type"],
        "version": data["version"],
        "description": data["description"],
        "tags": data.get("tags", []),
        "category_origin": data["category_origin"],
        "dependencies": data.get("dependencies", {"required": [], "recommended": []}),
        "metrics": {
            "used_in_projects": 0,
            "avg_effectiveness": 0.5,
            "confidence": 0.5,
            "last_used": datetime.now().strftime("%Y-%m-%d"),
        },
        "path": f"components/{data['id']}.json",
    }

    errors = validate_registry_entry(registry_entry)
    if errors:
        raise ValueError(f"Registry entry validation failed: {', '.join(errors)}")

    # Update registry
    registry["components"].append(registry_entry)
    registry["last_updated"] = datetime.now().isoformat()
    registry["stats"]["total_components"] = len(registry["components"])
    registry["stats"]["by_type"] = registry["stats"].get("by_type", {})
    registry["stats"]["by_type"][data["type"]] = (
        registry["stats"]["by_type"].get(data["type"], 0) + 1
    )

    save_json(registry, registry_path)

    # Return full component
    return {**registry_entry, **comp_data}


def update_component(component_id: str, data: dict, kb_dir: str) -> Optional[dict]:
    """Update an existing component (partial update).

    Args:
        component_id: Component ID
        data: Partial update data (from ComponentUpdate schema)
        kb_dir: Knowledge base directory path

    Returns:
        Updated component dict or None if not found

    Raises:
        ValueError: If validation fails
    """
    # Get existing component
    existing = get_component(component_id, kb_dir)
    if not existing:
        return None

    # Update component file
    comp_path = os.path.join(kb_dir, existing["path"])
    comp_data = load_json_safe(comp_path)
    if not comp_data:
        return None

    # Apply updates to component content
    if "content" in data and data["content"] is not None:
        comp_data["content"] = data["content"]
    if "placeholders" in data and data["placeholders"] is not None:
        comp_data["placeholders"] = data["placeholders"]
    if "quality_criteria" in data and data["quality_criteria"] is not None:
        comp_data["quality_criteria"] = data["quality_criteria"]
    if "adaptation_notes" in data and data["adaptation_notes"] is not None:
        comp_data["adaptation_notes"] = data["adaptation_notes"]

    # Update provenance
    if "provenance" in comp_data:
        comp_data["provenance"]["updated_at"] = datetime.now().strftime("%Y-%m-%d")

    save_json(comp_data, comp_path)

    # Update registry entry
    registry_path = os.path.join(kb_dir, "registry.json")
    registry = load_json_safe(registry_path)
    if not registry:
        return None

    for comp in registry["components"]:
        if comp["id"] == component_id:
            if "name" in data and data["name"] is not None:
                comp["name"] = data["name"]
            if "description" in data and data["description"] is not None:
                comp["description"] = data["description"]
            if "tags" in data and data["tags"] is not None:
                comp["tags"] = data["tags"]
            if "dependencies" in data and data["dependencies"] is not None:
                comp["dependencies"] = data["dependencies"]
            break

    registry["last_updated"] = datetime.now().isoformat()
    save_json(registry, registry_path)

    # Return updated component
    return {**comp, **comp_data}


def recommend_components(
    task_description: str, kb_dir: str, max_results: int = 5
) -> list[dict]:
    """Recommend components based on task description.

    Args:
        task_description: Task description string
        kb_dir: Knowledge base directory path
        max_results: Maximum recommendations to return

    Returns:
        List of recommendations with confidence and reason
    """
    # Use search as the base for recommendations
    search_results = search_components(task_description, kb_dir, top_k=max_results * 2)

    # Load registry for additional metadata
    registry_path = os.path.join(kb_dir, "registry.json")
    registry = load_json_safe(registry_path)
    if not registry:
        return []

    # Enhance with confidence and reasoning
    recommendations = []
    for result in search_results[:max_results]:
        # Find full component data
        comp_entry = None
        for comp in registry.get("components", []):
            if comp["id"] == result["id"]:
                comp_entry = comp
                break

        if not comp_entry:
            continue

        # Calculate confidence based on search score and metrics
        search_confidence = min(result["score"] / 10.0, 1.0)  # Normalize
        metrics_confidence = comp_entry.get("metrics", {}).get("confidence", 0.5)
        effectiveness = comp_entry.get("metrics", {}).get("avg_effectiveness", 0.5)

        # Weighted confidence
        confidence = (
            search_confidence * 0.5 + metrics_confidence * 0.3 + effectiveness * 0.2
        )

        # Generate recommendation reason
        reason_parts = []
        if result["score"] > 5.0:
            reason_parts.append("Strong keyword match")
        elif result["score"] > 2.0:
            reason_parts.append("Good keyword match")

        usage_count = comp_entry.get("metrics", {}).get("used_in_projects", 0)
        if usage_count > 5:
            reason_parts.append(f"Used in {usage_count} projects")
        elif usage_count > 0:
            reason_parts.append(f"Used {usage_count} times")

        if effectiveness > 0.7:
            reason_parts.append("High effectiveness")

        reason = "; ".join(reason_parts) if reason_parts else "Keyword match"

        recommendations.append(
            {
                "id": result["id"],
                "name": result["name"],
                "type": result["type"],
                "description": result["description"],
                "confidence": round(min(confidence, 1.0), 4),
                "reason": reason,
            }
        )

    return recommendations
