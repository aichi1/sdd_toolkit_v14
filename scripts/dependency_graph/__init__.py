"""依存グラフベースの推薦システム。

コンポーネント間の依存関係を有向グラフとして表現し、
グラフアルゴリズムを用いて関連コンポーネントを推薦する。
"""

from .graph import DependencyGraph
from .recommender import GraphRecommender

__all__ = ["DependencyGraph", "GraphRecommender"]
