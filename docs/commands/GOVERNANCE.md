# Comandos de decisões e aprovações

O LudoWright mantém decisões e aprovações como históricos lógicos imutáveis. O
arquivo canônico de uma decisão fica em `decisions/<id>.json`; uma solicitação de
aprovação fica em `approvals/<id>.json`. Os IDs são slugs canônicos e nunca são
derivados silenciosamente de um título ou nome.

## Decisões

Registre uma decisão proposta:

```bash
ludowright decision record ./my-game \
  --id camera-choice \
  --title "Usar câmera isométrica" \
  --note "Direção inicial para a pré-produção."
```

Consulte a coleção ou um histórico completo:

```bash
ludowright decision list ./my-game
ludowright decision inspect ./my-game camera-choice
```

Transições válidas são registradas como novas entradas no histórico:

```bash
ludowright decision transition ./my-game camera-choice --status accepted
ludowright decision transition ./my-game camera-choice --status rejected --note "..."
ludowright decision transition ./my-game camera-choice --status withdrawn
```

Para substituir uma decisão aceita, registre primeiro a decisão nova e depois
aponte a antiga para ela:

```bash
ludowright decision record ./my-game \
  --id camera-choice-v2 \
  --title "Usar câmera em três quartos"
ludowright decision supersede ./my-game camera-choice \
  --replacement-id camera-choice-v2
```

Uma decisão rejeitada, retirada ou superseded é terminal. Repetir a mesma
transição é idempotente e não acrescenta uma entrada nem um evento duplicado.

## Aprovações

Uma aprovação sempre aponta para uma revisão imutável de um sujeito:

```bash
ludowright approval request ./my-game \
  --id maya-front-review \
  --subject-kind reference \
  --subject-id maya-front \
  --revision sha256:abc123 \
  --label "Referência frontal da Maya"
```

Consulte a fila ou o histórico:

```bash
ludowright approval list ./my-game
ludowright approval inspect ./my-game maya-front-review
```

Transições possíveis dependem do estado atual e são validadas pelo domínio:

```bash
ludowright approval transition ./my-game maya-front-review --status approved
ludowright approval transition ./my-game maya-front-review --status revoked
```

Uma revisão corrigida precisa de uma nova solicitação com outro fingerprint.
Uma aprovação aprovada pode ser superseded por outra solicitação:

```bash
ludowright approval supersede ./my-game maya-front-review \
  --replacement-id maya-front-review-v2
```

## Saída e falhas

Todos os comandos usam Rich por padrão e o envelope `cli-response` com `--json`:

```bash
ludowright --json decision list ./my-game
ludowright approval inspect ./my-game maya-front-review --json
```

Os dados de mutação incluem o path canônico, ID, estado, tamanho do histórico e
sequência do evento de auditoria. A listagem é ordenada por ID. Erros de ID ou
registro ausente usam `invalid-input`/exit `4`; projeto ausente usa
`project-not-found`/exit `3`; corrupção do grafo ou estado persistido usa
`corrupt-state`/exit `6`.

## Segurança e atomicidade

Cada mutação usa o lock `governance-write`, valida os contratos Pydantic, escreve
com o repositório estruturado e atualiza o nó correspondente no grafo. Depois da
validação, o event log registra `decision.*` ou `approval.*` com o estado anterior,
novo estado, histórico, path e fingerprint relacionado quando aplicável.

Se a atualização do grafo ou do event log falhar, o documento e o grafo são
restaurados quando isso ainda é seguro. A causa original é preservada. Um arquivo
existente nunca é sobrescrito no comando `record` ou `request`; conflitos de
concorrência são recusados pelo repositório estruturado.

O event log continua sendo a trilha operacional canônica. O SQLite permanece um
índice derivado e não substitui os históricos JSON nem os eventos.
