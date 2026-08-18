import os
import json
import requests
import time

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

def enviar_resumen_mejores_apuestas(proyecciones_dict, titulo_bloque, analyzer, token_override=None, is_basket=False):
    todas_las_proyecciones = []
    
    for pais, ligas in agrupar_por_pais(proyecciones_dict).items():
        for liga, projs in ligas.items():
            for p in projs:
                
                if is_basket:
                    s_l = analyzer.get_basketball_team_stats(p['local'], p.get('local_id'))
                    s_v = analyzer.get_basketball_team_stats(p['visita'], p.get('visita_id'))
                else:
                    s_l = analyzer.get_team_stats(p['local'], p.get('local_id'))
                    s_v = analyzer.get_team_stats(p['visita'], p.get('visita_id'))

                count_l = s_l.get('count', 0)
                count_v = s_v.get('count', 0)

                # Filtro de madurez estadística (mínimo 3 partidos)
                if count_l >= 3 and count_v >= 3:
                    p['liga_nombre'] = liga
                    p['pais_nombre'] = pais
                    
                    if is_basket:
                        mercados = [
                            {'tipo': 'Gana Partido', 'seleccion': p['local'], 'prob': p['prob_home']},
                            {'tipo': 'Gana Partido', 'seleccion': p['visita'], 'prob': p['prob_away']}
                        ]
                    else:
                        # 💡 El Notificador ahora es un cliente limpio que solo lee las llaves del diccionario
                        prob_L = p['probs'][0]
                        prob_V = p['probs'][2]
                        
                        mercados = [
                            {'tipo': 'Gana Partido', 'seleccion': p['local'], 'prob': prob_L},
                            {'tipo': 'Gana Partido', 'seleccion': p['visita'], 'prob': prob_V},
                            {'tipo': 'Goles', 'seleccion': 'Ambos Anotan (Sí)', 'prob': p.get('btts', 0)},
                            {'tipo': 'Goles', 'seleccion': '+1.5 Goles', 'prob': p.get('over_1_5', 0)},
                            {'tipo': 'Goles', 'seleccion': '+2.5 Goles', 'prob': p.get('over_2_5', 0)},
                            {'tipo': 'Doble Oportunidad', 'seleccion': f"{p['local']} o Empate", 'prob': p.get('prob_1X', 0)},
                            {'tipo': 'Doble Oportunidad', 'seleccion': f"{p['visita']} o Empate", 'prob': p.get('prob_X2', 0)},
                            {'tipo': 'Sin Empate (DNB)', 'seleccion': p['local'], 'prob': p.get('prob_DNB_L', 0)},
                            {'tipo': 'Sin Empate (DNB)', 'seleccion': p['visita'], 'prob': p.get('prob_DNB_V', 0)}
                        ]
                    
                    mejor_mercado = max(mercados, key=lambda x: x['prob'])
                    
                    p['mejor_mercado_tipo'] = mejor_mercado['tipo']
                    p['mejor_mercado_seleccion'] = mejor_mercado['seleccion']
                    p['mejor_mercado_prob'] = mejor_mercado['prob']
                    
                    todas_las_proyecciones.append(p)
                
    if not todas_las_proyecciones:
        aviso = f"💎 *MENÚ DE MEJORES PICKS* 💎\n" + "━"*20 + "\n\n⚠️ _Hoy no hay partidos con historial maduro para generar proyecciones seguras._"
        enviar_mensaje_telegram(aviso, token_override=token_override)
        return

    sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
    mensaje_resumen = f"💎 *MENÚ ESTRATÉGICO DE APUESTAS{sufijo}* 💎\n" + "━"*20 + "\n\n"

    if is_basket:
        todas_las_proyecciones.sort(key=lambda x: x.get('mejor_mercado_prob', 0), reverse=True)
        top_10 = todas_las_proyecciones[:10]
        for i, p in enumerate(top_10, 1):
            prob = p.get('mejor_mercado_prob', 0)
            mensaje_resumen += f"*{i}.* 🏀 {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n"
            mensaje_resumen += f"   🎯 *Pick:* {p.get('mejor_mercado_seleccion', '')} ({prob:.0%}) | 🔥 Pts: `{p.get('puntos_proyectados', 0):.1f}`\n\n"
            
    else:
        # SEPARAMOS EN LAS CATEGORÍAS PRINCIPALES
        ganadores = [p for p in todas_las_proyecciones if p['mejor_mercado_tipo'] == 'Gana Partido']
        goles = [p for p in todas_las_proyecciones if p['mejor_mercado_tipo'] == 'Goles']
        seguros = [p for p in todas_las_proyecciones if p['mejor_mercado_tipo'] in ['Doble Oportunidad', 'Sin Empate (DNB)']]
        
        ganadores.sort(key=lambda x: x['mejor_mercado_prob'], reverse=True)
        goles.sort(key=lambda x: x['mejor_mercado_prob'], reverse=True)
        seguros.sort(key=lambda x: x['mejor_mercado_prob'], reverse=True)
        
        if ganadores:
            mensaje_resumen += "🏆 *TOP 5 - GANADOR DIRECTO*\n"
            for i, p in enumerate(ganadores[:5], 1):
                mensaje_resumen += f"*{i}.* ⚽ {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n   🎯 Gana {p['mejor_mercado_seleccion']} ({p['mejor_mercado_prob']:.0%})\n\n"
            
        if seguros:
            mensaje_resumen += "🛡️ *TOP 5 - MERCADOS SEGUROS (DNB / 1X2)*\n"
            for i, p in enumerate(seguros[:5], 1):
                mensaje_resumen += f"*{i}.* ⚽ {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n   🎯 {p['mejor_mercado_tipo']}: {p['mejor_mercado_seleccion']} ({p['mejor_mercado_prob']:.0%})\n\n"

        if goles:
            mensaje_resumen += "🔥 *TOP 5 - MERCADOS DE GOLES*\n"
            for i, p in enumerate(goles[:5], 1):
                marcador = p.get('scores', ['N/A'])[0] if p.get('scores') else 'N/A'
                mensaje_resumen += f"*{i}.* ⚽ {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n   🎯 Pick: {p['mejor_mercado_seleccion']} ({p['mejor_mercado_prob']:.0%}) | Marcador: `{marcador}`\n\n"

        # PORTAFOLIO DE COMBINADAS
        mensaje_resumen += "━"*20 + "\n💼 *PORTAFOLIO RECOMENDADO*\n\n"
        if len(seguros) >= 2:
            mensaje_resumen += f"🧱 *La Muralla (Seguros):*\n   1️⃣ {seguros[0]['mejor_mercado_tipo']}: {seguros[0]['mejor_mercado_seleccion']}\n   2️⃣ {seguros[1]['mejor_mercado_tipo']}: {seguros[1]['mejor_mercado_seleccion']}\n\n"
        if ganadores and goles:
            mensaje_resumen += f"🚀 *El Mix de Valor:*\n   1️⃣ Gana {ganadores[0]['mejor_mercado_seleccion']}\n   2️⃣ {goles[0]['mejor_mercado_seleccion']} en {goles[0]['local']} vs {goles[0]['visita']}\n"

    # Enviar particionado si supera el límite de caracteres de Telegram
    if len(mensaje_resumen) > 4000:
        mitad = len(mensaje_resumen) // 2
        enviar_mensaje_telegram(mensaje_resumen[:mitad], token_override=token_override)
        time.sleep(1.5)
        enviar_mensaje_telegram(mensaje_resumen[mitad:], token_override=token_override)
    else:
        enviar_mensaje_telegram(mensaje_resumen, token_override=token_override)


def enviar_bloque_reportes(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    agrupado_por_pais = agrupar_por_pais(proyecciones_dict)
    
    for pais, ligas_del_pais in sorted(agrupado_por_pais.items()):
        bandera = BANDERAS.get(pais, "🏴")
        sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
        
        mensajes_a_enviar = []
        mensaje_actual = f"🏆 {bandera} *{pais}*{sufijo}\n" + "━"*20 + "\n\n"
        
        for liga, proyecciones in sorted(ligas_del_pais.items()):
            top_items = proyecciones 
            
            bloque_liga = f"📌 *{liga} - TOTAL ({len(top_items)})*\n\n"
            
            for p in top_items:
                s_l = analyzer.get_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_team_stats(p['visita'], p.get('visita_id'))
                
                bloque_liga += f"📅 `{p.get('fecha_str', '')}` 🕒 `{p['hora']}`\n⚽ *{p['local']}* vs *{p['visita']}*\n"
                bloque_liga += (f"📊 Probabilidades: L:{p['probs'][0]:.0%} | E:{p['probs'][1]:.0%} | V:{p['probs'][2]:.0%}\n"
                                f"🎯 Ambos anotan: {p['btts']:.0%} | Marcadores: {', '.join(p['scores'])}\n")

                count_l = s_l.get('count', 0) if isinstance(s_l, dict) else 0
                count_v = s_v.get('count', 0) if isinstance(s_v, dict) else 0

                if count_l > 0 and count_v > 0:
                    bloque_liga += (f"📐 *Promedio de goles ({count_l}p | {count_v}p):*\n"
                                    f"  ⚽ A favor: `{s_l['goles_favor']:.1f}` | `{s_v['goles_favor']:.1f}`\n"
                                    f"  🛡️ En contra: `{s_l['goles_contra']:.1f}` | `{s_v['goles_contra']:.1f}`\n\n")

                    if s_l.get("has_details") and s_v.get("has_details"):
                        bloque_liga += (f"📊 *Estadísticas avanzadas:*\n"
                                        f"  🚩 Córners: `{s_l['corners']:.0f}` | `{s_v['corners']:.0f}`\n"
                                        f"  🟨 Tarjetas: `{s_l['tarjetas']:.0f}` | `{s_v['tarjetas']:.0f}`\n"
                                        f"  🥅 Remates: `{s_l['remates']:.0f}` | `{s_v['remates']:.0f}`\n\n")
                else:
                    bloque_liga += "⚠️ *Sin historial suficiente para promedios detallados.*\n\n"

            if len(mensaje_actual) + len(bloque_liga) > 3800:
                mensaje_actual += "━"*20 + "\n"
                mensajes_a_enviar.append(mensaje_actual)
                mensaje_actual = f"🏆 {bandera} *{pais}*{sufijo} (Cont.)\n" + "━"*20 + "\n\n" + bloque_liga
            else:
                mensaje_actual += bloque_liga
                
        if mensaje_actual:
            mensaje_actual += "━"*20 + "\n"
            mensajes_a_enviar.append(mensaje_actual)
            
        for msg in mensajes_a_enviar:
            enviar_mensaje_telegram(msg, token_override=token_override)
            time.sleep(1.5)
            
    enviar_resumen_mejores_apuestas(proyecciones_dict, titulo_bloque, analyzer, token_override, is_basket=False)


def enviar_bloque_reportes_basket(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    agrupado_por_pais = agrupar_por_pais(proyecciones_dict)
    
    for pais, ligas_del_pais in sorted(agrupado_por_pais.items()):
        bandera = BANDERAS.get(pais, "🏴")
        sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
        
        mensajes_a_enviar = []
        mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo}\n" + "━"*20 + "\n\n"
        
        for liga, proyecciones in sorted(ligas_del_pais.items()):
            top_items = proyecciones
            
            bloque_liga = f"📌 *{liga} - TOTAL ({len(top_items)})*\n\n"
            
            for p in top_items:
                s_l = analyzer.get_basketball_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_basketball_team_stats(p['visita'], p.get('visita_id'))
                ot_l = analyzer.get_basketball_overtime_stats(p['local'], p.get('local_id'))
                ot_v = analyzer.get_basketball_overtime_stats(p['visita'], p.get('visita_id'))

                bloque_liga += f"📅 `{p.get('fecha_str', '')}` 🕒 `{p['hora']}`\n🏀 *{p['local']}* vs *{p['visita']}*\n"
                bloque_liga += (f"📊 Victoria Proyectada: L:{p['prob_home']:.0%} | V:{p['prob_away']:.0%}\n"
                                f"🎯 Puntos Proyectados: `{p['puntos_proyectados']:.1f}` pts\n")

                count_l = s_l.get('count', 0) if isinstance(s_l, dict) else 0
                count_v = s_v.get('count', 0) if isinstance(s_v, dict) else 0

                if count_l > 0 and count_v > 0:
                    bloque_liga += (f"📐 *Promedios ({count_l}p | {count_v}p):*\n"
                                    f"  pts a favor: `{s_l['puntos_favor']:.1f}` | `{s_v['puntos_favor']:.1f}`\n"
                                    f"  pts en contra: `{s_l['puntos_contra']:.1f}` | `{s_v['puntos_contra']:.1f}`\n")

                    if ot_l.get('partidos_ot', 0) > 0 or ot_v.get('partidos_ot', 0) > 0:
                        bloque_liga += (f"⏱️ *Tendencia a Prórroga (OT):*\n"
                                        f"  partidos con OT: `{ot_l['partidos_ot']}/5` | `{ot_v['partidos_ot']}/5`\n"
                                        f"  puntos extra prom: `{ot_l['promedio_puntos_ot']:.1f}` | `{ot_v['promedio_puntos_ot']:.1f}`\n\n")
                    else:
                        bloque_liga += "\n"
                else:
                    bloque_liga += "⚠️ *Sin historial suficiente.*\n\n"

            if len(mensaje_actual) + len(bloque_liga) > 3800:
                mensaje_actual += "━"*20 + "\n"
                mensajes_a_enviar.append(mensaje_actual)
                mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo} (Cont.)\n" + "━"*20 + "\n\n" + bloque_liga
            else:
                mensaje_actual += bloque_liga
                
        if mensaje_actual:
            mensaje_actual += "━"*20 + "\n"
            mensajes_a_enviar.append(mensaje_actual)
            
        for msg in mensajes_a_enviar:
            enviar_mensaje_telegram(msg, token_override=token_override)
            time.sleep(1.5)

    enviar_resumen_mejores_apuestas(proyecciones_dict, titulo_bloque, analyzer, token_override, is_basket=True)
