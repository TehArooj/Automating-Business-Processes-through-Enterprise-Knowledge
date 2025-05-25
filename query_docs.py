#!/usr/bin/env python3

import sys
import argparse
from rag_system import MilvusRAGSystem
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def query_documentation(query: str, top_k: int = 5):
    """Query the documentation using RAG system"""
    try:
        # Initialize RAG system
        rag_system = MilvusRAGSystem()
        
        # Query the system
        result = rag_system.query(query, top_k)
        
        # Display results
        print(f"\n🔍 Query: {result['query']}")
        print("=" * 80)
        print(f"\n📝 Response:")
        print(result['response'])
        print("\n" + "=" * 80)
        
        print(f"\n📚 Sources ({len(result['sources'])}):")
        for i, source in enumerate(result['sources'], 1):
            print(f"{i}. {source}")
        
        if result['retrieved_docs']:
            print(f"\n📄 Retrieved Document Snippets:")
            for i, doc in enumerate(result['retrieved_docs'], 1):
                print(f"\n{i}. Source: {doc['source']}")
                print(f"   Score: {doc['score']:.4f}")
                print(f"   Content: {doc['text'][:200]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"Error querying documentation: {e}")
        return False

def interactive_mode():
    """Run in interactive mode for continuous querying"""
    print("🤖 Documentation Query System")
    print("Type 'quit' or 'exit' to stop")
    print("=" * 50)
    
    try:
        rag_system = MilvusRAGSystem()
        
        while True:
            try:
                query = input("\n💬 Enter your question: ").strip()
                
                if query.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                if not query:
                    continue
                
                result = rag_system.query(query)
                
                print(f"\n📝 Answer:")
                print(result['response'])
                print(f"\n📚 Sources: {', '.join(result['sources'])}")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                
    except Exception as e:
        logger.error(f"Failed to initialize RAG system: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Query documentation using RAG system")
    parser.add_argument("query", nargs="?", help="Question to ask the documentation")
    parser.add_argument("-k", "--top-k", type=int, default=5, help="Number of top results to retrieve")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_mode()
    elif args.query:
        success = query_documentation(args.query, args.top_k)
        if not success:
            sys.exit(1)
    else:
        # If no query provided, show some example queries
        print("📖 Documentation Query System")
        print("=" * 50)
        print("\nExample queries you can try:")
        print("• python query_docs.py 'How do I set up authentication?'")
        print("• python query_docs.py 'What are the pricing options?'")
        print("• python query_docs.py 'How do I use the API?'")
        print("• python query_docs.py -i  # Interactive mode")
        print("\nOr run with -h for help")

if __name__ == "__main__":
    main() 