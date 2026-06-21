# Emotion config single source of truth

## 使う場面
- `MEMORY_EMOTIONS_CONTEXT.md` / `MEMORY_EMOTIONS_DEBUG.json` に、TOML に無い keyword が出た時
- emotion 抽出条件の変更後に、古い重みや語がまだ効いているように見える時
- `build-memory-context.py` を触って、config の責務境界を確認したい時

## 原則
- emotion 抽出条件の唯一の正本は **`/opt/data/config/MEMORY_EMOTIONS_CONFIG.toml`**
- ここでいう条件には、少なくとも次を含める
  - day boundary (`yesterday_start_hour`)
  - recent window の扱い
  - `target_roles`
  - `meta_markers`
  - `max_distinct_keywords_per_message`
  - `[level_thresholds]`
  - `[session_filters]`
  - `[keywords.*]`
- `build-memory-context.py` に同等の fallback default や埋め込み keyword 群を残さない

## ありがちな誤認
### 1. `TOML に無い keyword が抽出された気がする`
まず次を分けて見る。

- **いまの生成物に本当に出ているか**
  - `MEMORY_EMOTIONS_DEBUG.json` の `days.today.keyword_hits` / `days.yesterday.keyword_hits` を見る
- **過去ログや tool 出力の引用を見ているだけではないか**
  - session DB には、過去に生成した `MEMORY_EMOTIONS_CONTEXT.md` の断片が tool message として残る
  - そのため、検索語に昔の keyword が引っかかっても、現行ロジックの出力とは限らない
- **TOML の現値にその keyword が存在するか**
  - `[keywords.emotion]` を直接見る

### 2. header の時刻が message 本体と合わない
- `today_preferred` の見出し時刻と、引用されている本文 message の時刻がズレることがある
- これは session 単位の見出し時刻と、preferred に入った個別 message の時刻を混同している可能性がある
- 本当に日付バケットが壊れているかの確認は、**本文 message 自体の time** を先に見る

## 切り分けの順番
1. `MEMORY_EMOTIONS_CONFIG.toml` に keyword があるか確認する
2. `MEMORY_EMOTIONS_DEBUG.json` の `keyword_hits` にその keyword があるか見る
3. 無ければ、会話ログや tool message に**古い snapshot 断片**が混ざっていないか疑う
4. あるのに TOML に無ければ、script 側の埋め込み既定値・fallback・merge ロジックを疑う
5. day 境界の違和感は、session_id ではなく message timestamp で確認する

## 実務メモ
- `MEMORY_EMOTIONS_DEBUG.json` は keyword ごとの `hit_count`, `message_count`, `tag_score_total`, `level_counts`, `sample_messages` を返すので、ノイズ語の発見に向く
- user が「この語は抽出対象じゃない」と言ったら、skill / memory ではなく、まず **TOML 正本にその語があるか** を確認する
- 修正後は、必ず snapshot を再生成して debug JSON まで見直す
