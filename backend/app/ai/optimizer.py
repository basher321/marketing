"""Rules + bandit ad optimization (structural stub)."""


def recommend_budget_shift(ad_performance: list[dict]) -> list[dict]:
    """Given [{"ad_id": ..., "roas": ...}, ...], return suggested budget deltas."""
    if not ad_performance:
        return []
    avg_roas = sum(a.get("roas", 0) for a in ad_performance) / len(ad_performance)
    return [
        {"ad_id": a["ad_id"], "suggested_delta_pct": 10 if a.get("roas", 0) > avg_roas else -10}
        for a in ad_performance
    ]
