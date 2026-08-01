# ADR 0034: Versioned project-local Codex skill installer

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `CODEX_SKILL.md`, `CLI.md`, `PROJECT_FILESYSTEM.md`

## Context

LudoWright precisa oferecer uma experiência Codex reproduzível, mas a skill não
pode se tornar a fonte de decisões, estado ou regras de domínio. A instalação
também precisa funcionar em um repositório local sem sobrescrever alterações
manuais ou deixar uma skill parcialmente gravada.

O formato padrão do Codex usa o nome case-sensitive `SKILL.md`, enquanto os
paths canônicos do projeto aceitam somente segmentos lowercase. A integração
precisa preservar essa convenção sem abrir uma nova superfície arbitrária de
paths.

## Decisão

1. A fonte da skill é dado versionado em `integrations/codex/skills/ludowright/`.
2. O destino é fixo em `.agents/skills/ludowright/` dentro de um projeto
   descoberto pelo marker canônico.
3. `manifest.json` declara identidade, revisão, compatibilidade, arquivos e
   checksums; `SKILL.md` é o entrypoint.
4. `install`, `update`, `verify` e `remove` são comandos não interativos no
   grupo `ludowright codex skill`.
5. A instalação usa o lock `codex-skill`, escreve payloads atomicamente e grava
   o manifesto por último. Falhas restauram os bytes anteriores.
6. O `ProjectFilesystem` ganha uma API restrita para arquivos case-sensitive de
   integração. Ela reutiliza contenção, validação de segmento, symlink denial,
   fsync e atomic replace; não muda a gramática de `RepositoryPath`.
7. O núcleo de domínio e aplicação não importa o adaptador Codex. A CLI chama o
   módulo de integração e continua usando o envelope comum.

## Alternativas consideradas

### Gravar `skill.md` lowercase

Rejeitada porque não respeita a convenção de descoberta do Codex em ambientes
case-sensitive.

### Permitir uppercase em todo `RepositoryPath`

Rejeitada porque amplia uma regra de compatibilidade global e muda a política
de nomes de todos os arquivos do projeto por causa de uma integração.

### Escrever com `pathlib` diretamente na CLI

Rejeitada porque duplicaria contenção, atomicidade, symlink denial e locks fora
da infraestrutura compartilhada.

### Instalar globalmente na máquina do usuário

Rejeitada nesta etapa. A skill é project-local, auditável e versionada junto do
repositório; instalação global exigiria política de escopo, permissões e
descoberta separadas.

## Consequências

### Positivas

- instalação determinística e verificável;
- nenhuma alteração no event log, SQLite ou formato de projeto;
- atualização não destrói alterações manuais;
- rollback preserva o estado anterior em falhas intermediárias;
- o núcleo continua utilizável sem Codex;
- a skill pode evoluir por revisão sem depender de histórico de conversa.

### Negativas

- a instalação não aceita customização de arquivos nesta versão;
- diretórios auxiliares `.agents/skills` podem permanecer vazios após uma falha
  externa, sem conter estado válido;
- a verificação usa uma comparação de versão local compatível com o formato
  publicado do pacote, não um resolvedor geral de PEP 440.

## Compatibilidade e migração

Não há migração de banco, event log ou arquivos canônicos. Mudanças incompatíveis
no manifesto exigem nova versão do schema e política de atualização explícita.
Instalações de revisão menor podem ser atualizadas somente quando seus arquivos
e checksums continuam intactos.
