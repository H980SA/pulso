#!/usr/bin/env bash
set -euo pipefail

output_path="${1:-/mnt/linux-data/pulso/models/gemma-4-E4B-it.litertlm}"
expected_sha256="0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0"
url="https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/f7ad3343bd6ebc9607f4dc3bc4f2398bd5749bc5/gemma-4-E4B-it.litertlm?download=true"

mkdir -p "$(dirname "${output_path}")"
curl --fail --location --continue-at - --retry 5 --retry-delay 2 \
  "${url}" --output "${output_path}"
printf '%s  %s\n' "${expected_sha256}" "${output_path}" | sha256sum --check -
ls -lh "${output_path}"
