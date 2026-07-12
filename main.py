import pandas as pd
import glob
from drivers import football
# Cuando tengas el de tenis listo, simplemente descomentarás la línea de abajo:
# from drivers import tennis 

# Carga todos los archivos CSV de la carpeta al inicio
all_files = glob.glob("historico_mensual/historico_*.csv")
li = [pd.read_csv(filename) for filename in all_files]
df_completo = pd.concat(li, axis=0, ignore_index=True)
# Ahora tienes tu dataframe maestro consolidado en RAM para analizar


def main():
    print("--- 🚀 INICIANDO CICLO DE PROCESAMIENTO GLOBAL ---")
    
    # 1. Ejecución del proceso de Fútbol
    try:
        football.run_process(df_completo)
    except Exception as e:
        print(f"❌ Error en el proceso de Fútbol: {e}")
        
    # 2. Aquí ejecutaremos el tenis más adelante
    # try:
    #     tennis.run_process()
    # except Exception as e:
    #     print(f"❌ Error en el proceso de Tenis: {e}")

    print("✅ Ciclo de ejecución finalizado.")

if __name__ == "__main__":
    main()