# Self-Improvement (A): このツールキットが自分を改良する

このSDD toolkitの「自己改善」は、モデルの重みを更新するのではなく、
次を改善対象とします。

- コマンド（.claude/commands）
- ルール（.claude/rules）
- スキル（.claude/skills）
- フック/設定（.claude/settings.json, hooks scripts）
- テンプレ（templates/）
- 評価（eval/）

## 1サイクルの標準手順
1. `/improve-toolkit` で改善観点を明確化
2. 小さく変更して整合を取る
3. `/eval <iteration_id>` → `eval/history` と `eval/summary.csv` 更新
4. `eval/reports/<iteration_id>.md` に変更点とスコア差分を記録
5. 悪化した軸があれば、理由と次の打ち手を明記

## ガードレール
- 変更は小さく、影響範囲を明記する
- `.claude/settings.json` / hooks は差分を最小化
- 可能ならテスト（最低1つ）を追加する
- 必ず `eval/` の固定3シナリオで評価し、スコアが改善しない変更は採用しない

## 限界
- 重み更新はできない（振る舞い改善はプロンプト/構造/ルールで実現）
- 評価軸に過適合しないよう、定期的にシナリオ/チェックリストを見直す
