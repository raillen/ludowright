# ADR 0043: Deterministic Package Builder

## Status

Accepted and implemented in PR54.

## Context

O manifesto v1 já fornece uma fotografia validada dos arquivos que devem ser
empacotados. O próximo passo precisa produzir um artefato distribuível sem
introduzir timestamps, permissões, ordenação ou conteúdo variáveis, e sem
transformar uma falha parcial em um release aparentemente válido.

## Decisão

Adicionar o contrato `package-index v1` e o `PackageBuilderService`.

O serviço:

1. carrega um `package-manifest` existente e confirma seu projeto e caminho;
2. relê cada arquivo incluído usando a fronteira segura de paths do scanner;
3. bloqueia arquivos ausentes, alterados, symlinks, especiais e caminhos
   inseguros;
4. inclui o manifesto e o índice sob `__ludowright__/` no arquivo ZIP;
5. fixa timestamp ZIP, sistema de criação, permissões, compressão e ordem;
6. valida o ZIP completo e seus membros antes de persistir;
7. grava `<package-id>.zip` e `<package-id>.index.json` em um diretório de
   release fora de `.ludowright`;
8. usa lock, escrita atômica, create-only, dry-run e rollback de artefatos
   criados pela própria operação.

O índice interno não lista a si mesmo como payload. `archive_member_count`
inclui o índice e evita uma referência circular ao próprio conteúdo.

## Alternativas consideradas

### Usar o ZIP padrão diretamente

Rejeitado porque `zipfile` preencheria timestamps e metadados dependentes do
ambiente, tornando repetições diferentes.

### Copiar todo o diretório atual sem manifesto

Rejeitado porque incluiria estado transitório ou arquivos adicionados depois da
fotografia aprovada, além de perder a verificação de checksums e provenance.

### Escrever o ZIP e o índice diretamente sobre alvos existentes

Rejeitado porque uma falha ou uma execução concorrente poderia sobrescrever um
artefato revisado. Os dois alvos são create-only e uma operação parcial é
removida quando a limpeza é segura.

## Compatibilidade e migração

Esta é uma publicação aditiva de `package-index v1`. O `package-manifest v1`,
event log, dependency graph e SQLite permanecem inalterados. Não há migração.
Assinatura, auditoria global e verificação de release continuam etapas
posteriores.

## Consequências

O pacote pode ser reproduzido e auditado offline a partir do manifesto e do
índice. O builder mantém um limite de conteúdo para evitar expansão de memória
sem controle. A política de prontidão e a autorização humana ainda não são
responsabilidade desta etapa.
