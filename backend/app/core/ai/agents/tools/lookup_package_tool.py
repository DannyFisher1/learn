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
    Inspects the **INTERNAL STRUCTURE** of an installed Python pip package. Use this to understand the modules, functions, and classes available within a specific package.

    Purpose: To provide a developer-focused view of a package's code organization and contents.

    Input:
      - `package_name` (string, required): The distribution name of the Python package as installed by pip (e.g., 'numpy', 'pandas', 'langchain-community'). The tool attempts to resolve this to the correct importable module name (e.g., 'langchain-community' -> 'langchain_community').

    Output:
      - (string): A JSON formatted string summarizing the package structure, including nested modules and their contained functions and classes. Returns a JSON error object on failure (e.g., package not found).

    ***IMPORTANT USAGE NOTES***:
    1.  **Code Structure:** Use this when the user wants to know *what code* is inside a package (module names, function names, class names).
    2.  **Contrast with `get_package_info`:** DO NOT use this tool to get metadata like version, author, or license. Use `get_package_info` for that.
    3.  **Requires Installation:** The package MUST be installed in the Python environment where the backend is running.

    Example Scenarios:
      - User asks: "What modules are available in the pandas library?" -> Use this tool with `package_name="pandas"`.
      - User asks: "Show me the functions inside the `langchain_core.prompts` module." -> Use this tool with `package_name="langchain-core"` (or potentially `langchain` depending on installation) and then explain how to interpret the JSON to find the specific module info.
      - User asks: "What version of numpy is installed?" -> DO NOT use this tool. Use `get_package_info`.
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
    Retrieves **METADATA** about an installed Python pip package. Use this to find information like version, summary, author, license, dependencies, and homepage.

    Purpose: To provide high-level, descriptive information about a package.

    Input:
      - `package_name` (string, required): The distribution name of the Python package as installed by pip (e.g., 'numpy', 'pandas', 'langchain-community').

    Output:
      - (string): A JSON formatted string containing key metadata fields for the package. Returns a JSON error object on failure (e.g., package not found).

    ***IMPORTANT USAGE NOTES***:
    1.  **Package Metadata:** Use this when the user asks for information *about* a package (version, description, author, license, etc.).
    2.  **Contrast with `inspect_package`:** DO NOT use this tool to see the internal code structure (modules, functions, classes). Use `inspect_package` for that.
    3.  **Requires Installation:** The package MUST be installed in the Python environment where the backend is running.

    Example Scenarios:
      - User asks: "What version of langchain is installed?" -> Use this tool with `package_name="langchain"`.
      - User asks: "What is the license for the 'requests' library?" -> Use this tool with `package_name="requests"`.
      - User asks: "What functions are in the numpy.linalg module?" -> DO NOT use this tool. Use `inspect_package`.
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
