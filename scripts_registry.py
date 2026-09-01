# script_registry.py
import os
import importlib
import inspect
from pathlib import Path

class ScriptRegistry:
    SCRIPTS_DIR = "scripts-library/"
    
    def discover_scripts(self):
        """Auto-discover Python scripts with metadata"""
        scripts = {}
        for file in Path(self.SCRIPTS_DIR).glob("*.py"):
            if not file.name.startswith("__"):
                module = importlib.import_module(f"scripts.{file.stem}")
                if hasattr(module, "Script"):
                    # Scripts should define a class with:
                    # - name, description, version
                    # - execute() method
                    script_class = getattr(module, "Script")
                    scripts[file.stem] = {
                        'class': script_class,
                        'metadata': script_class.metadata()
                    }
        return scripts
