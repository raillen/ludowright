# Image Normalization Contract

## Purpose

`image-normalization` v1 descreve os artefatos derivados de uma imagem local.
Ele prepara uma imagem para as próximas etapas visuais sem alterar a referência
de origem, aprovação, job, receipt, grafo ou SQLite.

O contrato publicado é `schemas/v1/image-normalization.schema.json` e o modelo
fonte está em `src/ludowright/contracts/image_normalization.py`. As regras de
publicação estão em [`JSON Schema Publication`](JSON_SCHEMAS.md).

## Entradas

O normalizador aceita uma imagem regular e local nos formatos PNG, JPEG ou WebP.
O caminho precisa ser um `RepositoryPath` relativo, ASCII, normalizado e sem
symlinks. A leitura é limitada a 64 MiB e 64 milhões de pixels; cada dimensão
fica limitada a 16.384 pixels. Imagens animadas, inválidas ou sem pixels
visíveis são rejeitadas.

Quando há canal alfa, o conteúdo visível define o recorte. Uma imagem opaca é
tratada como um quadro completo: o normalizador não tenta adivinhar a silhueta
ou remover um fundo de forma geométrica.

## Saídas

Cada execução cria quatro PNGs e um relatório JSON no diretório informado:

```text
normalized.png       # canvas RGBA transparente
neutral.png          # canvas composto no fundo neutro escolhido
thumbnail.png        # miniatura RGBA quadrada
alignment-guide.png  # canvas RGBA com eixos e bounding box
normalization.json   # contrato image-normalization v1
```

O canvas padrão é `1024x1024`, com padding mínimo de 64 pixels e miniatura de
`256x256`. `--width`, `--height`, `--padding`, `--thumbnail-size` e
`--neutral-background` permitem ajustar esses valores dentro dos limites
publicados. O relatório registra as dimensões de origem e destino, orientação
EXIF, padding real, bounding box, cor neutra, caminhos, tamanhos e checksums.

## Orientação e determinismo

As orientações EXIF 1–8 são aplicadas aos pixels e removidas dos PNGs gerados;
o relatório registra o valor original e se houve transformação. Metadados
operacionais e EXIF não são propagados para os outputs. A codificação PNG usa
opções fixas, e o ID da operação é derivado do checksum da entrada, caminhos e
opções.

## Segurança e ciclo de vida

- a operação usa o lock de projeto `image-normalization`;
- os destinos são create-only: arquivos existentes nunca são sobrescritos;
- repetir exatamente a mesma operação retorna `unchanged` quando todos os
  bytes e o relatório coincidem;
- targets parciais ou com conteúdo diferente resultam em conflito;
- cada arquivo é escrito atomicamente e o relatório é o último artefato;
- uma falha remove somente arquivos e diretórios criados pela operação;
- `--dry-run` decodifica e planeja sem criar arquivos;
- outputs normalizados são derivados, não aprovados automaticamente.

O relatório não é projetado no event log ou no SQLite nesta etapa. A montagem
de turnarounds e technical sheets pertence ao PR52.

## Compatibilidade

O contrato é v1 e não altera formatos existentes, migrações ou o state store.
Novas propriedades incompatíveis exigirão uma versão posterior e fixtures de
compatibilidade adicionais.
