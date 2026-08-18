import os
import json
import glob
import pandas as pd
from analyzer import MatchAnalyzer
import notifier

def re_notificar():
    # 1. Cargamos el caché de los partidos ya procesados (Cero API)
    ruta_cache = os.path.join("resultados", "proyecciones_cache.json")
    
    if not os.path.exists(ruta_cache):
        print("⚠️ No hay caché guardado. Debes ejecutar main.py primero.")
        return
        
    with open(ruta_cache, "r", encoding="utf-8") as f:
        proyecciones_dict = json.load(f)

    # 2. Consolidamos el histórico local en memoria (Cero API)
    archivos_csv = glob.glob("historico_mensual/*.csv")
    if archivos_csv:
        df_historico = pd.concat([pd.read_csv(f) for f in archivos_csv], ignore_index=True)
    else:
        df_historico = pd.DataFrame()

    # 3. Instanciamos tu motor estadístico
    analyzer = MatchAnalyzer(df_historico)

    # 4. Disparamos la interfaz visual de Telegram
    print("🚀 Ejecutando Notificador Offline...")
    notifier.enviar_resumen_mejores_apuestas(proyecciones_dict, "TEST UI", analyzer, is_basket=False)
    print("✅ Notificación enviada con éxito.")

if __name__ == "__main__":
    re_notificar()
