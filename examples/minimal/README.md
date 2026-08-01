# LudoWright minimal example

Este exemplo descreve um pequeno jogo 2D chamado **Lantern Path**. Ele é
intencionalmente pequeno: uma lanterna, uma referência visual aprovada, uma
folha técnica e um pacote local.

## Executar o fluxo

O projeto precisa ser inicializado pelo PR19 antes de aplicar estas entradas:

```bash
ludowright init ./lantern-path --name "Lantern Path" --template minimal \
  --non-interactive
cp -R examples/minimal/project/. ./lantern-path/
```

Registre o asset a partir da entrada canônica:

```bash
ludowright assets create ./lantern-path \
  --input imports/lantern.json
```

Decodifique a fixture visual determinística e valide o job e a aprovação
antes de executar a geração ou aplicar uma revisão humana:

```bash
mkdir -p lantern-path/normalized
base64 --decode \
  examples/minimal/project/fixtures/lantern-front.png.b64 \
  > lantern-path/normalized/lantern-front.png
```

O request de folha já contém o SHA-256 dessa fixture:

```bash
ludowright sheets assemble requests/lantern-sheet.json sheets/lantern .
ludowright package manifest . release/package-manifest.json --package-id minimal
ludowright package build . release/package-manifest.json release
ludowright release verify . release --package-id minimal --allow-warnings --check
```

O exemplo não inclui `.ludowright/state.sqlite3`, ZIP, sheet ou receipts
gerados. Esses artefatos são derivados e devem ser criados localmente pelos
comandos, preservando a propriedade local-first e evitando estado binário
oculto no repositório.

## Conteúdo

- `project/docs/game-brief.md` — documento canônico com a declaração explícita
  do asset;
- `project/imports/lantern.json` — contrato `asset` v1;
- `project/imports/lantern-job.json` — contrato `visual-job` v1;
- `project/imports/lantern-approval.json` — contrato `approval` v1;
- `project/requests/lantern-sheet.json` — contrato `technical-sheet-request`
  v1;
- `project/fixtures/lantern-front.png.b64` — fixture PNG determinística e
  textual, adequada para revisão em Git.

O teste `tests/test_minimal_example.py` valida os contratos, o layout e o
checksum da fixture sem depender de rede, Codex ou horário do sistema.
