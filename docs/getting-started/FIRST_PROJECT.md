# Primeiro projeto

Este tutorial cria um projeto LudoWright mínimo e local-first a partir de um
checkout já instalado. Os comandos são não interativos e podem ser repetidos
com outro diretório.

## 1. Conferir o plano sem escrever

Na raiz do checkout, faça um dry-run:

```bash
uv run ludowright --json init ./my-game-preview \
  --name "My Game" \
  --template minimal \
  --non-interactive \
  --dry-run
```

O resultado usa o envelope `cli-response`, informa o `ProjectId`, o template,
os arquivos previstos, as versões de schema e `dry_run: true`. O diretório
`my-game-preview` não é criado.

No PowerShell, a mesma operação usa a continuação de linha da própria shell:

```powershell
uv run ludowright --json init .\my-game-preview `
  --name "My Game" `
  --template minimal `
  --non-interactive `
  --dry-run
```

## 2. Criar o projeto

Crie o diretório definitivo:

```text
uv run ludowright init ./my-game --name "My Game" --template minimal --non-interactive
```

No Windows, use `.\\my-game` no lugar de `./my-game` quando preferir a
sintaxe nativa do PowerShell.

O comando retorna sucesso somente depois de validar o manifesto, o event log,
o dependency graph e o SQLite state store. O `ProjectId` derivado de
`My Game` é `my-game`.

## 3. Conferir os arquivos canônicos

O template `minimal` cria esta base:

```text
my-game/
├── .ludowright/
│   ├── dependency-graph.json
│   ├── events.jsonl
│   ├── project.json
│   └── state.sqlite3
├── assets/
├── decisions/
├── docs/
├── references/
└── visual-jobs/
```

O arquivo `.ludowright/project.json` é o marker canônico. O SQLite é um índice
derivado e pode ser reconstruído pelas rotinas de persistência; decisões,
documentos, assets e referências devem continuar nos arquivos canônicos do
projeto.

## 4. Instalar a skill local do Codex

Se o projeto for usado com Codex, instale a skill a partir da raiz do checkout:

```text
uv run ludowright codex skill install ./my-game
uv run ludowright codex skill verify ./my-game
```

A instalação fica em `my-game/.agents/skills/ludowright/`, é versionada,
verificável por checksum e não altera o event log, o grafo ou o SQLite. O
contrato completo está em [Codex Skill](../contracts/CODEX_SKILL.md).

## Repetição e falhas

- `--dry-run` não cria diretórios, locks ou arquivos;
- o comando recusa um diretório não vazio ou um projeto já existente;
- repetir o mesmo comando no diretório criado resulta em `conflict`, não em
  sobrescrita silenciosa;
- após uma falha intermediária, os artefatos conhecidos da inicialização são
  removidos e arquivos desconhecidos são preservados;
- para um novo teste, escolha outro diretório, como `./my-game-second`.

Erros esperados devem ser tratados pelo código semântico do envelope JSON,
principalmente `invalid-input`, `conflict` e `internal-error`; mensagens
humanas podem evoluir.

## Continuação

O [exemplo mínimo](../examples/MINIMAL.md) fornece entradas contratuais para um
fluxo 2D completo. Os tutoriais de personagem, perfil customizado,
troubleshooting avançado, atualização e remoção serão adicionados nas próximas
fatias da etapa de instalação e tutoriais.
