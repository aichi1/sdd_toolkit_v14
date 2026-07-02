# /improve-toolkit <iteration_id>

SDD toolkit 自身を（Aの意味で）改良し、同じ固定シナリオで評価して、改善が数値で示せる状態にしてください。

## 原則
- 改良は必ず「評価（/eval）」とセット。スコアが改善しない変更は採用しない。
- 壊れやすい箇所（.claude/settings.json、hooks）は差分を小さく。可能ならテストも追加。

## 手順
1. 改善テーマを1つに絞る（例：/init-task の質問削減、team-rosterの精度、README導線）
2. 変更案 → 実装（必要なら docs/ と templates/ を修正）
3. `eval/rubric.json` に照らして「どの軸が上がるか」仮説を明記
4. `/eval <iteration_id>` を実行して採点・履歴化
5. `eval/reports/<date>_<iteration_id>.md` に「変更内容」「結果」「次の課題」を記録
6. `docs/CHANGELOG.md` に変更点を追記

## 出力
- 変更ファイル一覧
- 影響範囲
- 改善が示されたスコア（前回比較）
- 次の改善候補（最大3つ）
