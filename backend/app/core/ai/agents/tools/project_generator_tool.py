# backend/app/core/ai/agents/tools/project_generator_tool.py
import logging
import asyncio
from langchain_core.tools import tool
from langchain_core.tools import ToolException # <<< Use ToolException from core

# Import the refactored workflow function (which is async)
from app.core.project_generator.workflow import execute_project_generation_workflow
from app.utils import get_logger

logger = get_logger(__name__)

@tool
async def generate_software_project(project_request: str) -> str:
    """Generates a complete software project based on a user request.

    Use this tool when a user explicitly asks to create, generate, or build a
    software project, web application, script, etc. Provide a detailed description
    of the project requirements in the 'project_request' argument.

    Args:
        project_request: A detailed natural language description of the software
                         project to be generated, including technologies, features,
                         and structure if specified.

    Returns:
        A string summarizing the outcome of the project generation process, including
        success or failure status, the location of the generated project files,
        and any relevant messages or errors.
    """
    logger.info(f"Project Generator Tool invoked. Request length: {len(project_request)}")
    final_result = "Error: Workflow did not produce a final status message."
    last_yielded = None
    try:
        async for result in execute_project_generation_workflow(project_request):
            last_yielded = result # Keep track of the last yielded item
            # Optionally log progress updates here if desired
            if result.get("type") == "status":
                 logger.info(f"Workflow Status [{result.get('step')}]: {result.get('message')}")
            elif result.get("type") == "error":
                 logger.error(f"Workflow Error [{result.get('step')}]: {result.get('message')}")
            elif result.get("type") == "warning":
                 logger.warning(f"Workflow Warning [{result.get('step')}]: {result.get('message')}")

        # After the loop, process the last yielded item, expecting it to be final_status
        if last_yielded and last_yielded.get("type") == "final_status":
            final_result = last_yielded.get("message", "Error: Final status message missing content.")
            logger.info(f"Project generation workflow finished. Final status: {last_yielded.get('status')}")
        elif last_yielded:
             logger.error(f"Workflow finished unexpectedly. Last yielded item was not final_status: {last_yielded}")
             final_result = f"Error: Workflow finished unexpectedly. Last message: {last_yielded}"
        else:
             logger.error("Workflow finished without yielding any results.")
             final_result = "Error: Workflow finished without yielding any results."

    except Exception as e:
        logger.exception(f"An error occurred while running or iterating the project generation workflow: {e}")
        final_result = f"Error during project generation workflow execution: {e}"

    logger.info(f"Project Generator Tool returning final message: '{final_result[:100]}...'")
    return final_result

# Note: The synchronous wrapper used previously (with asyncio.run)
# is no longer needed as the tool function itself is now async.
# Langchain handles invoking async tools correctly.