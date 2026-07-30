# Product Document Set

## Status

Atual. O PR26 adiciona o pack `product` ao engine de templates. Os documentos
renderizados são derivados; as decisões e os dados estruturados continuam sendo
a fonte de verdade do projeto.

## Documentos

Todos os documentos usam o manifesto `product` v1 e herdam de
`base.md.jinja`. O entrypoint padrão é `vision.md.jinja`.

| Documento | Entrypoint | Conteúdo principal |
|---|---|---|
| Vision | `vision.md.jinja` | visão e missão |
| Audience | `audience.md.jinja` | usuários primários e secundários |
| Pillars | `pillars.md.jinja` | pilares de produto e descrições |
| Loops | `loops.md.jinja` | loops e passos ordenados |
| Scope | `scope.md.jinja` | dentro e fora de escopo |
| Risk | `risk.md.jinja` | impacto e mitigação de riscos |
| Platform | `platform.md.jinja` | plataformas e observações |
| Success | `success.md.jinja` | medidas de sucesso |

Os arquivos de dados estão em:

```text
src/ludowright/template_data/product/
```

## Como renderizar

```python
from ludowright.application import DocumentTemplateEngine

engine = DocumentTemplateEngine()
result = engine.render(
    "product",
    {
        "title": "Meu jogo",
        "vision": "Uma experiência clara e terminável.",
        "mission": "Transformar decisões em trabalho executável.",
        "primary_users": ["Criadores independentes"],
        "secondary_users": [],
        "pillars": [{"name": "Foco", "description": "Limites explícitos."}],
        "loops": [{"name": "Design", "steps": ["Perguntar", "Decidir"]}],
        "in_scope": ["Documentação"],
        "out_of_scope": ["Runtime de engine"],
        "risks": [{"name": "Escopo", "impact": "Alto", "mitigation": "Cortar cedo."}],
        "platforms": [{"name": "Desktop", "notes": "Alvo local-first."}],
        "measures": [{"name": "Retomada", "description": "Sem depender do chat."}],
    },
    entrypoint="vision.md.jinja",
)
```

O contexto deve conter os campos usados pelo entrypoint selecionado. O engine
usa `StrictUndefined`, portanto campo ausente é erro; isso evita documentos
silenciosamente incompletos. A validação de valores, proveniência e decisões
continua pertencendo aos contratos e casos de uso que montam o contexto.

## Fonte de verdade e segurança

Templates e manifesto são dados versionados. O texto Markdown, snapshots e
futuros arquivos de projeto são projeções derivadas. O engine não persiste
resultados nem altera o event log ou o state store.

O manifesto limita a herança aos arquivos declarados. Overrides locais seguem
a política do contrato de templates e podem substituir um arquivo declarado sem
alterar o pack empacotado.

## Limitações e próximos passos

O PR26 entrega o catálogo inicial e seus contextos esperados. Ainda não existe
um caso de uso que leia respostas de uma entrevista, monte esses contextos e
grave documentos no projeto. Essa orquestração será tratada nas etapas de
arquitetura/documentação e refresh incremental.

## Validação

```bash
uv run pytest tests/test_document_templates.py --no-cov -q
uv run python -m ludowright.contracts check
```
