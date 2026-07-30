RETRIEVAL_CASES = []

def evaluate_retrieval(retrieve, cases=RETRIEVAL_CASES):
    top1 = top3 = irrelevant = 0
    for query, expected in cases:
        first = retrieve(query, limit=3); ids = [item["memory"]["id"] for item in first]
        if ids and ids[0] in expected: top1 += 1
        if set(ids) & set(expected): top3 += 1
        irrelevant += sum(item_id not in expected for item_id in ids)
    total = len(cases) or 1
    return {"top1_hit_rate": top1 / total, "top3_hit_rate": top3 / total, "irrelevant_result_count": irrelevant, "case_count": len(cases)}
