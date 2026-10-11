#!/bin/bash
# Starts the two self-hosted models as OpenAI-compatible servers once their GGUF files are complete.
# Sarvam-30B -> :8101, Qwen3-30B-A3B -> :8102 (both Q4_K_M, full GPU offload).
cd "$(dirname "$0")/.."
LS=${LLAMA_SERVER:-$HOME/embed-bench/llamacpp/llama-b11541/llama-server}
until grep -q ALLDONE logs/download.log 2>/dev/null; do sleep 20; done
"$LS" -m gguf/sarvam-30b-Q4_K_M.gguf-00001-of-00006.gguf --jinja -ngl 99 -c 32768 -np 4 --port 8101 > logs/server-sarvam30b.log 2>&1 &
"$LS" -m gguf/Qwen3-30B-A3B-Q4_K_M.gguf --jinja -ngl 99 -c 32768 -np 4 --port 8102 > logs/server-qwen3.log 2>&1 &
wait
