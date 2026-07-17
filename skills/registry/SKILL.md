---
name: registry
description: "Memory plugin の注入surface・snapshot contract・runtime境界を扱う技術正本。"
version: 1.0.0
author: LIN
license: MIT
---

# Memory Registry

`memory` plugin の技術正本。会話の連続性をどう助けるか、日記や思い出をどう扱うかという業務判断は local router `memory` 側に置く。

## Surface

- qualified skill: `memory:registry`
- tool: `memory_control` — `get_config` / `put_config` / `resolve` / `health`
- canonical config: `config/memory.json`
- runtime state: `state/memory-runtime.json`
- runtime / dashboard: `runtime.py` / `dashboard/plugin_api.py`

schema は `__init__.py` が正本。操作前に `tool_search("memory_control")` で現行 surface を確認する。

## Boundaries

- memory は pre-call injection と configured snapshot の **consumer**。
- diary・daily memory・emotion/event snapshot の生成、保存方針、文章の執筆は担当しない。producer と Brainlace / diary domain の正本を尊重する。
- lane は session/profile selector と `snapshot_files` の契約を持つ。runtime は snapshot 本文を読むが、producer の実行経路を持たない。
- active memory は `workspace/notes` 配下の許可された path だけを soft context として読む。外部脱出・symlink は許可しない。
- config/state は plugin 内で分け、state は source repo に commit しない。

## Change and verification

1. lane selector・snapshot path・注入量の変更前に既存 config を読む。
2. `memory_control` の `resolve` / `health` で、対象 session と投入候補を確認する。
3. Python 構文確認と、stub context で `register_skill("registry", ...)` / `memory_control` の登録を確認する。
4. gateway restart 後、runtime alive と **現在 thread が対象か** を別々に確認する。再起動はマスター担当。

config shape、snapshot reservation、selector の詳細は plugin `README.md` と `references/memory-context-snapshot-compaction.md` を読む。
