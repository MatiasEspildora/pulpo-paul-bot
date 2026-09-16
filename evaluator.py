import os
import json
import pandas as pd

def cargar_historico_real():
    """Carga y unifica todos los archivos CSV mensuales del histórico real."""
    carpeta_historico = "historico_mensual"
    if not os.path.exists(carpeta_historico):
        return pd.DataFrame()

    archivos = [os.path.join(carpeta_historico, f) for f in os.listdir(carpeta_historico) if f.endswith('.csv')]
    if not archivos:
        return pd.DataFrame()

    dfs = [pd.read_csv(f) for f in archivos]
    df_total = pd.concat(dfs, ignore_index=True)
    return df_total

def evaluar_pick(row, fthg, ftag):
    fthg, ftag = int(fthg), int(ftag)
    tg = fthg + ftag
    sel = str(row['Seleccion']).strip()
    sel_lower = sel.lower()
    loc = str(row['Local']).strip().lower()
    vis = str(row['Visita']).strip().lower()
    mercado = str(row['Mercado']).strip()

    if mercado == 'Ganador Directo':
        if loc in sel_lower: return 1 if fthg > ftag else 0
        if vis in sel_lower: return 1 if ftag > fthg else 0

    elif mercado == 'Doble Oportunidad':
        if '1x' in sel_lower: return 1 if fthg >= ftag else 0
        if 'x2' in sel_lower: return 1 if ftag >= fthg else 0

    elif mercado == 'Goles':
        if '+1.5' in sel_lower: return 1 if tg > 1.5 else 0
        if '+2.5' in sel_lower: return 1 if tg > 2.5 else 0
        if '-2.5' in sel_lower: return 1 if tg < 2.5 else 0
        if '-3.5' in sel_lower: return 1 if tg < 3.5 else 0

    elif mercado == 'Ambos Anotan':
        if 'sí' in sel_lower or 'si' in sel_lower: return 1 if fthg > 0 and ftag > 0 else 0
        if 'no' in sel_lower: return 1 if fthg == 0 or ftag == 0 else 0

    elif mercado == 'Mega-Misil SGBB':
        cond_1x2 = False
        cond_goles = False

        if "1x" in sel_lower: cond_1x2 = (fthg >= ftag)
        elif "x2" in sel_lower: cond_1x2 = (ftag >= fthg)
        elif loc in sel_lower: cond_1x2 = (fthg > ftag)
        elif vis in sel_lower: cond_1x2 = (ftag > fthg)
        else: cond_1x2 = True 

        if "menos" in sel_lower or "under" in sel_lower or "-" in sel_lower:
            if "2.5" in sel_lower: cond_goles = (tg < 2.5)
            elif "3.5" in sel_lower: cond_goles = (tg < 3.5)
            elif "4.5" in sel_lower: cond_goles = (tg < 4.5)
        elif "más" in sel_lower or "mas" in sel_lower or "over" in sel_lower or "+" in sel_lower:
            if "1.5" in sel_lower: cond_goles = (tg > 1.5)
            elif "2.5" in sel_lower: cond_goles = (tg > 2.5)
        else: cond_goles = True

        return 1 if (cond_1x2 and cond_goles) else 0

    return None

def auditar_y_reportar():
    log_path = "kpi/football/predicciones_log.csv"
    if not os.path.exists(log_path):
        print("⚠️ No existe el archivo de proyecciones log.")
        return None

    df_log = pd.read_csv(log_path)
    
    # Forzar tipo de dato a object para evitar errores con strings
    df_log['ResultadoReal'] = df_log['ResultadoReal'].astype(object)
    df_log['Acierto'] = df_log['Acierto'].astype(object)

    df_hist = cargar_historico_real()
    if df_hist.empty:
        print("⚠️ No hay datos históricos para cruzar.")
        return None

    # Mapeo rápido de resultados reales desde el histórico
    partidos_dict = {}
    for _, row in df_hist.iterrows():
        key = (str(row['Date']).strip(), str(row['HomeTeam']).strip(), str(row['AwayTeam']).strip())
        partidos_dict[key] = (row['FTHG'], row['FTAG'])

    # Actualizar pendientes
    pendientes = df_log[df_log['Estado'] == 'PENDIENTE']
    for idx, row in pendientes.iterrows():
        key = (str(row['Fecha']).strip(), str(row['Local']).strip(), str(row['Visita']).strip())
        if key in partidos_dict:
            fthg, ftag = partidos_dict[key]
            res_str = f"{fthg}-{ftag}"
            acierto = evaluar_pick(row, fthg, ftag)
            
            if acierto is not None:
                df_log.at[idx, 'ResultadoReal'] = res_str
                df_log.at[idx, 'Acierto'] = acierto
                df_log.at[idx, 'Estado'] = 'RESUELTO'

    df_log.to_csv(log_path, index=False)

    # --- GENERACIÓN DE KPIs Y REPORTE ---
    df_resueltos = df_log[df_log['Estado'] == 'RESUELTO'].copy()
    if df_resueltos.empty:
        print("✔️ No hay partidos resueltos para auditar en este momento.")
        return None

    fechas_unicas = sorted(df_resueltos['Fecha'].unique())
    dias_auditados = len(fechas_unicas)
    ultimo_dia = fechas_unicas[-1] if fechas_unicas else "N/A"
    penultimo_dia = fechas_unicas[-2] if len(fechas_unicas) > 1 else None

    # Métricas de Hoy (Último Lote)
    df_hoy = df_resueltos[df_resueltos['Fecha'] == ultimo_dia]
    total_hoy = len(df_log[df_log['Fecha'] == ultimo_dia])
    ganadas_hoy = len(df_hoy[df_hoy['Acierto'] == 1])
    perdidas_hoy = len(df_hoy[df_hoy['Acierto'] == 0])
    pendientes_hoy = total_hoy - (ganadas_hoy + perdidas_hoy)
    efectividad_hoy = (ganadas_hoy / len(df_hoy) * 100) if len(df_hoy) > 0 else 0.0

    # Métricas de Ayer (Lote Anterior)
    efectividad_ayer_str = "N/A"
    if penultimo_dia:
        df_ayer = df_resueltos[df_resueltos['Fecha'] == penultimo_dia]
        total_ayer = len(df_log[df_log['Fecha'] == penultimo_dia])
        ganadas_ayer = len(df_ayer[df_ayer['Acierto'] == 1])
        perdidas_ayer = len(df_ayer[df_ayer['Acierto'] == 0])
        pendientes_ayer = total_ayer - (ganadas_ayer + perdidas_ayer)
        efectiv_ayer = (ganadas_ayer / len(df_ayer) * 100) if len(df_ayer) > 0 else 0.0
        
        icono_ayer = "🟢" if efectiv_ayer >= 70 else ("🟡" if efectiv_ayer >= 50 else "🔴")
        efectividad_ayer_str = f"{efectiv_ayer:.1f}% {icono_ayer} ↳ Total Pronósticos: {total_ayer} ↳ ✅ Ganadas: {ganadas_ayer} | ❌ Perdidas: {perdidas_ayer} | ⏳ Pendientes: {pendientes_ayer}"

    # Métricas Acumuladas
    total_pronosticos_gen = len(df_log)
    total_resueltos_gen = len(df_resueltos)
    total_ganadas_gen = len(df_resueltos[df_resueltos['Acierto'] == 1])
    total_perdidas_gen = len(df_resueltos[df_resueltos['Acierto'] == 0])
    total_pendientes_gen = total_pronosticos_gen - total_resueltos_gen
    efectividad_global = (total_ganadas_gen / total_resueltos_gen * 100) if total_resueltos_gen > 0 else 0.0

    # Desglose por Mercado
    mercados = df_resueltos['Mercado'].unique()
    desglose_txt = ""
    for m in mercados:
        df_m = df_resueltos[df_resueltos['Mercado'] == m]
        gan_m = len(df_m[df_m['Acierto'] == 1])
        tot_m = len(df_m)
        ef_m = (gan_m / tot_m * 100) if tot_m > 0 else 0.0
        icon_m = "🟢" if ef_m >= 75 else ("🟡" if ef_m >= 65 else "🔴")
        desglose_txt += f"・ {m}: {ef_m:.1f}% ({gan_m} ganadas / {tot_m} resueltas) {icon_m} "

    # Radar de Ligas Tóxicas y Auto-Blacklist Dinámico
    ligas_toxicas = []
    if 'Liga' in df_resueltos.columns:
        df_ligas = df_resueltos.groupby('Liga').agg(
            ganadas=('Acierto', lambda x: (x == 1).sum()),
            total=('Acierto', 'count')
        ).reset_index()
        
        df_ligas['efectividad'] = df_ligas['ganadas'] / df_ligas['total'] * 100
        # Filtrar ligas con al menos 3 picks y efectividad menor al 40%
        toxicas = df_ligas[(df_ligas['total'] >= 3) & (df_ligas['efectividad'] < 40)].sort_values(by='efectividad')
        
        radar_txt = ""
        for _, l_row in toxicas.iterrows():
            liga_nombre = l_row['Liga']
            ligas_toxicas.append(liga_nombre)
            radar_txt += f"・ 🌍 {liga_nombre}: {l_row['efectividad']:.1f}% (en {l_row['total']} picks) "

        if not radar_txt:
            radar_txt = "・ Sin ligas tóxicas detectadas en este ciclo 🟢"
    else:
        radar_txt = "・ Columna 'Liga' no disponible en el log."

    # Guardar Auto-Blacklist en config/blacklist.json de forma dinámica
    os.makedirs("config", exist_ok=True)
    blacklist_path = "config/blacklist.json"
    with open(blacklist_path, "w", encoding="utf-8") as f:
        json.dump({"ligas_prohibidas": ligas_toxicas}, f, ensure_ascii=False, indent=4)

    # Construcción del Reporte Final para Telegram
    icono_hoy = "🟢" if efectividad_hoy >= 70 else ("🟡" if efectividad_hoy >= 50 else "🔴")
    
    reporte = (
        f"📊 ━━ REPORTE DE EFECTIVIDAD ━━ 📊\n"
        f"🗓️ Días Auditados: {dias_auditados} 📅 Último Lote: {ultimo_dia}\n\n"
        f"📈 RENDIMIENTO DIARIO (HOY vs AYER)\n"
        f"・ Hoy: {efectividad_hoy:.1f}% {icono_hoy}\n"
        f"  ↳ Total Pronósticos: {total_hoy}\n"
        f"  ↳ ✅ Ganadas: {ganadas_hoy} | ❌ Perdidas: {perdidas_hoy} | ⏳ Pendientes: {pendientes_hoy}\n"
        f"・ Ayer ({penultimo_dia if penultimo_dia else 'N/A'}): {efectividad_ayer_str}\n\n"
        f"📊 RENDIMIENTO ACUMULADO (HISTÓRICO)\n"
        f"・ Total Pronósticos: {total_pronosticos_gen}\n"
        f"・ ✅ Ganadas: {total_ganadas_gen} | ❌ Perdidas: {total_perdidas_gen} | ⏳ Pendientes: {total_pendientes_gen}\n"
        f"・ Efectividad Global: {efectividad_global:.1f}% 🎯\n\n"
        f"💣 DESGLOSE QUIRÚRGICO POR MERCADO\n{desglose_txt}\n"
        f"⚠️ RADAR DE LIGAS TÓXICAS (Auto-Blacklist Actualizado)\n{radar_txt}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Bender Analytics Engine"
    )

    return reporte
