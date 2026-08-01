# Codex Skill CLI

## Instalação

Instale a skill local em um projeto LudoWright existente:

```bash
ludowright codex skill install /caminho/do/projeto
```

O comando grava somente `.agents/skills/ludowright/manifest.json` e
`.agents/skills/ludowright/SKILL.md`. Um destino não vazio ou alterado é
recusado.

Para revisar o plano sem alterar o projeto:

```bash
ludowright codex skill install /caminho/do/projeto --dry-run
ludowright --json codex skill install /caminho/do/projeto --dry-run
```

O dry-run não cria o lock nem diretórios auxiliares.

## Verificação e atualização

```bash
ludowright codex skill verify /caminho/do/projeto
ludowright --json codex skill verify /caminho/do/projeto
ludowright codex skill update /caminho/do/projeto
```

`verify` confere o manifesto, os checksums, o ID, o caminho, a revisão e a
compatibilidade com a versão instalada do LudoWright. Uma instalação ausente,
desatualizada ou modificada retorna `checks-failed` com o relatório completo em
`data` no modo JSON.

`update` só atualiza uma versão antiga que ainda esteja intacta. Alterações
manuais, arquivos extras, symlinks e uma versão mais nova bloqueiam a operação.

## Remoção

```bash
ludowright codex skill remove /caminho/do/projeto
ludowright codex skill remove /caminho/do/projeto --dry-run
```

A remoção é segura e idempotente: uma skill ausente resulta em
`not-installed`; uma instalação modificada não é apagada. A pasta da skill é
removida somente quando fica vazia.

## Saída JSON

```bash
ludowright --json codex skill verify /caminho/do/projeto
```

O resultado usa o envelope `cli-response` e inclui um `codex-skill-report` com
`operation`, `state`, `dry_run`, `skill_id`, `skill_version`,
`installed_version`, `install_path`, arquivos com checksums, warnings e
`valid`.

## Falhas esperadas

- `project-not-found`: o caminho não pertence a um projeto LudoWright;
- `conflict`: instalação modificada, destino não vazio ou downgrade;
- `resource-not-found`: atualização sem skill instalada;
- `blocked`: versão do framework abaixo do mínimo;
- `checks-failed`: verificação encontrou estado inválido;
- `corrupt-state`: falha de escrita e rollback.

As mensagens humanas podem evoluir; os códigos e exit codes permanecem os
contratos para automação.
