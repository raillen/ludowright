# Release Verification CLI

Verifique um pacote local e prepare seu manifesto de checksums com:

```bash
ludowright release verify PROJECT RELEASE_DIRECTORY
```

Quando houver mais de um pacote no diretório, selecione o pacote explicitamente:

```bash
ludowright release verify ./my-game release \
  --package-id nightly --allow-warnings --check
```

O primeiro comando também funciona quando existe exatamente um índice
`<package-id>.index.json` no diretório.

## O que é verificado

O comando executa a auditoria global e valida, sem extração do ZIP:

- identidade do projeto e do pacote;
- manifesto v1 e índice v1 canônicos;
- caminhos declarados e checksums;
- ordenação, metadados, compressão e quantidade de membros do ZIP;
- cópia interna do manifesto e do índice;
- correspondência entre arquivos do manifesto, índice e archive.

Quando os gates permitem, cria:

```text
release/<package-id>.release.json
```

Esse arquivo lista SHA-256 e tamanhos do manifesto, índice e ZIP. Ele não é
assinado e não deve ser incluído no package manifest usado para construir o
próprio pacote.

## Warnings, dry-run e idempotência

Warnings bloqueiam por padrão. Use `--allow-warnings` somente quando a política
de release aceitar explicitamente um estado `ready-with-warnings`. Erros nunca
são liberados por essa opção.

`--dry-run` calcula o relatório e o manifesto esperado sem criar o arquivo ou
o lock. A execução real é create-only: retorna `created` na primeira gravação,
`unchanged` quando os bytes já são idênticos e conflito quando o arquivo
existente diverge.

Para automação:

```bash
ludowright --json release verify ./my-game release --package-id nightly --check
ludowright --json release verify ./my-game release --package-id nightly \
  --allow-warnings --dry-run
```

O JSON usa o envelope `cli-response`. Sem `--check`, o relatório completo é
retornado mesmo quando está `blocked`; com `--check`, o resultado inválido usa
`checks-failed` e exit code 1. Paths inseguros, estado corrompido e conflitos
usam os códigos e exit codes publicados da CLI.

## Limitações

Esta etapa não assina, publica, extrai ou instala artefatos. A assinatura
criptográfica exige uma decisão posterior sobre chaves, confiança e rotação.
