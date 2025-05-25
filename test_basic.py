#!/usr/bin/env python3

def test_imports():
    """Test if all required packages can be imported"""
    print("🔍 Testing Python dependencies...")
    print("=" * 50)
    
    packages = [
        ("pymilvus", "Milvus vector database client"),
        ("sentence_transformers", "Sentence transformers for embeddings"),
        ("langchain", "LangChain framework"),
        ("selenium", "Selenium web automation"),
        ("requests", "HTTP requests library"),
        ("webdriver_manager", "WebDriver manager")
    ]
    
    success_count = 0
    total_count = len(packages)
    
    for package, description in packages:
        try:
            __import__(package)
            print(f"✅ {package:<20} - {description}")
            success_count += 1
        except ImportError as e:
            print(f"❌ {package:<20} - FAILED: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Results: {success_count}/{total_count} packages imported successfully")
    
    if success_count == total_count:
        print("🎉 All dependencies are working!")
        return True
    else:
        print("⚠️  Some dependencies are missing. Please install them.")
        print("\n💡 To install missing packages:")
        print("   python install_deps.py")
        print("   OR")
        print("   pip install pymilvus sentence-transformers langchain selenium")
        return False

def test_milvus_connection():
    """Test connection to Milvus"""
    print("\n🔍 Testing Milvus connection...")
    try:
        from pymilvus import connections
        connections.connect("default", host="localhost", port="19530")
        print("✅ Successfully connected to Milvus")
        connections.disconnect("default")
        return True
    except Exception as e:
        print(f"❌ Failed to connect to Milvus: {e}")
        print("💡 Make sure Milvus is running: docker compose up -d")
        return False

def test_embeddings():
    """Test sentence transformers"""
    print("\n🔍 Testing sentence transformers...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        embeddings = model.encode(["Hello world", "Test sentence"])
        print(f"✅ Generated embeddings with shape: {embeddings.shape}")
        return True
    except Exception as e:
        print(f"❌ Failed to test embeddings: {e}")
        return False

def test_selenium():
    """Test Selenium WebDriver setup"""
    print("\n🔍 Testing Selenium WebDriver...")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        # Just test the setup, don't actually start browser
        service = Service(ChromeDriverManager().install())
        print("✅ Chrome WebDriver setup successful")
        return True
    except Exception as e:
        print(f"❌ Failed to setup WebDriver: {e}")
        print("💡 Make sure Chrome browser is installed")
        return False

def main():
    """Run all tests"""
    print("🚀 Selenium + Milvus RAG System - Dependency Test")
    print("=" * 60)
    
    tests = [
        ("Package Imports", test_imports),
        ("Milvus Connection", test_milvus_connection),
        ("Embeddings", test_embeddings),
        ("Selenium WebDriver", test_selenium)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 Test Summary:")
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status} - {test_name}")
        if result:
            passed += 1
    
    print(f"\n📊 Overall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All systems are ready!")
        print("\n🚀 You can now run:")
        print("   • python setup_knowledge_base.py")
        print("   • python query_docs.py -i")
        print("   • python app.py")
    else:
        print("⚠️  Some components need attention. Check the errors above.")
        print("\n💡 Quick fixes:")
        print("   • For missing packages: python install_deps.py")
        print("   • For Milvus: docker compose up -d")
        print("   • For Chrome: Install Chrome browser")

if __name__ == "__main__":
    main() 