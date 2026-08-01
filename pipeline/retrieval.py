from typing import Protocol
from pipeline import db

class MemoryRetriever(Protocol):
 def retrieve(self, query: str, *, domain=None, limit=8): ...

class DeterministicMemoryRetriever:
 def retrieve(self, query, *, domain=None, limit=8): return db.retrieve_assistant_memories(query, domain=domain or "personal", limit=limit)

class SemanticMemoryRetriever:
 def __init__(self, collection, embed_query, memories_by_id=None): self.collection=collection; self.embed_query=embed_query; self.memories_by_id=memories_by_id or {}
 def retrieve(self, query, *, domain=None, limit=8):
  result=self.collection.query(query_embeddings=[self.embed_query(query)], n_results=limit, where={"domain": domain} if domain else None)
  ids=result.get("ids", [[]])[0]; distances=result.get("distances", [[]])[0]
  output=[]
  for index, key in enumerate(ids):
   memory=self.memories_by_id.get(key)
   if memory is None: continue
   similarity=1.0/(1.0+float(distances[index])) if index < len(distances) else 0.0
   output.append({"memory":memory,"score":round(similarity,6),"semantic_score":round(similarity,6),"reasons":[f"semantic similarity: {similarity:.3f}"]})
  return output

class HybridMemoryRetriever:
 def __init__(self, deterministic, semantic, deterministic_weight=.6, semantic_weight=.4): self.deterministic=deterministic; self.semantic=semantic; self.deterministic_weight=deterministic_weight; self.semantic_weight=semantic_weight
 def retrieve(self, query, *, domain=None, limit=8):
  combined={};
  for item in self.deterministic.retrieve(query,domain=domain,limit=limit*2): combined.setdefault(item["memory"]["id"],{}).update(item); combined[item["memory"]["id"]]["deterministic_score"]=item["score"]
  for item in self.semantic.retrieve(query,domain=domain,limit=limit*2): combined.setdefault(item["memory"]["id"],{}).update(item); combined[item["memory"]["id"]]["semantic_score"]=item["score"]
  max_d=max((x.get("deterministic_score",0) for x in combined.values()),default=1) or 1; max_s=max((x.get("semantic_score",0) for x in combined.values()),default=1) or 1
  for item in combined.values():
   d=item.get("deterministic_score",0)/max_d; sem=item.get("semantic_score",0)/max_s; item["score"]=round(self.deterministic_weight*d+self.semantic_weight*sem,6); item["reasons"]=item.get("reasons",[])+[f"hybrid deterministic: {d:.3f}",f"hybrid semantic: {sem:.3f}"]
  return sorted(combined.values(),key=lambda x:(-x["score"],-int(x["memory"]["id"])))[:limit]
