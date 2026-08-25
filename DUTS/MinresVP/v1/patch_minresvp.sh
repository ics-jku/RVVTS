#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $(basename "$0") [--no-fixes] <Minres RISC-V VP dir>" >&2
}

no_fixes=0
if [[ "${1:-}" == "--no-fixes" ]]; then
    no_fixes=1
    shift
fi

if [[ $# -ne 1 ]]; then
    usage
    exit 2
fi

patch_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
minresvp_dir="$1"
core_dir="$minresvp_dir/dbt-rise-core"
riscv_dir="$minresvp_dir/dbt-rise-riscv"

for repo in "$minresvp_dir" "$core_dir" "$riscv_dir"; do
    if [[ ! -e "$repo/.git" ]]; then
        echo "error: '$repo' is not a git repository" >&2
        exit 1
    fi
done

git -C "$minresvp_dir" am "$patch_dir"/RISCV-VP/*.patch
git -C "$core_dir" am "$patch_dir"/DBT-RISE-Core/*.patch

git -C "$riscv_dir" am "$patch_dir"/DBT-RISE-RISCV/*.patch

if [[ "$no_fixes" -eq 0 ]]; then
    git -C "$riscv_dir" am \
        "$patch_dir"/DBT-RISE-RISCV-fixes/0001-*.patch \
        "$patch_dir"/DBT-RISE-RISCV-fixes/0002-*.patch \
        "$patch_dir"/DBT-RISE-RISCV-fixes/0003-*.patch
fi
