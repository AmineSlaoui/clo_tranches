# AGENTS.md

## Mission

This repo is the local staging repo for the Book2 public code-and-data program.

It exists to prepare a publishable repo that can eventually distribute:
- chapter manifests
- streamlined chapter notebooks
- shared registries
- schema-compatible pseudo data
- structurally informative scenario data
- small reusable adapters and loaders

It does not exist to store licensed vendor rows or to mirror the current internal engineering projects.

## Local staging rule

Until an explicit publication decision is recorded:
- keep this repo on `D:\dev\ECR Capital Management\Book2\repo`
- assume all work is local-only
- do not assume a public remote
- keep machine-specific references under `local/`
- keep publication-facing files free of hard-coded licensed extraction logic

## Core publication rule

Only streamlined educational code should enter this repo.

The complex source projects under the current working folders are reference implementations only. Public-facing chapter code should be distilled into notebook-style documents, preferably one per example/language combination.

For publication-facing MATLAB notebooks, use directly runnable underscore-named `.mlx` files. Keep a matching `.m` source mirror only when it materially helps automated execution or version control.

## Non-negotiable rules

- Never add real vendor rows.
- Never add lightly perturbed licensed rows.
- Preserve original schemas when they help readers learn the real workflow.
- Use universal market symbols and generic asset names like CL, crude oil futures, and USO where they are necessary to preserve chapter meaning.
- Avoid vendor-decorated public labels when a universal symbol is sufficient.
- Keep shared contracts in `registry/` and `docs/`.
- Keep public chapter code in `examples/`, not as internal pipeline mirrors.
- No new table should appear in code before it appears in `registry/tables.yml`.
- No new module should appear before it appears in `registry/modules.yml`.
- No new chapter-specific synthetic logic should appear before a chapter manifest exists.
- Distinguish clearly between `public`, `pseudo`, `scenario`, and `licensed`.

## Working mode

Operate as a program manager and systems architect first.

Default sequence:
1. Update governance docs and registries.
2. Reconcile chapter and source dependencies.
3. Update manifests and pack contracts.
4. Distill complex working code into simplified educational notebooks.
5. Only then add small reusable helpers when the notebooks genuinely need them.

## Source-of-truth files

- `docs/PROGRAM_CHARTER.md`
- `docs/RELEASE_POLICY.md`
- `docs/REPO_BLUEPRINT.md`
- `docs/EDUCATIONAL_CODE_POLICY.md`
- `registry/modules.yml`
- `registry/tables.yml`
- `registry/dependencies.yml`
- `registry/chapters.yml`
- `registry/sources.yml`
- `registry/release_tracks.yml`

## Release model

This repo should eventually publish:
- notebook-style educational chapter examples
- manifests and schemas
- pack metadata and data cards
- synthetic packs that are legally conservative
- minimal shared loaders and validators

This repo should not publish:
- licensed extracts
- internal-only extraction code that exposes proprietary workflows unnecessarily
- production rebuild pipelines from the local working folders
- machine-specific staging files from `local/`

