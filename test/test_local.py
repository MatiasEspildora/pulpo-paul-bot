import os
from drivers import football
from drivers import basketball

# Configura tus variables de entorno directamente para la prueba
os.environ["API_FOOTBALL_KEY"] = "1e9f054beeb458250c33afa9d461696d"
os.environ["API_BASKETBALL_KEY"] = "1e9f054beeb458250c33afa9d461696d"
os.environ["TELEGRAM_BOT_TOKEN"] = "8459090797:AAGFC4uO7gAi1oglp7uSEcpmWrJKWghl9sQ"
os.environ["TELEGRAM_BOT_TOKEN_BASKET"] = "8426366908:AAFAdJuNDedqLmE9kCCI_g71c7JL-QpZw2g"
os.environ["TELEGRAM_CHAT_ID"] = "6738814628"

if __name__ == "__main__":
    print("\n--- 🧪 INICIANDO TEST LOCAL DE BASKETBALL ---")
    try:
        basketball.run_process()
    except Exception as e:
        import traceback
        traceback.print_exc()