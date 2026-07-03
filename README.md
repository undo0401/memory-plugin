# memory plugin

`memory` plugin は、この workspace では **pre-call injection / memory snapshots の入口**をまとめて持つ場所だよ。

## canonical relation

- plugin runtime path: `/opt/data/plugins/memory/`
- これは project repo ではなく、runtime / extension surface として扱う
- source-like docs は runtime 側か workspace note 側へ寄せる

## release path

- auto deploy: 停止中
- runtime target: `/opt/data/plugins/memory/`
- tracked code の反映は必要時に host 上で手動 `git pull --ff-only` へ寄せる

## scope

この plugin 側で正本にするものは次の 2 系統。

1. **session-aware injection**
   - LLM call の直前に lane 判定して注入する
   - 内部 event や out-of-band ping では必要以上に膨らませない
   - lane 判定して `snapshot_files` を読む
   - 注入用 text を組み立てる

2. **memory snapshots contract**
   - `/opt/data/scripts/diaries/build-memory-context.py` が生成する
     - `/opt/data/state/MEMORY_EVENT_CONTEXT.md`
     - `/opt/data/state/MEMORY_EMOTIONS_CONTEXT.md`
   - plugin はこれらを読む側なので、snapshot の shape と期待順序もここで追う

## canonical files

- backend: `/opt/data/plugins/memory/dashboard/plugin_api.py`
- config: `/opt/data/plugins/memory/config/memory.json`
- runtime state: `/opt/data/plugins/memory/state/memory-runtime.json`
- snapshot builder: `/opt/data/scripts/diaries/build-memory-context.py`
- emotion config: `/opt/data/config/MEMORY_EMOTIONS_CONFIG.toml`
- emotion buffer: `/opt/data/state/MEMORY_EMOTION_BUFFER.json`
- retired sidecar note: `references/retired-lin-ops-project.md`
- surfaced bare skills:
  - `/opt/data/plugins/memory/skills/daily-memory/SKILL.md`
- discovery lane: `skills.external_dirs` に `/opt/data/plugins/memory/skills` を追加して bare `daily-memory` として拾わせる
- plugin register 側では `memory:daily-memory` も出し、**bare を canonical / namespaced を explicit load 用**として併用する

## session-aware injection

### config shape

```json
{
  "schema_version": 1,
  "description": "memory dashboard v3 config",
  "lanes": [
    {
      "name": "memory-1",
      "enabled": true,
      "include_current_time": true,
      "include_current_source": true,
      "include_session_gap": true,
      "reinject_interval_minutes": 0,
      "target_sessions": [],
      "target_channels": ["discord:#雑談"],
      "target_profiles": ["default"],
      "exclude_sessions": [],
      "exclude_channels": [],
      "exclude_profiles": [],
      "snapshot_files": ["/opt/data/state/STATUS.md"]
    }
  ]
}
```

### behavior

- lane selector の正本は `plugin_api.py`
- `target_channels` が入っている lane は channel 基準で評価する
- 空なら `target_sessions` を使う
- dashboard では `target type` と `scope`（全て / 対象 / 除外）を選び、その下の入力欄1つで selector を編集する。`scope=全て` または入力欄が空なら target/exclude は空配列になり、実質全て対象として扱う
- `target_profiles` / `exclude_profiles` で、現在の Hermes profile 名（例: `default`, `coder`）を絞り込む。`target_profiles` が空なら `default` に正規化する
- dashboard では `target profile` をドロップダウンで選び、保存時は `target_profiles: ["<profile>"]` として保持する
- gateway 側では再実装せず、helper を呼んで prepend するだけに保つ
- lane ごとに `include_current_time=true` を付けると、pre-call 注入に `current_time` / `timezone` を追加する
- lane ごとに `include_current_source=true` を付けると、pre-call 注入に現在の `platform` / `channel` を追加する
- 今日/昨日 daily memory を直接読むオプションは持たず、必要な短期文脈は `snapshot_files` 側の managed snapshot へ寄せる
- `reinject_interval_minutes` / `idle_seconds` は legacy config 互換用に残すが、dashboard からは編集しない
- LLM への memory context は、gateway の `_run_agent_inner` 直前で pre-call 注入する

## memory snapshots contract

### event context

`MEMORY_EVENT_CONTEXT.md` は、daily memory の `出来事` を書くための短い出来事断面を持つ。

- `days.today` / `days.yesterday` で分ける
- 各日付の中は session 単位
- 各 message は `role` / `time` / `content` を中心に保つ
- event 側本文は role を問わず char cap 100
- `[Recent channel messages]` と `[New message]` が両方ある時は、`[New message]` 側を優先する
- compaction / active task list みたいなシステム都合ノイズは落とす

圧縮ルールの詳細は `references/memory-context-snapshot-compaction.md` を見る。

### emotions context

`MEMORY_EMOTIONS_CONTEXT.md` は、daily memory の `LINの振り返り` や emotion context の候補を読むための主出力。

期待する shape:
- 感情タグ付き message
- 日別タグ要約
- `preferred_level`
- `preferred_sessions`

### ranking / ordering contract

`preferred_sessions` は次の意味で扱う。

- まず **high → medium → low** の順で読む
- 同じ level の中では `score` が高いものを先に見る
- 「上に出る候補」は recent ではなく、**preferred の強度順**であることを期待する

もし上位候補が関係なさそうに見えるなら、まず次を疑う。

1. `preferred_sessions` ではなく別の配列を描画していないか
2. preferred の抽出後に chronological sort へ戻っていないか
3. scope が広すぎて別チャット断面が混ざっていないか
4. `preferred_level` に合う message だけ拾ったあと、session へ戻す段で弱い断面が先頭化していないか

## emotion extraction scope

emotion 抽出の実行本体は `build-memory-context.py` で、条件の正本は `/opt/data/config/MEMORY_EMOTIONS_CONFIG.toml` に置く。

現在の emotion context は `/opt/data/state/MEMORY_EMOTION_BUFFER.json` を唯一の材料バッファとして使う。hourly 実行だけが `--refresh-emotion-buffer` 付きで **新規会話を追記**し、on-demand 実行は **保存済み buffer だけ**を読んで `MEMORY_EMOTIONS_CONTEXT.md` を再生成する。buffer は JST 0:00 をまたいだらリセットされ、その当日ぶんだけで emotion context を組み立てる。

既定の読み方:
- 既定 scope は **Discord 全チャット横断**
- 基礎条件は `sessions.source='discord'`
- channel 専用ではない
- 絞る時は `[session_filters]` の `title_allow_regex` / `title_deny_regex` を使う

既定の感情方針:
- 対象 role はまず assistant 優先
- 分類は既定で単一 `emotion` 軸
- `emotion_tags.level` は `low` / `medium` / `high`
- `MEMORY_EMOTIONS_CONTEXT.md` の本文でも keyword と重みが見える形を保つ

## tuning / verification
調整後は少なくとも次を確認する。

```bash
python3 /opt/data/scripts/diaries/build-memory-context.py --stdout summary
python3 /opt/data/scripts/diaries/build-memory-context.py --refresh-emotion-buffer
python3 /opt/data/scripts/diaries/build-memory-context.py
```

いまの current spec では、`memory` plugin の resolve 経路が managed memory snapshots (`MEMORY_EVENT_CONTEXT.md` / `MEMORY_EMOTIONS_CONTEXT.md`) を読む前に `build-memory-context.py` を on-demand 実行する。だから gateway 再起動を待たなくても、LLM call 直前の pre-call injection で最新 snapshot が使われる。

見る場所:
- `top_keywords=`
- `preferred_level`
- `preferred_sessions`
- 生成された `MEMORY_EMOTIONS_CONTEXT.md` の先頭候補
- plugin runtime state の `last_resolution`

## retired lin-ops note

以前は `/opt/data/projects/lin-ops/` に memory sidecar の試作があったけど、現行の正本にはしない。

- 未接続 API facade
- compose / worker 前提の deployment note
- daily memory 生ファイル直読みの session-open text builder

このへんの歴史メモだけ `references/retired-lin-ops-project.md` に残して、runtime の責務は plugin / script / gateway hook に統合する。

## out of scope

次は plugin の正本には置かない。

- daily memory 本文の文体ルール
- `LINの振り返り` の書き方そのもの
- daily memory を会話でどう自然に扱うか
- LIN の関係性や人格面の運用ルール

それらは plugin 同梱の skill `memory` 側で持つ。

helper script の入口:
- `references/helper-scripts.md`
- `python3 /opt/data/scripts/diaries/search-memory.py <query>`
- `python3 /opt/data/scripts/diaries/list-memory-range.py`
- `python3 /opt/data/scripts/diaries/read-recent-memory.py`
