#!/bin/bash
set -e
cd "$(dirname "$0")"

cat > script.txt << 'EOF'
Tokyo's subway system moves fourteen million people every single day. **That's more than the entire population of Greece, moving underground, every day.** It wasn't always this way.
EOF

say -o audio.wav --file-format=WAVE --data-format=LEI16@22050 \
  "Tokyo's subway system moves fourteen million people every single day. That's more than the entire population of Greece, moving underground, every day. It wasn't always this way."

echo "Fixture written: script.txt, audio.wav"
echo "Now run the end-to-end dry run: .venv/bin/python tests/fixtures/dry_run.py"
