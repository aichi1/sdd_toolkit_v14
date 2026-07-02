#!/usr/bin/env python3
"""グラフベース推薦エンジン。

依存グラフを使用して関連コンポーネントを推薦する。
距離・接続数・信頼度に基づくスコアリング。
"""

from collections import deque
from typing import Any

from .graph import DependencyGraph


class GraphRecommender:
    """グラフベースのコンポーネント推薦エンジン。"""

    def __init__(self, graph: DependencyGraph):
        """推薦エンジンを初期化する。

        Args:
            graph: DependencyGraph インスタンス
        """
        self.graph = graph

    def recommend(self, component_ids: list[str], max_results: int = 5) -> list[dict]:
        """入力コンポーネントに関連するコンポーネントを推薦する。

        Args:
            component_ids: 入力コンポーネント ID のリスト
            max_results: 最大推薦数

        Returns:
            推薦コンポーネントのリスト
            各要素: {"id": str, "name": str, "type": str, "score": float, "reason": str}
        """
        if not component_ids:
            return []

        # 各入力コンポーネントからの距離を計算
        distances = self._compute_distances(component_ids)
        connection_counts = self._compute_connections(component_ids, distances)

        # スコア計算
        recommendations = []
        for node_id, distance in distances.items():
            if node_id in component_ids:
                continue  # 入力コンポーネントは除外

            node_data = self.graph.nodes.get(node_id, {})
            confidence = node_data.get("metrics", {}).get("confidence", 0.5)
            connection_count = connection_counts.get(node_id, 1)

            # スコア = (1 / (distance + 1)) * connection_count * confidence
            score = (1.0 / (distance + 1)) * connection_count * confidence

            reason = self._generate_reason(node_id, component_ids, distance, connection_count)

            recommendations.append({
                "id": node_id,
                "name": node_data.get("name", node_id),
                "type": node_data.get("type", "unknown"),
                "score": round(score, 3),
                "reason": reason,
            })

        # スコアでソート
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:max_results]

    def recommend_for_category(
        self, category: str, registry_path: str, max_results: int = 5
    ) -> list[dict]:
        """カテゴリに基づいてコンポーネントを推薦する。

        Args:
            category: プロジェクトカテゴリ
            registry_path: registry.json のパス（実効性スコアの取得用）
            max_results: 最大推薦数

        Returns:
            推薦コンポーネントのリスト
        """
        # カテゴリに一致するコンポーネントをシードとして使用
        seed_ids = []
        for node_id, node_data in self.graph.nodes.items():
            if node_data.get("category_origin") == category:
                seed_ids.append(node_id)

        if not seed_ids:
            return []

        # シードから推薦を生成
        recommendations = self.recommend(seed_ids, max_results * 2)

        # 高実効性のプロジェクトで使用されたコンポーネントにボーナス
        for rec in recommendations:
            node_data = self.graph.nodes.get(rec["id"], {})
            effectiveness = node_data.get("metrics", {}).get("avg_effectiveness", 0.0)
            if effectiveness > 0.7:
                rec["score"] += 0.2 * effectiveness

        # 再ソートして返す
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:max_results]

    def explain_recommendation(self, from_id: str, to_id: str) -> str:
        """推薦理由を詳細に説明する。

        Args:
            from_id: 入力コンポーネント ID
            to_id: 推薦されたコンポーネント ID

        Returns:
            推薦理由の説明文
        """
        if from_id not in self.graph.nodes or to_id not in self.graph.nodes:
            return "Component not found in graph."

        from_name = self.graph.nodes[from_id].get("name", from_id)
        to_name = self.graph.nodes[to_id].get("name", to_id)

        # 関係性を分析
        is_dependency = to_id in [n for n, _ in self.graph.edges.get(from_id, [])]
        is_dependent = to_id in [n for n, _ in self.graph.reverse_edges.get(from_id, [])]

        to_data = self.graph.nodes[to_id]
        metrics = to_data.get("metrics", {})
        used_in = metrics.get("used_in_projects", 0)
        effectiveness = metrics.get("avg_effectiveness", 0.0)

        explanation = f"Component '{to_name}' is recommended because:\n"

        if is_dependency:
            explanation += f"- It is a direct dependency of '{from_name}'\n"
        elif is_dependent:
            explanation += f"- It directly depends on '{from_name}'\n"
        else:
            explanation += f"- It is indirectly related to '{from_name}'\n"

        if used_in > 0:
            explanation += f"- Used in {used_in} project(s) with avg effectiveness {effectiveness:.2f}\n"

        return explanation

    def get_installation_order(self, component_ids: list[str]) -> list[str]:
        """コンポーネントのインストール順序を取得する。

        Args:
            component_ids: インストールするコンポーネント ID のリスト

        Returns:
            トポロジカルソート済みコンポーネント ID のリスト（依存先が先）
        """
        # サブグラフを作成
        subgraph = DependencyGraph()
        visited = set()
        queue = deque(component_ids)

        # 全依存関係を含むサブグラフを構築
        while queue:
            node_id = queue.popleft()
            if node_id in visited or node_id not in self.graph.nodes:
                continue

            visited.add(node_id)
            subgraph.add_node(node_id, self.graph.nodes[node_id])

            # 依存関係を追加
            for dep_id, edge_type in self.graph.edges.get(node_id, []):
                if dep_id in self.graph.nodes:
                    if dep_id not in visited:
                        queue.append(dep_id)
                    subgraph.add_node(dep_id, self.graph.nodes[dep_id])
                    subgraph.add_edge(node_id, dep_id, edge_type)

        # トポロジカルソートの逆順 = 依存先が先（インストール順）
        try:
            sorted_ids = subgraph.topological_sort()
            # 逆順にして依存先を先に、入力リストに含まれるものだけを返す
            sorted_ids.reverse()
            return [nid for nid in sorted_ids if nid in component_ids]
        except ValueError:
            # 循環依存がある場合は元の順序を返す
            return component_ids

    def _compute_distances(self, seed_ids: list[str]) -> dict[str, int]:
        """各ノードへの最短距離を計算する（BFS）。

        Args:
            seed_ids: シードノード ID のリスト

        Returns:
            node_id -> 最短距離の辞書
        """
        distances = {}
        visited = set()
        queue = deque()

        for seed_id in seed_ids:
            if seed_id in self.graph.nodes:
                queue.append((seed_id, 0))
                visited.add(seed_id)
                distances[seed_id] = 0

        while queue:
            node_id, distance = queue.popleft()

            # 依存先と依存元の両方を探索
            neighbors = []
            neighbors.extend([n for n, _ in self.graph.edges.get(node_id, [])])
            neighbors.extend([n for n, _ in self.graph.reverse_edges.get(node_id, [])])

            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    distances[neighbor] = distance + 1
                    queue.append((neighbor, distance + 1))

        return distances

    def _compute_connections(
        self, seed_ids: list[str], distances: dict[str, int]
    ) -> dict[str, int]:
        """各ノードへの接続数を計算する。

        Args:
            seed_ids: シードノード ID のリスト
            distances: ノードごとの距離

        Returns:
            node_id -> 接続数の辞書
        """
        connections = {}

        for node_id in distances:
            if node_id in seed_ids:
                continue

            count = 0
            # 各シードノードとの接続を確認
            for seed_id in seed_ids:
                # 依存または被依存関係があるか
                deps = self.graph.get_dependencies(seed_id, depth=3)
                dependents = self.graph.get_dependents(seed_id, depth=3)

                if node_id in deps or node_id in dependents:
                    count += 1

            connections[node_id] = max(count, 1)  # 最小値は 1

        return connections

    def _generate_reason(
        self, node_id: str, seed_ids: list[str], distance: int, connection_count: int
    ) -> str:
        """推薦理由を生成する。

        Args:
            node_id: 推薦対象ノード ID
            seed_ids: シードノード ID のリスト
            distance: 距離
            connection_count: 接続数

        Returns:
            推薦理由の文字列
        """
        node_data = self.graph.nodes.get(node_id, {})
        node_name = node_data.get("name", node_id)

        reasons = []

        if distance == 1:
            reasons.append("directly related to input components")
        elif distance == 2:
            reasons.append("indirectly related (2 hops away)")
        else:
            reasons.append(f"related ({distance} hops away)")

        if connection_count > 1:
            reasons.append(f"connected to {connection_count} input components")

        return f"{node_name}: " + ", ".join(reasons)
