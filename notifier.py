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

def enviar_mensaje_telegram(mensaje, token_override=None):
    token_activo = token_override or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token_activo and chat_id:
        try:
            res = requests.post(
                f"https://api.telegram.org/bot{token_activo}/sendMessage", 
                data={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
            )
            
            if res.status_code == 429:
                error_data = res.json()
                espera = error_data.get("parameters", {}).get("retry_after", 5)
                print(f"⏳ Límite de Telegram. Esperando {espera} segundos...")
                time.sleep(espera)
                return enviar_mensaje_telegram(mensaje, token_override=token_override)

            if not res.ok:
                print(f"⚠️ Error al enviar a Telegram: {res.text}")
        except Exception as e:
            print(f"⚠️ Excepción al conectar con Telegram: {e}")
    else:
        print("⚠️ Faltan credenciales de Telegram.")

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
# ⚽ NUEVO FORMATO BENDER V3.0 (FÚTBOL)
# ==========================================
def enviar_bloque_reportes(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    tz_chile = pytz.timezone('America/Santiago')
    hora_generacion = datetime.now(tz_chile).strftime("%d/%m/%Y %H:%M")
    
    partidos_validos = []
    
    # 1. Aplanar y filtrar partidos maduros
    for pais, ligas in agrupar_por_pais(proyecciones_dict).items():
        for liga, projs in ligas.items():
            for p in projs:
                s_l = analyzer.get_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_team_stats(p['visita'], p.get('visita_id'))
                if s_l.get('count', 0) >= 3 and s_v.get('count', 0) >= 3:
                    p['liga_nombre'] = liga
                    p['pais_nombre'] = pais
                    p['bandera'] = BANDERAS.get(pais, "🏴")
                    partidos_validos.append(p)
                    
    if not partidos_validos:
        enviar_mensaje_telegram(f"⚠️ No hay partidos con historial maduro para este bloque.", token_override=token_override)
        return

    # 2. Construir Bloques
    bb_list = []
    ganadores = []
    dobles = []
    goles = []

    for p in partidos_validos:
        # Piezas Bet Builder (>80% Titanio)
        if p.get('btts_no', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('btts_no'), 'sel': 'Ambos Anotan (NO)'})
        if p.get('btts', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('btts'), 'sel': 'Ambos Anotan (SÍ)'})
        if p.get('under_3_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('under_3_5'), 'sel': '-3.5 Goles'})
        if p.get('over_1_5', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('over_1_5'), 'sel': '+1.5 Goles'})
        if p.get('prob_over_0_5_ht', 0) > 0.80: bb_list.append({'match': p, 'prob': p.get('prob_over_0_5_ht'), 'sel': '+0.5 Goles HT'})
        
        # Ganadores
        prob_gana = max(p['probs'][0], p['probs'][2])
        sel_gana = p['local'] if p['probs'][0] > p['probs'][2] else p['visita']
        ganadores.append({'match': p, 'prob': prob_gana, 'sel': sel_gana})
        
        # Dobles
        prob_doble = max(p.get('prob_1X', 0), p.get('prob_X2', 0))
        sel_doble = f"1X ({p['local']})" if p.get('prob_1X', 0) > p.get('prob_X2', 0) else f"X2 ({p['visita']})"
        dobles.append({'match': p, 'prob': prob_doble, 'sel': sel_doble})
        
        # Goles
        opciones_goles = [
            {'sel': 'Ambos Anotan', 'prob': p.get('btts', 0)},
            {'sel': '+1.5 Goles', 'prob': p.get('over_1_5', 0)},
            {'sel': '+2.5 Goles', 'prob': p.get('over_2_5', 0)},
            {'sel': '-3.5 Goles', 'prob': p.get('under_3_5', 0)}
        ]
        mejor_gol = max(opciones_goles, key=lambda x: x['prob'])
        goles.append({'match': p, 'prob': mejor_gol['prob'], 'sel': mejor_gol['sel']})

    # Ordenar bloques
    bb_list.sort(key=lambda x: x['prob'], reverse=True)
    ganadores.sort(key=lambda x: x['prob'], reverse=True)
    dobles.sort(key=lambda x: x['prob'], reverse=True)
    goles.sort(key=lambda x: x['prob'], reverse=True)

    # 3. Rastrear partidos seleccionados para La Autopsia (El Filtro de Basura)
    seleccionados = set()
    for item in bb_list: seleccionados.add(id(item['match']))
    for item in ganadores[:5]: seleccionados.add(id(item['match']))
    for item in dobles[:5]: seleccionados.add(id(item['match']))
    for item in goles[:5]: seleccionados.add(id(item['match']))

    # 4. Ensamblar Mensaje V3.0
    msg = f"💎 ━━ *MENÚ ESTRATÉGICO BENDER V3.0* ━━ 💎\n"
    msg += f"📅 _Generado: {hora_generacion}_\n"
    if titulo_bloque: msg += f"📌 _Ventana: {titulo_bloque}_\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    msg += "🧱 *PIEZAS BET BUILDER (Filtro Titanio > 80%)*\n"
    if bb_list:
        # Limitado a 10 para no saturar si es un día muy bueno
        for i, item in enumerate(bb_list[:10], 1):
            m = item['match']
            msg += f"*{i}.* ⚽ {m['bandera']} {m['pais_nombre']} - {m['local']} vs {m['visita']} | 🧩 *{item['sel']}* ({item['prob']:.0%})\n"
    else:
        msg += "_Ninguna variable pura superó el 80% hoy._\n"
    
    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🏆 *TOP 5 - GANADOR DIRECTO*\n"
    for i, item in enumerate(ganadores[:5], 1):
        m = item['match']
        msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']} | 🎯 Gana *{item['sel']}* ({item['prob']:.0%})\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🛡️ *TOP 5 - DOBLE OPORTUNIDAD*\n"
    for i, item in enumerate(dobles[:5], 1):
        m = item['match']
        msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']} | 🛡️ *{item['sel']}* ({item['prob']:.0%})\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🔥 *TOP 5 - MERCADOS DE GOLES*\n"
    for i, item in enumerate(goles[:5], 1):
        m = item['match']
        msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']} | 🔥 *{item['sel']}* ({item['prob']:.0%})\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🩸 *LA AUTOPSIA (Código Fuente)*\n\n"

    autopsia_dict = {}
    for p in partidos_validos:
        if id(p) in seleccionados:
            liga_key = f"{p['bandera']} {p['pais_nombre']} - {p['liga_nombre']}"
            autopsia_dict.setdefault(liga_key, []).append(p)
            
    for liga_key, projs in autopsia_dict.items():
        msg += f"📌 *{liga_key}*\n"
        for p in projs:
            msg += f"⚽ *{p['local']}* vs *{p['visita']}* | 🕒 {p.get('hora', '')}\n"
            msg += f"📊 1X2: L:{p['probs'][0]:.0%} | E:{p['probs'][1]:.0%} | V:{p['probs'][2]:.0%}\n"
            msg += f"🛡️ Doble Op: 1X ({p.get('prob_1X',0):.0%}) | 12 ({p.get('prob_12',0):.0%}) | X2 ({p.get('prob_X2',0):.0%})\n"
            msg += f"🎯 Ambos Anotan: Sí ({p.get('btts',0):.0%}) | No ({p.get('btts_no',0):.0%})\n"
            msg += f"⚽ Bajas/Altas: -2.5 ({p.get('under_2_5',0):.0%}) | -3.5 ({p.get('under_3_5',0):.0%}) | +1.5 ({p.get('over_1_5',0):.0%})\n"
            msg += f"⏱️ +0.5 Goles HT: {p.get('prob_over_0_5_ht',0):.0%}\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n✅ *FIN DEL REPORTE* ✅\n"

    # Enviar mensaje controlando la longitud de Telegram (Max 4096)
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


# ==========================================
# 🏀 LÓGICA PRESERVADA PARA BÁSQUETBOL 
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

    mensaje_resumen = f"💎 ━━ *MENÚ ESTRATÉGICO BASKET: {etiqueta_dia}* ━━ 💎\n"
    mensaje_resumen += f"📅 _Generado: {hora_generacion}_\n"
    mensaje_resumen += "━"*24 + "\n\n"

    basket_lista.sort(key=lambda x: x['prob'], reverse=True)
    for i, item in enumerate(basket_lista[:10], 1):
        p = item['match']
        mensaje_resumen += f"*{i}.* 🏀 {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n"
        mensaje_resumen += f"   🎯 *Pick:* Gana {item['seleccion']} ({item['prob']:.0%}) | 🔥 Pts: `{p.get('puntos_proyectados', 0):.1f}`\n\n"

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

def enviar_bloque_reportes_basket(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    agrupado_por_pais = agrupar_por_pais(proyecciones_dict)
    
    for pais, ligas_del_pais in sorted(agrupado_por_pais.items()):
        bandera = BANDERAS.get(pais, "🏴")
        sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
        
        mensajes_a_enviar = []
        mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo}\n" + "━"*20 + "\n\n"
        
        for liga, proyecciones in sorted(ligas_del_pais.items()):
            top_items = proyecciones
            
            header_liga = f"📌 *{liga} - TOTAL ({len(top_items)})*\n\n"
            
            if len(mensaje_actual) + len(header_liga) > 3800:
                mensaje_actual += "━"*20 + "\n"
                mensajes_a_enviar.append(mensaje_actual)
                mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo} (Cont.)\n" + "━"*20 + "\n\n"
                
            mensaje_actual += header_liga
            
            for p in top_items:
                s_l = analyzer.get_basketball_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_basketball_team_stats(p['visita'], p.get('visita_id'))
                ot_l = analyzer.get_basketball_overtime_stats(p['local'], p.get('local_id'))
                ot_v = analyzer.get_basketball_overtime_stats(p['visita'], p.get('visita_id'))

                bloque_partido = f"📅 `{p.get('fecha_str', '')}` 🕒 `{p['hora']}`\n🏀 *{p['local']}* vs *{p['visita']}*\n"
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
                                        f"  partidos con OT: `{ot_l.get('partidos_ot', 0)}/5` | `{ot_v.get('partidos_ot', 0)}/5`\n"
                                        f"  puntos extra prom: `{ot_l.get('promedio_puntos_ot', 0):.1f}` | `{ot_v.get('promedio_puntos_ot', 0):.1f}`\n\n")
                    else:
                        bloque_partido += "\n"
                else:
                    bloque_partido += "⚠️ *Sin historial suficiente.*\n\n"

                if len(mensaje_actual) + len(bloque_partido) > 3800:
                    mensaje_actual += "━"*20 + "\n"
                    mensajes_a_enviar.append(mensaje_actual)
                    mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo} (Cont.)\n" + "━"*20 + "\n\n"
                    
                mensaje_actual += bloque_partido

        if mensaje_actual:
            mensaje_actual += "━"*20 + "\n"
            mensajes_a_enviar.append(mensaje_actual)
            
        for msg in mensajes_a_enviar:
            enviar_mensaje_telegram(msg, token_override=token_override)
            time.sleep(1.5)

    enviar_resumen_mejores_apuestas_basket(proyecciones_dict, titulo_bloque, analyzer, token_override)
