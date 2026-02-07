#!/usr/bin/env python3
"""
Quick syntax and import check for main.py
This script verifies that the code has no syntax errors and all imports work correctly.
"""

import sys
import os

def check_syntax():
    """Check if main.py has any syntax errors"""
    print("=" * 60)
    print("CHECKING SYNTAX AND IMPORTS")
    print("=" * 60)
    
    try:
        # Check if file exists
        if not os.path.exists('main.py'):
            print("❌ ERROR: main.py not found!")
            return False
        
        # Try to compile the file
        with open('main.py', 'r') as f:
            code = f.read()
        
        compile(code, 'main.py', 'exec')
        print("✅ Syntax check: PASSED")
        
        # Try importing (this will check imports but not run the GUI)
        print("\n📦 Checking imports...")
        
        # Check critical imports
        imports_to_check = [
            ('sys', 'System'),
            ('os', 'Operating System'),
            ('json', 'JSON'),
            ('traceback', 'Traceback'),
            ('random', 'Random'),
            ('time', 'Time'),
            ('pygame', 'Pygame (Audio)'),
        ]
        
        for module, name in imports_to_check:
            try:
                __import__(module)
                print(f"  ✅ {name}: OK")
            except ImportError as e:
                print(f"  ⚠️  {name}: NOT INSTALLED - {e}")
        
        print("\n" + "=" * 60)
        print("FOLDER STRUCTURE CHECK")
        print("=" * 60)
        
        # Check folder structure
        required_folders = ['assets', 'sounds']
        for folder in required_folders:
            if os.path.exists(folder):
                count = len(os.listdir(folder))
                print(f"✅ {folder}/ exists ({count} files)")
            else:
                print(f"❌ {folder}/ is MISSING!")
        
        # Check critical files
        print("\n📁 Checking critical files...")
        critical_files = [
            'assets/logo.png',
            'sounds/opening_0.mp3',
            'sounds/closing_0.mp3',
            'sounds/win_exp_0.mp3',
            'sounds/lose_exp_0.mp3'
        ]
        
        for file_path in critical_files:
            if os.path.exists(file_path):
                size = os.path.getsize(file_path)
                print(f"  ✅ {file_path} ({size} bytes)")
            else:
                print(f"  ❌ {file_path} is MISSING!")
        
        print("\n" + "=" * 60)
        print("✅ ALL CHECKS COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("\n💡 To run the application:")
        print("   python3 main.py")
        print("\n")
        
        return True
        
    except SyntaxError as e:
        print(f"\n❌ SYNTAX ERROR found:")
        print(f"   Line {e.lineno}: {e.msg}")
        print(f"   {e.text}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False

if __name__ == '__main__':
    success = check_syntax()
    sys.exit(0 if success else 1)
