# Generated implementation: app/crud.py

from typing import List, Dict, Any

# In-memory storage for entities
_entities: List[Dict[str, Any]] = []
_next_id: int = 1

def get_entities() -> List[Dict[str, Any]]:
    """Retrieve all entities from the in-memory store.
    
    Returns:
        List of all entity dictionaries.
    """
    return _entities.copy()

def create_entity(entity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new entity with provided data.
    
    Args:
        entity_data: Dictionary containing entity fields.
        
    Returns:
        The newly created entity with assigned ID.
    """
    global _next_id
    new_entity = {'id': _next_id}
    new_entity.update(entity_data)
    _entities.append(new_entity)
    _next_id += 1
    return new_entity

def update_entity(entity_id: int, entity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing entity identified by entity_id.
    
    Args:
        entity_id: The ID of the entity to update.
        entity_data: Dictionary with updated fields.
        
    Returns:
        The updated entity.
        
    Raises:
        ValueError: If entity with given ID is not found.
    """
    for index, entity in enumerate(_entities):
        if entity['id'] == entity_id:
            updated_entity = {'id': entity_id}
            updated_entity.update(entity_data)
            _entities[index] = updated_entity
            return updated_entity
    raise ValueError(f"Entity with id {entity_id} not found.")

def delete_entity(entity_id: int) -> None:
    """Delete an entity by its ID.
    
    Args:
        entity_id: The ID of the entity to delete.
        
    Raises:
        ValueError: If entity with given ID is not found.
    """
    for index, entity in enumerate(_entities):
        if entity['id'] == entity_id:
            del _entities[index]
            return
    raise ValueError(f"Entity with id {entity_id} not found.")