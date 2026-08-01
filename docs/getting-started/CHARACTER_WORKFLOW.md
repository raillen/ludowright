# Workflow de personagem e perfil customizado

Este guia mostra como levar um personagem do asset declarado ao plano de jobs
visuais sem esconder decisões em uma conversa. Ele usa dois caminhos já
publicados:

- `Starfall Courier`: personagem 2D com um `capture-profile` customizado;
- `Copper & Forge`: personagem humanoide que reutiliza o perfil de pacote
  `humanoid/minimal`.

O fluxo planeja trabalho e preserva o bloqueio de aprovação. Ele não executa
ImageGen e não transforma uma imagem em blueprint geométrico.

## Limites atuais

| Responsabilidade | Fonte atual |
|---|---|
| Asset, componentes e estados | `assets/registry.yaml` e contratos de asset |
| Perfil customizado | JSON v1 em `profiles/` |
| Perfil humanoide inicial | dado empacotado `humanoid/minimal` |
| Planejamento | `VisualJobPlanner` e contrato `visual-job-plan` |
| Referência e aprovação | registros de referência, receipt e review |

Ainda não existe um catálogo de perfis persistido no projeto nem um comando CLI
para selecionar perfis. O perfil deve ser validado e passado explicitamente à
camada de aplicação, como fazem os exemplos e seus testes.

## 1. Criar a base do projeto

Na raiz do checkout, inicialize um projeto novo:

```text
uv run ludowright init ./starfall-courier \
  --name "Starfall Courier" \
  --template minimal \
  --non-interactive
```

No PowerShell:

```powershell
uv run ludowright init .\starfall-courier `
  --name "Starfall Courier" `
  --template minimal `
  --non-interactive
```

Copie as entradas do exemplo somente para o projeto recém-criado. Não use uma
operação de cópia sobre um projeto que já contenha trabalho do usuário.

Linux e macOS:

```bash
cp -R examples/2d/project/. ./starfall-courier/
```

Windows PowerShell:

```powershell
Copy-Item -Path examples/2d/project/* -Destination .\starfall-courier -Recurse
```

As entradas ficam em `imports/`, `profiles/`, `requests/`, `fixtures/` e
`docs/`. O marker, o event log, o grafo e o SQLite continuam sendo os arquivos
criados pelo `init`.

## 2. Registrar o asset

Registre o asset de personagem usando o contrato canônico:

```text
uv run ludowright assets create ./starfall-courier --input imports/courier.json
```

O comando usa o caminho relativo ao projeto descoberto. Ele valida o asset,
registra a mutação no event log e atualiza somente o índice SQLite derivado.

## 3. Validar o perfil customizado

O arquivo `profiles/courier-sprite.json` é um `capture-profile` v1 genérico.
Ele declara:

- família `character`;
- câmera ortográfica;
- fundo transparente e iluminação flat;
- canvas de 256×256 pixels;
- componentes `subject` e `body`;
- estados `idle` e `run`;
- views e requests de sheet determinísticas.

O perfil é uma entrada de dados, não uma constante Python. Para validar a
combinação de asset, perfil, referência, job e request, execute o smoke test do
exemplo:

```text
uv run pytest --no-cov tests/test_2d_example.py -q
```

O teste usa `CaptureProfileContract` e o mesmo `VisualJobPlanner` consumido
por uma futura integração de projeto. A API de aplicação para um perfil
customizado é conceitualmente:

```python
from ludowright.application import VisualJobPlanner
from ludowright.contracts import CaptureProfileContract

profile = CaptureProfileContract.model_validate(profile_payload).to_domain()
plan = VisualJobPlanner().plan(plan_id, plan_name, (target,), references=references)
```

O payload deve vir de um arquivo controlado pelo projeto; não coloque regras
de perfil em prompts ou no histórico do Codex.

## 4. Planejar e respeitar a aprovação

O planejador recebe o asset, o perfil resolvido e IDs de referências
explicitamente selecionadas. Ele cria jobs determinísticos para o asset,
componentes, estados e sheets obrigatórios.

A referência do exemplo começa como `candidate`. Portanto, o plano deve conter
jobs, mas permanecer `blocked` com o código `reference-not-approved`. Isso é
intencional: uma referência candidata não pode ser usada como se fosse uma
aprovação humana.

O fluxo correto é:

```text
asset + profile + candidate reference
        ↓
deterministic visual-job plan (blocked)
        ↓ human review of the exact revision
approved reference + ready plan
        ↓
ImageGen operation, receipt, review, and technical sheet
```

O planejador é read-only. Ele não grava jobs, não chama provider, não altera o
event log e não aprova referências. Depois de uma execução real, use o workflow
[`review`](../commands/REVIEWS.md) para registrar uma decisão vinculada ao
receipt exato.

## 5. Perfil humanoide reutilizável

Para um personagem low-poly ou 3D, use o exemplo Copper & Forge. O perfil
empacotado é carregado pela aplicação:

```python
from ludowright.application import load_humanoid_profile

humanoid = load_humanoid_profile("minimal")
capture_profile = humanoid.to_capture_profile()
```

Esse perfil declara um body base obrigatório, categorias de cabelo, roupas,
calçados, acessórios, props e detalhes, além de um modo de representação
neutra. A política v1 aceita somente `neutral-bodysuit`,
`fitted-neutral-clothing` e `technical-mannequin`.

O exemplo low-poly verifica a derivação, o número de jobs segmentados e o
bloqueio das referências candidatas:

```text
uv run pytest --no-cov tests/test_low_poly_example.py -q
```

Não copie o perfil humanoide para criar uma segunda definição. Para uma
variação, crie uma entrada de dados compatível com o contrato e mantenha a
revisão explícita.

## Proveniência e revisão

Cada referência deve manter seu alvo exato, origem, revisão de conteúdo e
licença quando aplicável. Alterar imagem, prompt, perfil, views, dimensões ou
target cria uma nova especificação e normalmente um novo job; não reaproveite
uma aprovação antiga.

Aprovação continua sendo uma decisão humana. O Codex pode preparar perguntas,
planos e diagnósticos, mas não pode aprovar o próprio output.

## Limitações e próximos passos

Este guia não adiciona persistência de perfis, execução de provider, geração
de imagens ou uma nova migração. Essas fronteiras já possuem contratos
separados e devem continuar sendo compostas pela aplicação. Atualização e
remoção serão documentadas nas próximas fatias de instalação; clean-room e
readiness final permanecem na PR62.
