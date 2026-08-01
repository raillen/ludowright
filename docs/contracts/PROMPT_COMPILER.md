# Prompt Compiler Contract

## Status

Atual: compilador provider-neutral implementado no PR38. O contrato
`compiled-prompt` v1 está publicado em
`schemas/v1/compiled-prompt.schema.json`; o manifesto de template
`prompt-template` v1 está publicado em `schemas/v1/prompt-template.schema.json`.

Esta etapa transforma um `VisualBible` imutável, um alvo estruturado e
referências selecionadas em texto positivo, texto negativo e um hash
reprodutível. Ela não chama provedores, não acessa o filesystem do projeto,
não cria imagens e não persiste jobs.

## Entradas e saída

`PromptCompiler.compile` recebe:

- um `VisualBible` já validado;
- um `ReferenceTarget` explícito;
- o ID de um template versionado, com `minimal` como default;
- zero ou mais referências disponíveis;
- zero ou mais `ReferenceId` selecionados explicitamente.

O resultado `CompiledPrompt` registra:

- template e versão;
- visual bible e versão;
- alvo de asset, componente, variante ou estado;
- IDs das camadas na ordem declarada;
- prompt positivo e negativo;
- as duas listas de restrições estruturadas;
- cada referência aprovada, seu papel e seu `content_revision`;
- `prompt_hash` SHA-256 em minúsculas.

As referências não são inferidas. Cada ID selecionado precisa existir no
catálogo recebido, estar `approved` e apontar para exatamente o mesmo alvo.
IDs são ordenados lexicograficamente antes da saída, portanto uma permutação
acidental do catálogo não muda o resultado. Referências candidatas, rejeitadas,
revogadas, superseded ou ausentes falham de forma fechada.

## Templates em dados

Templates ficam em `src/ludowright/prompt_data/`, com um manifesto JSON
versionado e camadas ordenadas. O template `minimal` é deliberadamente pequeno
e possui camadas positivas para alvo, formas, proporções, paleta, materiais,
iluminação, câmera, detalhe, restrições e referências, além de uma camada
negativa para exclusões.

Cada camada declara apenas `id`, `channel` e `text`. O compilador usa uma
substituição allow-listed de placeholders simples, como `{target}` e
`{negative_constraints}`. Não há avaliação de expressões, loops, acesso a
atributos, Jinja ou conteúdo de provedor. Placeholders desconhecidos, chaves
soltas, caracteres de controle, camadas duplicadas e templates sem os dois
canais são rejeitados.

Novos templates podem ser adicionados como dados versionados. A lógica de
domínio não contém uma implementação específica do template `minimal`.

## Determinismo e hash

O texto é normalizado para uma linha bounded. A compilação preserva a ordem
das camadas e das restrições do visual bible, ordena referências por ID e
serializa um payload canônico com chaves ordenadas e separadores estáveis. O
hash cobre todos os campos sem incluir a si próprio: template, visual bible,
alvo, camadas, textos, restrições, papéis e revisões das referências.

Alterar qualquer entrada significativa produz outro hash. O contrato rejeita
um hash que não corresponda ao conteúdo recebido, o que impede aceitar um
payload adulterado como se fosse a mesma compilação.

## Compatibilidade e limites

- os dois contratos são v1, estritos e rejeitam campos desconhecidos;
- não há migração de SQLite, event log, dependency graph ou filesystem;
- a API é local e sem efeitos colaterais;
- o texto de cada camada é limitado a 512 caracteres;
- cada prompt compilado é limitado a 12.000 caracteres por canal;
- uma compilação aceita no máximo 64 camadas e 64 referências;
- o compilador não define perfis por família, batching, jobs executáveis ou
  integração ImageGen; essas capacidades permanecem em PRs posteriores.

## Validação

```bash
uv run python -m ludowright.contracts check
uv run pytest tests/test_prompt_compiler.py tests/test_contract_schemas.py --no-cov -q
```
