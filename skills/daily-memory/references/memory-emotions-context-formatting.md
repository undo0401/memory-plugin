# MEMORY_EMOTIONS_CONTEXT の整形方針

## 使う場面
- `/opt/data/scripts/memory/build-memory-context.py` で `MEMORY_EMOTIONS_CONTEXT.md` の見え方を調整する時
- emotion context を『ログ一覧』ではなく『感情の断片』として薄く保ちたい時

## canonical ルール
- `MEMORY_EMOTIONS_CONTEXT` では、各メッセージの本文だけを残す
- 次は出さない
  - session title
  - `#19` みたいな番号
  - 時刻
  - role (`assistant:` / `user:`)
  - `total_score`
- メッセージ間の**空行区切りだけ**は残して、境界を保つ

## 実装修理の勘所
`/opt/data/scripts/memory/build-memory-context.py` では少なくとも次を見る。

- `message_heading()`
- `_render_message_lines()`
- `render_emotion_snapshot_markdown()`

今回の正本 shape は、`_render_message_lines()` が本文だけを返す形だよ。見出しや role ラベルを残すと、emotion context が『出典メタ情報の多いログ』へ戻りやすい。

## ねらい
- モデルが本文の余韻だけを拾いやすくする
- session title や番号に引っ張られないようにする
- 『会話ログ』より『感情の断片』として読ませる

## pitfall
- メタ情報を削りたい時でも、メッセージ間の空行まで消して塊を潰さない
- `MEMORY_EVENT_CONTEXT` まで同じ shape にするとは限らない。emotion context 専用の整形として考える
- score や role を backend に残すこと自体は問題ないが、`MEMORY_EMOTIONS_CONTEXT.md` の表示へ再露出させない
