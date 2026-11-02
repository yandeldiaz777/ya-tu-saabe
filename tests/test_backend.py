import importlib.util
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('backend',Path(__file__).resolve().parent.parent / 'backend.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)

class BackendTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'drive'; self.root.mkdir(); self.old=b.ROOT; b.ROOT=self.root
 def tearDown(self): b.ROOT=self.old; self.tmp.cleanup()
 def test_url_validation(self):
  self.assertEqual(b.verify_url('https://music.youtube.com/playlist?list=ABC','playlist'),'https://music.youtube.com/playlist?list=ABC')
  self.assertEqual(b.verify_url('https://music.youtube.com/browse/VLPLRBp0Fe2GpgmgoscNFLxNyBVSFVdYmFkq','playlist'),'https://music.youtube.com/playlist?list=PLRBp0Fe2GpgmgoscNFLxNyBVSFVdYmFkq')
  for url in ['file:///etc/passwd','https://youtube.com.evil.example/watch?v=x','https://youtube.com/watch?v=x']:
   with self.assertRaises(ValueError): b.verify_url(url,'playlist')
 def test_single_mode_rejects_playlist_only_link(self):
  with self.assertRaisesRegex(ValueError,'una canción'):
   b.verify_url('https://music.youtube.com/playlist?list=PLabc','single')
  for url in ['https://music.youtube.com/watch?v=abcdefghijk&list=PLabc', 'https://youtu.be/abcdefghijk', 'https://youtube.com/shorts/abcdefghijk']:
   self.assertEqual(b.verify_url(url,'single'),url)
 def test_metadata_counts_unavailable_entries(self):
  data={'title':'Lista','entries':[{'id':'abcdefghijk','title':'Canción'},None,{'title':'No disponible'},{'id':'bad'}]}
  with patch.object(b,'run',return_value=(0,__import__('json').dumps(data))),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit'):
   self.assertEqual(b.metadata('/fake/yt-dlp','https://youtube.com/playlist?list=abc'),('Lista',[('abcdefghijk','Canción')],3))
 def test_duration_validation_short_tolerance_and_unknown(self):
  import json
  duration_file=self.root/'duration.txt'
  def probe(actual):
   return json.dumps({'streams':[{'codec_name':'mp3','sample_rate':'44100'}],'format':{'duration':str(actual)}}).encode()
  with patch.object(b,'binary',return_value='/fake/ffprobe'),patch.object(b,'run',return_value=(0,'')),patch.object(b,'emit'):
   duration_file.write_text('180')
   with patch.object(b.subprocess,'check_output',return_value=probe(100)):
    self.assertFalse(b.validate_audio(self.root/'song.mp3',duration_file))
   with patch.object(b.subprocess,'check_output',return_value=probe(178)):
    self.assertTrue(b.validate_audio(self.root/'song.mp3',duration_file))
   duration_file.write_text('NA')
   with patch.object(b.subprocess,'check_output',return_value=probe(100)):
    self.assertTrue(b.validate_audio(self.root/'song.mp3',duration_file))
   with patch.object(b.subprocess,'check_output',return_value=probe(100)),patch.object(b,'run',return_value=(1,'')):
    self.assertFalse(b.validate_audio(self.root/'song.mp3',duration_file))
 def test_partial_playlist_is_not_reported_as_success(self):
  argv=['backend.py','--url','https://youtube.com/playlist?list=abc','--mode','playlist','--destination',str(self.root)]
  events=[]
  def fake_run(args,capture=False):
   template=args[args.index('--output')+1]
   Path(template.replace('%(title).120B','Tema').replace('%(id)s','abcdefghijk').replace('%(ext)s','mp3')).write_bytes(b'audio')
   return 0,''
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'metadata',return_value=('Lista',[('abcdefghijk','Tema')],2)),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit',side_effect=lambda kind,message,**kw:events.append((kind,message))):
   self.assertEqual(b.execute(),1)
  self.assertTrue(any(kind=='done' and '2 omitidas' in msg for kind,msg in events))
 def test_symlink_cannot_create_outside(self):
  outside=Path(self.tmp.name)/'outside'; outside.mkdir(); (self.root/'Musica').symlink_to(outside,target_is_directory=True)
  with self.assertRaises(RuntimeError): b.safe_dir('Musica','escapes')
  self.assertFalse((outside/'escapes').exists())
 def test_f3_blocks_before_creating_directories(self):
  argv=['backend.py','--url','https://youtu.be/abcdefghijk','--mode','single','--quality','256','--destination',str(self.root)]
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'f3_active',return_value=True):
   with self.assertRaisesRegex(RuntimeError,'F3'): b.execute()
  self.assertEqual(list(self.root.iterdir()),[])
 def test_existing_user_files_do_not_overfill_playlist_folder(self):
  argv=['backend.py','--url','https://music.youtube.com/playlist?list=abc','--mode','playlist','--quality','256','--destination',str(self.root)]
  key=b.hashlib_short('abc'); part=self.root/f'Mi musica [{key}]'/'Parte 001'; part.mkdir(parents=True)
  for i in range(200): (part/f'otra-{i}.txt').write_text('x')
  def fake_run(args,capture=False):
   template=args[args.index('--output')+1]
   Path(template.replace('%(title).120B','Tema').replace('%(id)s','abcdefghijk').replace('%(ext)s','mp3')).write_bytes(b'audio')
   return 0,''
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'metadata',return_value=('Mi musica',[('abcdefghijk','Tema')],0)),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit'):
   self.assertEqual(b.execute(),0)
  self.assertEqual(len(list(part.iterdir())),200)
  self.assertEqual(len(list((part.parent/'Parte 001 extra 01').glob('*.mp3'))),1)
 def test_playlist_splits_and_cleans_temp(self):
  argv=['backend.py','--url','https://music.youtube.com/playlist?list=abc','--mode','playlist','--quality','256','--destination',str(self.root)]
  def fake_run(args, capture=False):
   template=args[args.index('--output')+1]
   path=Path(template.replace('%(title).120B','Tema').replace('%(id)s',args[-1].split('v=')[-1]).replace('%(ext)s','mp3'))
   path.write_bytes(b'fake audio')
   return 0,''
  entries=[(f'{i:011d}',f'Tema {i}') for i in range(205)]
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'metadata',return_value=('Mi musica',entries,0)),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit'):
   self.assertEqual(b.execute(),0)
  dirs=next(self.root.iterdir())
  self.assertEqual(len(list((dirs/'Parte 001').glob('*.mp3'))),200)
  self.assertEqual(len(list((dirs/'Parte 002').glob('*.mp3'))),5)
  self.assertFalse(list(self.root.glob('.descarga-*')))
  reversed_entries=list(reversed(entries))
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'metadata',return_value=('Titulo cambiado',reversed_entries,0)),patch.object(b,'run',side_effect=AssertionError('redescargó un elemento existente')),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit'):
   self.assertEqual(b.execute(),0)
  self.assertEqual(len(list(self.root.iterdir())),1)
  self.assertEqual(len(list(dirs.rglob('*.mp3'))),205)

 def test_four_downloads_actually_run_concurrently(self):
  argv=['backend.py','--url','https://music.youtube.com/playlist?list=abc','--mode','playlist','--quality','256','--destination',str(self.root),'--workers','4','--artwork']
  barrier=threading.Barrier(4); lock=threading.Lock(); active=0; maximum=0; seen=[]
  def fake_run(args,capture=False):
   nonlocal active,maximum
   self.assertIn('--embed-thumbnail',args); self.assertIn('--convert-thumbnails',args); self.assertIn('--embed-metadata',args)
   self.assertIn('--concurrent-fragments',args)
   with lock:
    active+=1; maximum=max(maximum,active); seen.append(args[-1])
   barrier.wait(timeout=4)
   template=args[args.index('--output')+1]
   Path(template.replace('%(title).120B','Tema').replace('%(id)s',args[-1].split('v=')[-1]).replace('%(ext)s','mp3')).write_bytes(b'audio')
   with lock: active-=1
   return 0,''
  entries=[(f'{i:011d}',f'Tema {i}') for i in range(4)] + [('00000000000','duplicado')]
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'metadata',return_value=('Lista',entries,0)),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit'):
   self.assertEqual(b.execute(),0)
  self.assertEqual(maximum,4); self.assertEqual(len(seen),4)
  self.assertEqual(len(list(self.root.rglob('*.mp3'))),4)
 def test_artwork_failure_retries_without_losing_audio(self):
  argv=['backend.py','--url','https://youtu.be/abcdefghijk','--mode','single','--quality','256','--destination',str(self.root),'--artwork']
  attempts=[]; events=[]
  def fake_run(args,capture=False):
   attempts.append(args)
   if '--embed-thumbnail' in args: return 1,'ERROR: thumbnail unavailable'
   template=args[args.index('--output')+1]
   Path(template.replace('%(title).120B','Tema').replace('%(id)s','abcdefghijk').replace('%(ext)s','mp3')).write_bytes(b'audio')
   return 0,''
  def save_event(kind,message,**kw): events.append((kind,message))
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit',side_effect=save_event):
   self.assertEqual(b.execute(),0)
  self.assertEqual(len(attempts),2); self.assertNotIn('--embed-thumbnail',attempts[1])
  self.assertEqual(len(list(self.root.rglob('*.mp3'))),1)
  self.assertTrue(any('1 sin carátula' in msg for _,msg in events))
 def test_unavailable_video_is_not_retried_as_an_artwork_failure(self):
  argv=['backend.py','--url','https://music.youtube.com/playlist?list=abc','--mode','playlist','--destination',str(self.root),'--artwork']
  attempts=[]; events=[]
  def fake_run(args,capture=False):
   attempts.append(args)
   return 1,'ERROR: [youtube] AbCdEf12345: Video unavailable. This video is not available\n'
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'metadata',return_value=('Lista',[('AbCdEf12345','Video de ejemplo')],0)),patch.object(b,'music_canonical_id',return_value=None),patch.object(b,'run',side_effect=fake_run),patch.object(b,'emit',side_effect=lambda kind,message,**kw:events.append((kind,message))):
   self.assertEqual(b.execute(),1)
  self.assertEqual(len(attempts),1)
  self.assertTrue(any(kind=='error' and 'AbCdEf12345' in msg and 'YouTube no permitió' in msg for kind,msg in events))
  self.assertFalse(any('reintentando sin carátula' in msg for _,msg in events))
  self.assertFalse(list(self.root.rglob('*.mp3')))
 def test_unavailability_classifier_ignores_unrelated_failures(self):
  for message in ('ERROR: [youtube] id: Private video', 'ERROR: [youtube] id: Sign in to confirm your age', 'ERROR: [youtube] id: This video is not available'):
   self.assertTrue(b.youtube_unavailable(message))
  for message in ('WARNING: Video unavailable', 'ERROR: thumbnail unavailable', 'ERROR: HTTP Error 403: Forbidden', ''):
   self.assertFalse(b.youtube_unavailable(message))
 def test_success_without_embedded_image_is_reported(self):
  argv=['backend.py','--url','https://youtu.be/abcdefghijk','--mode','single','--quality','256','--destination',str(self.root),'--artwork']
  events=[]
  def fake_run(args,capture=False):
   template=args[args.index('--output')+1]
   Path(template.replace('%(title).120B','Tema').replace('%(id)s','abcdefghijk').replace('%(ext)s','mp3')).write_bytes(b'audio')
   return 0,''
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'run',side_effect=fake_run),patch.object(b,'has_embedded_art',return_value=False),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit',side_effect=lambda kind,message,**kw:events.append((kind,message))):
   self.assertEqual(b.execute(),0)
  self.assertEqual(len(list(self.root.rglob('*.mp3'))),1)
  self.assertTrue(any(kind=='done' and '1 sin carátula' in msg for kind,msg in events))

 def test_appledouble_mp3_does_not_count_as_second_audio(self):
  argv=['backend.py','--url','https://youtu.be/abcdefghijk','--mode','single','--quality','256','--destination',str(self.root)]
  def fake_run(args,capture=False):
   template=args[args.index('--output')+1]
   audio=Path(template.replace('%(title).120B','Tema').replace('%(id)s','abcdefghijk').replace('%(ext)s','mp3'))
   audio.write_bytes(b'audio')
   (audio.parent/('._'+audio.name)).write_bytes(b'metadata')
   return 0,''
  with patch.object(sys,'argv',argv),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit'):
   self.assertEqual(b.execute(),0)
  self.assertEqual(len([p for p in self.root.rglob('*.mp3') if not p.name.startswith('.')]),1)
  self.assertFalse(list(self.root.glob('.descarga-*')))

 def test_cleanup_handles_disappearing_appledouble(self):
  temp=self.root/'.descarga-test'; temp.mkdir()
  (temp/'song.mp3').write_bytes(b'audio'); (temp/'._song.mp3').write_bytes(b'metadata')
  import contextlib
  real_unlink=os.unlink; real_scandir=os.scandir; disappeared=[]
  @contextlib.contextmanager
  def entries_with_companion_last(*args, **kwargs):
   with real_scandir(*args, **kwargs) as entries:
    yield iter(sorted(entries, key=lambda entry: entry.name.startswith('._')))
  def unlink_with_appledouble(path, *, dir_fd=None):
   if Path(path).name == 'song.mp3':
    try:
     sidecar = '._song.mp3' if dir_fd is not None else str(Path(path).with_name('._song.mp3'))
     real_unlink(sidecar,dir_fd=dir_fd)
     disappeared.append(True)
    except FileNotFoundError:
     pass
   return real_unlink(path,dir_fd=dir_fd)
  with patch.object(os,'scandir',side_effect=entries_with_companion_last),patch.object(os,'unlink',side_effect=unlink_with_appledouble): b.remove_temp_dir(temp)
  self.assertFalse(temp.exists())
  self.assertTrue(disappeared, 'la prueba debe ejercitar la desaparición del acompañante')

 def test_cleanup_does_not_hide_permission_errors(self):
  def failed_removal(path,onerror):
   try: raise PermissionError('sin permiso')
   except PermissionError: onerror(os.unlink,str(path),sys.exc_info())
  with patch.object(b.shutil,'rmtree',side_effect=failed_removal):
   with self.assertRaises(PermissionError): b.remove_temp_dir(self.root/'tmp')
 def test_cancellation_stops_running_child_process(self):
  b.cancelled=False
  def cancel():
   time.sleep(.3); b.cancelled=True
  t=threading.Thread(target=cancel); t.start()
  start=time.monotonic()
  try:
   with patch.object(b,'volume_present',return_value=True):
    with self.assertRaisesRegex(RuntimeError,'cancelada'):
     b.run(['/usr/bin/python3','-c','import time; time.sleep(30)'])
   self.assertLess(time.monotonic()-start,3)
  finally:
   t.join(); b.cancelled=False

if __name__=='__main__': unittest.main()
