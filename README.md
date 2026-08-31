## 🐙 Pulpo Paul Bot

Bot automatizado de análisis predictivo de fútbol que procesa resultados de partidos en vivo o finalizados y genera proyecciones estadísticas avanzadas basadas en un histórico de datos particionado.

---

## 🚀 Arquitectura del Proyecto

El sistema está diseñado para operar de forma eficiente y ligera, adaptándose perfectamente a entornos de ejecución continua o integraciones con GitHub sin saturar el control de versiones con archivos masivos e inflados.

```text
pulpo-paul-bot/
│
├── config/                  # Archivos de configuración y mapeo
│   ├── leagues.json         # Ligas activas y traducción API -> Maestro
│   ├── statuses.json        # Estados de fixtures (terminados, próximos)
│   └── team_aliases.json    # Diccionario de nombres oficiales y alias de equipos
│
├── drivers/                 # Controladores por deporte/fuente
│   └── football.py          # Lógica principal de sincronización y análisis de fútbol
│
├── historico_mensual/       # Histórico de partidos fragmentado por mes (YYYY_MM.csv)
│   ├── historico_2026_01.csv
│   └── ...
│
├── logs/                    # Registros de equipos no mapeados o anomalías
├── resultados/              # Directorio de reportes generados
├── api_client.py            # Cliente para consumo de la API de Fútbol
├── analyzer.py              # Motor estadístico y proyecciones (MatchAnalyzer)
├── notifier.py              # Conector de alertas y formateo para Telegram
├── main.py                  # Orquestador principal de ejecución
└── README.md                # Documentación del proyecto
```

---

## 🧠 Motor Analítico y Matemático

El bot no solo promedia goles, sino que cuenta con un motor estadístico ajustado para leer el contexto táctico real del fútbol (`analyzer.py`):

*   **Detección de Eliminatorias (Mata-Mata):** Analiza si el encuentro pertenece a una fase de "ida y vuelta". Revisa automáticamente el historial de los últimos 30 días para determinar quién llega con ventaja y ajusta los Expected Goals (xG) simulando la necesidad de atacar de un equipo o el repliegue defensivo del otro.
*   **Distribución Poisson con Corrección Dixon-Coles:** Calcula matrices de probabilidad de resultados exactos, aplicando un factor de dependencia matemático para corregir la subestimación natural que los modelos estándar hacen sobre los empates (especialmente el 0-0 y el 1-1).

---

## 📊 Gestión del Histórico Modular

Para optimizar el rendimiento y la salud del repositorio en GitHub, los datos históricos no se almacenan en un único archivo gigante:
*   Se dividen por periodos mensuales dentro de la carpeta `historico_mensual/` (ej. `historico_2026_07.csv`).
*   Al iniciar el ciclo, el script consolida todos los archivos en memoria RAM para alimentar al motor analítico sin fricciones.
*   Las actualizaciones diarias impactan exclusivamente en el archivo del mes en curso, manteniendo los commits limpios y legibles.

---

## ⚙️ Requisitos y Dependencias

Asegúrate de tener instalado **Python 3.10** o superior. 

Instalación rápida de dependencias (incluye `scipy` para el motor estadístico):
```bash
pip install pandas requests pytz scipy
```

## 🔑 Variables de Entorno

El bot requiere la configuración de las siguientes variables de entorno para operar y enviar notificaciones:

*   `API_FOOTBALL_KEY`: Llave de acceso a la API externa de fútbol.
*   `TELEGRAM_BOT_TOKEN`: Token del bot de Telegram encargado de despachar los reportes.
*   `TELEGRAM_CHAT_ID`: Identificador del chat o canal de Telegram destino.

## ▶️ Ejecución

Para iniciar un ciclo completo de sincronización de partidos (ayer, hoy y mañana), procesamiento de pronósticos estadísticos y envío de reportes, ejecuta el orquestador principal en tu terminal:
```bash
python main.py
```
