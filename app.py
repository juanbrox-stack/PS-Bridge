import streamlit as st
import pandas as pd
import io
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Turaco PS Helper PRO", page_icon="🐦", layout="wide")

# Inicialización forzada de estados
for key in ['df_revisado', 'df_previa', 'df_final_generado']:
    if key not in st.session_state:
        st.session_state[key] = None

def limpiar_texto_excel(texto):
    if pd.isna(texto): return ""
    return str(texto).replace('\n', ' ').replace('\r', ' ').strip()

def normalizar_sku(serie):
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def truncar_texto(texto, limite):
    texto = limpiar_texto_excel(texto)
    if len(texto) <= limite: return texto
    recorte = texto[:limite]
    punto_corte = max(recorte.rfind('.'), recorte.rfind(' '))
    return recorte[:punto_corte].strip() if punto_corte != -1 else recorte

st.title("🐦 Turaco PrestaShop Assistant - v4.16")

tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar", "📦 FASE 2: Generar"])

# --- FASE 1: IDENTIFICAR ---
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
                
                # Normalización de cabeceras
                for d in [df_ps, df_amz, df_plan]: d.columns = d.columns.str.lower().str.strip()
                
                # Identificar columnas clave por contenido/nombre
                col_ref_ps = next((c for c in df_ps.columns if 'reference' in c), df_ps.columns[0])
                col_sku_amz = next((c for c in df_amz.columns if 'seller-sku' in c), df_amz.columns[0])
                col_sku_plan = next((c for c in df_plan.columns if 'sku' in c), df_plan.columns[0])
                col_asin_amz = next((c for c in df_amz.columns if 'asin' in c), df_amz.columns[-1])
                col_name_amz = next((c for c in df_amz.columns if 'item-name' in c or 'title' in c), df_amz.columns[1])

                df_ps['sku_norm'] = normalizar_sku(df_ps[col_ref_ps])
                df_amz['sku_norm'] = normalizar_sku(df_amz[col_sku_amz])
                df_plan['sku_norm'] = normalizar_sku(df_plan[col_sku_plan])
                
                estados_v = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto", "Solo MAIN"]
                df_nov = df_amz[~df_amz['sku_norm'].isin(df_ps['sku_norm'].unique())]
                df_final = pd.merge(df_nov, df_plan[df_plan['estado'].isin(estados_v)][['sku_norm', 'notas', 'estado']], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    # Estandarizamos para la tabla de edición
                    df_viz = df_final[['sku_norm', col_name_amz, col_asin_amz, 'notas']].copy()
                    df_viz.columns = ['SKU_FINAL', 'TITULO_PROV', 'ASIN_FINAL', 'NOTAS']
                    df_viz['ASIN_FINAL'] = df_viz['ASIN_FINAL'].str.strip().str.upper()
                    df_viz.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_viz
                else: st.warning("No se detectaron novedades.")
            except Exception as e: st.error(f"Fase 1: {e}")

    if st.session_state.df_previa is not None:
        df_editado = st.data_editor(st.session_state.df_previa, hide_index=True)
        if st.button("✅ Confirmar Selección"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success(f"Confirmados {len(st.session_state.df_revisado)} productos.")

# --- FASE 2: GENERADOR ---
with tab2:
    st.header("Generador Final")
    # Validación de seguridad: comprobamos si existe la columna en el DF de memoria
    if st.session_state.df_revisado is None or 'ASIN_FINAL' not in st.session_state.df_revisado.columns:
        st.info("⚠️ Primero completa y confirma la selección en la Fase 1.")
    else:
        c1, c2 = st.columns(2)
        with c1: f_keepa = st.file_uploader("1. Keepa (XLSX)", type=['xlsx'])
        with c2: 
            f_img = st.file_uploader("2. Imágenes (XLSX)", type=['xlsx'])
            f_cats = st.file_uploader("3. Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar Excel PrestaShop"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_excel(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)

                    # --- CRUCE CIEGO (Keepa) ---
                    # Usamos la primera columna del Excel (A) sin importar cómo se llame
                    col_key_keepa = df_k.columns[0]
                    df_k['KEY_JOIN'] = df_k[col_key_keepa].str.strip().str.upper()
                    
                    df_m = pd.merge(st.session_state.df_revisado, df_k.drop_duplicates(subset=['KEY_JOIN']), 
                                    left_on='ASIN_FINAL', right_on='KEY_JOIN', how='inner')

                    if df_m.empty:
                        st.error("❌ Los ASINs seleccionados no coinciden con la primera columna de tu Keepa.")
                    else:
                        final = pd.DataFrame()
                        final['Product ID'] = range(900001, 900001 + len(df_m))
                        final['Active (0/1)'] = "1"
                        
                        # Título: Índice 2 (Columna C)
                        final['Name *'] = df_m.iloc[:, df_m.columns.get_loc('KEY_JOIN') - len(df_k.columns) + 2].apply(lambda x: truncar_texto(x, 128))
                        final['Reference #'] = df_m['SKU_FINAL']
                        
                        # EAN: Índice 9 (Columna J)
                        col_ean = df_k.columns[9] if len(df_k.columns) > 9 else df_k.columns[-1]
                        final['EAN13'] = df_m[col_ean].apply(limpiar_texto_excel)
                        
                        # Categorías
                        col_sub = next((c for c in df_k.columns if 'subcategoría' in str(c).lower()), df_k.columns[3])
                        mapeo_cat = pd.Series(df_c.iloc[:,1].values, index=df_c.iloc[:,0].str.lower().str.strip()).to_dict()
                        final['Categories (x,y,z...)'] = df_m[col_sub].apply(lambda x: mapeo_cat.get(str(x).lower().strip(), x))
                        
                        # Características (Descripción)
                        cols_car = [c for c in df_m.columns if 'característica' in str(c).lower()]
                        cols_car.sort(reverse=True)
                        final['Description'] = df_m[cols_car].fillna('').agg('. '.join, axis=1).apply(lambda x: truncar_texto(x, 2000))
                        
                        # Imágenes
                        col_ref_i = next((c for c in df_i.columns if 'reference' in str(c).lower() or 'sku' in str(c).lower()), df_i.columns[0])
                        df_i['urls'] = df_i.iloc[:, 1:].fillna('').apply(lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                        img_dict = pd.Series(df_i['urls'].values, index=normalizar_sku(df_i[col_ref_i])).to_dict()
                        final['Image URLs (x,y,z...)'] = final['Reference #'].apply(lambda x: img_dict.get(x, ""))
                        
                        # Relleno PrestaShop
                        for c, v in {'Price tax included':"999", 'Tax rules ID':"1", 'Supplier':"Cecotec", 'Manufacturer':"Cecotec", 'Quantity':"0", 'Condition':"new", 'Show price (0 = No, 1 = Yes)':"1"}.items():
                            final[c] = v

                        st.session_state.df_final_generado = final.applymap(limpiar_texto_excel)
                        st.success(f"✅ Excel generado: {len(final)} productos.")

                except Exception as e:
                    st.error(f"Error técnico durante la generación: {e}")

# --- DESCARGA ---
if st.session_state.df_final_generado is not None:
    st.divider()
    st.dataframe(st.session_state.df_final_generado, use_container_width=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.df_final_generado.to_excel(writer, index=False)
    st.download_button("⬇️ Descargar Fichero Final", output.getvalue(), f"Novedades_PS_{datetime.now().strftime('%H%M')}.xlsx")