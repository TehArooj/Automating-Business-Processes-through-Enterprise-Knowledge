import os
import json
import requests
from pathlib import Path
from typing import List, Dict, Any
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.document_loaders import DirectoryLoader, TextLoader
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MilvusRAGSystem:
    def __init__(self, 
                 collection_name: str = "docs_collection",
                 milvus_host: str = "localhost",
                 milvus_port: str = "19530",
                 embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
                 gemini_api_key: str = None):
        
        self.collection_name = collection_name
        self.milvus_host = milvus_host
        self.milvus_port = milvus_port
        self.gemini_api_key = gemini_api_key or "AIzaSyCGQJM3AcplIqN7jYGIsy-ETMEjPz9ndPo"
        self.llm_model = 'gemini-2.0-flash'
        
        # Initialize embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model,
            model_kwargs={'device': 'cpu'}
        )
        
        # Connect to Milvus
        self._connect_to_milvus()
        self._setup_collection()
    
    def _connect_to_milvus(self):
        try:
            connections.connect("default", host=self.milvus_host, port=self.milvus_port)
            logger.info(f"Connected to Milvus at {self.milvus_host}:{self.milvus_port}")
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    def _setup_collection(self):
        # Define collection schema
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=1000),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=384)  # all-MiniLM-L6-v2 dimension
        ]
        
        schema = CollectionSchema(fields, "Document collection for RAG")
        
        # Create collection if it doesn't exist
        if utility.has_collection(self.collection_name):
            self.collection = Collection(self.collection_name)
            logger.info(f"Using existing collection: {self.collection_name}")
        else:
            self.collection = Collection(self.collection_name, schema)
            logger.info(f"Created new collection: {self.collection_name}")
        
        # Create index for vector field
        index_params = {
            "metric_type": "L2",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128}
        }
        
        if not self.collection.has_index():
            self.collection.create_index("embedding", index_params)
            logger.info("Created index for embedding field")
        
        # Load collection
        self.collection.load()
    
    def load_and_process_documents(self, docs_path: str = "docs"):
        logger.info(f"Loading documents from {docs_path}")
        
        # Load documents
        documents = []
        docs_dir = Path(docs_path)
        
        for file_path in docs_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix in ['.txt', '.md', '.rst', '.mdx']:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if content.strip():
                            doc = Document(
                                page_content=content,
                                metadata={"source": str(file_path.relative_to(docs_dir))}
                            )
                            documents.append(doc)
                except Exception as e:
                    logger.warning(f"Failed to load {file_path}: {e}")
        
        logger.info(f"Loaded {len(documents)} documents")
        
        # Split documents
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        
        split_docs = text_splitter.split_documents(documents)
        logger.info(f"Split into {len(split_docs)} chunks")
        
        return split_docs
    
    def add_documents_to_milvus(self, documents: List[Document]):
        logger.info(f"Adding {len(documents)} documents to Milvus")
        
        # Prepare data for insertion
        texts = [doc.page_content for doc in documents]
        sources = [doc.metadata.get("source", "unknown") for doc in documents]
        
        # Generate embeddings
        embeddings = self.embeddings.embed_documents(texts)
        
        # Insert data
        data = [texts, sources, embeddings]
        self.collection.insert(data)
        self.collection.flush()
        
        logger.info(f"Successfully added {len(documents)} documents to Milvus")
    
    def search_similar_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # Generate query embedding
        query_embedding = self.embeddings.embed_query(query)
        
        # Search parameters
        search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
        
        # Perform search
        results = self.collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["text", "source"]
        )
        
        # Format results
        similar_docs = []
        for hits in results:
            for hit in hits:
                similar_docs.append({
                    "text": hit.entity.get("text"),
                    "source": hit.entity.get("source"),
                    "score": hit.score
                })
        
        return similar_docs
    
    def generate_rag_response(self, query: str, context_docs: List[Dict[str, Any]]) -> str:
        # Prepare context from retrieved documents
        context = "\n\n".join([
            f"Source: {doc['source']}\nContent: {doc['text']}"
            for doc in context_docs
        ])
        
        prompt = f"""
You are a helpful assistant that answers questions based on the provided documentation context.

Context from documentation:
{context}

User Question: {query}

Please provide a comprehensive answer based on the context provided. If the context doesn't contain enough information to answer the question, please say so and provide what information you can.

Answer:
"""
        
        try:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.llm_model}:generateContent?key={self.gemini_api_key}"
            headers = {'Content-Type': 'application/json'}
            data = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 1000
                }
            }
            
            response = requests.post(api_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if (result.get('candidates') and 
                result['candidates'][0].get('content') and 
                result['candidates'][0]['content'].get('parts')):
                return result['candidates'][0]['content']['parts'][0]['text']
            else:
                return "Sorry, I couldn't generate a response."
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"Error generating response: {e}"
    
    def query(self, user_query: str, top_k: int = 5) -> Dict[str, Any]:
        # Search for similar documents
        similar_docs = self.search_similar_documents(user_query, top_k)
        
        # Generate response using RAG
        response = self.generate_rag_response(user_query, similar_docs)
        
        return {
            "query": user_query,
            "response": response,
            "sources": [doc["source"] for doc in similar_docs],
            "retrieved_docs": similar_docs
        }
    
    def setup_knowledge_base(self, docs_path: str = "docs"):
        # Check if collection already has data
        if self.collection.num_entities > 0:
            logger.info(f"Collection already contains {self.collection.num_entities} documents")
            return
        
        # Load and process documents
        documents = self.load_and_process_documents(docs_path)
        
        if documents:
            # Add documents to Milvus
            self.add_documents_to_milvus(documents)
            logger.info("Knowledge base setup complete")
        else:
            logger.warning("No documents found to add to knowledge base")

def main():
    # Initialize RAG system
    rag_system = MilvusRAGSystem()
    
    # Setup knowledge base
    rag_system.setup_knowledge_base()
    
    # Example query
    test_query = "What is the pricing structure?"
    result = rag_system.query(test_query)
    
    print(f"Query: {result['query']}")
    print(f"Response: {result['response']}")
    print(f"Sources: {result['sources']}")

if __name__ == "__main__":
    main() 