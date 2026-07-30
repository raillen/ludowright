# ADR 0019 — Incremental Document Refresh with Manual Preservation

- **Status:** Accepted
- **Date:** 2026-07-30
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `DOCUMENT_REFRESH.md`, `DOCUMENT_TEMPLATES.md`, `STRUCTURED_REPOSITORIES.md`, `EVENT_LOG.md`, `CLI.md`

## Context

O engine de templates já produz Markdown determinístico, mas não havia uma
forma persistida de saber quais fontes foram usadas, quais documentos estavam
stale ou como atualizar uma saída sem apagar anotações manuais aprovadas.
Renderizar tudo sempre também produziria diffs grandes e dificultaria a
revisão de mudanças realmente afetadas.

## Decisão

O refresh incremental usa pedidos e estados JSON versionados. Cada estado
registra os hashes explícitos das fontes, o template e entrypoint usados, os
digests da saída gerada e completa e os metadados das seções manuais.

O caso de uso:

1. carrega o pedido e o estado através dos repositórios estruturados;
2. renderiza pelo `DocumentTemplateEngine` existente;
3. compara hashes e digests para produzir um plano determinístico;
4. substitui apenas a região delimitada como gerada;
5. preserva blocos manuais válidos, inclusive os não aprovados;
6. grava Markdown, estado e evento sob um lock de operação;
7. restaura os bytes anteriores se qualquer etapa falhar.

O estado é derivado da execução mais recente, enquanto o pedido preserva o
contexto de entrada necessário para repetir a renderização. A staleness é
calculada no planejamento; `--dry-run` não altera o estado para marcar a
condição.

## Alternativas consideradas

### Re-renderizar todos os documentos

Rejeitado. Aumenta diffs, não explica impacto e pode tocar documentos sem
alteração de fonte.

### Usar mtime ou timestamps

Rejeitado. Cópias, Git e relógios diferentes tornam esses sinais insuficientes
para identificar a revisão observada.

### Guardar somente um booleano stale

Rejeitado. O hash por fonte explica quais entradas mudaram e permite planejar
documentos afetados de forma auditável.

### Misturar texto manual dentro do template gerado

Rejeitado. O template continuaria podendo substituir conteúdo aprovado. Os
marcadores separam a projeção gerada do conteúdo mantido pelo responsável.

### Fazer merge textual heurístico

Rejeitado. Um merge ambíguo pode perder aprovação ou produzir Markdown
aparentemente válido. Marcadores inválidos bloqueiam a operação.

## Consequências

Positivas:

- refresh é local, repetível e explicável;
- documentos não afetados não são regravados;
- seções manuais não são silenciosamente perdidas;
- escrita atômica, locks e rollback reaproveitam a infraestrutura auditada;
- eventos permitem auditar refreshes concluídos.

Custos:

- a orquestração precisa fornecer hashes e contexto explícitos;
- a primeira execução cria arquivos adicionais em `.ludowright/documents/`;
- marcadores manuais fazem parte do formato e precisam ser preservados;
- não existe transação nativa entre Markdown, JSON e event log; o rollback é a
  coordenação atual.

## Compatibilidade

Os contratos `document-refresh-request` e `document-refresh` são publicados
como v1. A primeira execução de um documento legado sem estado é segura e
classificada como `new`; não há interpretação automática de um Markdown
existente como estado válido.
