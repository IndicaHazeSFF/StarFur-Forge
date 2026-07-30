import unittest
from pathlib import Path
from pipeline.assistant import AssistantConfig, AssistantSession
class Message:
 def __init__(self, content, thinking=""): self.content=content; self.thinking=thinking
class Chunk:
 def __init__(self, content, thinking=""): self.message=Message(content,thinking)
class StreamingTests(unittest.TestCase):
 def test_typed_chunks_ignore_thinking_and_render_content(self):
  seen=[]
  def chat(**kwargs): return iter([Chunk("", "internal thought"), Chunk("hel", "more thought"), Chunk("lo")])
  cfg=AssistantConfig("fake",Path("persona/default.md"),Path("config/assistant_policy.md"),"personal",20,0,"off","off")
  s=AssistantSession(cfg,"persona",chat=chat,memory_loader=lambda **k: [],policy="policy",stream=True,stream_writer=seen.append)
  self.assertEqual(s.respond("hello"),"hello"); self.assertEqual(seen,["hel","lo"])

 def test_stream_chunks_accumulate_and_render(self):
  seen=[]
  def chat(**kwargs):
   if kwargs.get("stream"): return iter([{"message":{"content":"hel"}},{"message":{"content":"lo"}}])
   return {"message":{"content":"{}"}}
  cfg=AssistantConfig("fake",Path("persona/default.md"),Path("config/assistant_policy.md"),"personal",20,0,"off","off")
  s=AssistantSession(cfg,"persona",chat=chat,memory_loader=lambda **k: [],policy="policy",stream=True,stream_writer=seen.append)
  self.assertEqual(s.respond("hello"),"hello"); self.assertEqual(seen,["hel","lo"]); self.assertEqual(s.messages[-1]["content"],"hello")
if __name__ == "__main__": unittest.main()
