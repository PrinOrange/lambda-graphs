#!/usr/bin/env bash
#
# Generate CFG, DFG and AST (json + dot + png) for the multi-file C project
# in examples/atlas_paper_fig_4_demo_multi_file_example (main.c, math_utils.c,
# math_utils.h are merged into one source). Each view is generated separately
# and its output files are renamed to include the view name, e.g.
# atlas_paper_fig_4_demo_multi_file_example.json ->
# atlas_paper_fig_4_demo_multi_file_example_cfg.json, before the next view is
# generated.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

SRC_LANG="c"
CODE_FOLDER="./examples/atlas_paper_fig_4_demo_multi_file_example"
BASE="atlas_paper_fig_4_demo_multi_file_example"   # ATLAS names outputs after the folder name

# 1. Build the Docker image (cached after the first run).
echo ">>> Building Docker image 'atlas' ..."
docker build -t atlas .

mkdir -p output

# Generate one view (--output all => json + dot + png) and rename its files.
generate_and_rename() {
    local graph="$1"   # cfg | dfg | ast
    echo ">>> Generating ${graph} for ${CODE_FOLDER} ..."
    docker run --rm --user "$(id -u):$(id -g)" -v "$REPO_ROOT:/work" -w /work atlas \
        --lang "$SRC_LANG" \
        --code-folder "$CODE_FOLDER" \
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

echo ">>> Done. Files are in ${REPO_ROOT}/output/"
