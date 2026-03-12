import streamlit as st
import pandas as pd
import io
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Turaco PS Helper PRO", page_icon="🐦", layout="wide")

def normalizar_sku(serie):
    """Limpia espacios, mayúsculas y ceros iniciales."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave):
    """Busca columnas de forma flexible."""
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

def truncar_texto(texto, limite):
    """Corta el texto en el último espacio o punto sin exceder el límite."""
    texto = str(texto).strip()
    if len(texto) <= limite: return texto
    recorte = texto[:limite]
    ultimo_punto = recorte.rfind('.')
    ultimo_espacio = recorte.rfind(' ')
    punto_corte = max(ultimo_punto, ultimo_espacio)
    if punto_corte == -1: return recorte
    return recorte[:punto_corte].strip()

# Persistencia de datos entre pestañas
if 'df_revisado' not in st.session_state: st.session_state.df_revisado = None
if 'df_previa' not in st.session_state: st.session_state.df_previa = None

st.title("🐦 Turaco PrestaShop Assistant - Generador Completo")
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
                df_ps = pd.read_csv(f_ps, sep=None, engine='python', dtype=str) if f_ps.name.endswith('.csv') else pd.read_excel(f_ps, dtype=str)
                df_amz = pd.read_excel(f_amz, dtype=str) if f_amz.name.endswith('.xlsx') else pd.read_csv(f_amz, sep='\t', encoding='latin1', dtype=str)
                df_plan = pd.read_excel(f_plan, dtype=str)

                for d in [df_ps, df_amz, df_plan]: d.columns = d.columns.str.lower().str.strip()

                df_ps['sku_norm'] = normalizar_sku(df_ps['reference'])
                df_amz['sku_norm'] = normalizar_sku(df_amz['seller-sku'])
                df_plan['sku_norm'] = normalizar_sku(df_plan['sku'])

                estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto"]
                df_plan_f = df_plan[df_plan['estado'].isin(estados_ok)]

                skus_en_ps = df_ps['sku_norm'].unique()
                df_nov = df_amz[~df_amz['sku_norm'].isin(skus_en_ps)]
                
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
            st.success("Registros guardados. Ve a la Fase 2.")

# --- FASE 2: GENERADOR ---
with tab2:
    st.header("Generador de Fichero CSV Completo")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Debes confirmar la selección en la Fase 1.")
    else:
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

                    c_asin_k = buscar_columna(df_k, ['asin'])
                    c_tit_k = buscar_columna(df_k, ['título', 'title']) 
                    c_cat_sub = buscar_columna(df_k, ['subcategoría']) 
                    c_map_amz = buscar_columna(df_c, ['amazon', 'origen'])
                    c_map_ps = buscar_columna(df_c, ['prestashop', 'destino'])
                    c_asin_l = buscar_columna(df_l, ['asin'])
                    
                    df_m = pd.merge(df_l, df_k, left_on=c_asin_l, right_on=c_asin_k, how='inner')

                    # Validación Categorías
                    subcats_keepa = df_m[c_cat_sub].unique()
                    subcats_mapeadas = df_c[c_map_amz].str.lower().str.strip().unique()
                    faltantes = [str(cat) for cat in subcats_keepa if str(cat).lower().strip() not in subcats_mapeadas]
                    if faltantes: st.error(f"⚠️ Faltan subcategorías en el mapeo: {faltantes}"); st.stop()

                    # --- CONSTRUCCIÓN DEL DATASET CON TODAS LAS COLUMNAS ---
                    final = pd.DataFrame()
                    final['Product ID'] = range(900001, 900001 + len(df_m))
                    final['Active (0/1)'] = "1"
                    final['Name *'] = df_m[c_tit_k].apply(lambda x: truncar_texto(x, 128))
                    
                    mapeo = pd.Series(df_c[c_cat_ps].values, index=df_c[c_map_amz].str.lower().str.strip()).to_dict()
                    final['Categories (x,y,z...)'] = df_m[c_cat_sub].apply(lambda x: mapeo.get(str(x).lower().strip(), x))
                    
                    final['Price tax included'] = "999"
                    final['Tax rules ID'] = "1"
                    
                    # Columnas adicionales solicitadas
                    final['Wholesale price'] = ""
                    final['On sale (0/1)'] = "0"
                    for col in ['Discount amount', 'Discount percent', 'Discount from (yyyy-mm-dd)', 'Discount to (yyyy-mm-dd)']:
                        final[col] = ""

                    final['Reference #'] = df_m['seller-sku']
                    final['Supplier reference #'] = df_m['seller-sku']
                    final['Supplier'] = "Cecotec"
                    final['Manufacturer'] = "Cecotec"
                    final['EAN13'] = df_m[buscar_columna(df_k, ['ean'])] if buscar_columna(df_k, ['ean']) else ""
                    
                    # Medidas y Stock
                    for col, val in zip(['UPC', 'Ecotax', 'Width', 'Height', 'Depth', 'Weight', 'Quantity'], ["", "", "1", "1", "1", "1", "0"]):
                        final[col] = val
                    
                    # Otros campos solicitados
                    for col in ['Minimal quantity', 'Low stock level', 'Visibility', 'Additional shipping cost', 'Unity', 'Unit price', 'Short description']:
                        final[col] = ""

                    cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                    raw_desc = df_m[cols_car].fillna('').agg(' '.join, axis=1)
                    final['Description'] = raw_desc.apply(lambda x: truncar_texto(x, 2000))

                    for col in ['Tags (x,y,z...)', 'Meta title', 'Meta keywords', 'Meta description', 'URL rewritten']:
                        final[col] = ""

                    final['Text when in stock'] = "In Stock"
                    final['Text when backorder allowed'] = ""
                    final['Available for order (0 = No, 1 = Yes)'] = "1"
                    final['Product available date'] = ""
                    final['Product creation date'] = ""
                    final['Show price (0 = No, 1 = Yes)'] = "1"

                    # Imágenes
                    c_ref_i = buscar_columna(df_i, ['reference', 'sku'])
                    df_i['urls'] = df_i.drop(columns=[c_ref_i], errors='ignore').fillna('').apply(lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                    final = pd.merge(final, df_i[[c_ref_i, 'urls']].drop_duplicates(c_ref_i), left_on='Reference #', right_on=c_ref_i, how='left')
                    final.rename(columns={'urls': 'Image URLs (x,y,z...)'}, inplace=True)
                    
                    # Columnas finales solicitadas
                    final['Image alt texts (x,y,z...)'] = ""
                    final['Delete existing images (0 = No, 1 = Yes)'] = "0"
                    final['Feature(Name:Value:Position)'] = ""
                    final['Available online only (0 = No, 1 = Yes)'] = "1"
                    final['Condition'] = "new"
                    
                    for col in ['Customizable (0 = No, 1 = Yes)', 'Uploadable files (0 = No, 1 = Yes)', 'Text fields (0 = No, 1 = Yes)', 'Out of stock', 'ID / Name of shop', 'Advanced stock management', 'Depends On Stock', 'Warehouse']:
                        final[col] = "0"

                    # Exportación Final
                    fecha_str = datetime.now().strftime("%Y%m%d")
                    nombre_fichero = f"{fecha_str}_Novedades.csv"
                    csv_buf = io.BytesIO()
                    final.to_csv(csv_buf, index=False, sep=',', encoding='utf-8-sig')
                    
                    st.success(f"✅ Fichero '{nombre_fichero}' generado con éxito.")
                    st.download_button("⬇️ Descargar CSV PrestaShop", csv_buf.getvalue(), nombre_fichero, "text/csv")
                except Exception as e: st.error(f"Error: {e}")