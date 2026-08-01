# Atualização segura

Este guia cobre os dois updates suportados no estado atual:

1. atualizar o checkout, o ambiente `uv` e as ferramentas do LudoWright;
2. atualizar a skill `$ludowright` instalada dentro de um projeto.

Não existe um comando `ludowright update` para alterar um projeto inteiro e
não há migração automática de projeto nesta etapa. Não execute `init` novamente
sobre um projeto existente.

## Antes de atualizar

Registre o estado do checkout e do projeto sem modificar arquivos:

```text
git status --short
uv run ludowright --json diagnostics
uv run ludowright --json codex skill verify ./my-game
```

Se o checkout tiver alterações locais, preserve-as com um commit ou outro
procedimento de versionamento aprovado antes de buscar mudanças remotas. Não
use `git reset --hard`, `git clean` ou remoção manual para “destravar” um
update.

## 1. Atualizar o checkout e o ambiente

Na branch de trabalho autorizada, atualize somente quando o histórico puder
avançar sem merge implícito:

Linux e macOS:

```bash
cd ludowright
git status --short
git fetch origin
git pull --ff-only
uv sync --all-extras
uv run ludowright --version
```

Windows PowerShell:

```powershell
Set-Location ludowright
git status --short
git fetch origin
git pull --ff-only
uv sync --all-extras
uv run ludowright --version
```

`git pull --ff-only` recusa divergências em vez de criar um merge inesperado.
Se falhar, preserve a branch e examine `git status`, `git branch -vv` e a
política do repositório antes de decidir entre commit, rebase ou outra ação.
Não force a atualização.

`uv sync --all-extras` atualiza o ambiente para as dependências declaradas pelo
checkout. A instalação inicial pode usar a rede; depois disso, os comandos do
núcleo continuam locais.

## 2. Atualizar a skill do projeto

Depois de atualizar o checkout, verifique a instalação atual:

```text
uv run ludowright --json codex skill verify ./my-game
```

Planeje antes de escrever:

```text
uv run ludowright --json codex skill update ./my-game --dry-run
```

Aplique somente depois de revisar o relatório:

```text
uv run ludowright codex skill update ./my-game
uv run ludowright --json codex skill verify ./my-game
```

O update usa o lock `codex-skill`, escreve os payloads atomicamente e grava o
manifesto por último. Uma falha restaura os bytes anteriores. O update não
altera event log, dependency graph, SQLite ou arquivos canônicos do projeto.

## Estados e decisões

| Estado observado | Resultado do update | Próxima ação |
|---|---|---|
| `verified` | `already-up-to-date`, sucesso e sem alteração | Nenhuma; a skill já corresponde ao checkout. |
| `outdated` | `planned` no dry-run e `updated` na execução | Revise o relatório e execute o update. |
| `not-installed` | `resource-not-found` / exit code `3` | Use `codex skill install`; update não instala uma skill ausente. |
| `modified` ou `invalid` | `conflict` / exit code `5` no update; `checks-failed` / exit code `1` no verify | Preserve a instalação e investigue checksums, manifesto e arquivos extras. |
| `unsupported` ou `incompatible` | `conflict` / exit code `5` | Não faça downgrade nem force a substituição; use uma versão compatível do checkout. |
| framework incompatível | `blocked` / exit code `7` | Atualize o ambiente para atender à versão mínima publicada. |
| falha de escrita/rollback | `corrupt-state` / exit code `6` | Pare e preserve o diretório para diagnóstico; não remova arquivos manualmente. |

`update` só substitui uma instalação intacta e mais antiga. Alterações manuais,
symlinks e arquivos extras nunca são sobrescritos silenciosamente. `--dry-run`
não cria lock nem altera a skill.

## 3. Validar o resultado

Após atualizar o checkout e a skill:

```text
uv run ludowright --json codex skill verify ./my-game
uv run ludowright --json diagnostics
uv run ludowright quality check --dry-run --json
```

Para uma atualização do próprio checkout, execute o gate completo:

```text
uv run ludowright quality check
```

Use o exit code para controle amplo e `error.code` para automação precisa. O
texto Rich é uma apresentação humana; `data.state`, `data.warnings` e os
checksums do envelope JSON são a evidência estável.

## Recuperação conservadora

| Situação | O que fazer |
|---|---|
| Checkout com alterações locais | Pare o update e preserve as alterações em versionamento. |
| `git pull --ff-only` recusou a branch | Não force nem faça reset; investigue a divergência e escolha uma estratégia explícita. |
| Rede falhou no `git fetch` ou `uv sync` | Corrija a rede/proxy/certificados e repita; não desative TLS nem publique credenciais. |
| Skill modificada | Preserve os arquivos, compare o manifesto e decida manualmente como recuperar; `update` não sobrescreve. |
| Update falhou no meio | Verifique a skill e preserve a causa; o contrato tenta restaurar a revisão anterior. |
| Projeto antigo exige migração | Não invente uma migração nem apague o SQLite; consulte a [matriz de compatibilidade publicada](../contracts/MIGRATIONS.md) antes de qualquer atualização. |

Em POSIX use `./my-game`; no PowerShell use `.\my-game`. O caminho da skill é
sempre `.agents/skills/ludowright/` dentro do projeto descoberto.

Para detalhes normativos, consulte [Codex Skill](../contracts/CODEX_SKILL.md),
[Codex Skill CLI](../commands/CODEX.md), [CLI](../contracts/CLI.md),
[Project Filesystem](../contracts/PROJECT_FILESYSTEM.md) e o
[quality baseline](../quality/ENGINEERING_QUALITY.md). Para remover a skill
sem apagar o projeto, consulte [Remoção segura](UNINSTALLING.md).
