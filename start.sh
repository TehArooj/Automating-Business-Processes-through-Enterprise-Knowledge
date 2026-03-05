#!/bin/bash

echo "🚀 Starting Selenium + Milvus RAG System"
echo "========================================"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if docker compose is available (try both old and new syntax)
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "❌ Neither 'docker-compose' nor 'docker compose' found. Please install Docker Compose."
    exit 1
fi

echo "📦 Using: $DOCKER_COMPOSE_CMD"

# Start Milvus services
echo "📦 Starting Milvus services..."
$DOCKER_COMPOSE_CMD up -d

# Wait for services to be ready
echo "⏳ Waiting for Milvus to be ready..."
sleep 15

# Check if services are running
echo "🔍 Checking service status..."
$DOCKER_COMPOSE_CMD ps

# Install Python dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "📚 Installing Python dependencies..."
    pip install -r requirements.txt
    
    # If installation fails, try with specific versions that work better
    if [ $? -ne 0 ]; then
        echo "⚠️  Standard installation failed. Trying with compatible versions..."
        pip install --no-cache-dir pymilvus==2.3.4
        pip install --no-cache-dir sentence-transformers==2.2.2
        pip install --no-cache-dir langchain==0.1.0
        pip install --no-cache-dir "langchain-core>=0.1.7,<0.2"
        pip install --no-cache-dir langchain-community==0.0.10
        pip install --no-cache-dir selenium==4.15.2
        pip install --no-cache-dir webdriver-manager==4.0.1
        pip install --no-cache-dir requests==2.31.0
        pip install --no-cache-dir python-dotenv==1.0.0
        pip install --no-cache-dir tiktoken==0.5.2
    fi
else
    echo "⚠️  requirements.txt not found. Please install dependencies manually."
fi

# Check if pymilvus is installed
python3 -c "import pymilvus" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ pymilvus not installed. Trying alternative installation..."
    pip install --no-cache-dir pymilvus==2.3.4
fi

# Setup knowledge base
echo "🧠 Setting up knowledge base..."
python3 setup_knowledge_base.py

if [ $? -eq 0 ]; then
    echo "✅ Setup completed successfully!"
    echo ""
    echo "🎯 You can now:"
    echo "   • Run web automation: python app.py"
    echo "   • Query docs interactively: python query_docs.py -i"
    echo "   • Query docs directly: python query_docs.py 'your question'"
    echo ""
    echo "📊 Milvus UI available at: http://localhost:9001"
    echo "   Username: minioadmin"
    echo "   Password: minioadmin"
else
    echo "❌ Setup failed. Please check the logs above."
    echo "💡 Try running the commands manually:"
    echo "   1. $DOCKER_COMPOSE_CMD up -d"
    echo "   2. pip install pymilvus sentence-transformers langchain \"langchain-core>=0.1.7,<0.2\" langchain-community==0.0.10"
    echo "   3. python setup_knowledge_base.py"
    exit 1
fi
