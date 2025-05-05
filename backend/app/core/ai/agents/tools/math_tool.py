# app/core/ai/agents/tools/math_tool.py

import asyncio # <<< Added import
from langchain.tools import tool
from langchain.chains.llm_math.base import LLMMathChain
from langchain_core.tools import ToolException # <<< Added import
from app.core.ai.llm import get_llm
from app.utils import get_logger

logger = get_logger(__name__)

@tool
async def solve_math_question(query: str) -> str: # <<< Changed to async def
    """
    Use this tool for solving **COMPLEX mathematical problems** that require reasoning, interpretation, symbolic manipulation, or multiple steps. This includes word problems, algebra, calculus snippets, percentages, square roots, etc.
    (Docstring unchanged)
    """
    logger.info(f"Math Tool invoked (async). Query: '{query[:50]}...'")

    try:
        # Get LLM instance (sync is fine here)
        llm = get_llm()

        # Initialize the LLMMathChain (sync is fine here)
        math_chain = LLMMathChain.from_llm(llm=llm, verbose=False)

        # Run the query asynchronously
        logger.debug(f"Running LLMMathChain asynchronously for query: {query}")
        # LLMMathChain inherits from LLMChain which has arun
        result = await math_chain.arun(query) # <<< Changed to arun
        logger.info(f"Math Tool result length: {len(result)}")

        if not isinstance(result, str):
             logger.warning(f"Math tool result was not a string: {type(result)}. Converting.")
             result = str(result)

        if "error" in result.lower() or "failed" in result.lower():
             logger.warning(f"Math tool may have failed internally. Result: {result}")
             # Optionally raise ToolException here if the result indicates failure
             # raise ToolException(f"The math tool failed to solve the problem: {result}")
             # For now, just return the potentially informative error string from the chain

        return result

    except ToolException: # Re-raise ToolExceptions explicitly
        raise
    except Exception as e:
        logger.error(f"Unexpected error in math tool for query '{query}': {e}", exc_info=True)
        # Raise ToolException for agent awareness
        raise ToolException(f"An internal error occurred while solving the math problem: {e}")