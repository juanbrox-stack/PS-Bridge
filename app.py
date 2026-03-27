import streamlit as st
import pandas as pd
import io
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Turaco PS Helper PRO", page_icon="🐦", layout="wide")

def limpiar_saltos(texto):
    """Elimina saltos de línea internos para evitar que el CSV se rompa."""
    if pd.isna(texto): return ""
    return str(texto).replace('\n', ' ').replace('\r', ' ').strip()

def normalizar_sku(serie):
    """Limpia espacios, mayúsculas y ceros iniciales."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave, indice_fijo=None):
    """Busca columna de forma flexible o por índice si se proporciona."""
    if indice_fijo is not None and len(df.columns) > indice_fijo:
        return df.columns[indice_fijo]
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

def truncar_texto(texto, limite):
    """Corta el texto sin romper palabras."""
    texto = limpiar_saltos(texto)
    if len(texto) <= limite: return texto
    recorte = texto[:limite]
    punto_corte = max(recorte.rfind('.'), recorte.rfind(' '))
    return recorte[:punto_corte].strip() if punto_corte != -1 else recorte

# Persistencia de estados
for key in ['df_revisado', 'df_previa', 'df_final_generado']:
    if key not in st.session_state: st.session_state[key] = None

st.title("🐦 Turaco PrestaShop Assistant - v4.18")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar", "📦 FASE 2: Generar"])

# --- FASE 1: IDENTIFICACIÓN ---
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

                # Identificación de columnas clave
                col_ref_ps = buscar_columna(df_ps, ['reference'])
                col_sku_amz = buscar_columna(df_amz, ['seller-sku'])
                col_sku_plan = buscar_columna(df_plan, ['sku'])
                col_asin_amz = buscar_columna(df_amz, ['asin'])
                col_name_amz = buscar_columna(df_amz, ['item-name', 'title'])

                df_ps['sku_norm'] = normalizar_sku(df_ps[col_ref_ps])
                df_amz['sku_norm'] = normalizar_sku(df_amz[col_sku_amz])
                df_plan['sku_norm'] = normalizar_sku(df_plan[col_sku_plan])

                estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto", "Solo MAIN"]
                df_nov = df_amz[~df_amz['sku_norm'].isin(df_ps['sku_norm'].unique())]
                df_final = pd.merge(df_nov, df_plan[df_plan['estado'].isin(estados_ok)][['sku_norm', 'notas']], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    df_viz = df_final[['sku_norm', col_name_amz, col_asin_amz, 'notas']].copy()
                    df_viz.columns = ['SKU_FINAL', 'TITULO_PROV', 'ASIN_FINAL', 'NOTAS']
                    df_viz['ASIN_FINAL'] = df_viz['ASIN_FINAL'].str.strip().str.upper()
                    df_viz.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_viz
                else: st.warning("No hay novedades.")
            except Exception as e: st.error(f"Error Fase 1: {e}")

    if st.session_state.df_previa is not None:
        df_editado = st.data_editor(st.session_state.df_previa, hide_index=True, use_container_width=True)
        if st.button("✅ Confirmar Selección"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success("Registros guardados. Pasa a la Fase 2.")

# --- FASE 2: GENERADOR ---
with tab2:
    st.header("Generador de Fichero Final")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Primero confirma la selección en la Fase 1.")
    else:
        c1, c2 = st.columns(2)
        with c1: f_keepa = st.file_uploader("1. Keepa (XLSX)", type=['xlsx'])
        with c2: 
            f_img = st.file_uploader("2. Imágenes (XLSX o CSV)", type=['xlsx', 'csv'])
            f_cats = st.file_uploader("3. Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Procesar Fichero"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_csv(f_img, dtype=str) if f_img.name.endswith('.csv') else pd.read_excel(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)
                    
                    # Cruce ciego por posición 0 (ASIN en Keepa)
                    col_key_k = df_k.columns[0]
                    df_k['JOIN_KEY'] = df_k[col_key_k].str.strip().str.upper()
                    
                    df_m = pd.merge(st.session_state.df_revisado, df_k.drop_duplicates(subset=['JOIN_KEY']), 
                                    left_on='ASIN_FINAL', right_on='JOIN_KEY', how='inner')

                    if df_m.empty:
                        st.error("No se encontraron coincidencias con la primera columna de Keepa.")
                    else:
                        # Construcción con todas las columnas de v3.2 + lógica de índices de v4.17
                        final = pd.DataFrame()
                        final['Product ID'] = range(900001, 900001 + len(df_m))
                        final['Active (0/1)'] = "1"
                        
                        # Nombre -> Índice 2 (Columna C de Keepa)
                        c_tit_k = buscar_columna(df_k, ['título', 'title'], indice_fijo=2)
                        final['Name *'] = df_m[c_tit_k].apply(lambda x: truncar_texto(x, 128))
                        
                        # Categorías con mapeo
                        c_cat_sub = buscar_columna(df_k, ['subcategoría'], indice_fijo=3)
                        mapeo_cat = pd.Series(df_c.iloc[:,1].values, index=df_c.iloc[:,0].str.lower().str.strip()).to_dict()
                        final['Categories (x,y,z...)'] = df_m[c_cat_sub].apply(lambda x: mapeo_cat.get(str(x).lower().strip(), x))
                        
                        final['Price tax included'] = "999"
                        final['Tax rules ID'] = "1"
                        final['Reference #'] = df_m['SKU_FINAL']
                        final['Supplier reference #'] = df_m['SKU_FINAL']
                        final['Supplier'] = "Cecotec"
                        final['Manufacturer'] = "Cecotec"
                        
                        # EAN -> Índice 9 (Columna J de Keepa)
                        c_ean_k = buscar_columna(df_k, ['ean', 'códigos'], indice_fijo=9)
                        final['EAN13'] = df_m[c_ean_k].apply(limpiar_saltos)
                        
                        for col, val in zip(['Width', 'Height', 'Depth', 'Weight', 'Quantity'], ["1", "1", "1", "1", "0"]): 
                            final[col] = val
                        
                        # Descripción: Unifica columnas de características
                        cols_car = [c for c in df_m.columns if 'característica' in str(c).lower() or 'descripción' in str(c).lower()]
                        final['Description'] = df_m[cols_car].fillna('').agg(' '.join, axis=1).apply(lambda x: truncar_texto(x, 2000))

                        final['Text when in stock'] = "In Stock"
                        final['Available for order (0 = No, 1 = Yes)'] = "1"
                        final['Show price (0 = No, 1 = Yes)'] = "1"

                        # Imágenes (Lógica de v3.2)
                        c_ref_i = buscar_columna(df_i, ['reference', 'sku'])
                        df_i_clean = df_i.copy()
                        df_i_clean['urls'] = df_i_clean.drop(columns=[c_ref_i], errors='ignore').fillna('').apply(lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                        img_dict = pd.Series(df_i_clean['urls'].values, index=normalizar_sku(df_i_clean[c_ref_i])).to_dict()
                        final['Image URLs (x,y,z...)'] = final['Reference #'].apply(lambda x: img_map.get(x, "") if 'img_map' in locals() else img_dict.get(x, ""))
                        
                        # Campos finales fijos
                        for col in ['Condition', 'Available online only (0 = No, 1 = Yes)', 'Out of stock', 'ID / Name of shop', 'Warehouse']:
                            final[col] = "new" if "Condition" in col else ("1" if "Available" in col else "0")

                        st.session_state.df_final_generado = final.applymap(limpiar_saltos)
                        st.success(f"✅ Generado correctamente: {len(final)} productos.")

                except Exception as e: st.error(f"Error Técnico: {e}")

        if st.session_state.df_final_generado is not None:
            st.divider()
            st.subheader("👀 Previsualización del Fichero Final")
            st.dataframe(st.session_state.df_final_generado, use_container_width=True)
            
            # Exportación
            csv_buf = io.BytesIO()
            st.session_state.df_final_generado.to_csv(csv_buf, index=False, sep=',', encoding='utf-8-sig')
            
            st.download_button(
                label="⬇️ Descargar Novedades.csv",
                data=csv_buf.getvalue(),
                file_name=f"{datetime.now().strftime('%Y%m%d')}_Novedades_Turaco.csv",
                mime="text/csv"
            )