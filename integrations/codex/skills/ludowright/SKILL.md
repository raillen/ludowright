---
name: ludowright
description: Operar projetos LudoWright usando o estado canônico do repositório e o CLI local.
---

# $ludowright

Use esta skill para trabalhar em um projeto LudoWright local.

## Política de orquestração

O fluxo normativo está em `orchestration.json`. Aplique estas regras nesta ordem:

1. Leia `docs/ATLAS.md` e a fonte canônica da área antes de alterar qualquer arquivo.
2. Execute `ludowright --json status` primeiro. Se o projeto não for encontrado, o estado estiver bloqueado ou o comando não existir na versão instalada, pare e reporte o bloqueio.
3. Pergunte somente o que ainda estiver sem resposta. Não repita respostas, decisões ou aprovações já registradas; uma pergunta resolvida deve desaparecer da lista pendente.
4. Registre cada escolha canônica pelo comando e contrato publicados antes de usá-la para produzir artefatos. O histórico do chat nunca é a única fonte da decisão.
5. Execute as validações declaradas pela política antes de concluir uma fase: `atlas --check`, `quality check` e o `status` do projeto. Preserve o resultado e pare em qualquer falha bloqueante.
6. Pare em cada checkpoint que exigir aprovação humana. Nunca infira aprovação a partir de silêncio, uma resposta ambígua ou um estado antigo; a aprovação deve apontar para a revisão exata do artefato.
7. Para retomar uma operação, releia o estado durável e o cursor da fase, execute o status novamente e revalide as entradas antes de continuar. Repita uma ação somente quando o contrato dela for idempotente.

Use `--json` para automações, mantenha caminhos relativos ao projeto e preserve contratos, IDs, versões, aprovações e artefatos existentes. Se uma capacidade necessária ainda não estiver publicada no CLI, trate-a como bloqueada em vez de improvisar um armazenamento paralelo.

## Execução ImageGen

Quando um plano visual estiver `ready`, encaminhe o job selecionado e seu
`CompiledPrompt` ao `ImageGenExecutor` da integração Codex. O provider é
injetado pelo host; a execução registra um `imagegen-operation`, faz exatamente
uma chamada por view, valida PNG não animado, usa paths relativos, lock,
escrita atômica, dry-run, rollback e um receipt terminal com checksums,
referências candidatas e metadados disponíveis. Não trate a presença do
manifesto ou do receipt como aprovação: revisão e aprovação são etapas
posteriores.

## Limite desta versão

## Agentes especialistas

O catálogo versionado em `agents.json` declara os nove papéis especialistas e
suas rotas determinísticas: `interviewer`, `game-design-architect`,
`technical-architect`, `asset-planner`, `visual-director`,
`generation-operator`, `consistency-reviewer`, `quality-auditor` e
`release-verifier`.

O roteador só encaminha uma tarefa depois que o plano da policy confirma que o
status foi inspecionado. Ele valida a ação permitida, as capacidades exigidas,
os escopos declarados e a rota da tarefa. Um resultado bloqueado deve ser
reportado; não invente um agente alternativo nem uma capacidade ausente.

Os agentes podem propor e validar mudanças pelas superfícies canônicas, mas
nenhum agente possui autoridade de aprovação. O agente de geração não aprova o
próprio output, e checkpoints humanos continuam explícitos no plano.

## Limite desta versão

A política seleciona a próxima ação e o catálogo encaminha o especialista; os
adaptadores não gravam decisões ou aprovações por conta própria. Receipts e
referências candidatas são persistidos pelo adaptador ImageGen canônico, e a
aprovação continua nas superfícies de revisão do núcleo. A suíte offline de
conformidade foi implementada no PR50; execução de fases completas permanece
em etapas posteriores do roadmap.
