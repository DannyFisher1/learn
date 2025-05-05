# app/core/project_generator/testing.py

import asyncio
import logging
import os
import sys
from pathlib import Path
import time
from typing import Tuple, Optional

from app.utils import get_logger # Use shared logger utility
from app import config as app_config

logger = get_logger(__name__)

# --- Constants ---
REQUIREMENTS_FILE = "requirements.txt"
VENV_NAME = "venv_proj_test" # Name for the temporary virtual environment
venv_path = Path(VENV_NAME)
MAX_TEST_RUNTIME = 300 # Maximum seconds to allow tests to run (5 minutes)

# --- Helper Functions ---

async def _run_subprocess(command: str, cwd: Path) -> Tuple[int, str, str]:
    """Runs a subprocess and returns exit code, stdout, and stderr."""
    logger.debug(f"Running command in {cwd}: {command}")
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=MAX_TEST_RUNTIME
        )
        exit_code = process.returncode
        stdout_str = stdout.decode('utf-8', errors='ignore')
        stderr_str = stderr.decode('utf-8', errors='ignore')
        logger.debug(f"Command finished with exit code {exit_code}")
        # Log stdout/stderr only if there was an error for brevity
        if exit_code != 0:
            logger.debug(f"Stdout:\n{stdout_str}")
            logger.debug(f"Stderr:\n{stderr_str}")
        return exit_code, stdout_str, stderr_str
    except asyncio.TimeoutError:
        logger.error(f"Command timed out after {MAX_TEST_RUNTIME}s: {command}")
        try:
            process.terminate()
            await process.wait() # Ensure termination
        except ProcessLookupError:
            pass # Process already terminated
        except Exception as term_e:
            logger.error(f"Error terminating timed-out process: {term_e}")
        return -1, "", "TimeoutError: Process killed due to exceeding time limit."
    except Exception as e:
        logger.error(f"Error running command {command}: {e}", exc_info=True)
        return -1, "", f"Exception: {e}"

async def _create_and_activate_venv(project_dir: Path) -> Optional[str]:
    """Creates a virtual environment and returns the path to its python executable."""
    venv_path = project_dir / VENV_NAME
    python_executable = sys.executable # Use the same python that runs the backend

    # Create venv
    logger.info(f"Creating virtual environment in: {venv_path}")
    create_cmd = f'"{python_executable}" -m venv {VENV_NAME}'
    exit_code, _, stderr = await _run_subprocess(create_cmd, project_dir)
    if exit_code != 0:
        logger.error(f"Failed to create virtual environment at {venv_path}. Stderr: {stderr}")
        return None

    # Determine path to python/pip within the venv
    if sys.platform == "win32":
        venv_python = venv_path / "Scripts" / "python.exe"
        # venv_pip = venv_path / "Scripts" / "pip.exe"
    else:
        venv_python = venv_path / "bin" / "activate"
        # venv_pip = venv_path / "bin" / "pip"

    if not venv_python.exists():
         logger.error(f"Could not find python executable in venv: {venv_python}")
         return None

    logger.info(f"Virtual environment created successfully. Python: {venv_python}")
    return str(venv_python)

async def _install_dependencies(project_dir: Path, venv_python_executable: str) -> bool:
    """Installs dependencies from requirements.txt or pyproject.toml using the venv pip."""
    requirements_path = project_dir / "requirements.txt"
    pyproject_path = project_dir / "pyproject.toml"
    install_log = []
    success = True

    venv_pip_cmd = f'"{venv_python_executable}" -m pip'

    # Upgrade pip first
    logger.info("Upgrading pip in venv...")
    upgrade_cmd = f'{venv_pip_cmd} install --upgrade pip'
    exit_code, stdout, stderr = await _run_subprocess(upgrade_cmd, project_dir)
    install_log.append(f"--- Pip Upgrade ---\nExit Code: {exit_code}\nStdout:\n{stdout}\nStderr:\n{stderr}")
    if exit_code != 0:
        logger.warning(f"Failed to upgrade pip in venv. Proceeding anyway. Stderr: {stderr}")
        # Don't mark as failure, might still work

    # Install from requirements.txt if it exists
    if requirements_path.exists():
        logger.info(f"Found requirements.txt. Installing dependencies...")
        install_cmd = f'{venv_pip_cmd} install -r "{requirements_path.name}"'
        exit_code, stdout, stderr = await _run_subprocess(install_cmd, project_dir)
        install_log.append(f"--- requirements.txt Install ---\nExit Code: {exit_code}\nStdout:\n{stdout}\nStderr:\n{stderr}")
        if exit_code != 0:
            logger.error(f"Failed to install dependencies from requirements.txt. Stderr: {stderr}")
            success = False
        else:
            logger.info("Successfully installed dependencies from requirements.txt")
    else:
        logger.info("No requirements.txt found.")
        install_log.append("--- requirements.txt Install: Skipped (File not found) ---")

    # Install from pyproject.toml if it exists (and requirements install succeeded or didn't run)
    # Assumes basic install command, adjust if specific extras needed
    if pyproject_path.exists() and success:
        logger.info(f"Found pyproject.toml. Installing project in editable mode...")
        # Install project itself (often needed for tests to find local packages)
        # Ensure wheel is installed first for pyproject.toml builds
        wheel_cmd = f'{venv_pip_cmd} install wheel'
        exit_code_wheel, _, stderr_wheel = await _run_subprocess(wheel_cmd, project_dir)
        if exit_code_wheel != 0:
             logger.warning(f"Failed to install wheel in venv: {stderr_wheel}. pyproject.toml install might fail.")

        # Install project in editable mode
        install_cmd = f'{venv_pip_cmd} install -e .'
        exit_code, stdout, stderr = await _run_subprocess(install_cmd, project_dir)
        install_log.append(f"--- pyproject.toml Install (-e .) ---\nExit Code: {exit_code}\nStdout:\n{stdout}\nStderr:\n{stderr}")
        if exit_code != 0:
            logger.error(f"Failed to install project from pyproject.toml. Stderr: {stderr}")
            success = False
        else:
            logger.info("Successfully installed project from pyproject.toml")
    elif pyproject_path.exists() and not success:
        logger.warning("Skipping pyproject.toml install due to previous dependency failure.")
        install_log.append("--- pyproject.toml Install: Skipped (Previous failure) ---")
    else:
        logger.info("No pyproject.toml found.")
        install_log.append("--- pyproject.toml Install: Skipped (File not found) ---")

    # Log dependency installation details
    dep_log_path = project_dir / "dependency_install.log"
    try:
        with open(dep_log_path, "w", encoding='utf-8') as f:
            f.write("\n\n".join(install_log))
        logger.info(f"Dependency installation log saved to {dep_log_path}")
    except Exception as log_e:
        logger.error(f"Failed to write dependency installation log: {log_e}")

    return success

async def _run_tests_in_venv(project_dir: Path, venv_python_executable: str) -> Tuple[bool, str]:
    """Runs pytest or other test runners within the virtual environment."""
    tests_dir = project_dir / "tests"
    test_log = ["--- Test Execution Log ---"]
    all_passed = False

    if not tests_dir.is_dir():
        logger.warning(f"No 'tests' directory found in {project_dir}. Skipping test execution.")
        test_log.append("Result: SKIPPED (No 'tests' directory found)")
        return True, "\n".join(test_log) # Considered success if no tests exist

    # Determine test command (e.g., pytest)
    # Could be made more sophisticated (e.g., detect framework)
    test_command = f'"{venv_python_executable}" -m pytest'
    logger.info(f"Running tests using command: {test_command}")
    test_log.append(f"Test Command: {test_command}")

    exit_code, stdout, stderr = await _run_subprocess(test_command, project_dir)
    test_log.append(f"Exit Code: {exit_code}")
    test_log.append(f"Stdout:\n{stdout}")
    test_log.append(f"Stderr:\n{stderr}")

    if exit_code == 0:
        logger.info("Tests passed successfully.")
        test_log.append("Result: PASSED")
        all_passed = True
    else:
        # Different exit codes from pytest mean different things, but any non-zero is failure here
        logger.error(f"Tests failed or encountered errors. Exit Code: {exit_code}")
        test_log.append(f"Result: FAILED (Exit Code: {exit_code})")
        all_passed = False

    return all_passed, "\n".join(test_log)

# --- Main Test Execution Function ---

async def run_project_tests(project_dir: Path, venv_python_executable: str) -> Tuple[bool, str]:
    """
    Runs the testing process for a generated project.
    Assumes venv is already created and accepts the path to its python executable.
    1. Installs dependencies.
    2. Runs tests (currently assumes pytest).
    Returns a tuple: (tests_passed: bool, full_log: str)
    """
    logger.info(f"--- Starting Project Test Run for: {project_dir.name} ---")
    full_log = [f"Project: {project_dir.name}", f"Using Python: {venv_python_executable}"]
    overall_success = False

    # 1. Install Dependencies
    logger.info("Step 1: Installing project dependencies...")
    full_log.append("\n--- Dependency Installation ---")
    deps_installed = await _install_dependencies(project_dir, venv_python_executable)
    # Log content can be found in dependency_install.log
    dep_log_path = project_dir / "dependency_install.log"
    if dep_log_path.exists():
         try: full_log.append(dep_log_path.read_text(encoding='utf-8'))
         except Exception: full_log.append("(Failed to read dependency log)")
    else:
         full_log.append("(Dependency log file not found)")

    if not deps_installed:
        logger.error("Dependency installation failed. Aborting test run.")
        full_log.append("\n--- Test Execution: SKIPPED (Dependency Installation Failed) ---")
        overall_success = False # Mark as failure
    else:
        logger.info("Dependencies installed successfully (or skipped if none found). Proceeding to test execution.")
        # 2. Run Tests
        logger.info("Step 2: Running tests...")
        full_log.append("\n--- Test Execution ---")
        tests_passed, test_run_log = await _run_tests_in_venv(project_dir, venv_python_executable)
        full_log.append(test_run_log)
        overall_success = tests_passed

    final_log = "\n".join(full_log)
    # Optionally save the full log to a file
    test_summary_log_path = project_dir / "test_summary.log"
    try:
        with open(test_summary_log_path, "w", encoding='utf-8') as f:
            f.write(final_log)
        logger.info(f"Full test summary log saved to {test_summary_log_path}")
    except Exception as log_e:
        logger.error(f"Failed to write test summary log: {log_e}")

    logger.info(f"--- Project Test Run Finished for: {project_dir.name}. Overall Success: {overall_success} ---")
    return overall_success, final_log