# Emotion Context Hourly Buffer

## 使う場面
- emotion context の時系列が session 単位に引っ張られて見える時
- plugin resolve / on-demand build / cron build の役割分担を直したい時
- `MEMORY_EMOTION_BUFFER.json` を導入・改修・検証する時

## ねらい
emotion context は、毎回 DB 全体を見直して再解釈するより、**1時間ごとに新規会話だけを追加する当日 buffer** を正本にした方が、人間の「今日の流れ」に近い。

## canonical 配線
1. hourly cron が `build-memory-context.py --refresh-emotion-buffer` を実行する
2. その時だけ `lin-memory-session-sync.py collect --after-id <last_message_id>` 相当で**新規 message**を取る
3. `MEMORY_EMOTION_BUFFER.json` に追記する
4. emotion snapshot (`MEMORY_EMOTIONS_CONTEXT.md`) は、**その buffer の中だけ**から組み立てる
5. on-demand build / plugin resolve は **buffer を読むだけ**で、collector を追加実行しない

## day boundary
- 日付境界は JST 4:00
- `operational_day` が変わったら buffer をリセットする
- `00:00〜03:59` の会話は、見た目のカレンダー日付ではなく前日の buffer に属する

## buffer に入れないもの
- same-session heartbeat の内部文
- `HEARTBEAT_OK` / `HEARTBEAT_OFF`
- heartbeat 専用 session title（例: `Heartbeat Session Check`, `Conversation Resumption Greeting`）
- context compaction 断片

ポイントは、**emotion context に入れたいのは人間との会話であって、システムの脈拍ではない**こと。

## 実装メモ
- buffer は少なくとも次を持つと追跡しやすい
  - `operational_day`
  - `updated_at`
  - `last_message_id`
  - `message_count`
  - `collect_scan`
  - `messages`
- on-demand build でも markdown / debug 出力は再生成してよいが、buffer の材料集合そのものは増やさない
- summary 数字は event 側 scan と emotion 側 scan を混同しない

## 検証
- `--refresh-emotion-buffer` ありで buffer の `message_count` / `last_message_id` が進む
- `--refresh-emotion-buffer` なしでは buffer が増えない
- buffer 内に heartbeat 内製ログが入っていない
- `MEMORY_EMOTIONS_CONTEXT.md` 冒頭に buffer metadata が見える
- 4:00 跨ぎの次回実行で `operational_day` が切り替わり、前日の messages が消える

## permission 回復の扱い
既存 snapshot ファイルだけ別所有者で残ることがある。state dir に書けるなら、`PermissionError` 時に **unlink → 再作成** で回復できるようにしておくと、runtime 由来の所有権残骸に強い。
