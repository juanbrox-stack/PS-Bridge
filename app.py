import streamlit as st
import pandas as pd
import io
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Turaco PS Helper PRO", page_icon="🐦", layout="wide")

def limpiar_texto_excel(texto):
    """Limpia caracteres que podrían causar errores visuales."""
    if pd.isna(texto): return ""
    return str(texto).replace('\n', ' ').replace('\r', ' ').strip()

def normalizar_sku(serie):
    """Limpia espacios y ceros iniciales para cruces precisos."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave):
    """Busca una columna de forma flexible."""
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

def truncar_texto(texto, limite):
    """Recorte inteligente sin romper palabras."""
    texto = limpiar_texto_excel(texto)
    if len(texto) <= limite: return texto
    recorte = texto[:limite]
    punto_corte = max(recorte.rfind('.'), recorte.rfind(' '))
    return recorte[:punto_corte].strip() if punto_corte != -1 else recorte

# Persistencia de estados
if 'df_revisado' not in st.session_state: st.session_state.df_revisado = None
if 'df_previa' not in st.session_state: st.session_state.df_previa = None
if 'df_final_generado' not in st.session_state: st.session_state.df_final_generado = None

st.title("🐦 Turaco PrestaShop Assistant - v4.2")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar y Auditar", "📦 FASE 2: Generar Carga Final"])

# --- FASE 1 ---
with tab1:
    st.header("Auditoría de Novedades")
    c1, c2, c3 = st.columns(3)
    with c1: f_ps = st.file_uploader("1. BBDD PrestaShop", type=['csv', 'xlsx'])
    with c2: f_amz = st.file_uploader("2. Listing Amazon", type=['txt', 'xlsx'])
    with c3: f_plan = st.file_uploader("3. Plan Lanzamiento", type=['xlsx'])

    if all([f_ps, f_amz, f_plan]):
        if st.button("🚀 Iniciar Cruce"):
            try:
                df_ps = pd.read_csv(f_ps, sep=None, engine='python', dtype=str) if f_ps.name.endswith('.csv') else pd.read_excel(f_ps, dtype=str)
                df_amz = pd.read_excel(f_amz, dtype=str) if f_amz.name.endswith('.xlsx') else pd.read_csv(f_amz, sep='\t', encoding='latin1', dtype=str)
                df_plan = pd.read_excel(f_plan, dtype=str)
                
                for d in [df_ps, df_amz, df_plan]: d.columns = d.columns.str.lower().str.strip()
                
                df_ps['sku_norm'] = normalizar_sku(df_ps['reference'])
                df_amz['sku_norm'] = normalizar_sku(df_amz['seller-sku'])
                df_plan['sku_norm'] = normalizar_sku(df_plan['sku'])
                
                df_nov = df_amz[~df_amz['sku_norm'].isin(df_ps['sku_norm'].unique())]
                df_final = pd.merge(df_nov, df_plan[df_plan['estado'].isin(["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto"])][['sku_norm', 'notas']], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    c_asin = buscar_columna(df_final, ['asin'])
                    c_name = buscar_columna(df_final, ['item-name', 'title'])
                    df_viz = df_final[['seller-sku', c_name, c_asin, 'notas']].copy()
                    df_viz.rename(columns={c_asin: 'ASIN', c_name: 'item-name'}, inplace=True)
                    df_viz.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_viz
                else: st.warning("No hay novedades.")
            except Exception as e: st.error(f"Error: {e}")

    if st.session_state.df_previa is not None:
        df_editado = st.data_editor(st.session_state.df_previa, hide_index=True, use_container_width=True)
        if st.button("✅ Confirmar Selección"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success("Registros guardados.")

# --- FASE 2 ---
with tab2:
    st.header("Generador de Carga Directa a Excel")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Primero confirma la selección en la Fase 1.")
    else:
        c1, c2 = st.columns(2)
        with c1: 
            f_keepa = st.file_uploader("1. Keepa (XLSX)", type=['xlsx'])
        with c2: 
            # Cambiado de CSV a XLSX
            f_img = st.file_uploader("2. Imágenes (XLSX)", type=['xlsx'])
            f_cats = st.file_uploader("3. Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar Excel"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_excel(f_img, dtype=str) # Lectura Excel
                    df_c = pd.read_excel(f_cats, dtype=str)
                    df_l = st.session_state.df_revisado
                    
                    for d in [df_k, df_i, df_c]: d.columns = d.columns.str.lower().str.strip()

                    c_asin_k = buscar_columna(df_k, ['asin'])
                    df_k = df_k.drop_duplicates(subset=[c_asin_k]) 
                    c_tit_k = buscar_columna(df_k, ['título', 'title'])
                    c_cat_sub = buscar_columna(df_k, ['subcategoría'])
                    c_asin_l = buscar_columna(df_l, ['asin'])
                    
                    df_m = pd.merge(df_l, df_k, left_on=c_asin_l, right_on=c_asin_k, how='inner')

                    # --- CONSTRUCCIÓN DE COLUMNAS ---
                    final = pd.DataFrame()
                    final['Product ID'] = range(900001, 900001 + len(df_m))
                    final['Active (0/1)'] = "1"
                    final['Name *'] = df_m[c_tit_k].apply(lambda x: truncar_texto(x, 128))
                    
                    c_map_ps = buscar_columna(df_c, ['prestashop', 'destino'])
                    c_map_amz = buscar_columna(df_c, ['amazon', 'origen'])
                    mapeo = pd.Series(df_c[c_map_ps].values, index=df_c[c_map_amz].str.lower().str.strip()).to_dict()
                    final['Categories (x,y,z...)'] = df_m[c_cat_sub].apply(lambda x: mapeo.get(str(x).lower().strip(), x))
                    
                    final['Price tax included'] = "999"; final['Tax rules ID'] = "1"
                    final['Reference #'] = df_m['seller-sku']
                    final['Supplier reference #'] = df_m['seller-sku']
                    final['Supplier'] = "Cecotec"; final['Manufacturer'] = "Cecotec"
                    final['EAN13'] = df_m[buscar_columna(df_k, ['ean'])].apply(limpiar_texto_excel) if buscar_columna(df_k, ['ean']) else ""
                    
                    for col, val in zip(['Width', 'Height', 'Depth', 'Weight', 'Quantity'], ["1", "1", "1", "1", "0"]): final[col] = val
                    
                    cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                    final['Description'] = df_m[cols_car].fillna('').agg(' '.join, axis=1).apply(lambda x: truncar_texto(x, 2000))

                    final['Text when in stock'] = "In Stock"; final['Available for order (0 = No, 1 = Yes)'] = "1"; final['Show price (0 = No, 1 = Yes)'] = "1"

                    # --- LÓGICA DE IMÁGENES SIN DUPLICADOS (AHORA PARA EXCEL) ---
                    c_ref_i = buscar_columna(df_i, ['reference', 'sku'])
                    df_i[c_ref_i] = normalizar_sku(df_i[c_ref_i])
                    
                    cols_url = [c for c in df_i.columns if c != c_ref_i]
                    # Generamos el string de URLs una sola vez por fila
                    df_i['urls_tmp'] = df_i[cols_url].fillna('').apply(lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                    
                    # Mapeo único SKU -> URLs
                    df_i_map = df_i.drop_duplicates(subset=[c_ref_i]).set_index(c_ref_i)['urls_tmp'].to_dict()
                    
                    final['Image URLs (x,y,z...)'] = final['Reference #'].apply(lambda x: df_i_map.get(normalizar_sku(pd.Series(x)).iloc[0], ""))
                    
                    for col in ['Condition', 'Available online only (0 = No, 1 = Yes)', 'Out of stock', 'ID / Name of shop', 'Warehouse']:
                        final[col] = "new" if "Condition" in col else ("1" if "Available" in col else "0")
                    
                    st.session_state.df_final_generado = final.applymap(limpiar_texto_excel)
                    st.success("✅ Fichero Excel generado correctamente (Soporte XLSX para imágenes activo).")
                except Exception as e: st.error(f"Error: {e}")

        if st.session_state.df_final_generado is not None:
            st.divider()
            st.subheader("👀 Previsualización")
            st.dataframe(st.session_state.df_final_generado, use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                st.session_state.df_final_generado.to_excel(writer, index=False)
            
            st.download_button(
                label="⬇️ Descargar Excel Final",
                data=output.getvalue(),
                file_name=f"{datetime.now().strftime('%Y%m%d')}_Novedades.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )