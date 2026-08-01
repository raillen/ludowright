# Instalação

Este é o caminho de instalação suportado para o estado atual do projeto:
checkout local do repositório, ambiente Python gerenciado por `uv` e execução
do CLI pelo próprio checkout. A publicação de um pacote estável em um índice
externo ainda não faz parte desta etapa.

## Requisitos

- Git;
- Python 3.12 ou superior;
- [`uv`](https://docs.astral.sh/uv/), instalado pelo procedimento oficial da
  plataforma.

Consulte a [instalação oficial do
`uv`](https://docs.astral.sh/uv/getting-started/installation/) para Linux,
Windows e macOS. O restante deste guia usa comandos que não dependem de ativar
manualmente uma virtualenv.

## Linux e macOS

Abra um terminal e clone o repositório:

```bash
git clone https://github.com/raillen/ludowright.git
cd ludowright
uv python install 3.12
uv sync
```

## Windows

Abra o PowerShell, instale o `uv` pelo [procedimento oficial para
Windows](https://docs.astral.sh/uv/getting-started/installation/) e execute:

```powershell
git clone https://github.com/raillen/ludowright.git
Set-Location ludowright
uv python install 3.12
uv sync
```

O uso de `uv run` evita depender da política de ativação de scripts do
PowerShell. Não é necessário executar `Activate.ps1` para usar o LudoWright.

## Verificação

Execute a partir da raiz do checkout:

```text
uv --version
uv run ludowright --version
uv run ludowright status
```

O primeiro `uv sync` pode acessar a rede para obter dependências. Depois disso,
os comandos do LudoWright operam localmente sobre o checkout e sobre os
projetos indicados; o núcleo não depende de um serviço remoto para manter o
estado do projeto.

Para desenvolvimento, testes e documentação, instale também os extras:

```text
uv sync --extra dev --extra docs
```

## Diagnóstico inicial

Se a verificação falhar, confirme:

1. `uv --version` responde sem erro;
2. `uv python list` mostra uma versão 3.12 ou superior;
3. o comando foi executado dentro da raiz clonada;
4. `uv sync` terminou antes de chamar `uv run ludowright`.

Quando precisar relatar um problema, prefira compartilhar a saída de:

```text
uv run ludowright --json diagnostics
```

Revise caminhos locais e informações da máquina antes de publicar o
diagnóstico. O comando pode expor dados sensíveis do ambiente.

## Próximo passo

Com a instalação verificada, siga o [tutorial do primeiro
projeto](FIRST_PROJECT.md). A skill do Codex é instalada dentro de cada projeto
e não globalmente na máquina.
