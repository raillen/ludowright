# Review CLI

## Apply a visual review

O comando aplica um contrato `visual-review` a outputs exatos de um receipt
de geração bem-sucedido:

```bash
ludowright review review.json .
ludowright --json review review.json .
ludowright review review.json . --dry-run
```

Na forma completa, o subcomando é:

```bash
ludowright review INPUT.json [PROJECT] [--dry-run] [--json]
```

`INPUT.json` é relativo à raiz do projeto e precisa validar o schema publicado
`visual-review` v1. O `PROJECT` é a pasta que contém, ou está abaixo de, um
marker regular `.ludowright/project.json`.

O contrato deve nomear um receipt sucedido, os seus outputs, um `reviewer` e um
`producer` com IDs distintos. Para `accepted`, o reviewer precisa ser humano e
o contrato precisa nomear um `approval_id`. `changes-requested` é a ação
canônica para “correct”; `rejected` requer uma nota. Um review aceito v1 nomeia
exatamente um output porque o contrato possui um único `approval_id`.

## Estado persistido

Uma execução bem-sucedida cria ou atualiza, de forma atômica:

- `.ludowright/visual-reviews/<review-id>.json`;
- `.ludowright/approvals/<approval-id>.json` quando aplicável;
- `.ludowright/visual-references/<reference-id>.json`;
- `.ludowright/dependency-graph.json`;
- `.ludowright/events.jsonl`.

Reviews são create-only. Repetir exatamente o mesmo contrato retorna
`unchanged`; reutilizar o ID com outro conteúdo retorna `conflict`. O comando
nunca sobrescreve silenciosamente um review existente.

## Dry-run, falhas e saída

`--dry-run` valida receipt, provenance, atores, aprovação e grafo, mas não cria
arquivos, não atualiza referências e não registra evento. A execução real usa
lock exclusivo, paths relativos seguros, repositórios JSON atômicos e rollback
dos arquivos escritos pela operação quando uma etapa posterior falha.

O modo humano usa Rich. O modo `--json` usa o envelope `cli-response` publicado
e inclui `state`, `dry_run`, IDs, paths, `graph_revision`, impactos, `event_sequence`
e `warnings`. Erros esperados usam os códigos semânticos e exit codes da
[CLI Contract](../contracts/CLI.md).

## Validação

```bash
uv run pytest tests/test_visual_review.py --no-cov -q
uv run ludowright review --help
```
