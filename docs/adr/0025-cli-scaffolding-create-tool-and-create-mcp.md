# ADR 0025 — CLI Scaffolding Commands: `nexusai create-tool` and `nexusai create-mcp`

## Status

Accepted

## Context

As the NexusAI plugin ecosystem grows, contributors need to create standards-compliant
tool plugins and MCP server integrations repeatedly. Without scaffolding, each new author
must manually study existing plugins (e.g. `plugins/calculator/`, `plugins/git/`) to
replicate the correct file layout, `BaseTool` subclass shape, `PluginManifest` YAML
schema, and MCP JSON-RPC 2.0 STDIO protocol boilerplate — leading to:

- Inconsistencies in naming, docstring style, and capability declarations.
- Missing `nexusai_manifest.yaml` or `nexusai_mcp.yaml` configuration files.
- Incorrect `RiskLevel` defaults or missing `input_schema` declarations.

## Decision

Two top-level Typer commands are added to `nexusai.cli.app`:

| Command | Purpose |
|---|---|
| `nexusai create-tool <name>` | Scaffold a `BaseTool` plugin directory under `plugins/<name>/` |
| `nexusai create-mcp <name>` | Scaffold an MCP STDIO server directory under `plugins/mcp/<name>/` |

All template rendering is isolated in a new module `nexusai.cli.scaffolding`, keeping
`app.py` as a thin CLI wiring layer. The module exposes two pure functions
(`scaffold_tool`, `scaffold_mcp`) and a frozen `ScaffoldResult` dataclass for testability.

### Generated artefacts — `create-tool`

```
plugins/<name>/
  __init__.py
  plugin.py              # BaseTool + Plugin class, type-annotated, Google docstrings
  nexusai_manifest.yaml  # PluginManifest schema, capabilities, version
  README.md              # Developer quickstart
```

### Generated artefacts — `create-mcp`

```
plugins/mcp/<name>/
  __init__.py
  server.py              # Async JSON-RPC 2.0 STDIO event loop, tools/list + tools/call
  nexusai_mcp.yaml       # McpServerConfig YAML snippet, ready to merge into config/mcp_servers.yaml
  README.md              # Quickstart + transport documentation
```

### CLI options (both commands)

| Option | Default | Description |
|---|---|---|
| `--description / -d` | `"A new NexusAI …"` | Short description embedded in templates |
| `--output-dir / -o` | `plugins` / `plugins/mcp` | Parent directory for scaffolding |
| `--dry-run` | `False` | Preview files without writing to disk |
| `--overwrite` | `False` | Silently replace existing files |

### Validation

Plugin/server names are validated with `_VALID_IDENTIFIER = r"^[a-z][a-z0-9_]*$"`.
Invalid names exit immediately with a non-zero code and a descriptive error message.

## Alternatives Considered

1. **Cookiecutter-based templating**: Provides a richer UX but adds a dependency and requires
   an external template repository. Overkill for the current scope (4 files per scaffold).
   Revisit in Phase 4 if community plugins demand more complex project structures.

2. **Interactive wizard (prompt-based)**: Would require `questionary` or `InquirerPy` and
   complicates CI automation (`--no-input` flags). Rejected in favour of declarative option
   flags aligned with existing CLI conventions.

3. **Single `nexusai create` command with `--type tool|mcp`**: Rejected because Typer's
   command-name auto-completion and `--help` readability are superior with distinct verb-noun
   command names (`create-tool`, `create-mcp`).

## Consequences

### Positive
- **Zero boilerplate**: New contributors run one command and receive a working, lint-clean template.
- **Consistency enforcement**: All scaffolded tools use `RiskLevel.LOW`, `input_schema`, and
  Google-style docstrings by default.
- **Testability**: `scaffold_tool` / `scaffold_mcp` are pure functions (no global state),
  enabling parametric unit tests without mocking.
- **Dry-run safety**: The `--dry-run` flag lets contributors preview the scaffold in CI
  pipelines before committing.

### Negative
- Templates must be manually updated when `BaseTool`, `PluginManifest`, or the MCP protocol
  schema evolve. A future ADR should introduce template versioning or test fixtures that
  validate generated code compiles without errors.

## Validation Criteria

- `nexusai create-tool --help` and `nexusai create-mcp --help` display correct usage.
- `nexusai create-tool sample --dry-run` exits 0 and lists 4 preview files without writing them.
- `nexusai create-tool my_tool --output-dir /tmp/test` creates 4 files under `/tmp/test/my_tool/`.
- Generated `plugin.py` imports pass `ruff check` and `mypy --strict` without modification.
- `nexusai create-tool Bad-Name` exits non-zero with a validation error.
- All 33 tests in `tests/unit/cli/test_scaffolding.py` pass.

## Review Phase

Phase 3.2 — CLI Developer Experience
