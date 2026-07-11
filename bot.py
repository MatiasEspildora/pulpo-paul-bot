import json
import os
from datetime import datetime

# ... (resto de tu código de configuración arriba)

# 4. Configuración para guardar resultados
# Obtenemos la fecha actual para el nombre del archivo
fecha_str = datetime.now().strftime("%Y%m%d")
carpeta = "resultados"
nombre_archivo = f"partidos_{fecha_str}.json"
ruta_completa = os.path.join(carpeta, nombre_archivo)

# Crear la carpeta 'resultados' si no existe
if not os.path.exists(carpeta):
    os.makedirs(carpeta)
    print(f"📁 Carpeta '{carpeta}' creada.")

# Consulta a API-Football
url = f"https://v3.football.api-sports.io/fixtures?date={fecha_hoy}"
headers = {"x-rapidapi-key": API_FOOTBALL_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}

resp = requests.get(url, headers=headers)

if resp.status_code == 200:
    datos = resp.json()
    
    # GUARDAR EL JSON EN LA CARPETA RESULTADOS
    with open(ruta_completa, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=4)
    
    print(f"✅ Archivo guardado en: {ruta_completa}")
    print(f"📈 Total de partidos capturados: {len(datos.get('response', []))}")
else:
    print(f"❌ Error al conectar: {resp.status_code}")
