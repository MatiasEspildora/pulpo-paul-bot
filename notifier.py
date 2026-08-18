import os
import json
import requests
import time
from datetime import datetime
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

def enviar_resumen_mejores_apuestas(proyecciones_dict, titulo_bloque, analyzer, token_override=None, is_basket=False):
    ganadores_lista = []
    goles_lista = []
    seguros_lista = []
    basket_lista = []
    
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
                        prob_gana = max(p['prob_home'], p['prob_away'])
                        seleccion = p['local'] if p['prob_home'] > p['prob_away'] else p['visita']
                        basket_lista.append({'match': p, 'prob': prob_gana, 'seleccion': seleccion})
                    else:
                        # 1. EVALUACIÓN DE GANADOR DIRECTO
                        prob_gana = max(p['probs'][0], p['probs'][2])
                        seleccion_gana = p['local'] if p['probs'][0] > p['probs'][2] else p['visita']
                        ganadores_lista.append({'match': p, 'prob': prob_gana, 'seleccion': seleccion_gana})

                        # 2. EVALUACIÓN DE MERCADO DE GOLES
                        mercados_goles = [
                            {'tipo': 'Ambos Anotan (Sí)', 'prob': p.get('btts', 0)},
                            {'tipo': '+1.5 Goles', 'prob': p.get('over_1_5', 0)},
                            {'tipo': '+2.5 Goles', 'prob': p.get('over_2_5', 0)}
                        ]
                        mejor_gol = max(mercados_goles, key=lambda x: x['prob'])
                        goles_lista.append({'match': p, 'prob': mejor_gol['prob'], 'seleccion': mejor_gol['tipo']})

                        # 3. EVALUACIÓN DE MERCADOS SEGUROS (DNB / Doble Oportunidad)
                        mercados_seguros = [
                            {'tipo': 'Doble Oportunidad', 'seleccion': f"{p['local']} o Empate", 'prob': p.get('prob_1X', 0)},
                            {'tipo': 'Doble Oportunidad', 'seleccion': f"{p['visita']} o Empate", 'prob': p.get('prob_X2', 0)},
                            {'tipo': 'Sin Empate (DNB)', 'seleccion': p['local'], 'prob': p.get('prob_DNB_L', 0)},
                            {'tipo': 'Sin Empate (DNB)', 'seleccion': p['visita'], 'prob': p.get('prob_DNB_V', 0)}
                        ]
                        mejor_seguro = max(mercados_seguros, key=lambda x: x['prob'])
                        seguros_lista.append({'match': p, 'prob': mejor_seguro['prob'], 'seleccion': mejor_seguro['seleccion'], 'tipo': mejor_seguro['tipo']})
                
    if not (ganadores_lista or basket_lista):
        aviso = f"💎 ━━ *MENÚ DE MEJORES PICKS* ━━ 💎\n" + "━"*22 + "\n\n⚠️ _Hoy no hay partidos con historial maduro para generar proyecciones seguras._\n\n" + "━"*22 + "\n✅ *FIN DEL REPORTE* ✅"
        enviar_mensaje_telegram(aviso, token_override=token_override)
        return

    # Generamos la hora actual para el reporte
    tz_chile = pytz.timezone('America/Santiago')
    hora_generacion = datetime.now(tz_chile).strftime("%d/%m/%Y %H:%M")

    sufijo = f" {titulo_bloque} " if titulo_bloque else " "
    mensaje_resumen = f"💎 ━━ *MENÚ ESTRATÉGICO{sufijo}* ━━ 💎\n"
    mensaje_resumen += f"📅 _Generado: {hora_generacion}_\n"
    mensaje_resumen += "━"*24 + "\n\n"

    if is_basket:
        basket_lista.sort(key=lambda x: x['prob'], reverse=True)
        for i, item in enumerate(basket_lista[:10], 1):
            p = item['match']
            mensaje_resumen += f"*{i}.* 🏀 {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n"
            mensaje_resumen += f"   🎯 *Pick:* Gana {item['seleccion']} ({item['prob']:.0%}) | 🔥 Pts: `{p.get('puntos_proyectados', 0):.1f}`\n\n"
            
    else:
        ganadores_lista.sort(key=lambda x: x['prob'], reverse=True)
        goles_lista.sort(key=lambda x: x['prob'], reverse=True)
        seguros_lista.sort(key=lambda x: x['prob'], reverse=True)
        
        # BLOQUE 1: GANADORES
        if ganadores_lista:
            mensaje_resumen += "🏆 *TOP 5 - GANADOR DIRECTO*\n"
            for i, item in enumerate(ganadores_lista[:5], 1):
                p = item['match']
                mensaje_resumen += f"*{i}.* ⚽ {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n   🎯 Gana *{item['seleccion']}* ({item['prob']:.0%})\n\n"
        
        # BLOQUE 2: SEGUROS
        if seguros_lista:
            mensaje_resumen += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            mensaje_resumen += "🛡️ *TOP 5 - MERCADOS SEGUROS*\n"
            mensaje_resumen += "_(Doble Oportunidad / Sin Empate)_\n\n"
            for i, item in enumerate(seguros_lista[:5], 1):
                p = item['match']
                mensaje_resumen += f"*{i}.* ⚽ {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n   🎯 {item['tipo']}: *{item['seleccion']}* ({item['prob']:.0%})\n\n"

        # BLOQUE 3: GOLES
        if goles_lista:
            mensaje_resumen += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            mensaje_resumen += "🔥 *TOP 5 - MERCADOS DE GOLES*\n\n"
            for i, item in enumerate(goles_lista[:5], 1):
                p = item['match']
                marcador = p.get('scores', ['N/A'])[0] if p.get('scores') else 'N/A'
                mensaje_resumen += f"*{i}.* ⚽ {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n   🎯 Pick: *{item['seleccion']}* ({item['prob']:.0%}) | Marcador: `{marcador}`\n\n"

        # PORTAFOLIO DE COMBINADAS
        mensaje_resumen += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        mensaje_resumen += "💼 *PORTAFOLIO RECOMENDADO*\n\n"
        if len(seguros_lista) >= 2:
            s1, s2 = seguros_lista[0], seguros_lista[1]
            mensaje_resumen += f"🧱 *La Muralla (Combinada Segura):*\n   1️⃣ {s1['tipo']}: {s1['seleccion']}\n   2️⃣ {s2['tipo']}: {s2['seleccion']}\n\n"
        if ganadores_lista and goles_lista:
            g_top = ganadores_lista[0]
            gol_top = goles_lista[0]
            mensaje_resumen += f"🚀 *El Mix de Valor:*\n   1️⃣ Gana {g_top['seleccion']}\n   2️⃣ {gol_top['seleccion']} en {gol_top['match']['local']} vs {gol_top['match']['visita']}\n\n"

    # CIERRE OFICIAL DEL MENSAJE
    mensaje_resumen += "━"*24 + "\n"
    mensaje_resumen += "✅ *FIN DEL REPORTE* ✅\n"

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
