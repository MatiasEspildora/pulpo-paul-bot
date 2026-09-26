import sys
from drivers import football
from drivers import basketball

# 🚀 Forzar que los prints salgan en tiempo real en los logs de GitHub Actions
sys.stdout.reconfigure(line_buffering=True)

def main():
    print("\n" + "=" * 55)
    print("🚀  INICIANDO CICLO DE PROCESAMIENTO GLOBAL")
    print("=" * 55)
    
    try:
        print("\n⚽ [FOOTBALL] Iniciando procesamiento...")
        # Al no pasar argumentos, football.py utilizará su Carga Híbrida Inteligente optimizada
        football.run_process()
        print("   ↳ ⚽ [FOOTBALL] Finalizado con éxito.")
    except Exception as e:
        print(f"❌ [FOOTBALL] Error crítico: {e}")
    
    try:
        print("\n🏀 [BASKET] Iniciando procesamiento...")
        basketball.run_process()
        print("   ↳ 🏀 [BASKET] Finalizado con éxito.")
    except Exception as e:
        print(f"❌ [BASKET] Error crítico: {e}")
    
    print("\n" + "=" * 55)
    print("✅  CICLO DE EJECUCIÓN GLOBAL FINALIZADO")
    print("=" * 55 + "\n")

if __name__ == "__main__":
    main()
