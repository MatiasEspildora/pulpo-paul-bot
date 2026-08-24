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

def _generar_y_enviar_menu(proyecciones_dict, etiqueta_dia, analyzer, token_override=None, is_basket=False):
    ganadores_lista = []
    goles_lista = []
    seguros_lista = []
    basket_lista = []
    eliminatorias_lista = [] 
    bet_builders_lista = [] # Nuevo array para piezas de Bet Builder
    
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

                if count_l >= 3 and count_v >= 3:
                    p['liga_nombre'] = liga
                    p['pais_nombre'] = pais
                    
                    if is_basket:
                        prob_gana = max(p['prob_home'], p['prob_away'])
                        seleccion = p['local'] if p['prob_home'] > p['prob_away'] else p['visita']
                        basket_lista.append({'match': p, 'prob': prob_gana, 'seleccion': seleccion})
                    else:
                        es_elim = p.get('es_eliminatoria', False)

                        if es_elim:
                            prob_gana = max(p['probs'][0], p['probs'][2])
                            mercados_elim = [
                                {'tipo': 'Ganador', 'seleccion': p['local'] if p['probs'][0] > p['probs'][2] else p['visita'], 'prob': prob_gana},
                                {'tipo': 'Goles', 'seleccion': '+1.5 Goles', 'prob': p.get('over_1_5', 0)},
                                {'tipo': 'Goles', 'seleccion': 'Ambos Anotan', 'prob': p.get('btts', 0)},
                                {'tipo': 'Blindaje', 'seleccion': f"{p['local']} o Empate", 'prob': p.get('prob_1X', 0)},
                                {'tipo': 'Blindaje', 'seleccion': f"{p['visita']} o Empate", 'prob': p.get('prob_X2', 0)}
                            ]
                            mejor_pick = max(mercados_elim, key=lambda x: x['prob'])
                            eliminatorias_lista.append({'match': p, 'prob': mejor_pick['prob'], 'seleccion': mejor_pick['seleccion'], 'mercado': mejor_pick['tipo']})
                            
                        else:
                            # 1. GANADOR DIRECTO
                            prob_gana = max(p['probs'][0], p['probs'][2])
                            seleccion_gana = p['local'] if p['probs'][0] > p['probs'][2] else p['visita']
                            ganadores_lista.append({'match': p, 'prob': prob_gana, 'seleccion': seleccion_gana})

                            # 2. MERCADO DE GOLES
                            mercados_goles = [
                                {'tipo': 'Ambos Anotan (Sí)', 'prob': p.get('btts', 0)},
                                {'tipo': '+1.5 Goles', 'prob': p.get('over_1_5', 0)},
                                {'tipo': '+2.5 Goles', 'prob': p.get('over_2_5', 0)}
                            ]
                            mejor_gol = max(mercados_goles, key=lambda x: x['prob'])
                            goles_lista.append({'match': p, 'prob': mejor_gol['prob'], 'seleccion': mejor_gol['tipo']})

                            # 3. MERCADOS SEGUROS
                            mercados_seguros = [
                                {'tipo': 'Doble Oportunidad', 'seleccion': f"{p['local']} o Empate", 'prob': p.get('prob_1X', 0)},
                                {'tipo': 'Doble Oportunidad', 'seleccion': f"{p['visita']} o Empate", 'prob': p.get('prob_X2', 0)}
                            ]
                            mejor_seguro = max(mercados_seguros, key=lambda x: x['prob'])
                            seguros_lista.append({'match': p, 'prob': mejor_seguro['prob'], 'seleccion': mejor_seguro['seleccion'], 'tipo': mejor_seguro['tipo']})

                            # 4. EXTRACCIÓN DE PIEZAS PARA BET BUILDERS
                            if p.get('btts_no', 0) > 0.75:
                                bet_builders_lista.append({'match': p, 'prob': p.get('btts_no', 0), 'seleccion': 'Ambos Anotan (NO)'})
                            if p.get('under_3_5', 0) > 0.80:
                                bet_builders_lista.append({'match': p, 'prob': p.get('under_3_5', 0), 'seleccion': '-3.5 Goles Totales'})
                            if p.get('prob_over_0_5_ht', 0) > 0.75:
                                bet_builders_lista.append({'match': p, 'prob': p.get('prob_over_0_5_ht', 0), 'seleccion': '+0.5 Goles al Descanso (HT)'})
                
    if not (ganadores_lista or basket_lista or eliminatorias_lista):
        return False

    tz_chile = pytz.timezone('America/Santiago')
    hora_generacion = datetime.now(tz_chile).strftime("%d/%m/%Y %H:%M")

    mensaje_resumen = f"💎 ━━ *MENÚ ESTRATÉGICO: {etiqueta_dia}* ━━ 💎\n"
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
        eliminatorias_lista.sort(key=lambda x: x['prob'], reverse=True)
        bet_builders_lista.sort(key=lambda x: x['prob'], reverse=True)
        
        if ganadores_lista:
            mensaje_resumen += "🏆 *TOP 5 - GANADOR DIRECTO*\n"
            for i, item in enumerate(ganadores_lista[:5], 1):
                p = item['match']
                bandera = BANDERAS.get(p.get('pais_nombre', ''), "🏴")
                mensaje_resumen += f"*{i}.* ⚽ [{bandera} {p.get('pais_nombre', '')} - {p.get('liga_nombre', '')}]\n   {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n   🎯 Gana *{item['seleccion']}* ({item['prob']:.0%})\n\n"
        
        if seguros_lista:
            mensaje_resumen += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            mensaje_resumen += "🛡️ *TOP 5 - DOBLE OPORTUNIDAD*\n\n"
            for i, item in enumerate(seguros_lista[:5], 1):
                p = item['match']
                bandera = BANDERAS.get(p.get('pais_nombre', ''), "🏴")
                mensaje_resumen += f"*{i}.* ⚽ [{bandera} {p.get('pais_nombre', '')} - {p.get('liga_nombre', '')}]\n   {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n   🎯 1X2: *{item['seleccion']}* ({item['prob']:.0%})\n\n"

        if goles_lista:
            mensaje_resumen += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            mensaje_resumen += "🔥 *TOP 5 - MERCADOS DE GOLES*\n\n"
            for i, item in enumerate(goles_lista[:5], 1):
                p = item['match']
                bandera = BANDERAS.get(p.get('pais_nombre', ''), "🏴")
                marcador = p.get('scores', ['N/A'])[0] if p.get('scores') else 'N/A'
                prob_o25 = p.get('over_2_5', 0)
                prob_u35 = p.get('under_3_5', 0)
                prob_btts = p.get('btts', 0)
                
                mensaje_resumen += f"*{i}.* ⚽ [{bandera} {p.get('pais_nombre', '')} - {p.get('liga_nombre', '')}]\n"
                mensaje_resumen += f"   {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n"
                mensaje_resumen += f"   🎯 Pick: *{item['seleccion']}* ({item['prob']:.0%}) | Marcador: `{marcador}`\n"
                mensaje_resumen += f"   🔄 Respaldo: +2.5 ({prob_o25:.0%}) | -3.5 ({prob_u35:.0%}) | A.A. ({prob_btts:.0%})\n\n"

        # NUEVO BLOQUE: PIEZAS BET BUILDER
        if bet_builders_lista:
            mensaje_resumen += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            mensaje_resumen += "🧱 *PIEZAS BET BUILDER (Alta Confianza)*\n"
            mensaje_resumen += "_Úsalas para engordar cuotas de blindaje (1X2)_\n\n"
            for i, item in enumerate(bet_builders_lista[:5], 1):
                p = item['match']
                bandera = BANDERAS.get(p.get('pais_nombre', ''), "🏴")
                mensaje_resumen += f"*{i}.* ⚽ [{bandera} {p.get('pais_nombre', '')}] {p['local']} vs {p['visita']}\n"
                mensaje_resumen += f"   🧩 Pieza: *{item['seleccion']}* ({item['prob']:.0%})\n\n"

        mensaje_resumen += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        mensaje_resumen += "💼 *PORTAFOLIO RECOMENDADO*\n\n"
        
        if len(goles_lista) >= 3:
            g1, g2, g3 = goles_lista[0], goles_lista[1], goles_lista[2]
            mensaje_resumen += f"⚽ *El Triple de Goles:*\n"
            mensaje_resumen += f"   1️⃣ {g1['seleccion']}: {g1['match']['local']} vs {g1['match']['visita']}\n"
            mensaje_resumen += f"   2️⃣ {g2['seleccion']}: {g2['match']['local']} vs {g2['match']['visita']}\n"
            mensaje_resumen += f"   3️⃣ {g3['seleccion']}: {g3['match']['local']} vs {g3['match']['visita']}\n\n"

        if len(seguros_lista) >= 2:
            s1, s2 = seguros_lista[0], seguros_lista[1]
            mensaje_resumen += f"🛡️ *El Doble Blindado (1X2):*\n"
            mensaje_resumen += f"   1️⃣ {s1['tipo']}: {s1['seleccion']}\n"
            mensaje_resumen += f"   2️⃣ {s2['tipo']}: {s2['seleccion']}\n\n"

        if eliminatorias_lista:
            mensaje_resumen += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            mensaje_resumen += "⚠️ *ZONA DE ALTA VARIANZA (MATA-MATA)* ⚠️\n"
            mensaje_resumen += "_Radar secundario (Ignorar para caja principal)_\n\n"
            for i, item in enumerate(eliminatorias_lista[:5], 1):
                p = item['match']
                bandera = BANDERAS.get(p.get('pais_nombre', ''), "🏴")
                mensaje_resumen += f"*{i}.* ⚽ [{bandera} {p.get('pais_nombre', '')} - {p.get('liga_nombre', '')}]\n   {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n"
                mensaje_resumen += f"   🎯 {item['mercado']}: *{item['seleccion']}* ({item['prob']:.0%})\n\n"

    mensaje_resumen += "━"*24 + "\n"
    mensaje_resumen += "✅ *FIN DEL REPORTE* ✅\n"

    if len(mensaje_resumen) > 4000:
        mitad = len(mensaje_resumen) // 2
        enviar_mensaje_telegram(mensaje_resumen[:mitad], token_override=token_override)
        time.sleep(1.5)
        enviar_mensaje_telegram(mensaje_resumen[mitad:], token_override=token_override)
    else:
        enviar_mensaje_telegram(mensaje_resumen, token_override=token_override)
        
    return True

def enviar_resumen_mejores_apuestas(proyecciones_dict, titulo_bloque, analyzer, token_override=None, is_basket=False):
    tz_chile = pytz.timezone('America/Santiago')
    hoy_dt = datetime.now(tz_chile)
    hoy_str = hoy_dt.strftime("%Y-%m-%d")
    manana_str = (hoy_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    
    dict_hoy = {}
    dict_manana = {}
    
    for key, projs in proyecciones_dict.items():
        for p in projs:
            fecha = p.get('fecha_str', '')
            if fecha == hoy_str:
                dict_hoy.setdefault(key, []).append(p)
            elif fecha == manana_str:
                dict_manana.setdefault(key, []).append(p)
                
    enviado_hoy = _generar_y_enviar_menu(dict_hoy, f"HOY ({hoy_str})", analyzer, token_override, is_basket)
    enviado_manana = _generar_y_enviar_menu(dict_manana, f"MAÑANA ({manana_str})", analyzer, token_override, is_basket)
    
    if not enviado_hoy and not enviado_manana:
        aviso = f"💎 ━━ *MENÚ DE MEJORES PICKS* ━━ 💎\n" + "━"*22 + "\n\n⚠️ _No hay partidos con historial maduro para HOY ni MAÑANA._\n\n" + "━"*22 + "\n✅ *FIN DEL REPORTE* ✅"
        enviar_mensaje_telegram(aviso, token_override=token_override)

def enviar_bloque_reportes(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    agrupado_por_pais = agrupar_por_pais(proyecciones_dict)
    
    for pais, ligas_del_pais in sorted(agrupado_por_pais.items()):
        bandera = BANDERAS.get(pais, "🏴")
        sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
        
        mensajes_a_enviar = []
        mensaje_actual = f"🏆 {bandera} *{pais}*{sufijo}\n" + "━"*20 + "\n\n"
        
        for liga, proyecciones in sorted(ligas_del_pais.items()):
            top_items = proyecciones 
            
            header_liga = f"📌 *{liga} - TOTAL ({len(top_items)})*\n\n"
            
            if len(mensaje_actual) + len(header_liga) > 3800:
                mensaje_actual += "━"*20 + "\n"
                mensajes_a_enviar.append(mensaje_actual)
                mensaje_actual = f"🏆 {bandera} *{pais}*{sufijo} (Cont.)\n" + "━"*20 + "\n\n"
                
            mensaje_actual += header_liga
            
            for p in top_items:
                s_l = analyzer.get_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_team_stats(p['visita'], p.get('visita_id'))
                
                bloque_partido = f"📅 `{p.get('fecha_str', '')}` 🕒 `{p['hora']}`\n⚽ *{p['local']}* vs *{p['visita']}*\n"
                bloque_partido += (f"📊 1X2: L:{p['probs'][0]:.0%} | E:{p['probs'][1]:.0%} | V:{p['probs'][2]:.0%}\n"
                                f"🎯 Ambos Anotan: Sí ({p.get('btts', 0):.0%}) | No ({p.get('btts_no', 0):.0%})\n"
                                f"⚽ Bajas(U): -2.5 ({p.get('under_2_5', 0):.0%}) | -3.5 ({p.get('under_3_5', 0):.0%})\n"
                                f"⏱️ +0.5 Goles HT: {p.get('prob_over_0_5_ht', 0):.0%}\n")

                count_l = s_l.get('count', 0) if isinstance(s_l, dict) else 0
                count_v = s_v.get('count', 0) if isinstance(s_v, dict) else 0

                if count_l > 0 and count_v > 0:
                    bloque_partido += (f"📐 *Promedio de goles ({count_l}p | {count_v}p):*\n"
                                    f"  ⚽ A favor: `{s_l.get('goles_favor', 0):.1f}` | `{s_v.get('goles_favor', 0):.1f}`\n"
                                    f"  🛡️ En contra: `{s_l.get('goles_contra', 0):.1f}` | `{s_v.get('goles_contra', 0):.1f}`\n\n")

                    if s_l.get("has_details") and s_v.get("has_details"):
                        bloque_partido += (f"📊 *Estadísticas avanzadas:*\n"
                                        f"  🚩 Córners: `{s_l.get('corners', 0):.0f}` | `{s_v.get('corners', 0):.0f}`\n"
                                        f"  🟨 Tarjetas: `{s_l.get('tarjetas', 0):.0f}` | `{s_v.get('tarjetas', 0):.0f}`\n"
                                        f"  🥅 Remates: `{s_l.get('remates', 0):.0f}` | `{s_v.get('remates', 0):.0f}`\n\n")
                else:
                    bloque_partido += "⚠️ *Sin historial suficiente para promedios detallados.*\n\n"

                if len(mensaje_actual) + len(bloque_partido) > 3800:
                    mensaje_actual += "━"*20 + "\n"
                    mensajes_a_enviar.append(mensaje_actual)
                    mensaje_actual = f"🏆 {bandera} *{pais}*{sufijo} (Cont.)\n" + "━"*20 + "\n\n"
                    
                mensaje_actual += bloque_partido

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

    enviar_resumen_mejores_apuestas(proyecciones_dict, titulo_bloque, analyzer, token_override, is_basket=True)
