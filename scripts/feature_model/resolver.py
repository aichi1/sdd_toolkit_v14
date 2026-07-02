#!/usr/bin/env python3
"""
Feature dependency resolver for SDD Knowledge System.
Resolves feature configurations and provides recommendations.
"""
from pathlib import Path
from typing import Optional

from .model import FeatureModel


class FeatureResolver:
    """Resolves feature dependencies and provides configuration recommendations."""

    def __init__(self, model: FeatureModel):
        """Initialize resolver with a FeatureModel."""
        self.model = model

    def resolve(self, selected: list[str]) -> list[str]:
        """
        Given user-selected features, compute the full set.
        Steps:
        1. Add all mandatory features
        2. For each selected feature, add required dependencies (from constraints)
        3. Check excludes constraints (raise error if violated)

        Returns the complete resolved feature list.
        """
        resolved = set(selected)

        # Add all mandatory features
        mandatory = self.model.get_mandatory_features()
        resolved.update(mandatory)

        # Resolve 'requires' constraints iteratively
        changed = True
        max_iterations = 20  # Prevent infinite loop
        iteration = 0

        while changed and iteration < max_iterations:
            changed = False
            iteration += 1

            for constraint in self.model.constraints:
                if constraint.get("type") == "requires":
                    if_f = constraint.get("if")
                    then_f = constraint.get("then")
                    if if_f in resolved and then_f not in resolved:
                        resolved.add(then_f)
                        changed = True

        # Check for excludes violations
        for constraint in self.model.constraints:
            if constraint.get("type") == "excludes":
                f1 = constraint.get("feature1")
                f2 = constraint.get("feature2")
                if f1 in resolved and f2 in resolved:
                    reason = constraint.get("reason", "")
                    raise ValueError(
                        f"Cannot select both '{f1}' and '{f2}'. {reason}"
                    )

        return sorted(list(resolved))

    def get_minimal_configuration(self) -> list[str]:
        """Return minimum viable configuration (mandatory only)."""
        return self.model.get_mandatory_features()

    def get_recommended_configuration(self, category: Optional[str] = None) -> list[str]:
        """
        Return recommended configuration based on project category.

        Categories:
        - research_report: registry + search + extraction + context + templates
        - small_implementation: registry + search + extraction + templates
        - internal_proposal: registry + search + extraction + context + curation
        - full: all features (for advanced users)
        - None/default: minimal + search enhancements
        """
        if category == "research_report":
            selected = [
                "context",
                "context.active-context",
                "templates",
                "templates.skill-fragments",
                "templates.doc-fragments",
            ]
        elif category == "small_implementation":
            selected = [
                "templates",
                "templates.skill-fragments",
                "templates.doc-fragments",
            ]
        elif category == "internal_proposal":
            selected = [
                "context",
                "context.active-context",
                "context.retrospective-lessons",
                "curation",
                "curation.knowledge-curator",
            ]
        elif category == "full":
            # All features
            selected = list(self.model.features.keys())
        else:
            # Default: minimal + search enhancements
            selected = [
                "search.claude-rerank",
            ]

        return self.resolve(selected)

    def get_impact(self, feature: str) -> dict:
        """
        What enabling this feature would require and unlock.
        Returns: {"requires": [...], "enables": [...], "excludes": [...]}
        """
        if feature not in self.model.features:
            return {"error": f"Unknown feature: {feature}"}

        requires = []
        enables = []
        excludes = []

        # Check what this feature requires
        for constraint in self.model.constraints:
            if constraint.get("type") == "requires" and constraint.get("if") == feature:
                requires.append(constraint.get("then"))

        # Check what requires this feature (i.e., what it enables)
        for constraint in self.model.constraints:
            if constraint.get("type") == "requires" and constraint.get("then") == feature:
                enables.append(constraint.get("if"))

        # Check what it excludes
        for constraint in self.model.constraints:
            if constraint.get("type") == "excludes":
                if constraint.get("feature1") == feature:
                    excludes.append(constraint.get("feature2"))
                elif constraint.get("feature2") == feature:
                    excludes.append(constraint.get("feature1"))

        return {
            "requires": sorted(requires),
            "enables": sorted(enables),
            "excludes": sorted(excludes),
        }

    def explain_configuration(self, selected: list[str]) -> dict:
        """
        Explain a configuration: what's selected, what's added by resolution.
        Returns summary with breakdown.
        """
        mandatory = self.model.get_mandatory_features()
        resolved = self.resolve(selected)

        user_selected = set(selected) - set(mandatory)
        auto_added = set(resolved) - set(selected)

        return {
            "total_features": len(resolved),
            "mandatory": sorted(mandatory),
            "user_selected": sorted(user_selected),
            "auto_added": sorted(auto_added),
            "full_configuration": resolved,
        }

    def find_conflicts(self, features: list[str]) -> list[dict]:
        """
        Find all conflicts (excludes violations) in a feature list.
        Returns list of conflict descriptions.
        """
        conflicts = []
        feature_set = set(features)

        for constraint in self.model.constraints:
            if constraint.get("type") == "excludes":
                f1 = constraint.get("feature1")
                f2 = constraint.get("feature2")
                if f1 in feature_set and f2 in feature_set:
                    conflicts.append({
                        "feature1": f1,
                        "feature2": f2,
                        "reason": constraint.get("reason", ""),
                    })

        return conflicts


if __name__ == "__main__":
    # Example usage
    model_path = Path(__file__).parent / "feature_tree.json"
    model = FeatureModel(model_path)
    resolver = FeatureResolver(model)

    print("=== Minimal Configuration ===")
    minimal = resolver.get_minimal_configuration()
    print(f"Features: {len(minimal)}")
    for f in minimal[:10]:
        print(f"  - {f}")
    if len(minimal) > 10:
        print(f"  ... and {len(minimal) - 10} more")

    print("\n=== Recommended: research_report ===")
    research = resolver.get_recommended_configuration("research_report")
    print(f"Features: {len(research)}")
    for f in research[:15]:
        print(f"  - {f}")
    if len(research) > 15:
        print(f"  ... and {len(research) - 15} more")

    print("\n=== Feature Impact: context ===")
    impact = resolver.get_impact("context")
    print(f"Requires: {impact['requires']}")
    print(f"Enables: {impact['enables']}")
    print(f"Excludes: {impact['excludes']}")

    print("\n=== Explain Configuration ===")
    selected = ["context", "templates"]
    explanation = resolver.explain_configuration(selected)
    print(f"Total features: {explanation['total_features']}")
    print(f"Mandatory: {len(explanation['mandatory'])}")
    print(f"User selected: {explanation['user_selected']}")
    print(f"Auto-added: {explanation['auto_added']}")

    print("\n=== Test Conflict Detection ===")
    conflicting = ["auto-tagging", "claude-rerank"]
    conflicts = resolver.find_conflicts(conflicting)
    if conflicts:
        print("Conflicts found:")
        for c in conflicts:
            print(f"  - {c['feature1']} vs {c['feature2']}: {c['reason']}")
    else:
        print("No conflicts")
