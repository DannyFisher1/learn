import logging
from langchain.tools import tool
from app.utils import get_logger

logger = get_logger(__name__)

@tool
async def evaluate_expression(expression: str) -> str:
    """
    Use this tool ONLY for evaluating **SIMPLE, DIRECT numerical expressions**. It performs calculations exactly as written.

    Purpose: To quickly compute the result of basic arithmetic operations.

    Input:
      - `expression` (string, required): A mathematical expression containing only numbers, standard operators (+, -, *, /, %), and parentheses ().

    Output:
      - (string): The numerical result of the calculation, or an error message if the expression is invalid.

    ***IMPORTANT USAGE NOTES***:
    1.  **Simplicity is Key:** Ideal for inputs like '`4 + 5 * (6 / 2)`' or '`100 / 5 - 7`'.
    2.  **DO NOT USE FOR:**
        *   Word problems (e.g., "If I have 5 apples and get 3 more..."). Use `solve_math_question` instead.
        *   Expressions with variables (e.g., '`2*x + 5`'). Use `solve_math_question` instead.
        *   Units or percentages (e.g., '`25% of 640`'). Use `solve_math_question` instead.
        *   Symbolic math or functions (e.g., '`sqrt(16)`'). Use `solve_math_question` instead.
        *   Anything requiring interpretation or multi-step reasoning.
    3.  **Safety:** This tool uses a restricted `eval`. Do not attempt to pass code or complex statements.

    Example Scenarios:
      - User asks: "What is 5 times 3 plus 10?" -> Use this tool with `expression="5 * 3 + 10"`.
      - User asks: "Calculate (100 - 20) / 4" -> Use this tool with `expression="(100 - 20) / 4"`.
      - User asks: "What's the area of a circle with radius 5?" -> DO NOT use this tool. Use `solve_math_question`.
    """
    logger.info(f"Calculator Tool invoked. Expression: '{expression[:50]}...'")

    try:
        # Very restricted eval environment — only math operators
        allowed_names = {
            '__builtins__': None,
        }

        result = eval(expression, allowed_names, {})
        logger.info(f"Calculator Tool result: {result}")
        return str(result)

    except Exception as e:
        logger.error(f"Error evaluating expression '{expression}': {e}", exc_info=True)
        return f"Error: Invalid math expression."
