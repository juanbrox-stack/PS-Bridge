import streamlit as st
import pandas as pd
import io

# --- CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Turaco PS Helper PRO", page_icon="🐦", layout="wide")

def normalizar_sku(serie):
    """Limpia espacios, mayúsculas y quita ceros a la izquierda."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave):
    """Busca una columna de forma flexible por palabras clave."""
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

# Inicializar estados de la sesión para persistencia entre pestañas
if 'df_previa' not in st.session_state: st.session_state.df_previa = None
if 'df_revisado' not in st.session_state: st.session_state.df_revisado = None

st.title("🐦 Turaco PrestaShop Manager - Edición Profesional")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar y Auditar", "📦 FASE 2: Generar Carga Final"])

# --- FASE 1: IDENTIFICAR Y REVISAR ---
with tab1:
    st.header("1. Buscador de Novedades")
    c1, c2, c3 = st.columns(3)
    with c1: f_ps = st.file_uploader("BBDD PrestaShop (CSV/XLSX)", type=['csv', 'xlsx'], key="u_ps")
    with c2: f_amz = st.file_uploader("Listing Amazon (TXT/XLSX)", type=['txt', 'xlsx'], key="u_amz")
    with c3: f_plan = st.file_uploader("Plan Lanzamiento (XLSX)", type=['xlsx'], key="u_plan")

    if all([f_ps, f_amz, f_plan]):
        if st.button("🚀 Ejecutar Cruce de Novedades"):
            try:
                # Lectura de archivos
                df_ps = pd.read_csv(f_ps, sep=None, engine='python', dtype=str) if f_ps.name.endswith('.csv') else pd.read_excel(f_ps, dtype=str)
                df_amz = pd.read_excel(f_amz, dtype=str) if f_amz.name.endswith('.xlsx') else pd.read_csv(f_amz, sep='\t', encoding='latin1', dtype=str)
                df_plan = pd.read_excel(f_plan, dtype=str)

                for df in [df_ps, df_amz, df_plan]: df.columns = df.columns.str.lower().str.strip()

                # Normalización y Cruce
                df_ps['sku_norm'] = normalizar_sku(df_ps['reference'])
                df_amz['sku_norm'] = normalizar_sku(df_amz['seller-sku'])
                df_plan['sku_norm'] = normalizar_sku(df_plan['sku'])

                estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto"]
                df_plan_f = df_plan[df_plan['estado'].isin(estados_ok)]

                skus_en_ps = df_ps['sku_norm'].unique()
                df_nov = df_amz[~df_amz['sku_norm'].isin(skus_en_ps)]
                
                df_final = pd.merge(df_nov, df_plan_f[['sku_norm', 'estado', 'notas']], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    df_final.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_final
                else: st.warning("No se encontraron novedades.")
            except Exception as e: st.error(f"Error en el cruce: {e}")

    if st.session_state.df_previa is not None:
        st.divider()
        solo_notas = st.toggle("🎯 Mostrar solo productos con avisos en 'Notas'")
        df_a_mostrar = st.session_state.df_previa
        if solo_notas: df_a_mostrar = df_a_mostrar[df_a_mostrar['notas'].fillna('').str.strip() != ""]

        df_editado = st.data_editor(df_a_mostrar, column_config={
                "Seleccionado": st.column_config.CheckboxColumn("¿Procesar?"),
                "notas": st.column_config.TextColumn("Notas Plan", width="large"),
                "sku_norm": None
            }, disabled=["seller-sku", "asin1", "estado", "notas"], hide_index=True, use_container_width=True)

        if st.button("✅ Confirmar Selección y Pasar a Fase 2"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success(f"¡Hecho! {len(st.session_state.df_revisado)} productos validados.")

# --- FASE 2: GENERADOR DE CARGA ---
with tab2:
    st.header("2. Generador de Carga PrestaShop")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Completa la Fase 1 primero.")
    else:
        c1, c2 = st.columns(2)
        with c1: f_keepa = st.file_uploader("Exportación Keepa (XLSX)", type=['xlsx'])
        with c2: 
            f_img = st.file_uploader("Exportación Imágenes (CSV)", type=['csv'])
            f_cats = st.file_uploader("Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar Fichero Final"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_csv(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)
                    df_l = st.session_state.df_revisado

                    for d in [df_k, df_i, df_c]: d.columns = d.columns.str.lower().str.strip()

                    # Identificación con seguridad
                    c_asin_k = buscar_columna(df_k, ['asin'])
                    c_ean_k = buscar_columna(df_k, ['ean', 'código'])
                    c_tit_k = buscar_columna(df_k, ['título', 'title', 'nombre'])
                    c_cat_k = buscar_columna(df_k, ['categoría', 'category'])
                    
                    if not c_asin_k: st.error("❌ No se encontró columna ASIN en Keepa."); st.stop()
                    if not c_tit_k: st.error("❌ No se encontró columna Título en Keepa."); st.stop()

                    c_asin_l = 'asin1' if 'asin1' in df_l.columns else 'asin'
                    df_m = pd.merge(df_l, df_k, left_on=c_asin_l, right_on=c_asin_k, how='inner')

                    if df_m.empty: st.error("❌ No hay coincidencias de ASIN entre Fase 1 y Keepa."); st.stop()

                    res = pd.DataFrame()
                    res['Reference #'] = df_m['seller-sku']
                    res['Name *'] = df_m[c_tit_k].str.slice(0, 128)
                    res['EAN13'] = df_m[c_ean_k] if c_ean_k else ""
                    
                    # Características para Descripción
                    cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                    res['Description'] = df_m[cols_car].fillna('').agg(' '.join, axis=1).str.slice(0, 2000) if cols_car else "Sin descripción"

                    # Cruce de Imágenes Flexible
                    c_ref_img = buscar_columna(df_i, ['reference', 'sku', 'referencia'])
                    if c_ref_img:
                        df_i['urls'] = df_i.drop(columns=[c_ref_img], errors='ignore').fillna('').apply(
                            lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                        res = pd.merge(res, df_i[[c_ref_img, 'urls']].drop_duplicates(c_ref_img), 
                                       left_on='Reference #', right_on=c_ref_img, how='left')
                        res.rename(columns={'urls': 'Image URLs (x,y,z...)'}, inplace=True)
                    else: res['Image URLs (x,y,z...)'] = ""

                    # Campos fijos finales
                    res['Active (0/1)'] = "1"
                    res['Price tax included'] = "999"
                    res['Supplier'] = 'Cecotec'
                    res['Manufacturer'] = 'Cecotec'

                    csv_buf = io.StringIO()
                    res.to_csv(csv_buf, index=False, sep=',', encoding='utf-8-sig')
                    st.success(f"✅ ¡ÉXITO! {len(res)} productos procesados.")
                    st.download_button("⬇️ Descargar CSV Final", csv_buf.getvalue(), "subida_final.csv", "text/csv")
                except Exception as e: st.error(f"Error detallado en Fase 2: {e}")