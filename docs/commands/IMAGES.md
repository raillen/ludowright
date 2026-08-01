# Images CLI

## Normalizar uma imagem

```bash
ludowright images normalize references/maya/front.png normalized/maya/front .
ludowright images normalize references/maya/front.jpg normalized/maya/front . --width 1024 --height 1024 --padding 64 --thumbnail-size 256
```

A forma completa é:

```text
ludowright images normalize INPUT OUTPUT_DIRECTORY [PROJECT]
```

O comando aceita PNG, JPEG e WebP como entrada e cria quatro PNGs mais
`normalization.json`. A imagem é orientada conforme EXIF, ajustada ao canvas
com padding, e a variante `neutral.png` recebe a cor informada em
`--neutral-background` (padrão `#F2F2F2`).

O caminho do projeto pode ser relativo ou absoluto, mas a entrada e o diretório
de saída precisam permanecer dentro da raiz descoberta. Traversal, caminhos
não normalizados e symlinks são rejeitados.

## Dry-run e repetição

```bash
ludowright images normalize references/maya/front.png normalized/maya/front . --width 512 --height 512 --padding 32 --thumbnail-size 128 --dry-run
ludowright --json images normalize references/maya/front.png normalized/maya/front .
```

`--dry-run` valida a imagem e mostra o plano sem criar a pasta de saída. A
operação real é determinística e idempotente para o mesmo conteúdo, caminho e
opções: uma repetição exata retorna `unchanged`. Qualquer target parcial ou
alterado é um conflito e não é sobrescrito.

## Saída

O modo humano usa Rich. O modo `--json` usa o envelope `cli-response` e inclui
`state`, `dry_run`, `source_path`, `report_path`, os paths planejados/criados e
o relatório `image-normalization` completo. Falhas esperadas usam os códigos
publicados em [`CLI Contract`](../contracts/CLI.md).

## Validação

```bash
uv run pytest --no-cov tests/test_image_normalization.py -q
uv run ludowright images normalize --help
```
