# `ludowright init`

## Como usar

Inicializa um projeto LudoWright novo em um diretório local:

```bash
ludowright init PATH --name "Nome do Jogo" --non-interactive
```

O template inicial pode ser selecionado explicitamente:

```bash
ludowright init PATH --name "Nome do Jogo" --template minimal --dry-run
```

Para automações, use o envelope JSON publicado:

```bash
ludowright --json init PATH --name "Nome do Jogo" --non-interactive
```

## Resultado

O template `minimal` é versionado como dado em `src/ludowright/templates/minimal.json`.
Ele cria:

- o manifesto `.ludowright/project.json`;
- `.ludowright/events.jsonl`, inicialmente vazio e válido para replay;
- `.ludowright/dependency-graph.json`, com o nó do projeto;
- `.ludowright/state.sqlite3`, na versão de schema atual (`2`);
- diretórios iniciais para documentos, assets, referências, decisões e visual jobs.

O `ProjectId` é derivado deterministicamente do nome por `slugify()`. O manifesto também registra o ID e a versão do template escolhido.

## Dry-run e idempotência

`--dry-run` valida nome, template, caminho e conflito sem criar diretórios ou arquivos. A saída lista os caminhos planejados.

`init` é uma operação create-only. Um diretório inexistente ou vazio pode ser inicializado. Um diretório não vazio, um projeto existente ou uma execução concorrente são recusados; o comando nunca completa, repara ou sobrescreve um projeto existente.

## Segurança e falhas

O caminho pode ser relativo ou absoluto, mas traversal (`..`), componentes simbólicos e alvos que não sejam diretórios são recusados. A operação usa lock exclusivo, escritas atômicas dos artefatos e publica o manifesto por último. Se uma etapa intermediária falhar, os artefatos gerados são removidos e a causa original fica encadeada no erro de aplicação.

O event log inicial não recebe um evento artificial: um arquivo vazio é um log válido e preserva determinismo. O primeiro caso de uso que alterar o projeto poderá acrescentar o primeiro evento normalmente.

## Saída JSON

O campo `data` do envelope `cli-response` contém:

- `project_directory`, `project_id` e `template`;
- `files` e `directories` planejados ou criados;
- `schema_version`, `dry_run`, `warnings` e `state` (`planned` ou `created`).

Conflitos usam `conflict` e código de processo `5`; entradas inválidas usam `invalid-input` e código `4`; falhas inesperadas após rollback usam `internal-error` e código `70`.
