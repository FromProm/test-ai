import hashlib
import json
from typing import Any, Dict, List

def create_hash(data: Any) -> str:
    """Create a consistent hash for any data structure"""
    if isinstance(data, dict):
        # Sort keys for consistent hashing
        sorted_data = json.dumps(data, sort_keys=True, ensure_ascii=False)
    elif isinstance(data, list):
        sorted_data = json.dumps(data, ensure_ascii=False)
    else:
        sorted_data = str(data)
    
    return hashlib.sha256(sorted_data.encode('utf-8')).hexdigest()

def create_prompt_hash(prompt: str, example_inputs: List[Dict], params: Dict[str, Any]) -> str:
    """Create hash for prompt + inputs + parameters combination"""
    combined_data = {
        "prompt": prompt,
        "example_inputs": example_inputs,
        "params": params
    }
    return create_hash(combined_data)

def create_execution_hash(prompt: str, input_content: str, model: str, params: Dict[str, Any]) -> str:
    """Create hash for specific execution (prompt + input + model + params)"""
    execution_data = {
        "prompt": prompt,
        "input": input_content,
        "model": model,
        "params": params
    }
    return create_hash(execution_data)