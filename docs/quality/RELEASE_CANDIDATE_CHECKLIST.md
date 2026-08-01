# Checklist de release candidate e release estável

## Status atual

**Bloqueado: beta público, ainda sem aprovação de release candidate.**

Os gates locais do repositório estão automatizados e executáveis. Isso não
substitui o uso em um projeto real fora dos fixtures deste repositório. A
release candidate só pode ser declarada depois que essa evidência externa e as
correções dela forem registradas e revisadas.

## Evidência obrigatória

| Área | Evidência | Estado atual |
|---|---|---|
| Qualidade do repositório | `uv run ludowright quality release` | Passou nesta branch; repetir no commit candidato |
| Schemas | `uv run python -m ludowright.contracts check` | Incluído no gate de release |
| ATLAS e documentação | `uv run ludowright atlas --check`, `uv run ludowright docs audit --check` e `uv run mkdocs build --strict --clean` | Incluído no gate de release |
| Instalação | `uv run pytest -m clean_installation --no-cov` | Incluído no gate de release |
| Fluxo local-first | `uv run pytest -m end_to_end --no-cov` | Incluído no gate de release |
| Migrações | `uv run pytest --no-cov tests/test_migrations.py` | Validado na cadeia de compatibilidade |
| Segurança | `uv run pre-commit run detect-secrets --all-files` e `uv run pip-audit` | Incluído no gate de release |
| Exemplos públicos | `uv run pytest --no-cov tests/test_example_cli_smoke.py -q` | Validado para os quatro exemplos |
| Projeto real externo | execução autorizada, relatório de uso e correções verificadas | **Pendente** |

O comando `quality release` é a entrada operacional para um candidato. Ele
executa o gate normal e acrescenta a construção do wheel e do source
distribution. A saída do comando e os links dos artefatos devem ser anexados
à revisão do candidato; não basta marcar a caixa manualmente.

## Checklist de release candidate

- [x] O escopo da release e as limitações fora dela estão descritos no roadmap.
- [x] O gate local de qualidade, instalação, schemas, documentação, segurança,
      exemplos, auditoria e release é reproduzível por comandos versionados.
- [x] O fluxo end-to-end usa somente fixtures e adapters locais identificados.
- [x] O estado de beta e os riscos residuais estão publicados no modelo de
      ameaça e na auditoria de documentação beta.
- [ ] Um ou mais projetos reais externos foram executados com autorização e
      tiveram seus resultados registrados.
- [ ] Os problemas de usabilidade ou compatibilidade encontrados externamente
      foram corrigidos, testados e documentados.
- [ ] Uma revisão humana confirmou que não há defeito bloqueador conhecido
      para a release candidate.
- [ ] Os artefatos candidatos foram gerados pelo gate de release e seus
      checksums foram preservados para revisão.

Enquanto qualquer item pendente permanecer, o estado correto é **bloqueado**.
Não use `--allow-warnings` para converter falhas em aprovação: essa opção
apenas registra uma decisão explícita sobre warnings permitidos e não libera
erros nem substitui feedback externo.

## Checklist de release estável

Depois da aprovação da release candidate, a revisão final deve confirmar:

- [ ] versão e notas de release revisadas;
- [ ] schemas, migrações, exemplos e documentação correspondem ao commit
      candidato;
- [ ] `uv run ludowright quality release` foi executado novamente no commit
      que será distribuído;
- [ ] wheel e source distribution foram inspecionados e os checksums foram
      preservados;
- [ ] o método de publicação e a política de assinatura, se adotados, foram
      aprovados separadamente;
- [ ] o tag e o artefato publicados apontam para o mesmo commit revisado.

Assinatura digital, publicação remota e rotação de chaves continuam fora do
verificador local. Elas exigem uma decisão própria sobre identidade, confiança,
armazenamento e recuperação de chaves.

## Procedimento de revisão

1. Atualize a branch candidata sobre a cadeia de PRs aprovada.
2. Execute `uv sync --all-extras` e `uv run ludowright quality release`.
3. Execute a validação externa sem compartilhar credenciais ou dados privados
   no repositório.
4. Registre comandos, commit, versões, resultado, limitações e correções na
   revisão do candidato.
5. Só então altere o status para aprovado e inicie o procedimento de release
   estável definido pelos mantenedores.

Este documento é a fonte canônica do checklist operacional. Ele não publica
artefatos, não cria tags e não transforma uma conversa em evidência de release.
