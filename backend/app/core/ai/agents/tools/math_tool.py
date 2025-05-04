# app/core/ai/agents/tools/math_tool.py

from langchain.tools import tool
from langchain.chains.llm_math.base import LLMMathChain
from app.core.ai.llm import _get_llm 
from app.utils import get_logger

logger = get_logger(__name__)

@tool
def solve_math_question(query: str) -> str:
    """
    Use this tool for solving **COMPLEX mathematical problems** that require reasoning, interpretation, symbolic manipulation, or multiple steps. This includes word problems, algebra, calculus snippets, percentages, square roots, etc.

    Purpose: To leverage a Language Model's mathematical reasoning capabilities to solve problems that are NOT simple, direct calculations.

    Input:
      - `query` (string, required): The full mathematical question or problem statement as posed by the user (e.g., "What is 30% of 500?", "Solve for x in the equation 3x - 7 = 14", "What is the square root of 144?").

    Output:
      - (string): The solution to the math problem, often including the intermediate reasoning steps performed by the LLMMathChain, culminating in a final answer.

    ***IMPORTANT USAGE NOTES***:
    1.  **Use for Complexity:** This is for problems needing interpretation or steps beyond basic arithmetic.
    2.  **Input is the Question:** Pass the user's *entire* relevant math question as the `query`.
    3.  **Contrast with Calculator:** DO NOT use this for simple expressions like '`5 * 3 + 10`'. Use `evaluate_expression` for those to save time and resources. This tool invokes an LLM chain, which is slower and more resource-intensive.
    4.  **Expect Reasoning:** The output will likely contain the thought process, not just the final number. Present this clearly to the user.

    Example Scenarios:
      - User asks: "If a train travels at 60 mph for 2.5 hours, how far does it go?" -> Use this tool with `query="If a train travels at 60 mph for 2.5 hours, how far does it go?"`.
      - User asks: "Calculate the derivative of x^3 + 2x - 1" -> Use this tool with `query="Calculate the derivative of x^3 + 2x - 1"`.
      - User asks: "What is 5 * 8?" -> DO NOT use this tool. Use `evaluate_expression`.
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
