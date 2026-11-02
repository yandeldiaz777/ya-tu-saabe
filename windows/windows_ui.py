#!/usr/bin/env python3
"""YA TU SAABE!!: interfaz de Windows usando solo la biblioteca estándar."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / 'backend.py'

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('YA TU SAABE!!')
        self.geometry('820x760')
        self.minsize(670, 620)
        self.configure(bg='#19090d')
        self.events = queue.Queue()
        self.proc = None
        self.cancel_path = None
        self.closing = False
        self.destination = tk.StringVar(value=str(Path.home() / 'Music'))
        if not Path(self.destination.get()).is_dir(): self.destination.set(str(Path.home()))
        self.folder = tk.StringVar()
        self.url = tk.StringVar()
        self.mode = tk.StringVar(value='playlist')
        self.quality = tk.StringVar(value='320')
        self.speed = tk.StringVar(value='6')
        self.artwork = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Listo para comenzar')
        self.capacity = tk.StringVar()
        self.progress_text = tk.StringVar(value='')
        self.build()
        self.refresh_capacity()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def build(self):
        bg='#19090d'; fg='#fff3f3'; red='#eb3f50'; card='#2a1219'
        style=ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame',background=bg)
        style.configure('TLabel',background=bg,foreground=fg,font=('Segoe UI',10))
        style.configure('Title.TLabel',background=bg,foreground=fg,font=('Segoe UI',22,'bold'))
        style.configure('Small.TLabel',background=bg,foreground='#d5b8bf',font=('Segoe UI',9))
        style.configure('TButton',font=('Segoe UI',10),padding=7)
        style.configure('Accent.TButton',font=('Segoe UI',11,'bold'),padding=10,background=red,foreground='white')
        style.map('Accent.TButton',background=[('disabled','#72303a'),('active','#ff5b69')])
        style.configure('TCheckbutton',background=bg,foreground=fg,font=('Segoe UI',10))
        style.configure('TRadiobutton',background=bg,foreground=fg,font=('Segoe UI',10))
        style.configure('Red.Horizontal.TProgressbar',background=red,troughcolor=card)
        box=ttk.Frame(self,padding=22); box.pack(fill='both',expand=True)
        ttk.Label(box,text='YA TU SAABE!! 🇩🇴',style='Small.TLabel').pack(anchor='w')
        ttk.Label(box,text='Tu música, lista para el camino.',style='Title.TLabel').pack(anchor='w',pady=(2,14))
        ttk.Label(box,text='GUARDAR EN',style='Small.TLabel').pack(anchor='w')
        dest=ttk.Frame(box); dest.pack(fill='x',pady=(2,2))
        ttk.Entry(dest,textvariable=self.destination,state='readonly').pack(side='left',fill='x',expand=True)
        self.choose=ttk.Button(dest,text='Elegir carpeta…',command=self.choose_destination); self.choose.pack(side='left',padx=(8,0))
        ttk.Label(box,textvariable=self.capacity,style='Small.TLabel').pack(anchor='w',pady=(0,8))
        self.folder_entry=ttk.Entry(box,textvariable=self.folder); self.folder_entry.pack(fill='x')
        ttk.Label(box,text='Carpeta nueva opcional: escribe su nombre arriba o deja el campo vacío.',style='Small.TLabel').pack(anchor='w',pady=(2,10))
        ttk.Label(box,text='¿Qué quieres descargar?').pack(anchor='w')
        modes=ttk.Frame(box); modes.pack(fill='x')
        self.playlist=ttk.Radiobutton(modes,text='Una playlist',variable=self.mode,value='playlist'); self.playlist.pack(side='left',padx=(0,20))
        self.single=ttk.Radiobutton(modes,text='Una canción o video',variable=self.mode,value='single'); self.single.pack(side='left')
        ttk.Label(box,text='Pega el enlace de YouTube o YouTube Music').pack(anchor='w',pady=(12,2))
        self.url_entry=ttk.Entry(box,textvariable=self.url); self.url_entry.pack(fill='x')
        options=ttk.Frame(box); options.pack(fill='x',pady=(12,6))
        ttk.Label(options,text='MP3:').pack(side='left')
        self.quality_box=ttk.Combobox(options,textvariable=self.quality,values=['320','256','192'],state='readonly',width=5); self.quality_box.pack(side='left',padx=(4,12))
        ttk.Label(options,text='kbps    Descargas simultáneas:').pack(side='left')
        self.speed_box=ttk.Combobox(options,textvariable=self.speed,values=['6','4','2'],state='readonly',width=4); self.speed_box.pack(side='left',padx=4)
        self.art=ttk.Checkbutton(box,text='Incluir carátula en cada canción',variable=self.artwork); self.art.pack(anchor='w')
        ttk.Label(box,text='La calidad final depende del audio y de la imagen disponibles.',style='Small.TLabel').pack(anchor='w',pady=(2,8))
        controls=ttk.Frame(box); controls.pack(fill='x',pady=(0,10))
        self.start_button=ttk.Button(controls,text='Descargar música',style='Accent.TButton',command=self.start); self.start_button.pack(side='left')
        self.stop_button=ttk.Button(controls,text='Detener',command=self.stop,state='disabled'); self.stop_button.pack(side='left',padx=8)
        ttk.Label(box,textvariable=self.status,wraplength=760).pack(anchor='w')
        self.bar=ttk.Progressbar(box,orient='horizontal',mode='determinate',style='Red.Horizontal.TProgressbar'); self.bar.pack(fill='x',pady=(5,0))
        ttk.Label(box,textvariable=self.progress_text,style='Small.TLabel').pack(anchor='w')
        self.log=tk.Text(box,height=7,wrap='word',bg=card,fg=fg,insertbackground=fg,relief='flat',font=('Segoe UI',9),state='disabled')
        self.log.pack(fill='both',expand=True,pady=(8,2))
        ttk.Label(box,text='Descarga solo contenido que tengas permiso para guardar.',style='Small.TLabel').pack(anchor='w')

    def refresh_capacity(self):
        try:
            used=shutil.disk_usage(self.destination.get())
            self.capacity.set(f'{used.free / 1e9:.1f} GB libres de {used.total / 1e9:.1f} GB')
        except OSError:
            self.capacity.set('La carpeta no está disponible.')

    def choose_destination(self):
        selected=filedialog.askdirectory(title='Elige una carpeta del PC o pendrive',initialdir=self.destination.get(),mustexist=True)
        if selected:
            self.destination.set(selected)
            self.refresh_capacity()

    def append(self, text):
        self.log.configure(state='normal')
        self.log.insert('end',text+'\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def set_running(self, running):
        for w in (self.choose,self.playlist,self.single,self.art,self.url_entry,self.folder_entry):
            w.configure(state='disabled' if running else 'normal')
        for w in (self.quality_box,self.speed_box): w.configure(state='disabled' if running else 'readonly')
        self.start_button.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running else 'disabled')

    def start(self):
        if self.proc: return
        url=self.url.get().strip()
        if not url:
            messagebox.showerror('Falta el enlace','Pega el enlace de la playlist o del video.'); return
        if not Path(self.destination.get()).is_dir():
            messagebox.showerror('Destino no disponible','Elige una carpeta disponible.'); return
        self.cancel_path=Path(tempfile.gettempdir()) / ('musica-subaru-cancel-'+uuid.uuid4().hex)
        args=[sys.executable,'-u',str(BACKEND),'--url',url,'--mode',self.mode.get(),
              '--destination',self.destination.get(),'--quality',self.quality.get(),
              '--workers',self.speed.get(),'--cancel-file',str(self.cancel_path)]
        if self.folder.get().strip(): args += ['--new-folder',self.folder.get().strip()]
        if self.artwork.get(): args += ['--artwork']
        env=dict(os.environ,PYTHONUTF8='1',PYTHONUNBUFFERED='1')
        kwargs={'creationflags': subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        try:
            self.proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env,**kwargs)
        except OSError as exc:
            messagebox.showerror('No se pudo iniciar',str(exc)); self.proc=None; return
        self.bar['value']=0; self.progress_text.set(''); self.status.set('Preparando descarga…'); self.set_running(True)
        self.append('Iniciando descarga…')
        threading.Thread(target=self.read_output,args=(self.proc,),daemon=True).start()

    def read_output(self, process):
        for line in process.stdout:
            try: self.events.put(('event',json.loads(line)))
            except json.JSONDecodeError: self.events.put(('text',line.rstrip()))
        self.events.put(('exit',process.wait()))

    def stop(self):
        if self.proc and self.cancel_path:
            try:
                self.cancel_path.touch(exist_ok=True)
                self.status.set('Deteniendo la descarga…')
                self.stop_button.configure(state='disabled')
            except OSError as exc: messagebox.showerror('No se pudo detener',str(exc))

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='event':
                    message=value.get('message','')
                    typ=value.get('type')
                    if message: self.append(message)
                    if typ in ('status','done','error'): self.status.set(message)
                    if value.get('total'):
                        count=value.get('current',0); total=value['total']
                        self.bar['value']=100*count/total
                        self.progress_text.set(f'{count} de {total} canciones procesadas')
                elif kind=='text' and value: self.append(value)
                elif kind=='exit':
                    if self.cancel_path:
                        try: self.cancel_path.unlink(missing_ok=True)
                        except OSError: pass
                    self.proc=None; self.cancel_path=None; self.set_running(False); self.refresh_capacity()
                    if value != 0 and 'Deteniendo' in self.status.get(): self.status.set('Descarga detenida. Se conservaron las canciones guardadas.')
                    if self.closing: self.destroy(); return
        except queue.Empty: pass
        self.after(100,self.poll)

    def close(self):
        if self.proc:
            if not messagebox.askyesno('Descarga en curso','¿Detener la descarga y cerrar? Las canciones ya guardadas se conservan.'): return
            self.closing=True; self.stop()
        else: self.destroy()

if __name__=='__main__':
    App().mainloop()
