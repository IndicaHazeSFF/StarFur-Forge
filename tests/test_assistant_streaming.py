import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import assistant as assistant_module
from pipeline.assistant import AssistantConfig, AssistantSession, GenerationInterrupted, run_interactive
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

 def test_interrupt_before_first_token_rolls_back_turn(self):
  def chat(**kwargs):
   def stream():
    raise KeyboardInterrupt()
    yield None
   return stream()
  cfg=AssistantConfig("fake",Path("persona/default.md"),Path("config/assistant_policy.md"),"personal",20,0,"conservative","off")
  s=AssistantSession(cfg,"persona",chat=chat,memory_loader=lambda **k: [],policy="policy",stream=True,stream_writer=lambda _: None)
  s.last_memory_ids=[42]
  with self.assertRaises(GenerationInterrupted): s.respond("I like tea")
  self.assertEqual(s.messages,[]); self.assertEqual(s.proposals,[]); self.assertEqual(s.last_memory_ids,[42])

 def test_interrupt_after_partial_output_does_not_save_or_propose(self):
  seen=[]
  def chat(**kwargs):
   def stream():
    yield {"message":{"content":"partial"}}
    raise KeyboardInterrupt()
   return stream()
  cfg=AssistantConfig("fake",Path("persona/default.md"),Path("config/assistant_policy.md"),"personal",20,0,"conservative","off")
  s=AssistantSession(cfg,"persona",chat=chat,memory_loader=lambda **k: [],policy="policy",stream=True,stream_writer=seen.append)
  with self.assertRaises(GenerationInterrupted): s.respond("I like tea")
  self.assertEqual(seen,["partial"]); self.assertEqual(s.messages,[]); self.assertEqual(s.proposals,[])

 def test_ctrl_c_at_input_prompt_exits_cleanly(self):
  output=[]
  def interrupted(_): raise KeyboardInterrupt()
  with patch.object(assistant_module.ollama, "chat", lambda **kwargs: {"message": {"content": "unused"}}, create=True):
   run_interactive(input_fn=interrupted, output_fn=output.append)
  self.assertTrue(any("Goodbye." in line for line in output))

if __name__ == "__main__": unittest.main()
