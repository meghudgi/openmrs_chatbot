#!/usr/bin/env python3
"""
Quick Start Guide - OpenMRS Clinical Chatbot

This script helps verify the installation and run the chatbot.
"""

import subprocess
import sys
import os

def check_python_version():
    """Check if Python 3.11+ is installed"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        print("❌ Python 3.11+ required")
        print(f"   Current: Python {version.major}.{version.minor}")
        return False
    print(f"✓ Python {version.major}.{version.minor} detected")
    return True

def check_dependencies():
    """Check if required packages are installed"""
    required = {
        'mysql.connector': 'mysql-connector-python',
        'chromadb': 'chromadb',
        'langchain': 'langchain',
        'google': 'google-generativeai',
        'dotenv': 'python-dotenv'
    }
    optional = {
        'pypdf': 'pypdf'
    }
    
    missing = []
    
    for package, pip_name in required.items():
        try:
            __import__(package)
            print(f"✓ {pip_name} installed")
        except ImportError:
            print(f"❌ {pip_name} missing")
            missing.append(pip_name)
    
    for package, pip_name in optional.items():
        try:
            __import__(package)
            print(f"✓ {pip_name} installed (optional)")
        except ImportError:
            print(f"⚠️  {pip_name} missing (optional - PDF support disabled)")
    
    return len(missing) == 0, missing

def check_configuration():
    """Check if .env file exists"""
    if os.path.exists('.env'):
        print("✓ .env configuration file found")
        return True
    else:
        print("⚠ .env not found (using .env.example as template)")
        if os.path.exists('.env.example'):
            print("  Run: cp .env.example .env")
            return False
    return False

def check_data_files():
    """Check if all data files exist"""
    files = [
        'data/medication.json',
        'data/immunization.json',
        'data/milestones.json'
    ]
    
    all_exist = True
    for file in files:
        if os.path.exists(file):
            print(f"✓ {file} found")
        else:
            print(f"❌ {file} missing")
            all_exist = False
    
    return all_exist

def main():
    print("\n" + "=" * 60)
    print("OpenMRS Clinical Chatbot - Quick Start")
    print("=" * 60)
    
    print("\n📋 Checking environment...")
    
    if not check_python_version():
        sys.exit(1)
    
    print("\n📦 Checking dependencies...")
    deps_ok, missing = check_dependencies()
    
    if not deps_ok:
        print(f"\n❌ Missing packages: {', '.join(missing)}")
        print("\nInstall with:")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    
    print("\n⚙️  Checking configuration...")
    config_ok = check_configuration()
    
    if not config_ok:
        print("\n⚠️  Configuration needed:")
        print("  1. cp .env.example .env")
        print("  2. Edit .env with database credentials")
        print("  3. Set OPENAI_API_KEY")
        sys.exit(1)
    
    print("\n📂 Checking data files...")
    data_ok = check_data_files()
    
    if not data_ok:
        print("\n❌ Missing required data files")
        sys.exit(1)
    
    print("\n✅ All checks passed!")
    print("\n" + "=" * 60)
    print("READY TO USE")
    print("=" * 60)
    
    print("\nOptions:")
    print("\n1. Run test suite:")
    print("   python test.py")
    print("\n2. Initialize knowledge base (if PDFs added):")
    print("   python init_kb.py")
    print("\n3. Start interactive chatbot:")
    print("   python main.py")
    print("\n4. Test with single query:")
    print("   python main.py \"What is Metformin used for?\"")
    
    print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    main()
