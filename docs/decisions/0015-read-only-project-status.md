# ADR 0015 — Inspeção de status sem mutação

- Status: Accepted
- Date: 2026-07-29
- Decision owners: LudoWright maintainers

## Contexto

`ludowright status` precisa explicar prontidão e inconsistências sem criar um projeto,
reparar arquivos ou alterar o SQLite. O state store existente inicializa schemas e
usa WAL por padrão; abrir um banco ausente ou iniciar uma leitura WAL comum pode
criar arquivos auxiliares.

## Decisão

Adicionar uma abertura explícita `StateStore(read_only=True)` para inspeções:

- não cria diretórios ou banco;
- rejeita banco ausente, sidecar `-wal` ativo e schema incompatível;
- verifica o header SQLite para confirmar o formato WAL;
- abre a base com URI `immutable=1&mode=ro`;
- recusa todas as operações mutáveis;
- valida as mesmas tabelas, constraints e `quick_check` da abertura normal.

O comando de status trata componentes ausentes como blockers estruturados e estados
corrompidos como `corrupt-state`. Não há reparo implícito.

## Consequências

O relatório é seguro para automações e não altera o projeto. Um status concorrente
com um escritor que mantenha um WAL ativo pode falhar fechado e deve ser repetido
depois que a operação terminar. A recuperação continua sendo responsabilidade de
um comando futuro explícito, com suas próprias garantias de backup e auditoria.

Essa decisão não altera o schema SQLite, o caminho do banco, a política WAL normal ou
a autoridade dos arquivos canônicos.
