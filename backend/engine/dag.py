"""
DAG (Directed Acyclic Graph) Resolver.
Validates workflow connections, detects cycles, and determines topological execution order.
"""
from typing import Dict, List, Set, Any
from collections import defaultdict, deque


class WorkflowValidationError(Exception):
    pass


class DAG:
    def __init__(self, nodes: List[Dict[str, Any]], connections: List[Dict[str, Any]]):
        self.nodes = {n["id"]: n for n in nodes}
        self.connections = connections
        
        # Adjacency maps:
        self.successors: Dict[str, Set[str]] = defaultdict(set)
        self.predecessors: Dict[str, Set[str]] = defaultdict(set)
        self.edges_by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.edges_by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        self._build_graph()

    def _build_graph(self):
        for conn in self.connections:
            source = conn.get("source") or conn.get("from_node")
            target = conn.get("target") or conn.get("to_node")
            
            if not source or not target:
                continue
            if source not in self.nodes:
                raise WorkflowValidationError(f"Connection source node '{source}' does not exist.")
            if target not in self.nodes:
                raise WorkflowValidationError(f"Connection target node '{target}' does not exist.")

            self.successors[source].add(target)
            self.predecessors[target].add(source)
            self.edges_by_target[target].append(conn)
            self.edges_by_source[source].append(conn)

    def detect_cycles(self) -> bool:
        visited = {nid: 0 for nid in self.nodes}

        def dfs(node_id: str) -> bool:
            visited[node_id] = 1
            for nxt in self.successors.get(node_id, set()):
                if visited[nxt] == 1:
                    return True
                if visited[nxt] == 0:
                    if dfs(nxt):
                        return True
            visited[node_id] = 2
            return False

        for nid in self.nodes:
            if visited[nid] == 0:
                if dfs(nid):
                    return True
        return False

    def topological_sort(self) -> List[str]:
        if self.detect_cycles():
            raise WorkflowValidationError("Workflow contains a circular dependency (cycle).")

        in_degree = {nid: len(self.predecessors.get(nid, set())) for nid in self.nodes}
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        ordered: List[str] = []

        while queue:
            curr = queue.popleft()
            ordered.append(curr)

            for nxt in self.successors.get(curr, set()):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if len(ordered) != len(self.nodes):
            raise WorkflowValidationError("Could not resolve execution order. Possible cycle or invalid graph.")

        return ordered

    def get_input_edges(self, node_id: str) -> List[Dict[str, Any]]:
        return self.edges_by_target.get(node_id, [])

    def get_output_edges(self, node_id: str) -> List[Dict[str, Any]]:
        return self.edges_by_source.get(node_id, [])

    def get_ancestors(self, node_id: str) -> Set[str]:
        """Returns the set of all upstream ancestor node IDs that feed into node_id."""
        ancestors: Set[str] = set()
        stack = [node_id]
        while stack:
            curr = stack.pop()
            for p in self.predecessors.get(curr, set()):
                if p not in ancestors:
                    ancestors.add(p)
                    stack.append(p)
        return ancestors

    def get_subgraph_order(self, target_node_id: str) -> List[str]:
        """Returns topological execution order for target_node_id and its upstream ancestors only."""
        if target_node_id not in self.nodes:
            raise WorkflowValidationError(f"Target node '{target_node_id}' does not exist in workflow.")
        ancestors = self.get_ancestors(target_node_id)
        subgraph_nodes = ancestors | {target_node_id}
        full_order = self.topological_sort()
        return [nid for nid in full_order if nid in subgraph_nodes]

