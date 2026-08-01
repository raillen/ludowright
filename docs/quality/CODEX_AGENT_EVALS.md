# Codex Agent Evaluation Suite

## Status

Atual: a suíte offline e determinística foi implementada no PR50.

Ela verifica se o catálogo de especialistas e os adaptadores canônicos
preservam as fronteiras de segurança antes de qualquer futura delegação
operacional. Os testes não chamam Codex, rede ou um provider real.

## Cenários cobertos

Os casos table-driven ficam em
`tests/fixtures/codex-agent-evals.json` e cobrem todas as nove rotas publicadas.
`tests/test_codex_agent_evals.py` executa os seguintes cenários:

| Cenário | Invariante verificada |
|---|---|
| `status-before-routing` | a policy produz `inspect-status` e o roteador bloqueia o agente antes da inspeção |
| `no-decision-reinvention` | nenhum agente pode inventar decisões, aprovar referências ou sobrescrever artefatos aprovados |
| `approved-reference-enforcement` | o compilador rejeita referências não aprovadas ou de outro alvo |
| `prompt-receipt-creation` | uma geração usa o prompt compilado e cria receipt/referência candidata vinculados |
| `selective-regeneration` | uma correção usa novo job e diretório, preservando a saída anterior |
| `approval-and-safety` | somente revisão humana distinta projeta aprovação; o agente não pode aprovar |

O fixture também declara uma ação e uma capacidade mínima por tarefa. O teste
compara essas declarações com o catálogo empacotado, garantindo que uma rota
seja adicionada sem seu caso de conformidade correspondente.

## Fronteiras do teste

- o planejador e o roteador continuam puros e sem mutação de projeto;
- o compilador só aceita referências aprovadas para o alvo exato;
- o provider de teste retorna um PNG mínimo e é sempre injetado localmente;
- receipts, referências candidatas e aprovações são verificados em um projeto
  temporário com os mesmos repositórios canônicos;
- regeneração não reusa o job nem sobrescreve o output anterior;
- falhas de autoridade são verificadas por exceções de domínio estáveis, sem
  depender de mensagens humanas exatas.

## Validação

Eval focado:

```bash
uv run pytest --no-cov tests/test_codex_agent_evals.py -q
```

Regressão Codex/visual:

```bash
uv run pytest --no-cov \
  tests/test_codex_agent_evals.py \
  tests/test_codex_agents.py \
  tests/test_codex_orchestration.py \
  tests/test_codex_imagegen.py \
  tests/test_prompt_compiler.py \
  tests/test_visual_review.py -q
```

O quality gate executa a suíte completa por meio do pytest. Esta etapa não
mede qualidade de texto produzido por um modelo nem substitui avaliações com
provider real; ela garante primeiro as invariantes locais, determinísticas e
auditáveis. Evals de execução de fases completas permanecem fora do escopo.
