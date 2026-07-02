# retrospective - 構造化プロジェクト振り返り＆学びの蓄積

## 目的
完了したプロジェクトから、次回に活かせる「再現可能な学び」を抽出し、将来のパターン認識（ナレッジ化／自動改善）に使えるよう**機械可読な形式**で保存するための、構造化レトロスペクティブ（振り返り）を行う。

## 前提条件
- `/finalize` でプロジェクトを完了している（または完了間近）
- `outputs/` ディレクトリが存在し、成果物が格納されている
-（Validator を使った場合）検証レポートが存在する
-（`/finalize` を実行した場合）最終化レポートが存在する

## 入力
- 任意：注目領域（例：「プロセス」「ツール」「コンテンツ」）
- 任意：過去の類似プロジェクトとの比較

## 出力
- `./retrospective.md`：人が読める振り返り（Markdown）
- `~/.sdd-knowledge/retrospectives/{date}_{category}_{name}.json`：構造化データ（JSON）
- 更新：`~/.sdd-knowledge/retrospectives/summary.json`（集計統計）

## ワークフロー

### Phase 0：コンテキスト収集

**Step 0.1：プロジェクトデータを読み込む**
```bash
Read:
  - metadata.json（プロジェクトメタデータ、フェーズ統計）
  - CLAUDE.md（元の目的／ゴール）
  - finalization-report.md（存在すれば：暫定の学び）
  - outputs/phase-*/  validation/（検証で出た問題）
  - docs/（仕様ファイル群）
```

**Step 0.2：メトリクスを算出する**
```python
time_metrics = {
    "total_hours": sum(phase["duration"] for phase in phases),
    "estimated_hours": metadata["estimated_hours"],
    "variance_percent": ((actual - estimated) / estimated) * 100,
    "phases": [
        {
            "phase": N,
            "estimated": X,
            "actual": Y,
            "variance": Y - X
        }
    ]
}

quality_metrics = {
    "validation_runs": count_validation_reports(),
    "revision_cycles": count_builder_iterations(),
    "critical_issues": count_critical_validation_issues(),
    "user_manual_fixes": count_manual_commits()  # git が使える場合
}

content_metrics = {
    "docs_files_created": len(docs_files),
    "docs_files_used": count_referenced_in_validations(docs_files),
    "deliverables_count": count_output_files(),
    "total_words": estimate_word_count(outputs)
}
```

### Phase 1：対話型の振り返り

**Step 1.1：オープンエンド質問**
ユーザーに（1つずつ）会話調で質問する：

```
1. 「このプロジェクトで、想定以上にうまくいったことは何でしたか？」
   → 期待する観点：成功パターン、嬉しい誤算、時間短縮要因

2. 「想定より時間がかかった／難しかったことは何でしたか？」
   → 期待する観点：痛点、要件の曖昧さ、ツールの限界

3. 「明日もう一度このプロジェクトを最初からやるなら、何を変えますか？」
   → 期待する観点：プロセス改善、事前準備の不足

4. 「docs/ の仕様は十分でしたか？不足・不明瞭な点はありましたか？」
   → 期待する観点：仕様の抜け、過剰仕様の箇所

5. 「SKILL.md の手順は効果的でしたか？曖昧すぎ／厳格すぎでしたか？」
   → 期待する観点：スキル改善ポイント

6. 「Builder/Validator パターンは、見落としそうな問題を拾えましたか？」
   → 期待する観点：検証の有効性、誤検知（false positive）

7. 「最終成果物への満足度を 1〜5 で評価してください」
   → 定量データ点
```

**Step 1.2：メトリクスに基づくガイド付き分析**
算出した結果を提示し、背景を質問する：

```
時間分析:
  - Phase 2 が見積より 40% 長い（3h vs 2.1h）
  → 「Phase 2 の遅れの要因は何でしたか？」

品質分析:
  - Validator が 7 件検出、うち 3 件が critical
  → 「これらは振り返ると明らかでしたか？それとも本当に見つけにくい問題でしたか？」

コンテンツ分析:
  - docs/competitor-analysis.md が validation レポートで 0 回参照
  → 「このファイルは不要でしたか？それともチェック項目に入っていなかっただけですか？」
```

**Step 1.3：カテゴリ別の追加質問**
プロジェクトカテゴリに応じて、狙い撃ちの質問を追加する：

**investigation-report（調査レポート）の場合**
```
- 情報源は事前に整理できていましたか？
- 予想外に追加調査が必要になりましたか？
- 出力フォーマットは開始前に明確でしたか？
```

**technical-proposal（技術提案）の場合**
```
- ステークホルダーのニーズは明確でしたか？
- 途中で要件変更はありましたか？
- 技術的な深さは対象読者に対して適切でしたか？
```

**network-design（ネットワーク設計）の場合**
```
- 制約（予算、既存インフラ）は十分に明記されていましたか？
- 仮定（assumption）が必要でしたか？文書化できましたか？
- すべての要件に対して設計を検証できましたか？
```

### Phase 2：パターン抽出

**Step 2.1：繰り返しテーマを同定する**
ユーザー回答からパターンを検出する：

```python
# 検出したいテーマ例
themes = {
    "spec_insufficient": [
        "docs が足りない", "docs に欠けていた", "要件が不明確",
        "最初に仕様化すべきだった"
    ],
    "skill_too_vague": [
        "手順が不明確", "どうすればいいかわからなかった", "例が必要だった"
    ],
    "skill_too_rigid": [
        "逸脱せざるを得なかった", "手順が合わない", "柔軟性が必要だった"
    ],
    "validation_valuable": [
        "問題を拾った", "見落としたはず", "ミスを防げた"
    ],
    "time_underestimated": [
        "時間がかかった", "想定以上に複雑", "予想外に難しい"
    ],
    "time_overestimated": [
        "早く終わった", "想定より簡単", "計画過多だった"
    ]
}

# 具体例を抽出する
extract_quotes = True  # ユーザー回答から具体フレーズを抜き出す
```

**Step 2.2：学びをカテゴリ分けする**
抽出した学びを「バケット」に分類する：

```json
{
  "lessons": {
    "process": [
      "Phase 2 はチェックポイントを細分化して、早期に問題を検出できるようにすべき"
    ],
    "specification": [
      "docs/ に比較表の出力例フォーマットを含めるべき"
    ],
    "skills": [
      "phase-01 の SKILL.md に、情報源の妥当性検証ステップを明示すべき"
    ],
    "tools": [
      "Builder が複雑な表整形に苦戦し、手動修正が必要だった"
    ],
    "category_specific": [
      "調査レポートでは、情報源の信頼性チェックリストが有効"
    ]
  }
}
```

**Step 2.3：docs/ の有効性を評価する**
docs/ 配下の各ファイルについて：
```python
assessment = {
    "filename": "background.md",
    "status": "sufficient" | "insufficient" | "unnecessary",
    "evidence": {
        "referenced_in_phases": [1, 2],
        "validation_mentions": 3,
        "user_feedback": "文脈整理に役立った"
    },
    "recommendation": "Keep as-is" | "Expand to include X" | "Remove"
}
```

**Step 2.4：skills/ の有効性を評価する**
各フェーズの SKILL.md について：
```python
assessment = {
    "phase": 2,
    "followed_procedure": True | False,
    "deviation_reason": "競合価格比較ステップを追加する必要があった",
    "effectiveness": "high" | "medium" | "low",
    "improvement_suggestions": [
        "比較表の明示的な形式例を追加",
        "データ収集後の検証チェックポイントを追加"
    ],
    "builder_iterations": 2,  # >1 なら手順の明確化が必要かも
    "validator_caught_issues": 3  # 品質基準の有効性
}
```

### Phase 3：構造化データ生成

**Step 3.1：JSON レコードを作成する**
`~/.sdd-knowledge/retrospectives/{date}_{category}_{name}.json` を生成する：

```json
{
  "metadata": {
    "date": "2026-02-05",
    "project_name": "WebAssembly Framework Evaluation",
    "category": "investigation-report",
    "duration_hours": 8.5,
    "estimated_hours": 6.0,
    "phases": 3,
    "satisfaction_rating": 4
  },
  
  "time_analysis": {
    "total_variance_percent": 41.7,
    "phases": [
      {
        "phase": 1,
        "name": "Research & Analysis",
        "estimated_hours": 2.0,
        "actual_hours": 2.1,
        "variance_percent": 5.0,
        "notes": "On track"
      },
      {
        "phase": 2,
        "name": "Comparison & Evaluation",
        "estimated_hours": 2.0,
        "actual_hours": 3.4,
        "variance_percent": 70.0,
        "notes": "Competitor analysis was underspecified"
      },
      {
        "phase": 3,
        "name": "Report Generation",
        "estimated_hours": 2.0,
        "actual_hours": 3.0,
        "variance_percent": 50.0,
        "notes": "Formatting took longer than expected"
      }
    ]
  },
  
  "docs_assessment": {
    "files": [
      {
        "name": "background.md",
        "status": "sufficient",
        "referenced_in_phases": [1, 2, 3],
        "user_feedback": "Clear context, helped frame analysis"
      },
      {
        "name": "scope.md",
        "status": "sufficient",
        "referenced_in_phases": [1, 2],
        "user_feedback": "Boundaries were well-defined"
      },
      {
        "name": "sources.md",
        "status": "insufficient",
        "referenced_in_phases": [1],
        "user_feedback": "Lacked example citation format; caused inconsistency",
        "recommendation": "Add citation format examples"
      },
      {
        "name": "competitor-analysis.md",
        "status": "missing",
        "discovered_in_phase": 2,
        "user_feedback": "Should've been in docs/ from start",
        "recommendation": "Add to investigation-report starter"
      }
    ],
    "summary": {
      "sufficient": 2,
      "insufficient": 1,
      "unnecessary": 0,
      "missing": 1
    }
  },
  
  "skills_assessment": {
    "phases": [
      {
        "phase": 1,
        "effectiveness": "high",
        "followed_exactly": true,
        "builder_iterations": 1,
        "validator_issues": 1,
        "user_feedback": "Clear procedure, easy to follow"
      },
      {
        "phase": 2,
        "effectiveness": "medium",
        "followed_exactly": false,
        "deviation_reason": "Needed to add competitor pricing comparison",
        "builder_iterations": 2,
        "validator_issues": 5,
        "user_feedback": "Too vague on comparison methodology",
        "improvement_suggestions": [
          "Specify comparison criteria upfront",
          "Provide table format template",
          "Add step: validate data source credibility"
        ]
      },
      {
        "phase": 3,
        "effectiveness": "high",
        "followed_exactly": true,
        "builder_iterations": 1,
        "validator_issues": 2,
        "user_feedback": "Report structure was solid"
      }
    ],
    "summary": {
      "effective_phases": 2,
      "needs_improvement": 1
    }
  },
  
  "validation_effectiveness": {
    "total_validator_runs": 3,
    "issues_caught": {
      "critical": 3,
      "suggestions": 5
    },
    "false_positives": 0,
    "user_perception": "valuable",
    "notes": "Caught missing competitor pricing and inconsistent citations"
  },
  
  "user_feedback": {
    "went_well": [
      "Initial research phase was efficient",
      "Report structure matched expectations",
      "Validator caught issues I would've missed"
    ],
    "challenges": [
      "Comparison methodology took iteration to get right",
      "Source citation format wasn't standardized upfront",
      "Table formatting required manual adjustment"
    ],
    "would_do_differently": [
      "Define comparison criteria in docs/ before Phase 2",
      "Include citation examples in sources.md",
      "Request table format template in SKILL.md"
    ]
  },
  
  "lessons_learned": [
    {
      "category": "specification",
      "lesson": "Investigation reports need explicit comparison criteria in docs/",
      "evidence": "Phase 2 required 2 iterations due to unclear methodology",
      "applicability": "investigation-report",
      "priority": "high"
    },
    {
      "category": "specification",
      "lesson": "sources.md should include citation format examples",
      "evidence": "Validator caught inconsistent citations across 3 deliverables",
      "applicability": "investigation-report",
      "priority": "medium"
    },
    {
      "category": "skills",
      "lesson": "Phase 2 SKILL.md needs table format template",
      "evidence": "Manual formatting took 0.5h; could be avoided with template",
      "applicability": "any project with comparison tables",
      "priority": "medium"
    },
    {
      "category": "process",
      "lesson": "Competitor analysis warrants its own docs/ file",
      "evidence": "Discovered need mid-project; caused scope creep",
      "applicability": "investigation-report",
      "priority": "high"
    },
    {
      "category": "tools",
      "lesson": "Builder/Validator split is valuable for quality",
      "evidence": "Caught 3 critical issues (missing requirements) before user review",
      "applicability": "all projects",
      "priority": "high"
    }
  ],
  
  "tags": [
    "investigation-report",
    "comparison-heavy",
    "data-sourcing",
    "technical-analysis"
  ],
  
  "next_project_recommendations": [
    "Use updated investigation-report starter with competitor-analysis.md",
    "Review ~/.sdd-knowledge/starters/investigation-report for latest patterns",
    "Consider adding more time buffer for comparison-heavy phases"
  ]
}
```

> 注：上記 JSON 内の英語テキスト（例：`notes` や `lesson`）は、そのままでも問題ありませんが、運用上は**日本語に寄せた方がチーム共有しやすい**場合があります。プロジェクト方針に合わせて統一してください。

**Step 3.2：サマリーを更新する**
`~/.sdd-knowledge/retrospectives/summary.json` に追記する：
```json
{
  "total_projects": 5,
  "categories": {
    "investigation-report": {
      "count": 2,
      "avg_duration": 7.75,
      "avg_satisfaction": 4.0,
      "common_issues": [
        "Comparison criteria underspecified (2 occurrences)",
        "Citation format unclear (2 occurrences)"
      ]
    },
    ...
  },
  "lessons_by_priority": {
    "high": 12,
    "medium": 18,
    "low": 5
  },
  "last_updated": "2026-02-05T10:30:00Z"
}
```

### Phase 4：人間が読めるレポート

**Step 4.1：retrospective.md を生成する**
`./retrospective.md` を作成する：
```markdown
# Retrospective: WebAssembly Framework Evaluation

**Date**: February 5, 2026  
**Category**: Investigation Report  
**Duration**: 8.5 hours (estimated: 6.0 hours)  
**Satisfaction**: 4/5  

## What Went Well ✓

- **Efficient research phase**: Phase 1 completed on schedule with clear methodology
- **Strong report structure**: Phase 3's output matched expectations without major revisions
- **Effective validation**: Builder/Validator pattern caught 3 critical issues before user review

## Challenges & Learnings ⚠

### Specification Gaps
- **Comparison criteria**: Phase 2 methodology was unclear, leading to 2 revision cycles
  - *Lesson*: Define comparison dimensions in docs/ upfront
  - *Action*: Add comparison-criteria.md to investigation-report starter

- **Citation format**: sources.md lacked examples, causing inconsistent formatting
  - *Lesson*: Include citation examples for consistency
  - *Action*: Update sources.md template with format examples

### Process Improvements
- **Missing docs/ file**: Competitor analysis scope emerged mid-project
  - *Lesson*: For investigation reports, competitor context deserves its own spec file
  - *Action*: Add competitor-analysis.md to starter

### Skill Refinements
- **Phase 2 SKILL.md**: Procedure was too abstract for comparison tasks
  - *Suggestion*: Include table format template
  - *Suggestion*: Add explicit step for validating data sources
  - *Action*: Update investigation-report/phase-02 SKILL.md

## Time Analysis

| Phase | Estimated | Actual | Variance | Notes |
|-------|-----------|--------|----------|-------|
| 1: Research | 2.0h | 2.1h | +5% | On track |
| 2: Comparison | 2.0h | 3.4h | +70% | Methodology iteration |
| 3: Report | 2.0h | 3.0h | +50% | Formatting adjustments |
| **Total** | **6.0h** | **8.5h** | **+42%** | |

### Variance Drivers
- Comparison methodology took 2 iterations (1.0h)
- Table formatting manual adjustment (0.5h)
- Expanded competitor analysis scope (1.0h)

## Validation Effectiveness

**Builder/Validator Pattern**:
- Validator runs: 3
- Issues caught: 8 (3 critical, 5 suggestions)
- False positives: 0
- User assessment: Valuable

**Critical Issues Caught**:
1. Missing competitor pricing comparison
2. Inconsistent citation format across 3 deliverables
3. Incomplete data source validation

## docs/ Assessment

| File | Status | Referenced | Feedback |
|------|--------|------------|----------|
| background.md | ✓ Sufficient | Phases 1,2,3 | Clear context |
| scope.md | ✓ Sufficient | Phases 1,2 | Well-defined boundaries |
| sources.md | ⚠ Insufficient | Phase 1 | Lacked citation examples |
| competitor-analysis.md | ✗ Missing | (added in Phase 2) | Should've been upfront |

## skills/ Assessment

| Phase | Effectiveness | Issues | Improvement Suggestions |
|-------|---------------|--------|-------------------------|
| 1: Research | High | 1 minor | (none) |
| 2: Comparison | Medium | 5 (2 critical) | Add criteria template, data validation step |
| 3: Report | High | 2 minor | (none) |

## Lessons for Next Time

### High Priority
1. **Comparison criteria upfront**: For investigation reports, define comparison dimensions in docs/ before Phase 2
2. **Competitor analysis file**: Add competitor-analysis.md to investigation-report starter
3. **Validation pattern**: Continue using Builder/Validator split; caught critical issues

### Medium Priority
4. **Citation examples**: Include in sources.md template
5. **Table templates**: Add to phase-02 SKILL.md for comparison phases
6. **Time buffers**: Add 30-40% buffer for comparison-heavy investigations

### Applied to Starters
The following updates were automatically applied to `~/.sdd-knowledge/starters/investigation-report/`:
- Added: docs-template/competitor-analysis.md
- Updated: docs-template/sources.md (added citation examples)
- Updated: skills/phase-02/SKILL.md (added comparison criteria checklist)

## Starter Evolution
- **Version**: 1 → 2
- **Confidence**: 0.5 → 0.65
- **Based on projects**: 1 → 2

Next investigation-report project will benefit from these improvements automatically.

---

**Full structured data**: ~/.sdd-knowledge/retrospectives/2026-02-05_investigation_WebAssembly.json

**Review accumulated lessons**: `/lessons investigation-report`
```

> 補足：上記のサンプル `retrospective.md` は英語ですが、テンプレとしては有用です。必要なら同様に日本語版テンプレに置き換えてください。

### Phase 5：統合＆完了確認

**Step 5.1：過去振り返りとの突合**
```
過去のレトロスペクティブと比較する:
  - この学びは新規か、再発パターンか？
  - 再発（3回以上）なら → パターンとしてフラグ付け
  - 過去の学びと矛盾するなら → レビュー対象として強調
```

**Step 5.2：knowledge-curator による改善候補生成**
レトロスペクティブ JSON が保存された後、knowledge-curator を起動してコンポーネントの改善候補を生成する:

```bash
python3 scripts/knowledge_curator.py \
  ~/.sdd-knowledge/retrospectives/{date}_{category}_{name}.json \
  --kb-dir ~/.sdd-knowledge
```

実行結果をユーザーに提示:
```
knowledge-curator 結果:
  処理対象: {retrospective_file}
  改善候補: {N} 件生成 → candidates.jsonl に追記済み

  候補一覧:
    - [{priority}] {component_id}: {lesson_description}
    ...
```

> このステップにより、レトロスペクティブの教訓がコンポーネントの tags, quality_criteria, effectiveness に反映される候補として蓄積される。

**Step 5.3：スターター更新（/finalize 内で未実施なら）**
`/finalize` が未実行なら、いま適用する提案を行う：
```
この振り返りで、{N} 件の改善を investigation-report スターターへ適用できます。

今適用しますか？ [Y/n]
  （~/.sdd-knowledge/starters/investigation-report/ を更新します）
```

**Step 5.4：完了**
```
✓ 振り返り完了

記録:
  - ./retrospective.md（人間可読）
  - ~/.sdd-knowledge/retrospectives/{date}_{category}_{name}.json（構造化）
  - summary 更新済み

抽出した学び: {N}
  High priority: {N}
  Medium priority: {N}
  Low priority: {N}

すべての学びを見る:
  /lessons {category}
```

## 品質ゲート（Quality Gates）

振り返り完了前に確認：
- [ ] すべての振り返り質問に回答済み（または明示的にスキップ）
- [ ] プロジェクトデータからメトリクス算出済み
- [ ] 学びをカテゴリ分けし、優先度付け済み
- [ ] JSON レコードが正しいスキーマで作成済み
- [ ] Markdown レポート（retrospective.md）を生成済み
- [ ] summary.json を更新済み

## エラーハンドリング

**データ不足**
- 検証レポートがない → JSON に `"validation_effectiveness": null` として記録
- 見積時間がない → フェーズ数 * 2h を暫定値として使う
- 最終化レポートがない → 暫定の学びなしで進める

**ユーザーの関与が薄い**
- 回答が短い → 追加の深掘り質問を入れる
- スキップしたい → 取れる情報だけで生成する
- 部分的に保存して、後で再開できるようにする

## パフォーマンス目安
- 対話型振り返り：5〜15分（ユーザー次第）
- データ処理：1分未満
- レポート生成：1分未満

## 連携ポイント（Integration Points）
- **前提**：`/finalize`（推奨、必須ではない）
- **参照元**：`/lessons`（retrospectives/*.json を読む）
- **更新対象**：スターター（検出パターンにより更新）

## 将来拡張（Future Enhancements）
- [ ] 類似プロジェクト比較：「8.5h。カテゴリ平均は 7.2h」
- [ ] トレンド分析：「調査レポートが速くなっている」
- [ ] チーム集計：メンバー横断でレトロスペクティブを統合
- [ ] チーム Wiki / Notion へエクスポート
