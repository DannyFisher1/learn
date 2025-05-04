# app/core/ai/agents/tools/package_inspector_tool.py
import subprocess
import sys
import importlib
import pkgutil
import inspect
import json
import importlib.util
from langchain.tools import tool
from importlib.metadata import PackageNotFoundError, distribution, metadata


@tool
def inspect_package(package_name: str) -> str:
    """
    Inspect an installed Python pip package: list its modules, functions, and classes.
    Returns a JSON summary. Supports resolving distribution vs importable module name.
    
    Example input: 'pandas', 'numpy', 'langchain-community'
    """

    def resolve_importable_module(pkg: str):
        try:
            dist = distribution(pkg)
            top_level = dist.read_text("top_level.txt")
            if top_level:
                return top_level.strip().splitlines()[0]

            # Fallback: try common import-style equivalents
            candidate_names = [pkg.replace("-", "_"), pkg.replace("-", "")]
            for name in candidate_names:
                if importlib.util.find_spec(name):
                    return name

            raise ImportError(f"No importable module found for '{pkg}'")
        except PackageNotFoundError:
            raise ImportError(f"Package '{pkg}' is not installed.")


    def inspect_module(module):
        return {
            "functions": [n for n, o in inspect.getmembers(module, inspect.isfunction)],
            "classes": [n for n, o in inspect.getmembers(module, inspect.isclass)],
        }

    def scan_package(pkg_name):
        pkg = importlib.import_module(pkg_name)
        result = {"package": pkg_name, "modules": {}}

        if not hasattr(pkg, "__path__"):
            result["modules"][pkg_name] = inspect_module(pkg)
            return result

        for _, name, _ in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
            try:
                mod = importlib.import_module(name)
                result["modules"][name] = inspect_module(mod)
            except Exception:
                continue

        return result

    try:
        importable_name = resolve_importable_module(package_name)
        data = scan_package(importable_name)
        return json.dumps(data, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool 
def get_package_info(package_name: str) -> str:
    """
    Return basic metadata about a pip package: version, summary, license, homepage, dependencies, etc.
    
    Input: pip package name (e.g., 'numpy', 'langchain-community')
    Output: JSON summary of metadata fields.
    """

    try:
        dist = distribution(package_name)
        meta = metadata(package_name)

        info = {
            "name": dist.metadata['Name'],
            "version": dist.version,
            "summary": meta.get('Summary'),
            "license": meta.get('License'),
            "author": meta.get('Author'),
            "author_email": meta.get('Author-email'),
            "home_page": meta.get('Home-page'),
            "project_urls": meta.get_all('Project-URL') or [],
            "requires": dist.requires or []
        }

        return json.dumps(info, indent=2)

    except PackageNotFoundError:
        return json.dumps({"error": f"Package '{package_name}' is not installed."})
    except Exception as e:
        return json.dumps({"error": str(e)})
