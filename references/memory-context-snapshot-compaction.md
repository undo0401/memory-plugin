# memory snapshots compaction

21:00 / 02:00 の memory 更新用に、会話履歴だけを state artifact として前計算した時の圧縮ルール。

## 目的
- memory 更新 cron の入力を安定させる
- 毎回広い探索をせず、1時間おきに `/opt/data/state/` へ snapshot を置く
- ただし artifact を太らせすぎない

## このユーザー運用での shape
- conversation-only JSON にする
- `days.today` / `days.yesterday` に分ける
- 各 day の中は `sessions[]`
- 各 session は次だけ持つ
  - `session_id`
  - `session_title`
  - `messages[]`
- 各 message は次だけ持つ
  - `role`
  - `time`
  - `content`

## 圧縮ルール
1. user 発話は全部残す
2. assistant 発話は連続 run ごとに圧縮する
   - 次に user が来る run では、**その user の直前の assistant を1件だけ残す**
   - session 末尾で assistant run が終わる時は、**最後の短い一言より情報量の多い返答を優先**して1件だけ残す
3. Discord / gateway 由来で user message に `[Recent channel messages]` と `[New message]` が両方入る時は、**`[New message]` 側だけを残す**
4. 1 message の中で **完全一致の段落重複** があれば、その重複だけを落とす
5. event message は **100字 cap**、emotion message は **low 300字 / medium 500字 / high は cap なし** にする。超えたら `… [truncated]` を付ける
6. `yesterday` bucket は **前日 12:00 JST 以降**だけ残す
7. 同文重複は session_id × role × content ベースで落とす
8. 次のようなシステム都合のノイズは落とす
   - context compaction の長文メタ文
   - active task list preserved 系の注入文
9. per-message の `id` は出力しない

## なぜこの形か
- message ごとに `session_id` / `session_title` を持たせると無駄が大きい
- assistant の途中送信を雰囲気判定で消すより、会話順の run 圧縮の方が再現性がある
- memory 更新で欲しいのは内部進捗ではなく、各 user ターンに対して最終的に何を返したかの骨格

## 実装メモ
- まずノイズ文を除外
- 次に重複除去
- そのあと assistant run 圧縮
- 最後に session grouping

この順番の方が、同文重複や途中送信の残り方が安定しやすい。