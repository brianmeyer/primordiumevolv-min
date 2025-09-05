#!/bin/bash

# PrimordiumEvolv Development Sanity Check Script
# Run this to verify the system is properly configured and working

set -e  # Exit on any error

echo "🔍 PrimordiumEvolv Development Sanity Check"
echo "=========================================="

# Check Python environment
echo "1. Python Environment"
echo "   Python version: $(python --version)"
echo "   Pip location: $(which pip)"

# Check dependencies
echo ""
echo "2. Dependencies Check"
REQUIRED_PACKAGES=("fastapi" "uvicorn" "sentence-transformers" "faiss-cpu" "requests" "pydantic" "python-dotenv")

for package in "${REQUIRED_PACKAGES[@]}"; do
    if pip show "$package" >/dev/null 2>&1; then
        version=$(pip show "$package" | grep Version | cut -d' ' -f2)
        echo "   ✅ $package ($version)"
    else
        echo "   ❌ $package (missing)"
        echo "      Install with: pip install $package"
    fi
done

# Check project structure
echo ""
echo "3. Project Structure"
REQUIRED_DIRS=("app" "app/meta" "app/tools" "app/evolve" "app/ui" "docs")
REQUIRED_FILES=("app/main.py" "app/ollama_client.py" "app/meta/runner.py" "app/ui/index.html")

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "   ✅ $dir/"
    else
        echo "   ❌ $dir/ (missing directory)"
    fi
done

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✅ $file"
    else
        echo "   ❌ $file (missing file)"
    fi
done

# Check environment configuration
echo ""
echo "4. Environment Configuration"
if [ -f ".env" ]; then
    echo "   ✅ .env file exists"
    if grep -q "OLLAMA_HOST" .env; then
        OLLAMA_HOST=$(grep "OLLAMA_HOST" .env | cut -d'=' -f2)
        echo "   📍 OLLAMA_HOST=$OLLAMA_HOST"
    fi
    if grep -q "MODEL_ID" .env; then
        MODEL_ID=$(grep "MODEL_ID" .env | cut -d'=' -f2)
        echo "   🤖 MODEL_ID=$MODEL_ID"
    fi
else
    echo "   ⚠️  .env file not found (using defaults)"
    echo "   📍 OLLAMA_HOST=http://localhost:11434 (default)"
    echo "   🤖 MODEL_ID=qwen3:4b (default)"
fi

# Check Ollama connectivity
echo ""
echo "5. Ollama Service Check"
OLLAMA_URL="${OLLAMA_HOST:-http://localhost:11434}"

if curl -s -f "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    echo "   ✅ Ollama service is running at $OLLAMA_URL"
    
    # Check available models
    MODELS=$(curl -s "$OLLAMA_URL/api/tags" | python -c "
import sys, json
try:
    data = json.load(sys.stdin)
    models = [m.get('name', '') for m in data.get('models', [])]
    print(' '.join(models))
except:
    print('')")
    
    if [ -n "$MODELS" ]; then
        echo "   📋 Available models: $MODELS"
        
        # Check if configured model exists
        MODEL_ID="${MODEL_ID:-qwen3:4b}"
        if echo "$MODELS" | grep -q "$MODEL_ID"; then
            echo "   ✅ Configured model '$MODEL_ID' is available"
        else
            echo "   ⚠️  Configured model '$MODEL_ID' not found"
            echo "      Run: ollama pull $MODEL_ID"
        fi
    else
        echo "   ⚠️  No models found"
        echo "      Run: ollama pull qwen3:4b"
    fi
else
    echo "   ❌ Ollama service not reachable at $OLLAMA_URL"
    echo "      Start with: ollama serve"
fi

# Test basic imports
echo ""
echo "6. Python Module Imports"
python -c "
try:
    from app.main import app
    print('   ✅ FastAPI app import successful')
except ImportError as e:
    print(f'   ❌ FastAPI app import failed: {e}')

try:
    from app.ollama_client import health
    print('   ✅ Ollama client import successful')
except ImportError as e:
    print(f'   ❌ Ollama client import failed: {e}')

try:
    from app.meta.runner import meta_run
    print('   ✅ Meta runner import successful')
except ImportError as e:
    print(f'   ❌ Meta runner import failed: {e}')

try:
    from sentence_transformers import SentenceTransformer
    print('   ✅ Sentence transformers available')
except ImportError as e:
    print(f'   ❌ Sentence transformers failed: {e}')

try:
    import faiss
    print('   ✅ FAISS available')
except ImportError as e:
    print(f'   ❌ FAISS failed: {e}')
"

# Create necessary directories
echo ""
echo "7. Storage Directories"
STORAGE_DIRS=("storage" "data" "logs" "runs")

for dir in "${STORAGE_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "   📁 Created $dir/"
    else
        echo "   ✅ $dir/ exists"
    fi
done

# Test server startup (dry run)
echo ""
echo "8. Server Configuration Test"
python -c "
try:
    from app.main import app
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    response = client.get('/api/health')
    
    if response.status_code == 200:
        health_data = response.json()
        print(f'   ✅ Health check passed: {health_data}')
    else:
        print(f'   ⚠️  Health check returned {response.status_code}')
except Exception as e:
    print(f'   ❌ Server test failed: {e}')
"

echo ""
echo "🎯 Summary & Next Steps"
echo "======================"
echo "To start the development server:"
echo "  python -m uvicorn app.main:app --reload --port 8000"
echo ""
echo "To run a quick test:"
echo "  curl http://localhost:8000/api/health"
echo ""
echo "To access the UI:"
echo "  http://localhost:8000"
echo ""
echo "Check docs/UX_NOTES.md for detailed usage instructions."