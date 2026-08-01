# Codex Skill CLI

## Instalação

Instale a skill local em um projeto LudoWright existente:

```bash
ludowright codex skill install /caminho/do/projeto
```

O comando grava somente os arquivos declarados pelo manifesto em
`.agents/skills/ludowright/`. Atualmente eles são `manifest.json`, `SKILL.md`,
`orchestration.json` e `agents.json`. Um destino não vazio ou alterado é
recusado.

Para revisar o plano sem alterar o projeto:

```bash
ludowright codex skill install /caminho/do/projeto --dry-run
ludowright --json codex skill install /caminho/do/projeto --dry-run
```

O dry-run não cria o lock nem diretórios auxiliares.

## Verificação e atualização

```bash
ludowright codex skill verify /caminho/do/projeto
ludowright --json codex skill verify /caminho/do/projeto
ludowright codex skill update /caminho/do/projeto
```

`verify` confere o manifesto, os checksums, o ID, o caminho, a revisão e a
compatibilidade com a versão instalada do LudoWright. Uma instalação ausente,
desatualizada ou modificada retorna `checks-failed` com o relatório completo em
`data` no modo JSON.

`update` só atualiza uma versão antiga que ainda esteja intacta. Alterações
manuais, arquivos extras, symlinks e uma versão mais nova bloqueiam a operação.

## Remoção

```bash
ludowright codex skill remove /caminho/do/projeto
ludowright codex skill remove /caminho/do/projeto --dry-run
```

A remoção é segura e idempotente: uma skill ausente resulta em
`not-installed`; uma instalação modificada não é apagada. A pasta da skill é
removida somente quando fica vazia.

## Saída JSON

```bash
ludowright --json codex skill verify /caminho/do/projeto
```

O resultado usa o envelope `cli-response` e inclui um `codex-skill-report` com
`operation`, `state`, `dry_run`, `skill_id`, `skill_version`,
`installed_version`, `install_path`, arquivos com checksums, warnings e
`valid`.

## Falhas esperadas

- `project-not-found`: o caminho não pertence a um projeto LudoWright;
- `conflict`: instalação modificada, destino não vazio ou downgrade;
- `resource-not-found`: atualização sem skill instalada;
- `blocked`: versão do framework abaixo do mínimo;
- `checks-failed`: verificação encontrou estado inválido;
- `corrupt-state`: falha de escrita e rollback.

As mensagens humanas podem evoluir; os códigos e exit codes permanecem os
contratos para automação.

## Política de orquestração

A skill instalada na revisão 3 inclui a política declarativa em
`.agents/skills/ludowright/orchestration.json`. Ela não é um novo comando nem um
segundo armazenamento de estado. O adaptador Codex a usa para planejar uma única
próxima ação:

```text
status → bloqueios/revisão → perguntas pendentes → decisões
→ validações → aprovação humana → retomada → próxima fase
```

O planejador exige `status` antes de qualquer outro passo, seleciona somente
questões ainda não resolvidas, preserva IDs de decisões e aprovações, bloqueia
falhas de validação e só retoma um workflow com cursor durável e fase conhecida.
Ele não executa ImageGen, não aprova artefatos e não grava eventos por conta
própria.

Consulte o [contrato da política](../contracts/CODEX_ORCHESTRATION.md) para a
ordem completa, os contratos publicados e os limites desta etapa.

## Agentes especialistas

O arquivo `.agents/skills/ludowright/agents.json` declara as nove rotas
especialistas. O adaptador seleciona um agente somente depois de validar o
plano, o status, a ação e as capacidades exigidas. Os agentes não têm
autoridade de aprovação; o resultado preserva o checkpoint humano. Consulte o
[contrato de agentes](../contracts/CODEX_AGENTS.md).

## Avaliação de conformidade

A suíte offline dos agentes verifica as rotas e as fronteiras entre policy,
prompt, ImageGen, receipts e revisão. Ela usa apenas fixtures e providers de
teste locais:

```bash
uv run pytest --no-cov tests/test_codex_agent_evals.py -q
```

Essa avaliação não executa fases completas nem substitui a aprovação humana.
O contrato, os cenários e as limitações estão em
[`CODEX_AGENT_EVALS.md`](../quality/CODEX_AGENT_EVALS.md).

## Execução ImageGen

O PR46 não adiciona um comando CLI independente. A integração Codex expõe
`ImageGenExecutor` para o host fornecer um `VisualJob` selecionado de um plano
`ready`, seu `CompiledPrompt`, um diretório relativo e um provider ImageGen.
Cada view gera uma chamada e um PNG; o adaptador persiste `operation.json` com
prompt, inputs, paths e revisões.

O modo `dry_run` retorna o mesmo plano determinístico sem lock, chamada ao
provider ou escrita. Execução real é create-only: manifesto ou PNG existente
gera conflito, e falhas removem os artefatos criados pela tentativa. O
adaptador persiste o receipt terminal e as referências geradas como candidatas;
a revisão e a aprovação continuam workflows canônicos separados, não efeitos
implícitos dos agentes.
