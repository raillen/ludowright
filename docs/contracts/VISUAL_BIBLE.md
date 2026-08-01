# Visual Bible Contract

## Status

Atual: contrato `visual-bible` v1 publicado em `schemas/v1/visual-bible.schema.json`.

Esta etapa define a direção visual compartilhada de um projeto. Ela não cria
arquivos de imagem, não executa provedores e não compila prompts.

## Objetivo

O visual bible registra uma versão imutável e auditável de:

- linguagem de formas;
- regras de proporção;
- paleta semântica;
- materiais e acabamentos;
- iluminação e câmera padrão;
- níveis de detalhe;
- limites de carga de trabalho visual;
- restrições positivas e negativas para futuras operações.

O documento é associado a um `ProjectId`, possui um identificador estável e
uma revisão monotônica. Uma alteração de significado exige uma nova revisão.

## Forma canônica

O contrato superior contém:

```text
schema_version, kind, id, version, name, project_id,
shape_language, proportions, palette, materials,
lighting, camera, level_of_detail, budget,
prompt_constraints, negative_constraints
```

Todos os objetos rejeitam campos desconhecidos. Coleções são tuplas na camada
de domínio e preservam a ordem declarada para gerar resultados determinísticos.

### Linguagem de formas

`shape_language` possui um descritor primário e listas opcionais de descritores
secundários e evitados. O descritor primário não pode aparecer nas listas de
apoio ou de exclusão.

### Proporções

Cada regra possui `id`, `name` e `guidance`. A orientação é uma afirmação
bounded de direção visual; o v1 não finge que uma imagem gerada é uma planta
geométrica ou uma medição CAD.

### Paleta

Cada cor possui `id`, nome, papel semântico e cor em maiúsculas no formato
`#RRGGBB`. Os papéis publicados são `primary`, `secondary`, `accent`,
`neutral`, `background` e `highlight`.

### Materiais

Cada material possui `id`, nome, acabamento controlado e orientação. O v1
aceita `matte`, `satin`, `semi-gloss`, `glossy`, `metallic`, `translucent`,
`emissive` e `stylized`.

### Câmera e iluminação

Os objetos reutilizam as mesmas regras de câmera e iluminação do contrato de
capture profile. Isso evita duas interpretações para projeção, distância focal,
sombras e margem de enquadramento. O visual bible define defaults; um capture
profile versionado pode especializá-los em uma etapa posterior.

### Nível de detalhe

`level_of_detail` declara um nível padrão e pelo menos uma regra para cada nível
publicado. Os níveis disponíveis são `proxy`, `low`, `medium`, `high` e `hero`.
O nível padrão deve possuir uma regra correspondente.

### Orçamento

`budget` contém limites de planejamento independentes de provedor:

- `max_visual_jobs`;
- `max_generated_outputs`;
- `max_references_per_asset`.

Cada limite é inteiro entre 1 e 1.000.000. Esses números não são preço,
latência nem promessa de custo de um provedor.

### Restrições

`prompt_constraints` e `negative_constraints` são listas ordenadas de
afirmações não vazias, com no máximo 1.000 caracteres por item. Cada lista
deve ser única e uma afirmação não pode aparecer nas duas listas.

O v1 exige pelo menos uma afirmação em cada lista para tornar a ausência de
restrições explícita durante a revisão. A compilação em camadas e o hashing
dessas restrições pertencem ao PR38.

## Compatibilidade e segurança

- O schema publicado é v1 e possui fixture em `tests/fixtures/contracts/v1/`.
- Não há migração de SQLite, YAML, event log ou filesystem nesta etapa.
- O contrato não aceita URLs, caminhos, credenciais, payloads de provedor ou
  binários.
- Textos são limitados, normalizados em Unicode NFC e não aceitam caracteres de
  controle.
- Alterar campos obrigatórios, enumerações, limites ou semântica exige análise
  de compatibilidade, nova fixture e, quando incompatível, uma nova versão do
  schema.

## Limites desta etapa

Ainda não fazem parte do visual bible:

- perfis executáveis por família de asset;
- herança ou catálogo de capture profiles;
- resolução de referências aprovadas;
- compilação de prompts;
- planejamento ou execução de visual jobs;
- persistência de um arquivo de projeto ou comandos CLI.

Essas capacidades consomem este contrato nos PRs seguintes.

## Validação

```bash
uv run python -m ludowright.contracts check
uv run pytest tests/test_visual_bibles.py tests/test_contract_schemas.py --no-cov -q
```
