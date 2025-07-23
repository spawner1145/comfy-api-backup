from typing import Dict, Any, List

class ComfyWorkflow:
    def __init__(self, workflow_json_path: str):
        self.workflow_json_path = workflow_json_path
        self._replacements: Dict[str, Dict[str, Any]] = {}
        self._output_nodes: List[str] = []

    def add_replacement(self, node_id: str, input_name: str, value: Any) -> 'ComfyWorkflow':
        if node_id not in self._replacements: self._replacements[node_id] = {}
        self._replacements[node_id][input_name] = value
        return self

    def add_output_node(self, node_id: str) -> 'ComfyWorkflow':
        if node_id not in self._output_nodes: self._output_nodes.append(node_id)
        return self