# Asset Discovery Contract

## Status

Atual. O PR33 implementa a extração determinística de candidatos a partir dos
documentos Markdown gerados do projeto e a confirmação explícita desses
candidatos no registry v1.

## Fonte e sintaxe

Por padrão, o scanner lê somente arquivos `.md` abaixo de:

```text
.ludowright/documents/**/*.md
```

Uma declaração precisa usar o marcador reservado abaixo em uma única linha:

```markdown
<!-- ludowright:asset-candidate family="character" subtype="humanoid" priority="high" --> Maya
```

`id` é opcional. Quando omitido, o ID é derivado de forma determinística pelo
prefixo da taxonomia e pelo slug do nome (`Maya` → `chr-maya`). Os atributos
permitidos são `id`, `family`, `subtype` e `priority`; todos os valores são
quotados. Declarações dentro de blocos fenced de Markdown são ignoradas.

Menções livres em texto não são convertidas automaticamente. Isso evita que
uma frase ou exemplo de documentação crie um asset canônico sem revisão.

## Candidatos e relatório

Cada candidato publicado como `asset-discovery-candidate` contém:

- ID determinístico derivado do path, linha e conteúdo da declaração;
- asset ID sugerido, nome, família, subtipo e prioridade;
- path relativo, linha e evidência original;
- estado `pending`, `ambiguous`, `confirmed` ou `rejected`.

O comando retorna um `asset-discovery-report` com candidatos, paths
escaneados, versão atual do registry, issues e assets confirmados. Os
contratos v1, schemas e fixtures estão publicados em `schemas/v1/`.

## Confirmação

Descoberta sem `--confirm` é somente leitura. A confirmação é sempre explícita
e não interativa:

```bash
ludowright assets discover PROJECT
ludowright assets discover PROJECT --confirm candidate-<sha256>
ludowright --json assets discover PROJECT --confirm candidate-<sha256>
ludowright assets discover PROJECT --confirm candidate-<sha256> --dry-run
```

O scanner pode receber `--source` repetido para limitar a leitura a paths
específicos. A confirmação reutiliza o serviço do registry e cria todos os
assets selecionados em uma única operação. O registry, o evento
`asset.discovered` e o índice SQLite são atualizados juntos pela política de
rollback já publicada.

O event log registra candidate IDs, paths e linhas de origem. Assim, a
confirmação não depende de memória da conversa e permanece auditável.

## Duplicidades e ambiguidades

- duas declarações com o mesmo asset ID tornam todos os candidatos envolvidos
  `ambiguous`;
- um ID já existente no registry torna o candidato `rejected`;
- declarações inválidas geram `invalid-declaration` e não produzem candidato;
- candidatos ausentes, ambíguos ou rejeitados nunca podem ser confirmados;
- conflitos descobertos após a leitura falham sem sobrescrever o registry.

O usuário deve corrigir o documento ou escolher uma declaração sem conflito e
executar a descoberta novamente.

## Segurança e limites

Paths são `RepositoryPath`, ficam dentro de `.ludowright/documents`, rejeitam
traversal e symlinks e usam a leitura limitada do filesystem do projeto. O
scanner não executa Markdown, não usa rede, não chama um modelo e não altera
documentos de origem. `--dry-run` não cria registry, event log, locks
persistentes ou SQLite.

## Compatibilidade

Os contratos de candidato, issue e relatório são v1. A alteração da sintaxe
de marcador, da derivação de IDs ou da semântica de confirmação exige nova
versão, fixture e política de migração. A descoberta não implementa ainda
decomposição, dependências, recomendações de capture profile ou exportação
ODS.
