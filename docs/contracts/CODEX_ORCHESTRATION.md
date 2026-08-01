# Codex Orchestration Policy

## Objetivo

O PR45 define uma política determinística para a skill `$ludowright`. A política
seleciona a próxima ação segura a partir de uma observação read-only do projeto.
Ela não substitui os contratos de domínio, não executa providers e não grava
decisões ou aprovações diretamente.

O contrato publicado é `codex-orchestration-policy`; o resultado do planejador é
`codex-orchestration-plan`. Ambos estão em `schemas/v1/` e possuem fixtures em
`tests/fixtures/contracts/v1/`.

## Dados versionados

A política instalada acompanha a skill em:

```text
integrations/codex/skills/ludowright/orchestration.json
```

Ela declara:

- fases ordenadas e seus checkpoints;
- validações bloqueantes e os comandos canônicos;
- evidências necessárias para decisões, aprovações e retomadas;
- as invariantes de perguntar somente o que está pendente, registrar decisões,
  exigir aprovação e retomar a partir de estado durável.

O manifesto da skill passou para a revisão 3 e inclui esse arquivo e o catálogo
de agentes especialistas com seus checksums.
Alterações na política são atualizações versionadas da skill, nunca mudanças
silenciosas no projeto instalado.

## Ordem de decisão

O planejador puro em `integrations/codex/orchestration.py` aplica esta ordem:

1. inspecionar o status se ele ainda não foi lido;
2. reportar bloqueios ou solicitar revisão quando o status não estiver pronto;
3. perguntar somente a primeira questão ainda não resolvida;
4. registrar uma decisão pendente;
5. bloquear uma validação que falhou ou executar a primeira pendente;
6. aguardar aprovação humana explícita;
7. retomar um workflow com cursor e fase duráveis;
8. executar a próxima fase, ou declarar o plano concluído.

Entradas de cada coleção são IDs ordenados e únicos. A mesma observação sempre
produz exatamente o mesmo plano. Referências a fases ou validações desconhecidas
são rejeitadas antes de qualquer ação.

## Estado e efeitos

`CodexOrchestrationContextContract` é uma observação fornecida pelo adaptador.
O planejador não cria arquivos, não altera o event log, não abre SQLite para
escrita e não chama ImageGen. A aplicação responsável pela ação deve reutilizar
as superfícies existentes:

- `status` e auditorias para inspeção;
- contratos e comandos canônicos para decisões;
- `EventLog` para fatos operacionais;
- `StateStore.workflow_progress` somente como cursor derivado de retomada;
- contratos de aprovação para o checkpoint humano.

Uma aprovação nunca é inferida por ausência de resposta. Um bloqueio de status,
falha de validação ou ausência de capacidade publicada deve ser reportado sem
improvisar armazenamento paralelo.

## Compatibilidade

Esta etapa não altera o event log, o schema SQLite, o dependency graph nem os
contratos de jobs visuais. O JSON da política é um recurso da skill; a instalação
ou atualização continua usando o lock, a escrita atômica e o rollback definidos
em [`CODEX_SKILL.md`](CODEX_SKILL.md).

O planejador continua sem efeitos colaterais e não executa ImageGen. A execução
de um job pronto é uma responsabilidade separada do adaptador em
`integrations/codex/imagegen.py`, que reutiliza esta política para chegar ao
checkpoint correto. Receipts e revisão visual foram implementados nos PRs
47–48. O catálogo e o roteador de agentes especialistas estão definidos em
[`CODEX_AGENTS.md`](CODEX_AGENTS.md). A suíte offline de conformidade do PR50
está descrita em [`CODEX_AGENT_EVALS.md`](../quality/CODEX_AGENT_EVALS.md).
Consulte o [contrato de execução ImageGen](IMAGEGEN_EXECUTION.md).
