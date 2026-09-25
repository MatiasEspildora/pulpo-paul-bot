import os
import glob
import pandas as pd
import unicodedata

def normalizar_nombre(nombre):
    if not isinstance(nombre, str): return ""
    n = unicodedata.normalize('NFKD', nombre).encode('ASCII', 'ignore').decode('utf-8')
    return n.lower().strip()

def contar_partidos_selecciones():
    ruta_carpeta = "historico_mensual/football"
    archivos = glob.glob(os.path.join(ruta_carpeta, "historico_*.csv"))
    
    nombres_turquia = ["turkey", "turkiye", "turquia"]
    nombres_francia = ["france", "francia"]
    
    partidos_turquia = 0
    partidos_francia = 0

    for archivo in archivos:
        try:
            df = pd.read_csv(archivo)
            for _, row in df.iterrows():
                h_norm = normalizar_nombre(row.get('HomeTeam', ''))
                a_norm = normalizar_nombre(row.get('AwayTeam', ''))
                
                if any(t in h_norm for t in nombres_turquia) or any(t in a_norm for t in nombres_turquia):
                    partidos_turquia += 1
                if any(f in h_norm for f in nombres_francia) or any(f in a_norm for f in nombres_francia):
                    partidos_francia += 1
        except Exception:
            pass

    print(f"📊 Partidos de Turquía encontrados: {partidos_turquia}")
    print(f"📊 Partidos de Francia encontrados: {partidos_francia}")

if __name__ == "__main__":
    contar_partidos_selecciones()
