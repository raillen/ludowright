# Document Template Engine

## Status

Atual. O PR25 publica o primeiro template de documento e a API de renderização
determinística. O conjunto de documentos de produto será adicionado no PR26.

## Objetivo

O engine transforma um contexto JSON-compatible em texto Markdown usando
templates Jinja versionados. Ele não grava arquivos e não transforma o texto
renderizado em fonte de verdade: a aplicação que o invoca decide onde e como
persistir o resultado.

A implementação fica em:

```text
src/ludowright/application/document_templates.py
```

Os templates são dados empacotados, não constantes Python:

```text
src/ludowright/template_data/<template-id>/
├── manifest.json
├── base.md.jinja
└── document.md.jinja
```

## Manifesto

O manifesto usa o contrato público `document-template` na versão 1:

```json
{
  "schema_version": 1,
  "kind": "document-template",
  "id": "minimal",
  "version": 1,
  "entrypoint": "document.md.jinja",
  "files": ["base.md.jinja", "document.md.jinja"]
}
```

O entrypoint e todos os arquivos usados por herança precisam estar declarados
em `files`. IDs e paths usam a gramática canônica de slugs e caminhos seguros.

## Como renderizar

```python
from ludowright.application import DocumentTemplateEngine

result = DocumentTemplateEngine().render(
    "minimal",
    {
        "title": "Echoes",
        "sections": [{"title": "Summary", "body": "A small game."}],
    },
)

result.content
result.digest
```

O contexto aceita somente objetos, listas, strings, booleanos, números finitos
e `null`. As chaves são ordenadas antes da renderização. A saída usa UTF-8,
LF, não começa nem termina com linhas vazias e termina com uma única quebra de
linha. O digest é SHA-256 dos bytes UTF-8 da saída.

## Herança e overrides

Os templates `minimal` e `product` usam herança Jinja. Um projeto pode substituir arquivos
declarados sem alterar o pacote, colocando-os em:

```text
.ludowright/templates/<template-id>/<arquivo-declarado>
```

O loader do projeto tem precedência sobre o loader empacotado. Arquivos novos,
paths com traversal e symlinks não são aceitos; um override não declarado não
pode ser incluído por `{% extends %}` ou `{% include %}`.

O ambiente usa `SandboxedEnvironment`, `StrictUndefined`, globals vazios e um
conjunto pequeno de filtros determinísticos. Templates não recebem acesso ao
filesystem, ao relógio, a rede ou a objetos Python arbitrários.

Quando um manifesto declara vários arquivos de documento, o chamador pode
selecionar qualquer entrypoint declarado:

```python
DocumentTemplateEngine().render(
    "product",
    context,
    entrypoint="audience.md.jinja",
)
```

## Compatibilidade

O manifesto e o schema v1 são contratos publicados. A versão do template deve
ser incrementada quando a saída, a herança, os filtros permitidos ou o
significado do contexto mudar. Fixtures e snapshots devem acompanhar a
alteração. O PR25 não altera arquivos de projeto, o state store, o event log ou
as migrações.

## Limitações

O engine fornece templates mínimos e o pack inicial de documentos de produto.
Ele ainda não define os documentos de arquitetura, qualidade, segurança,
produção ou ATLAS, nem o caso de uso que persiste documentos no projeto; essas
capacidades pertencem aos PRs seguintes.

## Validação

```bash
uv run pytest tests/test_document_templates.py --no-cov -q
uv run python -m ludowright.contracts check
```
