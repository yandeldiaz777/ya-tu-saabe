# YA TU SAABE!! 🇩🇴 🎵

Una aplicación para guardar como MP3 canciones, videos y playlists de YouTube o YouTube Music en una carpeta del equipo o en un pendrive. Permite elegir la calidad, añadir carátulas cuando estén disponibles y ver el avance. En macOS incluye una mascota y una escena 3D durante la descarga.

**Descarga solo contenido que tengas derecho a guardar y respeta las condiciones del servicio y de los titulares de los derechos.**

## Antes de instalar

- Necesitas conexión a internet y espacio libre para procesar el audio en el equipo.
- **Mac:** macOS 14 o posterior, herramientas de línea de comandos de Xcode y Homebrew.
- **Windows:** Windows 10 u 11, Python con Tkinter y las herramientas indicadas abajo. La versión de Windows es una interfaz independiente: incluye las funciones principales de descarga, pero **no incluye las animaciones 3D** de macOS. Sus adaptaciones se han comprobado con pruebas automatizadas, pero **todavía no se han verificado en un equipo Windows real**.
- La versión de macOS se ha compilado y probado en Mac. Los sistemas y radios pueden comportarse de forma diferente; comprueba los archivos en tu dispositivo.

## Instalar en Mac

1. Si todavía no tienes las herramientas de Xcode, abre **Terminal**, ejecuta el siguiente comando y termina la instalación que aparece en pantalla:

   ```bash
   xcode-select --install
   ```

   Si ya están instaladas, no necesitas volver a instalarlas.

2. Instala [Homebrew](https://brew.sh/) siguiendo sus instrucciones oficiales. Después instala las dependencias:

   ```bash
   brew install yt-dlp ffmpeg deno
   ```

   `ffmpeg` incluye `ffprobe`; Deno ayuda a yt-dlp a procesar contenido de YouTube. Consulta la [guía oficial de yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/Installation) si necesitas actualizarlo.

3. En la página de este repositorio, selecciona **Code → Download ZIP** y descomprime el archivo. También puedes clonarlo con Git si lo prefieres.
4. En Terminal, escribe `cd ` (con un espacio al final), arrastra a la ventana la carpeta que acabas de descomprimir y pulsa **Enter**. Compila la aplicación:

   ```bash
   bash scripts/build-macos.sh
   ```

5. Ábrela con el siguiente comando o desde la carpeta `build` en Finder:

   ```bash
   open 'build/YA TU SAABE!!.app'
   ```

La primera compilación puede tardar unos minutos. Se crea una aplicación local con firma ad hoc; no es un instalador firmado por un desarrollador de Apple ni una descarga notarizada.

## Instalar en Windows

1. Abre **PowerShell** y ejecuta estos comandos, aceptando las indicaciones del instalador cuando aparezcan:

   ```powershell
   winget install --id Python.Python.3.13 -e
   winget install --id yt-dlp.yt-dlp -e
   winget install --id Gyan.FFmpeg -e
   winget install --id DenoLand.Deno -e
   ```

   Si `winget` no está disponible, instala o actualiza [App Installer de Microsoft](https://learn.microsoft.com/windows/package-manager/winget/). Python debe incluir Tkinter; puedes comprobarlo con `py -3 -c "import tkinter; print(tkinter.TkVersion)"`.

2. Cierra y vuelve a abrir PowerShell. Comprueba que están disponibles `py -3 --version`, `yt-dlp --version`, `ffmpeg -version` y `deno --version`. Si Windows todavía no reconoce las herramientas recién instaladas, cierra sesión y vuelve a entrar para actualizar la variable PATH.
3. En la página del repositorio, selecciona **Code → Download ZIP** y descomprime el archivo.
4. Abre la carpeta `windows` y haz doble clic en **Iniciar.bat**. También puedes iniciar la interfaz desde PowerShell situado en la carpeta del proyecto:

   ```powershell
   py -3 windows\windows_ui.py
   ```

## Cómo usarla

1. Conecta el pendrive si quieres guardar la música allí. En **Elegir carpeta**, selecciona una carpeta existente del USB o del equipo. La aplicación muestra el espacio disponible del destino.
2. Opcionalmente, escribe un nombre en el campo de carpeta nueva. Déjalo vacío para usar la carpeta seleccionada. Puedes seleccionar una carpeta que ya existe desde el botón **Elegir carpeta**.
3. Selecciona **Una playlist** para una lista completa o **Una canción** para un enlace individual. Pega el enlace de YouTube o YouTube Music. Los videos incluidos en una playlist se procesan como audio cuando están disponibles.
4. Elige la calidad MP3, la cantidad de descargas simultáneas y si quieres incluir carátulas. Pulsa **Descargar música** y revisa el progreso y los detalles.
5. Al terminar, expulsa el pendrive desde Finder o el Explorador de Windows antes de desconectarlo. Si detienes una descarga, las canciones que ya se guardaron se conservan.

Para retomar una playlist, selecciona **el mismo destino** y pega el mismo enlace. La app compara identificadores de YouTube en los nombres de los MP3 de la carpeta elegida y sus subcarpetas para omitir los que ya están guardados. También conserva los identificadores de origen y destino cuando YouTube Music redirige una canción. No identifica necesariamente duplicados que usen otros identificadores o archivos ajenos sin esos identificadores.

En macOS puedes ocultar o mostrar la animación con la **barra espaciadora** cuando no estés escribiendo en un campo.

## Calidad, compatibilidad y problemas frecuentes

- **Carátulas:** se buscan imágenes disponibles y se elige una resolución superior cuando se puede verificar. No todas las fuentes ofrecen imágenes 4K y algunos radios no muestran carátulas o las reducen.
- **Audio:** el MP3 se genera a 44,1 kHz en estéreo y puede configurarse hasta 320 kbps. La calidad real depende de la fuente. No se puede garantizar compatibilidad con todos los modelos de radio.
- **Video no disponible:** puede estar eliminado, restringido o requerir acceso. Si YouTube Music proporciona una redirección oficial accesible, la aplicación intenta seguirla; no todas las entradas se pueden recuperar.
- **Descarga lenta:** la velocidad depende del servicio, internet, el equipo, el tamaño del audio y la velocidad del pendrive. Procesar varios archivos a la vez puede saturar un equipo o unidad lenta; prueba con menos descargas simultáneas.
- **Falta de espacio:** la app procesa archivos temporales en el equipo antes de copiar el resultado al destino. Libera espacio y vuelve a intentar si aparece un aviso.
- **Radio con límites de archivos:** revisa el manual de tu equipo. La app organiza las listas en carpetas y limita la cantidad de archivos en unidades extraíbles, pero eso no sustituye una prueba con tu radio.
- **Dependencia no encontrada:** comprueba que `yt-dlp`, `ffmpeg`, `ffprobe` y `deno` estén instalados y accesibles en PATH. Actualiza yt-dlp si YouTube cambia su funcionamiento.

La app no formatea ni repara pendrives. Antes de usar uno con un radio, consulta los formatos que acepta ese modelo y conserva una copia de seguridad de tu música.

## Desarrollo

El motor compartido está en `backend.py`; la interfaz de macOS está en `macos/` y la interfaz de Windows en `windows/`. Para ejecutar las pruebas en macOS, con las dependencias instaladas:

```bash
python3 -m unittest discover -s tests
```

Las pruebas que simulan comportamientos específicos de Windows están en `tests/test_windows_port.py` y no reemplazan la validación en un equipo Windows.

## Licencia y créditos

El código del proyecto se publica bajo la [licencia MIT](LICENSE). El mapa utiliza recursos de [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/), de dominio público; consulta [los créditos](assets/Creditos.txt). Las herramientas externas [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org/) y [Deno](https://deno.com/) se instalan por separado y mantienen sus propias licencias. Los símbolos del sistema utilizados en macOS pertenecen a Apple y están sujetos a sus condiciones.
