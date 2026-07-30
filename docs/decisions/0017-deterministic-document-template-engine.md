# ADR 0017 — Deterministic Document Template Engine

- **Status:** Accepted
- **Date:** 2026-07-30
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `DOCUMENT_TEMPLATES.md`, `JSON_SCHEMAS.md`, `STRUCTURED_REPOSITORIES.md`

## Context

Os PRs de documentação precisam gerar Markdown repetível a partir de dados
estruturados. Um mecanismo que misture templates com lógica Python, paths
absolutos ou estado de execução produziria saídas difíceis de revisar e abriria
uma superfície de execução desnecessária para overrides do projeto.

## Decisão

O LudoWright usa manifests JSON versionados e templates Jinja armazenados como
dados empacotados. O `DocumentTemplateEngine`:

1. valida o manifesto através de `DocumentTemplateManifestContract`;
2. aceita somente arquivos declarados pelo manifesto;
3. resolve overrides do projeto sob `.ludowright/templates/<id>/` antes do
   pacote, mantendo a validação de paths da infraestrutura;
4. renderiza em `SandboxedEnvironment` com `StrictUndefined`, globals vazios e
   filtros determinísticos;
5. normaliza UTF-8, line endings e a quebra de linha final;
6. retorna texto e digest sem persistir o resultado.

## Alternativas consideradas

### Templates como constantes Python

Rejeitado. Mistura dados com lógica, dificulta revisão por designers e impede
packs versionados sem alterar código.

### `FileSystemLoader` irrestrito

Rejeitado. Permite que herança ou includes alcancem arquivos fora da allow-list
do template e não reaproveita a política de symlinks do projeto.

### Ambiente Jinja completo

Rejeitado. Globals, filtros e acesso a atributos podem introduzir dependências
ocultas e resultados não determinísticos.

### Escrever o resultado dentro do engine

Adiado. Renderizar e persistir têm conflitos, locks e políticas de aprovação
diferentes. O engine deve permanecer uma operação pura; um caso de uso futuro
coordenará escrita atômica e auditoria.

## Consequências

Positivas:

- templates são revisáveis, empacotáveis e versionados como dados;
- a mesma saída pode ser reproduzida em CI, CLI e Codex;
- overrides locais não precisam duplicar o pacote inteiro;
- a superfície de execução e de filesystem é limitada;
- snapshots detectam mudanças de saída.

Custos:

- alterar um template pode exigir incremento de versão e atualização de
  snapshots;
- overrides são limitados aos arquivos declarados;
- o primeiro template cobre somente um documento mínimo.
