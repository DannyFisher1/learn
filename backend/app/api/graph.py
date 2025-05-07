# app/api/graph.py

import logging
from fastapi import APIRouter, HTTPException, status
from langgraph.prebuilt import ToolNode # Import ToolNode to check instance type later if needed
from langgraph.graph.state import START, END # Import START and END

# App imports
# Import the function that holds the graph definition logic
from app.core.ai.agents.executor import get_langgraph_app
from app.utils import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/graph", tags=["Graph Structure"])

@router.get("/structure")
async def get_graph_structure():
    """
    Returns the structure of the primary LangGraph application.
    Dynamically introspects the compiled graph.
    """
    logger.info("Request received for graph structure.")
    try:
        compiled_app = get_langgraph_app()
        visualizable_graph = compiled_app.get_graph()

        # --- Add Detailed Logging --- 
        logger.debug(f"RAW Graph Nodes: {visualizable_graph.nodes}")
        if hasattr(visualizable_graph, 'edges'):
            logger.debug(f"RAW Graph Edges: {visualizable_graph.edges}")
        else:
            logger.debug("Graph object has no 'edges' attribute.")
        if hasattr(visualizable_graph, 'conditional_edges'):
            logger.debug(f"RAW Graph Conditional Edges: {visualizable_graph.conditional_edges}")
        else:
            logger.debug("Graph object has no 'conditional_edges' attribute.")
        # --- End Detailed Logging ---

        nodes_data = []
        # Use visualizable_graph.nodes
        for node_name, node_obj in visualizable_graph.nodes.items(): 
            node_type = "defaultNode" 
            actual_runnable = node_obj # Assume node_obj is the runnable or directly checkable

            if node_name == START:
                node_type = "userInput"
                label = "Start"
            elif node_name == END:
                node_type = "output"
                label = "End"
            elif isinstance(actual_runnable, ToolNode):
                node_type = "toolNode"
                label = node_name.replace("_", " ").title() # e.g., "Action (Tools)" or node_name.capitalize()
            elif "agent" in node_name.lower():
                node_type = "llmNode"
                label = node_name.replace("_", " ").title() # e.g., "Agent"
            else:
                label = node_name.replace("_", " ").title()

            nodes_data.append({"id": node_name, "type": node_type, "label": label})

        edges_data = []
        edge_id_counter = 0

        # Process all edges from visualizable_graph.edges
        if hasattr(visualizable_graph, 'edges'):
            for edge in visualizable_graph.edges:
                source_node = edge.source
                target_node = edge.target
                label = f"{source_node} to {target_node}" # Default label

                if edge.conditional:
                    if edge.target == END: # Check if the target is the END node
                        label = "Finish"
                    elif edge.data: # Check if there is specific condition data
                        label = f"If {edge.data}"
                    else: # Generic fallback for other conditional edges
                        label = f"Conditional to {target_node}"
                
                edges_data.append({
                    "id": f"e_{source_node}_{target_node}_{edge_id_counter}", # Make ID more descriptive
                    "source": source_node,
                    "target": target_node,
                    "label": label
                })
                edge_id_counter += 1
        else:
            logger.warning("'Graph' object has no 'edges' attribute. Edges will be missing.")

        
        # Determine entry point (usually START)
        entry_point_node = START 
        # Ensure the entry point actually exists as a node, otherwise default or error
        if entry_point_node not in visualizable_graph.nodes: # Check against visualizable_graph.nodes
            logger.warning(f"Default entry point '{START}' not found in graph nodes. Picking first available or agent.")
            # Fallback logic: try to find 'agent' or just pick the first node
            if "agent" in visualizable_graph.nodes: # Check against visualizable_graph.nodes
                 entry_point_node = "agent"
            elif visualizable_graph.nodes: # Check against visualizable_graph.nodes
                 entry_point_node = list(visualizable_graph.nodes.keys())[0]
            else: # Should not happen with a valid graph
                 entry_point_node = "unknown"


        structure = {
            "nodes": nodes_data,
            "edges": edges_data,
            "entry_point": entry_point_node
        }
        logger.info(f"Returning dynamic graph structure with {len(nodes_data)} nodes and {len(edges_data)} edges.")
        return structure

    except Exception as e:
        logger.error(f"Failed to get graph structure: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve graph structure."
        )