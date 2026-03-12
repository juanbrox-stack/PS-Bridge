import streamlit as st
import pandas as pd
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Turaco PS Assistant", page_icon="🐦", layout="wide")

def normalizar_sku(serie):
    """Limpia espacios, mayúsculas y quita ceros a la izquierda para comparaciones."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave):
    """Busca una columna de forma flexible por palabras clave."""
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

# Persistencia de datos entre pestañas
if 'df_revisado' not in st.session_state: st.session_state.df_revisado = None
if 'df_previa' not in st.session_state: st.session_state.df_previa = None

st.title("🐦 Turaco PrestaShop Assistant")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificación y Auditoría", "📦 FASE 2: Generador de Importación"])

# --- FASE 1: IDENTIFICAR NOVEDADES ---
with tab1:
    st.header("Auditoría de Novedades")
    st.write("Carga los ficheros para identificar qué productos procesar.")
    
    c1, c2, c3 = st.columns(3)
    with c1: f_ps = st.file_uploader("BBDD PrestaShop (CSV/XLSX)", type=['csv', 'xlsx'], key="f1")
    with c2: f_amz = st.file_uploader("Listing Amazon (TXT/XLSX)", type=['txt', 'xlsx'], key="f2")
    with c3: f_plan = st.file_uploader("Plan Lanzamiento (XLSX)", type=['xlsx'], key="f3")

    if all([f_ps, f_amz, f_plan]):
        if st.button("🚀 Iniciar Cruce"):
            try:
                # Lectura de datos
                df_ps = pd.read_csv(f_ps, sep=None, engine='python', dtype=str) if f_ps.name.endswith('.csv') else pd.read_excel(f_ps, dtype=str)
                df_amz = pd.read_excel(f_amz, dtype=str) if f_amz.name.endswith('.xlsx') else pd.read_csv(f_amz, sep='\t', encoding='latin1', dtype=str)
                df_plan = pd.read_excel(f_plan, dtype=str)

                for d in [df_ps, df_amz, df_plan]: d.columns = d.columns.str.lower().str.strip()

                # Normalización y Filtro
                df_ps['sku_norm'] = normalizar_sku(df_ps['reference'])
                df_amz['sku_norm'] = normalizar_sku(df_amz['seller-sku'])
                df_plan['sku_norm'] = normalizar_sku(df_plan['sku'])

                estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto"]
                df_plan_f = df_plan[df_plan['estado'].isin(estados_ok)]

                skus_en_ps = df_ps['sku_norm'].unique()
                df_nov = df_amz[~df_amz['sku_norm'].isin(skus_en_ps)]
                
                # Cruce final con Plan
                df_final = pd.merge(df_nov, df_plan_f[['sku_norm', 'notas']], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    # Seleccionamos solo las 4 columnas solicitadas para la visualización
                    # seller-sku, item-name, asin, notas
                    c_asin_amz = buscar_columna(df_final, ['asin'])
                    c_name_amz = buscar_columna(df_final, ['item-name', 'title', 'nombre'])
                    
                    df_viz = df_final[['seller-sku', c_name_amz, c_asin_amz, 'notas']].copy()
                    df_viz.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_viz
                else: st.warning("No se encontraron novedades.")
            except Exception as e: st.error(f"Error: {e}")

    if st.session_state.df_previa is not None:
        solo_notas = st.toggle("🎯 Filtrar solo productos con Notas")
        df_disp = st.session_state.df_previa
        if solo_notas: df_disp = df_disp[df_disp['notas'].fillna('').str.strip() != ""]

        df_editado = st.data_editor(df_disp, hide_index=True, use_container_width=True, 
                                    column_config={"Seleccionado": st.column_config.CheckboxColumn("¿Procesar?")})

        if st.button("✅ Confirmar y pasar a Fase 2"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success(f"{len(st.session_state.df_revisado)} SKUs cargados.")

# --- FASE 2: GENERADOR DE IMPORTACIÓN (VERSIÓN CORREGIDA Y BLINDADA) ---
with tab2:
    st.header("Generador de Fichero PrestaShop")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Primero completa la revisión en la Fase 1.")
    else:
        st.write(f"Procesando **{len(st.session_state.df_revisado)}** productos validados de la Fase 1.")
        
        c1, c2 = st.columns(2)
        with c1: f_keepa = st.file_uploader("Exportación Keepa (XLSX)", type=['xlsx'])
        with c2: 
            f_img = st.file_uploader("Exportación Imágenes (CSV)", type=['csv'])
            f_cats = st.file_uploader("Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar Fichero Final"):
                try:
                    # 1. CARGA DE DATOS
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_csv(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)
                    df_l = st.session_state.df_revisado

                    # Estandarizar columnas a minúsculas
                    for d in [df_k, df_i, df_c]: d.columns = d.columns.str.lower().str.strip()

                    # 2. IDENTIFICACIÓN DE COLUMNAS CRÍTICAS
                    c_asin_k = buscar_columna(df_k, ['asin'])
                    c_ean_k = buscar_columna(df_k, ['ean', 'código'])
                    c_cat_k = buscar_columna(df_k, ['categoría', 'category', 'subcategoría'])
                    
                    # Validación de seguridad para evitar error 'None'
                    if not c_asin_k:
                        st.error("❌ ERROR: No se encuentra la columna 'ASIN' en el fichero de Keepa.")
                        st.stop()
                    
                    # Buscar el ASIN en los datos que vienen de la Fase 1
                    c_asin_l = buscar_columna(df_l, ['asin'])
                    
                    # 3. CRUCE DE DATOS (MERGE)
                    df_m = pd.merge(df_l, df_k, left_on=c_asin_l, right_on=c_asin_k, how='inner')

                    if df_m.empty:
                        st.error("❌ ERROR DE CRUCE: Los ASINs seleccionados en la Fase 1 no coinciden con los del fichero Keepa.")
                        st.info("Asegúrate de que el fichero de Keepa contiene los datos de los productos que seleccionaste anteriormente.")
                        st.stop()

                    # 4. CONSTRUCCIÓN DEL CSV FINAL (Estructura de 64 columnas)
                    final = pd.DataFrame()
                    final['Product ID'] = range(900001, 900001 + len(df_m))
                    final['Active (0/1)'] = "1"
                    
                    # El nombre viene de la segunda columna del df de revisión (item-name)
                    final['Name *'] = df_m.iloc[:, 1] 
                    
                    # Mapeo de categorías
                    c_cat_amz = buscar_columna(df_c, ['amazon', 'origen'])
                    c_cat_ps = buscar_columna(df_c, ['prestashop', 'destino'])
                    if c_cat_amz and c_cat_ps:
                        mapeo = pd.Series(df_c[c_cat_ps].values, index=df_c[c_cat_amz].str.lower().str.strip()).to_dict()
                        final['Categories (x,y,z...)'] = df_m[c_cat_k].apply(lambda x: mapeo.get(str(x).lower().strip(), x))
                    else:
                        final['Categories (x,y,z...)'] = df_m[c_cat_k] if c_cat_k else "Inicio"
                    
                    final['Price tax included'] = "999"
                    final['Tax rules ID'] = "1"
                    final['Reference #'] = df_m['seller-sku']
                    final['Supplier reference #'] = df_m['seller-sku']
                    final['Supplier'] = "Cecotec"
                    final['Manufacturer'] = "Cecotec"
                    final['EAN13'] = df_m[c_ean_k] if c_ean_k else ""
                    
                    # Descripción dinámica (características)
                    cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                    final['Description'] = df_m[cols_car].fillna('').agg(' '.join, axis=1).str.slice(0, 2000) if cols_car else ""

                    # 5. IMÁGENES
                    c_ref_img = buscar_columna(df_i, ['reference', 'sku'])
                    if c_ref_img:
                        df_i['urls'] = df_i.drop(columns=[c_ref_img], errors='ignore').fillna('').apply(
                            lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                        df_i_clean = df_i[[c_ref_img, 'urls']].drop_duplicates(c_ref_img)
                        final = pd.merge(final, df_i_clean, left_on='Reference #', right_on=c_ref_img, how='left')
                        final.rename(columns={'urls': 'Image URLs (x,y,z...)'}, inplace=True)
                    
                    # 6. RELLENO DE CAMPOS FIJOS RESTANTES
                    campos_fijos = {
                        'Wholesale price': "", 'On sale (0/1)': "0", 'UPC': "", 'Ecotax': "", 
                        'Width': "1", 'Height': "1", 'Depth': "1", 'Weight': "1", 'Quantity': "0",
                        'Text when in stock': "In Stock", 'Available for order (0 = No, 1 = Yes)': "1",
                        'Show price (0 = No, 1 = Yes)': "1", 'Condition': "new", 'Available online only (0 = No, 1 = Yes)': "1"
                    }
                    for col, val in campos_fijos.items(): final[col] = val

                    # Descarga
                    csv_buf = io.StringIO()
                    final.to_csv(csv_buf, index=False, sep=',', encoding='utf-8-sig')
                    st.success(f"✅ ¡ÉXITO! Fichero generado con {len(final)} productos.")
                    st.download_button("⬇️ Descargar CSV PrestaShop", csv_buf.getvalue(), "subida_final.csv", "text/csv")
                    
                    # Vista previa para depuración
                    st.subheader("Visualización del resultado (Primeras 5 filas)")
                    st.dataframe(final.head())

                except Exception as e:
                    st.error(f"❌ Error detallado: {str(e)}")