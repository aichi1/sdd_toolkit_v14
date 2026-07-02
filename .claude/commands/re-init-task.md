# /re-init-task

イテレーション完了後に、新しいイテレーションを開始します。

**詳細な手順は `.claude/skills/re-init-task/SKILL.md` に定義されています。**
そのSKILL.mdに従って、以下を実行してください：

1. 前提条件チェック（全フェーズが completed or completed_with_issues）
2. 既存 docs/ の読み込みと現状サマリー表示
3. 差分インテーク（新イテレーションの目標・追加機能・制約変更を質問）
4. docs/ の差分更新
5. 新フェーズの skills/phase-{N}/SKILL.md 作成
6. metadata.json の更新（iterations[] 追加、phase_count 更新）
7. iteration_history.md の更新
8. CLAUDE.md のフェーズ一覧更新

実行前に `.claude/skills/re-init-task/SKILL.md` を必ず読み込んでください。

## 利用例

```
# Iteration 1 完了後に新機能を追加する
/re-init-task

# 特定の目標を指定して開始する
/re-init-task LLMマッチング機能の追加
```

## 前提条件
- `/init-task` でプロジェクトが初期化済み
- 現在のイテレーションの全フェーズが完了（completed or completed_with_issues）
- metadata.json が存在し最新状態
