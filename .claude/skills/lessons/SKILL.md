# lessons - 蓄積された学びのレビュー（Accumulated Learnings）

## 目的
過去のレトロスペクティブ（振り返り）から蓄積された学び（Lessons）を検索・表示し、新規プロジェクトの意思決定をエビデンスベースで行えるようにします。

## 前提条件
- `~/.sdd-knowledge/retrospectives/` ディレクトリが存在すること
- 少なくとも1つのレトロスペクティブ JSON ファイルが存在すること

## 入力
- 任意: カテゴリフィルタ（例: `"investigation-report"`, `"technical-proposal"`）
- 任意: 優先度フィルタ（`"high"`, `"medium"`, `"low"`, `"all"`）
- 任意: 検索クエリ（lesson テキスト内のキーワード）
- 任意: 上限（表示する lesson 数。デフォルト: 10）

## 出力
- 以下を含む Markdown レポート:
  - カテゴリ別のパターン
  - カテゴリ横断のインサイト
  - lesson の頻度 / エビデンス（根拠）
  - 実行可能な推奨アクション（Actionable recommendations）

## ワークフロー

### フェーズ 0: データの読み込み

**Step 0.1: レトロスペクティブ・ディレクトリをスキャン**
```bash
cd ~/.sdd-knowledge/retrospectives/

# すべての retrospective JSON ファイルを列挙（summary.json は除外）
files=$(find . -name "*.json" -not -name "summary.json")

# カテゴリ別に件数を集計
categories=$(jq -r '.metadata.category' *.json | sort | uniq -c)
```

**Step 0.2: サマリーを読み込み（存在する場合）**
```bash
if [ -f summary.json ]; then
  # すぐに使える統計がある
  summary=$(cat summary.json)
else
  # その場で生成
  summary=$(generate_summary_from_all_retrospectives)
fi
```

**Step 0.3: フィルタをパース**
```python
filters = {
    "category": None,  # None = 全カテゴリ
    "priority": "all",  # high|medium|low|all
    "search": None,     # lesson テキスト内のキーワード検索
    "limit": 10,        # 表示する最大 lesson 数
    "sort_by": "frequency"  # frequency|priority|date
}

# ユーザー入力から更新
filters.update(parse_user_input(command))
```

### フェーズ 1: Lesson の集約

**Step 1.1: 全 lesson を抽出**
```python
all_lessons = []

for retro_file in retrospective_files:
    data = load_json(retro_file)
    
    for lesson in data["lessons_learned"]:
        all_lessons.append({
            "lesson": lesson["lesson"],
            "category": lesson.get("category", "general"),
            "priority": lesson.get("priority", "medium"),
            "evidence": lesson.get("evidence", ""),
            "applicability": lesson.get("applicability", data["metadata"]["category"]),
            "project": data["metadata"]["project_name"],
            "date": data["metadata"]["date"],
            "satisfaction": data["metadata"].get("satisfaction_rating", None)
        })
```

**Step 1.2: 重複排除 & クラスタリング**
```python
# 類似する lesson をグルーピング
lesson_clusters = {}

for lesson in all_lessons:
    # 比較しやすいようにテキストを正規化
    normalized = normalize_lesson_text(lesson["lesson"])
    
    # 類似 lesson を探す（曖昧一致 / fuzzy matching）
    similar_key = find_similar_cluster(normalized, lesson_clusters)
    
    if similar_key:
        # 既存クラスタに追加
        lesson_clusters[similar_key].append(lesson)
    else:
        # 新規クラスタ作成
        lesson_clusters[normalized] = [lesson]

# 頻度（frequency）を計算
for key, cluster in lesson_clusters.items():
    cluster_meta = {
        "canonical_lesson": cluster[0]["lesson"],
        "frequency": len(cluster),
        "projects": [l["project"] for l in cluster],
        "priorities": [l["priority"] for l in cluster],
        "evidence": [l["evidence"] for l in cluster],
        "first_seen": min(l["date"] for l in cluster),
        "last_seen": max(l["date"] for l in cluster)
    }
```

**Step 1.3: フィルタを適用**
```python
filtered_lessons = []

for cluster_key, cluster in lesson_clusters.items():
    meta = cluster_meta[cluster_key]
    
    # カテゴリフィルタ
    if filters["category"]:
        if not any(l["applicability"] == filters["category"] for l in cluster):
            continue
    
    # 優先度フィルタ
    if filters["priority"] != "all":
        if filters["priority"] not in meta["priorities"]:
            continue
    
    # 検索フィルタ
    if filters["search"]:
        if filters["search"].lower() not in meta["canonical_lesson"].lower():
            continue
    
    filtered_lessons.append(meta)

# ソート
if filters["sort_by"] == "frequency":
    filtered_lessons.sort(key=lambda x: x["frequency"], reverse=True)
elif filters["sort_by"] == "priority":
    priority_order = {"high": 0, "medium": 1, "low": 2}
    filtered_lessons.sort(key=lambda x: min(priority_order.get(p, 2) for p in x["priorities"]))
elif filters["sort_by"] == "date":
    filtered_lessons.sort(key=lambda x: x["last_seen"], reverse=True)

# 件数制限
filtered_lessons = filtered_lessons[:filters["limit"]]
```

### フェーズ 2: パターン認識

**Step 2.1: 高信頼パターンを特定**
```python
patterns = {
    "high_confidence": [],  # 頻度 >= 3 かつ High priority
    "emerging": [],         # 頻度 == 2
    "single_occurrence": [] # 頻度 == 1 だが High priority
}

for lesson_meta in filtered_lessons:
    if lesson_meta["frequency"] >= 3 and "high" in lesson_meta["priorities"]:
        patterns["high_confidence"].append(lesson_meta)
    elif lesson_meta["frequency"] == 2:
        patterns["emerging"].append(lesson_meta)
    elif lesson_meta["frequency"] == 1 and "high" in lesson_meta["priorities"]:
        patterns["single_occurrence"].append(lesson_meta)
```

**Step 2.2: 矛盾を検出**
```python
# 互いに競合する lesson を探す
contradictions = []

for i, lesson1 in enumerate(filtered_lessons):
    for lesson2 in filtered_lessons[i+1:]:
        if detect_contradiction(lesson1["canonical_lesson"], lesson2["canonical_lesson"]):
            contradictions.append({
                "lesson1": lesson1,
                "lesson2": lesson2,
                "conflict_type": "approach",  # 例: "tool", "process" など
                "resolution_needed": True
            })
```

**Step 2.3: カテゴリ別インサイト**
```python
if filters["category"]:
    # 1カテゴリに深掘り
    category_analysis = {
        "category": filters["category"],
        "total_projects": count_projects_in_category(filters["category"]),
        "avg_duration": calculate_avg_duration(filters["category"]),
        "avg_satisfaction": calculate_avg_satisfaction(filters["category"]),
        "common_pain_points": extract_frequent_challenges(filters["category"]),
        "success_factors": extract_frequent_successes(filters["category"]),
        "docs_template_evolution": {
            "essential_files": get_always_used_docs(filters["category"]),
            "optional_files": get_sometimes_used_docs(filters["category"]),
            "often_missing": get_frequently_missing_docs(filters["category"])
        },
        "time_trends": analyze_duration_trends(filters["category"])
    }
```

### フェーズ 3: レポート生成

**Step 3.1: エグゼクティブサマリー**
```markdown
# Accumulated Learnings

**Query**: {フィルタ内容の説明}
**Projects analyzed**: {N} retrospectives
**Date range**: {first} to {last}
**Lessons found**: {total count}

## Quick Stats
- High-confidence patterns: {N} (3+ プロジェクトで観測)
- Emerging patterns: {N} (2 プロジェクトで観測)
- Category-specific: {N}
- Cross-category: {N}
```

**Step 3.2: 高信頼パターン**
```markdown
## High-Confidence Patterns

これらの lesson は 3+ プロジェクトで出現し、かつ High priority です:

### 1. {Lesson title/summary}
**Frequency**: {N} projects
**Categories**: {list}
**First seen**: {date}
**Last seen**: {date}

**Lesson**:
{最新の発生例から全文を引用}

**Evidence**（プロジェクト例）:
- {Project 1}: {evidence}
- {Project 2}: {evidence}
- {Project 3}: {evidence}

**Current status**:
- [x] {category} starter に適用済み (v{version})
- [ ] starter には未反映
- [ ] 手動での判断が必要

**Actionable recommendation**:
{次プロジェクトで取るべき具体アクション}

---

### 2. {Next lesson}
...
```

**Step 3.3: カテゴリ別分析（フィルタ時のみ）**
```markdown
## Deep Dive: {Category}

**Projects completed**: {N}
**Average duration**: {X} hours
**Average satisfaction**: {X}/5
**Starter maturity**: v{version}, confidence {score}

### Success Factors
一貫してうまくいったこと:
1. {Factor 1} - {N} プロジェクトで観測
2. {Factor 2} - {N} プロジェクトで観測

### Common Challenges
摩擦になりやすいこと:
1. {Challenge 1} - {N} 回発生
   - *Recommendation*: {対策}
2. {Challenge 2} - {N} 回発生
   - *Recommendation*: {対策}

### docs/ テンプレートの状態
{N} プロジェクトからの示唆:

**必須ファイル**（全プロジェクトで使われた）:
- background.md
- scope.md
- ...

**有用なことが多い**（50%+ のプロジェクトで使用）:
- competitor-analysis.md ({N}/{total})
- ...

**ほぼ不要**（<25% のプロジェクトで使用）:
- {file}（starter から外す検討）

**途中で頻繁に追加される**（starter に入れるべき）:
- {file} - Phase {X} 中に {N} プロジェクトで追加

### 見積もりガイダンス（時間）
過去データから:

| Phase | Typical Duration | Range | Common Delays |
|-------|------------------|-------|---------------|
| 1     | 2.0h            | 1.5-2.5h | Source gathering |
| 2     | 2.5h            | 2.0-4.0h | Comparison methodology |
| 3     | 2.0h            | 1.5-3.0h | Formatting |
| **Total** | **6.5h**    | **5-9h** | |

**Recommendation**: {category} プロジェクトは {X}h ± {Y}h で見積もる

### トレンド分析
時間推移:
- Project 1 ({date}): {X}h
- Project 2 ({date}): {X}h
- Project 3 ({date}): {X}h
- **Trend**: {improving/stable/degrading}

{改善なら}: {category} は高速化しています。平均改善率: {X}% / プロジェクト
{悪化なら}: 最近遅くなっています。原因の仮説: {analysis}
```

**Step 3.4: 新興パターン**
```markdown
## Emerging Patterns (2 occurrences)

これらの lesson はパターン化し始めています。再発に注意:

### {Lesson}
**Seen in**: {Project 1}, {Project 2}
**Lesson**: {text}
**Consider**: {starter に追加すべきか？}
```

**Step 3.5: カテゴリ横断のインサイト**
```markdown
## Cross-Category Insights

複数カテゴリに適用できる lesson:

### Builder/Validator Effectiveness
全カテゴリで:
- **Projects using B/V**: {N}
- **Average issues caught**: {X}
- **User satisfaction**: {X}/5（B/V なしは {Y}/5）
- **Recommendation**: すべてのプロジェクトで継続利用

### docs/ Best Practices
普遍的な学び:
- すべてのプロジェクトで {X} は有益
- {Y} がないプロジェクトは遅延が起きやすい

### Tool Learnings
- {Tool/technique} は {use case} に有効
- {Tool/technique} は {limitation} が弱点
```

**Step 3.6: 次に取るべきアクション**
```markdown
## Recommendations for Your Next Project

{N} 件のレトロスペクティブから:

### Before Starting
1. {開始前アクション}
2. {別のアクション}

### During Execution
1. {進行中の調整}
2. {別の調整}

### Avoid These Pitfalls
1. {よくある失敗 + 回避策}
2. {別の失敗}

### Use These Resources
- Starter: `~/.sdd-knowledge/starters/{category}/` (v{version})
- Reference projects: {成功例の一覧}
- Time estimate: {X}h ± {Y}h
```

**Step 3.7: 矛盾 & 未解決事項（存在する場合）**
```markdown
## Needs Resolution

以下の lesson は矛盾している可能性があります:

### Contradiction 1
**Lesson A** ({from Project X}):
{lesson text}

**Lesson B** ({from Project Y}):
{lesson text}

**Possible reasons**:
- Context difference: {analysis}
- Evolution of approach: {analysis}

**Recommendation**: {解決 / 検証方法}
```

### フェーズ 4: インタラクティブ探索

**Step 4.1: 深掘りメニューを提示**
レポート表示後:
```
Lessons report complete.

Explore further:
  1. Show evidence for lesson #{N}
  2. Compare with {another category}
  3. See projects where lesson #{N} applied
  4. Export to file
  5. Done

Choice [5]:
```

**Step 4.2: 深掘りリクエストに対応**
```
If user selects "Show evidence for lesson #3":
  → Display full retrospectives for all projects with that lesson
  → Highlight relevant sections
  → Show before/after if applicable

If user selects "Compare with another category":
  → Run lessons for second category
  → Generate side-by-side comparison
  → Highlight unique vs shared lessons

If user selects "See projects where lesson applied":
  → List projects chronologically
  → Show if lesson was followed vs ignored
  → Correlate with satisfaction ratings
```

### フェーズ 5: エクスポート

**Step 5.1: レポートを保存**
保存確認:
```
Save this report?
  1. Yes, save to ./lessons-{category}-{date}.md
  2. Yes, and copy to project docs/
  3. No

Choice [1]:
```

**Step 5.2: init-task との統合**
```
For next project using {category}:
  /init-task will automatically reference these lessons.

Want to review {category} starter before starting?
  /show-starter {category}
```

## 品質ゲート（Quality Gates）

/lessons 完了前に確認:
- [ ] フィルタ範囲の全レトロスペクティブを読み込んだ
- [ ] lesson を重複排除し、クラスタリングした
- [ ] パターンを識別した（high-confidence / emerging）
- [ ] 実行可能な推奨アクション付きでレポート生成した
- [ ] インタラクティブな選択肢を提示した

## エラーハンドリング

**レトロスペクティブが見つからない:**
```
No retrospectives found for "{category}".

Options:
1. View all categories: /lessons
2. Create first project: /init-task
3. Import retrospectives from elsewhere

Choice:
```

**矛盾する lesson:**
```
Found {N} contradictory lessons.

These are noted in the "Needs Resolution" section.
Consider running more projects in {category} to clarify best approach.
```

**サマリーが古い:**
```
summary.json is outdated (last updated {days} ago).

Regenerate? [Y/n]
  (Will recalculate stats from all retrospective files)
```

## パフォーマンス最適化

**キャッシュ:**
- パース済みレトロスペクティブを 1 時間キャッシュ
- 集約したパターンをセッション中キャッシュ
- summary.json は必要時のみ再生成

**遅延読み込み（Lazy Loading）:**
- すべてではなく、フィルタ対象のみ読み込む
- カテゴリ分析はカテゴリ指定時のみ生成

**インデックス化:**
- quick stats 用に summary.json を維持
- カテゴリタグで高速フィルタ
- キーワードで検索できるよう lesson をインデックス

## ユースケース

**1. 新規プロジェクトを開始する前**
```bash
$ /lessons investigation-report --priority high --limit 5

# 調査レポートの high 優先度 lesson 上位 5 件を表示
# /init-task 前に確認する
```

**2. あるフェーズで詰まっているとき**
```bash
$ /lessons --search "Phase 2" --category investigation-report

# 調査レポートで Phase 2 に言及する lesson を表示
# よくある落とし穴を特定する
```

**3. 四半期レビュー**
```bash
$ /lessons --sort-by date --limit 20

# 全カテゴリの直近 20 件を表示
# チームでパターンと starter 更新を議論する
```

**4. カテゴリ比較**
```bash
$ /lessons investigation-report
$ /lessons technical-proposal

# 2回実行して比較
# カテゴリ固有 / 普遍的な lesson を見分ける
```

## 統合ポイント（Integration Points）
- **前提**: 少なくとも1回 `/retrospective` を完了していること
- **連携先**: `/init-task`（自動的に参照される）
- **参照元**: `~/.sdd-knowledge/retrospectives/*.json`
- **更新**: なし（読み取り専用）

## 将来拡張（Future Enhancements）
- [ ] 自然言語クエリ: `"/lessons for projects about data analysis"`
- [ ] 可視化: lesson の頻度推移チャート
- [ ] チーム集約: 複数メンバーの lesson を統合
- [ ] 信頼度スコア: 満足度で重み付け
- [ ] 自動サジェスト: 「このクエリなら、こちらも見ると良い」
