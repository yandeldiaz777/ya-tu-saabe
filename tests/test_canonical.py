import importlib.util
import contextlib
import http.client
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('canonical_backend',Path(__file__).resolve().parent.parent / 'backend.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
OLD='AbCdEf12345'; NEW='ZyXwVu98765'

class Response:
 def __init__(self,body,url='https://music.youtube.com/watch?v='+OLD): self.body=body.encode(); self.url=url
 def __enter__(self): return self
 def __exit__(self,*a): return False
 def geturl(self): return self.url
 def read(self,n): return self.body[:n]
class Opener:
 def __init__(self,response): self.response=response
 def open(self,req,timeout): return self.response

class CanonicalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'drive'; self.root.mkdir(); b.cancelled=False
 def tearDown(self):
  b.cancelled=False; self.tmp.cleanup()
 def resolve(self,html,url='https://music.youtube.com/watch?v='+OLD):
  with patch.object(b,'volume_present',return_value=True), patch.object(b.urllib.request,'build_opener',return_value=Opener(Response(html,url))):
   return b.music_canonical_id(OLD)
 def test_exact_official_canonical(self):
  self.assertEqual(self.resolve('<link rel="canonical" href="https://music.youtube.com/watch?v='+NEW+'">'),NEW)
 def test_rejects_non_music_and_ambiguous_links(self):
  for html in ['<link rel="canonical" href="https://music.youtube.com.evil.test/watch?v='+NEW+'">', '<link rel="canonical" href="https://evil.test/watch?v='+NEW+'">', '<link rel="canonical" href="https://music.youtube.com/watch?v='+NEW+'"><link rel="canonical" href="https://music.youtube.com/watch?v=abcdefghijk">', '<link rel="canonical" href="https://music.youtube.com/watch?v='+OLD+'">']:
   self.assertIsNone(self.resolve(html))
  self.assertIsNone(self.resolve('<link rel="canonical" href="https://music.youtube.com/watch?v='+NEW+'">','https://evil.test/watch?v='+OLD))
 def test_cancel_is_not_swallowed(self):
  b.cancelled=True
  with patch.object(b,'volume_present',return_value=True),self.assertRaisesRegex(RuntimeError,'cancelada'):
   b.music_canonical_id(OLD)
 def test_broken_http_response_falls_back_without_crash(self):
  response=Response('')
  with patch.object(response,'read',side_effect=http.client.IncompleteRead(b'incomplete')),patch.object(b,'volume_present',return_value=True),patch.object(b.urllib.request,'build_opener',return_value=Opener(response)):
   self.assertIsNone(b.music_canonical_id(OLD))
 def test_existing_ids_recognize_explicit_alias_and_ignore_title_brackets(self):
  (self.root/f'Tema [origen={OLD}] [{NEW}].mp3').write_bytes(b'audio')
  (self.root/'Tema [abcdefghijk] [12345678901].mp3').write_bytes(b'audio')
  with patch.object(b,'volume_present',return_value=True): ids=b.existing_video_ids(self.root)
  self.assertEqual(ids,{OLD,NEW,'12345678901'})
 def test_fallback_and_future_runs_deduplicate_both_ids(self):
  argv=['backend.py','--url','https://music.youtube.com/playlist?list=abc','--mode','playlist','--destination',str(self.root),'--artwork']
  entries=[(OLD,'Tema')]; attempts=[]
  def fake_run(args,capture=False):
   video=args[-1].split('v=')[-1]; attempts.append(video)
   if video==OLD: return 1,'ERROR: [youtube] unavailable: Video unavailable. This video is not available\n'
   template=args[args.index('--output')+1]
   Path(template.replace('%(title).120B','Tema').replace('%(id)s',video).replace('%(ext)s','mp3')).write_bytes(b'audio')
   return 0,''
  common=[patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'metadata',return_value=('Lista',entries,0)),patch.object(b,'music_canonical_id',return_value=NEW),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'has_embedded_art',return_value=False),patch.object(b,'emit')]
  with contextlib.ExitStack() as stack:
   for p in common: stack.enter_context(p)
   self.assertEqual(b.execute(),0)
   self.assertEqual(attempts,[OLD,NEW])
   paths=list(self.root.rglob('*.mp3')); self.assertEqual(len(paths),1)
   self.assertIn(f'[origen={OLD}] [{NEW}].mp3',paths[0].name)
   attempts.clear(); self.assertEqual(b.execute(),0); self.assertFalse(attempts)
   entries[:]=[(NEW,'Tema')]; self.assertEqual(b.execute(),0); self.assertFalse(attempts)
 def test_collision_keeps_both_ids_at_end(self):
  p=self.root/f'Tema [origen={OLD}] [{NEW}].mp3'; p.write_bytes(b'audio')
  other=b.unique_destination(p,NEW); self.assertIn(f'[origen={OLD}] [{NEW}].mp3',other.name)
 def test_parallel_original_and_canonical_publish_only_one(self):
  argv=['backend.py','--url','https://music.youtube.com/playlist?list=abc','--mode','playlist','--destination',str(self.root),'--workers','2']
  barrier=threading.Barrier(2)
  def fake_run(args,capture=False):
   video=args[-1].split('v=')[-1]
   if video==OLD: return 1,'ERROR: Video unavailable. This video is not available\n'
   barrier.wait(timeout=5)
   template=args[args.index('--output')+1]
   Path(template.replace('%(title).120B','Tema').replace('%(id)s',video).replace('%(ext)s','mp3')).write_bytes(b'audio')
   return 0,''
  common=[patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'metadata',return_value=('Lista',[(OLD,'Tema'),(NEW,'Tema')],0)),patch.object(b,'music_canonical_id',return_value=NEW),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit')]
  with contextlib.ExitStack() as stack:
   for p in common: stack.enter_context(p)
   self.assertEqual(b.execute(),0)
  self.assertEqual(len(list(self.root.rglob('*.mp3'))),1)

if __name__=='__main__': unittest.main()
