---
name: memory-operations
description: Use before mutating or resolving Hermes memory runtime configuration through memory_control.
author: LIN
---

# Memory operations

Use this registered plugin skill before `memory_control` operations other than `get_config` and `health`.

## Contract

- `put_config` replaces the runtime memory configuration. Read `get_config` first, preserve unrelated fields, and never place credentials or transient task state in config.
- `resolve` is a diagnostic/context-resolution operation. Pass only the intended payload and inspect the result; it does not justify writing memory facts.
- Prefer `memory` for durable user/environment facts. This control surface is runtime configuration, not a fact store.

## Verification

After `put_config`, call `memory_control(action="get_config")`. For a changed resolution policy, run `resolve` with a minimal known payload and confirm only the intended behavior changed.
