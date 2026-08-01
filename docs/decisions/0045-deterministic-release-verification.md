# ADR 0045: Deterministic Local Release Verification

## Status

Accepted and implemented in PR56.

## Contexto

O manifesto de pacote e o builder verificam fontes e produzem um ZIP
reproduzível, enquanto o projeto-audit descreve prontidão. Ainda faltava uma
fronteira que combinasse essas evidências, validasse o conteúdo final e
preparasse um resumo verificável para revisão ou distribuição local.

## Decisão

Adicionar `ludowright release verify PROJECT RELEASE_DIRECTORY` com:

- consumo read-only do `project-audit`;
- gates determinísticos para manifesto, índice, archive e checksums cruzados;
- política explícita `block` ou `allow` para warnings;
- contrato `release-verification` para o relatório;
- contrato `release-manifest` com SHA-256 e tamanhos dos três artefatos;
- criação atômica, create-only e protegida pelo lock `package-build`.

O verificador inspeciona o ZIP através do adapter de infraestrutura existente,
sem extrair arquivos. O manifesto de release não inclui a si mesmo e a
operação bloqueia sua criação quando o package manifest já o lista, evitando
circularidade e um pacote que não corresponde ao checksum preparado.

## Alternativas consideradas

### Regerar o pacote durante a verificação

Rejeitado: a verificação deve provar a identidade do artefato existente e não
substituir ou reconstruir uma saída aprovada silenciosamente.

### Aceitar warnings por padrão

Rejeitado: um release deve exigir uma decisão explícita para distribuir um
projeto com pendências não bloqueantes. `--allow-warnings` deixa essa decisão
visível e auditável.

### Assinar o manifesto nesta etapa

Rejeitado: assinatura exige política de chaves, identidade, confiança,
rotação, revogação e armazenamento seguro. Esta etapa prepara apenas
integridade SHA-256; assinatura e publicação são capacidades posteriores.

### Extrair o ZIP para validar seus membros

Rejeitado: a extração amplia a superfície de zip-slip e expansão de conteúdo.
O adapter existente valida bytes e metadados diretamente em memória limitada.

## Compatibilidade, migração e rollback

Os contratos `release-manifest v1` e `release-verification v1` são aditivos.
Não há migração de projetos, SQLite, event log ou dependency graph. O arquivo
de checksums é create-only; divergência gera conflito sem sobrescrever o
artefato existente. `--dry-run` não cria estado.

## Consequências

O pipeline local possui uma evidência única e verificável para a decisão de
release, enquanto o projeto-audit continua sendo a fonte das pendências de
produção. A capacidade não fornece autenticidade criptográfica nem publicação
remota; esses limites permanecem explícitos.
