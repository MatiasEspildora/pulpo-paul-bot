import os
import pandas as pd
import glob
import requests
from datetime import datetime, timedelta
import pytz

# Configuración de Telegram (Bot KPIs)
# Si no tienes los tokens del nuevo bot aún, usará los del bot principal como respaldo
KPI_TOKEN = os.environ.get("TELEGRAM_KPI_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
KPI_CHAT_ID = os.environ.get("TELEGRAM_KPI_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")

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
        cond_1x2 = False
        cond_goles = False

        if "1X" in sel: cond_1x2 = (fthg >= ftag)
        elif "X2" in sel: cond_1x2 = (ftag >= fthg)
        elif f"Gana {loc}" in sel: cond_1x2 = (fthg > ftag)
        elif f"Gana {vis}" in sel: cond_1x2 = (ftag > fthg)
        elif "Ambos Anotan (No)" in sel: cond_1x2 = (fthg == 0 or ftag == 0)
        elif "Ambos Anotan" in sel: cond_1x2 = (fthg > 0 and ftag > 0)

        if "Menos 2.5" in sel: cond_goles = (tg < 2.5)
        elif "Menos 3.5" in sel: cond_goles = (tg < 3.5)
        elif "Menos 4.5" in sel: cond_goles = (tg < 4.5)
        elif "Más 1.5" in sel: cond_goles = (tg > 1.5)
        elif "Más 2.5" in sel: cond_goles = (tg > 2.5)

        return 1 if (cond_1x2 and cond_goles) else 0

    return None

def auditar_y_reportar():
    log_path = "kpi/football/predicciones_log.csv"
    if not os.path.exists(log_path):
        print("⚠️ No existe el archivo de proyecciones log.")
        return

    df_log = pd.read_csv(log_path)
    
    # <--- NUEVO: Forzar el tipo de dato a 'object' (acepta texto y números)
    df_log['ResultadoReal'] = df_log['ResultadoReal'].astype(object)
    df_log['Acierto'] = df_log['Acierto'].astype(object)

    df_hist = cargar_historico_real()

    if df_hist.empty:
        print("⚠️ No hay datos históricos para cruzar.")
        return

    pendientes = df_log[df_log['Estado'] == 'PENDIENTE']
    if pendientes.empty:
        print("✔️ No hay partidos pendientes por auditar.")
        return

    cambios = 0
    # 1. Resolver pendientes cruzando con histórico
    for idx, row in pendientes.iterrows():
        # Buscar el partido en el histórico (Filtramos por ID y Fecha)
        mask = (df_hist['HomeTeamId'] == row['HomeTeamId']) & \
               (df_hist['AwayTeamId'] == row['AwayTeamId']) & \
               (df_hist['Date'] == row['Fecha'])
        
        match = df_hist[mask]
        
        if not match.empty:
            fthg = match.iloc[0]['FTHG']
            ftag = match.iloc[0]['FTAG']
            
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
    else:
        print("⏳ Los partidos pendientes aún no han finalizado.")
        return

    # 2. Calcular KPIs
    df_resueltos = df_log[df_log['Estado'] == 'RESUELTO'].copy()
    if df_resueltos.empty: return

    # Tomar la fecha más reciente con partidos resueltos para el "Reporte Diario"
    fecha_reporte = df_resueltos['Fecha'].max()
    df_diario = df_resueltos[df_resueltos['Fecha'] == fecha_reporte]

    def metricas(df_subset):
        total = len(df_subset)
        hits = df_subset['Acierto'].sum()
        pct = (hits / total * 100) if total > 0 else 0
        return total, hits, pct

    # Métricas Globales
    t_dia, h_dia, p_dia = metricas(df_diario)
    t_acu, h_acu, p_acu = metricas(df_resueltos)

    # Métricas por Mercado (Acumulado)
    mercados_stats = ""
    for mercado in ['Mega-Misil SGBB', 'Doble Oportunidad', 'Ganador Directo', 'Goles', 'Ambos Anotan']:
        df_merc = df_resueltos[df_resueltos['Mercado'] == mercado]
        if not df_merc.empty:
            tm, hm, pm = metricas(df_merc)
            icon = "🟢" if pm >= 80 else ("🟡" if pm >= 70 else "🔴")
            mercados_stats += f"・ {mercado}: {pm:.1f}% ({int(hm)}/{tm}) {icon}\n"

    # Generar Mensaje de Telegram
    msg = f"📊 ━━ *REPORTE DE EFECTIVIDAD* ━━ 📊\n\n"
    msg += f"📅 *Fecha Evaluada:* {fecha_reporte}\n\n"
    
    msg += "📈 *RENDIMIENTO DIARIO*\n"
    msg += f"・ Picks Resueltos: {t_dia}\n"
    msg += f"・ Aciertos: {int(h_dia)} | Fallos: {int(t_dia - h_dia)}\n"
    msg += f"・ *Acierto Diario:* {p_dia:.1f}% {'🟢' if p_dia >= 75 else '🟡'}\n\n"
    
    msg += "📊 *RENDIMIENTO ACUMULADO*\n"
    msg += f"・ Total Evaluados: {t_acu}\n"
    msg += f"・ Total Aciertos: {int(h_acu)}\n"
    msg += f"・ *Acierto Histórico:* {p_acu:.1f}% 🎯\n\n"
    
    msg += "💣 *DESGLOSE HISTÓRICO POR MERCADO*\n"
    msg += mercados_stats

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n✅ _Bender Analytics Engine_"

    enviar_reporte_telegram(msg)

if __name__ == "__main__":
    auditar_y_reportar()
