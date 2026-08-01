# Remoção segura

Este guia cobre a única remoção suportada nesta etapa: retirar a skill
project-local `$ludowright` de um projeto LudoWright.

Não existe um comando `ludowright uninstall` para apagar um projeto inteiro.
Não remova `.ludowright/`, o event log, o dependency graph, o SQLite ou os
arquivos canônicos para retirar a skill. Esses dados pertencem ao projeto e
não são recriados por `codex skill install`.

## Antes de remover

Confirme o projeto e registre o estado sem modificar arquivos:

```text
uv run ludowright --json diagnostics
uv run ludowright --json codex skill verify ./my-game
git -C ./my-game status --short
```

Preserve alterações locais em versionamento antes de remover a integração. A
remoção da skill não é uma operação de limpeza geral e não deve ser usada para
resolver conflitos de arquivos modificados.

## 1. Planejar sem escrever

Execute primeiro o dry-run:

```text
uv run ludowright --json codex skill remove ./my-game --dry-run
```

O comando retorna o envelope `cli-response` com `operation: "remove"`, o
estado planejado, a revisão, o caminho fixo, os arquivos declarados e
`dry_run: true`. O dry-run não cria lock, diretório ou arquivo e não altera o
projeto.

Em modo humano, a mesma operação usa Rich:

```text
uv run ludowright codex skill remove ./my-game --dry-run
```

No Windows PowerShell, use `.\my-game` no lugar de `./my-game`. A operação
continua não interativa e usa os mesmos estados e códigos semânticos.

## 2. Aplicar a remoção

Depois de revisar o plano, remova somente a skill intacta:

```text
uv run ludowright --json codex skill remove ./my-game
uv run ludowright --json codex skill verify ./my-game
```

O primeiro comando deve retornar `state: "removed"`. A verificação seguinte
deve relatar `state: "not-installed"` no `data` e `checks-failed` no envelope,
porque verificar uma skill ausente não é uma verificação bem-sucedida. Esse
resultado esperado não indica corrupção do projeto.

O comando usa o lock `codex-skill`, remove somente os arquivos declarados pelo
manifesto e remove a pasta `.agents/skills/ludowright/` quando ela fica vazia.
Diretórios-pai, arquivos do projeto e integrações de outras ferramentas ficam
intactos.

## Estados e decisões

| Estado observado | Resultado | Próxima ação |
|---|---|---|
| `verified` | `planned` no dry-run; `removed` na execução | Revise o plano e aplique a remoção. |
| `outdated` | `planned` no dry-run; `removed` na execução | A skill ainda pertence ao LudoWright; remova-a se não for mais necessária. |
| `unsupported` | `planned` no dry-run; `removed` na execução | Remova a instalação intacta sem fazer downgrade ou sobrescrita. |
| `not-installed` | `not-installed`, sucesso e sem alteração relevante | Nenhuma; a remoção é idempotente. |
| `modified`, `invalid` ou `incompatible` | `conflict` / exit code `5` | Preserve os arquivos e investigue o manifesto, checksums e conteúdo extra. |
| caminho inexistente ou fora de projeto | `project-not-found` / exit code `3` | Use a raiz de um projeto descoberto pelo marker canônico. |
| symlink ou path inseguro | `invalid-input` / exit code `4` | Preserve o projeto e corrija a causa; não siga nem apague symlinks manualmente. |
| falha de filesystem | `corrupt-state` / exit code `6` | Preserve o projeto e corrija a causa; confirme o estado antes de tentar novamente. |
| falha durante a remoção | `corrupt-state` / exit code `6` | Pare, preserve a causa e confirme o rollback antes de tentar novamente. |

Uma instalação modificada nunca é tratada como descartável. Arquivos extras,
alterações manuais e manifestos inválidos exigem decisão explícita para não
apagar conteúdo do usuário.

## Reinstalar depois

Remover a skill não altera o projeto canônico. Para reinstalá-la a partir do
checkout atual:

```text
uv run ludowright --json codex skill install ./my-game --dry-run
uv run ludowright codex skill install ./my-game
uv run ludowright --json codex skill verify ./my-game
```

O `install` continua create-only: se a pasta tiver conteúdo desconhecido, ele
recusa a operação. Não use `init` novamente sobre o projeto e não copie a
skill manualmente para contornar o conflito.

## Limites e recuperação

- a remoção é local e não usa rede;
- nenhum evento, decisão, asset, referência, aprovação, documento, grafo ou
  índice SQLite é removido;
- o comando não remove o checkout, o ambiente `uv`, o pacote Python ou dados
  fora do projeto;
- falhas de escrita tentam restaurar os bytes anteriores; uma falha de
  rollback retorna `corrupt-state` e deixa o diretório para diagnóstico;
- `--dry-run` deve ser usado antes de qualquer remoção automatizada;
- não force locks e não use `rm -rf`, `git clean` ou exclusões amplas para
  recuperar uma operação.

Para detalhes normativos, consulte [Codex Skill](../contracts/CODEX_SKILL.md),
[Codex Skill CLI](../commands/CODEX.md), [CLI](../contracts/CLI.md),
[Project Filesystem](../contracts/PROJECT_FILESYSTEM.md) e o guia de
[troubleshooting](TROUBLESHOOTING.md).
