#!/usr/bin/env python3
"""Backend de Música USB. JSON por línea para la interfaz nativa de macOS."""
import argparse
import contextlib
import hashlib
import os
if os.name == 'nt':
    import msvcrt
else:
    import fcntl
import json
import math
import os
import plistlib
import re
import shutil
import signal
import site
import sysconfig
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path.home() / 'Downloads'
MOUNT_ROOT = ROOT
ALLOWED_HOSTS = {'music.youtube.com','www.youtube.com','youtube.com','m.youtube.com','youtu.be'}
MEDIA_EXTS = {'.mp3','.m4a','.aac','.wma','.wav','.flac','.ogg','.opus'}
cancelled = False
initial_dev = None
initial_inode = None
initial_uuid = None
initial_windows_serial = None
output_lock = threading.Lock()
LOCAL_STAGE_ROOT = '/private/tmp' if sys.platform == 'darwin' else tempfile.gettempdir()
# Keep breathing room on the system disk, even with several downloads active.
LOCAL_STAGE_START_FREE = 1024 * 1024 * 1024
LOCAL_STAGE_STOP_FREE = 768 * 1024 * 1024
staging_low = threading.Event()

def check_local_space(start=False):
    threshold = LOCAL_STAGE_START_FREE if start else LOCAL_STAGE_STOP_FREE
    if staging_low.is_set() or shutil.disk_usage(LOCAL_STAGE_ROOT).free < threshold:
        staging_low.set()
        raise RuntimeError('No hay suficiente espacio libre en el equipo para procesar la música. Libera espacio y vuelve a intentarlo; las canciones guardadas se conservan.')

def publish_audio(source, destination):
    """Copy to a hidden file on the target, verify bytes, then publish atomically."""
    partial=destination.parent/('.musica-subaru-'+uuid.uuid4().hex+'.part')
    source_hash=hashlib.sha256()
    try:
        if cancelled: raise RuntimeError('Descarga cancelada.')
        if not volume_present(): raise RuntimeError('El dispositivo de destino dejó de estar disponible.')
        with source.open('rb') as src, partial.open('xb') as dst:
            while True:
                if cancelled: raise RuntimeError('Descarga cancelada.')
                if not volume_present(): raise RuntimeError('El dispositivo de destino dejó de estar disponible.')
                chunk=src.read(1024*1024)
                if not chunk: break
                dst.write(chunk)
                source_hash.update(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        copied_hash=hashlib.sha256()
        with partial.open('rb') as copied:
            while True:
                if cancelled: raise RuntimeError('Descarga cancelada.')
                if not volume_present(): raise RuntimeError('El dispositivo de destino dejó de estar disponible.')
                chunk=copied.read(1024*1024)
                if not chunk: break
                copied_hash.update(chunk)
        if source_hash.digest() != copied_hash.digest():
            raise RuntimeError('La copia en el destino no pasó la comprobación de integridad.')
        if cancelled: raise RuntimeError('Descarga cancelada.')
        if not volume_present(): raise RuntimeError('El dispositivo de destino dejó de estar disponible.')
        validate_volume()
        os.replace(partial,destination)
    finally:
        if volume_present():
            try: partial.unlink()
            except FileNotFoundError: pass

def emit(kind, message, **kwargs):
    with output_lock:
        print(json.dumps({'type': kind, 'message': message, **kwargs}, ensure_ascii=False), flush=True)

def abort(signum, frame):
    global cancelled
    cancelled = True

signal.signal(signal.SIGTERM, abort)
signal.signal(signal.SIGINT, abort)

def binary(name):
    dirs = ['/opt/homebrew/bin','/usr/local/bin','/usr/bin','/bin']
    if os.name == 'nt':
        dirs += [str(Path(sys.executable).parent / 'Scripts'), str(Path(site.getuserbase()) / 'Scripts'), sysconfig.get_path('scripts') or '']
    path = os.pathsep.join(dirs + [os.environ.get('PATH','')])
    return shutil.which(name, path=path)

def windows_volume_serial(root):
    """Return the Windows volume serial to detect a swapped drive letter."""
    if os.name != 'nt': return None
    import ctypes
    from ctypes import wintypes
    serial = wintypes.DWORD()
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    get_volume = kernel32.GetVolumeInformationW
    get_volume.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
    get_volume.restype = wintypes.BOOL
    ok = get_volume(str(root), None, 0, ctypes.byref(serial), None, None, None, 0)
    if not ok:
        raise OSError(ctypes.get_last_error(), 'No se pudo verificar la unidad.')
    return int(serial.value)

def is_removable_volume():
    if os.name != 'nt':
        return str(MOUNT_ROOT).startswith('/Volumes/')
    import ctypes
    from ctypes import wintypes
    get_type=ctypes.WinDLL('kernel32',use_last_error=True).GetDriveTypeW
    get_type.argtypes=[wintypes.LPCWSTR]
    get_type.restype=wintypes.UINT
    return get_type(str(MOUNT_ROOT)) == 2

def validate_volume():
    global initial_dev, initial_inode, initial_uuid, initial_windows_serial
    try:
        if not os.path.ismount(MOUNT_ROOT) or not ROOT.is_dir():
            raise OSError('el volumen o la carpeta ya no están disponibles')
        stat = os.stat(ROOT)
        if os.stat(MOUNT_ROOT).st_dev != stat.st_dev:
            raise OSError('el volumen ha cambiado')
        if not os.access(ROOT, os.W_OK):
            raise OSError('la carpeta no permite escritura')
    except OSError as exc:
        raise RuntimeError('La carpeta de destino no está disponible o no permite escritura.') from exc
    if os.name == 'nt':
        try:
            serial = windows_volume_serial(MOUNT_ROOT)
        except OSError as exc:
            raise RuntimeError('No pude verificar la unidad de destino.') from exc
        if initial_windows_serial is not None and serial != initial_windows_serial:
            raise RuntimeError('La unidad de destino cambió durante la operación.')
        initial_windows_serial = serial
    dev = stat.st_dev
    if initial_dev is not None and dev != initial_dev:
        raise RuntimeError('El dispositivo de destino se desconectó o cambió durante la operación.')
    if initial_inode is not None and stat.st_ino != initial_inode:
        raise RuntimeError('La carpeta de destino cambió durante la operación.')
    if str(MOUNT_ROOT).startswith('/Volumes/'):
        try:
            info=plistlib.loads(subprocess.check_output(
                ['/usr/sbin/diskutil','info','-plist',str(MOUNT_ROOT)],timeout=10))
            found_uuid=(info.get('VolumeUUID') or '').upper()
            if not info.get('WritableVolume'):
                raise ValueError('El volumen no permite escritura')
        except (OSError,subprocess.SubprocessError,ValueError,TypeError) as exc:
            raise RuntimeError('No pude verificar que la unidad externa esté disponible para escritura.') from exc
        if initial_uuid and found_uuid != initial_uuid:
            raise RuntimeError('La unidad de destino cambió durante la operación.')
        if found_uuid:
            initial_uuid=found_uuid
    initial_dev = dev
    initial_inode = stat.st_ino

def set_destination(value):
    """Use exactly the existing, explicitly selected folder and its mount."""
    global ROOT, MOUNT_ROOT, initial_dev, initial_inode, initial_uuid, initial_windows_serial
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise RuntimeError('Elige una carpeta de destino existente en el equipo o en el pendrive.')
    ROOT = path.resolve(strict=True)
    MOUNT_ROOT = ROOT
    while not os.path.ismount(MOUNT_ROOT) and MOUNT_ROOT != MOUNT_ROOT.parent:
        MOUNT_ROOT = MOUNT_ROOT.parent
    initial_dev = None
    initial_inode = None
    initial_uuid = None
    initial_windows_serial = None
    validate_volume()

def select_new_folder(name):
    global ROOT, initial_inode
    if (not name or name in ('.', '..') or name != name.strip(' .')
        or len(name.encode('utf-8')) > 200
        or re.search(r'[\\/:*?"<>|\x00-\x1f]', name)):
        raise RuntimeError('El nombre de la carpeta no es válido. Elige un nombre sencillo sin barras ni caracteres especiales.')
    candidate = ROOT / name
    if candidate.is_symlink():
        raise RuntimeError('La carpeta nueva no puede ser un enlace a otra ubicación.')
    if candidate.exists() and not candidate.is_dir():
        raise RuntimeError('Ya existe un archivo con ese nombre; elige otro nombre de carpeta.')
    if not volume_present():
        raise RuntimeError('El destino se desconectó antes de crear la carpeta.')
    candidate = safe_dir(name)
    if not volume_present():
        raise RuntimeError('El destino cambió durante la creación de la carpeta.')
    ROOT = candidate
    initial_inode = None
    validate_volume()

def volume_present():
    try:
        stat = os.stat(ROOT)
        return (ROOT.is_dir() and os.path.ismount(MOUNT_ROOT)
                and stat.st_dev == initial_dev and stat.st_ino == initial_inode
                and os.stat(MOUNT_ROOT).st_dev == initial_dev
                and (os.name != 'nt' or windows_volume_serial(MOUNT_ROOT) == initial_windows_serial))
    except OSError: return False

def f3_active():
    # F3 is a Unix utility; it is not started by the Windows app.
    if os.name == 'nt': return False
    p = subprocess.run(['/bin/ps','-axo','command'],capture_output=True,text=True,timeout=10)
    for line in p.stdout.splitlines():
        if not re.search(r'(?:^|/)(?:f3read|f3write)(?:\s|$)', line.strip()):
            continue
        try: args = shlex.split(line)
        except ValueError: continue
        for index, value in enumerate(args[1:], start=1):
            if not value.startswith('/'):
                continue
            # `ps` may display an argument with spaces without shell quoting.
            # Reconstruct successive suffixes so a volume named "Mi USB"
            # is checked just as reliably as a single-word mount name.
            for end in range(index + 1, len(args) + 1):
                candidate = ' '.join(args[index:end])
                try:
                    if os.stat(candidate).st_dev == initial_dev: return True
                except OSError: pass
    return False

def single_video_id(parts):
    segments = parts.path.strip('/').split('/')
    if parts.hostname == 'youtu.be' and len(segments) == 1:
        return segments[0]
    if parts.path == '/watch':
        return (parse_qs(parts.query).get('v') or [None])[0]
    if len(segments) == 2 and segments[0] in ('shorts', 'live', 'embed'):
        return segments[1]
    return None

def verify_url(url, mode):
    parts=urlparse(url)
    if parts.scheme != 'https' or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password or parts.port not in (None,443):
        raise ValueError('Introduce un enlace https de YouTube o YouTube Music válido.')
    if mode == 'playlist':
        list_ids = parse_qs(parts.query).get('list') or []
        # YouTube Music also shares playlists as /browse/VL<playlist ID>.
        # Normalize this form for both the extractor and folder identity.
        if not list_ids and parts.hostname == 'music.youtube.com':
            match = re.fullmatch(r'/browse/VL([A-Za-z0-9_-]+)', parts.path)
            if match:
                return 'https://music.youtube.com/playlist?list=' + match.group(1)
        if not list_ids or not re.fullmatch(r'[A-Za-z0-9_-]+', list_ids[0]):
            raise ValueError('Para una playlist necesitas un enlace que contenga la lista de reproducción.')
    if mode == 'single':
        video_id = single_video_id(parts)
        if not video_id or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError('Para una canción, pega el enlace de un video o canción concreto; el enlace de playlist se usa en modo playlist.')
    return url

def safe_name(s, fallback):
    s=unicodedata.normalize('NFKC', str(s or ''))
    s=re.sub(r'[\\/:*?"<>|\x00-\x1f]', ' ',s)
    s=re.sub(r'\s+', ' ',s).strip(' .')[:85].strip(' .')
    return s or fallback

def safe_dir(*parts):
    if initial_dev is not None and not volume_present():
        raise RuntimeError('La carpeta o el dispositivo de destino ya no está disponible.')
    root=ROOT.resolve(strict=True)
    target=root.joinpath(*parts)
    # The volume is FAT32, but resolve existing paths to defend against unexpected links.
    try:
        target.resolve(strict=False).relative_to(root)
        target.mkdir(parents=True,exist_ok=True)
        target.resolve(strict=True).relative_to(root)
    except ValueError as exc: raise RuntimeError('La carpeta de destino está fuera de la ubicación seleccionada.') from exc
    return target

def remove_temp_dir(path):
    """Remove our temporary folder while tolerating macOS AppleDouble races.

    On FAT volumes macOS may delete a ._ companion automatically when its
    associated file is removed. Python 3.9's rmtree can still try to unlink
    that now-missing directory entry. Only ignore this specific benign race;
    propagate all other errors, including permissions and I/O failures.
    """
    def onerror(function, name, exc_info):
        exc = exc_info[1]
        if isinstance(exc, FileNotFoundError):
            return
        raise exc
    shutil.rmtree(path, onerror=onerror)

def run(args, capture=False):
    if cancelled: raise RuntimeError('Descarga cancelada.')
    if not volume_present(): raise RuntimeError('La carpeta o el dispositivo de destino dejó de estar disponible; se detuvo la descarga.')
    check_local_space()
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    child=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,env={**os.environ,'PYTHONUNBUFFERED':'1','PYTHONUTF8':'1'},**options)
    stopped=threading.Event()
    def monitor():
        while not stopped.wait(0.25):
            try:
                check_local_space()
            except (RuntimeError,OSError):
                staging_low.set()
            if cancelled or staging_low.is_set() or not volume_present():
                try:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        os.killpg(child.pid, signal.SIGTERM)
                except (OSError, subprocess.SubprocessError, AttributeError):
                    child.terminate()
                return
    watcher=threading.Thread(target=monitor,daemon=True); watcher.start()
    lines=[]
    try:
        for line in child.stdout:
            if capture: lines.append(line)
            else:
                line=line.strip()
                if line and (line.startswith('ERROR:') or line.startswith('WARNING:')):
                    lines.append(line + '\n')
                    # The caller may recover unavailable YouTube Music IDs via
                    # its official canonical URL; only report an error if that
                    # recovery fails, so a successful retry is not confusing.
                    if not (line.startswith('ERROR:') and youtube_unavailable(line)):
                        emit('detail', line[:500])
        code=child.wait()
    finally:
        stopped.set(); watcher.join(timeout=2); child.stdout.close()
    if cancelled: raise RuntimeError('Descarga cancelada.')
    if not volume_present(): raise RuntimeError('La carpeta o el dispositivo de destino dejó de estar disponible; se detuvo la descarga.')
    check_local_space()
    return code,''.join(lines)

def metadata(yt, url):
    emit('status','Consultando la playlist. Algunas listas privadas o protegidas pueden no estar disponibles.')
    args=[yt,'--ignore-config','--no-cache-dir','--no-warnings','--flat-playlist','--dump-single-json','--playlist-end','10000',url]
    code,out=run(args,capture=True)
    if code: raise RuntimeError('No se pudo leer la playlist. Revisa que el enlace sea público y esté disponible. '+out[-400:])
    try: data=json.loads(out)
    except (ValueError,TypeError): raise RuntimeError('La respuesta de la playlist no se pudo interpretar.')
    entries=data.get('entries') or []
    if len(entries)>9999: raise RuntimeError('La playlist supera el límite de 9.999 archivos del radio.')
    valid=[]
    omitted=0
    for entry in entries:
        if not isinstance(entry,dict):
            omitted+=1
            continue
        vid=entry.get('id','')
        if re.fullmatch(r'[\w-]{11}',str(vid),flags=re.ASCII):
            valid.append((vid,entry.get('title') or ''))
        else:
            omitted+=1
    if not valid: raise RuntimeError('No encontré canciones accesibles en esta playlist.')
    return data.get('title') or 'Playlist', valid, omitted

def count_files(folder):
    return sum(1 for p in folder.iterdir() if p.is_file() and not p.name.startswith('.'))

@contextlib.contextmanager
def destination_lock(folder):
    """Serialize writers to the same folder on Windows and POSIX."""
    if os.name != 'nt':
        try:
            descriptor = os.open(folder, os.O_RDONLY)
        except OSError as exc:
            raise RuntimeError('No pude abrir la carpeta seleccionada para comprobar sus canciones.') from exc
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError) as exc:
                raise RuntimeError('Ya hay otra descarga usando esta carpeta o no se pudo bloquear.') from exc
            yield
        finally:
            os.close(descriptor)
        return
    lock_dir = Path(tempfile.gettempdir()) / 'musicasubaru-locks'
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    name = hashlib.sha256(os.path.normcase(str(folder.resolve())).encode('utf-8')).hexdigest()
    lock_path = lock_dir / (name + '.lock')
    try:
        # Stable lock files must remain: unlinking them could create two locks.
        lock = open(lock_path, 'a+b')
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        if 'lock' in locals(): lock.close()
        raise RuntimeError('Ya hay otra descarga usando esta carpeta o no se pudo bloquear.') from exc
    try:
        yield
    finally:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()

def existing_video_ids(folder):
    """Index exact YouTube IDs within the selected folder, not beyond it."""
    ids = set()
    scope_device = os.stat(folder).st_dev
    def onerror(error):
        raise RuntimeError('No pude revisar una carpeta del destino para detectar canciones repetidas.') from error
    for base, dirs, files in os.walk(folder, followlinks=False, onerror=onerror):
        if cancelled:
            raise RuntimeError('Descarga cancelada.')
        if not volume_present():
            raise RuntimeError('La carpeta o el dispositivo de destino dejó de estar disponible; se detuvo la descarga.')
        safe_dirs = []
        for name in dirs:
            if name.startswith('.'):
                continue
            path = Path(base) / name
            try:
                if not path.is_symlink() and path.stat().st_dev == scope_device:
                    safe_dirs.append(name)
            except FileNotFoundError:
                continue
        dirs[:] = safe_dirs
        for name in files:
            if name.startswith('.'):
                continue
            # Extension matching is case-insensitive; the YouTube ID is not.
            match = re.search(r'(?:\[origen=([A-Za-z0-9_-]{11})\] )?\[([A-Za-z0-9_-]{11})\]\.[mM][pP]3$', name)
            if not match:
                continue
            path = Path(base) / name
            try:
                if not path.is_symlink() and path.is_file() and path.stat().st_dev == scope_device:
                    ids.update(group for group in match.groups() if group)
            except FileNotFoundError:
                continue
    return ids

def count_radio_audio():
    total=0
    for base, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink()]
        total+=sum(1 for name in files if not name.startswith('.') and Path(name).suffix.lower() in MEDIA_EXTS)
    return total

def has_embedded_art(path):
    probe=binary('ffprobe')
    if not probe: return False
    try:
        output=subprocess.check_output([probe,'-v','error','-select_streams','v',
            '-show_entries','stream_disposition=attached_pic','-of','json',str(path)],
            timeout=20,stderr=subprocess.DEVNULL)
        info=json.loads(output)
        return any(s.get('disposition',{}).get('attached_pic') == 1 for s in info.get('streams',[]))
    except (OSError,subprocess.SubprocessError,ValueError,TypeError):
        return False

def picture_dimensions(path, attached=False):
    """Return real pixel dimensions, not the size claimed by metadata."""
    probe=binary('ffprobe')
    if not probe:
        return None
    try:
        output=subprocess.check_output([probe,'-v','error','-select_streams','v',
            '-show_entries','stream=width,height:stream_disposition=attached_pic',
            '-of','json',str(path)],timeout=15,stderr=subprocess.DEVNULL)
        for stream in json.loads(output).get('streams',[]):
            if attached and stream.get('disposition',{}).get('attached_pic') != 1:
                continue
            width=int(stream.get('width') or 0); height=int(stream.get('height') or 0)
            if 0 < width <= 8192 and 0 < height <= 8192:
                return width,height
    except (OSError,subprocess.SubprocessError,ValueError,TypeError):
        pass
    return None

def picture_codec(path):
    probe=binary('ffprobe')
    if not probe:
        return None
    try:
        output=subprocess.check_output([probe,'-v','error','-select_streams','v:0',
            '-show_entries','stream=codec_name','-of','json',str(path)],
            timeout=15,stderr=subprocess.DEVNULL)
        return (json.loads(output).get('streams') or [{}])[0].get('codec_name')
    except (OSError,subprocess.SubprocessError,ValueError,TypeError):
        return None

def allowed_thumbnail_url(url):
    """Permit only HTTPS images from YouTube/Google image hosts."""
    try:
        p=urlparse(url); host=(p.hostname or '').lower()
        domains=('ytimg.com','ggpht.com','googleusercontent.com','gstatic.com')
        return (p.scheme=='https' and not p.username and not p.password
                and p.port in (None,443)
                and any(host==d or host.endswith('.'+d) for d in domains))
    except ValueError:
        return False

def thumbnail_candidates(info, current_size, limit=6):
    """Select a small set likely to improve the embedded cover.

    Actual pixels are always checked after retrieval; a source can claim
    dimensions it does not deliver, or an apparently high-res URL can 404.
    """
    current_area=(current_size[0]*current_size[1]) if current_size else 0
    candidates=[]; seen=set()
    thumbs=info.get('thumbnails') or []
    if not isinstance(thumbs,list):
        thumbs=[]
    for thumb in thumbs:
        if not isinstance(thumb,dict): continue
        url=thumb.get('url')
        if not isinstance(url,str) or not allowed_thumbnail_url(url): continue
        try:
            width=int(thumb.get('width') or 0); height=int(thumb.get('height') or 0)
        except (ValueError,TypeError,OverflowError):
            width=height=0
        area=max(width,0)*max(height,0)
        lower=url.lower()
        # YouTube sometimes omits dimensions for these potentially larger
        # candidates; use this only to prioritize requests, never as a result.
        if not area:
            if 'maxresdefault' in lower: area=1920*1080
            elif 'hq720' in lower: area=1280*720
            elif 'sddefault' in lower: area=640*480
        if area > current_area and url not in seen:
            candidates.append((area,url)); seen.add(url)
        # Google image links with w/h resize parameters may have a larger
        # original. s0 asks the server for its natural size; the result is
        # checked and never enlarged locally.
        host=(urlparse(url).hostname or '').lower()
        if (host.endswith('.ggpht.com') or host.endswith('.googleusercontent.com')):
            original=re.sub(r'=w\d+-h\d+[^/?#]*$', '=s0', url)
            if original!=url and original not in seen and allowed_thumbnail_url(original):
                candidates.append((8192*8192,original)); seen.add(original)
    candidates.sort(key=lambda pair:pair[0],reverse=True)
    return [url for _,url in candidates[:limit]]

class _ThumbnailRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_thumbnail_url(newurl):
            raise urllib.error.HTTPError(newurl,code,'Destino de imagen no permitido',headers,fp)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch_thumbnail(url, path):
    """Bounded network read; candidate is written only in our temp folder."""
    if not allowed_thumbnail_url(url) or cancelled or not volume_present(): return None
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        opener=urllib.request.build_opener(_ThumbnailRedirect())
        with opener.open(req,timeout=6) as response:
            if not allowed_thumbnail_url(response.geturl()): return None
            length=response.headers.get('Content-Length')
            if length and int(length)>12*1024*1024: return None
            chunks=[]; total=0
            while True:
                if cancelled or not volume_present(): return None
                data=response.read(256*1024)
                if not data: break
                total+=len(data)
                if total>12*1024*1024: return None
                chunks.append(data)
        if not chunks or cancelled or not volume_present(): return None
        path.write_bytes(b''.join(chunks))
        dims=picture_dimensions(path)
        return (path,dims) if dims else None
    except Exception:
        # An optional cover must never discard an otherwise good song (e.g.
        # a truncated HTTP response can raise http.client.IncompleteRead).
        return None

def improve_artwork(audio, temp, ffmpeg):
    """Upgrade cover only if a checked candidate has more real pixels.

    The existing audio and artwork stay intact if metadata, downloads, image
    conversion or postprocessing fail. The temporary metadata/images are
    removed with the containing temp directory.
    """
    current=picture_dimensions(audio,attached=True)
    try:
        infofiles=[p for p in temp.glob('*.info.json') if not p.name.startswith('.')]
        if len(infofiles)!=1:
            return current
        with infofiles[0].open(encoding='utf-8') as f:
            info=json.load(f)
        urls=thumbnail_candidates(info,current)
        if not urls: return current
        paths=[temp/('.portada-'+str(i)+'.img') for i in range(len(urls))]
        with ThreadPoolExecutor(max_workers=min(4,len(urls))) as executor:
            futures=[executor.submit(fetch_thumbnail,url,path) for url,path in zip(urls,paths)]
            found=[]
            for future in futures:
                try: found.append(future.result())
                except Exception: pass
        if cancelled: raise RuntimeError('Descarga cancelada.')
        if not volume_present(): raise RuntimeError('La carpeta o el dispositivo de destino dejó de estar disponible; se detuvo la descarga.')
        valid=[item for item in found if item]
        if not valid: return current
        winner=max(valid,key=lambda item:item[1][0]*item[1][1])
        if current and winner[1][0]*winner[1][1] <= current[0]*current[1]:
            return current
        upgraded=temp/'.portada-mejorada.mp3'
        # Preserve JPEG bytes when possible; other image formats need a JPEG
        # conversion for the MP3 album-art tag used by car stereos.
        video_args=['-c:v','copy'] if picture_codec(winner[0])=='mjpeg' else ['-c:v','mjpeg','-q:v','2']
        cmd=[ffmpeg,'-v','error','-y','-i',str(audio),'-i',str(winner[0]),
            '-map','0:a:0','-map','1:v:0','-map_metadata','0','-c:a','copy',
            *video_args,'-disposition:v:0','attached_pic',
            '-id3v2_version','3','-metadata:s:v','title=Album cover',
            '-metadata:s:v','comment=Cover (front)',str(upgraded)]
        code,_=run(cmd)
        actual=picture_dimensions(upgraded,attached=True) if code==0 and upgraded.exists() else None
        if not actual or actual[0]*actual[1] <= (current[0]*current[1] if current else 0):
            return current
        with upgraded.open('rb') as f:
            header=f.read(4)
        if header != b'ID3\x03' or not volume_present() or cancelled:
            return current
        if not validate_audio(upgraded,temp/'duracion.txt'):
            return current
        os.replace(upgraded,audio)
        return actual
    except Exception:
        if cancelled: raise RuntimeError('Descarga cancelada.')
        if not volume_present(): raise RuntimeError('La carpeta o el dispositivo de destino dejó de estar disponible; se detuvo la descarga.')
        check_local_space()
        return current

def validate_audio(path, duration_file):
    """Reject unplayable or suspiciously short outputs before moving them to music."""
    probe=binary('ffprobe')
    if not probe:
        raise RuntimeError('Falta ffprobe para verificar la canción descargada.')
    try:
        output=subprocess.check_output([probe,'-v','error','-select_streams','a:0',
            '-show_entries','stream=codec_name,sample_rate:format=duration',
            '-of','json',str(path)],timeout=30,stderr=subprocess.DEVNULL)
        info=json.loads(output)
        streams=info.get('streams') or []
        duration=float((info.get('format') or {}).get('duration',0))
        if not streams or streams[0].get('codec_name') != 'mp3' or streams[0].get('sample_rate') != '44100' or not math.isfinite(duration) or duration <= 0:
            raise ValueError('formato no válido')
        try:
            expected=float(duration_file.read_text().strip().splitlines()[-1])
        except (OSError,IndexError,ValueError):
            expected=0
        # Metadata can be absent or imprecise; compare only known durations.
        if math.isfinite(expected) and expected > 0 and abs(duration-expected) > max(2.0,expected*0.02):
            raise ValueError(f'duración no coincide ({duration:.1f} s frente a {expected:.1f} s)')
        # Decode the complete audio without creating another file. This catches
        # corrupt frames that a container-duration check alone cannot detect.
        ffmpeg=binary('ffmpeg')
        if not ffmpeg:
            raise ValueError('falta ffmpeg para verificar el audio')
        code,_=run([ffmpeg,'-v','error','-xerror','-i',str(path),'-map','0:a:0','-f','null','-'])
        if code:
            raise ValueError('contiene audio que no se pudo decodificar completamente')
        return True
    except (OSError,subprocess.SubprocessError,ValueError,TypeError,KeyError) as exc:
        emit('detail',f'La comprobación de audio falló: {exc}')
        return False

def playlist_folder(title, playlist_key):
    ending=f' [{playlist_key}]'
    for item in ROOT.iterdir():
        if item.is_dir() and not item.is_symlink() and item.name.endswith(ending):
            return item.name
    return f'{title}{ending}'

def select_single_folder(base):
    if count_files(ROOT) < 200:
        return ROOT
    for i in range(1, 100):
        candidate=safe_dir(f'Parte {i:03d}')
        count=count_files(candidate)
        if count < 200: return candidate
    raise RuntimeError('No hay espacio disponible en las carpetas de canciones.')

def unique_destination(path, video_id):
    """Avoid filesystem name collisions while keeping the exact YouTube ID."""
    if not path.exists() and not path.is_symlink():
        return path
    # FAT and typical macOS volumes are case-insensitive, while YouTube IDs
    # distinguish uppercase from lowercase. Preserve both distinct videos.
    id_suffix = f'[{video_id}]'
    stem = path.stem
    alias = re.search(r'\[origen=[A-Za-z0-9_-]{11}\] '+re.escape(id_suffix)+r'$',stem)
    if alias:
        id_suffix=alias.group(0)
    prefix = stem[:-len(id_suffix)].rstrip() if stem.endswith(id_suffix) else stem
    for number in range(2, 10000):
        candidate = path.with_name(f'{prefix} ({number}) {id_suffix}{path.suffix}')
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise RuntimeError('No se pudo elegir un nombre libre para esta canción.')

def youtube_unavailable(output):
    """Identify explicit access/unavailability errors, never thumbnail warnings."""
    patterns = (
        r'video unavailable', r'video is not available', r'video is unavailable',
        r'private video', r'video is private', r'not available in your country',
        r'content (?:is not|isn\'t) available', r'age[- ]restricted',
        r'members[- ]only', r'sign in to confirm (?:your age|you(?:\'re| are) not a bot)',
    )
    for line in output.splitlines():
        if line.lstrip().lower().startswith('error:'):
            if any(re.search(pattern, line, re.I) for pattern in patterns):
                return True
    return False

def _music_watch_id(url):
    """Only accept a concrete YouTube Music watch URL and a single valid ID."""
    try:
        parsed=urlparse(url)
        if (parsed.scheme!='https' or (parsed.hostname or '').lower()!='music.youtube.com'
            or parsed.port not in (None,443) or parsed.username or parsed.password
            or parsed.path!='/watch'):
            return None
        ids=parse_qs(parsed.query).get('v',[])
        return ids[0] if len(ids)==1 and re.fullmatch(r'[A-Za-z0-9_-]{11}',ids[0]) else None
    except ValueError:
        return None

class _MusicCanonicalParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()!='link': return
        values=dict(attrs)
        if 'canonical' in (values.get('rel') or '').lower().split() and values.get('href'):
            self.links.append(values['href'])

class _MusicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _music_watch_id(newurl):
            raise urllib.error.HTTPError(newurl,code,'Redirección de YouTube Music no permitida',headers,fp)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def music_canonical_id(video_id):
    """Read Music's official canonical URL; never guess a replacement by title.

    YouTube Music sometimes migrates an unavailable recording to a new ID.
    Its canonical link names that replacement even when a normal YouTube page
    or yt-dlp still reports the original ID unavailable.
    """
    if cancelled: raise RuntimeError('Descarga cancelada.')
    if not volume_present(): raise RuntimeError('El dispositivo de destino dejó de estar disponible.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id): return None
    try:
        url='https://music.youtube.com/watch?v='+video_id
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        opener=urllib.request.build_opener(_MusicRedirect())
        with opener.open(req,timeout=8) as response:
            if not _music_watch_id(response.geturl()): return None
            data=response.read(512*1024+1)
        if len(data)>512*1024: return None
        parser=_MusicCanonicalParser(); parser.feed(data.decode('utf-8','replace'))
        ids={_music_watch_id(link) for link in parser.links}
        ids.discard(None)
        # Ignore ambiguous pages rather than guessing which link is correct.
        found=next(iter(ids)) if len(ids)==1 else None
        return found if found and found!=video_id else None
    except Exception:
        # The canonical lookup is optional; broken or partial HTTP responses
        # must not abort an otherwise recoverable playlist.
        return None
    finally:
        if cancelled: raise RuntimeError('Descarga cancelada.')
        if not volume_present(): raise RuntimeError('El dispositivo de destino dejó de estar disponible.')

def execute():
    global cancelled
    ap=argparse.ArgumentParser()
    ap.add_argument('--url',required=True); ap.add_argument('--mode',choices=['single','playlist'],required=True)
    ap.add_argument('--quality',choices=['192','256','320'],default='256')
    ap.add_argument('--destination',required=True)
    ap.add_argument('--new-folder',default=None)
    ap.add_argument('--workers',type=int,choices=[2,4,6],default=4)
    ap.add_argument('--artwork',action='store_true')
    ap.add_argument('--cancel-file',default=None,help=argparse.SUPPRESS)
    a=ap.parse_args()
    # Tk UI requests cancellation by creating a unique local marker.
    if a.cancel_file:
        cancel_path=Path(a.cancel_file)
        def watch_cancel_file():
            global cancelled
            while not cancelled:
                if cancel_path.exists():
                    cancelled=True
                    return
                time.sleep(0.2)
        threading.Thread(target=watch_cancel_file, daemon=True).start()
    a.url=verify_url(a.url,a.mode); set_destination(a.destination)
    # Lock the folder the user selected, before creating an optional child.
    # This prevents two app instances using the same scope from racing.
    scope_root = ROOT
    with destination_lock(scope_root):
        return execute_in_destination(a, scope_root)

def execute_in_destination(a, scope_root):
    global cancelled
    if f3_active(): raise RuntimeError('La prueba F3 de este dispositivo sigue en curso. Espera a que termine antes de descargar música.')
    yt=binary('yt-dlp'); ff=binary('ffmpeg')
    if not yt or not ff: raise RuntimeError('Faltan yt-dlp o ffmpeg. Instala las dependencias para usar la app.')
    emit('status','Revisando canciones existentes en la carpeta elegida…')
    existing=existing_video_ids(scope_root)
    if a.new_folder is not None:
        select_new_folder(a.new_folder)
    omitted=0
    duplicates=0
    if a.mode=='playlist':
        title,entries,omitted=metadata(yt,a.url)
        title=safe_name(title,'Playlist')
        playlist_key=hashlib_short(parse_qs(urlparse(a.url).query)['list'][0])
        playlist_name=playlist_folder(title,playlist_key)
    else:
        entries=[(single_video_id(urlparse(a.url)),'')]; playlist_name='Canciones'
    done=0; skipped=0; failed=0; no_art=0
    # The radio's practical file limit matters for removable media. Avoid
    # recursively scanning unrelated folders on the internal Mac drive.
    audio_count=count_radio_audio() if is_removable_volume() else 0
    commit_lock=threading.Lock()
    if a.mode=='playlist':
        # A repeated song in a list, or an existing copy, is downloaded once.
        unique=[]; seen=set()
        for vid,title in entries:
            if vid not in seen: unique.append((vid,title)); seen.add(vid)
        duplicates=len(entries)-len(unique)
        entries=unique
        if omitted:
            emit('detail',f'{omitted} elemento(s) de la playlist no están disponibles o no se pudieron identificar.')
        if duplicates:
            emit('detail',f'{duplicates} canción(es) repetidas se guardarán una sola vez.')
    total=len(entries)
    emit('status',f'Preparando {total} canción(es), hasta {a.workers} descargas simultáneas.',current=0,total=total)

    def download(index, video_id, title):
        nonlocal audio_count
        if cancelled: raise RuntimeError('Descarga cancelada.')
        if not volume_present(): raise RuntimeError('La carpeta o el dispositivo de destino dejó de estar disponible; se detuvo la descarga.')
        validate_volume()
        if f3_active(): raise RuntimeError('La prueba F3 se inició; la descarga se detuvo.')
        if video_id in existing:
            return 'existing', f'Ya estaba guardada: {title or video_id}', False
        url='https://music.youtube.com/watch?v='+video_id if a.mode=='playlist' else a.url
        resolved_id=video_id
        prefix=f'{index:04d} - ' if a.mode=='playlist' else ''
        check_local_space(start=True)
        tmp=Path(tempfile.mkdtemp(prefix='musica-subaru-',dir=LOCAL_STAGE_ROOT))
        try:
            template=str(tmp/(prefix+'%(title).120B [%(id)s].%(ext)s'))
            duration_file=tmp/'duracion.txt'
            args=[yt,'--ignore-config','--no-cache-dir','--no-playlist','--no-overwrites','--newline','--restrict-filenames','--windows-filenames','--no-mtime','--concurrent-fragments','4','--abort-on-unavailable-fragments','--ffmpeg-location',ff,'-f','bestaudio/best','--extract-audio','--audio-format','mp3','--audio-quality',a.quality+'K','--postprocessor-args','ExtractAudio+ffmpeg_o:-ar 44100 -ac 2 -id3v2_version 3','--print-to-file','after_move:%(duration)s',str(duration_file)]
            audio_args=list(args)
            if a.artwork: args.extend(['--embed-thumbnail','--convert-thumbnails','jpg','--embed-metadata','--write-info-json',
                '--postprocessor-args','Metadata+ffmpeg_o:-id3v2_version 3'])
            args.extend(['--output',template,url])
            code,output=run(args)
            if code and youtube_unavailable(output):
                canonical=music_canonical_id(video_id)
                if canonical:
                    resolved_id=canonical
                    with commit_lock:
                        if video_id in existing or resolved_id in existing:
                            return 'existing', f'Ya estaba guardada: {title or video_id}', False
                    emit('detail',f'YouTube Music actualizó el enlace de {title or "una canción"}; intentando el enlace oficial.')
                    url='https://music.youtube.com/watch?v='+canonical
                    args[-1]=url
                    code,output=run(args)
                if code and youtube_unavailable(output):
                    return 'failed', f'YouTube no permitió descargar {title or "el video"} [{video_id}]. Revisa si el video está disponible y si requiere acceso.', False
            missing_art=bool(a.artwork and re.search(r'(?:warning|error).*thumbnail',output,re.I))
            if code and a.artwork and volume_present() and not cancelled:
                emit('detail',f'No se pudo completar {title or "una canción"} con carátula; reintentando sin carátula.')
                remove_temp_dir(tmp)
                tmp.mkdir()
                code,output=run(audio_args+['--output',template,url])
                if code and youtube_unavailable(output):
                    return 'failed', f'YouTube no permitió descargar {title or "el video"} [{video_id}]. Revisa si el video está disponible y si requiere acceso.', False
                missing_art=True
            # FAT32 stores resource forks as hidden AppleDouble sidecars named
            # ._*.mp3; these are metadata, not downloaded audio files.
            files=[p for p in tmp.glob('*.mp3') if not p.name.startswith('.')] if volume_present() else []
            if code or len(files)!=1:
                return 'failed', f'No se pudo descargar: {title or "la canción"}.',False
            if not validate_audio(files[0],duration_file):
                return 'failed', f'La canción {title or "descargada"} no pasó la comprobación de duración o formato.',False
            if a.artwork:
                actual=improve_artwork(files[0],tmp,ff)
                missing_art=not has_embedded_art(files[0])
                if missing_art:
                    emit('detail',f'No se encontró una carátula incrustada en {title or "la canción"}; se conservará el audio.')
                elif actual:
                    emit('detail',f'Carátula verificada: {actual[0]} × {actual[1]} píxeles.')
            with commit_lock:
                if cancelled: raise RuntimeError('Descarga cancelada.')
                if not volume_present(): raise RuntimeError('La carpeta o el dispositivo de destino dejó de estar disponible; se detuvo la descarga.')
                validate_volume()
                if video_id in existing or resolved_id in existing:
                    return 'existing', f'Ya estaba guardada: {title or video_id}', False
                if is_removable_volume() and audio_count >= 9999: raise RuntimeError('La carpeta seleccionada ya tiene 9.999 archivos de audio; alcanzó el límite del radio.')
                output_name=files[0].name
                if resolved_id!=video_id:
                    suffix=f' [{resolved_id}].mp3'
                    if not output_name.endswith(suffix):
                        raise RuntimeError('No se pudo identificar el archivo de audio recuperado.')
                    output_name=output_name[:-len(suffix)]+f' [origen={video_id}]'+suffix
                if a.mode=='playlist':
                    folder=safe_dir(playlist_name,f'Parte {(index-1)//200+1:03d}')
                    dst=folder/output_name
                    if count_files(folder)>=200:
                        for extra in range(1,100):
                            alternative=safe_dir(playlist_name,f'Parte {(index-1)//200+1:03d} extra {extra:02d}')
                            if count_files(alternative)<200:
                                dst=alternative/output_name; break
                        else: raise RuntimeError('Demasiadas canciones en esta carpeta de playlist.')
                else:
                    folder=select_single_folder(ROOT)
                    dst=folder/output_name
                dst=unique_destination(dst,resolved_id)
                publish_audio(files[0],dst)
                existing.update((video_id,resolved_id))
                audio_count+=1
            return 'saved', f'Guardada: {title or files[0].stem}',missing_art
        finally:
            if tmp.exists(): remove_temp_dir(tmp)

    # Enqueue at most the selected number of transfers so cancellation does not
    # start new work, while all final moves and folder counts stay serialized.
    pending={}; jobs=iter(enumerate(entries,1))
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        def submit_one():
            try: index,(video_id,title)=next(jobs)
            except StopIteration: return False
            pending[pool.submit(download,index,video_id,title)]=index
            return True
        for _ in range(a.workers):
            if not submit_one(): break
        while pending:
            completed,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in completed:
                pending.pop(future)
                try: result,message,missing_art=future.result()
                except Exception:
                    # Stop all child processes through their volume/cancel monitors.
                    cancelled=True
                    raise
                if result == 'saved': done+=1; no_art+=int(missing_art)
                elif result == 'existing': skipped+=1; emit('detail',message)
                else: failed+=1; emit('error',message)
                processed=done+skipped+failed
                emit('status',f'Procesadas {processed} de {total} · {done} nuevas, {skipped} ya estaban, {failed} con error.',current=processed,total=total)
                if not cancelled: submit_one()
    if failed or omitted:
        emit('done',f'Terminó parcialmente: {done} nuevas, {skipped} ya estaban, {failed} fallidas y {omitted} omitidas; {no_art} sin carátula.',success=done,skipped=skipped,failed=failed+omitted)
        return 1
    emit('done',f'Listo: {done} canciones nuevas; {skipped} ya estaban en la carpeta elegida.' + (f' {duplicates} repetidas dentro de la lista se procesaron una sola vez.' if duplicates else '') + (f' {no_art} sin carátula.' if no_art else ''),success=done,skipped=skipped,failed=0)
    return 0

def hashlib_short(value):
    import hashlib
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:8]

if __name__=='__main__':
    try: sys.exit(execute())
    except (RuntimeError,ValueError,OSError,subprocess.SubprocessError) as exc:
        emit('error',str(exc)); sys.exit(1)
