#!/usr/bin/env bash
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v uv >/dev/null; then
  read -r -p "Needs a small helper tool called uv (20 MB, from astral.sh). Install it now? [Y/n] " a
  [[ "$a" =~ ^[Nn] ]] && exit 1
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
while true; do
  uv run --quiet ui/server.py && break
  echo; echo "The dashboard stopped unexpectedly. Restarting in 3 seconds... (details: data/ui.log)"; sleep 3
done
