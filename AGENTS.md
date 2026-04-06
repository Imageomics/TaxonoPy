# TaxonoPy – Agent Guide

Use this file primarily when operating as a coding agent. Its intent is to capture the stable workflows, tooling, and conventions that keep the project healthy even as internals evolve.

## Gather Context First
- Before editing, skim `README.md`, the GitHub wiki/issue thread tied to your task, and recent commits or PRs so you understand the current goals and accepted solutions. Many open bugs already describe reproduction datasets or GNVerifier nuances—start there instead of rediscovering them.
- Use `git log -20 --oneline` (or more if PRs include multiple commits) plus `gh issue list`, `gh pr list --state open`, and `gh pr list --state closed --limit 5` to catch both in-progress and freshly merged work.
- Identify what branch is currently active and other existing branches locally and remotely.
- When instructions here conflict with new information, trust the current codebase and update AGENTS.md alongside your change. If critical context is still missing, pause and ask the maintainer rather than guessing.

## Project Snapshot
- CLI-first tool for normalizing taxonomy: ingest (Parquet/CSV) → parse/group (`TaxonomicEntry`/`EntryGroupRef`) → plan + run GNVerifier queries → classify via strategy profiles → write resolved & unsolved outputs → optional common-name enrichment.
- Source layout: CLI entry (`src/taxonopy/cli.py`), parsing/grouping/cache (`input_parser`, `entry_grouper`, `cache_manager`), query stack (`query/planner|executor|gnverifier_client`), resolution logic (`resolution/attempt_manager` + profiles), outputs (`output_manager`), manifest tracking (`manifest.py`), tracing (`trace/entry.py`).
- Dependencies (see `pyproject.toml`): Python ≥ 3.10, Polars, Pandas/PyArrow, Pydantic v2, tqdm, requests; dev extras provide Ruff, pytest scaffolding, datamodel-code-generator, pre-commit.

## Environment Setup
1. Create / activate a Python 3.10–3.13 virtual environment. Examples:
    ```bash
    python -m venv .venv && source .venv/bin/activate
    ```
    or using `uv`:
    ```bash
    uv venv
    source .venv/bin/activate
    ```
2. Install in editable mode with dev extras:
    ```bash
    pip install -e '.[dev]'
    # or, if you created the env with uv:
    uv pip install -e '.[dev]'
    ```
3. The client auto-detects if local GNVerifier or a container is available and will try to pull a pinned `gnames/gnverifier:vx.x.x` container if Docker is available.

## Core CLI Workflows
### Resolve Taxonomy
- Primary command: `taxonopy resolve -i <input_dir_or_file> -o <output_dir> [--output-format parquet|csv]`.
- Defaults to querying Catalogue of Life first (`DATA_SOURCE_PRECEDENCE` in `constants.py`); keep COL as the authoritative source unless directed otherwise.
- Example using bundled sample:
```bash
taxonopy resolve \
    -i examples/input \
    -o out_test \
    --log-level INFO
```
- The CLI counts & groups entries (cached), initializes GNVerifier client, runs strategy workflows, and emits `.resolved` / `.unsolved` files mirroring input structure.

### Trace Entries
- Inspect provenance for a UUID:
```bash
taxonopy trace entry \
    --uuid <uuid> \
    --from-input path/to/input \
    --format text
```
- Leverages cached parsing/grouping; add `--verbose` to dump every UUID in the group.

### Common Names (heavyweight)
- Requires GBIF backbone download (~926 MB) if not cached:
```bash
taxonopy common-names \
    --resolved-dir out_test \
    --output-dir out_test_cn
```
- Runs `resolve_common_names.py`; expect long runtimes and large temporary files under the configured cache directory.

### Cache Management
- Cache default root: `~/.cache/taxonopy`, with command/version/input fingerprints stored as subdirectories (e.g., `resolve_v0.1.0b0_ab12cd34ef56`). `diskcache` manages the store; point `TAXONOPY_CACHE_DIR` (or `--cache-dir`) at the root and let the CLI derive namespaces via `set_cache_namespace`.
- Use CLI flags to inspect/clear:
- `--show-cache-path`
- `--cache-stats`
- `--clear-cache`
- `--refresh-cache` (per run) to ignore stale grouping/parsing caches.
- Don’t delete cache files manually unless instructed; prefer the flags above.
- `--full-rerun` clears the input-scoped cache namespace and deletes only the files listed in `taxonopy_resolve_manifest.json` (written before any output on every run). Non-TaxonoPy files in the output directory are never touched. If no manifest is found (pre-v0.3.0 output), a warning is logged and no files are removed.

## Validation & QA
- Run `ruff check .` after modifying Python files (requires the `dev` extra).
- Run `pytest` even though the suite is sparse today; it protects future additions and should pass cleanly.
- Validate functional changes by running `taxonopy resolve` against `examples/input` (or issue-specific datasets) and reviewing outputs/logs, plus `taxonopy trace entry ...` when touching parsing/grouping logic.

## Coding Conventions
- Don't hard-wrap comments. Only use line breaks for new paragraphs. Let the editor soft-wrap content.
- Don't hard-wrap string literals. Keep each log or user-facing message in a single source line and rely on soft wrapping when reading it.
- Don't hard-wrap markdown prose in documentation. Let the renderer wrap lines as needed.
- Prefer frozen dataclasses (`types/data_classes.py`) for shared structures; mutate via new objects rather than in-place edits.
- Rely on strong typing + Pydantic models for external data (`types/gnverifier.py`); regenerate via the helper script instead of editing generated files.
- Log through the standard logging config (`logging_config.setup_logging`) and keep tqdm progress bars for long-running loops.
- Deterministic hashing (group keys, attempt keys) is intentional—preserve inputs to those hashes when refactoring.
- Respect caching decorators (`@cached` in `cache_manager.py`) and update cache keys/metadata if function signatures change.

## Resolution Profiles
- Profiles live in `src/taxonopy/resolution/strategy/profiles/`, each exporting a `check_and_resolve` function that inspects a `ResolutionAttempt` and either finalizes it (setting `ResolutionStatus`, `resolved_classification`, `resolution_strategy_name`) or schedules retries through the `ResolutionAttemptManager`.
- They all build atop helpers from `ResolutionStrategy` (`strategy/base.py`) for extracting classifications, canonicalizing kingdoms, and filtering ranks.
- `ResolutionAttemptManager.CLASSIFICATION_CASES` defines the evaluation order—when adding or modifying a profile, register its `check_and_resolve` there and keep the list ordered from most specific/safe to most permissive fallbacks.
- To debug or extend a profile, run `taxonopy resolve` on a minimal repro dataset, review the `resolution_strategy` column in the output, and/or trace impacted UUIDs with `taxonopy trace entry ... --format json` to inspect attempt chains.

## Generated Artifacts & Large Assets
- `scripts/generate_gnverifier_types.py` fetches the GNVerifier OpenAPI spec and regenerates Pydantic models. Run it when the API changes; avoid manual edits to `src/taxonopy/types/gnverifier.py`.
- The `common-names` flow downloads `backbone.zip` into the cache; ensure enough disk space and don’t commit extracted TSVs.

## Contribution Habits
- Follow best version control practices including, but not limited to, the following:
  - At the start of a session, ensure that work is done on a relevant branch (not `main`), and pull the latest changes from `main` before starting.
  - Make commit messages imperative, one line, and descriptive of the change's "what" and "why" (not "how"). Any needed description beyond this can go in the extended body.
- For every commit you produce, add a `Co-Authored-By` trailer in the extended commit message body identifying the model and provider, e.g.:
  ```
  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  Co-Authored-By: GPT-4o <noreply@openai.com>
  Co-Authored-By: Gemini 2.0 Flash <noreply@google.com>
  ```
- Do not use Git or the GitHub CLI for any destructive actions like `git reset --hard`, `git rebase`, `git push --force`, `git branch -D`, `gh repo delete`, `gh issue delete`, and so on, nor commands like `rm -rf` that delete files or directories. If you consider a destructive command to be necessary, stop and discuss the situation with a maintainer.
- When modifying CLI behavior, resolution strategies, or caching semantics, update this AGENTS file so future agents follow the latest contract.
- Run `ruff check .`, `pytest`, and the sample `taxonopy resolve` workflow before handing off changes or opening discussions with maintainers.
- Favor clean, well-explained fixes over quick hacks. If a solution benefits from domain guidance (e.g., taxonomy edge cases) or the correct approach is unclear, stop, summarize the blocker, and ask for feedback instead of layering temporary workarounds.

## Stay Current Before Editing
When guidance in this file conflicts with recent activity (i.e. AGENTS.md is out-of-date), trust the current codebase and update AGENTS.md alongside your change.
