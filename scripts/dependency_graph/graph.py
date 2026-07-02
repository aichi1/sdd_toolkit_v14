#!/usr/bin/env python3
"""依存グラフ構築と検索。

registry.json のコンポーネント依存関係から有向グラフを構築し、
BFS/DFS による関連コンポーネント検索を提供する。
"""

import json
import os
import sys
from collections import deque

# scripts/ ディレクトリをパスに追加（registry_utils のインポート用）
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
from registry_utils import load_json_safe


class DependencyGraph:
    """コンポーネント依存関係グラフ。"""

    def __init__(self):
        self.nodes: dict[str, dict] = {}  # node_id -> node_data
        self.edges: dict[str, list[tuple[str, str]]] = {}  # from_id -> [(to_id, edge_type)]
        self.reverse_edges: dict[str, list[tuple[str, str]]] = {}  # to_id -> [(from_id, edge_type)]

    @classmethod
    def from_registry(cls, registry_path: str) -> "DependencyGraph":
        """registry.json からグラフを構築する。

        Args:
            registry_path: registry.json のパス

        Returns:
            DependencyGraph インスタンス
        """
        graph = cls()
        registry = load_json_safe(registry_path)
        if not registry:
            return graph

        components = registry.get("components", [])
        # First pass: add all nodes
        for comp in components:
            graph.add_node(comp["id"], comp)

        # Second pass: add all edges (now all nodes exist)
        for comp in components:
            comp_id = comp["id"]
            deps = comp.get("dependencies", {})
            for req_id in deps.get("required", []):
                graph.add_edge(comp_id, req_id, "required")
            for rec_id in deps.get("recommended", []):
                graph.add_edge(comp_id, rec_id, "recommended")

        return graph

    def add_node(self, node_id: str, data: dict) -> None:
        """ノードを追加する。

        Args:
            node_id: ノード ID
            data: ノードデータ（コンポーネント情報）
        """
        self.nodes[node_id] = data
        if node_id not in self.edges:
            self.edges[node_id] = []
        if node_id not in self.reverse_edges:
            self.reverse_edges[node_id] = []

    def add_edge(self, from_id: str, to_id: str, edge_type: str = "required") -> None:
        """エッジを追加する（from は to に依存）。

        Args:
            from_id: 依存元コンポーネント ID
            to_id: 依存先コンポーネント ID
            edge_type: エッジタイプ（"required" | "recommended"）
        """
        # 未知のノードは無視（graceful handling）
        if from_id not in self.nodes or to_id not in self.nodes:
            return

        if from_id not in self.edges:
            self.edges[from_id] = []
        if to_id not in self.reverse_edges:
            self.reverse_edges[to_id] = []

        self.edges[from_id].append((to_id, edge_type))
        self.reverse_edges[to_id].append((from_id, edge_type))

    def get_dependencies(self, node_id: str, depth: int = -1) -> list[str]:
        """ノードの依存先を取得する（BFS）。

        Args:
            node_id: ノード ID
            depth: 探索深度（-1 で無制限）

        Returns:
            依存先ノード ID のリスト
        """
        if node_id not in self.nodes:
            return []

        visited = set()
        result = []
        queue = deque([(node_id, 0)])
        visited.add(node_id)

        while queue:
            current, current_depth = queue.popleft()

            if depth != -1 and current_depth >= depth:
                continue

            for neighbor, _ in self.edges.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    result.append(neighbor)
                    queue.append((neighbor, current_depth + 1))

        return result

    def get_dependents(self, node_id: str, depth: int = -1) -> list[str]:
        """ノードに依存するノードを取得する（BFS）。

        Args:
            node_id: ノード ID
            depth: 探索深度（-1 で無制限）

        Returns:
            依存元ノード ID のリスト
        """
        if node_id not in self.nodes:
            return []

        visited = set()
        result = []
        queue = deque([(node_id, 0)])
        visited.add(node_id)

        while queue:
            current, current_depth = queue.popleft()

            if depth != -1 and current_depth >= depth:
                continue

            for neighbor, _ in self.reverse_edges.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    result.append(neighbor)
                    queue.append((neighbor, current_depth + 1))

        return result

    def get_related(self, node_id: str, max_depth: int = 2) -> list[str]:
        """関連ノードを取得する（依存先 + 依存元）。

        Args:
            node_id: ノード ID
            max_depth: 最大探索深度

        Returns:
            関連ノード ID のリスト
        """
        deps = self.get_dependencies(node_id, max_depth)
        dependents = self.get_dependents(node_id, max_depth)
        return list(set(deps + dependents))

    def detect_cycles(self) -> list[list[str]]:
        """循環依存を検出する。

        Returns:
            循環依存のリスト（各循環は [node1, node2, ..., node1] 形式）
        """
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor, _ in self.edges.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path[:])
                elif neighbor in rec_stack:
                    # 循環検出
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            rec_stack.remove(node)

        for node in self.nodes:
            if node not in visited:
                dfs(node, [])

        return cycles

    def topological_sort(self) -> list[str]:
        """トポロジカルソートを実行する。

        Returns:
            トポロジカルソート済みノード ID のリスト

        Raises:
            ValueError: 循環依存が存在する場合
        """
        cycles = self.detect_cycles()
        if cycles:
            raise ValueError(f"Circular dependencies detected: {cycles}")

        in_degree = {node: 0 for node in self.nodes}
        for node in self.nodes:
            for neighbor, _ in self.edges.get(node, []):
                in_degree[neighbor] += 1

        queue = deque([node for node, degree in in_degree.items() if degree == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)

            for neighbor, _ in self.edges.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result

    def to_dict(self) -> dict:
        """グラフを JSON シリアライズ可能な辞書に変換する。

        Returns:
            グラフの辞書表現
        """
        return {
            "nodes": self.nodes,
            "edges": {
                from_id: [(to_id, edge_type) for to_id, edge_type in edges]
                for from_id, edges in self.edges.items()
            },
            "stats": {
                "node_count": len(self.nodes),
                "edge_count": sum(len(edges) for edges in self.edges.values()),
            },
        }
