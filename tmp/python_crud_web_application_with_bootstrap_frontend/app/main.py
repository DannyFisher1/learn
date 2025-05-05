# app/main.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .models import EntityModel
from .crud import get_entities, create_entity, update_entity, delete_entity

app = FastAPI()

def startup_event() -> None:
    """
    Initialize the FastAPI application by mounting static files and templates.
    """
    # Mount static files directory
    app.mount("/static", StaticFiles(directory="static"), name="static")
    # Set up templates directory
    app.templates = Jinja2Templates(directory="templates")

# Register startup event
app.add_event_handler("startup", startup_event)

@app.get("/", response_class=HTMLResponse, tags=["Templates"])
async def read_index(request: Request):
    """
    Serve the main index page.
    
    Args:
        request: The incoming HTTP request.
        
    Returns:
        Rendered HTML response for the index page.
    """
    return app.templates.TemplateResponse("index.html", {"request": request})

@app.get("/entities/", response_model=list[EntityModel], tags=["Entities"])
async def list_entities():
    """
    Retrieve a list of all entities.
    
    Returns:
        List of EntityModel instances.
    """
    entities = await get_entities()
    return entities

@app.post("/entities/", response_model=EntityModel, tags=["Entities"])
async def create_new_entity(entity: EntityModel):
    """
    Create a new entity.
    
    Args:
        entity: The EntityModel data to create.
        
    Returns:
        The created EntityModel instance.
    """
    created_entity = await create_entity(entity)
    return created_entity

@app.put("/entities/{entity_id}", response_model=EntityModel, tags=["Entities"])
async def update_existing_entity(entity_id: int, entity: EntityModel):
    """
    Update an existing entity by ID.
    
    Args:
        entity_id: The ID of the entity to update.
        entity: The EntityModel data with updates.
        
    Returns:
        The updated EntityModel instance.
        
    Raises:
        HTTPException 404: If the entity with given ID does not exist.
    """
    existing_entity = await get_entities(entity_id)
    if not existing_entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    updated_entity = await update_entity(entity_id, entity)
    return updated_entity

@app.delete("/entities/{entity_id}", response_class=HTMLResponse, tags=["Entities"])
async def delete_entity_by_id(entity_id: int):
    """
    Delete an entity by ID.
    
    Args:
        entity_id: The ID of the entity to delete.
        
    Returns:
        Confirmation message or redirect.
        
    Raises:
        HTTPException 404: If the entity with given ID does not exist.
    """
    existing_entity = await get_entities(entity_id)
    if not existing_entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    await delete_entity(entity_id)
    # Optionally, redirect or return a confirmation page
    return app.templates.TemplateResponse("index.html", {"request": Request, "message": "Entity deleted"})