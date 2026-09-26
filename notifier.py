import os
import json
import requests
import time
import math
from datetime import datetime, timedelta
import pytz
from scipy.stats import poisson

try:
    from api_client import FootballAPI
    API_KEY = os.environ.get("API_FOOTBALL_KEY")
    bot_api_client = FootballAPI(API_KEY) if API_KEY else None
except ImportError:
    bot_api_client = None

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

def calcular_confidence_score(probabilidad, partidos_jugados):
    if partidos_jugados == 0: 
        return 0
    partidos_topados = min(partidos_jugados, 15)
    factor_peso = math.log10(partidos_topados + 5) / math.log10(20)
    return probabilidad * factor_peso

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

def obtener_alertas_bajas(fixture_id):
    if not bot_api_client or not fixture_id:
        return ""
    try:
        data = bot_api_client.get_fixture_injuries(fixture_id)
        if not data or not data.get("response"):
            return ""
            
        bajas = []
        for inj in data["response"]:
            nombre = inj.get("player", {}).get("name", "")
            if nombre:
                bajas.append(nombre)
                
        if not bajas:
            return ""
            
        if len(bajas) > 2:
            return f" 🚑 [Bajas: {bajas[0]}, {bajas[1]} y {len(bajas)-2} más]"
        return f" 🚑 [Bajas: {', '.join(bajas)}]"
    except Exception:
        return ""

# ==========================================
# ⚽ FORMATO BENDER V4.0 (FÚTBOL - MODO ESTADÍSTICO)
# ==========================================
def _procesar_y_enviar_bloque_futbol(proyecciones_dict, titulo_bloque, fecha_bloque, analyzer, token_override=None):
    tz_chile = pytz.timezone('America/Santiago')
    hora_generacion = datetime.now(tz_chile).strftime("%d/%m/%Y %H:%M")
    
    partidos_validos = []
    for pais, ligas in agrupar_por_pais(proyecciones_dict).items():
        es_seleccion = (pais == "World")
        for liga, projs in ligas.items():
            for p in projs:
                es_copa = p.get('es_eliminatoria', False)
                s_l = analyzer.get_team_stats(p['local'], p.get('local_id'), league_id=p.get('league_id'), es_eliminatoria=es_copa, es_seleccion=es_seleccion)
                s_v = analyzer.get_team_stats(p['visita'], p.get('visita_id'), league_id=p.get('league_id'), es_eliminatoria=es_copa, es_seleccion=es_seleccion)
                
                min_partidos = 3 if es_copa else 5
                
                if s_l.get('count', 0) >= min_partidos and s_v.get('count', 0) >= min_partidos:
                    p['liga_nombre'] = liga
                    p['pais_nombre'] = pais
                    p['bandera'] = BANDERAS.get(pais, "🏴")
                    p['_id_interno'] = f"{p['local_id']}_{p['visita_id']}_{p['fecha_str']}"
                    p['total_partidos_muestra'] = s_l.get('count', 0) + s_v.get('count', 0)
                    p['es_seleccion'] = es_seleccion
                    
                    if s_l.get('has_details') and s_v.get('has_details'):
                        lam_s_home = (s_l.get('remates_f', 12.0) + s_v.get('remates_c', 12.0)) / 2
                        lam_s_away = (s_v.get('remates_f', 12.0) + s_l.get('remates_c', 12.0)) / 2
                        lam_s_total = lam_s_home + lam_s_away
                        p['over_24_5_shots'] = 1 - poisson.cdf(24, lam_s_total) if lam_s_total > 0 else 0.0
                        p['over_26_5_shots'] = 1 - poisson.cdf(26, lam_s_total) if lam_s_total > 0 else 0.0
                    else:
                        p['over_24_5_shots'] = 0.0
                        p['over_26_5_shots'] = 0.0

                    partidos_validos.append(p)
                    
    if not partidos_validos:
        return 0, set()

    bb_list = []
    mega_misiles = []
    ganadores = []
    dobles = []
    goles = []
    quirofano_tactico = []
    radar_remontadas = []
    francotiradores = []
    
    selecciones_bb = []
    selecciones_goles = []
    selecciones_dobles = []

    for p in partidos_validos:
        sgbb = p.get('sgbb', {})
        loc, vis = p['local'], p['visita']
        t_partidos = p['total_partidos_muestra']
        es_sel_partido = p.get('es_seleccion', False)
        
        descanso_l = p.get('dias_descanso_local', 7)
        descanso_v = p.get('dias_descanso_visita', 7)
        alerta_fatiga = ""
        if descanso_l < 4: alerta_fatiga += " ⚠️[L: Físico]"
        if descanso_v < 4: alerta_fatiga += " ⚠️[V: Físico]"
        p['alerta_fatiga'] = alerta_fatiga

        mapa_nombres_sgbb = {
            '1X_U25': '1X + Menos 2.5 Goles', '1X_U35': '1X + Menos 3.5 Goles', '1X_U45': '1X + Menos 4.5 Goles',
            '1X_O15': '1X + Más 1.5 Goles', '1X_O25': '1X + Más 2.5 Goles',
            'X2_U25': 'X2 + Menos 2.5 Goles', 'X2_U35': 'X2 + Menos 3.5 Goles', 'X2_U45': 'X2 + Menos 4.5 Goles',
            'X2_O15': 'X2 + Más 1.5 Goles', 'X2_O25': 'X2 + Más 2.5 Goles',
            '1_U25': f'Gana {loc} + Menos 2.5 Goles', '1_U35': f'Gana {loc} + Menos 3.5 Goles', '1_U45': f'Gana {loc} + Menos 4.5 Goles',
            '1_O15': f'Gana {loc} + Más 1.5 Goles', '1_O25': f'Gana {loc} + Más 2.5 Goles',
            '2_U25': f'Gana {vis} + Menos 2.5 Goles', '2_U35': f'Gana {vis} + Menos 3.5 Goles', '2_U45': f'Gana {vis} + Menos 4.5 Goles',
            '2_O15': f'Gana {vis} + Más 1.5 Goles', '2_O25': f'Gana {vis} + Más 2.5 Goles',
            'BTTS_O25': 'Ambos Anotan + Más 2.5 Goles', 'BTTS_No_U25': 'Ambos Anotan (No) + Menos 2.5 Goles',
            'BTTS_No_U35': 'Ambos Anotan (No) + Menos 3.5 Goles', '1X_BTTS_Yes': '1X + Ambos Anotan', 'X2_BTTS_Yes': 'X2 + Ambos Anotan'
        }

        for combo_key, prob in sgbb.items():
            if combo_key in mapa_nombres_sgbb:
                score = calcular_confidence_score(prob, t_partidos)
                item_data = {'match': p, 'prob': prob, 'sel': mapa_nombres_sgbb[combo_key], 'score': score}
                mega_misiles.append(item_data)
        
        def add_bb(condicion, variable_prob, texto):
            if condicion > 0.80: 
                item_data = {'match': p, 'prob': variable_prob, 'sel': texto, 'score': calcular_confidence_score(variable_prob, t_partidos)}
                if es_sel_partido:
                    selecciones_bb.append(item_data)
                else:
                    bb_list.append(item_data)

        add_bb(p.get('btts_no', 0), p.get('btts_no'), 'Ambos Anotan (NO)')
        add_bb(p.get('btts', 0), p.get('btts'), 'Ambos Anotan (SÍ)')
        add_bb(p.get('home_clean_sheet', 0), p.get('home_clean_sheet'), f"Clean Sheet {loc}")
        add_bb(p.get('away_clean_sheet', 0), p.get('away_clean_sheet'), f"Clean Sheet {vis}")
        add_bb(p.get('under_2_5', 0), p.get('under_2_5'), '-2.5 Goles')
        add_bb(p.get('under_3_5', 0), p.get('under_3_5'), '-3.5 Goles')
        add_bb(p.get('over_1_5', 0), p.get('over_1_5'), '+1.5 Goles')
        add_bb(p.get('over_2_5', 0), p.get('over_2_5'), '+2.5 Goles')
        add_bb(p.get('over_3_5', 0), p.get('over_3_5'), '+3.5 Goles')
        add_bb(p.get('prob_over_0_5_ht', 0), p.get('prob_over_0_5_ht'), '+0.5 Goles HT')

        prob_gana = max(p.get('probs', [0,0,0])[0], p.get('probs', [0,0,0])[2])
        if prob_gana >= 0.90:
            sel_gana = p['local'] if p.get('probs', [0,0,0])[0] > p.get('probs', [0,0,0])[2] else p['visita']
            item_g = {'match': p, 'prob': prob_gana, 'sel': sel_gana, 'score': calcular_confidence_score(prob_gana, t_partidos)}
            ganadores.append(item_g)
        
        prob_doble = max(p.get('prob_1X', 0), p.get('prob_X2', 0))
        sel_doble = f"1X ({p['local']})" if p.get('prob_1X', 0) > p.get('prob_X2', 0) else f"X2 ({p['visita']})"
        item_d = {'match': p, 'prob': prob_doble, 'sel': sel_doble, 'score': calcular_confidence_score(prob_doble, t_partidos)}
        if es_sel_partido:
            selecciones_dobles.append(item_d)
        else:
            dobles.append(item_d)
        
        opciones_goles = [
            {'sel': 'Ambos Anotan', 'prob': p.get('btts', 0)}, {'sel': '+1.5 Goles', 'prob': p.get('over_1_5', 0)},
            {'sel': '+2.5 Goles', 'prob': p.get('over_2_5', 0)}, {'sel': '-3.5 Goles', 'prob': p.get('under_3_5', 0)}
        ]
        mejor_gol = max(opciones_goles, key=lambda x: x['prob'])
        item_gol = {'match': p, 'prob': mejor_gol['prob'], 'sel': mejor_gol['sel'], 'score': calcular_confidence_score(mejor_gol['prob'], t_partidos)}
        if es_sel_partido:
            selecciones_goles.append(item_gol)
        else:
            goles.append(item_gol)

        if p.get('btts', 0) > 0.80: 
            francotiradores.append({'match': p, 'prob': p.get('btts'), 'sel': 'Ambos Anotan (SÍ)', 'score': calcular_confidence_score(p.get('btts'), t_partidos)})
        
        # --- CÓRNERS ---
        corner_sel = None
        corner_prob = 0
        if p.get('over_9_5_corners', 0) > 0.75:
            corner_sel = '+9.5 Córners'
            corner_prob = p.get('over_9_5_corners')
        elif p.get('over_8_5_corners', 0) > 0.80:
            corner_sel = '+8.5 Córners'
            corner_prob = p.get('over_8_5_corners')
            
        if corner_sel:
            es_c = p.get('es_eliminatoria', False)
            sl = analyzer.get_team_stats(p['local'], p.get('local_id'), league_id=p.get('league_id'), es_eliminatoria=es_c, es_seleccion=es_sel_partido)
            sv = analyzer.get_team_stats(p['visita'], p.get('visita_id'), league_id=p.get('league_id'), es_eliminatoria=es_c, es_seleccion=es_sel_partido)
            promedio_str = f"L: {sl.get('corners_f', 0):.1f} - V: {sv.get('corners_f', 0):.1f}"
            quirofano_tactico.append({
                'match': p, 
                'prob': corner_prob, 
                'sel': f"{corner_sel} ({promedio_str})", 
                'score': calcular_confidence_score(corner_prob, t_partidos)
            })

        # --- REMATES ---
        shot_sel = None
        shot_prob = 0
        if p.get('over_26_5_shots', 0) > 0.75:
            shot_sel = '+26.5 Remates'
            shot_prob = p.get('over_26_5_shots')
        elif p.get('over_24_5_shots', 0) > 0.80:
            shot_sel = '+24.5 Remates'
            shot_prob = p.get('over_24_5_shots')

        if shot_sel:
            es_c = p.get('es_eliminatoria', False)
            sl = analyzer.get_team_stats(p['local'], p.get('local_id'), league_id=p.get('league_id'), es_eliminatoria=es_c, es_seleccion=es_sel_partido)
            sv = analyzer.get_team_stats(p['visita'], p.get('visita_id'), league_id=p.get('league_id'), es_eliminatoria=es_c, es_seleccion=es_sel_partido)
            promedio_remates_str = f"L: {sl.get('remates_f', 0):.1f} - V: {sv.get('remates_f', 0):.1f}"
            quirofano_tactico.append({
                'match': p,
                'prob': shot_prob,
                'sel': f"{shot_sel} ({promedio_remates_str})",
                'score': calcular_confidence_score(shot_prob, t_partidos)
            })

        # --- TARJETAS ---
        card_sel = None
        card_prob = 0
        if p.get('over_5_5_cards', 0) > 0.75:
            card_sel = '+5.5 Tarjetas'
            card_prob = p.get('over_5_5_cards')
        elif p.get('over_4_5_cards', 0) > 0.80:
            card_sel = '+4.5 Tarjetas'
            card_prob = p.get('over_4_5_cards')

        if card_sel:
            es_c = p.get('es_eliminatoria', False)
            sl = analyzer.get_team_stats(p['local'], p.get('local_id'), league_id=p.get('league_id'), es_eliminatoria=es_c, es_seleccion=es_sel_partido)
            sv = analyzer.get_team_stats(p['visita'], p.get('visita_id'), league_id=p.get('league_id'), es_eliminatoria=es_c, es_seleccion=es_sel_partido)
            promedio_str = f"L: {sl.get('tarjetas_f', 0):.1f} - V: {sv.get('tarjetas_f', 0):.1f}"
            
            ref_name = p.get('referee', 'Desconocido')
            ref_avg = p.get('ref_avg', 0.0)
            if ref_name != "Desconocido" and ref_avg > 0:
                promedio_str += f" | 👮 {ref_avg:.1f}T"
                
                if ref_avg >= 5.0 and card_prob > 0.80:
                    card_sel = f"🧨 MISIL: {card_sel}"

            quirofano_tactico.append({
                'match': p, 
                'prob': card_prob, 
                'sel': f"{card_sel} ({promedio_str})", 
                'score': calcular_confidence_score(card_prob, t_partidos)
            })
        
        dif_global = p.get('dif_global', 0)
        if p.get('es_eliminatoria') and (dif_global <= -2 or dif_global >= 2):
            quien_remonta = p['local'] if dif_global <= -2 else p['visita']
            radar_remontadas.append({
                'match': p, 'prob': 1.0, 'score': 1.0,
                'sel': f"🚨 Alerta Volatilidad: {quien_remonta} debe remontar {abs(dif_global)} goles"
            })

    mega_misiles.sort(key=lambda x: x['score'], reverse=True)
    bb_list.sort(key=lambda x: x['score'], reverse=True)
    selecciones_bb.sort(key=lambda x: x['score'], reverse=True)
    ganadores.sort(key=lambda x: x['score'], reverse=True)
    dobles.sort(key=lambda x: x['score'], reverse=True)
    selecciones_dobles.sort(key=lambda x: x['score'], reverse=True)
    goles.sort(key=lambda x: x['score'], reverse=True)
    selecciones_goles.sort(key=lambda x: x['score'], reverse=True)
    francotiradores.sort(key=lambda x: x['score'], reverse=True)
    quirofano_tactico.sort(key=lambda x: x['score'], reverse=True)

    seleccionados = set()
    for item in bb_list[:30]: seleccionados.add(item['match'].get('_id_interno'))
    for item in selecciones_bb[:15]: seleccionados.add(item['match'].get('_id_interno'))
    for item in ganadores[:30]: seleccionados.add(item['match'].get('_id_interno'))
    for item in dobles[:30]: seleccionados.add(item['match'].get('_id_interno'))
    for item in selecciones_dobles[:15]: seleccionados.add(item['match'].get('_id_interno'))
    for item in goles[:30]: seleccionados.add(item['match'].get('_id_interno'))
    for item in selecciones_goles[:15]: seleccionados.add(item['match'].get('_id_interno'))
    for item in quirofano_tactico[:15]: seleccionados.add(item['match'].get('_id_interno'))
    for item in francotiradores[:15]: seleccionados.add(item['match'].get('_id_interno'))
    for item in radar_remontadas: seleccionados.add(item['match'].get('_id_interno'))
    for item in mega_misiles[:30]: seleccionados.add(item['match'].get('_id_interno'))

    cache_bajas = {}
    if bot_api_client:
        fixtures_a_consultar = set()
        for p in partidos_validos:
            if p.get('_id_interno') in seleccionados and p.get('fixture_id'):
                fixtures_a_consultar.add(p['fixture_id'])
                
        print(f"🛡️ [ANTI-BAJAS] Consultando lesiones para {len(fixtures_a_consultar)} partidos TOP...")
        for fix_id in fixtures_a_consultar:
            alerta = obtener_alertas_bajas(fix_id)
            if alerta:
                cache_bajas[fix_id] = alerta
            time.sleep(0.5) 

    etiqueta_ventana = f" | {titulo_bloque}" if titulo_bloque else ""
    msg = f"💎 ━━ *MENÚ BENDER V4.0 (Estadístico): {fecha_bloque}{etiqueta_ventana}* ━━ 💎\n\n"
    msg += f"📅 _Generado: {hora_generacion}_\n\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if selecciones_bb or selecciones_goles or selecciones_dobles:
        msg += "🌍 *SELECCIONES Y FECHA FIFA (Bloque Especial)* 🌍\n\n"
        if selecciones_bb:
            msg += "_🧩 Piezas Bet Builder de Selecciones:_\n"
            for i, item in enumerate(selecciones_bb[:10], 1):
                m = item['match']
                bajas_str = cache_bajas.get(m.get('fixture_id'), "")
                msg += f"  *{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{bajas_str} | 🧩 *{item['sel']}* ({item['prob']:.0%})\n"
            msg += "\n"
        if selecciones_goles:
            msg += "_🔥 Mercados de Goles en Selecciones:_\n"
            for i, item in enumerate(selecciones_goles[:10], 1):
                m = item['match']
                bajas_str = cache_bajas.get(m.get('fixture_id'), "")
                msg += f"  *{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{bajas_str} | 🔥 *{item['sel']}* ({item['prob']:.0%})\n"
            msg += "\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if radar_remontadas:
        msg += "⚔️ *RADAR DE REMONTADAS (Alerta Mata-Mata)* ⚔️\n\n"
        for i, item in enumerate(radar_remontadas, 1):
            m = item['match']
            msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']} | {item['sel']}\n"
            msg += f"   🔥 _(Táctica rota: Sugerencia de Altas o Córners)_\n\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    msg += "🧱 *PIEZAS BET BUILDER (Filtro Titanio > 80%)*\n\n"
    if bb_list:
        for i, item in enumerate(bb_list[:30], 1): 
            m = item['match']
            es_mata_mata = " ⚔️" if m.get('es_eliminatoria') else ""
            bajas_str = cache_bajas.get(m.get('fixture_id'), "")
            msg += f"*{i}.* ⚽ {m['bandera']} {m['pais_nombre']} - {m['local']} vs {m['visita']}{es_mata_mata}{m['alerta_fatiga']}{bajas_str} | 🧩 *{item['sel']}* ({item['prob']:.0%})\n\n"
    else:
        msg += "_Ninguna variable pura superó el 80% hoy en clubes._\n\n"
    
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += "🏆 *TOP 30 - GANADOR DIRECTO*\n\n"
    if ganadores:
        for i, item in enumerate(ganadores[:30], 1):
            m = item['match']
            es_mata_mata = " ⚔️" if m.get('es_eliminatoria') else ""
            bajas_str = cache_bajas.get(m.get('fixture_id'), "")
            msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{es_mata_mata}{m['alerta_fatiga']}{bajas_str} | 🎯 Gana *{item['sel']}* ({item['prob']:.0%})\n"
            msg += f"   📈 Forma Global: L `{m.get('home_form')}` ({m.get('home_ppg')}p) | V `{m.get('away_form')}` ({m.get('away_ppg')}p)\n"
            msg += f"   🏟️ Casa/Fuera: L `{m.get('home_venue_form')}` ({m.get('home_venue_ppg')}p) | V `{m.get('away_venue_form')}` ({m.get('away_venue_ppg')}p)\n\n"
    else:
        msg += "_Ningún equipo superó el umbral estricto del 90% hoy. Peligro de varianza._\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += "🛡️ *TOP 30 - DOBLE OPORTUNIDAD*\n\n"
    for i, item in enumerate(dobles[:30], 1):
        m = item['match']
        es_mata_mata = " ⚔️" if m.get('es_eliminatoria') else ""
        bajas_str = cache_bajas.get(m.get('fixture_id'), "")
        msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{es_mata_mata}{m['alerta_fatiga']}{bajas_str} | 🛡️ *{item['sel']}* ({item['prob']:.0%})\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += "🔥 *TOP 30 - MERCADOS DE GOLES*\n\n"
    for i, item in enumerate(goles[:30], 1):
        m = item['match']
        es_mata_mata = " ⚔️" if m.get('es_eliminatoria') else ""
        bajas_str = cache_bajas.get(m.get('fixture_id'), "")
        msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{es_mata_mata}{m['alerta_fatiga']}{bajas_str} | 🔥 *{item['sel']}* ({item['prob']:.0%})\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += "🚩 *EL QUIRÓFANO TÁCTICO (Córners, Remates y Tarjetas)*\n\n"
    if quirofano_tactico:
        for i, item in enumerate(quirofano_tactico[:15], 1):
            m = item['match']
            bajas_str = cache_bajas.get(m.get('fixture_id'), "")
            msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{bajas_str} | 🧩 *{item['sel']}* ({item['prob']:.0%})\n\n"
    else:
        msg += "_Sin opciones viables de Córners/Remates/Tarjetas hoy._\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += "🎯 *LOS FRANCOTIRADORES (Ambos Anotan - SÍ)*\n\n"
    if francotiradores:
        for i, item in enumerate(francotiradores[:15], 1):
            m = item['match']
            bajas_str = cache_bajas.get(m.get('fixture_id'), "")
            msg += f"*{i}.* ⚽ {m['bandera']} {m['local']} vs {m['visita']}{m['alerta_fatiga']}{bajas_str} | 🎯 *{item['sel']}* ({item['prob']:.0%})\n\n"
    else:
        msg += "_Ningún partido superó el 80% de BTTS hoy._\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += "💣 *MEGA-MISILES INTERNOS (SGBB Pre-calculados)*\n\n"
    if mega_misiles:
        for i, item in enumerate(mega_misiles[:30], 1):
            m = item['match']
            es_mata_mata = " ⚔️" if m.get('es_eliminatoria') else ""
            bajas_str = cache_bajas.get(m.get('fixture_id'), "")
            msg += f"*{i}.* ⚽ {m['bandera']} {m['pais_nombre']} - {m['local']} vs {m['visita']}{es_mata_mata}{bajas_str} | 🧩 *{item['sel']}* ({item['prob']:.0%})\n\n"
    else:
        msg += "_Ninguna combinación SGBB superó el umbral hoy._\n\n"

    max_len = 3900 
    if len(msg) > max_len:
        mensajes_a_enviar = []
        bloques = msg.split("\n\n")
        chunk_actual = ""
        for bloque in bloques:
            if len(chunk_actual) + len(bloque) + 2 > max_len:
                mensajes_a_enviar.append(chunk_actual)
                chunk_actual = bloque + "\n\n"
            else:
                chunk_actual += bloque + "\n\n"
        if chunk_actual.strip():
            mensajes_a_enviar.append(chunk_actual)
        for chunk in mensajes_a_enviar:
            enviar_mensaje_telegram(chunk, token_override=token_override)
            time.sleep(1.5)
    else:
        enviar_mensaje_telegram(msg, token_override=token_override)
        
    return len(partidos_validos), seleccionados


# ==========================================
# 🩸 LA AUTOPSIA TÁCTICA (FÚTBOL V4.0 - Formato Dashboard Optimizado)
# ==========================================
def _procesar_y_enviar_autopsia_futbol(proyecciones_dict, titulo_bloque, fecha_bloque, analyzer, seleccionados, token_override=None):
    agrupado_por_pais = agrupar_por_pais(proyecciones_dict)
    
    mensajes_a_enviar = []
    mensaje_actual = ""
    max_len = 3900
    
    fechas_incluidas = sorted({
        p.get("fecha_str", "Sin fecha")
        for ligas in agrupado_por_pais.values()
        for proyecciones in ligas.values()
        for p in proyecciones
    })
    
    fechas_texto = ", ".join(fechas_incluidas)
    
    header_general = (f"🩸 *LA AUTOPSIA TÁCTICA (V4.0)*\n📅 _Fecha: {fechas_texto}_\n\n")
    mensaje_actual = header_general
    
    for pais, ligas_del_pais in sorted(agrupado_por_pais.items()):
        bandera = BANDERAS.get(pais, "🏴")
        es_seleccion = (pais == "World")
        
        for liga, proyecciones in sorted(ligas_del_pais.items()):
            
            partidos_validos = []
            for p in proyecciones:
                if p.get('_id_interno') not in seleccionados:
                    continue

                es_copa = p.get('es_eliminatoria', False)
                s_l = analyzer.get_team_stats(p['local'], p.get('local_id'), league_id=p.get('league_id'), es_eliminatoria=es_copa, es_seleccion=es_seleccion)
                s_v = analyzer.get_team_stats(p['visita'], p.get('visita_id'), league_id=p.get('league_id'), es_eliminatoria=es_copa, es_seleccion=es_seleccion)
                
                min_partidos = 3 if es_copa else 5
                
                if s_l.get('count', 0) >= min_partidos and s_v.get('count', 0) >= min_partidos:
                    partidos_validos.append((p, s_l, s_v))
            
            if not partidos_validos:
                continue

            header_liga = f"📌 {bandera} *{pais} - {liga}*\n\n"
            
            if len(mensaje_actual) + len(header_liga) > max_len:
                if mensaje_actual.strip():
                    mensajes_a_enviar.append(mensaje_actual)
                mensaje_actual = header_liga
            else:
                mensaje_actual += header_liga
            
            for p, s_l, s_v in partidos_validos:
                es_mata_mata = " ⚔️ [MATA-MATA]" if p.get('es_eliminatoria') else ""
                
                ph = p.get('probs', [0,0,0])[0]
                pd_draw = p.get('probs', [0,0,0])[1]
                pa = p.get('probs', [0,0,0])[2]
                
                p_1x = p.get('prob_1X', ph + pd_draw)
                p_12 = p.get('prob_12', ph + pa)
                p_x2 = p.get('prob_X2', pa + pd_draw)

                bloque_partido = f"⚽ *{p['local']} vs {p['visita']}*\n"
                bloque_partido += f"📅 `{p.get('fecha_str', '')}` | 🕒 `{p.get('hora', '')}`{es_mata_mata}\n"
                bloque_partido += f"📊 *RESULTADO* ➔ 1X2: L ({ph:.0%}) | E ({pd_draw:.0%}) | V ({pa:.0%})\n"
                bloque_partido += f"🛡️ *DOBLE OP.* ➔ 1X ({p_1x:.0%}) | 12 ({p_12:.0%}) | X2 ({p_x2:.0%})\n"
                bloque_partido += f"🎯 *BTTS* ➔ Sí ({p.get('btts', 0):.0%}) | No ({p.get('btts_no', 0):.0%}) | ⏱️ +0.5 HT: {p.get('prob_over_0_5_ht', 0):.0%}\n"
                bloque_partido += f"🔥 *ALTAS* ➔ +1.5 ({p.get('over_1_5', 0):.0%}) | +2.5 ({p.get('over_2_5', 0):.0%}) | +3.5 ({p.get('over_3_5', 0):.0%})\n"
                bloque_partido += f"⚽ *BAJAS* ➔ -2.5 ({p.get('under_2_5', 0):.0%}) | -3.5 ({p.get('under_3_5', 0):.0%}) | -4.5 ({p.get('under_4_5', 0):.0%})\n"
                bloque_partido += f"🧱 *PORT. A CERO* ➔ L ({p.get('home_clean_sheet', 0):.0%}) | V ({p.get('away_clean_sheet', 0):.0%})\n"
                bloque_partido += f"📈 *FORMA (Global)* ➔ L [{p.get('home_form', 'N/A')}] ({p.get('home_ppg', 0)}p) | V [{p.get('away_form', 'N/A')}] ({p.get('away_ppg', 0)}p)\n"
                bloque_partido += f"🏟️ *FORMA (H/A)* ➔ L [{p.get('home_venue_form', 'N/A')}] ({p.get('home_venue_ppg', 0)}p) | V [{p.get('away_venue_form', 'N/A')}] ({p.get('away_venue_ppg', 0)}p)\n"
                bloque_partido += f"📐 *PROM. GOLES ({s_l.get('count',0)}p|{s_v.get('count',0)}p)* ➔ L ({s_l.get('goles_favor', 0):.1f}F-{s_l.get('goles_contra', 0):.1f}C) | V ({s_v.get('goles_favor', 0):.1f}F-{s_v.get('goles_contra', 0):.1f}C)\n"
                
                if s_l.get('has_details') or s_v.get('has_details'):
                    bloque_partido += f"📋 *RADIOGRAFÍA* ➔ Remates: L ({s_l.get('remates_f', 0):.1f}) | V ({s_v.get('remates_f', 0):.1f})\n"
                    bloque_partido += f"🎯 *REMATES (Poiss)* ➔ +24.5 ({p.get('over_24_5_shots', 0):.0%}) | +26.5 ({p.get('over_26_5_shots', 0):.0%})\n"
                    bloque_partido += f"🚩 *CÓRNERS (Prom)* ➔ L ({s_l.get('corners_f', 0):.1f}) | V ({s_v.get('corners_f', 0):.1f})\n"
                    bloque_partido += f"🎯 *CÓRNERS (Poiss)* ➔ +8.5 ({p.get('over_8_5_corners', 0):.0%}) | +9.5 ({p.get('over_9_5_corners', 0):.0%})\n"
                    
                    bloque_partido += f"🟨 *TARJETAS (Prom)* ➔ L ({s_l.get('tarjetas_f', 0):.1f}) | V ({s_v.get('tarjetas_f', 0):.1f})\n"
                    ref_name = p.get('referee', 'Desconocido')
                    if ref_name != "Desconocido":
                        ref_avg = p.get('ref_avg', 0.0)
                        avg_str = f" ({ref_avg:.1f}xP)" if ref_avg > 0 else ""
                        bloque_partido += f"👮 *ÁRBITRO* ➔ {ref_name}{avg_str}\n"
                    
                    bloque_partido += f"🎯 *TARJETAS (Poiss)* ➔ +3.5 ({p.get('over_3_5_cards', 0):.0%}) | +4.5 ({p.get('over_4_5_cards', 0):.0%})\n"

                bloque_partido += "\n\n"

                if len(mensaje_actual) + len(bloque_partido) > max_len:
                    if mensaje_actual.strip():
                        mensajes_a_enviar.append(mensaje_actual)
                    mensaje_actual = bloque_partido
                else:
                    mensaje_actual += bloque_partido

    cierre_reporte = "━"*24 + "\n\n✅ *FIN DE LA AUTOPSIA* ✅\n\n"
    if len(mensaje_actual) + len(cierre_reporte) > max_len:
        if mensaje_actual.strip():
            mensajes_a_enviar.append(mensaje_actual)
        mensajes_a_enviar.append(cierre_reporte)
    elif mensaje_actual.strip() and mensaje_actual != header_general:
        mensaje_actual += cierre_reporte
        mensajes_a_enviar.append(mensaje_actual)
        
    for msg in mensajes_a_enviar:
        enviar_mensaje_telegram(msg, token_override=token_override)
        time.sleep(1.5)

def enviar_bloque_reportes(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    agrupado_por_fecha = {}
    for key, projs in proyecciones_dict.items():
        for p in projs:
            fecha = p.get('fecha_str', 'Sin Fecha')
            agrupado_por_fecha.setdefault(fecha, {}).setdefault(key, []).append(p)
            
    total_validos_global = 0
    for fecha in sorted(agrupado_por_fecha.keys()):
        procesados, seleccionados = _procesar_y_enviar_bloque_futbol(agrupado_por_fecha[fecha], titulo_bloque, fecha, analyzer, token_override)
        
        total_validos_global += (procesados or 0)
        
        if procesados:
            time.sleep(2) 
 
        _procesar_y_enviar_autopsia_futbol(agrupado_por_fecha[fecha], titulo_bloque, fecha, analyzer, seleccionados, token_override)
        
        time.sleep(2)
            
    if total_validos_global == 0:
        enviar_mensaje_telegram(f"⚠️ No hay partidos con historial maduro para este bloque.", token_override=token_override)


# ==========================================
# 🏀 MÓDULO BÁSQUETBOL (AUTOPSIA V3.0)
# ==========================================
def _generar_y_enviar_menu_basket(proyecciones_dict, etiqueta_dia, analyzer, token_override=None):
    basket_lista = []
    
    for pais, ligas in agrupar_por_pais(proyecciones_dict).items():
        for liga, projs in ligas.items():
            for p in projs:
                s_l = analyzer.get_basketball_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_basketball_team_stats(p['visita'], p.get('visita_id'))

                if s_l.get('count', 0) >= 5 and s_v.get('count', 0) >= 5:
                    prob_gana = max(p['prob_home'], p['prob_away'])
                    seleccion = p['local'] if p['prob_home'] > p['prob_away'] else p['visita']
                    total_partidos = s_l.get('count', 0) + s_v.get('count', 0)
                    score = calcular_confidence_score(prob_gana, total_partidos)
                    
                    basket_lista.append({'match': p, 'prob': prob_gana, 'seleccion': seleccion, 'score': score})
                
    if not basket_lista:
        return False

    tz_chile = pytz.timezone('America/Santiago')
    hora_generacion = datetime.now(tz_chile).strftime("%d/%m/%Y %H:%M")

    mensaje_resumen = f"💎 ━━ *MENÚ BENDER V3.0 BASKET: {etiqueta_dia}* ━━ 💎\n\n"
    mensaje_resumen += f"📅 _Generado: {hora_generacion}_\n\n"
    mensaje_resumen += "━"*24 + "\n\n"

    basket_lista.sort(key=lambda x: x['score'], reverse=True)
    for i, item in enumerate(basket_lista[:15], 1):
        p = item['match']
        mensaje_resumen += f"*{i}.* 🏀 {p['local']} vs {p['visita']} | 🕒 {p.get('hora', '')}\n"
        mensaje_resumen += f"   🎯 *Pick:* Gana {item['seleccion']} ({item['prob']:.0%}) | 🔥 Pts: `{p.get('puntos_proyectados', 0):.1f}`\n"
        mensaje_resumen += f"   📈 Forma Global: L `{p.get('home_form', 'N/A')}` | V `{p.get('away_form', 'N/A')}`\n\n"

    mensaje_resumen += "━"*24 + "\n\n"
    mensaje_resumen += "✅ *FIN DEL REPORTE* ✅\n\n"

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
        aviso = "💎 ━━ *MENÚ DE MEJORES PICKS* ━━ 💎\n\n" + "━"*22 + "\n\n⚠️ _No hay partidos con historial maduro para HOY ni MAÑANA._\n\n" + "━"*22 + "\n\n✅ *FIN DEL REPORTE* ✅\n\n"
        enviar_mensaje_telegram(aviso, token_override=token_override)

def _procesar_y_enviar_autopsia_basket(proyecciones_dict, titulo_bloque, fecha_bloque, analyzer, token_override=None):
    agrupado_por_pais = agrupar_por_pais(proyecciones_dict)
    
    mensajes_a_enviar = []
    mensaje_actual = ""
    max_len = 3900
    
    for pais, ligas_del_pais in sorted(agrupado_por_pais.items()):
        bandera = BANDERAS.get(pais, "🏴")
        
        for liga, proyecciones in sorted(ligas_del_pais.items()):
            
            partidos_validos = []
            for p in proyecciones:
                s_l = analyzer.get_basketball_team_stats(p['local'], p.get('local_id'))
                s_v = analyzer.get_basketball_team_stats(p['visita'], p.get('visita_id'))
                if s_l.get('count', 0) >= 5 and s_v.get('count', 0) >= 5:
                    partidos_validos.append((p, s_l, s_v))
            
            if not partidos_validos:
                continue

            header_liga = f"🏀 *LA AUTOPSIA TÁCTICA (BASKET V3.0)*\n📌 {bandera} *{pais} - {liga}*\n\n"
            
            if len(mensaje_actual) + len(header_liga) > max_len:
                mensajes_a_enviar.append(mensaje_actual)
                mensaje_actual = header_liga
            else:
                if not mensaje_actual:
                    mensaje_actual = header_liga
                else:
                    mensaje_actual += "\n" + header_liga
            
            for p, s_l, s_v in partidos_validos:
                bloque_partido = f"🏀 *{p['local']} vs {p['visita']}*\n"
                bloque_partido += f"📅 `{p.get('fecha_str', '')}` | 🕒 `{p.get('hora', '')}`\n"
                bloque_partido += "━━━━━━━━━━━━━━━━━━━━\n"
                bloque_partido += f"📊 *VICTORIA* ➔ L ({p['prob_home']:.0%}) | V ({p['prob_away']:.0%})\n"
                bloque_partido += f"🎯 *PUNTOS PROYECTADOS* ➔ {p['puntos_proyectados']:.1f} pts\n"
                bloque_partido += "─"*20 + "\n"
                bloque_partido += f"📈 *FORMA (Global)* ➔ L [{p.get('home_form')}] ({p.get('home_ppg')}p) | V [{p.get('away_form')}] ({p.get('away_ppg')}p)\n"
                bloque_partido += f"🏟️ *FORMA (H/A)* ➔ L [{p.get('home_venue_form')}] ({p.get('home_venue_ppg')}p) | V [{p.get('away_venue_form')}] ({p.get('away_venue_ppg')}p)\n"

                count_l = s_l.get('count', 0)
                count_v = s_v.get('count', 0)
                bloque_partido += f"📐 *PROM. PTS ({count_l}p|{count_v}p)* ➔ L ({s_l.get('puntos_favor', 0):.1f}F-{s_l.get('puntos_contra', 0):.1f}C) | V ({s_v.get('puntos_favor', 0):.1f}F-{s_v.get('puntos_contra', 0):.1f}C)\n"
                bloque_partido += "\n\n"

                if len(mensaje_actual) + len(bloque_partido) > max_len:
                    mensajes_a_enviar.append(mensaje_actual)
                    mensaje_actual = f"🏀 *LA AUTOPSIA TÁCTICA (Cont.)*\n📌 {bandera} *{pais} - {liga}*\n\n" + bloque_partido
                else:
                    mensaje_actual += bloque_partido

    if mensaje_actual.strip():
        mensajes_a_enviar.append(mensaje_actual)
        
    for msg in mensajes_a_enviar:
        enviar_mensaje_telegram(msg, token_override=token_override)
        time.sleep(1.5)

def enviar_bloque_reportes_basket(proyecciones_dict, titulo_bloque, analyzer, token_override=None):
    agrupado_por_fecha = {}
    for key, projs in proyecciones_dict.items():
        for p in projs:
            fecha = p.get('fecha_str', 'Sin Fecha')
            agrupado_por_fecha.setdefault(fecha, {}).setdefault(key, []).append(p)
            
    for fecha in sorted(agrupado_por_fecha.keys()):
        _procesar_y_enviar_autopsia_basket(agrupado_por_fecha[fecha], titulo_bloque, fecha, analyzer, token_override)
        time.sleep(2)
        
    enviar_resumen_mejores_apuestas_basket(proyecciones_dict, titulo_bloque, analyzer, token_override)
