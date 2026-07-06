#!/usr/bin/env bash
#
# Generate CFG, DFG and AST (json + dot + png) for
# examples/single/atlas_paper_fig_3_sample_code_block.cpp.
# Each view is generated separately and its output files are renamed to
# include the view name, e.g. atlas_paper_fig_3_sample_code_block.json ->
# atlas_paper_fig_3_sample_code_block_cfg.json, before the next view is generated.
# Two additional AST variants are also generated:
#   - ast_collapsed: all variable occurrences collapsed into one node (--collapsed)
#   - ast_blacklisted: number_literal nodes removed (--blacklisted "number_literal")
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

SRC_LANG="cpp"
CODE_FILE="./examples/single/atlas_paper_fig_3_sample_code_block.cpp"
BASE="atlas_paper_fig_3_sample_code_block"   # lambda-graphs names outputs after the file stem

# 1. Build the Docker image (cached after the first run).
echo ">>> Building Docker image 'lambda-graphs' ..."
docker build -t lambda-graphs .

mkdir -p output

# Generate one view (--output all => json + dot + png) and rename its files.
generate_and_rename() {
    local graph="$1"   # cfg | dfg | ast
    echo ">>> Generating ${graph} for ${CODE_FILE} ..."
    lambda-graphs \
        --lang "$SRC_LANG" \
        --code-file "$CODE_FILE" \
        --graphs "$graph" \
        --output all

    echo ">>> Renaming ${graph} output files ..."
    for ext in json dot png; do
        local src="output/${BASE}.${ext}"
        local dst="output/${BASE}_${graph}.${ext}"
        if [ -f "$src" ]; then
            mv -f "$src" "$dst"
            echo "    ${src} -> ${dst}"
        else
            echo "    WARNING: ${src} not found, skipping"
        fi
    done
}

generate_and_rename cfg
generate_and_rename dfg
generate_and_rename ast

# AST with --collapsed: all variable occurrences collapsed into one node.
echo ">>> Generating ast_collapsed for ${CODE_FILE} ..."
lambda-graphs \
    --lang "$SRC_LANG" \
    --code-file "$CODE_FILE" \
    --graphs ast \
    --collapsed \
    --output all
echo ">>> Renaming ast_collapsed output files ..."
for ext in json dot png; do
    src="output/${BASE}.${ext}"
    dst="output/${BASE}_ast_collapsed.${ext}"
    if [ -f "$src" ]; then
        mv -f "$src" "$dst"
        echo "    ${src} -> ${dst}"
    else
        echo "    WARNING: ${src} not found, skipping"
    fi
done

# AST with --blacklisted "number_literal": number literal nodes removed.
echo ">>> Generating ast_blacklisted for ${CODE_FILE} ..."
lambda-graphs \
    --lang "$SRC_LANG" \
    --code-file "$CODE_FILE" \
    --graphs ast \
    --blacklisted "number_literal" \
    --output all
echo ">>> Renaming ast_blacklisted output files ..."
for ext in json dot png; do
    src="output/${BASE}.${ext}"
    dst="output/${BASE}_ast_blacklisted.${ext}"
    if [ -f "$src" ]; then
        mv -f "$src" "$dst"
        echo "    ${src} -> ${dst}"
    else
        echo "    WARNING: ${src} not found, skipping"
    fi
done

echo ">>> Done. Files are in ${REPO_ROOT}/output/"
