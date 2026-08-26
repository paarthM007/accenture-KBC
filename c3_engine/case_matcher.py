import os
import json
from typing import List
from .schemas import Anomaly, MatchedCase

# Resolve the path to the local database file
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "case_studies.json")

def load_case_studies() -> list:
    """Loads the case studies database in memory."""
    try:
        with open(DB_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return []

def match_cases_for_clusters(
    sector_id: str,
    clusters: List[List[str]],
    anomalies: List[Anomaly],
    threshold: float = 0.50
) -> List[MatchedCase]:
    """
    Finds matching case studies for each anomaly cluster based on context_tags overlap
    using Jaccard similarity index: |Cluster Tags ∩ Case Tags| / |Cluster Tags ∪ Case Tags|.
    
    Only returns cases with similarity score >= threshold.
    Returns the top 1-2 cases per cluster, sorted by score.
    """
    cases = load_case_studies()
    
    # Filter cases by sector
    sector_cases = [c for c in cases if c.get("sector_id") == sector_id]
    if not sector_cases:
        return []
        
    matched_cases_list = []
    anomaly_map = {a.anomaly_id: a for a in anomalies}
    
    for cluster_idx, cluster_anomaly_ids in enumerate(clusters):
        # Extract and deduplicate context tags from all anomalies in the cluster
        cluster_tags = set()
        for aid in cluster_anomaly_ids:
            if aid in anomaly_map:
                cluster_tags.update(anomaly_map[aid].context_tags)
                
        if not cluster_tags:
            continue
            
        cluster_matches = []
        for case in sector_cases:
            case_tags = set(case.get("context_tags", []))
            if not case_tags:
                continue
                
            intersection = cluster_tags.intersection(case_tags)
            union = cluster_tags.union(case_tags)
            
            similarity = len(intersection) / len(union) if union else 0.0
            similarity = round(similarity, 2)
            
            if similarity >= threshold:
                cluster_matches.append((similarity, case))
                
        # Sort: score descending, then case_id ascending (for determinism)
        cluster_matches.sort(key=lambda x: (-x[0], x[1].get("case_id", "")))
        
        # Take the top 1-2 matches
        for score, case in cluster_matches[:2]:
            matched_cases_list.append(
                MatchedCase(
                    case_id=case["case_id"],
                    cluster_index=cluster_idx,
                    similarity_score=score,
                    problem_description=case["problem_description"],
                    root_causes=case["root_causes"],
                    recommended_actions=case["recommended_actions"]
                )
            )
            
    return matched_cases_list
