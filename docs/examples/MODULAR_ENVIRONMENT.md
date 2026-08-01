# Exemplo de ambiente modular

O exemplo `examples/modular-environment/` descreve **Mossbridge Commons**:
um pequeno ambiente low-poly composto por prédio, kit modular, estrada, árvore
e planta. O fluxo exercita componentes, estados, sockets e regras direcionais
de conexão sem criar um grafo paralelo.

## Perfis reutilizados

O prédio usa `hard-surface/building`, o kit usa `hard-surface/modular-kit`, a
árvore usa `visual/tree` e a planta usa `visual/plant`. A estrada usa um
`capture-profile` v1 mínimo armazenado como dado do próprio exemplo porque a
taxonomia já publica `terrain/road`, mas ainda não existe um perfil
especializado de estrada no catálogo de pacotes.

O kit demonstra as conexões `root → floor-module`, `root → wall-module` e
`root → connector` com `socket`. Essas linhas são orientação de construção
descritiva; não são mutações do dependency graph.

## Fluxo

Inicialize pelo PR19 e copie as entradas:

```bash
ludowright init ./mossbridge-commons --name "Mossbridge Commons" \
  --template minimal --non-interactive
cp -R examples/modular-environment/project/. ./mossbridge-commons/
```

Depois registre os cinco assets com `ludowright assets create`, conforme o
README do exemplo. Os jobs derivam assets completos, componentes e estados.
Todas as referências começam como `candidate`; portanto o plano é útil para
auditoria, mas permanece bloqueado até aprovações humanas revision-bound.

A fixture PNG é pequena, textual e ligada por SHA-256 a todas as sheet
requests. SQLite, event log, dependency graph, imagens normalizadas, receipts,
sheets e pacotes são artefatos derivados e não fazem parte do exemplo
versionado.

## Compatibilidade

O exemplo consome somente contratos v1 publicados. Não adiciona schema,
migração, comando, persistência de seleção de perfil ou ADR arquitetural.
