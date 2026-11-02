import contextlib, http.server, importlib.util, json, os, sys, tempfile, threading, unittest, wave, math, struct
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('backend_under_test',Path(__file__).resolve().parent.parent / 'backend.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
class Integration(unittest.TestCase):
 def test_real_downloader_and_ffmpeg_on_synthetic_media(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); drive=root/'fake-volume'; drive.mkdir()
   wav=root/'test.wav'
   with wave.open(str(wav),'wb') as f:
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000)
    f.writeframes(b''.join(struct.pack('<h',round(8000*math.sin(2*math.pi*440*i/24000))) for i in range(24000)))
   def handler(*args, **kwargs): return Handler(*args,directory=str(root),**kwargs)
   server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
   th=threading.Thread(target=server.serve_forever,daemon=True); th.start()
   url=f'http://127.0.0.1:{server.server_port}/test.wav'
   argv=['backend.py','--url',url,'--mode','single','--quality','320','--destination',str(drive),'--artwork']
   events=[]
   try:
    with patch.object(b,'ROOT',drive),patch.object(b,'verify_url',side_effect=lambda url,mode:url),patch.object(b,'validate_volume'),patch.object(b,'volume_present',return_value=True),patch.object(b,'f3_active',return_value=False),patch.object(sys,'argv',argv),patch.object(b,'emit',side_effect=lambda typ,msg,**kw: events.append((typ,msg))):
     b.cancelled=False
     self.assertEqual(b.execute(),0,events)
    paths=list(drive.rglob('*.mp3'))
    self.assertEqual(len(paths),1,events)
    import subprocess
    p=subprocess.run([b.binary('ffprobe'),'-v','error','-show_entries','stream=codec_name,sample_rate,channels,bit_rate:format=duration','-of','json',str(paths[0])],capture_output=True,text=True,check=True)
    info=json.loads(p.stdout); stream=info['streams'][0]
    self.assertEqual(stream['codec_name'],'mp3')
    self.assertEqual(stream['sample_rate'],'44100'); self.assertEqual(stream['channels'],2)
    self.assertEqual(int(stream['bit_rate']),320000)
    self.assertLess(abs(float(info['format']['duration'])-1),0.3)
    self.assertEqual(paths[0].read_bytes()[:4],b'ID3\x03')
    self.assertFalse(list(drive.rglob('.descarga-*')))
   finally:
    server.shutdown(); server.server_close(); th.join()
if __name__=='__main__': unittest.main()
