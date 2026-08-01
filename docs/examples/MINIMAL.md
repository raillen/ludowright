# Minimal example

O exemplo `examples/minimal/` é a referência executável mínima do fluxo local:
um projeto 2D chamado Lantern Path, um asset de prop, um job visual, uma
aprovação pendente, uma fixture PNG e um request de folha técnica.

## Dependência de inicialização

A pasta `project/` contém entradas para um projeto recém-criado. Execute
`ludowright init` primeiro, conforme o [PR19 — Project initialization](../plans/IMPLEMENTATION_PLAN.md),
e então copie seu conteúdo para a raiz do projeto:

```bash
ludowright init ./lantern-path --name "Lantern Path" --template minimal \
  --non-interactive
cp -R examples/minimal/project/. ./lantern-path/
```

O exemplo não versiona o marker, eventos, grafo, SQLite, receipts, sheets ou
ZIP. Esses arquivos são estado canônico ou artefatos derivados e devem ser
produzidos pelas fronteiras existentes durante a execução.

## Entradas e garantias

| Entrada | Contrato | Papel |
|---|---|---|
| `docs/game-brief.md` | Markdown | documentação e declaração explícita do asset |
| `imports/lantern.json` | `asset` v1 | asset `prop-lantern` |
| `imports/lantern-job.json` | `visual-job` v1 | referência frontal |
| `imports/lantern-approval.json` | `approval` v1 | aprovação pendente para revisão humana |
| `requests/lantern-sheet.json` | `technical-sheet-request` v1 | folha de prop |
| `fixtures/lantern-front.png.b64` | fixture textual | PNG 1×1 e SHA-256 conhecido |

O smoke test valida todos os contratos, o marcador de asset, a geometria e o
checksum da fixture. Não depende de rede, Codex, provider ou relógio do
sistema. O README do exemplo contém os comandos para criar a sheet, o pacote
e a verificação de release.

Compatibilidade: o exemplo usa somente contratos v1 já publicados e não
introduz migração ou schema próprio.
