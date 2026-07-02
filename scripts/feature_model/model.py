#!/usr/bin/env python3
"""
SPL Feature Model for SDD Knowledge System.
Loads, validates, and queries the feature tree.
"""
import json
from pathlib import Path
from typing import Any


class FeatureModel:
    """Manages the feature tree and provides query operations."""

    def __init__(self, tree_path: str | Path):
        """Load feature tree from JSON file."""
        self.tree_path = Path(tree_path)
        with open(self.tree_path, 'r', encoding='utf-8') as f:
            self.tree = json.load(f)

        self.root = self.tree.get("root", "")
        self.version = self.tree.get("version", "1.0.0")
        self.features = self._flatten_features(self.tree.get("features", {}))
        self.constraints = self.tree.get("constraints", [])

    def _flatten_features(self, features: dict[str, Any], parent: str = "") -> dict[str, dict]:
        """Flatten nested feature hierarchy into {name: feature_data}."""
        result = {}
        for name, data in features.items():
            full_name = f"{parent}.{name}" if parent else name
            feature_info = {
                "name": full_name,
                "type": data.get("type", "optional"),
                "description": data.get("description", ""),
                "parent": parent or None,
                "children": []
            }
            result[full_name] = feature_info

            # Process children recursively
            children = data.get("children", {})
            if children:
                feature_info["children"] = list(children.keys())
                child_features = self._flatten_features(children, full_name)
                result.update(child_features)

        return result

    def validate_tree(self) -> list[str]:
        """
        Validate the feature tree structure.
        Returns list of error messages (empty if valid).
        """
        errors = []

        # Check all features have type and description
        for name, feature in self.features.items():
            if not feature.get("type"):
                errors.append(f"Feature '{name}' missing type")
            elif feature["type"] not in ["mandatory", "optional", "alternative"]:
                errors.append(f"Feature '{name}' has invalid type: {feature['type']}")

            if not feature.get("description"):
                errors.append(f"Feature '{name}' missing description")

        # Check constraints reference valid features
        for constraint in self.constraints:
            c_type = constraint.get("type")
            if c_type == "requires":
                if_feature = constraint.get("if")
                then_feature = constraint.get("then")
                if if_feature not in self.features:
                    errors.append(f"Constraint 'requires' references unknown feature: {if_feature}")
                if then_feature not in self.features:
                    errors.append(f"Constraint 'requires' references unknown feature: {then_feature}")
            elif c_type == "excludes":
                f1 = constraint.get("feature1")
                f2 = constraint.get("feature2")
                if f1 not in self.features:
                    errors.append(f"Constraint 'excludes' references unknown feature: {f1}")
                if f2 not in self.features:
                    errors.append(f"Constraint 'excludes' references unknown feature: {f2}")
            else:
                errors.append(f"Unknown constraint type: {c_type}")

        # Check for circular dependencies in requires constraints
        circular = self._detect_circular_dependencies()
        if circular:
            errors.append(f"Circular dependency detected: {' -> '.join(circular)}")

        return errors

    def _detect_circular_dependencies(self) -> list[str] | None:
        """Detect circular dependencies in requires constraints using DFS."""
        # Build dependency graph
        deps = {}
        for constraint in self.constraints:
            if constraint.get("type") == "requires":
                if_f = constraint.get("if")
                then_f = constraint.get("then")
                if if_f not in deps:
                    deps[if_f] = []
                deps[if_f].append(then_f)

        # DFS to detect cycle
        visited = set()
        path = []

        def dfs(node: str) -> bool:
            if node in path:
                # Found cycle, return the cycle path
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]
            if node in visited:
                return None

            visited.add(node)
            path.append(node)

            for neighbor in deps.get(node, []):
                result = dfs(neighbor)
                if result:
                    return result

            path.pop()
            return None

        for feature in deps:
            if feature not in visited:
                cycle = dfs(feature)
                if cycle:
                    return cycle

        return None

    def get_feature(self, name: str) -> dict | None:
        """Return feature by name, or None if not found."""
        return self.features.get(name)

    def get_mandatory_features(self) -> list[str]:
        """Return all unconditionally mandatory features.

        Only includes features where the entire parent chain is mandatory.
        Children of optional parents are conditionally mandatory.
        """
        mandatory = []
        for name, feature in self.features.items():
            if feature["type"] != "mandatory":
                continue
            # Check parent chain is all mandatory
            parent = feature.get("parent")
            all_mandatory = True
            while parent:
                parent_feat = self.features.get(parent)
                if not parent_feat or parent_feat["type"] != "mandatory":
                    all_mandatory = False
                    break
                parent = parent_feat.get("parent")
            if all_mandatory:
                mandatory.append(name)
        return sorted(mandatory)

    def get_optional_features(self) -> list[str]:
        """Return all optional features."""
        optional = []
        for name, feature in self.features.items():
            if feature["type"] == "optional":
                optional.append(name)
        return sorted(optional)

    def list_features(self, include_children: bool = True) -> list[dict]:
        """
        Return all features as flat list with path info.
        If include_children=False, only return top-level features.
        """
        if include_children:
            return [
                {
                    "name": name,
                    "type": f["type"],
                    "description": f["description"],
                    "parent": f["parent"]
                }
                for name, f in sorted(self.features.items())
            ]
        else:
            # Only top-level (no parent)
            return [
                {
                    "name": name,
                    "type": f["type"],
                    "description": f["description"],
                    "parent": f["parent"]
                }
                for name, f in sorted(self.features.items())
                if f["parent"] is None
            ]

    def validate_configuration(self, selected: list[str]) -> tuple[bool, list[str]]:
        """
        Check if a set of selected features is valid.
        Returns (is_valid, list_of_errors).

        Validation rules:
        1. All mandatory features must be selected
        2. If a parent is selected, child can be selected
        3. 'requires' constraints must be satisfied
        4. 'excludes' constraints must not be violated
        """
        errors = []
        selected_set = set(selected)

        # Check mandatory features: only require if parent chain is active
        for name, feature in self.features.items():
            if feature["type"] != "mandatory":
                continue
            # Check if parent chain is active (all parents are mandatory or selected)
            parent = feature.get("parent")
            parent_active = True
            while parent:
                parent_feat = self.features.get(parent)
                if not parent_feat:
                    break
                if parent_feat["type"] != "mandatory" and parent not in selected_set:
                    parent_active = False
                    break
                parent = parent_feat.get("parent")
            if parent_active and name not in selected_set:
                errors.append(f"Mandatory feature '{name}' not selected")

        # Check parent-child relationships for selected features
        for feature in selected:
            if feature not in self.features:
                errors.append(f"Unknown feature: {feature}")
                continue

            parent = self.features[feature].get("parent")
            if parent and parent not in selected_set:
                parent_feature = self.features.get(parent)
                if parent_feature and parent_feature["type"] != "mandatory":
                    errors.append(
                        f"Feature '{feature}' requires parent '{parent}' to be selected"
                    )

        # Check 'requires' constraints
        for constraint in self.constraints:
            if constraint.get("type") == "requires":
                if_f = constraint.get("if")
                then_f = constraint.get("then")
                if if_f in selected_set and then_f not in selected_set:
                    reason = constraint.get("reason", "")
                    errors.append(
                        f"Feature '{if_f}' requires '{then_f}' to be selected. {reason}"
                    )

        # Check 'excludes' constraints
        for constraint in self.constraints:
            if constraint.get("type") == "excludes":
                f1 = constraint.get("feature1")
                f2 = constraint.get("feature2")
                if f1 in selected_set and f2 in selected_set:
                    reason = constraint.get("reason", "")
                    errors.append(
                        f"Features '{f1}' and '{f2}' cannot be selected together. {reason}"
                    )

        return (len(errors) == 0, errors)


if __name__ == "__main__":
    # Example usage
    model_path = Path(__file__).parent / "feature_tree.json"
    model = FeatureModel(model_path)

    print(f"Feature Model: {model.root} v{model.version}")
    print(f"Total features: {len(model.features)}")

    # Validate tree
    errors = model.validate_tree()
    if errors:
        print("\nValidation errors:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("\nFeature tree is valid.")

    # List mandatory features
    print(f"\nMandatory features ({len(model.get_mandatory_features())}):")
    for feature in model.get_mandatory_features():
        print(f"  - {feature}")

    # List optional features
    print(f"\nOptional features ({len(model.get_optional_features())}):")
    for feature in model.get_optional_features():
        print(f"  - {feature}")
