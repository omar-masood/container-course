#!/bin/bash

set -e

echo "🐳 Docker Environment Reset Script"
echo "=================================="
echo "This script will remove ALL Docker resources including:"
echo "  - All containers (running and stopped)"
echo "  - All images"
echo "  - All volumes"
echo "  - All networks (except default ones)"
echo "  - Build cache"
echo ""

read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Operation cancelled."
    exit 1
fi

echo ""
echo "🧹 Starting Docker cleanup..."

echo "📦 Stopping all running containers..."
if [ "$(docker ps -q)" ]; then
    docker stop $(docker ps -q)
    echo "✅ All containers stopped"
else
    echo "ℹ️  No running containers found"
fi

echo "🗑️  Removing all containers..."
if [ "$(docker ps -aq)" ]; then
    docker rm $(docker ps -aq)
    echo "✅ All containers removed"
else
    echo "ℹ️  No containers found"
fi

echo "🖼️  Removing all images..."
if [ "$(docker images -q)" ]; then
    docker rmi $(docker images -q) --force
    echo "✅ All images removed"
else
    echo "ℹ️  No images found"
fi

echo "💾 Removing all volumes..."
if [ "$(docker volume ls -q)" ]; then
    docker volume rm $(docker volume ls -q) --force
    echo "✅ All volumes removed"
else
    echo "ℹ️  No volumes found"
fi

echo "🌐 Removing custom networks..."
NETWORKS=$(docker network ls --format "{{.Name}}" | grep -v -E "^(bridge|host|none)$" || true)
if [ -n "$NETWORKS" ]; then
    echo "$NETWORKS" | xargs docker network rm
    echo "✅ Custom networks removed"
else
    echo "ℹ️  No custom networks found"
fi

echo "🧽 Cleaning build cache..."
docker builder prune --all --force
echo "✅ Build cache cleaned"

echo "🔄 Running system prune for final cleanup..."
docker system prune --all --volumes --force

echo ""
echo "✨ Docker environment reset complete!"
echo "📊 Current Docker status:"
echo "  Containers: $(docker ps -a --format "table {{.Names}}" | wc -l | awk '{print $1-1}')"
echo "  Images: $(docker images --format "table {{.Repository}}" | wc -l | awk '{print $1-1}')"
echo "  Volumes: $(docker volume ls --format "table {{.Name}}" | wc -l | awk '{print $1-1}')"
echo "  Networks: $(docker network ls --format "table {{.Name}}" | wc -l | awk '{print $1-1}')"