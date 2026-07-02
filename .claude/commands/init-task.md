# /init-task（v6）

SDDプロジェクトを初期化します。

**詳細な手順は `.claude/skills/init-task/SKILL.md` に定義されています。**
そのSKILL.mdに従って、以下を実行してください：

1. タスク分類（task_type の判定）
2. docs/ 生成（requirements.md, plan.md, team.md, _manifest.json + カテゴリ固有ファイル）
3. skills/phase-{N}/SKILL.md 作成
4. 専門家エージェント召喚（templates/team-roster.json → .claude/agents/generated/）
5. CLAUDE.md, metadata.json 作成
6. ユーザーへの案内（次のコマンド提示）

実行前に `.claude/skills/init-task/SKILL.md` を必ず読み込んでください。
