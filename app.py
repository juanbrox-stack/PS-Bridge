import streamlit as st
import pandas as pd
import io
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Turaco PS Helper PRO", page_icon="🐦", layout="wide")

def normalizar_sku(serie):
    """Elimina espacios, mayúsculas y ceros iniciales para cruces precisos."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave):
    """Busca columnas de forma flexible ignorando mayúsculas y espacios."""
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

# Persistencia de datos entre pestañas
if 'df_revisado' not in st.session_state: st.session_state.df_revisado = None
if 'df_previa' not in st.session_state: st.session_state.df_previa = None

st.title("🐦 Turaco PrestaShop Assistant")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar y Auditar", "📦 FASE 2: Generar Carga Final"])

# --- FASE 1: IDENTIFICACIÓN ---
with tab1:
    st.header("Auditoría de Novedades")
    c1, c2, c3 = st.columns(3)
    with c1: f_ps = st.file_uploader("BBDD PrestaShop", type=['csv', 'xlsx'], key="ps_vfinal")
    with c2: f_amz = st.file_uploader("Listing Amazon", type=['txt', 'xlsx'], key="amz_vfinal")
    with c3: f_plan = st.file_uploader("Plan Lanzamiento", type=['xlsx'], key="plan_vfinal")

    if all([f_ps, f_amz, f_plan]):
        if st.button("🚀 Cruce de Novedades"):
            try:
                # Lectura flexible según formato
                df_ps = pd.read_csv(f_ps, sep=None, engine='python', dtype=str) if f_ps.name.endswith('.csv') else pd.read_excel(f_ps, dtype=str)
                df_amz = pd.read_excel(f_amz, dtype=str) if f_amz.name.endswith('.xlsx') else pd.read_csv(f_amz, sep='\t', encoding='latin1', dtype=str)
                df_plan = pd.read_excel(f_plan, dtype=str)

                for d in [df_ps, df_amz, df_plan]: d.columns = d.columns.str.lower().str.strip()

                # Normalización de SKUs
                df_ps['sku_norm'] = normalizar_sku(df_ps['reference'])
                df_amz['sku_norm'] = normalizar_sku(df_amz['seller-sku'])
                df_plan['sku_norm'] = normalizar_sku(df_plan['sku'])

                # Filtro por estados aprobados
                estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto"]
                df_plan_f = df_plan[df_plan['estado'].isin(estados_ok)]

                skus_en_ps = df_ps['sku_norm'].unique()
                df_nov = df_amz[~df_amz['sku_norm'].isin(skus_en_ps)]
                
                # Cruce final con Plan
                df_final = pd.merge(df_nov, df_plan_f[['sku_norm', 'notas']], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    c_asin = buscar_columna(df_final, ['asin'])
                    c_name = buscar_columna(df_final, ['item-name', 'title'])
                    df_viz = df_final[['seller-sku', c_name, c_asin, 'notas']].copy()
                    df_viz.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_viz
                else: st.warning("No hay novedades.")
            except Exception as e: st.error(f"Error: {e}")

    if st.session_state.df_previa is not None:
        solo_notas = st.toggle("🎯 Mostrar solo productos con Notas")
        df_disp = st.session_state.df_previa
        if solo_notas: df_disp = df_disp[df_disp['notas'].fillna('').str.strip() != ""]

        df_editado = st.data_editor(df_disp, hide_index=True, use_container_width=True)

        if st.button("✅ Confirmar Selección"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success("Registros guardados en memoria. Ve a la pestaña 'FASE 2' arriba.")

# --- FASE 2: GENERADOR ---
with tab2:
    st.header("Generador de Carga PrestaShop")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Debes confirmar la selección en la Fase 1 primero.")
    else:
        st.write(f"Trabajando con **{len(st.session_state.df_revisado)}** productos validados.")
        c1, c2 = st.columns(2)
        with c1: f_keepa = st.file_uploader("Keepa (XLSX)", type=['xlsx'])
        with c2: 
            f_img = st.file_uploader("Imágenes (CSV)", type=['csv'])
            f_cats = st.file_uploader("Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar Fichero Final"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_csv(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)
                    df_l = st.session_state.df_revisado

                    for d in [df_k, df_i, df_c]: d.columns = d.columns.str.lower().str.strip()

                    # Mapeo de columnas dinámicas
                    c_asin_k = buscar_columna(df_k, ['asin'])
                    c_tit_k = buscar_columna(df_k, ['título', 'title']) # Columna B
                    c_cat_sub = buscar_columna(df_k, ['subcategoría']) # Subcategoría
                    c_map_amz = buscar_columna(df_c, ['amazon', 'origen'])
                    c_map_ps = buscar_columna(df_c, ['prestashop', 'destino'])
                    
                    c_asin_l = buscar_columna(df_l, ['asin'])
                    
                    # Cruce Fase 1 + Keepa
                    df_m = pd.merge(df_l, df_k, left_on=c_asin_l, right_on=c_asin_k, how='inner')

                    # --- VALIDACIÓN DE CATEGORÍAS (NOVEDAD) ---
                    subcats_keepa = df_m[c_cat_sub].unique()
                    subcats_mapeadas = df_c[c_map_amz].str.lower().str.strip().unique()
                    faltantes = [str(cat) for cat in subcats_keepa if str(cat).lower().strip() not in subcats_mapeadas]
                    
                    if faltantes:
                        st.error("⚠️ ERROR: Subcategorías de Keepa no encontradas en tu Excel de Mapeo:")
                        st.write(faltantes)
                        st.warning("Añade estas categorías a 'ps_categories.xlsx' y vuelve a subir el archivo.")
                        st.stop() # Detenemos el proceso para evitar errores en la carga

                    # --- CONSTRUCCIÓN ---
                    final = pd.DataFrame()
                    final['Product ID'] = range(900001, 900001 + len(df_m))
                    final['Active (0/1)'] = "1"
                    final['Name *'] = df_m[c_tit_k].str.slice(0, 128) # Nombre desde Título Keepa
                    
                    # Mapeo de Categoría
                    mapeo = pd.Series(df_c[c_map_ps].values, index=df_c[c_map_amz].str.lower().str.strip()).to_dict()
                    final['Categories (x,y,z...)'] = df_m[c_cat_sub].apply(lambda x: mapeo.get(str(x).lower().strip(), x))
                    
                    final['Price tax included'] = "999"
                    final['Tax rules ID'] = "1"
                    final['Reference #'] = df_m['seller-sku']
                    final['Supplier reference #'] = df_m['seller-sku']
                    final['Supplier'] = "Cecotec"
                    final['Manufacturer'] = "Cecotec"
                    final['EAN13'] = df_m[buscar_columna(df_k, ['ean'])] if buscar_columna(df_k, ['ean']) else ""
                    
                    # Campos de medidas y stock
                    for col, val in zip(['Width', 'Height', 'Depth', 'Weight', 'Quantity'], ["1", "1", "1", "1", "0"]): final[col] = val
                    
                    # Descripción dinámica
                    cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                    final['Description'] = df_m[cols_car].fillna('').agg(' '.join, axis=1).str.slice(0, 2000)

                    # Campos fijos adicionales
                    for col, val in zip(['Text when in stock', 'Available for order (0 = No, 1 = Yes)', 'Show price (0 = No, 1 = Yes)', 'Condition', 'Available online only (0 = No, 1 = Yes)'], 
                                        ["In Stock", "1", "1", "new", "1"]):
                        final[col] = val

                    # Imágenes
                    c_ref_i = buscar_columna(df_i, ['reference', 'sku'])
                    df_i['urls'] = df_i.drop(columns=[c_ref_i], errors='ignore').fillna('').apply(lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                    final = pd.merge(final, df_i[[c_ref_i, 'urls']].drop_duplicates(c_ref_i), left_on='Reference #', right_on=c_ref_i, how='left')
                    final.rename(columns={'urls': 'Image URLs (x,y,z...)'}, inplace=True)
                    
                    # Campos finales de la plantilla (ID Shop, Out of stock, etc.)
                    for col in ['Out of stock', 'ID / Name of shop', 'Advanced stock management', 'Depends On Stock', 'Warehouse']:
                        final[col] = "0"

                    # Exportación Final con BOM para corregir caracteres
                    fecha_str = datetime.now().strftime("%Y%m%d")
                    nombre_fichero = f"{fecha_str}_Novedades.csv"
                    
                    csv_buf = io.BytesIO()
                    # El parámetro utf-8-sig soluciona los caracteres extraños en Excel
                    final.to_csv(csv_buf, index=False, sep=',', encoding='utf-8-sig')
                    
                    st.success(f"✅ ¡ÉXITO! {len(final)} productos listos.")
                    st.download_button("⬇️ Descargar CSV PrestaShop", csv_buf.getvalue(), nombre_fichero, "text/csv")
                except Exception as e: st.error(f"Error: {e}")