# app/core/ai/agents/tools/lookup_package_tool.py # Note: Filename was different in comment

import asyncio # <<< Added import
import sys
import importlib
import pkgutil
import inspect
import json
import importlib.util
from langchain.tools import tool
from importlib.metadata import PackageNotFoundError, distribution, metadata
from langchain_core.tools import ToolException # <<< Added import

# --- App imports ---
from app.utils import get_logger # Assuming get_logger is in utils

logger = get_logger(__name__) # Initialize logger


# --- Synchronous Helper for inspect_package ---
def _sync_inspect_package(package_name: str) -> str:
    """Synchronous core logic for inspecting package structure."""
    logger.debug(f"Starting synchronous inspection for package: {package_name}")

    # --- Helper functions remain nested or defined here ---
    def resolve_importable_module(pkg: str):
        try:
            dist = distribution(pkg) # Blocking I/O potentially
            # Blocking I/O
            top_level_text = dist.read_text("top_level.txt") if dist.read_text("top_level.txt") else None
            if top_level_text:
                module_name = top_level_text.strip().splitlines()[0]
                logger.debug(f"Resolved '{pkg}' to importable module '{module_name}' via top_level.txt")
                return module_name

            # Fallback: try common import-style equivalents
            candidate_names = [pkg.replace("-", "_"), pkg.replace("-", "")]
            for name in candidate_names:
                 # find_spec can involve file system checks
                 if importlib.util.find_spec(name):
                      logger.debug(f"Resolved '{pkg}' to importable module '{name}' via fallback.")
                      return name

            logger.error(f"Could not resolve importable module for package '{pkg}'")
            raise ImportError(f"No importable module found for '{pkg}'")
        except PackageNotFoundError:
            logger.warning(f"Package '{pkg}' not found during resolution.")
            raise # Re-raise PackageNotFoundError

    def inspect_module(module):
        # inspect.getmembers might involve importing parts, potentially blocking
        functions = [n for n, o in inspect.getmembers(module, inspect.isfunction)]
        classes = [n for n, o in inspect.getmembers(module, inspect.isclass)]
        logger.debug(f"Inspected module '{module.__name__}': found {len(functions)} functions, {len(classes)} classes.")
        return {
            "functions": functions,
            "classes": classes,
        }

    def scan_package(pkg_name):
        # import_module is blocking
        pkg = importlib.import_module(pkg_name)
        result = {"package": pkg_name, "modules": {}}
        logger.debug(f"Scanning package '{pkg_name}'...")

        if not hasattr(pkg, "__path__"): # Single module package
            logger.debug(f"'{pkg_name}' is a single module.")
            result["modules"][pkg_name] = inspect_module(pkg)
            return result

        # walk_packages involves file system iteration and imports, can block
        logger.debug(f"Walking package path for '{pkg_name}'...")
        module_count = 0
        for _, name, _ in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
            try:
                # import_module is blocking
                mod = importlib.import_module(name)
                result["modules"][name] = inspect_module(mod)
                module_count += 1
            except Exception as import_err:
                # Log errors during module import within the package but continue
                logger.warning(f"Could not import/inspect module '{name}' within '{pkg_name}': {import_err}")
                continue
        logger.debug(f"Finished walking package '{pkg_name}', inspected {module_count} modules.")
        return result
    # --- End of nested helper functions ---

    try:
        importable_name = resolve_importable_module(package_name)
        data = scan_package(importable_name)
        logger.info(f"Successfully inspected package '{package_name}' (resolved to '{importable_name}').")
        return json.dumps(data, indent=2)
    except PackageNotFoundError:
         # Re-raise specific error for async wrapper
         raise PackageNotFoundError(f"Package '{package_name}' is not installed.")
    except ImportError as ie:
        # Re-raise specific error for async wrapper
        raise ImportError(f"Could not resolve importable module for '{package_name}': {ie}")
    except Exception as e:
        # Catch-all for other errors during inspection
        logger.error(f"Error during synchronous inspection of '{package_name}': {e}", exc_info=True)
        # Re-raise a generic exception for the async wrapper
        raise RuntimeError(f"Failed to inspect package '{package_name}': {e}")

# --- Async Tool Wrapper for inspect_package ---
@tool
async def inspect_package(package_name: str) -> str: # <<< Changed to async def
    """
    Inspects the **INTERNAL STRUCTURE** of an installed Python pip package asynchronously.
    (Docstring partially updated for async context, detailed usage notes remain)
    """
    logger.info(f"Inspect Package Tool invoked (async) for: '{package_name}'")
    try:
        # Wrap the synchronous helper function call
        result_json = await asyncio.to_thread(_sync_inspect_package, package_name)
        return result_json
    except PackageNotFoundError as e:
         logger.warning(f"Package not found error for '{package_name}': {e}")
         raise ToolException(f"Package '{package_name}' is not installed.") from e
    except ImportError as e:
         logger.warning(f"Import error for '{package_name}': {e}")
         raise ToolException(f"Could not resolve or import package '{package_name}'. Is it installed correctly?") from e
    except Exception as e:
         logger.error(f"Unexpected error in async inspect_package tool for '{package_name}': {e}", exc_info=True)
         raise ToolException(f"An internal error occurred while inspecting package '{package_name}'.")


# --- Synchronous Helper for get_package_info ---
def _sync_get_package_info(package_name: str) -> str:
    """Synchronous core logic for retrieving package metadata."""
    logger.debug(f"Starting synchronous metadata retrieval for package: {package_name}")
    try:
        # distribution() and metadata() involve file system I/O
        dist = distribution(package_name)
        meta = metadata(package_name)

        # Extracting metadata is usually fast
        info = {
            "name": dist.metadata.get('Name', package_name), # Use get for safety
            "version": dist.version,
            "summary": meta.get('Summary'),
            "license": meta.get('License'),
            "author": meta.get('Author'),
            "author_email": meta.get('Author-email'),
            "home_page": meta.get('Home-page'),
            "project_urls": dict(url.split(', ', 1) for url in meta.get_all('Project-URL', []) if ', ' in url), # Nicer format
            "requires": dist.requires or []
        }
        logger.info(f"Successfully retrieved metadata for package '{package_name}'.")
        return json.dumps(info, indent=2)

    except PackageNotFoundError:
        logger.warning(f"Package '{package_name}' not found during metadata retrieval.")
        raise # Re-raise for async wrapper
    except Exception as e:
        logger.error(f"Error during synchronous metadata retrieval for '{package_name}': {e}", exc_info=True)
        raise RuntimeError(f"Failed to retrieve metadata for package '{package_name}': {e}")


# --- Async Tool Wrapper for get_package_info ---
@tool
async def get_package_info(package_name: str) -> str: # <<< Changed to async def
    """
    Retrieves **METADATA** about an installed Python pip package asynchronously.
    (Docstring partially updated for async context, detailed usage notes remain)
    """
    logger.info(f"Get Package Info Tool invoked (async) for: '{package_name}'")
    try:
        # Wrap the synchronous helper function call
        result_json = await asyncio.to_thread(_sync_get_package_info, package_name)
        return result_json
    except PackageNotFoundError as e:
        logger.warning(f"Package not found error for '{package_name}': {e}")
        raise ToolException(f"Package '{package_name}' is not installed.") from e
    except Exception as e:
        logger.error(f"Unexpected error in async get_package_info tool for '{package_name}': {e}", exc_info=True)
        raise ToolException(f"An internal error occurred while retrieving info for package '{package_name}'.")