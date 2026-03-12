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

# --- FASE 2: GENERADOR DE IMPORTACIÓN ---
with tab2:
    st.header("Generador de Fichero PrestaShop")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Completa la Fase 1 primero.")
    else:
        c1, c2 = st.columns(2)
        with c1: f_keepa = st.file_uploader("Exportación Keepa (XLSX)", type=['xlsx'])
        with c2: 
            f_img = st.file_uploader("Exportación Imágenes (CSV)", type=['csv'])
            f_cats = st.file_uploader("Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar CSV Final"):
                try:
                    # Carga de datos
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_csv(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)
                    df_l = st.session_state.df_revisado

                    for d in [df_k, df_i, df_c]: d.columns = d.columns.str.lower().str.strip()

                    # Mapeo de columnas dinámicas
                    c_asin_k = buscar_columna(df_k, ['asin'])
                    c_ean_k = buscar_columna(df_k, ['ean', 'código'])
                    c_cat_k = buscar_columna(df_k, ['categorías: subcategoría'])
                    c_cat_amz = buscar_columna(df_c, ['amazon', 'origen'])
                    c_cat_ps = buscar_columna(df_c, ['prestashop', 'destino'])
                    
                    c_asin_l = buscar_columna(df_l, ['asin'])
                    
                    # Cruce Fase 1 + Keepa
                    df_m = pd.merge(df_l, df_k, left_on=c_asin_l, right_on=c_asin_k, how='inner')

                    # --- CONSTRUCCIÓN DEL CSV FINAL (ESTRUCTURA SOLICITADA) ---
                    final = pd.DataFrame()
                    final['Product ID'] = range(900001, 900001 + len(df_m))
                    final['Active (0/1)'] = "1"
                    
                    # Nombres de columnas mapeados
                    final['Name *'] = df_m.iloc[:, 1] # item-name de la Fase 1
                    
                    # Categorías con mapeo
                    mapeo = pd.Series(df_c[c_cat_ps].values, index=df_c[c_cat_amz].str.lower().str.strip()).to_dict()
                    final['Categories (x,y,z...)'] = df_m[c_cat_k].apply(lambda x: mapeo.get(str(x).lower().strip(), x))
                    
                    final['Price tax included'] = "999"
                    final['Tax rules ID'] = "1"
                    final['Wholesale price'] = ""
                    final['On sale (0/1)'] = "0"
                    
                    # Campos de descuento vacíos
                    for col in ['Discount amount', 'Discount percent', 'Discount from (yyyy-mm-dd)', 'Discount to (yyyy-mm-dd)']:
                        final[col] = ""

                    final['Reference #'] = df_m['seller-sku']
                    final['Supplier reference #'] = df_m['seller-sku']
                    final['Supplier'] = "Cecotec"
                    final['Manufacturer'] = "Cecotec"
                    final['EAN13'] = df_m[c_ean_k] if c_ean_k else ""
                    
                    # Campos de medidas y stock
                    for col, val in zip(['UPC', 'Ecotax', 'Width', 'Height', 'Depth', 'Weight', 'Quantity'], ["", "", "1", "1", "1", "1", "0"]):
                        final[col] = val
                    
                    # Descripción dinámica
                    cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                    final['Description'] = df_m[cols_car].fillna('').agg(' '.join, axis=1).str.slice(0, 2000) if cols_car else ""
                    
                    # Otros campos vacíos solicitados
                    for col in ['Minimal quantity', 'Low stock level', 'Visibility', 'Additional shipping cost', 
                                'Unity', 'Unit price', 'Short description', 'Tags (x,y,z...)', 'Meta title', 
                                'Meta keywords', 'Meta description', 'URL rewritten']:
                        final[col] = ""

                    final['Text when in stock'] = "In Stock"
                    final['Text when backorder allowed'] = ""
                    final['Available for order (0 = No, 1 = Yes)'] = "1"
                    
                    # Fechas vacías
                    final['Product available date'] = ""
                    final['Product creation date'] = ""
                    final['Show price (0 = No, 1 = Yes)'] = "1"

                    # Imágenes
                    c_ref_img = buscar_columna(df_i, ['reference', 'sku'])
                    df_i['urls'] = df_i.drop(columns=[c_ref_img], errors='ignore').fillna('').apply(
                        lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                    final = pd.merge(final, df_i[[c_ref_img, 'urls']].drop_duplicates(c_ref_img), 
                                     left_on='Reference #', right_on=c_ref_img, how='left')
                    final.rename(columns={'urls': 'Image URLs (x,y,z...)'}, inplace=True)
                    
                    # Campos finales fijos
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

                    # Eliminar columna técnica de unión de imágenes
                    if c_ref_img in final.columns: final.drop(columns=[c_ref_img], inplace=True)

                    csv_buf = io.StringIO()
                    final.to_csv(csv_buf, index=False, sep=',', encoding='utf-8-sig')
                    st.success("✅ Fichero de importación generado con éxito.")
                    st.download_button("⬇️ Descargar Fichero PrestaShop", csv_buf.getvalue(), "importacion_ps.csv", "text/csv")
                except Exception as e: st.error(f"Error en Fase 2: {e}")