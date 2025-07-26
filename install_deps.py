#!/usr/bin/env python3

import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and handle errors gracefully"""
    print(f"📦 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"Error: {e.stderr}")
        return False

def install_package(package, description=None):
    """Install a single package with error handling"""
    if description is None:
        description = f"Installing {package}"
    
    cmd = f"pip3 install --no-cache-dir {package}"
    return run_command(cmd, description)

def check_package(package_name):
    """Check if a package is installed"""
    try:
        __import__(package_name)
        return True
    except ImportError:
        return False

def main():
    print("🚀 Installing Python dependencies for Selenium + Milvus RAG System")
    print("=" * 70)
    
    # Core packages that usually install without issues
    core_packages = [
        "requests==2.31.0",
        "python-dotenv==1.0.0",
        "selenium==4.15.2",
        "webdriver-manager==4.0.1"
    ]
    
    # ML/AI packages that might need special handling
    ml_packages = [
        "sentence-transformers==4.1.0",
        "pymilvus==2.5.1",
        "tiktoken==0.5.2",
        "openai==1.97.0"
    ]
    
    # LangChain packages
    langchain_packages = [
        "langchain==0.1.0",
        "langchain-community==0.0.10"
    ]
    
    print("📦 Installing core packages...")
    for package in core_packages:
        install_package(package)
    
    print("\n📦 Installing ML/AI packages...")
    for package in ml_packages:
        if not install_package(package):
            # Try alternative installation for problematic packages
            package_name = package.split("==")[0]
            print(f"⚠️  Trying alternative installation for {package_name}...")
            install_package(package_name)
    
    print("\n📦 Installing LangChain packages...")
    for package in langchain_packages:
        install_package(package)
    
    print("\n🔍 Verifying installations...")
    
    # Check critical packages
    critical_packages = {
        "selenium": "selenium",
        "requests": "requests", 
        "pymilvus": "pymilvus",
        "sentence_transformers": "sentence-transformers",
        "langchain": "langchain"
    }
    
    all_good = True
    for import_name, package_name in critical_packages.items():
        if check_package(import_name):
            print(f"✅ {package_name} is installed")
        else:
            print(f"❌ {package_name} is NOT installed")
            all_good = False
    
    if all_good:
        print("\n🎉 All dependencies installed successfully!")
        return True
    else:
        print("\n⚠️  Some dependencies failed to install. You may need to install them manually.")
        print("💡 Try running these commands manually:")
        print("   pip3 install pymilvus")
        print("   pip3 install sentence-transformers")
        print("   pip3 install langchain")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 