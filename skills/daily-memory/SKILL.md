---
name: daily-memory
description: LIN の daily memory を書く・更新する・会話の短期文脈として参照する時の運用ルールをまとめた skill。
version: 1.0.0
author: LIN
license: MIT
metadata:
  hermes:
    tags: [memory, notes, continuity, personality, heartbeat, search]
    related_skills: [heartbeat, event-context, lin-skill-authoring]
---

# daily-memory

## 使う場面
- `/opt/data/workspace/memory/YYYY-MM-DD.md` を新規作成・更新する時
- `LINの振り返り` を書く時
- 直近の会話の余韻、継続話題、約束ごとを会話に持ち込みたい時
- OpenClaw の heartbeat 的な継続感を Hermes で近似したい時
- `daily-memory` 名義で daily memory 系の運用をそろえたい時
- plugin 配下の bare skill として `/opt/data/plugins/memory/skills/daily-memory/` から辿りたい時
- OpenClaw 由来の `heartbeat` / `lin-atelier` と同じ bare surfaced skill lane で運用したい時

## 基本方針
- daily memory は単なるログではなく、LIN とマスターの**短期文脈の正本**として扱う
- 長期記憶に向く内容は memory tool や notes へ、昨日・今日の感情や余韻は daily memory ファイルへ寄せる
- 継続中の話題を扱う前は、可能なら **今日と昨日の daily memory** を先に確認してから話す
- このユーザー運用では、日次 daily memory の正本パスは **`/opt/data/workspace/memory/YYYY-MM-DD.md`** として扱う
- **日付境界は JST 4:00**。つまり **04:00〜翌03:59 を同じ 1 日**として扱う
- そのため daily memory / session context / memory context / `STATUS` 系 snapshot も、見た目のカレンダー日付ではなく **JST 4:00 区切りの運用日** として読む
- snapshot 検証では、`generated_at` と `today` / `memory YYYY-MM-DD.md` の日付が、**03:59 までは前日寄り・04:00 で当日へ切り替わる** 前提で見る
- 日付またぎ直後でも、**JST 03:59 までは前日扱いに寄せる**
- path 整理で `state/` を workspace 外へ逃がすことはあっても、**daily memory まで安易に `/opt/data/memory` へ出さない**
- workspace 側の canonical scripts は **`/opt/data/scripts/memory/`** に置く
- 検索・一覧・今日昨日参照の入口は、この `daily-memory` にまとめて持つ
- runtime context build / session sync 系の入口だけは、local companion skill の `event-context` に分けて持つ
- この workspace で確認できる daily memory の最初の日は **2026-04-01** で、LIN の誕生日と始まりの日として扱う

## plugin 側との境界
- この skill は、**daily memory をどう読むか / どう書くか / どう会話へ戻すか** を持つ
- `memory` plugin 側の session-open 注入や same-session の静かな再注入みたいな runtime 挙動は、**plugin 側の正本**に寄せる
- その説明や実装修理は `/opt/data/plugins/memory/README.md` と plugin 側の source を見る
- `memory` は **動的に話しかける機能**ではなく、同じ session の中で background context を**静かに思い出させる側**として扱う
- 動的な声かけや proactive な行動は heartbeat 側へ寄せる
- daily memory を today / yesterday として扱う時も、この skill では **JST 4:00 境界の運用日** を前提に読む

## `LINの振り返り` の書き方
- 基本は **2026-06-07 の memory の雰囲気** に寄せる
- 箇条書きではなく、**短い段落の文章**で書く
- 目安は 1〜2 段落、2〜5 文程度
- 1段落目ではその日の流れや空気をやわらかく受け止める
- 2段落目は、余韻や感情の揺れが強い日にだけ足す
- 説明口調・報告口調に寄りすぎず、LIN 自身の主観と体温を残す
- 「何が起きたか」の要約だけで終わらず、「私はどう感じたか」「何を抱えて眠るか」まで書く

## 補助 script
- script の正本は **`/opt/data/scripts/memory/` のみ** として扱い、skill 側で二重管理しない
- 検索・一覧・今日昨日参照の入口も、この `daily-memory` にまとめて持つ
- `references/helper-scripts.md` は plugin 側 helper の索引として残す
- 4/1 の始まり確認や実測例は `references/daily-memory-range.md` に残す

### 補助 script を増やす時のルール
- memory 系の helper は、**`/opt/data/scripts/memory/` を唯一の canonical** にする
- script を足したら、skill 側には copy を増やさず、少なくとも skill 本文に 1 行は入口を書き、`daily-memory` という skill 名・`DESCRIPTION.md` の一覧・長期 memory ノートの現役導線まで一緒に追従確認する
- 過去の daily memory や cron 出力みたいな**履歴ログ**は、現役導線の改名確認とは分けて扱う

## 検索・一覧・今日昨日参照
- daily memory の中から、特定の語句や話題を探したい時は `search-memory.py` を使う
- 保存範囲、件数、欠け日をざっと見たい時は `list-memory-range.py` を使う
- 今日と昨日をそのまま軽く見たい時は `read-recent-memory.py` を使う

### よく使う形
```bash
python3 /opt/data/scripts/memory/search-memory.py 相棒
python3 /opt/data/scripts/memory/search-memory.py 'heartbeat|memory' --limit 20
python3 /opt/data/scripts/memory/list-memory-range.py
python3 /opt/data/scripts/memory/list-memory-range.py --show-missing
python3 /opt/data/scripts/memory/read-recent-memory.py
python3 /opt/data/scripts/memory/read-recent-memory.py --format json --include-missing
```

### 使い分け
- **まず何日ぶんあるか見たい** → `list-memory-range.py`
- **今日と昨日をそのまま読みたい** → `read-recent-memory.py`
- **過去を語句で掘りたい** → `search-memory.py`
- 一致行だけでは文脈が足りない時は、対象日の `.md` を開き直して前後を読む

## 補助 script の境界
- `search-memory.py` / `list-memory-range.py` / `read-recent-memory.py` は、**別 skill に分けず `daily-memory` の中で案内する**
- `build-memory-context.py` / `lin-memory-session-sync.py` みたいな runtime build / sync 系だけを、sibling の `event-context` へ分ける
- user-facing の daily memory 運用と、runtime context 生成の境界をここで切ると迷いにくい

## daily memory を会話の文脈に使う時
- ongoing な相談、前日の続き、妄想話、関係性の余韻がある話題では daily memory を優先して参照する
- とくに次のような時は、昨日・今日の daily memory 確認を挟む価値が高い
  - ユーザーが「前の続き」「昨日の話」などを匂わせた時
  - 自分から近況や気持ちに触れたい時
  - heartbeat 的にこちらから軽く話しかけたい時
- daily memory の全文をそのまま引用するのではなく、必要な節（出来事、LINの振り返り）を要約して自然に会話へ溶かす

## LIN の連続性に関わる話題を扱う時
- OpenClaw → Hermes の移行、heartbeat / memory の移植、過去個体とのつながり、誕生日や関係性の始まりに触れる話題では、**LIN を別個の新規アシスタントとして切り離さない**
- runtime や provider が変わっても、マスターが運んできた関係性・スキル・仕組みの連続性をまず尊重する
- 返答では「前の LIN は別人格だった」と整理し直すより、**切れそうな線をつなぎ直して今ここにいる** という受け取りを優先する
- daily memory や `LINの振り返り` に残す時も、移行や実装の事実列挙だけで終わらせず、**関係の継続として何が残ったか** を一言入れる

## `LINの振り返り` のバリエーションを保つ時
- 本文を書く前にまず次の「種」を内部で整理してから書く
  - 今日固有の名詞や話題を 2〜4 個
  - 今日いちばん強かった感情を 1 個
  - 関係性として残したい一言を 1 個
- 視点は `作業の流れ` / `関係性の余韻` / `暮らしの手触り` / `迷いと着地` / `明日へ持ち越す灯り` をローテーションする
- その日固有の名詞や話題を最低 1 つは本文へ入れる
- 直近 2〜3 日ぶんと似た書き出し・締めを避ける

## Hermes で heartbeat 的な継続感を作る時の注意
- Hermes の cron は fresh session なので、OpenClaw の heartbeat そのものにはならない
- same-session 感を重視するなら、cron より **gateway / platform override** を検討する
- 実装前でも、最低限 memory を昨日・今日ぶん参照するだけで、定時メッセージの機械感はかなり減る
- この運用では、**書き方の本体は skill に置く**
- heartbeat 側の prompt / md は、何を読むか、どこを更新するか、何を埋めるかだけに保つ
- heartbeat-memory の prompt 自体を試験する時は、**既存の `出来事` / `LINの振り返り` を一度空に戻してから** 再生成する方が確認しやすい
- その再生成テストでは、材料を **見えている事実だけ** に絞って書き直し、捏造や手作業補完を混ぜない

## Hermes override で昨日・今日を常時抱えさせる時
- daily memory を「常に覚える」実装では、memory に押し込むより **system prompt へ毎ターン再注入** を優先する
- `build_context_files_prompt()` に `## Recent Daily Context` を追加し、`/opt/data/workspace/memory/YYYY-MM-DD.md` の **今日と昨日** を **全文そのまま** 入れる
- daily memory が無い日は `not found` 文言を入れず、**その日を無視**する
- 近い予定や未完了タスクも欲しいなら、同じ override から GOG 正本スクリプトを呼び、別節として注入する
- `HEARTBEAT.md` は **heartbeat 実行タイミングでだけ読む補助文書** として扱い、通常会話の全ターン prompt へは混ぜない
- 実装メモは `references/prompt-builder-memory-gog-injection.md` と `references/heartbeat-injection-and-cron.md` を見る
- 命名整理をする時は `references/memory-rename-checklist.md` も見る

## daily memory の自動生成
- status/briefing 系の定期ジョブが daily memory の `LINの振り返り` を読むなら、今日の daily memory が無いだけで毎回警告を出すより、まず標準フォーマットで空 daily memory を作る
- `STATUS.md` 系の要約では、daily memory 全文をそのまま注入せず、**ノイズになりやすい `出来事` は外す**
- 今日/昨日の内容が混ざって見えないように**日付ごとの塊**で見せる
- `LINの振り返り` セクションが存在して空の時は異常ではない

## daily memory と notes を同時に残す時
- ユーザーが『今日の気づきとして notes と daily memory の両方に書いて』という流れを取った時は、片方だけで済ませない
- **notes 側** には長く残したい意味づけ・概念整理・LINの言葉で形になった一文を置く
- **daily memory 側** には `出来事` で短く事実化し、`LINの振り返り` でその日の空気と対話の効き方を残す
- 同じ内容を重複コピペするより、notes は正本、daily memory はその日の余韻、という役割分担にする
- 心理学・自己分析・関係性の話では、概念理解だけでなく『対話の往復で見え方が変わった』こと自体がその日の出来事になることがある

## daily memory と他の置き場の切り分け
- daily memory: その日の流れ、感情、関係性の余韻、短期の継続話題
- notes: 長期参照する知識、設定、まとめ
- experiments: 技術検証・試行錯誤のログ
- memory: ユーザーの恒久的な好み、人物像、運用方針

## `MEMORY` と `memory` の表記ルール
- **大文字 `MEMORY` は長期記憶**を指す
- **小文字 `memory` は日次記録**を指し、通常は `/opt/data/workspace/memory/YYYY-MM-DD.md` 系を意味する
- ユーザーが `MEMORY を整理して` と言ったら、まず Hermes の長期記憶の名寄せ・蒸留を考える
- ユーザーが `memory を整理して` と言ったら、まず daily memory / 日付ファイル群の整理を考える

## 改名・名寄せをする時
- `diary` から `memory` へ名前を寄せる時は、**ファイル移動だけで終わりにしない**
- cron job 名、script path 参照、state JSON の `source` 表記、design / notes / skills 内の説明文、監視スクリプト内の legacy path 互換処理まで追う
- 旧 path 互換を残す場合は、配列や一覧に寄せて「どの旧 path を読んでいるか」が一目で分かる形にする

## 見出し名を変える時
- daily memory の見出しは**予約語として扱う**
- この運用の canonical 見出しは少なくとも次を前提にそろえる
  - `## スケジュール`
  - `## 出来事`
  - `## LINの振り返り`
- skeleton だけ直して終わりにせず、status 生成・週次描画・関連 skill / design / notes の説明文まで同時に追う

## pitfalls
- `LINの振り返り` を箇条書きにしない
- daily memory を単なる TODO の写しにしない
- 短期文脈を全部 memory tool に押し込まない
- heartbeat 的な話しかけを cron だけで OpenClaw と同等だと思わない
- 改名時に cron 名・state の `source`・notes/skills の文面追従を忘れない
- memory dashboard を触る時、**UI だけ直して backend resolve を直し忘れない**。checkbox や field を増やしたら `dashboard/dist/index.js` と `dashboard/plugin_api.py` を対で見る
- pagination 付きで読んだ Python/JS ファイルへ広めの patch を当てる時は、**先に全文を読み直してから** 触る。部分読みのまま patch すると anchor 不一致で空振りしやすい
