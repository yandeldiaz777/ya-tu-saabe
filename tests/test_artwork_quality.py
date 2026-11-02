import contextlib
import http.server
import importlib.util
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('backend', HERE.parent / 'backend.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
FF = b.binary('ffmpeg')

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path=='/truncated.jpg':
            self.send_response(200)
            self.send_header('Content-Length','500000')
            self.end_headers()
            self.wfile.write(b'incomplete')
            self.close_connection=True
            return
        return super().do_GET()

class ArtworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(dir=HERE)
        cls.root = Path(cls.scratch.name)
        for name, size, color in [('small', '640x480', 'blue'), ('large', '1280x720', 'red'), ('tiny', '320x180', 'green')]:
            subprocess.run([FF, '-v', 'error', '-f', 'lavfi', '-i', 'color=c='+color+':s='+size, '-frames:v', '1', '-threads', '1', str(cls.root/(name+'.jpg'))], check=True)
        subprocess.run([FF, '-v', 'error', '-i', str(cls.root/'large.jpg'), '-frames:v', '1', '-threads', '1', str(cls.root/'large.png')], check=True)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), lambda *a, **k: QuietHandler(*a, directory=str(cls.root), **k))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:'+str(cls.server.server_port)+'/'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.scratch.cleanup()
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=self.root)
        self.work = Path(self.tmp.name)
        self.audio = self.work/'song.mp3'
        subprocess.run([FF, '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-i', str(self.root/'small.jpg'), '-map', '0:a', '-map', '1:v', '-c:a', 'libmp3lame', '-b:a', '192k', '-ar', '44100', '-ac', '2', '-c:v', 'copy', '-disposition:v:0', 'attached_pic', '-id3v2_version', '3', str(self.audio)], check=True)
        (self.work/'duracion.txt').write_text('2\n')
        self.patches = [patch.object(b, 'volume_present', return_value=True), patch.object(b, 'allowed_thumbnail_url', side_effect=lambda u: u.startswith(self.base))]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()
    def info(self, thumbnails):
        (self.work/'item.info.json').write_text(json.dumps({'thumbnails': thumbnails}))
    def thumb(self, name, width, height):
        return {'url':self.base+name+'.jpg','width':width,'height':height}
    def test_real_dimensions_win_over_inflated_metadata_and_404(self):
        self.info([self.thumb('missing',5000,5000),self.thumb('small',4000,4000),self.thumb('large',1280,720)])
        self.assertEqual(b.improve_artwork(self.audio,self.work,FF),(1280,720))
        self.assertEqual(b.picture_dimensions(self.audio,True),(1280,720))
        self.assertEqual(self.audio.read_bytes()[:4],b'ID3\x03')
        self.assertTrue(b.validate_audio(self.audio,self.work/'duracion.txt'))
        self.assertEqual(b.picture_codec(self.audio),'mjpeg')
        extracted=self.work/'extracted.jpg'
        subprocess.run([FF,'-v','error','-i',str(self.audio),'-map','0:v:0','-c:v','copy',str(extracted)],check=True)
        self.assertEqual(extracted.read_bytes(),(self.root/'large.jpg').read_bytes())
    def test_failure_and_fake_4k_do_not_replace_cover_or_audio(self):
        before=self.audio.read_bytes()
        self.info([self.thumb('missing',6000,6000),self.thumb('tiny',3840,2160)])
        self.assertEqual(b.improve_artwork(self.audio,self.work,FF),(640,480))
        self.assertEqual(self.audio.read_bytes(),before)
    def test_missing_metadata_preserves_audio(self):
        before=self.audio.read_bytes()
        self.assertEqual(b.improve_artwork(self.audio,self.work,FF),(640,480))
        self.assertEqual(self.audio.read_bytes(),before)
    def test_png_is_converted_to_compatible_jpeg(self):
        self.info([{'url':self.base+'large.png','width':1280,'height':720}])
        self.assertEqual(b.improve_artwork(self.audio,self.work,FF),(1280,720))
        self.assertEqual(b.picture_codec(self.audio),'mjpeg')
        self.assertEqual(self.audio.read_bytes()[:4],b'ID3\x03')
    def test_truncated_http_download_keeps_original(self):
        self.info([{'url':self.base+'truncated.jpg','width':3840,'height':2160}])
        before=self.audio.read_bytes()
        self.assertEqual(b.improve_artwork(self.audio,self.work,FF),(640,480))
        self.assertEqual(self.audio.read_bytes(),before)
    def test_unexpected_candidate_failure_keeps_song(self):
        self.info([self.thumb('large',1280,720)])
        before=self.audio.read_bytes()
        with patch.object(b,'fetch_thumbnail',side_effect=RuntimeError('unexpected')):
            self.assertEqual(b.improve_artwork(self.audio,self.work,FF),(640,480))
        self.assertEqual(self.audio.read_bytes(),before)
    def test_volume_disconnection_is_not_swallowed(self):
        self.info([self.thumb('large',1280,720)])
        with patch.object(b,'fetch_thumbnail',side_effect=lambda *args: setattr(b,'cancelled',True)):
            try:
                with self.assertRaisesRegex(RuntimeError,'cancelada'):
                    b.improve_artwork(self.audio,self.work,FF)
            finally:
                b.cancelled=False

class CandidateTests(unittest.TestCase):
    def test_domains_and_candidate_limit(self):
        self.assertTrue(b.allowed_thumbnail_url('https://i.ytimg.com/vi/abc/maxresdefault.jpg'))
        self.assertFalse(b.allowed_thumbnail_url('https://i.ytimg.com.evil.test/abc.jpg'))
        self.assertFalse(b.allowed_thumbnail_url('http://i.ytimg.com/abc.jpg'))
        self.assertFalse(b.allowed_thumbnail_url('https://i.ytimg.com:444/abc.jpg'))
        thumbs=[{'url':'https://i.ytimg.com/vi/a/%s.jpg'%i,'width':1000+i,'height':1000} for i in range(20)]
        candidates=b.thumbnail_candidates({'thumbnails':thumbs},(640,480))
        self.assertEqual(len(candidates),6)
        self.assertTrue(candidates[0].endswith('/19.jpg'))
    def test_google_original_variant_and_small_rejected(self):
        url='https://lh3.googleusercontent.com/something=w544-h544-l90-rj'
        got=b.thumbnail_candidates({'thumbnails':[{'url':url,'width':544,'height':544}]},(640,640))
        self.assertEqual(got,['https://lh3.googleusercontent.com/something=s0'])
    def test_playlist_keeps_music_and_video_entries(self):
        data={'title':'Mixed','entries':[{'id':'abcdefghijk','title':'Video','ie_key':'Youtube'}, {'id':'12345678901','title':'Song','ie_key':'YoutubeMusic'}]}
        with patch.object(b,'run',return_value=(0,json.dumps(data))):
            title,entries,omitted=b.metadata('yt-dlp','https://youtube.com/playlist?list=abc')
        self.assertEqual(entries,[('abcdefghijk','Video'),('12345678901','Song')])
        self.assertEqual(omitted,0)

if __name__ == '__main__': unittest.main()
