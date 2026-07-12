import pandas as pd
import glob
from drivers import football
from drivers import basketball

# Carga de históricos segmentados por subcarpetas
all_files_fb = glob.glob("historico_mensual/football/historico_*.csv")
li_fb = [pd.read_csv(filename) for filename in all_files_fb]
df_completo_fb = pd.concat(li_fb, axis=0, ignore_index=True) if li_fb else pd.DataFrame()

all_files_bk = glob.glob("historico_mensual/basketball/historico_*.csv")
li_bk = [pd.read_csv(filename) for filename in all_files_bk]
df_completo_bk = pd.concat(li_bk, axis=0, ignore_index=True) if li_bk else pd.DataFrame()

def main():
    print("--- 🚀 INICIANDO CICLO DE PROCESAMIENTO GLOBAL ---")
    
    #try:
    #    print("--- 🚀 INICIANDO CICLO DE PROCESAMIENTO FOOTBALL ---")
    #    football.run_process(df_completo_fb)
    #except Exception as e:
    #    print(f"❌ Error en el proceso de Fútbol: {e}")
        
    try:
        print("--- 🚀 INICIANDO CICLO DE PROCESAMIENTO BASKET ---")
        basketball.run_process(df_completo_bk)
    except Exception as e:
        print(f"❌ Error en el proceso de Basketball: {e}")

    print("✅ Ciclo de ejecución finalizado.")

if __name__ == "__main__":
    main()