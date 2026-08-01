# LudoWright low-poly 3D example

Este exemplo descreve **Copper & Forge**, um fluxo local-first de referências
low-poly para uma personagem humanoide e um edifício. Ele mostra componentes
segmentados, estados construtivos e o limite de aprovação antes da geração.

## Executar o fluxo

O projeto precisa ser inicializado pelo PR19 antes de aplicar estas entradas:

```bash
ludowright init ./copper-and-forge --name "Copper & Forge" \
  --template minimal --non-interactive
cp -R examples/low-poly-3d/project/. ./copper-and-forge/
```

Registre os assets:

```bash
ludowright assets create ./copper-and-forge --input imports/copper.json
ludowright assets create ./copper-and-forge --input imports/forge-building.json
```

Os testes demonstram o planejamento com os perfis empacotados:

```bash
uv run pytest --no-cov tests/test_low_poly_example.py -q
```

O perfil humanoide cobre corpo-base, roupas e calçados. O perfil de edifício
cobre raiz, telhado, aberturas e os estados `closed` e `construction`. Em ambos
os casos a referência da fixture está `candidate`; o plano não fica pronto até
que a aprovação correspondente seja aplicada à mesma revisão.

## Conteúdo

- `project/docs/game-brief.md` — documento canônico e dois marcadores de asset;
- `project/imports/copper.json` — asset humanoide segmentado;
- `project/imports/forge-building.json` — edifício com estados construtivos;
- `project/imports/*-reference.json` — referências capturadas candidatas;
- `project/imports/*-job.json` — jobs imutáveis com views low-poly;
- `project/imports/*-approval.json` — aprovações pendentes;
- `project/requests/*-sheet.json` — requests de sheets com checksums;
- `project/fixtures/*.png.b64` — fixtures PNG textuais determinísticas.

Não são versionados marker, imagens normalizadas, sheets, receipts, ZIPs ou
qualquer estado derivado do projeto.
