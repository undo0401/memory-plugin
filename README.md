# memory plugin

`memory` plugin は、この workspace では **pre-call injection / context snapshot consumer** を持つ場所だよ。

diaries / daily notes / emotion context の生成は別責務。memory はそれらの
producer script を直接実行せず、lane config の `snapshot_files` に列挙された
既存 snapshot を読むだけに保つ。

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

2. **snapshot consumer contract**
   - producer が用意した markdown snapshot を `snapshot_files` から読む
   - memory plugin は producer の path や実行方法を正本にしない
   - snapshot の shape と読み取り順序だけをここで追う

## canonical files

- backend: `/opt/data/plugins/memory/dashboard/plugin_api.py`
- config: `/opt/data/plugins/memory/config/memory.json`
- runtime state: `/opt/data/plugins/memory/state/memory-runtime.json`
- managed snapshots:
  - `/opt/data/state/MEMORY_EVENT_CONTEXT.md`
  - `/opt/data/state/MEMORY_EMOTIONS_CONTEXT.md`
- retired sidecar note: `references/retired-lin-ops-project.md`
- diaries / daily-memory の書き方・生成・検索は memory plugin の責務外

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
      "reinject_interval_minutes": 0,
      "target_sessions": ["agent:main:discord:group:1514000804028092618:1342027443027836941"],
      "target_profiles": ["default"],
      "exclude_sessions": [],
      "exclude_profiles": [],
      "snapshot_files": ["state/STATUS.md"]
    }
  ]
}
```

### behavior

- lane selector の正本は `plugin_api.py`
- selector は session-only。`target_sessions` / `exclude_sessions` だけで評価し、channel selector は互換なしで廃止する
- dashboard では `scope`（全て / 対象 / 除外）を選び、その下の入力欄1つで session selector を編集する。`scope=全て` または入力欄が空なら target/exclude は空配列になり、実質全て対象として扱う
- `target_profiles` / `exclude_profiles` で、現在の Hermes profile 名（例: `default`, `coder`）を絞り込む。`target_profiles` が空なら `default` に正規化する
- dashboard は今開いている profile を使い、保存時は `target_profiles: ["<profile>"]` として保持する
- gateway 側では再実装せず、helper を呼んで prepend するだけに保つ
- lane ごとに `include_current_time=true` を付けると、pre-call 注入に OpenClaw 風の `Current time` ブロックを追加する
- lane ごとに `include_current_source=true` を付けると、pre-call 注入に現在の `platform` / `channel` を追加する
- 今日/昨日 daily memory を直接読むオプションは持たず、必要な短期文脈は `snapshot_files` 側の managed snapshot へ寄せる
- dashboard 詳細画面の `idle minutes` 欄を、pre-call memory context の再注入タイミングとして編集する
  - `0` は毎回注入
  - `1` 以上は初回注入後、その分数が経過した会話でだけ再注入
  - 保存時は runtime canonical key の `idle_seconds` へ分→秒換算して保持する
- `reinject_interval_minutes` は互換キーとして保存され、`idle_seconds` が 0 より大きい時は `idle_seconds` から再計算される
- LLM への memory context は、gateway の `_run_agent_inner` 直前で policy 判定してから pre-call 注入する
- `active_memory_directory` を設定すると、返答直前に現在の発言でその directory 配下の Markdown / text を軽量検索する
  - 相対 path は `HERMES_HOME`（この workspace では `/opt/data`）基準
  - `workspace/notes` 配下だけを許可し、absolute path・`..`・symlink による外部脱出は拒否する
  - 上位3件の短い抜粋だけを soft context として追加する
  - 関連候補が無い時は何も追加しない
  - 検索や読み取り失敗は main response を止めず、runtime trace に残して skip する

## snapshot consumer contract

`snapshot_files` は 1 行 1 ファイルで指定する。相対 path は `/opt/data` 直下を root として解決するので、通常は `state/STATUS.md` や `workspace/memory/{TODAY}.md` のように書く。絶対 path も互換として読める。

日付予約語は JST 基準で展開する。

- `{TODAY}` → `yyyy-mm-dd`
- `{TOMORROW}` / `{TODAY+1}` → 明日
- `{TODAY-1}` / `{YESTERDAY}` / `{YESTADAY}` → 昨日
- `{TODAY+1}` のような ±日数も許可

### event context

`MEMORY_EVENT_CONTEXT.md` は、event producer が用意する短い出来事断面。

- `days.today` / `days.yesterday` で分ける
- 各日付の中は session 単位
- 各 message は `role` / `time` / `content` を中心に保つ
- event 側本文は role を問わず char cap 100
- `[Recent channel messages]` と `[New message]` が両方ある時は、`[New message]` 側を優先する
- compaction / active task list みたいなシステム都合ノイズは落とす

圧縮ルールの詳細は `references/memory-context-snapshot-compaction.md` を見る。

### emotions context

`MEMORY_EMOTIONS_CONTEXT.md` は、emotion producer が用意する感情・余韻の断面。

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

## producer boundary

- memory plugin は snapshot producer を直接起動しない
- snapshot freshness は producer 側の cron/tooling が担う
- memory 側の確認対象は、`snapshot_files` の path が存在して読めることと、pre-call injection に含まれること
- snapshot の生成条件・抽出 scope・day boundary・検索 helper は diaries / event-context 側で管理する

## retired lin-ops note

以前は `/opt/data/projects/lin-ops/` に memory sidecar の試作があったけど、現行の正本にはしない。

- 未接続 API facade
- compose / worker 前提の deployment note
- daily memory 生ファイル直読みの session-open text builder

このへんの歴史メモだけ `references/retired-lin-ops-project.md` に残す。

## out of scope

次は plugin の正本には置かない。

- diaries / daily notes 本文の文体ルール
- `LINの振り返り` の書き方そのもの
- diary helper scripts の入口や実行方法
- daily notes を会話でどう自然に扱うか
- LIN の関係性や人格面の運用ルール

それらは diaries / daily-memory 側の skill・tooling で持つ。
