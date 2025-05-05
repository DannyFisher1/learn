# Import tools defined in this directory
from .rag_tool import query_uploaded_documents, summarize_document_content
from .math_tool import solve_math_question
from .calculator_tool import evaluate_expression
from .lookup_package_tool import inspect_package, get_package_info
from .web_search_searx_tool import search_the_web
from .reddit_search_tool import search_reddit
from .project_generator_tool import generate_software_project
# Add other tools here as you create them
# from .calculator_tool import calculator

# This list is imported by app.core.ai.agents.executor
tools = [
    query_uploaded_documents,
    summarize_document_content,
    solve_math_question,
    evaluate_expression,
    inspect_package,
    get_package_info,
    search_the_web,
    search_reddit,
    generate_software_project,
    # calculator, # Example of adding another tool
]