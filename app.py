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

st.title("🐦 Turaco PrestaShop Assistant - v4.28")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar", "📦 FASE 2: Generar Excel"])

# --- FASE 1: IDENTIFICACIÓN ---
with tab1:
    st.header("Auditoría de Novedades")
    c1, c2, c3 = st.columns(3)
    with c1: f_ps = st.file_uploader("1. BBDD PrestaShop", type=['csv', 'xlsx'])
    with c2: f_amz = st.file_uploader("2. Listing Amazon", type=['txt', 'xlsx'])
    with c3: f_plan = st.file_uploader("3. Plan Lanzamiento", type=['xlsx'])

    if all([f_ps, f_amz, f_plan]):
        if st.button("🚀 Iniciar Cruce con Filtros"):
            try:
                # Carga de archivos [cite: 5, 8, 11]
                df_ps = pd.read_csv(f_ps, sep=None, engine='python', dtype=str) if f_ps.name.endswith('.csv') else pd.read_excel(f_ps, dtype=str)
                df_amz = pd.read_excel(f_amz, dtype=str) if f_amz.name.endswith('.xlsx') else pd.read_csv(f_amz, sep='\t', encoding='latin1', dtype=str)
                df_plan = pd.read_excel(f_plan, dtype=str)
                
                # Estandarizar cabeceras [cite: 4]
                df_ps.columns = df_ps.columns.str.lower().str.strip()
                df_amz.columns = df_amz.columns.str.lower().str.strip()
                df_plan.columns = df_plan.columns.str.lower().str.strip()

                # Localización de columnas críticas [cite: 7, 10, 16]
                col_ref_ps = next((c for c in df_ps.columns if 'reference' in c), None)
                col_sku_amz = next((c for c in df_amz.columns if 'seller-sku' in c), None)
                col_asin_amz = next((c for c in df_amz.columns if 'asin' in c), None)
                col_name_amz = next((c for c in df_amz.columns if 'item-name' in c or 'title' in c), None)
                
                col_sku_plan = next((c for c in df_plan.columns if c == 'sku'), df_plan.columns[0])
                col_est_plan = next((c for c in df_plan.columns if 'estado' in c), None)
                col_clu_plan = next((c for c in df_plan.columns if 'cluster' in c), None)
                col_not_plan = next((c for c in df_plan.columns if 'notas' in c), None)

                # Normalización para el cruce [cite: 7]
                df_ps['sku_norm'] = normalizar_sku(df_ps[col_ref_ps])
                df_amz['sku_norm'] = normalizar_sku(df_amz[col_sku_amz])
                df_plan['sku_norm'] = normalizar_sku(df_plan[col_sku_plan])

                # Aplicación de Filtros del Plan [cite: 15, 16]
                estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto", "Solo MAIN"]
                
                mask = df_plan[col_est_plan].isin(estados_ok)
                if col_clu_plan: 
                    mask &= (df_plan[col_clu_plan].astype(str).str.upper() != 'A')
                if col_not_plan: 
                    mask &= (df_plan[col_not_plan].isna() | (df_plan[col_not_plan].astype(str).str.strip() == ""))

                df_plan_f = df_plan[mask]

                # Cruce: Solo lo que NO está en PS y SÍ está en el Plan Filtrado [cite: 6]
                df_nov = df_amz[~df_amz['sku_norm'].isin(df_ps['sku_norm'].unique())]
                df_final = pd.merge(df_nov, df_plan_f[['sku_norm']], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    df_viz = df_final[['sku_norm', col_name_amz, col_asin_amz]].copy()
                    df_viz.columns = ['SKU_FINAL', 'TITULO_PROV', 'ASIN_FINAL']
                    df_viz.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_viz
                else: 
                    st.warning("No se han encontrado novedades con los filtros aplicados (Cluster != A y Sin Notas).")
            except Exception as e: 
                st.error(f"Error en el Cruce: {e}. Asegúrate de que las columnas 'reference', 'seller-sku', 'sku' y 'estado' existen.")

    if st.session_state.df_previa is not None:
        df_editado = st.data_editor(st.session_state.df_previa, hide_index=True, use_container_width=True)
        if st.button("✅ Confirmar Selección"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success("Cruce confirmado. Pasa a la Fase 2.")

# --- FASE 2: GENERADOR ---
with tab2:
    st.header("Generador de Fichero Maestro")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Primero confirma la selección en la Fase 1.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1: f_keepa = st.file_uploader("1. Keepa (XLSX)", type=['xlsx'])
        with c2: f_img = st.file_uploader("2. Imágenes (XLSX)", type=['xlsx'])
        with c3: f_cats = st.file_uploader("3. Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar Excel Final"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_excel(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)

                    # Unión por posición física (Columna A de Keepa es el ASIN) [cite: 20]
                    df_k['KEY_JOIN'] = df_k.iloc[:, 0].str.strip().str.upper()
                    df_m = pd.merge(st.session_state.df_revisado, df_k.drop_duplicates(subset=['KEY_JOIN']), 
                                    left_on='ASIN_FINAL', right_on='KEY_JOIN', how='inner')

                    if df_m.empty:
                        st.error("No hay coincidencia de ASINs entre tu selección y el archivo de Keepa.")
                    else:
                        final = pd.DataFrame()
                        # Generación de IDs secuenciales [cite: 25]
                        final['Product ID'] = range(900001, 900001 + len(df_m))
                        final['Active (0/1)'] = "1"
                        # Name -> Columna C de Keepa [cite: 20]
                        final['Name *'] = df_m.iloc[:, df_m.columns.get_loc(df_k.columns[2])].apply(lambda x: truncar_texto(x, 128))
                        # Categories -> Columna D de Keepa + Mapeo [cite: 20, 24]
                        mapeo_cat = pd.Series(df_c.iloc[:,1].values, index=df_c.iloc[:,0].str.lower().str.strip()).to_dict()
                        final['Categories (x,y,z...)'] = df_m.iloc[:, df_m.columns.get_loc(df_k.columns[3])].apply(lambda x: mapeo_cat.get(str(x).lower().strip(), x))
                        
                        final['Price tax included'] = "999"; final['Tax rules ID'] = "1"
                        final['Reference #'] = df_m['SKU_FINAL']
                        # EAN -> Columna J de Keepa [cite: 20]
                        final['EAN13'] = df_m.iloc[:, df_m.columns.get_loc(df_k.columns[9])].apply(limpiar_texto)
                        
                        # Descripción -> Concatenación E a I de Keepa [cite: 20]
                        cols_desc_keepa = df_k.columns[4:9] 
                        final['Description'] = df_m[cols_desc_keepa].fillna('').agg('. '.join, axis=1).apply(lambda x: truncar_texto(x, 2000))
                        
                        # Imágenes [cite: 22]
                        col_ref_i = df_i.columns[0]
                        df_i['urls_merged'] = df_i.iloc[:, 1:].fillna('').apply(lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                        img_dict = pd.Series(df_i['urls_merged'].values, index=normalizar_sku(df_i[col_ref_i])).to_dict()
                        final['Image URLs (x,y,z...)'] = final['Reference #'].apply(lambda x: img_dict.get(x, ""))
                        
                        # Campos fijos finales [cite: 25]
                        final['Condition'] = "new"
                        final['On sale (0/1)'] = "0"
                        final['Supplier'] = "Cecotec"; final['Manufacturer'] = "Cecotec"
                        final['Show price (0 = No, 1 = Yes)'] = "1"
                        final['Available for order (0 = No, 1 = Yes)'] = "1"

                        st.session_state.df_final_generado = final.applymap(limpiar_texto)
                        st.success(f"✅ Fichero generado con {len(final)} productos.")

                except Exception as e: st.error(f"Error técnico en Fase 2: {e}")

if st.session_state.df_final_generado is not None:
    st.divider()
    st.dataframe(st.session_state.df_final_generado, use_container_width=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.df_final_generado.to_excel(writer, index=False)
    st.download_button(label="⬇️ Descargar Excel Final", data=output.getvalue(), file_name=f"Carga_PS_{datetime.now().strftime('%Y%m%d')}.xlsx")