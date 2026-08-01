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

Decodifique a fixture visual determinística para preparar o caminho de uma
sheet:

```bash
mkdir -p lantern-path/normalized
base64 --decode \
  examples/minimal/project/fixtures/lantern-front.png.b64 \
  > lantern-path/normalized/lantern-front.png
```

O request de folha já contém o SHA-256 dessa fixture. Porém, a fixture não é
uma referência aprovada: os arquivos `imports/lantern-job.json` e
`imports/lantern-approval.json` são entradas contratuais, não operações
aplicadas ao projeto. `sheets assemble` só pode ser executado depois que uma
execução de ImageGen criar um receipt e uma revisão humana aplicar a aprovação
da referência correspondente. Executá-lo imediatamente depois do `cp` falha
corretamente com `invalid-input`, pois a referência ainda não existe no
repositório canônico.

O fluxo completo determinístico, incluindo geração por provider fixture,
revisão, sheet, pacote, auditoria e release verification, é exercitado pelo
teste end-to-end do repositório:

```bash
uv run pytest -m end_to_end --no-cov
```

Para validar somente o projeto copiado antes da geração, execute a auditoria
estrutural:

```bash
ludowright assets audit ./lantern-path --check
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
