import streamlit as st
import pandas as pd
import io
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Turaco PS Helper PRO", page_icon="🐦", layout="wide")

# Inicialización de estados
for key in ['df_revisado', 'df_previa', 'df_final_generado']:
    if key not in st.session_state:
        st.session_state[key] = None

def limpiar_texto_excel(texto):
    if pd.isna(texto): return ""
    return str(texto).replace('\n', ' ').replace('\r', ' ').strip()

def normalizar_sku(serie):
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave):
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

def truncar_texto(texto, limite):
    texto = limpiar_texto_excel(texto)
    if len(texto) <= limite: return texto
    recorte = texto[:limite]
    punto_corte = max(recorte.rfind('.'), recorte.rfind(' '))
    return recorte[:punto_corte].strip() if punto_corte != -1 else recorte

st.title("🐦 Turaco PrestaShop Assistant - v4.9")

# --- GUÍA VISUAL ---
with st.expander("📋 Estructura Keepa Requerida"):
    st.write("1. **ASIN** | 2. **Modelo** (SKU) | 3. **Título** | 4. **Subcategoría** | 5-9. **Características** | 10. **EAN**")

tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar", "📦 FASE 2: Generar"])

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
                
                df_ps['sku_norm'] = normalizar_sku(df_ps[buscar_columna(df_ps, ['reference'])])
                df_amz['sku_norm'] = normalizar_sku(df_amz[buscar_columna(df_amz, ['seller-sku'])])
                df_plan['sku_norm'] = normalizar_sku(df_plan[buscar_columna(df_plan, ['sku'])])
                
                estados_v = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto", "Solo MAIN"]
                df_nov = df_amz[~df_amz['sku_norm'].isin(df_ps['sku_norm'].unique())]
                df_final = pd.merge(df_nov, df_plan[df_plan['estado'].isin(estados_v)][['sku_norm', 'notas']], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    col_asin_orig = buscar_columna(df_final, ['asin'])
                    col_name_orig = buscar_columna(df_final, ['item-name', 'title'])
                    
                    # Forzamos nombres de columnas para evitar el KeyError posterior
                    df_viz = df_final[['sku_norm', col_name_orig, col_asin_orig, 'notas']].copy()
                    df_viz.columns = ['SKU', 'item-name', 'ASIN', 'notas'] 
                    df_viz.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_viz
                else: st.warning("Sin novedades.")
            except Exception as e: st.error(f"Error Fase 1: {e}")

    if st.session_state.df_previa is not None:
        df_editado = st.data_editor(st.session_state.df_previa, hide_index=True)
        if st.button("✅ Confirmar"):
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success("Cruce confirmado.")

# --- FASE 2 ---
with tab2:
    st.header("Generador Final")
    if st.session_state.df_revisado is None:
        st.info("⚠️ Completa la Fase 1.")
    else:
        c1, c2 = st.columns(2)
        with c1: f_keepa = st.file_uploader("1. Keepa (XLSX)", type=['xlsx'])
        with c2: 
            f_img = st.file_uploader("2. Imágenes (XLSX)", type=['xlsx'])
            f_cats = st.file_uploader("3. Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar Excel"):
                try:
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_excel(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)
                    for d in [df_k, df_i, df_c]: d.columns = d.columns.str.lower().str.strip()

                    # Buscamos el ASIN en Keepa dinámicamente
                    c_asin_keepa = buscar_columna(df_k, ['asin'])
                    
                    # Aseguramos que el cruce use la columna 'ASIN' que forzamos en la Fase 1
                    df_m = pd.merge(st.session_state.df_revisado, df_k.drop_duplicates(subset=[c_asin_keepa]), left_on='ASIN', right_on=c_asin_keepa, how='inner')

                    if df_m.empty:
                        st.error("No se han encontrado coincidencias entre tu selección y el fichero de Keepa (revisa los ASINs).")
                    else:
                        final = pd.DataFrame()
                        final['Product ID'] = range(900001, 900001 + len(df_m))
                        final['Active (0/1)'] = "1"
                        final['Name *'] = df_m[buscar_columna(df_k, ['título', 'title'])].apply(lambda x: truncar_texto(x, 128))
                        
                        mapeo = pd.Series(df_c[buscar_columna(df_c, ['prestashop', 'destino'])].values, index=df_c[buscar_columna(df_c, ['amazon', 'origen'])].str.lower().str.strip()).to_dict()
                        final['Categories (x,y,z...)'] = df_m[buscar_columna(df_k, ['subcategoría'])].apply(lambda x: mapeo.get(str(x).lower().strip(), x))
                        
                        final['Reference #'] = df_m['SKU']
                        final['EAN13'] = df_m[buscar_columna(df_k, ['ean', 'códigos'])].apply(limpiar_texto_excel)
                        
                        cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                        cols_car.sort(reverse=True) 
                        final['Description'] = df_m[cols_car].fillna('').agg('. '.join, axis=1).apply(lambda x: truncar_texto(x, 2000)) if cols_car else ""
                        
                        c_ref_i = buscar_columna(df_i, ['reference', 'sku'])
                        df_i[c_ref_i] = normalizar_sku(df_i[c_ref_i])
                        cols_url = [c for c in df_i.columns if c != c_ref_i]
                        df_i['urls_tmp'] = df_i[cols_url].fillna('').apply(lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                        df_i_map = df_i.drop_duplicates(subset=[c_ref_i]).set_index(c_ref_i)['urls_tmp'].to_dict()
                        final['Image URLs (x,y,z...)'] = final['Reference #'].apply(lambda x: df_i_map.get(normalizar_sku(pd.Series(x)).iloc[0], ""))
                        
                        for c, v in {'Price tax included':"999", 'Tax rules ID':"1", 'Supplier':"Cecotec", 'Manufacturer':"Cecotec", 'Quantity':"0", 'Condition':"new", 'Show price (0 = No, 1 = Yes)':"1"}.items():
                            final[c] = v

                        st.session_state.df_final_generado = final.applymap(limpiar_texto_excel)
                        st.success("✅ Generado con éxito.")
                except Exception as e: st.error(f"Error en Generador: {e}")

        if st.session_state.df_final_generado is not None:
            st.divider()
            st.dataframe(st.session_state.df_final_generado, use_container_width=True)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                st.session_state.df_final_generado.to_excel(writer, index=False)
            st.download_button("⬇️ Descargar Excel", output.getvalue(), f"{datetime.now().strftime('%Y%m%d')}_Novedades.xlsx")