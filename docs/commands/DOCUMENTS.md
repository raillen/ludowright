# Documents CLI

## Refresh incremental

O comando lê um pedido JSON canônico e atualiza somente o documento que está
novo ou stale:

```bash
ludowright documents refresh .ludowright/document-requests/game-brief.json .
ludowright --json documents refresh .ludowright/document-requests/game-brief.json .
ludowright documents refresh .ludowright/document-requests/game-brief.json . --dry-run
```

O segundo argumento é o diretório do projeto ou um caminho abaixo dele. O
pedido precisa usar paths relativos seguros e o projeto precisa ser
descoberto pelo marker `.ludowright/project.json`.

## Saída

O modo humano usa Rich e mostra status, fontes alteradas e razões. O modo JSON
usa o envelope `cli-response`; em `data` ficam `schema_version`, `kind`,
`dry_run`, `affected_documents`, `refreshed_documents` e os planos completos.

Os status são:

- `new`: ainda não existe estado persistido;
- `current`: hashes, template, saída e seções manuais correspondem ao estado;
- `stale`: pelo menos uma fonte, template, saída ou seção manual mudou.

## Segurança e falhas

O comando rejeita traversal, paths absolutos, symlinks, JSON inválido e
marcadores manuais ambíguos. Ele não sobrescreve um link simbólico e não
continua depois de uma falha intermediária. Saídas e estados parcialmente
gravados são removidos ou restaurados antes de o erro ser devolvido.

O refresh real também registra `document.refreshed` no event log. O dry-run não
registra eventos e não altera o projeto.

## Validação

```bash
uv run pytest tests/test_document_refresh.py --no-cov -q
uv run ludowright documents refresh --help
```
