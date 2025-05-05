# components/test_creator.py
from langchain_core.language_models.chat_models import BaseChatModel
from app.core.project_generator.utils.prompt_loader import load_prompt
from app.core.project_generator.utils.output_parser import extract_code_block
from typing import List, Dict, Optional, Union
from pathlib import Path

from app.core.project_generator.testing import _create_and_activate_venv

def generate_tests(
    source_code: str,
    source_file_path: str,
    test_file_path: str,
    test_framework: str,
    llm: BaseChatModel,
    original_task: Optional[Dict] = None,
    technical_spec: Optional[Dict] = None,
    requirements: List[str] = None,
    adjacent_files_list: List[str] = None
) -> Optional[str]:
    """Enhanced test generator that handles both backend and frontend test cases."""
    prompt_template = load_prompt("test_generator")
    
    # Determine language and test configuration
    test_config = get_test_config(source_file_path, test_file_path, test_framework)
    if not test_config:
        return None

    # Prepare test requirements
    test_reqs = get_test_requirements(test_config['type'], requirements or [])
    
    # Build context for the prompt
    context = {
        'source_code': source_code,
        'source_path': source_file_path,
        'test_path': test_file_path,
        'framework': test_config['framework'],
        'language': test_config['language'],
        'test_type': test_config['type'],
        'requirements': test_reqs,
        'adjacent_files': adjacent_files_list or [],
        'original_task': original_task or {},
        'technical_spec': technical_spec or {}
    }

    # Generate the prompt
    prompt = build_test_prompt(prompt_template, context)
    
    # Get LLM response and process it
    response = llm.invoke(prompt)
    test_code = process_llm_response(
        response.content,
        test_config['language_hint'],
        source_file_path,
        test_file_path
    )
    
    return test_code

def get_test_config(
    source_path: str, 
    test_path: str,
    framework: str
) -> Optional[Dict[str, Union[str, List[str]]]]:
    """Determine test configuration based on file paths."""
    if source_path.startswith("backend/"):
        return {
            'type': 'unit' if 'test_' in test_path else 'integration',
            'framework': framework or 'pytest',
            'language': 'Python',
            'language_hint': 'python',
            'default_imports': [
                'import pytest',
                'from unittest.mock import Mock, patch'
            ]
        }
    elif source_path.startswith("frontend/"):
        return {
            'type': 'component' if '.test.tsx' in test_path else 'unit',
            'framework': framework or 'jest',
            'language': 'TypeScript',
            'language_hint': 'typescript' if test_path.endswith(('.ts', '.tsx')) else 'javascript',
            'default_imports': [
                "import { render, screen } from '@testing-library/react'",
                "import userEvent from '@testing-library/user-event'"
            ]
        }
    return None

def get_test_requirements(
    test_type: str,
    project_reqs: List[str]
) -> List[str]:
    """Get framework-specific test requirements."""
    base_reqs = {
        'pytest': ['pytest', 'pytest-mock', 'pytest-cov'],
        'jest': ['jest', '@testing-library/react', '@testing-library/jest-dom'],
    }.get(test_type.split('_')[0], [])
    
    return list(set(base_reqs + project_reqs))



# Example generators (would be more detailed in actual implementation)
def generate_python_unit_test_example() -> str:
    return """```python
# Example Python unit test
def test_function_behavior():
    \"\"\"Test the core functionality\"\"\"
    result = some_function(input_value)
    assert result == expected_value
```"""

def generate_react_component_test_example() -> str:
    return """```typescript
// Example React component test
test('renders correctly', () => {
  render(<MyComponent prop1="test" />);
  expect(screen.getByText('Expected text')).toBeInTheDocument();
});
```"""



def generate_python_integration_test_example() -> str:
    return """```python
# Example Python integration test
def test_integration():
    # Test the integration of multiple components
    """



def build_test_prompt(
    template: str,
    context: Dict
) -> str:
    """Construct the test generation prompt."""
    # Prepare examples based on test type
    examples = {
        'unit': generate_python_unit_test_example(),
        'integration': generate_python_integration_test_example(),
        'component': generate_react_component_test_example()
    }.get(context['test_type'], "")
    
    return template.format(
        SOURCE_CODE=context['source_code'],
        SOURCE_PATH=context['source_path'],
        TEST_PATH=context['test_path'],
        TEST_TYPE=context['test_type'],
        FRAMEWORK=context['framework'],
        LANGUAGE=context['language'],
        REQUIREMENTS=", ".join(context['requirements']),
        ADJACENT_FILES="\n".join(context['adjacent_files']),
        TASK_DESCRIPTION=context['original_task'].get('description', ''),
        TECHNICAL_SPEC=context['technical_spec'],
        TEST_EXAMPLES=examples,
        DEFAULT_IMPORTS="\n".join(context.get('default_imports', []))
    )

def process_llm_response(
    llm_output: str,
    language_hint: str,
    source_path: str,
    test_path: str
) -> Optional[str]:
    """Process and validate the LLM's test code output."""
    test_code = extract_code_block(llm_output, language=language_hint)
    
    if not test_code:
        print(f"Failed to extract test code for {test_path}")
        return generate_fallback_test(source_path, language_hint)
    
    # Add header and format
    header = f"# Tests for {source_path}\n# Generated by test_creator\n\n"
    return header + test_code.strip()

def generate_fallback_test(
    source_path: str,
    language_hint: str
) -> str:
    """Generate a placeholder test when generation fails."""
    if language_hint == 'python':
        return f"""# Test generation failed for {source_path}
# TODO: Implement proper tests

def test_placeholder():
    \"\"\"Placeholder test\"\"\"
    assert True
"""
    else:
        return f"""// Test generation failed for {source_path}
// TODO: Implement tests

test('placeholder', () => {{
  expect(true).toBeTruthy();
}});
"""
