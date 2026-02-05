#!/bin/bash
set -e

echo "Setting up Container Fundamentals environment..."

echo "Installing additional tools (vim, neovim, ncat)..."
sudo apt-get update -qq
sudo apt-get install -y vim neovim ncat

echo "Verifying Docker..."
docker_ready=0
for _ in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    docker_ready=1
    break
  fi
  sleep 1
done

if [ "$docker_ready" -eq 1 ]; then
  docker --version || true
  docker compose version || true

  echo "Skipping image pre-pull."
else
  echo "Warning: Docker daemon did not become ready in time; skipping pre-pull."
  echo "If needed later, run: docker run hello-world"
fi

echo "Verifying Python..."
python3 --version
pip3 --version

# Create a student workspace directory
mkdir -p ~/labs

echo ""
echo "✅ Environment setup complete!"
echo ""
echo "Quick verification:"
echo "  docker run hello-world"
echo ""
echo "To get started with Week 1:"
echo "  cd week-01/labs"
echo ""
