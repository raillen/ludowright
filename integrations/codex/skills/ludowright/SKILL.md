---
name: ludowright
description: Operar projetos LudoWright usando o estado canônico do repositório e o CLI local.
---

# $ludowright

Use esta skill para trabalhar em um projeto LudoWright local.

## Regras de operação

1. Leia `docs/ATLAS.md` e a fonte canônica da área antes de alterar qualquer arquivo.
2. Inspecione o estado do projeto com o CLI antes de propor uma ação.
3. Prefira o CLI com `--json` para automações e mantenha o estado importante no repositório.
4. Preserve contratos, IDs, versões, aprovações e artefatos existentes.
5. Pare e reporte o bloqueio quando uma validação ou aprovação necessária estiver ausente.

## Limite desta skill

Esta versão instala apenas a integração local e o roteamento básico para o núcleo
determinístico. Políticas de orquestração, execução de ImageGen, receipts,
aprovações e agentes especialistas pertencem a etapas posteriores do roadmap.
