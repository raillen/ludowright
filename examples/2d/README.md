# LudoWright 2D sprite example

Este exemplo descreve **Starfall Courier**, um jogo 2D de sprites com uma
personagem jogável e estados `idle` e `run`. Ele demonstra como um projeto pode
declarar um perfil de captura específico para sprites e planejar jobs sem
depender de um provider 3D.

## Executar o fluxo

O projeto precisa ser inicializado pelo PR19 antes de aplicar estas entradas:

```bash
ludowright init ./starfall-courier --name "Starfall Courier" \
  --template minimal --non-interactive
cp -R examples/2d/project/. ./starfall-courier/
```

Registre o asset:

```bash
ludowright assets create ./starfall-courier --input imports/courier.json
```

Valide os contratos do perfil, asset, referência, job, aprovação e request da
sheet com o teste determinístico do exemplo:

```bash
uv run pytest --no-cov tests/test_2d_example.py -q
```

O perfil customizado exige `subject`, `body`, `idle` e `run`. O planejador
deriva jobs para o asset, o componente e os estados, mas reporta um blocker
porque a referência ainda está `candidate`. A aprovação deve ser produzida
pela revisão humana correspondente antes de qualquer uso como input aprovado.

## Conteúdo

- `project/docs/game-brief.md` — documento canônico com o marcador de asset;
- `project/profiles/courier-sprite.json` — `capture-profile` v1 customizado;
- `project/imports/courier.json` — contrato `asset` v1;
- `project/imports/courier-reference.json` — contrato `visual-reference` v1;
- `project/imports/courier-job.json` — contrato `visual-job` v1;
- `project/imports/courier-approval.json` — aprovação pendente v1;
- `project/requests/courier-sheet.json` — request de technical sheet v1;
- `project/fixtures/courier-front.png.b64` — fixture PNG textual determinística.

O exemplo não versiona marker, eventos, grafo, SQLite, receipts, imagens
normalizadas ou sheets. Esses artefatos devem ser criados pelas fronteiras
existentes quando as pré-condições de aprovação forem satisfeitas.
