import gobby
import sys
import os

print(f"DEBUG_IMPORT: gobby file: {gobby.__file__}")
print(f"DEBUG_IMPORT: gobby path: {gobby.__path__}")
print(f"DEBUG_IMPORT: CWD: {os.getcwd()}")
