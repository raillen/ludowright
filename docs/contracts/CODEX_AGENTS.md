# Codex Specialist Agents Contract

## Objetivo

O PR49 publica um catálogo versionado de especialistas para o adaptador Codex.
O catálogo define escopos de leitura e escrita, capacidades, guidance, ações
permitidas e rota de cada papel. Ele não executa prompts, providers ou comandos
e não é fonte de estado do projeto.

## Catálogo publicado

O contrato `codex-agent-catalog` v1 é carregado de:

```text
integrations/codex/skills/ludowright/agents.json
```

A instalação project-local da skill leva esse arquivo junto com `SKILL.md` e
`orchestration.json`. A revisão da skill passou para 3. O catálogo contém nove
papéis:

| Tarefa | Agente |
|---|---|
| `interview` | `interviewer` |
| `game-design` | `game-design-architect` |
| `technical-architecture` | `technical-architect` |
| `asset-planning` | `asset-planner` |
| `visual-direction` | `visual-director` |
| `generation` | `generation-operator` |
| `consistency-review` | `consistency-reviewer` |
| `quality-audit` | `quality-auditor` |
| `release-verification` | `release-verifier` |

Cada perfil declara `phase_ids`, `capabilities`, escopos de leitura e escrita,
`guidance`, ações de orquestração permitidas e fronteiras proibidas. Os IDs e
`capabilities` são ordenados e únicos para tornar a validação e o hash
determinísticos.

## Routing

`CodexAgentRouter` recebe um `CodexAgentRoutingContextContract` com a tarefa e
um `CodexOrchestrationPlanContract`. Ele:

1. bloqueia planos sem status inspecionado, bloqueados ou em revisão;
2. retorna conclusão sem selecionar agente quando o plano está completo;
3. resolve uma única rota declarada para a tarefa;
4. verifica a ação do plano e as capacidades exigidas;
5. recusa um agente solicitado que não corresponda à rota canônica;
6. preserva o checkpoint humano no resultado.

O resultado é o contrato `codex-agent-route` v1. Uma rota bloqueada não escolhe
um fallback implícito. Uma rota encaminhada informa as capacidades e se exige
interação humana.

## Segurança e limites

Todos os agentes têm `can_approve: false` e declaram as proibições de aprovar
referências, inventar decisões e sobrescrever artefatos aprovados. O roteador
não confere autoridade por ausência de resposta e não transforma uma sugestão
em mutação canônica. Execução de fases e chamadas a providers continuam nas
superfícies existentes; o PR50 adicionará a suíte de evals.

Não há alteração no event log, SQLite, dependency graph ou arquivos do projeto.
O catálogo é recurso versionado da skill e sua integridade é protegida pelo
manifesto e por checksum.

## Validação

```bash
uv run pytest --no-cov tests/test_codex_agents.py tests/test_codex_skill.py
uv run python -m ludowright.contracts check
```

O primeiro comando verifica as nove rotas, determinismo, bloqueios, capacidades
e ausência de autoridade de aprovação. O segundo verifica os schemas publicados.
