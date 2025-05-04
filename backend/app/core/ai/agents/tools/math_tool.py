# app/core/ai/agents/tools/math_tool.py

from langchain.tools import tool
from langchain.chains.llm_math.base import LLMMathChain
from app.core.ai.llm import _get_llm 
from app.utils import get_logger

logger = get_logger(__name__)

@tool
def solve_math_question(query: str) -> str:
    """
    Use this tool for solving symbolic math expressions or word problems
    that involve reasoning (e.g., 'What is 25% of 640?', 'What is the square root of 144?').
    This tool uses a language model to think through the solution step-by-step.

    Avoid using this tool for simple numerical expressions like '4 + 5 * 6'.
    For those, use the calculator tool.
    """
    logger.info(f"Math Tool invoked. Query: '{query[:50]}...'")

    try:
        # Get LLM instance
        llm = _get_llm()

        # Initialize the LLMMathChain
        math_chain = LLMMathChain.from_llm(llm=llm, verbose=False)

        # Run the query
        result = math_chain.run(query)
        logger.info(f"Math Tool result length: {len(result)}")

        return result

    except Exception as e:
        logger.error(f"Unexpected error in math tool for query '{query}': {e}", exc_info=True)
        return f"Error: An internal error occurred while solving the math problem."
