# Public-beta documentation audit

## Status

Atual: a auditoria documental da prontidão beta está concluída neste slice de
PR62. Este documento registra a cobertura e as verificações do repositório; ele
não simula feedback de usuários externos nem transforma a documentação em uma
garantia de release.

## Escopo revisado

A revisão cobre as superfícies necessárias para uma instalação local-first
reproduzível:

- instalação suportada em Linux, Windows e macOS;
- primeiro projeto com `ludowright init`, incluindo dry-run e modo não
  interativo;
- fluxo de personagem e perfil customizado, troubleshooting, atualização e
  remoção segura;
- comandos, contratos, schemas, plano de implementação, roadmap e ATLAS;
- exemplos mínimo, 2D, low-poly 3D e ambiente modular;
- quality baseline, instalação clean-room, validação end-to-end, matriz de
  migração, modelo de ameaça e política de suporte.

## Evidência executável

Os checks abaixo são locais, determinísticos e fazem parte do fluxo de revisão:

| Superfície | Verificação | Resultado esperado |
|---|---|---|
| Navegação e links | `uv run ludowright atlas --check` | ATLAS válido, sem links quebrados ou documentos órfãos |
| Política documental | `uv run ludowright docs audit --check` | auditoria válida, sem findings |
| Site | `uv run mkdocs build --strict --clean` | build estrito concluído |
| Guias e contratos | `uv run pytest --no-cov tests/test_getting_started_docs.py tests/test_atlas.py tests/test_documentation_audit.py -q` | fluxo documental, ATLAS e auditoria aprovados |
| Gate do repositório | `uv run ludowright quality check` | todos os checks do PR aprovados |

Os testes dos guias executam o fluxo principal em diretórios temporários e
validam o envelope JSON, a criação inicial e as fronteiras de aprovação. Os
checks de ATLAS e documentação usam os metadados e a política versionados, sem
modificar o repositório.

## Estado e pendências

Implementado e documentado:

- instalação de checkout e instalação clean-room de wheel e sdist;
- caminho end-to-end local-first;
- matriz de compatibilidade de migração;
- revisão de segurança com modelo de ameaça e testes negativos;
- documentação pública mínima e auditoria determinística de cobertura,
  links, órfãos, fontes canônicas e referências obsoletas.

Ainda pendente para a prontidão 1.0:

- feedback de uso em projetos reais e correções de usabilidade/compatibilidade
  derivadas desse feedback;
- release candidate e checklist de release estável.

Não há mudança de API pública, schema persistido, migração ou formato de
projeto nesta auditoria. A próxima etapa deve continuar em uma PR separada,
com evidência de projetos reais antes de declarar a release candidate.
