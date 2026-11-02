import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('dedup_backend',Path(__file__).resolve().parent.parent / 'backend.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)

class DedupTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.root=Path(self.temp.name).resolve(); b.cancelled=False
 def tearDown(self):
  b.cancelled=False; self.temp.cleanup()
 def call(self, playlist, entries, *, folder=None, url=None):
  is_single=url is not None
  url=url or 'https://music.youtube.com/playlist?list='+playlist
  argv=['backend.py','--url',url,'--mode','single' if is_single else 'playlist','--destination',str(self.root),'--workers','4']
  if folder: argv.extend(['--new-folder',folder])
  calls=[]; events=[]
  def fake_run(args,capture=False):
   calls.append(args[-1])
   template=args[args.index('--output')+1]
   vid=args[-1].split('v=')[-1] if 'v=' in args[-1] else args[-1].rsplit('/',1)[-1]
   path=Path(template.replace('%(title).120B','Mismo_titulo').replace('%(id)s',vid).replace('%(ext)s','mp3'))
   path.write_bytes(b'fake-audio'); return 0,''
  def event(kind,message,**kw): events.append((kind,message,kw))
  with patch.object(sys,'argv',argv),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'metadata',return_value=('Lista '+str(playlist),entries,0)),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit',side_effect=event):
   code=b.execute()
  return code,calls,events
 def mp3s(self):
  return sorted(p for p in self.root.rglob('*.mp3') if not p.name.startswith('.') and not p.is_symlink())
 def test_two_playlists_and_single_skip_across_all_subfolders(self):
  a='AbCdEf12345'; overlap='B2345678901'; c='C2345678901'
  self.assertEqual(self.call('first',[(a,'A'),(overlap,'B')])[0],0)
  original={p.relative_to(self.root):p.read_bytes() for p in self.mp3s()}
  code,calls,events=self.call('second',[(overlap,'B'),(c,'C')])
  self.assertEqual(code,0); self.assertEqual(calls,['https://music.youtube.com/watch?v='+c])
  self.assertEqual(len(self.mp3s()),3)
  self.assertTrue(any(k=='done' and e.get('success')==1 and e.get('skipped')==1 for k,_,e in events))
  for rel,data in original.items(): self.assertEqual((self.root/rel).read_bytes(),data)
  code,calls,events=self.call(None,[],url='https://youtu.be/'+a)
  self.assertEqual((code,calls),(0,[])); self.assertEqual(len(self.mp3s()),3)
  self.assertTrue(any(k=='done' and e.get('skipped')==1 and e.get('success')==0 for k,_,e in events))
 def test_new_subfolder_does_not_hide_previous_songs(self):
  vid='AbCdEf12345'; self.call('first',[(vid,'A')])
  code,calls,events=self.call('second',[(vid,'A')],folder='Otra carpeta')
  self.assertEqual((code,calls),(0,[])); self.assertEqual(len(self.mp3s()),1)
  self.assertTrue((self.root/'Otra carpeta').is_dir())
 def test_id_is_case_sensitive_and_same_title_not_enough(self):
  low='abcdefghijk'; high='ABCDEFGHIJK'
  self.call('first',[(low,'Mismo título')]); code,calls,_=self.call('second',[(high,'Mismo título')])
  self.assertEqual(code,0); self.assertEqual(len(calls),1); self.assertEqual(len(self.mp3s()),2)
 def test_single_ids_differing_only_in_case_survive_name_collision(self):
  low='abcdefghijk'; high='ABCDEFGHIJK'
  self.assertEqual(self.call(None,[],url='https://youtu.be/'+low)[0],0)
  code,calls,_=self.call(None,[],url='https://youtu.be/'+high)
  self.assertEqual(code,0); self.assertEqual(len(calls),1)
  self.assertEqual(len(self.mp3s()),2)
  names=[p.name for p in self.mp3s()]
  self.assertTrue(any(name.endswith('['+low+'].mp3') for name in names))
  self.assertTrue(any(name.endswith('['+high+'].mp3') for name in names))
  code,calls,_=self.call(None,[],url='https://youtu.be/'+high)
  self.assertEqual((code,calls),(0,[])); self.assertEqual(len(self.mp3s()),2)
 def test_symlinks_hidden_files_and_other_scope_are_not_counted(self):
  vid='AbCdEf12345'; outside=Path(self.temp.name).parent/'dedup-outside-fixture'
  with tempfile.TemporaryDirectory() as outside:
   external=Path(outside).resolve(); (external/f'Song [{vid}].mp3').write_bytes(b'audio')
   (self.root/'link-dir').symlink_to(external,target_is_directory=True)
   (self.root/f'linked [{vid}].mp3').symlink_to(external/f'Song [{vid}].mp3')
   hidden=self.root/'.tmp'; hidden.mkdir(); (hidden/f'Song [{vid}].mp3').write_bytes(b'audio')
   (self.root/'Mismo título.mp3').write_bytes(b'audio')
   b.set_destination(str(self.root)); self.assertNotIn(vid,b.existing_video_ids(self.root))
   code,calls,_=self.call('second',[(vid,'Mismo título')]); self.assertEqual(code,0); self.assertEqual(len(calls),1)
   self.assertEqual((external/f'Song [{vid}].mp3').read_bytes(),b'audio')
 def test_distinct_destination_is_independent(self):
  vid='AbCdEf12345'; self.call('first',[(vid,'A')]); other=self.root/'independiente'; other.mkdir(); self.root=other
  code,calls,_=self.call('second',[(vid,'A')]); self.assertEqual(code,0); self.assertEqual(len(calls),1)
 def test_nested_mount_is_not_scanned(self):
  from types import SimpleNamespace
  nested=self.root/'otro-volumen'; nested.mkdir(); vid='AbCdEf12345'
  (nested/f'Song [{vid}].mp3').write_bytes(b'audio')
  b.set_destination(str(self.root)); real_stat=Path.stat
  def fake_stat(path,*args,**kwargs):
   if path==nested: return SimpleNamespace(st_dev=os.stat(self.root).st_dev+123)
   return real_stat(path,*args,**kwargs)
  with patch.object(Path,'stat',fake_stat): self.assertNotIn(vid,b.existing_video_ids(self.root))
 def test_repeated_id_within_list_is_counted_once(self):
  vid='AbCdEf12345'; code,calls,events=self.call('first',[(vid,'A'),(vid,'A otra vez')])
  self.assertEqual((code,len(calls)),(0,1)); self.assertEqual(len(self.mp3s()),1)
  self.assertTrue(any(k=='done' and '1 repetidas dentro de la lista' in msg for k,msg,_ in events))
 def test_selected_folder_lock_blocks_another_download(self):
  with b.destination_lock(self.root):
   with self.assertRaisesRegex(RuntimeError,'otra descarga'):
    with b.destination_lock(self.root): pass
  with b.destination_lock(self.root): pass

if __name__=='__main__': unittest.main()
