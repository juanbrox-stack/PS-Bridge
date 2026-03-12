import streamlit as st
import pandas as pd
import io

# --- CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Turaco PS Helper Final", page_icon="🐦", layout="wide")

def normalizar_sku(serie):
    """Limpia espacios, mayúsculas y quita ceros a la izquierda."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave):
    """Busca una columna de forma flexible por palabras clave."""
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

if 'df_revisado' not in st.session_state: st.session_state.df_revisado = None
if 'df_previa' not in st.session_state: st.session_state.df_previa = None

st.title("🐦 Turaco PrestaShop Assistant - Versión Final")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar y Auditar", "📦 FASE 2: Generar Carga Final"])

# --- FASE 1: IDENTIFICAR Y REVISAR ---
with tab1:
    st.header("Identificación de Novedades")
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

        df_editado = st.data_editor(df_disp, hide_index=True, use_container_width=True, key="editor_final")

        if st.button("✅ Confirmar Selección"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success("Registros listos para Fase 2.")

# --- FASE 2: GENERADOR DE CARGA ---
with tab2:
    st.header("Generador de Fichero CSV")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Completa la Fase 1 primero.")
    else:
        c1, c2 = st.columns(2)
        with c1: f_keepa = st.file_uploader("Keepa (XLSX)", type=['xlsx'])
        with c2: 
            f_img = st.file_uploader("Imágenes (CSV)", type=['csv'])
            f_cats = st.file_uploader("Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar CSV PrestaShop"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_csv(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)
                    df_l = st.session_state.df_revisado

                    for d in [df_k, df_i, df_c]: d.columns = d.columns.str.lower().str.strip()

                    c_asin_k = buscar_columna(df_k, ['asin'])
                    c_cat_k = buscar_columna(df_k, ['categoría', 'category', 'subcategoría'])
                    c_asin_l = buscar_columna(df_l, ['asin'])
                    
                    if not c_asin_k: st.error("No se encontró columna ASIN en Keepa."); st.stop()

                    df_m = pd.merge(df_l, df_k, left_on=c_asin_l, right_on=c_asin_k, how='inner')
                    if df_m.empty: st.error("No hay coincidencias de ASIN."); st.stop()

                    # --- CONSTRUCCIÓN DE COLUMNAS EXACTAS ---
                    final = pd.DataFrame()
                    final['Product ID'] = range(900001, 900001 + len(df_m))
                    final['Active (0/1)'] = "1"
                    final['Name *'] = df_m.iloc[:, 1] # item-name
                    
                    c_cat_amz = buscar_columna(df_c, ['amazon', 'origen'])
                    c_cat_ps = buscar_columna(df_c, ['prestashop', 'destino'])
                    mapeo = pd.Series(df_c[c_cat_ps].values, index=df_c[c_cat_amz].str.lower().str.strip()).to_dict()
                    final['Categories (x,y,z...)'] = df_m[c_cat_k].apply(lambda x: mapeo.get(str(x).lower().strip(), x))
                    
                    final['Price tax included'] = "999"
                    final['Tax rules ID'] = "1"
                    
                    for col in ['Wholesale price', 'On sale (0/1)', 'Discount amount', 'Discount percent', 
                                'Discount from (yyyy-mm-dd)', 'Discount to (yyyy-mm-dd)']: final[col] = "0" if "sale" in col else ""

                    final['Reference #'] = df_m['seller-sku']
                    final['Supplier reference #'] = df_m['seller-sku']
                    final['Supplier'] = "Cecotec"
                    final['Manufacturer'] = "Cecotec"
                    final['EAN13'] = df_m[buscar_columna(df_k, ['ean', 'código'])] if buscar_columna(df_k, ['ean']) else ""
                    
                    for col, val in zip(['UPC', 'Ecotax', 'Width', 'Height', 'Depth', 'Weight', 'Quantity'], ["", "", "1", "1", "1", "1", "0"]): final[col] = val
                    
                    cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                    final['Description'] = df_m[cols_car].fillna('').agg(' '.join, axis=1).str.slice(0, 2000)

                    for col in ['Minimal quantity', 'Low stock level', 'Visibility', 'Additional shipping cost', 
                                'Unity', 'Unit price', 'Short description', 'Tags (x,y,z...)', 'Meta title', 
                                'Meta keywords', 'Meta description', 'URL rewritten']: final[col] = ""

                    final['Text when in stock'] = "In Stock"
                    final['Text when backorder allowed'] = ""
                    final['Available for order (0 = No, 1 = Yes)'] = "1"
                    final['Product available date'] = ""
                    final['Product creation date'] = ""
                    final['Show price (0 = No, 1 = Yes)'] = "1"

                    # Imágenes
                    c_ref_i = buscar_columna(df_i, ['reference', 'sku'])
                    df_i['urls'] = df_i.drop(columns=[c_ref_i], errors='ignore').fillna('').apply(
                        lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                    final = pd.merge(final, df_i[[c_ref_i, 'urls']].drop_duplicates(c_ref_i), left_on='Reference #', right_on=c_ref_i, how='left')
                    final.rename(columns={'urls': 'Image URLs (x,y,z...)'}, inplace=True)
                    
                    # --- COLUMNAS FALTANTES AÑADIDAS ---
                    final['Image alt texts (x,y,z...)'] = ""
                    final['Delete existing images (0 = No, 1 = Yes)'] = "0"
                    final['Feature(Name:Value:Position)'] = ""
                    final['Available online only (0 = No, 1 = Yes)'] = "1"
                    final['Condition'] = "new"
                    final['Customizable (0 = No, 1 = Yes)'] = "0"
                    final['Uploadable files (0 = No, 1 = Yes)'] = "0"
                    final['Text fields (0 = No, 1 = Yes)'] = "0"
                    final['Out of stock'] = "0"
                    final['ID / Name of shop'] = "0"
                    final['Advanced stock management'] = "0"
                    final['Depends On Stock'] = "0"
                    final['Warehouse'] = "0"

                    if c_ref_i in final.columns: final.drop(columns=[c_ref_i], inplace=True)

                    # Exportación con firma BOM para evitar caracteres extraños
                    csv_buf = io.StringIO()
                    final.to_csv(csv_buf, index=False, sep=',', encoding='utf-8-sig')
                    st.success(f"✅ ¡ÉXITO! {len(final)} productos listos.")
                    st.download_button("⬇️ Descargar CSV PrestaShop", csv_buf.getvalue(), "importacion_ps.csv", "text/csv")
                except Exception as e: st.error(f"Error: {e}")