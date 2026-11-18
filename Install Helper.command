#!/bin/bash
# macOS: double-click once. Sets up viral-clipper and starts the helper at every login.
cd "$(dirname "$0")" || exit 1
python3 scripts/setup.py && python3 scripts/install_helper.py \
  && echo && echo "✅ Helper installed. Now just ask Claude: '10 shorts from <YouTube link>'." \
  || echo "❌ Something failed above. Tell Claude 'failed'."
read -n1 -p "Press any key to close"
