🐙 Pulpo Paul Bot
Bot automatizado de análisis predictivo de fútbol que procesa resultados de partidos en vivo o finalizados y genera proyecciones estadísticas (probabilidades de victoria, ambos anotan y marcadores probables) basadas en un histórico de datos particionado.

🚀 Arquitectura del Proyecto
El sistema está diseñado para operar de forma eficiente y ligera, adaptándose perfectamente a entornos de ejecución continua o integraciones con GitHub sin saturar el control de versiones con archivos masivos e inflados.

Directorio del proyecto:

config/ - Archivos de configuración y mapeo (leagues.json, statuses.json, team_aliases.json)

drivers/ - Controladores por deporte/fuente (football.py)

historico_mensual/ - Histórico de partidos fragmentado por mes (historico_YYYY_MM.csv)

logs/ - Registros de equipos no mapeados o anomalías

resultados/ - Directorio de reportes generados

api_client.py - Cliente para consumo de la API de Fútbol

analyzer.py - Motor estadístico y proyecciones (MatchAnalyzer)

notifier.py - Conector de alertas y formateo para Telegram

main.py - Orquestador principal de ejecución

README.md - Documentación del proyecto

📊 Gestión del Histórico Modular
Para optimizar el rendimiento y la salud del repositorio en GitHub, los datos históricos no se almacenan en un único archivo gigante:

Se dividen por periodos mensuales dentro de la carpeta historico_mensual/ (ej. historico_2026_07.csv).

Al iniciar el ciclo, el script en main.py consolida todos los archivos en memoria RAM para alimentar al motor analítico sin fricciones.

Las actualizaciones diarias impactan exclusivamente en el archivo del mes en curso, manteniendo los commits limpios y legibles.

⚙️ Requisitos y Dependencias
Asegúrate de tener instalado Python 3.10 o superior. Las librerías principales utilizadas son pandas, requests, pytz y glob.

Instalación rápida: pip install pandas requests pytz

🔑 Variables de Entorno
El bot requiere la configuración de las siguientes variables de entorno para operar:

API_FOOTBALL_KEY - Llave de acceso a la API externa de fútbol.

TELEGRAM_BOT_TOKEN - Token del bot de Telegram encargado de despachar los reportes.

TELEGRAM_CHAT_ID - Identificador del chat o canal de Telegram destino.

▶️ Ejecución
Para iniciar un ciclo completo de sincronización de partidos, procesamiento de pronósticos y envío de reportes, ejecuta en tu terminal:

python main.py
