# Codex Skill Contract

## Objetivo

O PR44 instala uma única skill local e versionada para o Codex. O PR45 adiciona
a política de orquestração declarativa ao mesmo pacote:

```text
$ludowright
```

A skill é um adaptador fino. Ela orienta a leitura do estado canônico e o uso
do CLI, mas não guarda decisões, substitui o núcleo determinístico ou executa
providers.

## Pacote versionado

A fonte da skill fica em:

```text
integrations/codex/skills/ludowright/manifest.json
integrations/codex/skills/ludowright/SKILL.md
integrations/codex/skills/ludowright/orchestration.json
integrations/codex/skills/ludowright/agents.json
```

O manifesto publicado é o contrato `codex-skill-manifest` v1. Ele declara:

- ID `ludowright` e invocação `$ludowright`;
- revisão inteira da skill (atualmente `3`);
- versão mínima do LudoWright;
- caminho canônico de instalação;
- entrypoint `SKILL.md`;
- checksums SHA-256 dos arquivos de payload.

`orchestration.json` declara a política `codex-orchestration-policy` v1. Ela é
validada pelo adaptador antes de produzir um `codex-orchestration-plan`.

O manifesto instalado acompanha o entrypoint. Ele não é incluído na própria
lista de payloads para evitar um checksum circular.

## Caminho de instalação

O destino é sempre relativo ao projeto descoberto:

```text
.agents/skills/ludowright/
├── manifest.json
├── SKILL.md
├── orchestration.json
└── agents.json
```

O nome `SKILL.md` preserva a convenção case-sensitive do Codex. A extensão
controlada de `ProjectFilesystem` para arquivos de integração mantém a
contenção, a recusa de symlinks e a escrita atômica sem ampliar a gramática de
paths canônicos do projeto.

## Estados e versionamento

| Estado | Significado |
|---|---|
| `verified` | Arquivos, manifesto, identidade e versão atual conferem |
| `outdated` | Instalação intacta, mas com revisão menor que a empacotada |
| `modified` | Checksum, manifesto, arquivos ou conteúdo extra não conferem |
| `unsupported` | A instalação é mais nova que o pacote local |
| `incompatible` | A revisão coincide, mas o manifesto mudou de forma incompatível |
| `not-installed` | O destino não existe ou está vazio |

`install` é idempotente quando encontra uma instalação idêntica. Ele recusa
um destino não vazio, modificado ou de outra skill. `update` só aceita uma
instalação intacta e mais antiga; não faz downgrade e não sobrescreve alterações
manuais. `verify` é somente leitura. `remove` só remove uma instalação intacta
da skill LudoWright e nunca apaga arquivos extras.

## Comandos

```bash
ludowright codex skill install PROJECT
ludowright codex skill install PROJECT --dry-run
ludowright codex skill update PROJECT
ludowright codex skill update PROJECT --dry-run
ludowright codex skill verify PROJECT
ludowright codex skill remove PROJECT
ludowright codex skill remove PROJECT --dry-run
```

Todos os comandos são não interativos e aceitam `--json` global ou local. A
resposta fica no envelope `cli-response`; o campo `data` usa o contrato
`codex-skill-report` v1.

## Segurança e atomicidade

- `PROJECT` precisa estar dentro de um projeto descobrível por
  `.ludowright/project.json`;
- o destino e seus ancestrais não podem ser symlinks;
- a escrita usa o lock `codex-skill`, arquivos temporários irmãos, `fsync` e
  troca atômica;
- o manifesto é escrito por último, depois dos payloads;
- falhas intermediárias restauram os bytes anteriores ou removem o alvo novo;
- `--dry-run` não cria diretórios nem locks;
- versão mínima do framework é verificada antes da instalação.

Não há mudança no event log, no SQLite, no grafo de dependências ou em
migrações. A instalação da skill é uma integração local independente do estado
canônico do projeto.

## Política de orquestração

A política exige inspeção de status antes de qualquer ação, perguntas somente
para questões pendentes, registro de decisões, validações bloqueantes,
checkpoints de aprovação humana e retomada a partir de cursor durável. O
planejador é read-only: ele retorna a próxima ação e não grava estado nem chama
providers. A ordem e os códigos estão no contrato
[`CODEX_ORCHESTRATION.md`](CODEX_ORCHESTRATION.md).

## Execução ImageGen

A skill pode encaminhar um job selecionado de um plano `ready` e seu prompt
compilado para o adaptador `ImageGenExecutor`. O adaptador usa o provider
injetado pelo host, grava o contrato `imagegen-operation` e faz uma chamada por
view, com validação PNG, lock, escrita atômica, rollback, receipt terminal e
referências candidatas. A aprovação continua no workflow de revisão e não é
inferida pela skill.

## Agentes especialistas

A revisão 3 inclui `agents.json`, o catálogo dos nove papéis e suas rotas. O
adaptador carrega o catálogo com validação estrita e o `CodexAgentRouter`
encaminha somente tarefas compatíveis com o plano, capacidades e ações
declaradas. A especificação canônica está em
[`CODEX_AGENTS.md`](CODEX_AGENTS.md).

Agentes não possuem autoridade de aprovação. A aprovação humana continua sendo
um checkpoint explícito da policy e sua gravação continua responsabilidade dos
comandos canônicos.

## Limites desta versão

O catálogo seleciona papéis, mas não executa fases completas nem substitui o
CLI, o event log, o SQLite, o grafo ou os providers. A suíte offline de
conformidade foi implementada no PR50; delegação operacional e execução de
fases completas permanecem fora desta etapa.
