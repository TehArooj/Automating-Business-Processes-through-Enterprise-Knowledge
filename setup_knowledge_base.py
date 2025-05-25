#!/usr/bin/env python3

import os
import sys
import time
from pathlib import Path
from rag_system import MilvusRAGSystem
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def wait_for_milvus(rag_system, max_retries=30, delay=2):
    """Wait for Milvus to be ready"""
    for i in range(max_retries):
        try:
            rag_system._connect_to_milvus()
            logger.info("Milvus is ready!")
            return True
        except Exception as e:
            logger.info(f"Waiting for Milvus... (attempt {i+1}/{max_retries})")
            time.sleep(delay)
    
    logger.error("Milvus is not ready after maximum retries")
    return False

def setup_docs_knowledge_base():
    """Setup the knowledge base with documents from the docs folder"""
    
    # Check if docs folder exists
    docs_path = Path("docs")
    if not docs_path.exists():
        logger.error("docs folder not found. Please ensure the docs folder exists.")
        return False
    
    try:
        # Initialize RAG system
        logger.info("Initializing Milvus RAG system...")
        rag_system = MilvusRAGSystem()
        
        # Wait for Milvus to be ready
        if not wait_for_milvus(rag_system):
            return False
        
        # Setup knowledge base
        logger.info("Setting up knowledge base...")
        rag_system.setup_knowledge_base("docs")
        
        # Test the system with a sample query
        logger.info("Testing the system...")
        test_queries = [
            "What is the pricing structure?",
            "How do I contribute to the project?",
            "What are the security features?",
            "How do I use the API?"
        ]
        
        for query in test_queries:
            logger.info(f"Testing query: {query}")
            result = rag_system.query(query)
            logger.info(f"Response: {result['response'][:200]}...")
            logger.info(f"Sources: {result['sources']}")
            print("-" * 80)
        
        logger.info("Knowledge base setup completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up knowledge base: {e}")
        return False

def main():
    """Main function"""
    print("Setting up Milvus RAG Knowledge Base")
    print("=" * 50)
    
    success = setup_docs_knowledge_base()
    
    if success:
        print("\n✅ Knowledge base setup completed successfully!")
        print("You can now use the RAG system to query your documentation.")
    else:
        print("\n❌ Knowledge base setup failed!")
        print("Please check the logs and ensure Milvus is running.")
        sys.exit(1)

if __name__ == "__main__":
    main() 