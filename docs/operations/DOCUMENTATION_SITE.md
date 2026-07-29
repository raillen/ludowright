# Documentation Site Operations

## Purpose

The public documentation site is built from the canonical Markdown files under `docs/` using MkDocs and Material for MkDocs.

The website is a presentation layer. The Markdown files in the repository remain the source of truth.

## Install documentation dependencies

```bash
uv sync --extra dev --extra docs
```

## Preview locally

```bash
uv run mkdocs serve
```

Open the local address printed by MkDocs. The preview rebuilds when documentation files change.

## Run the release-quality build

```bash
uv run mkdocs build --strict --clean
```

Strict mode converts warnings into failures. The configuration treats these as errors:

- pages present under `docs/` but omitted from navigation;
- navigation entries pointing to missing files;
- broken relative document links;
- invalid internal anchors;
- unrecognized relative links;
- absolute local links that should be repository-relative.

External websites are not fetched during the normal build. This avoids making pull requests fail because an unrelated website is temporarily unavailable.

## Navigation policy

`mkdocs.yml` contains the published navigation.

When adding, moving, or removing a canonical document:

1. update `docs/ATLAS.md`;
2. update `mkdocs.yml`;
3. repair inbound links;
4. run the strict build;
5. include documentation navigation changes in the same pull request.

A file intentionally kept outside the public site must be documented and excluded explicitly rather than silently omitted.

## Repository-root policies

GitHub expects files such as `CONTRIBUTING.md`, `SECURITY.md`, and `CODE_OF_CONDUCT.md` at the repository root. The documentation site links to their canonical GitHub-rendered versions instead of duplicating their contents under `docs/`.

## Continuous integration

Pull requests that change documentation run the documentation workflow. The workflow:

1. checks out the repository;
2. installs Python and `uv`;
3. installs the documentation dependency group;
4. performs a strict clean build;
5. uploads the built site as an artifact on eligible `main` builds;
6. deploys the artifact through GitHub Pages.

The Python CI and documentation build remain separate so failures are easier to classify.

## GitHub Pages setup

The repository must use **GitHub Actions** as the Pages publishing source.

The deploy job uses GitHub's Pages environment and official configure, upload, and deploy actions. The workflow deploys only from `main`; pull requests build the site without publishing it.

## Publication address

The configured canonical address is:

```text
https://raillen.github.io/ludowright/
```

A future custom domain requires updating `site_url`, repository Pages settings, and any canonical links.

## Troubleshooting

### Page omitted from navigation

Add the page to `mkdocs.yml`, or document an intentional exclusion.

### Link target is not found

Use a path relative to the current Markdown file and keep the `.md` extension for links to source documents.

### Anchor is not found

Check the target heading and generated slug. Prefer linking to stable headings rather than manually crafted HTML anchors.

### Root policy link fails validation

Use the full GitHub URL for repository-root policy files. They are outside `docs_dir` and are not part of the MkDocs source tree.

### Pages deployment fails

Confirm that Pages is enabled with GitHub Actions as its source and that the workflow has `pages: write` and `id-token: write` permissions.
