# Context: IronFrame-OuterFortress-Cart-01-Decomp

- **Tier R (`nes`):** `D3/S4/R0` (`goal: D5/S5/R3`, target engine `reCart` `0.1.x`, `v0.2.0` `26` cohesive `D3_Mapped` C modules). Zero `Builds`/`Releases`; `Corpus` & `Dev/data/` gitignored (`-xr!Corpus\*`, `standalone/` RO).
- **Control:** [research.manifest.json](Dev/research.manifest.json) | [decomp_recipe.json](Dev/schemas/decomp_recipe.json) | [IronFrame-OuterFortress-Cart-01-Decomp.code-workspace](Dev/IronFrame-OuterFortress-Cart-01-Decomp.code-workspace) | Downstream: `MetalGearRecomp` (`read-only`)

## 1. Quartet, Security & State
- [README.md](README.md) | [FEATURES.md](FEATURES.md) | [ROADMAP.md](ROADMAP.md) | [CHANGELOG.md](CHANGELOG.md) | [SECURITY.md](SECURITY.md) | [CONTRIBUTING.md](CONTRIBUTING.md) | [active.state](active.state)

## 2. Manuals (`Dev/docs/`)
- [ARCHITECTURE.md](Dev/docs/ARCHITECTURE.md) | [SPECIFICATIONS.md](Dev/docs/SPECIFICATIONS.md) | [FINDINGS.md](Dev/docs/FINDINGS.md) | [OPERATIONS.md](Dev/docs/OPERATIONS.md)
- **Spokes, Plans & Reports:** [specifications/](Dev/docs/specifications/) | [findings/](Dev/docs/findings/) | [stages/](Dev/docs/stages/) | Local-only gitignored: `Dev/docs/plans/`, `Dev/docs/reports/`

## 3. Governance & Notion
- **Notion:** `<NOTION_PROJECT_PAGE_ID>` (`<NOTION_TASK_LIST_COLLECTION>` — local IDs in gitignored `Dev/data/notion_hub.local.json`)
- **Commit `/post` Hook:** Once public, every release posts `/post` via `active.state` -> `discordPost` (`DISCORD_WEBHOOK_FOUNDATION`).
