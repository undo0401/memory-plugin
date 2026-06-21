# emotion context refresh and selection

## いつ使うか
- `MEMORY_EMOTIONS_CONTEXT.md` の上位候補が会話感とズレて見える時
- 設定変更が「再起動しないと反映されない」ように見える時
- memory / heartbeat / daily memory のどこで stale になっているか切り分けたい時

## まず切り分けること
1. **生成の問題か、読込配線の問題かを分ける**
   - `build-memory-context.py` を直接実行して snapshot 自体が更新されるか見る
   - その後、実際の consumer が `MEMORY_EMOTIONS_CONTEXT.md` を参照しているか config / lane / prompt を確認する
2. **再起動待ちではなく cron 待ちのことがある**
   - 「反映されない」は gateway 再起動必須ではなく、単に hourly rebuild 待ちのことがある
3. **現在の lane が本当にその snapshot を読んでいるか確認する**
   - `STATUS.md` だけを読んでいる lane なら、emotion snapshot を更新しても session-open 注入には乗らない

## 今回の durable pitfall
- `preferred` を score 順で見たいのに、sort key が level や session 順に引っぱられると、期待と違う候補が前に出る
- だから candidate ロジックを見る時は、
  - `preferred_messages` の抽出条件
  - score の計算方法
  - 最終 sort key
  を必ずセットで確認する

## 良かった修正パターン
- managed snapshot を読む resolve 経路の直前で `build-memory-context.py` を on-demand 実行する
- これで new session / fresh reset / auto reset の first turn に最新 snapshot を使いやすくなる
- ただし **consumer 側 config がその snapshot を参照していること** が前提

## 確認ポイント
- `build-memory-context.py --stdout summary` が成功するか
- `MEMORY_EMOTIONS_CONTEXT.md` の `today_preferred` / `yesterday_preferred` の先頭候補
- `preferred_score_total` と、上位10件が score 順に並んでいるか
- 実際に読んでいる lane / config の `snapshot_files`

## ひとことで
- 「再起動が必要そう」に見えたら、まず **stale build / cron 待ち / 未配線** を疑う
- 「候補が変」に見えたら、まず **score の sort key や表示ヘッダが誤解を生んでいないか** を疑う
