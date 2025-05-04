import logging
from langchain.tools import tool
from app.utils import get_logger

logger = get_logger(__name__)

@tool
def evaluate_expression(expression: str) -> str:
    """
    Use this tool to quickly evaluate direct numeric expressions like '4 + 5 * 6' or '100 / (4 + 1)'.
    This tool does not support symbolic math or word problems. Use 'solve_math_question' for those.
    
    WARNING: This uses eval in a restricted scope. Do NOT pass user-defined variables or code.
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
