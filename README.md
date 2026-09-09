## 🐙 Pulpo Paul Bot (V3.5 - Bender Engine)

Bot automatizado de análisis predictivo de fútbol que procesa resultados de partidos en vivo o finalizados, genera proyecciones estadísticas avanzadas basadas en un histórico de datos particionado, y audita su propio rendimiento diario para buscar Valor Esperado Positivo (EV+).

---

## 🚀 Arquitectura del Proyecto (SOLID)

El sistema está diseñado de forma modular, separando estrictamente la estadística matemática pura de la construcción financiera de apuestas, adaptándose perfectamente a entornos de ejecución continua mediante GitHub Actions.

```text
pulpo-paul-bot/
│
├── config/                  # Archivos de configuración y mapeo (ligas, estados, alias)
├── drivers/                 # Controladores de orquestación (ej. football.py)
├── historico_mensual/       # Base de datos particionada por mes (YYYY_MM.csv)
├── kpi/                     # Registros de auditoría (predicciones_log.csv)
│
├── api_client.py            # Cliente para consumo de la API de Fútbol
├── analyzer.py              # 🧠 Motor Estadístico (Poisson, xG, Contexto Táctico)
├── bet_builder.py           # 💣 Motor Financiero (SGBB, Filtro Titanio, Mercados)
├── evaluator.py             # 📊 Auditor de KPIs (Resolución de picks y reportes de efectividad)
├── notifier.py              # Conector de alertas y formateo para Telegram
├── main.py                  # Orquestador principal de ejecución
└── README.md                # Documentación del proyecto
```

---

## 🧠 Motor Analítico y Financiero (Bender Engine)

La lógica predictiva está dividida en dos cerebros para garantizar escalabilidad y precisión:

1. **El Estadístico (`analyzer.py`):** 
   * **Detección de Eliminatorias (Mata-Mata):** Analiza ventajas de ida y vuelta para ajustar los *Expected Goals* (xG) según la necesidad de atacar o defender.
   * **Distribución Poisson Pura:** Calcula matrices de probabilidad matemática sin contaminación comercial, aplicando correcciones para dependencias de empates (Dixon-Coles).
2. **La Licuadora SGBB (`bet_builder.py`):**
   * Recibe la matriz matemática y genera todas las combinaciones comerciales posibles (Ganador, Doble Oportunidad, Goles, BTTS).
   * **Filtro de Titanio:** Ensambla *Same Game Bet Builders* (SGBB) híbridos cruzando variables (ej. Resultado + Goles), y solo aprueba mercados que superen independientemente un umbral de confianza extrema (>80%-85%).

---

## 📊 Módulo de Auditoría Continua (Hermes Conrad)

Pulpo Paul no solo predice, sino que evalúa su propia rentabilidad a largo plazo mediante `evaluator.py`:
* **Trazabilidad PENDIENTE/RESUELTO:** Registra cada pick sugerido y lo cruza con el histórico real al día siguiente.
* **Métricas Quirúrgicas:** Reporta el porcentaje de acierto diario ("Hoy vs Ayer") y el histórico acumulado, desglosando la efectividad exacta por mercado (SGBB, Altas, Bajas, BTTS).
* **Radar de Ligas Tóxicas:** Identifica y expone automáticamente las competiciones con peor rendimiento estadístico para descartarlas de futuras inversiones.

---

## 📊 Gestión del Histórico Modular

Para optimizar el rendimiento y la salud del repositorio en GitHub, los datos históricos no se almacenan en un único archivo gigante:
* Se dividen por periodos mensuales dentro de la carpeta `historico_mensual/` (ej. `historico_2026_07.csv`).
* Al iniciar el ciclo, el script consolida los archivos en memoria RAM para alimentar al motor analítico sin fricciones.
* Las actualizaciones diarias impactan exclusivamente en el archivo del mes en curso, manteniendo los commits limpios.

---

## ⚙️ Requisitos y Dependencias

Asegúrate de tener instalado **Python 3.10** o superior. 

Instalación rápida de dependencias (incluye `scipy` para el motor estadístico):
```bash
pip install pandas requests pytz scipy
```

## 🔑 Variables de Entorno

El bot requiere la configuración de las siguientes variables de entorno (Secrets en GitHub) para operar y despachar reportes:

*   `API_FOOTBALL_KEY`: Llave de acceso a la API externa de fútbol.
*   `TELEGRAM_BOT_TOKEN`: Token del bot principal (Menú Bender).
*   `TELEGRAM_CHAT_ID`: Chat ID destino para los pronósticos.
*   `TELEGRAM_KPI_BOT_TOKEN`: (Opcional) Token del bot secundario para reportes de auditoría.
*   `TELEGRAM_KPI_CHAT_ID`: (Opcional) Chat ID destino para los KPIs diarios.

## ▶️ Ejecución

Para iniciar un ciclo completo (sincronización, auditoría de KPIs de ayer y proyecciones de hoy/mañana), ejecuta:
```bash
python main.py
```
