from drivers import football
# Cuando tengas el de tenis listo, simplemente descomentarás la línea de abajo:
# from drivers import tennis 

def main():
    print("--- 🚀 INICIANDO CICLO DE PROCESAMIENTO GLOBAL ---")
    
    # 1. Ejecución del proceso de Fútbol
    try:
        football.run_process()
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
