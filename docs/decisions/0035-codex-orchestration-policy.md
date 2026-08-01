# ADR 0035: Declarative Codex orchestration policy

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `CODEX_SKILL.md`, `CODEX_ORCHESTRATION.md`, `CLI.md`, `STATE_STORE.md`

## Context

A skill local pode orientar o Codex, mas uma lista de instruções solta não é
suficiente para garantir que o agente inspecione o estado antes de agir,
registre decisões, execute validações, pare para aprovação e retome operações
interrompidas. Ao mesmo tempo, a política não deve duplicar o event log, o SQLite,
as regras de aprovação ou a execução de providers.

## Decisão

1. A política de orquestração será um arquivo JSON versionado dentro do pacote da
   skill e terá os contratos `codex-orchestration-policy` e
   `codex-orchestration-plan`.
2. O adaptador Codex validará a política e usará um planejador puro para escolher
   uma única próxima ação a partir de uma observação read-only.
3. A ordem obrigatória será status, bloqueios/revisão, perguntas pendentes,
   decisões, validações, aprovação humana, retomada e próxima fase.
4. IDs, coleções e referências desconhecidas serão rejeitados de forma fail-closed;
   resultados e entradas serão serializados deterministicamente.
5. Mutações permanecerão nas APIs canônicas de aplicação e infraestrutura. O
   planejador não gravará decisões, aprovações, eventos, SQLite ou imagens.

## Alternativas consideradas

### Manter somente instruções em `SKILL.md`

Rejeitada porque texto livre não oferece validação de schema, revisão de versão ou
um resultado determinístico testável.

### Fazer o planejador executar comandos e providers

Rejeitada porque misturaria política com efeitos colaterais, duplicaria o CLI e
anteciparia a execução ImageGen, receipts e revisão previstos nos PRs seguintes.

### Guardar o cursor apenas no prompt

Rejeitada porque a retomada seria perdida quando a conversa terminasse. O
adaptador deve consumir o cursor durável já definido pelo state store quando uma
aplicação o fornecer.

## Consequências

### Positivas

- ordem de segurança explícita e auditável;
- comportamento determinístico e fácil de testar;
- nenhuma aprovação automática ou decisão escondida no chat;
- política atualizável junto da skill, com checksum e compatibilidade;
- futura execução pode reutilizar o plano sem acoplar providers ao núcleo.

### Negativas

- esta etapa orienta e planeja, mas não executa uma operação completa;
- o adaptador ainda depende de comandos de status, governança e validação que
  devem estar publicados no branch integrado correspondente;
- uma política incompatível exige nova revisão da skill.

## Compatibilidade e migração

Não há migração de projeto, event log ou SQLite. A skill revisão 1 continua sendo
detectada como antiga e pode ser atualizada pela instalação versionada; o arquivo
de política é instalado como novo payload na revisão 2. A mudança de forma do
contrato exige nova versão de schema e política explícita de atualização.
