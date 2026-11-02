import importlib.util, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('backend_dest',Path(__file__).resolve().parent.parent / 'backend.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)

class DestinationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name).resolve(); self.dest=self.base/'seleccionado'; self.dest.mkdir(); b.cancelled=False
 def tearDown(self): self.temp.cleanup()
 def test_mac_selected_folder_is_available(self):
  b.set_destination(str(self.dest)); self.assertEqual(b.ROOT,self.dest); self.assertTrue(b.volume_present()); self.assertEqual(b.MOUNT_ROOT,Path('/'))
 def test_new_folder_and_existing_data_are_preserved(self):
  b.set_destination(str(self.dest)); folder=self.dest/'Favoritas'; folder.mkdir(); (folder/'anterior.txt').write_text('conservar')
  b.select_new_folder('Favoritas'); self.assertEqual(b.ROOT,folder); self.assertTrue(b.volume_present()); self.assertEqual((folder/'anterior.txt').read_text(),'conservar')
 def test_reject_traversal_bad_names_and_symlink(self):
  b.set_destination(str(self.dest)); outside=self.base/'fuera'; outside.mkdir(); (self.dest/'enlace').symlink_to(outside,target_is_directory=True)
  for name in ['..','../fuera','a/b','a\\b',' nombre ','enlace']:
   with self.assertRaises(RuntimeError,msg=name): b.select_new_folder(name)
  self.assertEqual(list(outside.iterdir()),[])
 def test_reject_missing_and_relative_destination(self):
  for value in ['relativa',str(self.base/'no-existe')]:
   with self.assertRaises(RuntimeError): b.set_destination(value)
 def test_replaced_folder_cannot_be_used(self):
  b.set_destination(str(self.dest)); self.dest.rename(self.base/'anterior'); self.dest.mkdir(); self.assertFalse(b.volume_present())
  with self.assertRaises(RuntimeError): b.safe_dir('prohibido')
  self.assertFalse((self.dest/'prohibido').exists())
 def test_mount_removal_is_detected(self):
  b.set_destination(str(self.dest))
  with patch.object(b.os.path,'ismount',return_value=False): self.assertFalse(b.volume_present())
 def test_external_volume_uuid_change_is_rejected(self):
  import plistlib
  b.ROOT=self.dest; b.MOUNT_ROOT=Path('/Volumes/MockDisk'); b.initial_dev=None; b.initial_inode=None; b.initial_uuid=None
  realstat=os.stat
  def fake_stat(path,*args,**kwargs):
   return realstat(self.dest if str(path)=='/Volumes/MockDisk' else path,*args,**kwargs)
  replies=[plistlib.dumps({'VolumeUUID':'AAAA','WritableVolume':True}),plistlib.dumps({'VolumeUUID':'BBBB','WritableVolume':True})]
  with patch.object(b.os.path,'ismount',return_value=True),patch.object(b.os,'stat',side_effect=fake_stat),patch.object(b.subprocess,'check_output',side_effect=replies):
   b.validate_volume()
   with self.assertRaisesRegex(RuntimeError,'unidad de destino cambió'): b.validate_volume()
 def test_f3_on_same_device_is_blocked(self):
  b.set_destination(str(self.dest))
  import subprocess
  output=f'/opt/homebrew/bin/f3read --show-progress=0 {self.dest}\n'
  with patch.object(b.subprocess,'run',return_value=subprocess.CompletedProcess([],0,output,'')):
   self.assertTrue(b.f3_active())
 def test_f3_path_containing_spaces_is_blocked(self):
  named=self.base/'Mi pendrive'; named.mkdir(); b.set_destination(str(named))
  import subprocess
  output=f'/opt/homebrew/bin/f3read --show-progress=0 {named}\n'
  with patch.object(b.subprocess,'run',return_value=subprocess.CompletedProcess([],0,output,'')):
   self.assertTrue(b.f3_active())
 def test_single_saves_inside_selected_or_new_folder(self):
  for folder_name in [None,'Nuevas']:
   b.cancelled=False; self.assertTrue(self.dest.is_dir())
   video_id='ABCDEFGHIJK' if folder_name else 'abcdefghijk'
   argv=['backend.py','--url','https://youtu.be/'+video_id,'--mode','single','--destination',str(self.dest)]
   if folder_name: argv+=['--new-folder',folder_name]
   def fake_run(args,capture=False):
    template=args[args.index('--output')+1]
    path=Path(template.replace('%(title).120B','Tema').replace('%(id)s',video_id).replace('%(ext)s','mp3'))
    path.write_bytes(b'fake-audio'); return 0,''
   with patch.object(sys,'argv',argv),patch.object(b,'f3_active',return_value=False),patch.object(b,'binary',return_value='/fake/tool'),patch.object(b,'run',side_effect=fake_run),patch.object(b,'validate_audio',return_value=True),patch.object(b,'emit'):
    self.assertEqual(b.execute(),0)
   chosen=self.dest/folder_name if folder_name else self.dest
   self.assertEqual(len(list(chosen.glob('*.mp3'))),1)
   self.assertFalse((chosen/'Musica').exists())

if __name__=='__main__': unittest.main()
