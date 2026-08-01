# Package Build Contract

## Purpose

O contrato `package-index` descreve um pacote ZIP reproduzível criado a partir
de um `package-manifest` validado. Ele é um índice de conteúdo, não uma
assinatura nem uma declaração de prontidão para release.

O schema v1 publicado é:

```text
schemas/v1/package-index.schema.json
```

## Conteúdo

Cada índice registra:

- `package_id` e `project_id` estáveis;
- caminho e checksum exatos do manifesto usado;
- caminhos relativos do ZIP e do índice externo;
- política fixa de compressão `deflate`;
- timestamp ZIP fixo em `1980-01-01T00:00:00`;
- todos os arquivos do manifesto e uma cópia do manifesto dentro do ZIP;
- tamanho e SHA-256 de cada entrada descrita;
- quantidade total de membros, incluindo o próprio índice interno;
- tamanho descompactado dos itens descritos.

O índice interno fica em:

```text
__ludowright__/package-index.json
```

O manifesto usado fica em:

```text
__ludowright__/package-manifest.json
```

O índice não lista a si mesmo como payload para evitar uma referência
autocircular. `archive_member_count` inclui esse membro adicional.

## Construção segura

`PackageBuilderService` valida o manifesto, confirma o `project_id` contra o
marker atual e relê cada arquivo incluído através do scanner seguro do pacote.
Arquivos ausentes ou com tamanho/checksum diferente bloqueiam a construção.
Symlinks, arquivos especiais, traversal e caminhos fora do projeto são
rejeitados.

O escritor ZIP:

- aceita somente entradas regulares e ASCII dentro do limite de paths;
- ordena membros lexicalmente;
- fixa timestamp, sistema de criação, permissões e nível de compressão;
- rejeita duplicatas, diretórios, metadados variáveis e conteúdo divergente;
- limita quantidade e tamanho total das entradas;
- valida o ZIP completo antes de qualquer persistência.

## Diretório de release e idempotência

O comando cria, por exemplo:

```text
release/nightly.zip
release/nightly.index.json
```

O diretório é relativo ao projeto e não pode estar sob `.ludowright`. Os dois
arquivos são create-only:

- primeira execução: `state: created`;
- repetição byte a byte: `state: unchanged`;
- alvo parcial ou conteúdo diferente: `conflict`, sem sobrescrita.

O índice externo é gravado depois do ZIP e funciona como segundo artefato da
operação. Se uma escrita falhar, os arquivos e diretórios criados pela própria
execução são removidos; falhas de limpeza preservam a causa original e geram
erro de rollback.

`--dry-run` valida todas as entradas, renderiza o ZIP e calcula o índice, mas
não cria lock, diretório ou arquivo.

## Compatibilidade

O builder consome `package-manifest v1` sem alterá-lo. Não há migração de
projetos, event log, dependency graph ou SQLite. Mudanças incompatíveis no
índice exigem nova versão de schema, fixture, publicação e ADR.

Assinatura, auditoria de prontidão, verificação de release e publicação ficam
fora desta etapa e pertencem aos PRs seguintes.
