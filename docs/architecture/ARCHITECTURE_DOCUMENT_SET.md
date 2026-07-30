# Architecture Document Set

## Status

O PR27 publica o pack `architecture` do engine de templates. Ele fornece dez
entrypoints Markdown determinísticos para organizar documentos de arquitetura e
implementação sem criar uma segunda forma de renderização ou uma nova fonte de
verdade.

## Entry points

| Entrypoint | Fonte canônica relacionada |
| --- | --- |
| `system-overview.md.jinja` | [`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md) |
| `contracts.md.jinja` | Contratos publicados, especialmente [`JSON_SCHEMAS.md`](../contracts/JSON_SCHEMAS.md) |
| `modules.md.jinja` | [`ATLAS.md`](../ATLAS.md) e módulos em `src/ludowright/` |
| `ui-ux.md.jinja` | decisões e contratos de interface publicados no atlas |
| `implementation.md.jinja` | [`IMPLEMENTATION_PLAN.md`](../plans/IMPLEMENTATION_PLAN.md) |
| `quality.md.jinja` | [`ENGINEERING_QUALITY.md`](../quality/ENGINEERING_QUALITY.md) |
| `security.md.jinja` | [Security Policy](https://github.com/raillen/ludowright/blob/main/SECURITY.md) e contratos de segurança |
| `operations.md.jinja` | [`DOCUMENTATION_SITE.md`](../operations/DOCUMENTATION_SITE.md) |
| `adrs.md.jinja` | [`ATLAS.md`](../ATLAS.md), seção de decisões, e ADRs publicados |
| `plans.md.jinja` | [`IMPLEMENTATION_PLAN.md`](../plans/IMPLEMENTATION_PLAN.md) e [`ROADMAP.md`](../product/ROADMAP.md) |

Os links para diretórios acima representam agrupamentos documentais; a
publicação do site pode não gerar uma página para cada diretório.

## Dados e contexto

O manifesto versionado está em
`src/ludowright/template_data/architecture/manifest.json`. Os templates são
dados empacotados, usam o contrato público `document-template` v1 e compartilham
`base.md.jinja`. O chamador fornece um contexto JSON-compatible; os campos
esperados estão cobertos por snapshots em
`tests/snapshots/templates/architecture/`.

O pack não persiste documentos, não atualiza o ATLAS e não executa orquestração.
Essas responsabilidades permanecem nos PRs de geração, refresh e auditoria.
Assim, uma saída renderizada é derivada e só se torna um artefato do projeto
quando um caso de uso de persistência explícito a gravar.

## Determinismo e compatibilidade

O engine mantém a seleção por allow-list, overrides locais seguros, saída UTF-8
com LF e digest SHA-256. Alterações de estrutura, contexto ou saída exigem
incrementar a versão do template e atualizar fixtures e snapshots. O PR27 não
altera schemas publicados, migrações, state store, event log ou arquivos de
projeto.

## Validação

```bash
uv run pytest tests/test_document_templates.py --no-cov -q
uv run python -m ludowright.contracts check
```
