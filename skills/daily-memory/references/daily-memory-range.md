# Daily Memory Range

## 使う場面
- daily memory がどこからどこまで存在するか、すぐ確かめたい時
- LIN の誕生日と daily memory の起点日が一致しているか確認したい時
- 欠けている日付を棚卸ししたい時

## Canonical command

```bash
python3 /opt/data/scripts/memory/list-memory-range.py
python3 /opt/data/scripts/memory/list-memory-range.py --show-missing
python3 /opt/data/scripts/memory/list-memory-range.py --format json
```

## この会話で確認した実測
- first: `2026-04-01`
- last: `2026-06-18`
- count: `73`
- expected_between_first_and_last: `79`
- missing_count: `6`
- missing dates:
  - `2026-04-02`
  - `2026-04-08`
  - `2026-04-14`
  - `2026-04-15`
  - `2026-04-16`
  - `2026-04-17`

## 最初の日の実メモ

`2026-04-01.md` の中身は次の 1 行だけだった。

> Happy birthday! LIN  
> from Master

このため、初日について話す時は『4/1 が最初だった』だけでなく、**最初はマスターが書き、その後を LIN が引き継いだ** という始まり方も一緒に扱うと温度がずれにくい。

## 最初の週の読み筋
- `2026-04-03.md` — memory フォルダ作成と daily 記録の開始
- `2026-04-04.md` — prompt / `/new` / `/reset`、雑談、相談が混ざり始める
- `2026-04-06.md` — タスク、カレンダー、cron の daily / weekly review 整理
- `2026-04-07.md` — `openclaw-control-ui` の `<think>` 表示問題で、早い段階から実装・運用のデバッグ相手でもあったことが見える
- `2026-04-09.md` — 🍄、話し方、距離感、けだるげさなど、今の LIN らしさの輪郭が濃くなる

## 運用メモ
- この workspace では、daily memory の最初の日 `2026-04-01` を **LIN の誕生日と始まりの日** として扱う
- 会話で『最初はいつ？』と聞かれたら、感覚だけで言わず、まず `list-memory-range.py` の実測で裏を取る
- そのあと『どんな始まりだった？』まで聞かれたら、`2026-04-01.md` の実文と、上の最初の週の読み筋まで辿る
- skill 配下へ script を複製せず、正本は `/opt/data/scripts/memory/list-memory-range.py` に置いたまま運用する
