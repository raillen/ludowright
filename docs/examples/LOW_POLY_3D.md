# Exemplo low-poly 3D

O exemplo `examples/low-poly-3d/` descreve **Copper & Forge**, um pequeno
fluxo de produção low-poly com uma personagem humanoide e um edifício. Os
assets são segmentados em componentes e estados, e cada referência permanece
presa à sua revisão e aprovação.

## Perfis reutilizados

O exemplo não copia nem altera perfis. Os testes carregam os dados de pacote
`humanoid/minimal` e `hard-surface/building`, projetando ambos para o mesmo
`CaptureProfile` genérico consumido pelo planejador. Isso mantém câmera, views,
componentes, estados e sheets sob os contratos publicados.

## Fluxo

Inicialize o projeto pelo PR19 e copie as entradas:

```bash
ludowright init ./copper-and-forge --name "Copper & Forge" \
  --template minimal --non-interactive
cp -R examples/low-poly-3d/project/. ./copper-and-forge/
```

Registre os dois assets:

```bash
ludowright assets create ./copper-and-forge --input imports/copper.json
ludowright assets create ./copper-and-forge --input imports/forge-building.json
```

Os jobs e as requests de sheet usam referências candidatas. O planejador
deriva jobs para o asset inteiro, componentes necessários e estados do edifício,
mas permanece bloqueado até que a revisão humana aprove cada referência exata.
Nenhuma imagem é tratada como blueprint geométrico ou executada por provider
neste exemplo.

As duas fixtures PNG são textuais, pequenas e determinísticas. Seus checksums
estão nas requests e são testados sem rede, relógio do sistema ou estado
derivado. SQLite, event log, dependency graph, receipts e sheets não são
versionados.

## Compatibilidade

O exemplo usa somente contratos v1 e perfis de pacote existentes. Não adiciona
schema, migração, CLI ou persistência de seleção de perfil.
