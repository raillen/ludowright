# Release Verification Contract

O verificador local fecha a fronteira entre um pacote reproduzível e uma
declaração de release. Ele consome o `project-audit`, o manifesto de pacote,
o índice externo e o ZIP; não corrige o projeto, publica arquivos remotamente
nem transforma checksums em assinatura.

## Artefatos publicados

Os contratos v1 são:

```text
schemas/v1/release-manifest.schema.json
schemas/v1/release-verification.schema.json
```

`release-manifest` é um manifesto create-only com SHA-256 e tamanho exato de:

- `package-manifest`;
- `package-index`;
- `package-archive`.

Ele também registra o projeto, o pacote, o diretório de release, o próprio
caminho do manifesto e a quantidade de membros do ZIP. O manifesto não inclui
a si mesmo e não pode ser listado como payload do `package-manifest`; isso
evita uma referência circular.

## Gates e warnings

O relatório `release-verification` valida:

1. auditoria global do projeto;
2. manifesto e índice canônicos;
3. caminhos e identidade do pacote;
4. ZIP canônico, ordenado e com metadados fixos;
5. membros, manifesto interno, índice interno e checksums cruzados;
6. manifesto de checksums do release.

Cada gate é `passed`, `warning` ou `failed`. A política padrão é `block`:
warnings também impedem um release válido. `--allow-warnings` muda a política
para `allow` e produz `ready-with-warnings`; erros continuam bloqueando.

O relatório usa `ready`, `ready-with-warnings` ou `blocked`. `valid` só é falso
quando o estado é `blocked`. `--check` converte um resultado inválido no
envelope `checks-failed` com exit code 1.

## Segurança e concorrência

O verificador usa a fronteira de paths e o scanner de pacotes existentes,
rejeita traversal, symlinks, arquivos especiais e leituras acima dos limites.
A verificação e a criação do manifesto usam o lock `package-build`; o ZIP é
inspecionado sem extraí-lo. O manifesto é escrito atomicamente e create-only:
uma repetição idêntica é `unchanged`, enquanto bytes divergentes são conflito.

`--dry-run` não cria lock, diretório, arquivo ou sidecar. Uma alteração dos
arquivos observados é tratada como conflito pelo `project-audit` ou como gate
falho quando ocorre na validação do pacote.

## Compatibilidade

Os contratos são aditivos em `v1`. Nenhuma migração de projeto, event log,
dependency graph ou SQLite é necessária. O campo `integrity: sha256` descreve
verificação de integridade; assinatura digital, chaves, rotação, revogação e
publicação remota permanecem fora desta etapa.
