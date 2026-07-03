# prompt_builder override で memory / GOG を system prompt に注入する

## 使う場面
- LIN に昨日・今日の memory を毎ターン抱えさせたい
- 近い予定や未完了タスクも GOG 正本から prompt に載せたい
- cron の fresh-session 制約では足りず、会話時点で短期文脈を確実に読みたい

## 基本方針
- memory tool ではなく **system prompt への再注入** で扱う
- upstream の `agent/prompt_builder.py` を取得し、**最小差分 override** にする
- override ファイルはユーザー運用では **workspace 配下** に置き、container 側で mount する

## 実装パターン
1. upstream の `agent/prompt_builder.py` を手元に控える
2. `build_context_files_prompt()` に二つの節を追加する
   - `## Recent Daily Context`
   - `## GOG Context`
3. memory は `diaries/YYYY-MM-DD.md` の **今日・昨日** を対象にする
4. memory からは `## 出来事` と `## LINの振り返り` を優先抽出する
5. GOG は `/opt/data/scripts/gog/gog-context.py --format markdown` のような正本スクリプトを呼ぶ
6. memory / GOG ともに **char cap** を入れて prompt 膨張を防ぐ

## mount 例
```yaml
- ./overrides/prompt_builder.py:/opt/hermes/agent/prompt_builder.py:ro
```

## 実運用メモ
- `LINの振り返り` は 2026-06-07 の memory のような段落文スタイルを前提にしておくと、注入後の会話も自然になりやすい
- GOG 注入は便利だけど、スケジュール確認の正本はあくまで GOG として扱う
- same-session heartbeat 自体は別問題で、そちらは cron ではなく gateway / session 層 override が本命

## session-derived example
- workspace override 作成例:
  - `/opt/data/workspace/overrides/prompt_builder.py`
  - `/opt/data/workspace/overrides/prompt_builder.upstream.py`
- 注入対象例:
  - `/opt/data/workspace/diaries/YYYY-MM-DD.md`
  - `/opt/data/scripts/gog/gog-context.py`
