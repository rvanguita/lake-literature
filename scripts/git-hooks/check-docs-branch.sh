#!/usr/bin/env bash
# Bloqueia commits que só tocam documentação quando feitos direto na main/master.
set -euo pipefail

branch="$(git rev-parse --abbrev-ref HEAD)"

if [[ "$branch" != "main" && "$branch" != "master" ]]; then
    exit 0
fi

staged_files="$(git diff --cached --name-only)"

if [[ -z "$staged_files" ]]; then
    exit 0
fi

is_doc_file() {
    case "$1" in
        docs/*|*.md|README*|CLAUDE.md) return 0 ;;
        *) return 1 ;;
    esac
}

all_docs=true
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    if ! is_doc_file "$file"; then
        all_docs=false
        break
    fi
done <<< "$staged_files"

if [[ "$all_docs" == true ]]; then
    echo "Commit bloqueado: você está tentando commitar apenas documentação direto na branch '$branch'." >&2
    echo "Crie uma branch dedicada antes de continuar, por exemplo:" >&2
    echo "  git checkout -b docs/<assunto>" >&2
    echo "e refaça o commit nela." >&2
    exit 1
fi

exit 0
