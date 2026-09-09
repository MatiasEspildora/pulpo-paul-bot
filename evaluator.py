import os
import json
import pandas as pd
import glob
import requests
from datetime import datetime, timedelta

# Configuración de Telegram aislada para el Evaluador
_kpi_token_env = os.environ.get("TELEGRAM_KPI_BOT_TOKEN", "").strip()
_main_token_env = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
KPI_TOKEN = _kpi_token_env if _kpi_token_env else _main_token_env

_kpi_chat_env = os.environ.get("TELEGRAM_KPI_CHAT_ID", "").strip()
_main_chat_env = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
KPI_CHAT_ID = _kpi_chat_env if _kpi_chat_env else _main_chat_env

def get_flag(country_name):
    """Carga la bandera leyendo directamente el JSON, sin depender de notifier.py"""
    ruta_banderas = os.path.join("config", "flags.json")
    country_str = str(country_name).strip()
    
    try:
        with open(ruta_banderas, "r", encoding="utf-8") as f:
            flags = json.load(f)
            
        # Intento directo
        if country_str in flags:
            return flags[country_str]
            
        # Mapeo de seguridad para nombres comunes que la API envía distinto
        map_nombres = {
            "South-Korea": "South Korea",
            "Republic of Korea": "South Korea",
            "Korea Republic": "South Korea",
            "El-Salvador": "El Salvador"
        }
        
        nombre_limpio = map_nombres.get(country_str, country_str)
        return flags.get(nombre_limpio, "🏳️")
        
    except Exception:
        return "🏳️"

def enviar_reporte_telegram(mensaje):
    if not KPI_TOKEN or not KPI_CHAT_ID:
        print("⚠️ Faltan credenciales de Telegram para KPIs.")
        return

    lista_chats = [c.strip() for c in KPI_CHAT_ID.split(",") if c.strip()]
    for chat_id in lista_chats:
        try:
            res = requests.post(
                f"https://api.telegram.org/bot{KPI_TOKEN}/sendMessage",
                data={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
            )
            if not res.ok:
                print(f"⚠️ Error Telegram KPI: {res.text}")
        except Exception as e:
            print(f"⚠️ Excepción Telegram KPI: {e}")

def cargar_historico_real():
    all_files = glob.glob("historico_mensual/football/historico_*.csv")
    if not all_files:
        return pd.DataFrame()
    li = [pd.read_csv(f) for f in all_files]
    df_hist = pd.concat(li, axis=0, ignore_index=True)
    df_hist = df_hist.dropna(subset=['HomeTeamId', 'AwayTeamId', 'FTHG', 'FTAG'])
    return df_hist

def evaluar_pick(row, fthg, ftag):
    fthg, ftag = int(fthg), int(ftag)
    tg = fthg + ftag
    sel = str(row['Seleccion']).strip()
    loc = str(row['Local']).strip()
    vis = str(row['Visita']).strip()
    mercado = str(row['Mercado']).strip()

    if mercado == 'Ganador Directo':
        if sel == f"Gana {loc}": return 1 if fthg > ftag else 0
        if sel == f"Gana {vis}": return 1 if ftag > fthg else 0

    elif mercado == 'Doble Oportunidad':
        if sel == '1X': return 1 if fthg >= ftag else 0
        if sel == 'X2': return 1 if ftag >= fthg else 0

    elif mercado == 'Goles':
        if sel == '+1.5 Goles': return 1 if tg > 1.5 else 0
        if sel == '+2.5 Goles': return 1 if tg > 2.5 else 0
        if sel == '-2.5 Goles': return 1 if tg < 2.5 else 0
        if sel == '-3.5 Goles': return 1 if tg < 3.5 else 0

    elif mercado == 'Ambos Anotan':
        if sel == 'Sí': return 1 if fthg > 0 and ftag > 0 else 0
        if sel == 'No': return 1 if fthg == 0 or ftag == 0 else 0

    elif mercado == 'Mega-Misil SGBB':
        partes = sel.split('_')
        if len(partes) >= 2:
            cond_1x2_str, cond_goles_str = partes[0], partes[1]
            cond_1x2 = False
            cond_goles = False

            if cond_1x2_str == "1X": cond_1x2 = (fthg >= ftag)
            elif cond_1x2_str == "X2": cond_1x2 = (ftag >= fthg)
            elif cond_1x2_str == "12": cond_1x2 = (fthg != ftag)
            elif cond_1x2_str == "1": cond_1x2 = (fthg > ftag)
            elif cond_1x2_str == "2": cond_1x2 = (ftag > fthg)
            elif cond_1x2_str == "X": cond_1x2 = (fthg == ftag)
            elif cond_1x2_str == "BTTS": cond_1x2 = (fthg > 0 and ftag > 0)

            if cond_goles_str == "O15": cond_goles = (tg > 1.5)
            elif cond_goles_str == "O25": cond_goles = (tg > 2.5)
            elif cond_goles_str == "O35": cond_goles = (tg > 3.5)
            elif cond_goles_str == "U15": cond_goles = (tg < 1.5)
            elif cond_goles_str == "U25": cond_goles = (tg < 2.5)
            elif cond_goles_str == "U35": cond_goles = (tg < 3.5)
            elif cond_goles_str == "U45": cond_goles = (tg < 4.5)
            elif cond_goles_str == "Yes": cond_goles = (fthg > 0 and ftag > 0)

            return 1 if (cond_1x2 and cond_goles) else 0
        return 0

    return None

def auditar_y_reportar():
    log_path = "kpi/football/predicciones_log.csv"
    if not os.path.exists(log_path):
        print("⚠️ No existe el archivo de proyecciones log.")
        return

    df_log = pd.read_csv(log_path)
    df_log['ResultadoReal'] = df_log['ResultadoReal'].astype(object)
    df_log['Acierto'] = df_log['Acierto'].astype(object)

    df_hist = cargar_historico_real()
    if df_hist.empty:
        print("⚠️ No hay datos históricos para cruzar.")
        return

    pendientes = df_log[df_log['Estado'] == 'PENDIENTE']
    if not pendientes.empty:
        cambios = 0
        for idx, row in pendientes.iterrows():
            mask = (df_hist['HomeTeamId'] == row['HomeTeamId']) & \
                   (df_hist['AwayTeamId'] == row['AwayTeamId']) & \
                   (df_hist['Date'] == row['Fecha'])
            
            match = df_hist[mask]
            if not match.empty:
                fthg, ftag = match.iloc[0]['FTHG'], match.iloc[0]['FTAG']
                if pd.notna(fthg) and pd.notna(ftag):
                    acierto = evaluar_pick(row, fthg, ftag)
                    if acierto is not None:
                        df_log.at[idx, 'Estado'] = 'RESUELTO'
                        df_log.at[idx, 'ResultadoReal'] = f"{int(fthg)}-{int(ftag)}"
                        df_log.at[idx, 'Acierto'] = int(acierto)
                        cambios += 1

        if cambios > 0:
            df_log.to_csv(log_path, index=False, encoding='utf-8')
            print(f"✔️ Se resolvieron {cambios} predicciones nuevas.")

    df_resueltos = df_log[df_log['Estado'] == 'RESUELTO'].copy()
    if df_resueltos.empty: return

    # Extraer el País (Country) del histórico
    df_ligas = df_hist[['HomeTeamId', 'AwayTeamId', 'Date', 'League', 'Country']].drop_duplicates(subset=['HomeTeamId', 'AwayTeamId', 'Date'])
    df_resueltos = df_resueltos.merge(df_ligas, left_on=['HomeTeamId', 'AwayTeamId', 'Fecha'], right_on=['HomeTeamId', 'AwayTeamId', 'Date'], how='left')

    fechas_unicas = sorted(df_resueltos['Fecha'].unique())
    dias_totales = len(fechas_unicas)
    
    fecha_hoy = fechas_unicas[-1]
    fecha_hoy_dt = datetime.strptime(fecha_hoy, "%Y-%m-%d")
    fecha_ayer = (fecha_hoy_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    df_hoy = df_resueltos[df_resueltos['Fecha'] == fecha_hoy]
    df_ayer = df_resueltos[df_resueltos['Fecha'] == fecha_ayer] 
    df_hoy_total_picks = df_log[df_log['Fecha'] == fecha_hoy]

    def metricas(df_subset):
        total = len(df_subset)
        hits = df_subset['Acierto'].sum() if total > 0 else 0
        pct = (hits / total * 100) if total > 0 else 0
        return total, hits, pct

    t_hoy, h_hoy, p_hoy = metricas(df_hoy)
    t_ayer, h_ayer, p_ayer = metricas(df_ayer)
    t_acu, h_acu, p_acu = metricas(df_resueltos)
    
    fallos_acu = t_acu - h_acu
    total_pendientes = len(df_log[df_log['Estado'] == 'PENDIENTE'])

    desglose = [
        ("Mega-Misil SGBB", df_resueltos[df_resueltos['Mercado'] == 'Mega-Misil SGBB']),
        ("Doble Oportunidad", df_resueltos[df_resueltos['Mercado'] == 'Doble Oportunidad']),
        ("Ganador Directo", df_resueltos[df_resueltos['Mercado'] == 'Ganador Directo']),
        ("Goles (Altas/Over)", df_resueltos[(df_resueltos['Mercado'] == 'Goles') & (df_resueltos['Seleccion'].str.contains(r'\+'))]),
        ("Goles (Bajas/Under)", df_resueltos[(df_resueltos['Mercado'] == 'Goles') & (df_resueltos['Seleccion'].str.contains(r'\-'))]),
        ("Ambos Anotan (Sí)", df_resueltos[(df_resueltos['Mercado'] == 'Ambos Anotan') & (df_resueltos['Seleccion'] == 'Sí')]),
        ("Ambos Anotan (No)", df_resueltos[(df_resueltos['Mercado'] == 'Ambos Anotan') & (df_resueltos['Seleccion'] == 'No')])
    ]

    mercados_stats = ""
    for nombre, df_sub in desglose:
        if not df_sub.empty:
            tm, hm, pm = metricas(df_sub)
            icon = "🟢" if pm >= 80 else ("🟡" if pm >= 70 else "🔴")
            mercados_stats += f"・ {nombre}: {pm:.1f}% ({int(hm)} ganadas / {tm} resueltas) {icon}\n"

    ligas_stats = []
    if 'League' in df_resueltos.columns and 'Country' in df_resueltos.columns:
        for (pais, liga), group in df_resueltos.groupby(['Country', 'League']):
            tl = len(group)
            if tl >= 3:
                pl = (group['Acierto'].sum() / tl) * 100
                ligas_stats.append((pais, liga, pl, tl))
        
        ligas_stats.sort(key=lambda x: (x[2], -x[3])) 
        peores_ligas = ligas_stats[:3]

    msg = f"📊 ━━ *REPORTE DE EFECTIVIDAD* ━━ 📊\n\n"
    msg += f"🗓️ *Días Auditados:* {dias_totales}\n"
    msg += f"📅 *Último Lote:* {fecha_hoy}\n\n"
    
    msg += "📈 *RENDIMIENTO DIARIO (HOY vs AYER)*\n"
    msg += f"・ *Hoy:* {p_hoy:.1f}% {'🟢' if p_hoy >= 75 else '🟡'}\n"
    msg += f"  ↳ Apuestas Ganadas: {int(h_hoy)} | Perdidas: {int(t_hoy - h_hoy)}\n"
    msg += f"  ↳ Partidos Aún Pendientes: {len(df_hoy_total_picks) - t_hoy}\n\n"
    
    if not df_ayer.empty:
        tendencia = "🔼" if p_hoy >= p_ayer else "🔽"
        msg += f"・ *Ayer ({fecha_ayer}):* {p_ayer:.1f}% {tendencia}\n"
        msg += f"  ↳ Apuestas Ganadas: {int(h_ayer)} | Perdidas: {int(t_ayer - h_ayer)}\n\n"
    else:
        msg += f"・ *Ayer ({fecha_ayer}):* Sin picks registrados.\n\n"
    
    msg += "📊 *RENDIMIENTO ACUMULADO (HISTÓRICO)*\n"
    msg += f"・ Total Partidos Finalizados: {t_acu}\n"
    msg += f"・ Partidos Aún Pendientes: {total_pendientes}\n"
    msg += f"・ Apuestas Ganadas: {int(h_acu)} | Perdidas: {int(fallos_acu)}\n"
    msg += f"・ *Efectividad Global:* {p_acu:.1f}% 🎯\n\n"
    
    msg += "💣 *DESGLOSE QUIRÚRGICO POR MERCADO*\n"
    msg += mercados_stats + "\n"

    if peores_ligas:
        msg += "⚠️ *RADAR DE LIGAS TÓXICAS (Peor Rendimiento)*\n"
        for pais, liga, pct, tot in peores_ligas:
            bandera = get_flag(pais)
            msg += f"・ {bandera} {pais} - {liga}: {pct:.1f}% (en {tot} picks)\n"
        msg += "\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n✅ _Bender Analytics Engine_"

    enviar_reporte_telegram(msg)

if __name__ == "__main__":
    auditar_y_reportar()
