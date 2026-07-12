import os
import requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

BANDERAS = {
    "Argentina": "🇦🇷", "Chile": "🇨🇱", "World": "🌍", "Australia": "🇦🇺", 
    "Belarus": "🇧🇾", "Ecuador": "🇪🇨", "USA": "🇺🇸", "Russia": "🇷🇺",
    "Finland": "🇫🇮", "Paraguay": "🇵🇾", "South-Korea": "🇰🇷", "Estonia": "🇪🇪",
    "Ireland": "🇮🇪", "Kazakhstan": "🇰🇿", "Lebanon": "🇱🇧", "Zimbabwe": "🇿🇼",
    "Kyrgyzstan": "🇰🇬", "Latvia": "🇱🇻", "Brazil": "🇧🇷", "Peru": "🇵🇪", "China": "🇨🇳",
    "Canada": "🇨🇦", "Puerto Rico": "🇵🇷", "New Zealand": "🇳🇿"
}

def enviar_mensaje_telegram(mensaje, token_override=None):
    """Dispara un mensaje directo a Telegram usando el token indicado o el general."""
    token_activo = token_override or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token_activo and chat_id:
        try:
            res = requests.post(
                f"https://api.telegram.org/bot{token_activo}/sendMessage", 
                data={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
            )
            if not res.ok:
                print(f"⚠️ Error al enviar a Telegram: {res.text}")
        except Exception as e:
            print(f"⚠️ Excepción al conectar con Telegram: {e}")
    else:
        print("⚠️ Faltan credenciales de Telegram (TOKEN o CHAT_ID).")

def enviar_bloque_reportes(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    """Reportes estándar para Fútbol."""
    for liga, proyecciones in proyecciones_dict.items():
        if not proyecciones:
            continue
        limite_dinamico = min(len(proyecciones), 3)
        top_items = analyzer.get_top_by_league(proyecciones, n=limite_dinamico)
        pais_liga = top_items[0].get('pais', 'World') if top_items else 'World'
        bandera = BANDERAS.get(pais_liga, "🏴")
        
        sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
        mensaje = f"🏆 {bandera} *{pais_liga}* - *TOP ({len(top_items)}): {liga}{sufijo}*\n\n"
        
        for p in top_items:
            s_l = analyzer.get_team_stats(p['local'])
            s_v = analyzer.get_team_stats(p['visita'])
            mensaje += f"📅 `{p.get('fecha_str', '')}` 🕒 `{p['hora']}`\n⚽ *{p['local']}* vs *{p['visita']}*\n"
            mensaje += (f"📊 Probabilidades: L:{p['probs'][0]:.0%} | E:{p['probs'][1]:.0%} | V:{p['probs'][2]:.0%}\n"
                        f"🎯 Ambos anotan: {p['btts']:.0%} | Marcadores: {', '.join(p['scores'])}\n")
            
            count_l = s_l.get('count', 0) if isinstance(s_l, dict) else 0
            count_v = s_v.get('count', 0) if isinstance(s_v, dict) else 0
            if count_l > 0 and count_v > 0:
                mensaje += (f"📐 *Promedios últimos partidos ({count_l}p | {count_v}p):*\n"
                            f"  🚩 Córners: `{s_l['corners']:.0f}` | `{s_v['corners']:.0f}`\n"
                            f"  🟨 Tarjetas: `{s_l['tarjetas']:.0f}` | `{s_v['tarjetas']:.0f}`\n"
                            f"  🥅 Remates: `{s_l['remates']:.0f}` | `{s_v['remates']:.0f}`\n\n")
            else:
                mensaje += "⚠️ *Sin historial suficiente para promedios detallados.*\n\n"
                
        enviar_mensaje_telegram(mensaje, token_override=token_override)

def enviar_bloque_reportes_basket(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    """Construye y envía el reporte específico para Basketball (sin córners ni tarjetas)."""
    for liga, proyecciones in proyecciones_dict.items():
        if not proyecciones:
            continue
        limite_dinamico = min(len(proyecciones), 3)
        top_items = analyzer.get_top_by_league(proyecciones, n=limite_dinamico)
        pais_liga = top_items[0].get('pais', 'World') if top_items else 'World'
        bandera = BANDERAS.get(pais_liga, "🏴")
        
        sufijo = f" ({titulo_bloque})" if titulo_bloque else ""
        mensaje = f"🏀 {bandera} *{pais_liga}* - *TOP BÁSQUET ({len(top_items)}): {liga}{sufijo}*\n\n"
        
        for p in top_items:
            s_l = analyzer.get_basketball_team_stats(p['local'])
            s_v = analyzer.get_basketball_team_stats(p['visita'])
            mensaje += f"📅 `{p.get('fecha_str', '')}` 🕒 `{p['hora']}`\n🏀 *{p['local']}* vs *{p['visita']}*\n"
            mensaje += (f"📊 Victoria Proyectada: L:{p['prob_home']:.0%} | V:{p['prob_away']:.0%}\n"
                        f"🎯 Puntos Proyectados en el Partido: `{p['puntos_proyectados']:.1f}` pts\n")
            
            count_l = s_l.get('count', 0) if isinstance(s_l, dict) else 0
            count_v = s_v.get('count', 0) if isinstance(s_v, dict) else 0
            if count_l > 0 and count_v > 0:
                mensaje += (f"📐 *Promedios últimos partidos ({count_l}p | {count_v}p):*\n"
                            f"  pts a favor: `{s_l['puntos_favor']:.1f}` | `{s_v['puntos_favor']:.1f}`\n"
                            f"  pts en contra: `{s_l['puntos_contra']:.1f}` | `{s_v['puntos_contra']:.1f}`\n\n")
            else:
                mensaje += "⚠️ *Sin historial suficiente para promedios de anotación.*\n\n"
                
        enviar_mensaje_telegram(mensaje, token_override=token_override)