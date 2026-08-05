import PyInstaller.__main__
import os

# Definimos las rutas
entry_point = 'src/backend/mqtt_client.py'
project_name = 'RRDOCS_Recorder'

PyInstaller.__main__.run([
    entry_point,
    '--name=%s' % project_name,
    '--onefile',           # Empaqueta todo en un solo .exe
    '--windowed',          # Que no abra consola al ejecutar (opcional)
    '--add-data=src;src',  # Incluimos toda nuestra lógica
    '--add-data=config.json;.', # Incluimos la configuración
    '--clean',
])