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

# Persistencia de estados
for key in ['df_revisado', 'df_previa', 'df_final_generado']:
    if key not in st.session_state: st.session_state[key] = None

st.title("🐦 Turaco PrestaShop Assistant - v4.26")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar", "📦 FASE 2: Generar CSV"])

# --- FASE 1: IDENTIFICACIÓN (Con Filtros de Cluster y Notas) ---
with tab1:
    st.header("Auditoría de Novedades")
    c1, c2, c3 = st.columns(3)
    with c1: f_ps = st.file_uploader("1. BBDD PrestaShop", type=['csv', 'xlsx'])
    with c2: f_amz = st.file_uploader("2. Listing Amazon", type=['txt', 'xlsx'])
    with c3: f_plan = st.file_uploader("3. Plan Lanzamiento", type=['xlsx'])

    if all([f_ps, f_amz, f_plan]):
        if st.button("🚀 Iniciar Cruce con Filtros"):
            try:
                df_ps = pd.read_csv(f_ps, sep=None, engine='python', dtype=str) if f_ps.name.endswith('.csv') else pd.read_excel(f_ps, dtype=str)
                df_amz = pd.read_excel(f_amz, dtype=str) if f_amz.name.endswith('.xlsx') else pd.read_csv(f_amz, sep='\t', encoding='latin1', dtype=str)
                df_plan = pd.read_excel(f_plan, dtype=str)
                
                for d in [df_ps, df_amz, df_plan]: d.columns = d.columns.str.lower().str.strip()

                col_ref_ps = next(c for c in df_ps.columns if 'reference' in c)
                col_sku_amz = next(c for c in df_amz.columns if 'seller-sku' in c)
                col_sku_plan = next(c for c in df_plan.columns if 'sku' in c)
                col_asin_amz = next(c for c in df_amz.columns if 'asin1' in df_amz.columns or 'asin' in df_amz.columns) # Flexible ASIN1
                
                col_cluster = next((c for c in df_plan.columns if 'cluster' in c), None)
                col_notas = next((c for c in df_plan.columns if 'notas' in c), None)

                df_ps['sku_norm'] = normalizar_sku(df_ps[col_ref_ps])
                df_amz['sku_norm'] = normalizar_sku(df_amz[col_sku_amz])
                df_plan['sku_norm'] = normalizar_sku(df_plan[col_sku_plan])

                # FILTROS: Cluster != A y Notas vacías
                mask_plan = (df_plan['estado'].isin(["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto", "Solo MAIN"]))
                if col_cluster: mask_plan &= (df_plan[col_cluster].astype(str).str.upper() != "A")
                if col_notas: mask_plan &= (df_plan[col_notas].isna() | (df_plan[col_notas].astype(str).str.strip() == ""))

                df_nov = df_amz[~df_amz['sku_norm'].isin(df_ps['sku_norm'].unique())]
                df_f = pd.merge(df_nov, df_plan[mask_plan][['sku_norm']], on='sku_norm', how='inner')
                
                if not df_f.empty:
                    df_viz = df_f[['sku_norm', df_amz.columns[2], df_amz.columns[3]]].copy() # Usando índices para mayor seguridad
                    df_viz.columns = ['SKU_FINAL', 'TITULO_PROV', 'ASIN_FINAL']
                    df_viz.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_viz
                else: st.warning("No hay novedades tras aplicar filtros.")
            except Exception as e: st.error(f"Fase 1: {e}")

    if st.session_state.df_previa is not None:
        df_editado = st.data_editor(st.session_state.df_previa, hide_index=True)
        if st.button("✅ Confirmar Selección"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success("Selección confirmada.")

# --- FASE 2: GENERADOR (Mapeo corregido según Excel real) ---
with tab2:
    st.header("Generador Final")
    if st.session_state.df_revisado is not None:
        c1, c2, c3 = st.columns(3)
        with c1: f_keepa = st.file_uploader("1. Keepa (Excel real)", type=['xlsx'])
        with c2: f_img = st.file_uploader("2. Imágenes (XLSX)", type=['xlsx'])
        with c3: f_cats = st.file_uploader("3. Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar CSV PrestaShop"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_excel(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)

                    # KEY JOIN: Columna A de Keepa (ASIN)
                    df_k['KEY_JOIN'] = df_k.iloc[:, 0].str.strip().str.upper()
                    df_m = pd.merge(st.session_state.df_revisado, df_k.drop_duplicates(subset=['KEY_JOIN']), 
                                    left_on='ASIN_FINAL', right_on='KEY_JOIN', how='inner')

                    if df_m.empty:
                        st.error("No hay coincidencia de ASINs. Revisa que el Excel de Keepa sea el correcto.")
                    else:
                        final = pd.DataFrame()
                        
                        # MAPEO SEGÚN EXCEL REAL:
                        final['Product ID'] = range(900001, 900001 + len(df_m))
                        final['Active (0/1)'] = "1"
                        # Name -> Columna C de Keepa (Título)
                        final['Name *'] = df_m.iloc[:, df_m.columns.get_loc(df_k.columns[2])].apply(lambda x: truncar_texto(x, 128))
                        
                        # Categories -> Columna D de Keepa (Subcategoría) + Mapeo
                        mapeo_cat = pd.Series(df_c.iloc[:,1].values, index=df_c.iloc[:,0].str.lower().str.strip()).to_dict()
                        final['Categories (x,y,z...)'] = df_m.iloc[:, df_m.columns.get_loc(df_k.columns[3])].apply(lambda x: mapeo_cat.get(str(x).lower().strip(), x))
                        
                        final['Reference #'] = df_m['SKU_FINAL']
                        # EAN13 -> Columna J de Keepa (Códigos de producto: EAN)
                        final['EAN13'] = df_m.iloc[:, df_m.columns.get_loc(df_k.columns[9])].apply(limpiar_texto)
                        
                        # Description -> Concatenación Columnas E a I de Keepa (Descripción & Características)
                        cols_desc_keepa = df_k.columns[4:9] 
                        final['Description'] = df_m[cols_desc_keepa].fillna('').agg('. '.join, axis=1).apply(lambda x: truncar_texto(x, 2000))
                        
                        # Valores fijos solicitados
                        final['Condition'] = "new"
                        final['On sale (0/1)'] = "0"
                        final['Price tax included'] = "999"
                        final['Supplier'] = "Cecotec"
                        final['Manufacturer'] = "Cecotec"
                        final['Show price (0 = No, 1 = Yes)'] = "1"
                        final['Available for order (0 = No, 1 = Yes)'] = "1"

                        # Imágenes
                        col_ref_i = next((c for c in df_i.columns if 'reference' in c.lower() or 'sku' in c.lower()), df_i.columns[0])
                        df_i['urls_merged'] = df_i.iloc[:, 1:].fillna('').apply(lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                        img_dict = pd.Series(df_i['urls_merged'].values, index=normalizar_sku(df_i[col_ref_i])).to_dict()
                        final['Image URLs (x,y,z...)'] = final['Reference #'].apply(lambda x: img_dict.get(x, ""))

                        st.session_state.df_final_generado = final.applymap(limpiar_texto)
                        st.success("✅ CSV generado con el mapeo real del Excel.")

                except Exception as e: st.error(f"Error técnico: {e}")

if st.session_state.df_final_generado is not None:
    st.divider()
    st.dataframe(st.session_state.df_final_generado, use_container_width=True)
    csv_buf = io.StringIO()
    st.session_state.df_final_generado.to_csv(csv_buf, index=False, sep=',', encoding='utf-8')
    st.download_button(label="⬇️ Descargar CSV", data=csv_buf.getvalue(), file_name=f"Carga_PS_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")