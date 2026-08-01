# Troubleshooting

Este guia diagnostica o caminho de instalação suportado: checkout do
repositório, `uv`, `ludowright init` e skill local do Codex. Ele não transforma
o estado atual em um pacote publicado em índice externo.

## Regra de segurança

Antes de tentar uma correção, preserve a saída do comando e não remova
`.ludowright/`, locks, `state.sqlite3` ou arquivos desconhecidos. A inicialização
e a instalação da skill são create-only e recusam conteúdo existente quando
não conseguem provar que é seguro continuar.

Para obter contexto sem modificar arquivos:

```text
uv run ludowright --json diagnostics
uv run ludowright quality check --dry-run --json
```

`diagnostics` pode ser executado fora de um projeto. Ele informa a versão,
Python, plataforma e o projeto mais próximo, mas pode expor caminhos locais;
revise e redija esses dados antes de compartilhar o resultado.

## 1. `uv`, Python e dependências

| Sintoma | Verificação | Correção segura |
|---|---|---|
| `uv` não é encontrado | `uv --version` falha | Instale o `uv` pelo procedimento oficial da plataforma, abra um novo terminal e repita a verificação. |
| Python incompatível | `uv python list` não mostra 3.12 ou superior | Execute `uv python install 3.12` e depois sincronize o checkout. |
| `uv run` não encontra dependências | `uv sync` não terminou | A partir da raiz do checkout, execute `uv sync --all-extras`; não contorne o ambiente com um Python global. |
| O comando foi executado no diretório errado | `pwd`/`Get-Location` não aponta para o checkout | Volte à raiz clonada antes de usar `uv run ludowright`. |
| A sincronização não baixa pacotes | erro de rede durante `uv sync` | Verifique proxy, DNS, certificado e política de rede local. A sincronização inicial pode precisar de rede; não desative TLS ou publique credenciais. |

Depois da sincronização, confirme:

```text
uv run ludowright --version
uv run ludowright status
```

O caminho documentado neste release é o checkout local. `pip install
ludowright` a partir de um índice externo ainda não é uma instalação suportada.

## 2. Projeto não encontrado

Comandos que operam um projeto, como `codex skill`, descobrem o marker regular:

```text
.ludowright/project.json
```

Se o comando retornar `project-not-found` com exit code `3`, passe a raiz do
projeto ou um caminho descendente dela:

```text
uv run ludowright --json codex skill verify ./my-game
```

Não crie o marker manualmente para contornar a descoberta. Use `init` em um
diretório novo e vazio, ou restaure o projeto a partir de seus arquivos
canônicos e investigue a causa antes de continuar.

Um `diagnostics` com `project.status: not-found` fora de um projeto é um estado
normal e não um erro do diagnóstico.

## 3. Falhas em `ludowright init`

Consulte primeiro o plano completo:

```text
uv run ludowright --json init ./my-game \
  --name "My Game" \
  --template minimal \
  --non-interactive \
  --dry-run
```

| Código / exit code | Significado | Ação |
|---|---|---|
| `invalid-input` / `4` | Nome inválido, traversal, separador incompatível ou symlink | Corrija o nome ou escolha um caminho local seguro. Não normalize silenciosamente o caminho. |
| `conflict` / `5` | Diretório ocupado, projeto existente, alvo que não é diretório ou inicialização concorrente | Preserve o conteúdo e use outro diretório vazio. Não execute `rm`, não apague o marker e não sobrescreva arquivos. |
| `internal-error` / `70` | Falha depois do início da escrita | A operação tenta remover somente artefatos conhecidos e diretórios vazios criados por ela. Preserve qualquer arquivo desconhecido, confirme a ausência do marker e registre a saída JSON para diagnóstico. |

O marker só é escrito depois da validação do event log, dependency graph,
SQLite e índice do projeto. A presença de
`.ludowright/project.json` significa que a operação chegou ao estado final;
um diretório sem marker não deve ser tratado como projeto válido.

Um lock deixado por interrupção não deve ser removido com base apenas na idade.
Esta versão não possui comando de recuperação de stale lock; preserve os
metadados e use outro diretório enquanto a causa é investigada.

## 4. Falhas na skill local do Codex

A instalação correta acontece dentro de um projeto já inicializado:

```text
uv run ludowright codex skill install ./my-game --dry-run
uv run ludowright codex skill install ./my-game
uv run ludowright --json codex skill verify ./my-game
```

| Código / exit code | Situação comum | Ação |
|---|---|---|
| `project-not-found` / `3` | O caminho não está dentro de um projeto descobrível | Passe `./my-game` ou um descendente válido. |
| `resource-not-found` / `3` | `update` não encontrou uma instalação | Instale a skill no projeto; `verify` usa `checks-failed` para relatar instalação ausente. |
| `checks-failed` / `1` | `verify` encontrou skill ausente, modificada, incompatível ou fora da revisão | Leia `data.state`, checksums e warnings no envelope JSON; não substitua arquivos manualmente. |
| `conflict` / `5` | Destino não vazio, conteúdo modificado, arquivo extra ou downgrade | Preserve os arquivos e compare a instalação com o manifesto. `update` e `remove` recusam alterações manuais. |
| `blocked` / `7` | A versão do framework não atende à versão mínima | Sincronize o checkout suportado e use uma skill compatível; não force a instalação. |
| `corrupt-state` / `6` | Falha de escrita ou rollback | Pare, preserve o diretório e os metadados para investigação. |

O destino canônico é `.agents/skills/ludowright/`. A skill não altera event
log, graph ou SQLite. `--dry-run` não cria lock nem diretório auxiliar.

## 5. Quality gate

Instale todos os extras antes do gate completo:

```text
uv sync --all-extras
uv run ludowright quality check --dry-run --json
uv run ludowright quality check
```

O resultado JSON mantém cada check em `data.checks`. Se o gate falhar, use o
`name`, `command` e `exit_code` do check para reproduzir somente o diagnóstico
necessário e depois rode o gate completo novamente. O exit code `1` e o código
`checks-failed` significam que a verificação executou e encontrou uma falha;
não significam que a falha possa ser ignorada.

O gate executa pre-commit, testes, publicação de schemas, ATLAS, auditoria de
documentação, build estrito do MkDocs e auditoria de dependências. Não desative
checks, reduza cobertura ou adicione exclusões para contornar uma falha.

## 6. JSON, Rich e shells

- Use exit code para controle amplo e `error.code` para automação precisa.
- Mensagens Rich são para humanos e podem mudar; códigos semânticos são o
  contrato estável.
- Erros esperados após o parsing usam o envelope `cli-response`.
- Erros de sintaxe do Typer/Click acontecem antes do callback e usam exit code
  `2`; eles não precisam produzir o envelope JSON.
- No PowerShell, use `Set-Location`, caminhos `.\my-game` e backticks para
  continuação. Em Linux e macOS, use `cd`, `./my-game` e `\`.
- Se a plataforma não permitir criar symlinks durante um teste, registre essa
  limitação do ambiente; não afrouxe a política de recusa de symlinks.

## Checklist para abrir um diagnóstico

Colete, após revisar dados sensíveis:

```text
uv --version
uv python list
uv run ludowright --json diagnostics
uv run ludowright --json quality check --dry-run
```

Inclua o comando que falhou, o exit code e `error.code`. Não inclua tokens,
credenciais, caminhos privados desnecessários ou o conteúdo integral de
manifests que possam conter dados do projeto.

Para os contratos completos, consulte [CLI](../contracts/CLI.md),
[Project Filesystem](../contracts/PROJECT_FILESYSTEM.md), [Project
Initialization](../commands/INIT.md), [Codex Skill](../commands/CODEX.md) e o
[quality baseline](../quality/ENGINEERING_QUALITY.md). Para atualizar o
checkout ou uma skill intacta, consulte [Atualização segura](UPDATING.md).
