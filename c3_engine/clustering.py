from typing import List
from .schemas import Anomaly

def build_anomaly_clusters(anomalies: List[Anomaly]) -> List[List[str]]:
    """
    Constructs an undirected graph where nodes are anomaly_ids and edges
    represent mutual correlation pointers (i.e. u lists v in correlated_anomalies
    AND v lists u in correlated_anomalies).
    
    Returns the connected components of this graph as a list of list of anomaly_ids,
    with elements and clusters sorted for determinism.
    """
    anomaly_map = {a.anomaly_id: a for a in anomalies}
    
    # Initialize adjacency list for all anomaly_ids
    adj = {a.anomaly_id: set() for a in anomalies}
    
    # Build undirected edges for mutual correlation pointers
    for a in anomalies:
        u = a.anomaly_id
        for v in a.correlated_anomalies:
            if v in anomaly_map:
                v_anomaly = anomaly_map[v]
                if u in v_anomaly.correlated_anomalies:
                    adj[u].add(v)
                    adj[v].add(u)
                    
    visited = set()
    clusters = []
    
    # Traverse in sorted order for deterministic results
    for node in sorted(anomaly_map.keys()):
        if node not in visited:
            component = []
            queue = [node]
            visited.add(node)
            while queue:
                curr = queue.pop(0)
                component.append(curr)
                for neighbor in sorted(adj[curr]):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            clusters.append(sorted(component))
            
    # Sort the outer list by the first element of each cluster for deterministic outer ordering
    clusters.sort(key=lambda x: x[0] if x else "")
    return clusters
