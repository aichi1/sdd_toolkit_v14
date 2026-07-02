# /retrospective

SDDプロジェクトの構造化振り返りを実行し、学びを蓄積します。

**詳細な手順は `.claude/skills/retrospective/SKILL.md` に定義されています。**
そのSKILL.mdに従って、以下を実行してください：

1. プロジェクトデータ収集（metadata.json, 検証レポート, finalization-report.md）
2. ユーザーとの構造化対話（成功・課題・発見）
3. 教訓の抽出とパターン認識
4. `./retrospective.md`（人間用）の生成
5. `~/.sdd-knowledge/retrospectives/` へJSON保存（機械用）
6. `summary.json` の更新

引数: $ARGUMENTS（任意: 注目領域の指定）

実行前に `.claude/skills/retrospective/SKILL.md` を必ず読み込んでください。
