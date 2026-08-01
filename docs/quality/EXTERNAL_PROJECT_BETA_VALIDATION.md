# Validação beta com projeto externo

## Objetivo

Esta validação usa um pequeno conjunto autorizado de assets de um projeto real
para testar a fronteira entre dados externos e o pipeline visual do LudoWright.
Ela não transforma o formato externo em um contrato canônico do produto e não
altera o projeto de origem.

O slice versionado cobre dois casos:

- `UII-022` — ícone de UI, usando o perfil `interface-icon`;
- `CHV-0102` — retrato de Fulgor, usando o perfil `humanoid/minimal`.

Os IDs podem ser reduzidos com `LUDOWRIGHT_EXTERNAL_ASSET_IDS`, portanto não é
necessário processar o catálogo inteiro.

## Como executar

Defina o diretório do projeto externo e execute:

```bash
LUDOWRIGHT_EXTERNAL_PROJECT="/caminho/para/Echos of Mythology" \
  uv run pytest -m external_beta tests/test_external_asset_beta.py -q
```

Para validar somente um asset:

```bash
LUDOWRIGHT_EXTERNAL_PROJECT="/caminho/para/Echos of Mythology" \
LUDOWRIGHT_EXTERNAL_ASSET_IDS="UII-022" \
  uv run pytest -m external_beta tests/test_external_asset_beta.py -q
```

Sem `LUDOWRIGHT_EXTERNAL_PROJECT`, o teste é pulado e não faz parte do gate
normal. O caminho não é armazenado no repositório.

## O que o teste verifica

Para cada item selecionado, o teste:

1. lê o manifesto externo e confirma ID, slug e categoria;
2. lê uma imagem candidata real sem escrever no projeto externo;
3. prepara normalização, fundo neutro, thumbnail e guia de alinhamento em
   memória;
4. confirma que a preparação é determinística;
5. deriva um asset e um perfil LudoWright a partir da fixture de compatibilidade;
6. planeja os jobs de todas as vistas exigidas pelo perfil;
7. mantém o plano bloqueado porque a referência externa ainda é `candidate`;
8. confirma que o compilador de prompt recusa uma referência não aprovada.

O teste não aprova referências automaticamente e não chama um provider de
imagem. Isso é intencional: a aprovação humana deve ocorrer antes de uma
geração que produza estado canônico.

## Resultado observado no projeto Convergência

Na primeira execução autorizada:

- o manifesto externo passou pelos validadores próprios e continha 510 assets;
- os dois arquivos de imagem selecionados foram lidos com sucesso;
- a normalização gerou quatro artefatos determinísticos em memória por imagem;
- o perfil de ícone derivou 3 jobs e 9 outputs;
- a referência candidata bloqueou o plano e o prompt compiler;
- nenhum arquivo foi criado ou modificado no projeto externo.

## Limitações e próximo passo

O projeto externo usa uma planilha, CSV, YAML e manifestos próprios. A fixture
de beta registra apenas o mapeamento mínimo necessário para testar a fronteira;
ela não é um importador genérico.

Para executar uma geração real de um ou dois assets, primeiro é necessário
criar um staging LudoWright separado, registrar a referência com provenance e
aprovação explícitas, revisar o prompt compilado e só então executar o
provider. O projeto original permanece somente leitura durante esse fluxo.
