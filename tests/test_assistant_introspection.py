import unittest
from pathlib import Path
from pipeline.assistant import AssistantConfig, AssistantSession

class FakeChat:
 def __init__(self): self.calls=[]
 def __call__(self, **kwargs): self.calls.append(kwargs); return {"message":{"content":"explained"}}
class IntrospectionTests(unittest.TestCase):
 def cfg(self): return AssistantConfig("fake",Path("persona/default.md"),Path("config/assistant_policy.md"),"personal",20,5,"off","off")
 def test_no_prior_memory_asks_for_target(self):
  chat=FakeChat(); s=AssistantSession(self.cfg(),"persona",chat=chat,policy="policy",memory_loader=lambda **k: [])
  self.assertIn("which memory",s.respond("Why do you remember that?").lower()); self.assertEqual(chat.calls,[])
 def test_custom_loader_explanation_is_structured(self):
  memories=[{"id":3,"summary":"Blue glasses","details":"right eye","confidence":.9,"importance":.7,"source":"test"}]; chat=FakeChat(); s=AssistantSession(self.cfg(),"persona",chat=chat,policy="policy",memory_loader=lambda **k: memories); s.last_memory_ids=[3]
  self.assertEqual(s.respond("Where did that memory come from?"),"explained"); self.assertIn("Blue glasses",chat.calls[0]["messages"][0]["content"]); self.assertNotIn("sqlite",chat.calls[0]["messages"][0]["content"].lower())
if __name__ == "__main__": unittest.main()
