# Documentation ATLAS Contract

## Status

Atual. O PR28 publica o contrato `atlas-metadata` para fontes canônicas e o
contrato `atlas-report` para o índice e a análise de integridade da árvore de
documentação.

## Canonical metadata

The repository metadata file is:

```text
docs/atlas.json
```

It is a versioned `atlas-metadata` JSON document. Each entry declares:

- `path`: Markdown path relative to `docs/`;
- `title`: display title used by generated indexes;
- `section`: stable slug used for deterministic grouping;
- `canonical_source`: path relative to `docs/` that owns the document's truth.

The metadata file is itself canonical input. It is parsed through the existing
strict JSON repository and is never inferred from chat history or generated
output.

## Report

`AtlasGenerator` returns an `atlas-report` containing:

- the sorted document index and metadata digest;
- every local Markdown link discovered;
- broken links with `missing-file`, `missing-anchor`, `unsafe-path`, or
  `missing-canonical-source` reasons;
- sorted Markdown paths that exist under `docs/` but are absent from metadata.

External links with a URI scheme are not dereferenced. Relative links are
resolved from the source document, remain inside `docs/`, and are checked for
file existence. Markdown fragments are checked against deterministic heading
slugs. A symlink anywhere in the scanned documentation tree is rejected.

## Generation and output

The application API is:

```python
from ludowright.application import AtlasGenerator

generation = AtlasGenerator(".").generate()
generation.report
generation.markdown
generation.valid
```

The CLI uses the same report and the shared response envelope:

```bash
ludowright atlas
ludowright --json atlas
ludowright atlas --check
```

`--check` returns `checks-failed` with exit code 1 when integrity findings
exist. Generation is read-only and does not overwrite `docs/ATLAS.md` or any
canonical document. Callers may persist `generation.markdown` through an
explicit, separately reviewed workflow.

## Determinism and compatibility

Metadata entries, links, findings, sections, and generated Markdown use stable
ordering. The metadata digest is the exact UTF-8 byte digest of
`docs/atlas.json`. Changes to the metadata or report shape require fixtures,
schema publication, and compatibility review. The PR28 implementation does not
change project manifests, state storage, event logs, or migrations.
