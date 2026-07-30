# Incremental Document Refresh Contract

## Status

Atual. O PR29 publica os contratos `document-refresh-request` e
`document-refresh`, além do caso de uso que planeja e persiste documentos
gerados incrementalmente.

## Arquivos do projeto

Para cada `document_id`, o refresh usa somente paths derivados e seguros:

```text
.ludowright/documents/<document-id>.md
.ludowright/documents/<document-id>.json
```

O JSON de estado é a fonte canônica dos hashes observados, do template e dos
digests da saída. O Markdown é a projeção gerada e pode conter seções manuais.
O pedido de renderização é um documento separado, normalmente criado por uma
orquestração futura:

```json
{
  "schema_version": 1,
  "kind": "document-refresh-request",
  "document_id": "game-brief",
  "template_id": "minimal",
  "context": {"title": "Echoes", "body": "A small game.", "sections": []},
  "source_hashes": []
}
```

O pedido guarda o contexto necessário para a renderização, mas não substitui
as fontes canônicas que produziram esse contexto.

## Staleness e planejamento

`DocumentRefreshService.plan()` compara, sem escrever arquivos:

- hashes de fontes adicionadas, removidas ou alteradas;
- ID, versão e entrypoint do template;
- digest do Markdown renderizado;
- digest completo da saída atual;
- digests das seções manuais.

O resultado é `new`, `current` ou `stale`. Somente documentos `new` ou `stale`
são afetados por um refresh. A comparação é determinística e não usa mtime,
relógio ou conteúdo da conversa.

## Seções manuais

O conteúdo gerado é delimitado por:

```markdown
<!-- ludowright:generated:start -->
...
<!-- ludowright:generated:end -->
```

Seções manuais são explícitas e preservadas, inclusive quando ainda não foram
aprovadas:

```markdown
<!-- ludowright:manual:start id="review-notes" approved="true" -->
Texto aprovado pelo responsável.
<!-- ludowright:manual:end -->
```

IDs duplicados, nesting e marcadores incompletos bloqueiam a operação. O
refresh substitui somente a região gerada e reanexa os blocos manuais na ordem
em que foram encontrados. A aprovação fica registrada no estado como
metadado; o refresh não aprova nem remove conteúdo.

## Persistência e falhas

`ludowright documents refresh` usa o repositório JSON estruturado, o lock
`document-refresh` e escrita atômica. A operação grava saída, estado e um evento
`document.refreshed`. Se qualquer gravação ou o evento falhar, os bytes
anteriores são restaurados; uma falha de rollback preserva a causa original.

`--dry-run` apenas carrega, renderiza e planeja. Ele não cria diretórios,
estado, saída ou eventos.

## Compatibilidade

Os contratos v1 estão publicados em `schemas/v1/` e possuem fixtures. O estado
usa a infraestrutura existente de JSON canônico, limites, symlink denial,
locks e digests exatos. Não há migração de arquivos anteriores: documentos sem
estado são tratados como `new` e a primeira execução cria os dois arquivos.

## Limitações

Esta etapa não monta contextos a partir de entrevistas, não descobre fontes
automaticamente e não altera o dependency graph. A integração dessas fontes e
o audit documental continuam sendo etapas posteriores.
