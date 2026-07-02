# /update-docs

docs/ 配下のドキュメントを対話的に充実させます。

**詳細な手順は `.claude/skills/update-docs/SKILL.md` に定義されています。**
そのSKILL.mdに従って、以下を実行してください：

1. docs/ 配下の全ファイル読み込みと充実度診断
2. 未解決マーカー（TODO, 要確認 等）の洗い出し
3. skills/ が期待する情報との整合チェック
4. 優先度付きの改善提案
5. ユーザーとの対話による段階的充実化

引数: $ARGUMENTS（`{ファイル名}`, `gaps`, `validate`, 空=全体診断）

実行前に `.claude/skills/update-docs/SKILL.md` を必ず読み込んでください。
