# components/code_generator.py
from langchain_core.language_models.chat_models import BaseChatModel
from app.core.project_generator.utils.prompt_loader import load_prompt
from app.core.project_generator.utils.output_parser import extract_code_block
from typing import List, Dict, Optional, Any

def generate_code(
    file_path: str,
    task_description: str,
    llm: BaseChatModel,
    overall_project_context: str = "",
    adjacent_files_list: List[str] = None,
    required_libraries: List[str] = None,
    technical_spec: Dict[str, Any] = None,
    requirements: List[str] = None,
    file_purpose: str = ""
) -> Optional[str]:
    """Generates code for a single file using the LLM with enhanced context from task checklist.
    
    Args:
        file_path: Path to the file being generated
        task_description: Description of what the file should accomplish
        llm: The language model instance to use
        overall_project_context: High-level project description
        adjacent_files_list: List of other files in the project
        required_libraries: List of required libraries/dependencies
        technical_spec: Detailed technical specifications from task checklist
        requirements: List of requirement IDs (FR-xxx) this file addresses
        file_purpose: Additional purpose/context for the file
        
    Returns:
        Generated code as string, or None if generation failed
    """
    prompt_template = load_prompt("code_generator")
    
    # Enhanced language/framework detection with more specific handling
    file_ext_map = {
        '.py': 'Python',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.jsx': 'JavaScript (React)',
        '.tsx': 'TypeScript (React)',
        '.md': 'Markdown',
        '.json': 'JSON',
        '.yaml': 'YAML',
        '.yml': 'YAML',
        '.txt': 'Text',
        '.sh': 'Bash',
        '.dockerfile': 'Docker',
        'dockerfile': 'Docker',
    }
    
    # Determine primary language and framework
    primary_language = "Unknown"
    framework = ""
    for ext, lang in file_ext_map.items():
        if file_path.lower().endswith(ext):
            primary_language = lang
            break
    
    # Special handling for certain file types
    if file_path.lower() == 'requirements.txt':
        primary_language = 'Python Requirements'
    elif file_path.lower() == '.gitignore':
        primary_language = 'Gitignore'
    elif file_path.lower().endswith('dockerfile'):
        primary_language = 'Docker'
    
    # Prepare technical specifications text if available
    tech_spec_text = ""
    if technical_spec:
        tech_spec_text = "Technical Specifications:\n"
        if technical_spec.get('imports'):
            tech_spec_text += f"- Required imports: {', '.join(technical_spec['imports'])}\n"
        if technical_spec.get('exports'):
            tech_spec_text += f"- Exports: {', '.join(technical_spec['exports'])}\n"
        if technical_spec.get('functions'):
            tech_spec_text += "- Functions:\n"
            for func in technical_spec['functions']:
                tech_spec_text += f"  * {func['name']}({func.get('params', '')}) -> {func.get('returns', 'void')}: {func.get('purpose', '')}\n"
        if technical_spec.get('error_handling'):
            tech_spec_text += f"- Error Handling: {technical_spec['error_handling']}\n"
        if technical_spec.get('notes'):
            tech_spec_text += f"- Implementation Notes: {technical_spec['notes']}\n"
    
    # Prepare requirements text if available
    requirements_text = ""
    if requirements:
        requirements_text = f"Requirements to fulfill: {', '.join(requirements)}\n"
    
    # Replace placeholders with enhanced context
    formatted_prompt = prompt_template.format(
        FILE_PATH=file_path,
        TASK_DESCRIPTION=task_description,
        FILE_PURPOSE=file_purpose,
        OVERALL_PROJECT_CONTEXT=overall_project_context,
        ADJACENT_FILES_LIST=", ".join(adjacent_files_list) if adjacent_files_list else "None",
        PRIMARY_LANGUAGE=primary_language,
        FRAMEWORK=framework,
        REQUIRED_LIBRARIES=", ".join(required_libraries) if required_libraries else "None",
        TECHNICAL_SPEC=tech_spec_text,
        REQUIREMENTS=requirements_text,
    )

    # Invoke the LLM
    try:
        response = llm.invoke(formatted_prompt)
        llm_output = response.content
        
        # Determine language hint for code block extraction
        lang_hint = None
        if primary_language.startswith('Python'):
            lang_hint = 'python'
        elif primary_language.startswith('TypeScript'):
            lang_hint = 'typescript'
        elif primary_language.startswith('JavaScript'):
            lang_hint = 'javascript'
        elif primary_language in ['Markdown', 'JSON', 'YAML', 'Gitignore', 'Docker']:
            lang_hint = primary_language.lower()
        
        # Extract the code block
        generated_code = extract_code_block(llm_output, language=lang_hint)
        
        # Fallback for simple file types or when no code block is found
        if generated_code is None:
            if lang_hint in ['markdown', 'json', 'yaml', 'gitignore', 'docker']:
                generated_code = llm_output.strip()
                print(f"Info: Using raw output for {primary_language} file: {file_path}")
            else:
                print(f"Warning: No code block found in LLM response for {file_path}")
                # Create a basic template based on technical specs
                if technical_spec:
                    generated_code = generate_template_from_spec(file_path, technical_spec, primary_language)
        
        return generated_code
    
    except Exception as e:
        print(f"Error during code generation for {file_path}: {str(e)}")
        if technical_spec:
            return generate_template_from_spec(file_path, technical_spec, primary_language)
        return None

def generate_template_from_spec(file_path: str, technical_spec: Dict[str, Any], language: str) -> str:
    """Generates a basic code template when LLM generation fails."""
    template = f"# Auto-generated template for {file_path}\n"
    template += f"# Language: {language}\n\n"
    
    if technical_spec.get('imports'):
        template += "\n".join(technical_spec['imports']) + "\n\n"
    
    if technical_spec.get('functions'):
        for func in technical_spec['functions']:
            template += f"def {func['name']}({func.get('params', '')}) -> {func.get('returns', 'None')}:\n"
            template += f"    \"\"\"{func.get('purpose', '')}\"\"\"\n"
            template += "    # TODO: Implement this function\n"
            template += "    pass\n\n"
    
    if technical_spec.get('error_handling'):
        template += f"# Error Handling: {technical_spec['error_handling']}\n"
    
    if technical_spec.get('notes'):
        template += f"# Notes: {technical_spec['notes']}\n"
    
    return template