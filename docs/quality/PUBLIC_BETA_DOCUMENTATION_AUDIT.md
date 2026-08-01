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
| Exemplos públicos | `uv run pytest --no-cov tests/test_example_cli_smoke.py -q` | quatro exemplos inicializam e registram assets pela CLI |
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
- compatibilidade inicial dos quatro exemplos públicos com `init` e registro
  de assets pela CLI; o fluxo mínimo foi corrigido para não prometer uma sheet
  antes de existir receipt e aprovação aplicados.

Ainda pendente para a prontidão 1.0:

- feedback de uso em projetos reais e correções de usabilidade/compatibilidade
  derivadas desse feedback;
- aprovação da release candidate e da release estável. O checklist operacional
  já está publicado em
  [`quality/RELEASE_CANDIDATE_CHECKLIST.md`](RELEASE_CANDIDATE_CHECKLIST.md).

A varredura local dos exemplos não substitui validação com projetos externos.
Ela cobre somente a compatibilidade dos comandos publicados de inicialização e
registro; geração por provider, review e packaging continuam demonstrados pelo
teste end-to-end com provider fixture.

Não há mudança de API pública, schema persistido, migração ou formato de
projeto nesta auditoria. A aprovação da release candidate continua bloqueada
até existir evidência de projetos reais e revisão humana conforme o
[`checklist de release`](RELEASE_CANDIDATE_CHECKLIST.md).
