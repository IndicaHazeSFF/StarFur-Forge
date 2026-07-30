import json
from pathlib import Path
from pipeline import db

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

def load_cases(path=FIXTURE_ROOT / "retrieval_cases.json"):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,list): raise ValueError("Retrieval fixture must be a list")
    required={"name","query","expected_keys","irrelevant_keys","domain","limit"}
    for case in data:
        if not isinstance(case,dict) or not required.issubset(case) or not isinstance(case["limit"],int) or case["limit"]<=0: raise ValueError("Invalid retrieval case")
        if not isinstance(case["expected_keys"],list) or not isinstance(case["irrelevant_keys"],list): raise ValueError("Invalid retrieval keys")
    return data

def load_memories(path=FIXTURE_ROOT / "retrieval_memories.json"):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,list): raise ValueError("Retrieval memories fixture must be a list")
    return data

def run_benchmark(cases=None, memories=None):
    cases=load_cases() if cases is None else cases; memories=load_memories() if memories is None else memories
    old=db.DB_PATH; import tempfile; temp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True); db.DB_PATH=Path(temp.name)/"retrieval.sqlite"
    try:
        key_to_id={}
        for item in memories:
            key=item["key"]; key_to_id[key]=db.create_assistant_memory(item["subject"],item["memory_type"],item["summary"],details=item.get("details"),importance=item.get("importance",.5),confidence=item.get("confidence",.5),retention=item.get("retention","long_term"),domain=item.get("domain","personal"))
        top1=top3=irrelevant=0; failures=[]; repeat=True
        for case in cases:
            expected={key_to_id[k] for k in case["expected_keys"]}; irrelevant_keys={key_to_id[k] for k in case["irrelevant_keys"]}
            def retrieve(q): return db.retrieve_assistant_memories(q,domain=case["domain"],limit=case["limit"])
            first=retrieve(case["query"]); second=retrieve(case["query"]); ids=[x["memory"]["id"] for x in first]; repeat &= ids==[x["memory"]["id"] for x in second]
            if ids and ids[0] in expected: top1+=1
            if set(ids)&expected: top3+=1
            irrelevant += sum(i in irrelevant_keys or i not in expected for i in ids)
            if (expected and (not ids or ids[0] not in expected)) or (not expected and ids): failures.append({"name":case["name"],"expected":sorted(expected),"returned":ids})
        total=len(cases) or 1
        return {"cases":len(cases),"top1_hit_rate":top1/total,"top3_hit_rate":top3/total,"irrelevant_result_count":irrelevant,"repeatability":repeat,"failures":failures}
    finally: db.DB_PATH=old; temp.cleanup()
