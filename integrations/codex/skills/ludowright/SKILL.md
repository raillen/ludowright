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

## Limite desta versão

A política seleciona a próxima ação e orienta o Codex; o planejador não executa
providers nem grava decisões, aprovações ou receipts por conta própria. Essas
mutações continuam nas superfícies canônicas do núcleo. Execução de ImageGen,
receipts, revisão visual e agentes especialistas pertencem às etapas posteriores
do roadmap.
