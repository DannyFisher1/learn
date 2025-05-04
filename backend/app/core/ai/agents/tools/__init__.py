# Import tools defined in this directory
from .rag_tool import query_uploaded_documents
from .math_tool import solve_math_question
from .calculator_tool import evaluate_expression
from .lookup_package_tool import inspect_package, get_package_info
# Add other tools here as you create them
# from .calculator_tool import calculator

# This list is imported by app.core.ai.agents.executor
tools = [
    query_uploaded_documents,
    solve_math_question,
    evaluate_expression,
    inspect_package,
    get_package_info,
    # calculator, # Example of adding another tool
]