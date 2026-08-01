# ADR 0040: Deterministic Image Normalization Boundary

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `IMAGE_NORMALIZATION.md`, `CAPTURE_PROFILES.md`, `PROJECT_FILESYSTEM.md`, `CLI.md`

## Context

ImageGen já produz PNGs válidos e receipts rastreáveis, mas as etapas de sheets
precisam de dimensões, orientação, padding e previews consistentes. O
normalizador deve ser local, determinístico e seguro sem confundir um output
derivado com uma referência aprovada.

## Decision

1. Usar Pillow somente na infraestrutura de processamento de imagens; o
   domínio e o core não importam o codec.
2. Aceitar PNG, JPEG e WebP limitados, aplicar orientação EXIF e produzir
   exclusivamente PNGs sem transportar metadados de origem.
3. Gerar um canvas transparente, uma composição neutra, uma miniatura e uma
   imagem com guias de alinhamento, acompanhados pelo relatório
   `image-normalization` v1.
4. Persistir sob o lock de projeto existente, com paths relativos, escrita
   atômica, create-only, dry-run e rollback dos artefatos da operação.
5. Manter o relatório e os PNGs como artefatos derivados; aprovação, event log,
   SQLite e montagem de sheets permanecem em etapas posteriores.

## Alternatives considered

### Implementar decodificação PNG própria

Rejeitado: aumentaria a superfície de parser e não cobriria orientação EXIF de
formatos de entrada sem duplicar uma biblioteca madura.

### Alterar a referência aprovada durante a normalização

Rejeitado: normalização é uma transformação derivada. Uma nova referência ou
aprovação deve passar pelo workflow de review correspondente.

### Sobrescrever outputs para facilitar reexecuções

Rejeitado: um target modificado pode ser um artefato aprovado ou uma evidência
de intervenção manual. O comportamento seguro é `unchanged` para bytes iguais
e conflito para qualquer divergência.

## Consequences

### Positive

- dimensões e padding podem ser consumidos pelo PR52;
- previews e guias são reproduzíveis sem provider;
- orientação e checksums ficam registrados no relatório;
- entradas grandes, animadas, inválidas e symlinks falham de forma segura;
- a operação não deixa uma saída parcial aparentemente válida.

### Negative

- a silhueta de imagens opacas não é inferida automaticamente;
- a primeira versão gera apenas PNGs e não preserva metadados EXIF;
- os outputs ainda não são indexados nem aprovados automaticamente.

## Compatibility and migration

O relatório é uma nova publicação v1 e possui fixture/schema. Nenhum documento
existente, evento, tabela SQLite ou migração é alterado.
