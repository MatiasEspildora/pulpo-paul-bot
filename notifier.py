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
    """Genera y envía un TOP 10 buscando la MEJOR OPCIÓN DE MERCADO en lugar de solo al ganador."""
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

                # Filtro de madurez estadística
                if count_l >= 3 and count_v >= 3:
                    p['liga_nombre'] = liga
                    p['pais_nombre'] = pais
                    
                    # 💡 NUEVO: EVALUADOR TRANSVERSAL DE MERCADOS
                    if is_basket:
                        mercados = [
                            {'tipo': 'Gana Partido', 'seleccion': p['local'], 'prob': p['prob_home']},
                            {'tipo': 'Gana Partido', 'seleccion': p['visita'], 'prob': p['prob_away']}
                        ]
                    else:
                        mercados = [
                            {'tipo': 'Gana Partido', 'seleccion': p['local'], 'prob': p['probs'][0]},
                            {'tipo': 'Gana Partido', 'seleccion': p['visita'], 'prob': p['probs'][2]},
                            {'tipo': 'Ambos Anotan (BTTS)', 'seleccion': 'Sí', 'prob': p.get('btts', 0)}
                        ]
                    
                    # Encontramos el mercado con mayor probabilidad real para este evento
                    mejor_mercado = max(mercados, key=lambda x: x['prob'])
                    
                    p['mejor_mercado_tipo'] = mejor_mercado['tipo']
                    p['mejor_mercado_seleccion'] = mejor_mercado['seleccion']
                    p['mejor_mercado_prob'] = mejor_mercado['prob']
                    
                    todas_las_proyecciones.append(p)
                
    if not todas_las_proyecciones:
        aviso = f"💎 *TOP 10 MEJORES PICKS* 💎\n" + "━"*20 + "\n\n⚠️ _Hoy no hay partidos con historial maduro (Mín. 3 partidos por equipo) para generar proyecciones seguras._"
        enviar_mensaje_telegram(aviso, token_override=token_override)
        return

    # 1. Obtenemos el Top 10 absoluto basándonos en la probabilidad del MEJOR MERCADO
    todas_las_proyecciones.sort(key=lambda x: x.get('mejor_mercado_prob', 0), reverse=True)
    top_10 = todas_las_proyecciones[:10]
    
    # 2. Ordenamos: Chile primero, luego el resto (cronológicamente)
    top_10.sort(key=lambda x: (
        0 if x.get('pais_nombre') == 'Chile' else 1, 
        x.get('fecha_str', ''), 
        x.get('hora', '')
    ))
    
    deporte_icono = "🏀" if is_basket else "⚽"
    sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
    mensaje_resumen = f"💎 *TOP 10 MEJORES OPCIONES DE APUESTA{sufijo}* 💎\n" + "━"*20 + "\n\n"
    
    for i, p in enumerate(top_10, 1):
        prob_top = p.get('mejor_mercado_prob', 0)
        tipo_mercado = p.get('mejor_mercado_tipo', '')
        seleccion = p.get('mejor_mercado_seleccion', '')
        
        hora = p.get('hora', '')
        fecha = p.get('fecha_str', '')
        flag = "🇨🇱 " if p['pais_nombre'] == 'Chile' else ""
        
        if is_basket:
            pts_proyectados = p.get('puntos_proyectados', 0)
            mensaje_resumen += f"*{i}.* {flag}{deporte_icono} {p['local']} vs {p['visita']}\n"
            mensaje_resumen += f"   🏆 {p['pais_nombre']} - {p['liga_nombre']} | 📅 {fecha} 🕒 {hora}\n"
            mensaje_resumen += f"   🎯 *Mercado Sugerido:* {tipo_mercado} -> *{seleccion}* ({prob_top:.0%})\n"
            mensaje_resumen += f"   🔥 *Dato Extra:* Puntos Totales Proyectados: `{pts_proyectados:.1f}`\n\n"
        else:
            mejores_scores = p.get('scores', [])
            marcador_top = mejores_scores[0] if mejores_scores else "N/A"
            
            mensaje_resumen += f"*{i}.* {flag}{deporte_icono} {p['local']} vs {p['visita']}\n"
            mensaje_resumen += f"   🏆 {p['pais_nombre']} - {p['liga_nombre']} | 📅 {fecha} 🕒 {hora}\n"
            mensaje_resumen += f"   🎯 *Mercado Sugerido:* {tipo_mercado} -> *{seleccion}* ({prob_top:.0%})\n"
            mensaje_resumen += f"   🔥 *Marcador Proyectado:* `{marcador_top}`\n\n"
            
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
