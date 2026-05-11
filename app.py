import streamlit as st
import pandas as pd
import io
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Turaco PS Helper PRO", page_icon="🐦", layout="wide")

def limpiar_texto(texto):
    if pd.isna(texto): return ""
    return str(texto).replace('\n', ' ').replace('\r', ' ').strip()

def normalizar_sku(serie):
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def truncar_texto(texto, limite):
    texto = limpiar_texto(texto)
    if len(texto) <= limite: return texto
    recorte = texto[:limite]
    punto_corte = max(recorte.rfind('.'), recorte.rfind(' '))
    return recorte[:punto_corte].strip() if punto_corte != -1 else recorte

def obtener_columna(df, palabras_clave, indice_fallback):
    for col in df.columns:
        if any(p in str(col).lower() for p in palabras_clave):
            return col
    return df.columns[indice_fallback] if len(df.columns) > indice_fallback else df.columns[0]

# Persistencia de estados
for key in ['df_revisado', 'df_previa', 'df_final_generado']:
    if key not in st.session_state: st.session_state[key] = None

st.title("🐦 Turaco PrestaShop Assistant - v4.32")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar", "📦 FASE 2: Generar Excel Maestro"])

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

                col_ref_ps = obtener_columna(df_ps, ['reference'], 0)
                col_sku_amz = obtener_columna(df_amz, ['seller-sku', 'sku'], 0)
                col_asin_amz = obtener_columna(df_amz, ['asin1', 'asin'], 2)
                col_name_amz = obtener_columna(df_amz, ['item-name', 'title'], 1)
                col_sku_plan = obtener_columna(df_plan, ['sku'], 0)
                col_est_plan = obtener_columna(df_plan, ['estado'], 1)
                col_clu_plan = obtener_columna(df_plan, ['cluster'], 3)
                col_not_plan = obtener_columna(df_plan, ['notas'], 2)

                df_ps['sku_norm'] = normalizar_sku(df_ps[col_ref_ps])
                df_amz['sku_norm'] = normalizar_sku(df_amz[col_sku_amz])
                df_plan['sku_norm'] = normalizar_sku(df_plan[col_sku_plan])

                # Filtro: Excluir Cluster A, mantener el resto (con o sin notas)
                estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto", "Solo MAIN"]
                mask = (df_plan[col_est_plan].isin(estados_ok)) & (df_plan[col_clu_plan].astype(str).str.upper() != "A")

                df_plan_f = df_plan[mask]
                df_nov = df_amz[~df_amz['sku_norm'].isin(df_ps['sku_norm'].unique())]
                df_final = pd.merge(df_nov, df_plan_f[['sku_norm', col_not_plan]], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    df_viz = df_final[['sku_norm', col_name_amz, col_asin_amz, col_not_plan]].copy()
                    df_viz.columns = ['SKU_FINAL', 'TITULO_PROV', 'ASIN_FINAL', 'NOTAS_REVISION']
                    df_viz.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_viz
                else: st.warning("Sin novedades (excluidos Cluster A y existentes en PS).")
            except Exception as e: st.error(f"Fase 1: {e}")

    if st.session_state.df_previa is not None:
        df_editado = st.data_editor(st.session_state.df_previa, hide_index=True, use_container_width=True)
        if st.button("✅ Confirmar Selección"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success("Cruce guardado.")

# --- FASE 2: GENERADOR ---
with tab2:
    st.header("Generador Final (60 Columnas)")
    if st.session_state.df_revisado is not None:
        c1, c2, c3 = st.columns(3)
        with c1: f_keepa = st.file_uploader("1. Keepa (XLSX)", type=['xlsx'])
        with c2: f_img = st.file_uploader("2. Imágenes (XLSX)", type=['xlsx'])
        with c3: f_cats = st.file_uploader("3. Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar Maestro XLSX"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_excel(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)

                    df_k['KEY_JOIN'] = df_k.iloc[:, 0].str.strip().str.upper()
                    df_m = pd.merge(st.session_state.df_revisado, df_k.drop_duplicates(subset=['KEY_JOIN']), 
                                    left_on='ASIN_FINAL', right_on='KEY_JOIN', how='inner')

                    if df_m.empty: st.error("No hay coincidencias con Keepa.")
                    else:
                        final = pd.DataFrame()
                        # A-C
                        final['Product ID'] = range(900001, 900001 + len(df_m))
                        final['Active (0/1)'] = "1"
                        final['Name *'] = df_m.iloc[:, df_m.columns.get_loc(df_k.columns[2])].apply(lambda x: truncar_texto(x, 128))
                        # D: Categories
                        mapeo_cat = pd.Series(df_c.iloc[:,1].values, index=df_c.iloc[:,0].str.lower().str.strip()).to_dict()
                        final['Categories (x,y,z...)'] = df_m.iloc[:, df_m.columns.get_loc(df_k.columns[3])].apply(lambda x: mapeo_cat.get(str(x).lower().strip(), x))
                        
                        # E-L
                        final['Price tax included'] = "999"; final['Tax rules ID'] = "1"; final['Wholesale price'] = ""
                        final['On sale (0/1)'] = "0"; final['Discount amount'] = ""; final['Discount percent'] = ""
                        final['Discount from (yyyy-mm-dd)'] = ""; final['Discount to (yyyy-mm-dd)'] = ""
                        
                        # M-P
                        final['Reference #'] = df_m['SKU_FINAL']
                        final['Supplier reference #'] = df_m['SKU_FINAL']
                        final['Supplier'] = "Cecotec"; final['Manufacturer'] = "Cecotec"
                        
                        # Q-X
                        final['EAN13'] = df_m.iloc[:, df_m.columns.get_loc(df_k.columns[9])].apply(limpiar_texto)
                        final['UPC'] = ""; final['Ecotax'] = ""
                        for col in ['Width', 'Height', 'Depth', 'Weight']: final[col] = "1"
                        final['Quantity'] = "0"
                        
                        # Y-AG
                        final['Minimal quantity'] = "1"; final['Low stock level'] = ""; final['Visibility'] = ""
                        final['Additional shipping cost'] = ""; final['Unity'] = ""; final['Unit price'] = ""
                        final['Short description'] = ""
                        
                        # AH: Description (E-I)
                        cols_desc = df_k.columns[4:9] 
                        final['Description'] = df_m[cols_desc].fillna('').agg('. '.join, axis=1).apply(lambda x: truncar_texto(x, 2000))
                        
                        # AI-AR
                        final['Tags (x,y,z...)'] = ""; final['Meta title'] = ""; final['Meta keywords'] = ""
                        final['Meta description'] = ""; final['URL rewritten'] = ""
                        final['Text when in stock'] = "In Stock"; final['Text when backorder allowed'] = ""
                        final['Available for order (0 = No, 1 = Yes)'] = "1"; final['Product available date'] = ""; final['Product creation date'] = ""
                        
                        # AS-BH (Final)
                        final['Show price (0 = No, 1 = Yes)'] = "1"
                        col_ref_i = df_i.columns[0]
                        df_i['urls'] = df_i.iloc[:, 1:].fillna('').apply(lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                        img_dict = pd.Series(df_i['urls'].values, index=normalizar_sku(df_i[col_ref_i])).to_dict()
                        final['Image URLs (x,y,z...)'] = final['Reference #'].apply(lambda x: img_dict.get(x, ""))
                        
                        final['Image alt texts (x,y,z...)'] = ""; final['Delete existing images (0 = No, 1 = Yes)'] = "0"
                        final['Feature(Name:Value:Position)'] = ""; final['Available online only (0 = No, 1 = Yes)'] = "1"
                        final['Condition'] = "new"; final['Customizable (0 = No, 1 = Yes)'] = "0"
                        final['Uploadable files (0 = No, 1 = Yes)'] = "0"; final['Text fields (0 = No, 1 = Yes)'] = "0"
                        for col in ['Out of stock', 'ID / Name of shop', 'Advanced stock management', 'Depends On Stock', 'Warehouse']: final[col] = "0"

                        st.session_state.df_final_generado = final.applymap(limpiar_texto)
                        st.success("✅ Generado.")
                except Exception as e: st.error(f"Error: {e}")

if st.session_state.df_final_generado is not None:
    st.divider()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.df_final_generado.to_excel(writer, index=False)
    st.download_button("⬇️ Descargar Maestro XLSX", output.getvalue(), f"Carga_PS_{datetime.now().strftime('%Y%m%d')}.xlsx")