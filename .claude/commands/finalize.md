# /finalize

SDDプロジェクトの完了処理を実行します。

**詳細な手順は `.claude/skills/finalize/SKILL.md` に定義されています。**
そのSKILL.mdに従って、以下を実行してください：

1. 完了チェック（全フェーズのステータス確認）
2. 成果物パッケージ化
3. `~/.sdd-knowledge/docs-archive/` へアーカイブ
4. スターターテンプレートの抽出・更新
5. `finalization-report.md` の生成
6. metadata.json を "finalized" に更新

引数: $ARGUMENTS（オプション: `--skip-archive`, `--skip-starter`, `--force`）

実行前に `.claude/skills/finalize/SKILL.md` を必ず読み込んでください。
