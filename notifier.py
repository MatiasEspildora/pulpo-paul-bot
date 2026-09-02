import os
import json
import requests
import time
from datetime import datetime, timedelta
import pytz

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def cargar_banderas():
    ruta_flags = os.path.join("config", "flags.json")
    try:
        with open(ruta_flags, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

BANDERAS = cargar_banderas()

def enviar_mensaje_telegram(mensaje, token_override=None, chat_id_especifico=None):
    token_activo = token_override or os.environ.get("TELEGRAM_BOT_TOKEN")
    chats_crudos = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token_activo or not chats_crudos:
        print("⚠️ Faltan credenciales de Telegram.")
        return

    lista_chats = [chat_id_especifico] if chat_id_especifico else [c.strip() for c in chats_crudos.split(",") if c.strip()]

    for chat_id in lista_chats:
        try:
            res = requests.post(
                f"https://api.telegram.org/bot{token_activo}/sendMessage", 
                data={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
            )
            
            if res.status_code == 429:
                error_data = res.json()
                espera = error_data.get("parameters", {}).get("retry_after", 5)
                print(f"⏳ Límite de Telegram para {chat_id}. Esperando {espera} segundos...")
                time.sleep(espera)
                enviar_mensaje_telegram(mensaje, token_override=token_override, chat_id_especifico=chat_id)
                continue

            if not res.ok:
                print(f"⚠️ Error al enviar a Telegram ({chat_id}): {res.text}")
                
        except Exception as e:
            print(f"⚠️ Excepción al conectar con Telegram ({chat_id}): {e}")
        
        if len(lista_chats) > 1:
            time.sleep(0.2)

def agrupar_por_pais(proyecciones_dict):
    agrupado = {}
    for key, proyecciones in proyecciones_dict.items():
        if not proyecciones:
            continue
        
        if isinstance(key, tuple):
            pais, liga = key
        else:
            liga = key
            p_info = proyecciones[0].get('pais', 'World')
            pais = p_info.get('name', 'World') if isinstance(p_info, dict) else (p_info or 'World')
            
        if pais not in agrupado:
            agrupado[pais] = {}
        
        if liga not in agrupado[pais]:
            agrupado[pais][liga] = []
        agrupado[pais][liga].extend(proyecciones)
        
    return agrupado


# ==========================================
# ⚽ FORMATO BENDER V3.0 (FÚTBOL)
# ==========================================
def _procesar_y_enviar_bloque_futbol(proyecciones_dict, titulo_bloque, fecha_bloque, analyzer, token_override=None):
    tz_chile = pytz.timezone('America/Santiago')
    hora_generacion = datetime.now(tz_chile).strftime("%d/%m/%Y %H:%M")
    
    partidos_validos = []
    
    for pais, ligas in agrupar_por_pais(proyecciones_dict).items():
        for liga, projs in ligas.items():
            for p in projs:
                s_l = analyzer.get_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_team_stats(p['visita'], p.get('visita_id'))
                if s_l.get('count', 0) >= 3 and s_v.get('count', 0) >= 3:
                    p['liga_nombre'] = liga
                    p['pais_nombre'] = pais
                    p['bandera'] = BANDERAS.get(pais, "🏴")
                    p['_id_interno'] = f"{p['local_id']}_{p['visita_id']}_{p['fecha_str']}" 
                    partidos_validos.append(p)
                    
    if not partidos_validos:
        return 0

    bb_list = []
    ganadores = []
    dobles = []
    goles = []

    for p in partidos_validos:
        if p.get('btts_no', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('btts_no'), 'sel': 'Ambos Anotan (NO)'})
        if p.get('btts', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('btts'), 'sel': 'Ambos Anotan (SÍ)'})
        if p.get('home_clean_sheet', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('home_clean_sheet'), 'sel': f"Clean Sheet {p['local']}"})
        if p.get('away_clean_sheet', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('away_clean_sheet'), 'sel': f"Clean Sheet {p['visita']}"})
        
        if p.get('under_2_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('under_2_5'), 'sel': '-2.5 Goles'})
        # Aumentamos exigencia del -3.5 a 85% y eliminamos -4.5 y -5.5 para evitar cuotas sin valor
        if p.get('under_3_5', 0) > 0.85: bb_list.append({'match': p, 'prob': p.get('under_3_5'), 'sel': '-3.5 Goles'})
        
        if p.get('over_1_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('over_1_5'), 'sel': '+1.5 Goles'})
        if p.get('over_2_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('over_2_5'), 'sel': '+2.5 Goles'})
        if p.get('over_3_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('over_3_5'), 'sel': '+3.5 Goles'})
        if p.get('over_4_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('over_4_5'), 'sel': '+4.5 Goles'})
        if p.get('over_5_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('over_5_5'), 'sel': '+5.5 Goles'})
        
        if p.get('prob_over_0_5_ht', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('prob_over_0_5_ht'), 'sel': '+0.5 Goles HT'})
        if p.get('prob_under_1_5_ht', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('prob_under_1_5_ht'), 'sel': '-1.5 Goles HT'})
        
        if p.get('home_over_0_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('home_over_0_5'), 'sel': f"{p['local']} +0.5 Goles"})
        if p.get('home_over_1_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('home_over_1_5'), 'sel': f"{p['local']} +1.5 Goles"})
        if p.get('home_over_2_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('home_over_2_5'), 'sel': f"{p['local']} +2.5 Goles"})
        if p.get('away_over_0_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('away_over_0_5'), 'sel': f"{p['visita']} +0.5 Goles"})
        if p.get('away_over_1_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('away_over_1_5'), 'sel': f"{p['visita']} +1.5 Goles"})
        if p.get('away_over_2_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('away_over_2_5'), 'sel': f"{p['visita']} +2.5 Goles"})
        
        prob_gana = max(p['probs'][0], p['probs'][2])
        sel_gana = p['local'] if p['probs'][0] > p['probs'][2] else p['visita']
        ganadores.append({'match': p, 'prob': prob_gana, 'sel': sel_gana})
        
        prob_doble = max(p.get('prob_1X', 0), p.get('prob_X2', 0))
        sel_doble = f"1X ({p['local']})" if p.get('prob_1X', 0) > p.get('prob_X2', 0) else f"X2 ({p['visita']})"
        dobles.append({'match': p, 'prob': prob_doble, 'sel': sel_doble})
        
        opciones_goles = [
            {'sel': 'Ambos Anotan', 'prob': p.get('btts', 0)},
            {'sel': '+1.5 Goles', 'prob': p.get('over_1_5', 0)},
            {'sel': '+2.5 Goles', 'prob': p.get('over_2_5', 0)},
            {'sel': '-3.5 Goles', 'prob': p.get('under_3_5', 0)}
        ]
        mejor_gol = max(opciones_goles, key=lambda x: x['prob'])
        goles.append({'match': p, 'prob': mejor_gol['prob'], 'sel': mejor_gol['sel']})

    bb_list.sort(key=lambda x: x['prob'], reverse=True)
    ganadores.sort(key=lambda x: x['prob'], reverse=True)
    dobles.sort(key=lambda x: x['prob'], reverse=True)
    goles.sort(key=lambda x: x['prob'], reverse=True)

    seleccionados = set()
    for item in bb_list[:15]: seleccionados.add(item['match']['_id_interno'])
    for item in ganadores[:15]: seleccionados.add(item['match']['_id_interno'])
    for item in dobles[:15]: seleccionados.add(item['match']['_id_interno'])
    for item in goles[:15]: seleccionados.add(item['match']['_id_interno'])

    etiqueta_ventana = f" | {titulo_bloque}" if titulo_bloque else ""
    
    msg = f"💎 ━━ *MENÚ BENDER V3.0: {fecha_bloque}{etiqueta_ventana}* ━━ 💎\n"
    msg += f"📅 _Generado: {hora_generacion}_\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    msg += "🧱 *PIEZAS BET BUILDER (Filtro Titanio > 80%)*\n"
    if bb_list:
        for i, item in enumerate(bb_list[:15], 1): 
            m = item['match']
            es_mata_mata = " ⚔️" if m.get('es_eliminatoria') else ""
            msg += f"*{i}.* ⚽ {m['bandera']} {m['pais_nombre']} - {m['local']} vs {m['visita']}{es_mata_mata} | 🧩 *{item['sel']}* ({item['prob']:.0%})\n"
    else:
        msg += "_Ninguna variable pura superó el 80% hoy._\n"
    
    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🏆 *TOP 15 - GANADOR DIRECTO*\n"
    for i, item in enumerate(ganadores[:15], 1):
        m = item['match']
        es_mata_mata = " ⚔️" if m.get('es_eliminatoria') else ""
        msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{es_mata_mata} | 🎯 Gana *{item['sel']}* ({item['prob']:.0%})\n"
        msg += f"   📈 Forma Global: L `{m.get('home_form')}` ({m.get('home_ppg')}p) | V `{m.get('away_form')}` ({m.get('away_ppg')}p)\n"
        msg += f"   🏟️ Casa/Fuera: L `{m.get('home_venue_form')}` ({m.get('home_venue_ppg')}p) | V `{m.get('away_venue_form')}` ({m.get('away_venue_ppg')}p)\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🛡️ *TOP 15 - DOBLE OPORTUNIDAD*\n"
    for i, item in enumerate(dobles[:15], 1):
        m = item['match']
        es_mata_mata = " ⚔️" if m.get('es_eliminatoria') else ""
        msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{es_mata_mata} | 🛡️ *{item['sel']}* ({item['prob']:.0%})\n"
        msg += f"   📈 Forma Global: L `{m.get('home_form')}` ({m.get('home_ppg')}p) | V `{m.get('away_form')}` ({m.get('away_ppg')}p)\n"
        msg += f"   🏟️ Casa/Fuera: L `{m.get('home_venue_form')}` ({m.get('home_venue_ppg')}p) | V `{m.get('away_venue_form')}` ({m.get('away_venue_ppg')}p)\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🔥 *TOP 15 - MERCADOS DE GOLES*\n"
    for i, item in enumerate(goles[:15], 1):
        m = item['match']
        es_mata_mata = " ⚔️" if m.get('es_eliminatoria') else ""
        msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{es_mata_mata} | 🔥 *{item['sel']}* ({item['prob']:.0%})\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🩸 *LA AUTOPSIA (Código Fuente)*\n\n"

    autopsia_dict = {}
    for p in partidos_validos:
        if p['_id_interno'] in seleccionados:
            liga_key = f"{p['bandera']} {p['pais_nombre']} - {p['liga_nombre']}"
            autopsia_dict.setdefault(liga_key, []).append(p)
            
    for liga_key in sorted(autopsia_dict.keys()):
        projs = autopsia_dict[liga_key]
        msg += f"📌 *{liga_key}*\n"
        
        projs.sort(key=lambda x: x.get('hora', '00:00'))
        
        for p in projs:
            s_l = analyzer.get_team_stats(p['local'], p.get('local_id'))
            s_v = analyzer.get_team_stats(p['visita'], p.get('visita_id'))
            
            es_mata_mata = " ⚔️ *[MATA-MATA]*" if p.get('es_eliminatoria') else ""
            
            l_league_str = str(p.get('local_league', ''))[:18]
            v_league_str = str(p.get('visita_league', ''))[:18]
            
            l_tag = f" [{l_league_str}]" if l_league_str else ""
            v_tag = f" [{v_league_str}]" if v_league_str else ""
            
            msg += f"📅 `{p.get('fecha_str', '')}` | 🕒 `{p.get('hora', '')}`{es_mata_mata}\n"
            msg += f"⚽ *{p['local']}*{l_tag} vs *{p['visita']}*{v_tag}\n"
            msg += f"📈 Global: L `{p.get('home_form')}` ({p.get('home_ppg')}p) | V `{p.get('away_form')}` ({p.get('away_ppg')}p)\n"
            msg += f"🏟️ Casa/Fuera: L `{p.get('home_venue_form')}` ({p.get('home_venue_ppg')}p) | V `{p.get('away_venue_form')}` ({p.get('away_venue_ppg')}p)\n"
            msg += f"📊 1X2: L:{p['probs'][0]:.0%} | E:{p['probs'][1]:.0%} | V:{p['probs'][2]:.0%}\n"
            msg += f"🛡️ Doble Op: 1X ({p.get('prob_1X',0):.0%}) | 12 ({p.get('prob_12',0):.0%}) | X2 ({p.get('prob_X2',0):.0%})\n"
            
            msg += f"🎯 Ambos Anotan (BTTS): Sí ({p.get('btts',0):.0%}) | No ({p.get('btts_no',0):.0%})\n"
            msg += f"🧱 Portería a Cero (CS): L ({p.get('home_clean_sheet',0):.0%}) | V ({p.get('away_clean_sheet',0):.0%})\n"
            msg += f"⚽ Bajas: -2.5 ({p.get('under_2_5',0):.0%}) | -3.5 ({p.get('under_3_5',0):.0%}) | -4.5 ({p.get('under_4_5',0):.0%}) | -5.5 ({p.get('under_5_5',0):.0%})\n"
            msg += f"🔥 Altas: +1.5 ({p.get('over_1_5',0):.0%}) | +2.5 ({p.get('over_2_5',0):.0%}) | +3.5 ({p.get('over_3_5',0):.0%}) | +4.5 ({p.get('over_4_5',0):.0%}) | +5.5 ({p.get('over_5_5',0):.0%})\n"
            msg += f"⏱️ +0.5 Goles HT: {p.get('prob_over_0_5_ht',0):.0%}\n"
            
            msg += f"📐 Promedios ({s_l.get('count',0)}p | {s_v.get('count',0)}p):\n"
            msg += f"  ⚽ A favor: {s_l.get('goles_favor',0):.1f} | {s_v.get('goles_favor',0):.1f}\n"
            msg += f"  🛡️ En contra: {s_l.get('goles_contra',0):.1f} | {s_v.get('goles_contra',0):.1f}\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n✅ *FIN DEL REPORTE* ✅\n"

    max_len = 4000
    if len(msg) > max_len:
        parts = msg.split("🩸 *LA AUTOPSIA (Código Fuente)*\n\n")
        if len(parts) == 2:
            enviar_mensaje_telegram(parts[0], token_override=token_override)
            time.sleep(1.5)
            autopsia_text = "🩸 *LA AUTOPSIA (Código Fuente)*\n\n" + parts[1]
            
            if len(autopsia_text) > max_len:
                subparts = autopsia_text.split("📌")
                current_chunk = subparts[0]
                for sp in subparts[1:]:
                    if len(current_chunk) + len("📌" + sp) > max_len:
                        enviar_mensaje_telegram(current_chunk, token_override=token_override)
                        time.sleep(1.5)
                        current_chunk = "📌" + sp
                    else:
                        current_chunk += "📌" + sp
                if current_chunk:
                    enviar_mensaje_telegram(current_chunk, token_override=token_override)
            else:
                enviar_mensaje_telegram(autopsia_text, token_override=token_override)
        else:
            for i in range(0, len(msg), max_len):
                enviar_mensaje_telegram(msg[i:i+max_len], token_override=token_override)
                time.sleep(1.5)
    else:
        enviar_mensaje_telegram(msg, token_override=token_override)
        
    return len(partidos_validos)

def enviar_bloque_reportes(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    agrupado_por_fecha = {}
    for key, projs in proyecciones_dict.items():
        for p in projs:
            fecha = p.get('fecha_str', 'Sin Fecha')
            if fecha not in agrupado_por_fecha:
                agrupado_por_fecha[fecha] = {}
            if key not in agrupado_por_fecha[fecha]:
                agrupado_por_fecha[fecha][key] = []
            agrupado_por_fecha[fecha][key].append(p)
            
    total_validos_global = 0
    fechas_ordenadas = sorted(agrupado_por_fecha.keys())
    
    for fecha in fechas_ordenadas:
        procesados = _procesar_y_enviar_bloque_futbol(agrupado_por_fecha[fecha], titulo_bloque, fecha, analyzer, token_override)
        total_validos_global += (procesados or 0)
        if procesados:
            time.sleep(2) 
            
    if total_validos_global == 0:
        enviar_mensaje_telegram(f"⚠️ No hay partidos con historial maduro para este bloque.", token_override=token_override)


# ==========================================
# 🏀 FORMATO BENDER V3.0 (BÁSQUETBOL)
# ==========================================
def _generar_y_enviar_menu_basket(proyecciones_dict, etiqueta_dia, analyzer, token_override=None):
    basket_lista = []
    
    for pais, ligas in agrupar_por_pais(proyecciones_dict).items():
        for liga, projs in ligas.items():
            for p in projs:
                s_l = analyzer.get_basketball_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_basketball_team_stats(p['visita'], p.get('visita_id'))

                if s_l.get('count', 0) >= 3 and s_v.get('count', 0) >= 3:
                    prob_gana = max(p['prob_home'], p['prob_away'])
                    seleccion = p['local'] if p['prob_home'] > p['prob_away'] else p['visita']
                    basket_lista.append({'match': p, 'prob': prob_gana, 'seleccion': seleccion})
                
    if not basket_lista:
        return False

    tz_chile = pytz.timezone('America/Santiago')
    hora_generacion = datetime.now(tz_chile).strftime("%d/%m/%Y %H:%M")

    mensaje_resumen = f"💎 ━━ *MENÚ BENDER V3.0 BASKET: {etiqueta_dia}* ━━ 💎\n"
    mensaje_resumen += f"📅 _Generado: {hora_generacion}_\n"
    mensaje_resumen += "━"*24 + "\n\n"

    basket_lista.sort(key=lambda x: x['prob'], reverse=True)
    # Aumentado a Top 15
    for i, item in enumerate(basket_lista[:15], 1):
        p = item['match']
        mensaje_resumen += f"*{i}.* 🏀 {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n"
        mensaje_resumen += f"   🎯 *Pick:* Gana {item['seleccion']} ({item['prob']:.0%}) | 🔥 Pts: `{p.get('puntos_proyectados', 0):.1f}`\n"
        mensaje_resumen += f"   📈 Forma Global: L `{p.get('home_form', 'N/A')}` | V `{p.get('away_form', 'N/A')}`\n\n"

    mensaje_resumen += "━"*24 + "\n"
    mensaje_resumen += "✅ *FIN DEL REPORTE* ✅\n"

    enviar_mensaje_telegram(mensaje_resumen, token_override=token_override)
    return True

def enviar_resumen_mejores_apuestas_basket(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    tz_chile = pytz.timezone('America/Santiago')
    hoy_dt = datetime.now(tz_chile)
    hoy_str = hoy_dt.strftime("%Y-%m-%d")
    manana_str = (hoy_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    
    dict_hoy, dict_manana = {}, {}
    
    for key, projs in proyecciones_dict.items():
        for p in projs:
            fecha = p.get('fecha_str', '')
            if fecha == hoy_str: dict_hoy.setdefault(key, []).append(p)
            elif fecha == manana_str: dict_manana.setdefault(key, []).append(p)
                
    enviado_hoy = _generar_y_enviar_menu_basket(dict_hoy, f"HOY ({hoy_str})", analyzer, token_override)
    enviado_manana = _generar_y_enviar_menu_basket(dict_manana, f"MAÑANA ({manana_str})", analyzer, token_override)
    
    if not enviado_hoy and not enviado_manana:
        aviso = "💎 ━━ *MENÚ DE MEJORES PICKS* ━━ 💎\n" + "━"*22 + "\n\n⚠️ _No hay partidos con historial maduro para HOY ni MAÑANA._\n\n" + "━"*22 + "\n✅ *FIN DEL REPORTE* ✅"
        enviar_mensaje_telegram(aviso, token_override=token_override)

def _procesar_y_enviar_autopsia_basket(proyecciones_dict, titulo_bloque, fecha_bloque, analyzer, token_override=None):
    agrupado_por_pais = agrupar_por_pais(proyecciones_dict)
    
    for pais, ligas_del_pais in sorted(agrupado_por_pais.items()):
        bandera = BANDERAS.get(pais, "🏴")
        sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
        
        mensajes_a_enviar = []
        mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo} | 📅 {fecha_bloque}\n" + "━"*20 + "\n\n"
        
        for liga, proyecciones in sorted(ligas_del_pais.items()):
            top_items = proyecciones
            
            header_liga = f"📌 *{liga} - TOTAL ({len(top_items)})*\n\n"
            
            if len(mensaje_actual) + len(header_liga) > 3800:
                mensaje_actual += "━"*20 + "\n"
                mensajes_a_enviar.append(mensaje_actual)
                mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo} | 📅 {fecha_bloque} (Cont.)\n" + "━"*20 + "\n\n"
                
            mensaje_actual += header_liga
            
            for p in top_items:
                s_l = analyzer.get_basketball_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_basketball_team_stats(p['visita'], p.get('visita_id'))
                ot_l = analyzer.get_basketball_overtime_stats(p['local'], p.get('local_id'))
                ot_v = analyzer.get_basketball_overtime_stats(p['visita'], p.get('visita_id'))

                bloque_partido = f"📅 `{p.get('fecha_str', '')}` 🕒 `{p['hora']}`\n🏀 *{p['local']}* vs *{p['visita']}*\n"
                bloque_partido += f"📈 Global: L `{p.get('home_form')}` ({p.get('home_ppg')}p) | V `{p.get('away_form')}` ({p.get('away_ppg')}p)\n"
                bloque_partido += f"🏟️ Casa/Fuera: L `{p.get('home_venue_form')}` ({p.get('home_venue_ppg')}p) | V `{p.get('away_venue_form')}` ({p.get('away_venue_ppg')}p)\n"
                bloque_partido += (f"📊 Victoria Proyectada: L:{p['prob_home']:.0%} | V:{p['prob_away']:.0%}\n"
                                f"🎯 Puntos Proyectados: `{p['puntos_proyectados']:.1f}` pts\n")

                count_l = s_l.get('count', 0) if isinstance(s_l, dict) else 0
                count_v = s_v.get('count', 0) if isinstance(s_v, dict) else 0

                if count_l > 0 and count_v > 0:
                    bloque_partido += (f"📐 *Promedios ({count_l}p | {count_v}p):*\n"
                                    f"  pts a favor: `{s_l.get('puntos_favor', 0):.1f}` | `{s_v.get('puntos_favor', 0):.1f}`\n"
                                    f"  pts en contra: `{s_l.get('puntos_contra', 0):.1f}` | `{s_v.get('puntos_contra', 0):.1f}`\n")

                    if ot_l.get('partidos_ot', 0) > 0 or ot_v.get('partidos_ot', 0) > 0:
                        bloque_partido += (f"⏱️ *Tendencia a Prórroga (OT):*\n"
                                        f"  partidos con OT: `{ot_l.get('partidos_ot', 0)}/5` | `{ot_v.get('partidos_ot', 0)}/15`\n"
                                        f"  puntos extra prom: `{ot_l.get('promedio_puntos_ot', 0):.1f}` | `{ot_v.get('promedio_puntos_ot', 0):.1f}`\n\n")
                    else:
                        bloque_partido += "\n"
                else:
                    bloque_partido += "⚠️ *Sin historial suficiente.*\n\n"

                if len(mensaje_actual) + len(bloque_partido) > 3800:
                    mensaje_actual += "━"*20 + "\n"
                    mensajes_a_enviar.append(mensaje_actual)
                    mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo} | 📅 {fecha_bloque} (Cont.)\n" + "━"*20 + "\n\n"
                    
                mensaje_actual += bloque_partido

        if mensaje_actual:
            mensaje_actual += "━"*20 + "\n"
            mensajes_a_enviar.append(mensaje_actual)
            
        for msg in mensajes_a_enviar:
            enviar_mensaje_telegram(msg, token_override=token_override)
            time.sleep(1.5)

def enviar_bloque_reportes_basket(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    agrupado_por_fecha = {}
    for key, projs in proyecciones_dict.items():
        for p in projs:
            fecha = p.get('fecha_str', 'Sin Fecha')
            if fecha not in agrupado_por_fecha:
                agrupado_por_fecha[fecha] = {}
            if key not in agrupado_por_fecha[fecha]:
                agrupado_por_fecha[fecha][key] = []
            agrupado_por_fecha[fecha][key].append(p)
            
    for fecha in sorted(agrupado_por_fecha.keys()):
        _procesar_y_enviar_autopsia_basket(agrupado_por_fecha[fecha], titulo_bloque, fecha, analyzer, token_override)
        time.sleep(2)
        
    enviar_resumen_mejores_apuestas_basket(proyecciones_dict, titulo_bloque, analyzer, token_override)
