# Codex Skill Contract

## Objetivo

O PR44 instala uma única skill local e versionada para o Codex:

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
```

O manifesto publicado é o contrato `codex-skill-manifest` v1. Ele declara:

- ID `ludowright` e invocação `$ludowright`;
- revisão inteira da skill;
- versão mínima do LudoWright;
- caminho canônico de instalação;
- entrypoint `SKILL.md`;
- checksums SHA-256 dos arquivos de payload.

O manifesto instalado acompanha o entrypoint. Ele não é incluído na própria
lista de payloads para evitar um checksum circular.

## Caminho de instalação

O destino é sempre relativo ao projeto descoberto:

```text
.agents/skills/ludowright/
├── manifest.json
└── SKILL.md
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

## Limites desta versão

Política de orquestração, execução de ImageGen, receipts, aprovações e agentes
especialistas pertencem aos PRs seguintes. A skill instalada não deve ser
interpretada como implementação dessas capacidades.
