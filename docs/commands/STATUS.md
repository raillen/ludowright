# `ludowright status`

## Como usar

Mostra a prontidão operacional do projeto LudoWright mais próximo:

```bash
ludowright status
ludowright status ./meu-jogo
ludowright --json status ./meu-jogo
```

O argumento opcional pode apontar para um diretório ou arquivo dentro do projeto. Sem
argumento, a descoberta começa no diretório atual e segue até o marker canônico
`.ludowright/project.json`.

## O que é verificado

O comando é somente leitura. Ele valida:

- manifesto do projeto contra o contrato publicado;
- replay e integridade do event log;
- dependency graph e seus estados de frescor;
- SQLite state store na versão suportada;
- consistência entre o event log, os arquivos indexados e o SQLite.

O resultado usa três estados de prontidão:

- `ready`: os componentes obrigatórios estão consistentes e não há saída obsoleta;
- `needs-review`: há dependências que exigem revisão, mas não invalidam a saída;
- `blocked`: há um blocker de consistência ou uma saída stale.

O estágio exibido em `readiness.stage` é o estágio de produção do manifesto. Ele não
significa que o projeto está pronto para lançamento.

## JSON e erros

O modo JSON reutiliza o envelope `cli-response`:

```bash
ludowright --json status ./meu-jogo
```

`data` contém `project`, `readiness`, `components`, `blockers`, `stale_outputs`,
`recommended_actions`, `consistency` e `project_directory`.

Fora de um projeto, o comando retorna `project-not-found` com exit code `3`. Um
manifesto, log, grafo ou banco que não possa ser validado retorna `corrupt-state` com
exit code `6`. Nenhum desses caminhos cria ou repara arquivos.

## Segurança e limites

O state store é aberto em modo SQLite read-only e não é criado se estiver ausente. Um
WAL ativo impede a inspeção imutável; nesse caso o status falha fechado para evitar
criar sidecars ou ler uma revisão incompleta. A correção permanece uma operação
explícita futura.
