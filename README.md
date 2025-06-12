# Selenium Automation with Milvus RAG System

This project combines Selenium web automation with a Retrieval-Augmented Generation (RAG) system powered by Milvus vector database and LangChain. The system can automate web interactions while leveraging documentation knowledge to make more informed decisions.

## Features

- **Selenium Web Automation**: Automated web browser interactions using Selenium WebDriver
- **Milvus Vector Database**: High-performance vector storage for document embeddings
- **RAG System**: Retrieval-Augmented Generation using LangChain and Gemini AI
- **Documentation Query**: Interactive CLI for querying documentation
- **Enhanced LLM Context**: Web automation enhanced with relevant documentation context
- **Data Management**: Complete cleanup and reset capabilities

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Selenium      │    │   Milvus        │    │   Gemini AI     │
│   WebDriver     │◄──►│   Vector DB     │◄──►│   LLM           │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                       ▲                       ▲
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Chrome        │    │   Document      │    │   RAG Context   │
│   Browser       │    │   Embeddings    │    │   Generation    │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Prerequisites

- Python 3.8+
- Docker and Docker Compose
- Chrome browser
- Gemini API key

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd selenium-milvus-rag
```

### 2. Start Services

```bash
# Option A: Use the automated script
./start.sh

# Option B: Manual setup
# Install dependencies
python3 install_deps.py
# Start Milvus services
docker-compose up -d
# Setup knowledge base
python setup_knowledge_base.py
```

### 2. Verify the Setup

Check that Milvus is running and accessible:

```bash
# Check Milvus containers
docker-compose ps

# Check Milvus logs
docker-compose logs standalone
```

## Usage

### Web Automation with RAG

Run the main Selenium automation script:

```bash
python app.py
```

The script will:

1. Initialize the RAG system
2. Start Chrome browser
3. Navigate to the target website
4. Use LLM with RAG context to generate automation steps
5. Execute the steps using Selenium

### Documentation Querying

#### Interactive Mode

```bash
python query_docs.py -i
```

#### Single Query

```bash
python query_docs.py "How do I set up authentication?"
```

#### With Custom Top-K Results

```bash
python query_docs.py "What are the pricing options?" -k 10
```

### Data Management and Cleanup

#### View Current Status

```bash
python cleanup_milvus.py --info-only
```

#### Delete All Collections and Data

```bash
# With confirmation prompt
python cleanup_milvus.py

# Skip confirmation
python cleanup_milvus.py --yes
```

#### Delete Specific Collection

```bash
python cleanup_milvus.py --collection docs_collection --yes
```

#### Clear Data but Keep Collection Structure

```bash
python cleanup_milvus.py --clear-only --yes
```

#### Reset and Rebuild Knowledge Base

```bash
# Complete reset
python cleanup_milvus.py --yes
python setup_knowledge_base.py
```

### Example Queries

- "How do I set up authentication?"
- "What are the pricing options?"
- "How do I use the API?"
- "What security features are available?"
- "How do I contribute to the project?"

## Configuration

### Environment Variables

You can customize the system using environment variables:

```bash
# Milvus connection
export MILVUS_HOST=localhost
export MILVUS_PORT=19530

# Gemini API
export GEMINI_API_KEY=your_api_key_here

# Embedding model
export EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### Customizing the RAG System

Edit `rag_system.py` to modify:

- Collection schema
- Embedding model
- Chunk size and overlap
- Search parameters

### Customizing Web Automation

Edit `app.py` to modify:

- Target URLs
- User goals
- Selenium timeouts
- LLM prompts

## File Structure

```
├── app.py                    # Main Selenium automation script
├── rag_system.py            # Milvus RAG system implementation
├── setup_knowledge_base.py  # Knowledge base setup script
├── query_docs.py           # CLI for querying documentation
├── requirements.txt        # Python dependencies
├── docker-compose.yml      # Milvus Docker setup
├── README.md              # This file
└── docs/                  # Documentation folder
    ├── api/
    ├── concepts/
    ├── contributing/
    ├── organization/
    ├── platforms/
    ├── pricing/
    ├── product/
    └── security-legal-pii/
```

## How It Works

### 1. Document Processing

- Documents from `docs/` are loaded and split into chunks
- Each chunk is embedded using sentence-transformers
- Embeddings are stored in Milvus with metadata

### 2. RAG Query Process

- User query is embedded using the same model
- Milvus performs vector similarity search
- Top-K most relevant documents are retrieved
- Context is provided to Gemini AI for response generation

### 3. Enhanced Web Automation

- User goals are analyzed for documentation relevance
- RAG system provides relevant context
- LLM generates web automation steps with enhanced understanding
- Selenium executes the steps

## Troubleshooting

### Milvus Connection Issues

```bash
# Check if Milvus is running
docker-compose ps

# Restart Milvus
docker-compose down
docker-compose up -d

# Check logs
docker-compose logs standalone
```

### Python Dependencies

```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Check for conflicts
pip check
```

### Chrome Driver Issues

```bash
# Update Chrome driver
pip install --upgrade webdriver-manager
```

### Memory Issues

If you encounter memory issues with large document sets:

- Reduce chunk size in `rag_system.py`
- Process documents in batches
- Use a smaller embedding model

## Performance Optimization

### For Large Document Sets

- Use batch processing for document insertion
- Implement incremental updates
- Consider using GPU for embeddings

### For Better Search Results

- Experiment with different embedding models
- Adjust chunk size and overlap
- Fine-tune search parameters

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:

1. Check the troubleshooting section
2. Review Milvus documentation
3. Check LangChain documentation
4. Open an issue on GitHub
