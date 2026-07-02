# /run-phase

Builder / Validator パターンでSDDプロジェクトのフェーズを実行します。

**詳細な手順は `.claude/skills/run-phase/SKILL.md` に定義されています。**
そのSKILL.mdに従って、以下を実行してください：

1. 環境チェック（docs/, skills/, CLAUDE.md, metadata.json の存在確認）
2. 依存関係バリデーション（前フェーズの完了確認）
3. Builder エージェント実行（SKILL.md の手順に従い成果物を生成）
4. Validator エージェント実行（docs/ と SKILL.md の要件照合・検証レポート作成）
5. 修正ループ（NEEDS_REVISION なら最大2回まで自動修正）
6. 完了処理（metadata.json 更新・次アクション提示）

引数: $ARGUMENTS（フェーズ番号: `1`, `1-3`, `all`）

実行前に `.claude/skills/run-phase/SKILL.md` を必ず読み込んでください。
