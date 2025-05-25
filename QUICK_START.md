# Quick Start Guide

If you're having trouble with the automated setup, follow these manual steps:

## 1. Start Milvus

```bash
# Start Milvus services
docker compose up -d

# Wait for services to start (about 1-2 minutes)
docker compose ps
```

## 2. Install Python Dependencies

### Option A: Use the custom installer (recommended)

```bash
python3 install_deps.py
```

### Option B: Install manually

```bash
# Core packages
pip3 install requests==2.31.0
pip3 install selenium==4.15.2
pip3 install webdriver-manager==4.0.1

# Milvus and ML packages
pip3 install pymilvus==2.5.1
pip3 install sentence-transformers==4.1.0

# LangChain
pip3 install langchain==0.1.0
pip3 install langchain-community==0.0.10

# Optional
pip3 install python-dotenv==1.0.0
pip3 install tiktoken==0.5.2
```

### Option C: If you have compilation issues

```bash
# Install pre-compiled wheels
pip3 install --only-binary=all pymilvus sentence-transformers langchain
```

## 3. Setup Knowledge Base

```bash
python3 setup_knowledge_base.py
```

## 4. Test the System

### Test RAG System

```bash
python3 query_docs.py "What is the pricing structure?"
```

### Test Web Automation

```bash
python3 app.py
```

## 5. Cleanup and Reset (Optional)

### View Milvus Status

```bash
python3 cleanup_milvus.py --info-only
```

### Delete All Collections and Data

```bash
python3 cleanup_milvus.py --yes
```

### Delete Specific Collection

```bash
python3 cleanup_milvus.py --collection docs_collection --yes
```

### Clear Data but Keep Structure

```bash
python3 cleanup_milvus.py --clear-only --yes
```

## Troubleshooting

### Milvus Connection Issues

```bash
# Check if Milvus is running
docker compose ps

# Check logs
docker compose logs standalone

# Restart if needed
docker compose down
docker compose up -d
```

### Python Import Errors

```bash
# Check what's installed
pip3 list | grep -E "(pymilvus|langchain|sentence)"

# Reinstall problematic packages
pip3 uninstall pymilvus
pip3 install pymilvus==2.5.1
```

### macOS Compilation Issues

If you're on macOS and getting compilation errors:

```bash
# Install Xcode command line tools
xcode-select --install

# Use conda instead of pip for problematic packages
conda install -c conda-forge sentence-transformers
conda install -c conda-forge langchain
pip3 install pymilvus
```

### Reset Everything

If you want to start completely fresh:

```bash
# Stop Milvus
docker compose down

# Remove all data
docker compose down -v

# Clean up Python packages
pip3 uninstall pymilvus sentence-transformers langchain -y

# Start fresh
docker compose up -d
python3 install_deps.py
python3 setup_knowledge_base.py
```

## Alternative: Use Docker for Everything

If you continue having Python dependency issues, you can run everything in Docker:

```bash
# Create a Dockerfile for the Python environment
cat > Dockerfile << EOF
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python3", "app.py"]
EOF

# Build and run
docker build -t selenium-rag .
docker run -it --network host selenium-rag python3 query_docs.py -i
```

## Minimal Test

To test if the basic system works:

```bash
python3 test_basic.py
```

Or manually:

```python
# test_basic.py
try:
    import pymilvus
    print("✅ pymilvus imported successfully")

    import sentence_transformers
    print("✅ sentence-transformers imported successfully")

    import langchain
    print("✅ langchain imported successfully")

    import selenium
    print("✅ selenium imported successfully")

    print("\n🎉 All core dependencies are working!")

except ImportError as e:
    print(f"❌ Import error: {e}")
```

## Cleanup Script Usage

The `cleanup_milvus.py` script provides several options:

```bash
# Show help
python3 cleanup_milvus.py --help

# Just show current status
python3 cleanup_milvus.py --info-only

# Delete everything (with confirmation)
python3 cleanup_milvus.py

# Delete everything (no confirmation)
python3 cleanup_milvus.py --yes

# Delete specific collection
python3 cleanup_milvus.py --collection docs_collection

# Clear data but keep collection structure
python3 cleanup_milvus.py --clear-only

# Connect to remote Milvus
python3 cleanup_milvus.py --host remote-host --port 19530
```
