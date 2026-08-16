import os
import json
import requests
import time

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def cargar_banderas():
    """Carga de forma dinámica el mapa de banderas desde la configuración."""
    ruta_flags = os.path.join("config", "flags.json")
    try:
        with open(ruta_flags, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        print("⚠️ No se pudo cargar config/flags.json, se usarán banderas por defecto.")
        return {}

BANDERAS = cargar_banderas()

def enviar_mensaje_telegram(mensaje, token_override=None):
    """Dispara un mensaje directo a Telegram usando el token indicado o el general, manejando Rate Limits."""
    token_activo = token_override or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token_activo and chat_id:
        try:
            res = requests.post(
                f"https://api.telegram.org/bot{token_activo}/sendMessage", 
                data={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
            )
            
            # 🛡️ Manejo inteligente del límite de envíos (Error 429)
            if res.status_code == 429:
                error_data = res.json()
                espera = error_data.get("parameters", {}).get("retry_after", 5)
                print(f"⏳ Límite de Telegram alcanzado. Esperando {espera} segundos...")
                time.sleep(espera)
                return enviar_mensaje_telegram(mensaje, token_override=token_override)

            if not res.ok:
                print(f"⚠️ Error al enviar a Telegram: {res.text}")
        except Exception as e:
            print(f"⚠️ Excepción al conectar con Telegram: {e}")
    else:
        print("⚠️ Faltan credenciales de Telegram (TOKEN o CHAT_ID).")

def agrupar_por_pais(proyecciones_dict):
    """Función auxiliar para reestructurar el diccionario de ligas a países."""
    agrupado = {}
    for liga, proyecciones in proyecciones_dict.items():
        if not proyecciones:
            continue
        
        # Extraer país desde el primer partido de forma segura
        p_info = proyecciones[0].get('pais', 'World')
        pais = p_info.get('name', 'World') if isinstance(p_info, dict) else (p_info or 'World')
        
        if pais not in agrupado:
            agrupado[pais] = {}
        agrupado[pais][liga] = proyecciones
        
    return agrupado

def enviar_bloque_reportes(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    """Reportes agrupados por PAÍS para Fútbol ordenados alfabéticamente."""
    agrupado_por_pais = agrupar_por_pais(proyecciones_dict)
    
    for pais, ligas_del_pais in sorted(agrupado_por_pais.items()):
        bandera = BANDERAS.get(pais, "🏴")
        sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
        
        mensajes_a_enviar = []
        mensaje_actual = f"🏆 {bandera} *{pais}*{sufijo}\n" + "━"*20 + "\n\n"
        
        for liga, proyecciones in sorted(ligas_del_pais.items()):
            limite_dinamico = min(len(proyecciones), 3)
            top_items = analyzer.get_top_by_league(proyecciones, n=limite_dinamico)
            
            bloque_liga = f"📌 *{liga} - TOP ({len(top_items)})*\n\n"
            
            for p in top_items:
                s_l = analyzer.get_team_stats(p['local'])
                s_v = analyzer.get_team_stats(p['visita'])
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

            # 🛡️ Control de límite de caracteres de Telegram (Max 4096)
            if len(mensaje_actual) + len(bloque_liga) > 3800:
                mensaje_actual += "━"*20 + "\n"  # ✅ DIVISIÓN AL FINAL DEL MENSAJE
                mensajes_a_enviar.append(mensaje_actual)
                mensaje_actual = f"🏆 {bandera} *{pais}*{sufijo} (Cont.)\n" + "━"*20 + "\n\n" + bloque_liga
            else:
                mensaje_actual += bloque_liga
                
        if mensaje_actual:
            mensaje_actual += "━"*20 + "\n"  # ✅ DIVISIÓN AL FINAL DEL MENSAJE
            mensajes_a_enviar.append(mensaje_actual)
            
        for msg in mensajes_a_enviar:
            enviar_mensaje_telegram(msg, token_override=token_override)
            time.sleep(1.5)

def enviar_bloque_reportes_basket(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    """Reportes agrupados por PAÍS para Basketball ordenados alfabéticamente."""
    agrupado_por_pais = agrupar_por_pais(proyecciones_dict)
    
    for pais, ligas_del_pais in sorted(agrupado_por_pais.items()):
        bandera = BANDERAS.get(pais, "🏴")
        sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
        
        mensajes_a_enviar = []
        mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo}\n" + "━"*20 + "\n\n"
        
        for liga, proyecciones in sorted(ligas_del_pais.items()):
            limite_dinamico = min(len(proyecciones), 3)
            top_items = analyzer.get_top_by_league(proyecciones, n=limite_dinamico)
            
            bloque_liga = f"📌 *{liga} - TOP ({len(top_items)})*\n\n"
            
            for p in top_items:
                s_l = analyzer.get_basketball_team_stats(p['local'])
                s_v = analyzer.get_basketball_team_stats(p['visita'])
                ot_l = analyzer.get_basketball_overtime_stats(p['local'])
                ot_v = analyzer.get_basketball_overtime_stats(p['visita'])

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

            # 🛡️ Control de límite de caracteres
            if len(mensaje_actual) + len(bloque_liga) > 3800:
                mensaje_actual += "━"*20 + "\n"  # ✅ DIVISIÓN AL FINAL DEL MENSAJE
                mensajes_a_enviar.append(mensaje_actual)
                mensaje_actual = f"🏀 {bandera} *{pais}*{sufijo} (Cont.)\n" + "━"*20 + "\n\n" + bloque_liga
            else:
                mensaje_actual += bloque_liga
                
        if mensaje_actual:
            mensaje_actual += "━"*20 + "\n"  # ✅ DIVISIÓN AL FINAL DEL MENSAJE
            mensajes_a_enviar.append(mensaje_actual)
            
        for msg in mensajes_a_enviar:
            enviar_mensaje_telegram(msg, token_override=token_override)
            time.sleep(1.5)
