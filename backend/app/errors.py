# backend/app/errors.py

class AgentNotReadyError(Exception):
    """Custom exception for when the LangGraph agent is not ready."""
    pass

class ConfigurationError(Exception):
    """Custom exception for configuration-related issues."""
    pass

class JobNotFoundError(Exception):
    """Custom exception when a specific Job ID is not found."""
    pass

class JobExecutionError(Exception):
    """Custom exception for errors during background job execution."""
    pass