# backend/app/core/workflows/deep_research.py

import logging
import asyncio
import json
from typing import Dict, Any, List, Set, Optional

# Langchain/LLM specific imports
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field as PydanticField

# App imports
from app import config # For LLM model names and potentially other configs
from app.errors import JobExecutionError
from app.utils import get_logger
from app.core.ai.llm import get_llm
from app.core.ai.agents.tools.web_search_searx_tool import search_web_raw # Your raw search tool
from app.core.jobs.store import get_job_store_instance
from app.schemas import JOB_STATUS_FAILED

logger = get_logger(__name__)

# Timeout for gathering results from a batch of web searches (in seconds)
SEARCH_GATHER_TIMEOUT = 60 # Adjust as needed

# --- Pydantic Models for Structured LLM Responses ---
class RefinedQuery(BaseModel):
    query: str = PydanticField(description="A specific, refined search query targeting a sub-topic.")

class RefinedQueryList(BaseModel):
    queries: List[RefinedQuery] = PydanticField(description="List of refined search queries.")
    key_concepts: List[str] = PydanticField(description="Key concepts identified from the initial search.")

# --- Prompts ---
QUERY_REFINEMENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert research assistant. Analyze the following initial web search results for the user's topic.
Identify key sub-topics, concepts, and areas requiring deeper investigation.
Generate a list of specific, follow-up search queries. Also list key concepts.
Respond ONLY with a JSON object: {{"queries": [{{"query": "..."}}], "key_concepts": ["..."]}}"""), # JSON structure in prompt is fine with double braces for literal JSON
    ("human", "Original Topic: {original_topic}\n\nInitial Search Results:\n{initial_results_summary}") # CHANGED TO SINGLE BRACES
])

REPORT_SYNTHESIS_PROMPT = ChatPromptTemplate.from_messages([
     ("system", """You are a research report writer. Synthesize the provided web content into a comprehensive, well-structured report on the original topic.
Instructions:
1. Structure: Logical headings (##), subheadings (###), paragraphs. Intro, body (key findings), conclusion.
2. Content: Base report ONLY on provided context. No external info/opinions.
3. Citations (Inline): Attribute significant claims, e.g., "(Source: [URL/Title])" or "According to [Source Title], ...".
4. Formatting: Use Markdown (bold, lists). Ensure readability.
5. Completeness: Cover main aspects from context. Note limitations if context is insufficient.
6. Tone: Neutral, objective, informative.

Original Research Topic: {original_topic} # CHANGED TO SINGLE BRACES
Collected Web Content (Each entry is a separate source):
---CONTEXT START---
{aggregated_content} # CHANGED TO SINGLE BRACES
---CONTEXT END---
Begin the Markdown report:"""),
])


# --- Main Workflow Function ---
async def execute_deep_research_workflow(
    job_id: str,
    original_topic: str,
    depth: int = 2, # Number of deeper search rounds/batches using refined queries
    max_sources_per_query: int = 3, 
    max_total_sources: int = 15 # Max unique sources to collect in total
) -> Dict[str, Any]:
    job_store = get_job_store_instance()
    all_fetched_content: Dict[str, Dict[str, Any]] = {} # url -> {title, url, snippet, cleaned_content}
    processed_urls: Set[str] = set()
    error_messages: List[str] = []
    
    # Estimate total steps for progress reporting
    # Initial Search (1), Refinement (1), N Depth Rounds (depth), Aggregation (1), Synthesis (1)
    total_workflow_steps = 3 + depth + 1 
    current_workflow_step = 0

    async def update_progress(step_num: int, message: str, is_major_step_start: bool = True):
        nonlocal current_workflow_step
        if is_major_step_start:
            current_workflow_step = step_num
        
        progress_msg = f"[Step {current_workflow_step}/{total_workflow_steps}] {message}"
        logger.info(f"[Job {job_id}] {progress_msg}")
        await job_store.update_job(job_id, {"progress_message": progress_msg})

    try:
        await update_progress(1, f"Initializing research for: '{original_topic}'")

        # === Step 1: Initial Broad Search ===
        await update_progress(1, f"Performing initial search for '{original_topic}'...")
        initial_search_results_json_str = await search_web_raw.ainvoke({"query": original_topic, "num_results": max_sources_per_query + 2}) # Fetch a bit more for refinement
        initial_sources_raw = []
        try:
            parsed_initial = json.loads(initial_search_results_json_str)
            if isinstance(parsed_initial, list): initial_sources_raw = parsed_initial
        except json.JSONDecodeError as e:
             logger.error(f"[Job {job_id}] Failed to parse initial search JSON: {e}. Results: {initial_search_results_json_str[:200]}")
             error_messages.append("Error parsing initial search results.")

        if initial_sources_raw:
            for src in initial_sources_raw:
                url = src.get("url")
                if url and url not in processed_urls and len(all_fetched_content) < max_total_sources :
                    all_fetched_content[url] = {**src, "cleaned_content": src.get("cleaned_content", src.get("snippet", ""))}
                    processed_urls.add(url)
            await update_progress(1, f"Initial search: Found {len(initial_sources_raw)} raw, added {len(all_fetched_content)} unique sources.", is_major_step_start=False)
        else:
            await update_progress(1, "Initial search yielded no results.", is_major_step_start=False)


        # === Step 2: Result Analysis & Query Refinement ===
        await update_progress(2, "Analyzing initial results to refine queries...")
        refined_queries_list: List[str] = []
        if all_fetched_content: # Only refine if we have content
            summary_for_llm = "\n".join([
                f"Title: {data.get('title','N/A')}\nSnippet: {data.get('snippet','N/A')}\n---" 
                for data in list(all_fetched_content.values())[:5] # Use up to 5 diverse sources for refinement prompt
            ])
            refinement_llm = get_llm()
            from langchain_core.output_parsers import PydanticOutputParser as CorePydanticOutputParser # Ensure correct import
            refinement_parser = CorePydanticOutputParser(pydantic_object=RefinedQueryList)
            refinement_chain = QUERY_REFINEMENT_PROMPT | refinement_llm | refinement_parser
            try:
                refined_data: RefinedQueryList = await refinement_chain.ainvoke({"original_topic": original_topic, "initial_results_summary": summary_for_llm})
                refined_queries_list = [q.query for q in refined_data.queries if q.query.strip()]
                logger.info(f"[Job {job_id}] Refined queries: {refined_queries_list}. Key concepts: {refined_data.key_concepts}")
                await update_progress(2, f"Generated {len(refined_queries_list)} refined queries.", is_major_step_start=False)
            except Exception as e:
                logger.error(f"[Job {job_id}] Query refinement failed: {e}", exc_info=True)
                error_messages.append(f"Query refinement error: {str(e)[:100]}.")
        
        if not refined_queries_list: # Fallback if no sources or refinement failed
            refined_queries_list.append(original_topic) # At least search the original topic more
            await update_progress(2, "Using original topic for deeper search as no refined queries were generated.", is_major_step_start=False)

        # === Step 3: Iterative Deeper Search (for `depth` rounds) ===
        # `queries_to_process_in_deeper_search` will be the unique refined queries.
        # We will iterate `depth` times, each time taking a batch of these queries if available.
        
        queries_for_deeper_rounds = list(set(refined_queries_list)) # Unique queries
        
        for i in range(depth):
            current_depth_round_step_num = 2 + 1 + i # Base step after initial search & refinement
            
            if not queries_for_deeper_rounds or len(all_fetched_content) >= max_total_sources:
                await update_progress(current_depth_round_step_num, f"Deeper search round {i+1}/{depth} skipped (no more queries or max sources).")
                continue

            # Take a batch of queries for this round.
            # For simplicity, let's say each depth round processes `max_sources_per_query` new distinct queries
            # from our refined list until the list is exhausted or max_total_sources is hit.
            batch_to_search_now = []
            temp_remaining_queries = []
            for q_str in queries_for_deeper_rounds:
                if len(batch_to_search_now) < max_sources_per_query:
                    batch_to_search_now.append(q_str)
                else:
                    temp_remaining_queries.append(q_str)
            queries_for_deeper_rounds = temp_remaining_queries # Update list for next potential round

            if not batch_to_search_now: # Should be caught by outer check, but for safety
                await update_progress(current_depth_round_step_num, f"Deeper search round {i+1}/{depth} - No queries in current batch.")
                continue

            query_preview = ", ".join([f"'{q[:25]}...'" for q in batch_to_search_now])
            await update_progress(current_depth_round_step_num, f"Deeper search (Round {i+1}/{depth}). Searching {len(batch_to_search_now)} queries: {query_preview}")

            search_tasks = [search_web_raw.ainvoke({"query": q_str, "num_results": 2}) for q_str in batch_to_search_now] # Fetch 2 results per sub-query
            
            new_sources_this_round = 0
            try:
                logger.info(f"[Job {job_id}] Gathering {len(search_tasks)} search results for round {i+1} with timeout {SEARCH_GATHER_TIMEOUT}s.")
                results_from_gather = await asyncio.wait_for(
                    asyncio.gather(*search_tasks, return_exceptions=True),
                    timeout=SEARCH_GATHER_TIMEOUT
                )
                logger.info(f"[Job {job_id}] Gathered results for round {i+1}.")

                for res_idx, res_json_or_exc in enumerate(results_from_gather):
                    query_used = batch_to_search_now[res_idx]
                    if isinstance(res_json_or_exc, Exception):
                        logger.error(f"[Job {job_id}] Deeper search API call failed for query '{query_used}': {res_json_or_exc}")
                        error_messages.append(f"Search API fail for: {query_used[:50]}...")
                        continue
                    
                    try:
                        current_query_sources = json.loads(res_json_or_exc)
                        if isinstance(current_query_sources, list):
                            for src in current_query_sources:
                                url = src.get("url")
                                if url and url not in processed_urls and len(all_fetched_content) < max_total_sources:
                                    all_fetched_content[url] = {**src, "cleaned_content": src.get("cleaned_content", src.get("snippet", ""))}
                                    processed_urls.add(url)
                                    new_sources_this_round += 1
                    except json.JSONDecodeError as e:
                        logger.error(f"[Job {job_id}] JSON Parse error in deeper search for query '{query_used}': {e}. Data: {str(res_json_or_exc)[:200]}")
                        error_messages.append(f"Parse error for results of: {query_used[:50]}...")
            except asyncio.TimeoutError:
                logger.error(f"[Job {job_id}] Timeout gathering search results for round {i+1}.")
                error_messages.append(f"Timeout during deeper search round {i+1}.")
            except Exception as e_gather: # Catch other errors from gather if any
                logger.error(f"[Job {job_id}] Error during asyncio.gather for search tasks: {e_gather}", exc_info=True)
                error_messages.append(f"Error processing search batch for round {i+1}.")
            
            await update_progress(current_depth_round_step_num, f"Deeper search (Round {i+1}/{depth}) complete. Added {new_sources_this_round}. Total unique sources: {len(all_fetched_content)}.", is_major_step_start=False)

        # === Step 4: Content Aggregation ===
        # Adjust current_workflow_step after all depth rounds
        current_workflow_step = 2 + depth + 1
        await update_progress(current_workflow_step, f"Aggregating content from {len(all_fetched_content)} sources...")
        if not all_fetched_content:
            raise JobExecutionError("No content retrieved from any web source. Cannot generate report.")

        content_parts_for_llm = []
        total_chars = 0
        synthesis_context_char_limit = getattr(config, 'DEEP_RESEARCH_SYNTHESIS_MAX_CHARS', 45000)

        for url_key, src_data in all_fetched_content.items():
            if total_chars >= synthesis_context_char_limit:
                logger.warning(f"[Job {job_id}] Reached char limit for synthesis context ({synthesis_context_char_limit}). Some sources truncated/excluded.")
                error_messages.append(f"Context limit reached; report may not include all {len(all_fetched_content)} sources.")
                break
            
            title = src_data.get('title', 'Untitled')
            url = src_data.get('url', url_key) # Use url_key as fallback
            content = src_data.get('cleaned_content', '') # Prefer cleaned_content
            if not content.strip() and src_data.get('snippet'): # Fallback to snippet if cleaned_content is empty
                content = src_data.get('snippet', '')

            if not content or not content.strip(): continue

            available_chars = synthesis_context_char_limit - total_chars - (len(title) + len(url) + 50) # Approx overhead
            content_to_add = content[:available_chars] if len(content) > available_chars else content
            
            content_parts_for_llm.append(f"Source Title: {title}\nSource URL: {url}\nContent:\n{content_to_add}\n---\n")
            total_chars += len(content_parts_for_llm[-1])

        if not content_parts_for_llm:
             raise JobExecutionError("No usable content aggregated from sources. Cannot generate report.")
        aggregated_content_for_llm = "\n".join(content_parts_for_llm)
        await update_progress(current_workflow_step, f"Aggregated {len(content_parts_for_llm)} content blocks ({total_chars} chars).", is_major_step_start=False)

        # === Step 5: Synthesis / Report Generation ===
        current_workflow_step += 1
        await update_progress(current_workflow_step, f"Synthesizing report for '{original_topic}'...")
        synthesis_llm = get_llm()
        synthesis_parser = StrOutputParser()
        synthesis_chain = REPORT_SYNTHESIS_PROMPT | synthesis_llm | synthesis_parser
        
        markdown_report = ""
        try:
            markdown_report = await synthesis_chain.ainvoke({"original_topic": original_topic, "aggregated_content": aggregated_content_for_llm})
            if not markdown_report or not markdown_report.strip():
                raise JobExecutionError("Report synthesis produced empty output.")
            logger.info(f"[Job {job_id}] Report synthesis complete. Length: {len(markdown_report)} chars.")
        except Exception as synth_err:
             logger.error(f"[Job {job_id}] Report synthesis failed: {synth_err}", exc_info=True)
             error_messages.append(f"Failed to synthesize report: {str(synth_err)[:100]}.")
             if aggregated_content_for_llm: # Fallback if synthesis fails
                 markdown_report = f"# Report Synthesis Failed\n\n**Error:** {str(synth_err)[:150]}...\n\n## Aggregated Raw Content (Partial)\n\n{aggregated_content_for_llm[:max(5000, int(synthesis_context_char_limit * 0.2))]}..."
                 logger.warning(f"[Job {job_id}] Falling back to raw content due to synthesis error.")
             else:
                raise JobExecutionError(f"Synthesis failed and no raw content to return: {synth_err}") from synth_err
        
        await update_progress(current_workflow_step, "Report synthesis complete.", is_major_step_start=False)

        # === Final Result Packaging ===
        final_sources_for_report = [{
            "title": data.get("title", "Untitled"), "url": data.get("url", "N/A"),
            "snippet": data.get("snippet", data.get("cleaned_content","N/A")[:200])
        } for data in all_fetched_content.values()]

        final_result_data = {
            "report_markdown": markdown_report,
            "sources": final_sources_for_report,
            "errors": error_messages
        }
        logger.info(f"[Job {job_id}] Workflow completed for '{original_topic}'.")
        return final_result_data

    except JobExecutionError as jee:
        logger.error(f"[Job {job_id}] Workflow execution error: {jee}", exc_info=False)
        await job_store.update_job(job_id, {"status": JOB_STATUS_FAILED, "error_message": str(jee), "progress_message": f"Error: {str(jee)[:100]}..."})
        raise
    except Exception as e:
        logger.error(f"[Job {job_id}] Unexpected workflow error: {e}", exc_info=True)
        err_msg = f"Unexpected error: {str(e)[:100]}..."
        await job_store.update_job(job_id, {"status": JOB_STATUS_FAILED, "error_message": err_msg, "progress_message": "Unexpected error."})
        raise JobExecutionError(err_msg) from e