import streamlit as st
import pandas as pd
import io

# --- CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Turaco PS Helper PRO", page_icon="🐦", layout="wide")

def normalizar_sku(serie):
    """Limpia espacios, mayúsculas y quita ceros a la izquierda para comparaciones."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave):
    """Busca una columna de forma flexible por palabras clave."""
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

# Inicializar estados de la sesión
if 'df_previa' not in st.session_state:
    st.session_state.df_previa = None
if 'df_revisado' not in st.session_state:
    st.session_state.df_revisado = None

st.title("🐦 Turaco PrestaShop Manager - Flujo Optimizado")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar y Auditar", "📦 FASE 2: Generar Carga Final"])

# --- FASE 1: IDENTIFICAR Y REVISAR ---
with tab1:
    st.header("1. Buscador de Novedades con Filtro de Notas")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        f_ps = st.file_uploader("BBDD PrestaShop (CSV/XLSX)", type=['csv', 'xlsx'])
    with c2:
        f_amz = st.file_uploader("Listing Amazon (TXT/XLSX)", type=['txt', 'xlsx'])
    with c3:
        f_plan = st.file_uploader("Plan Lanzamiento (XLSX)", type=['xlsx'])

    if all([f_ps, f_amz, f_plan]):
        if st.button("🚀 Ejecutar Cruce de Datos"):
            try:
                # Lectura de archivos
                if f_ps.name.endswith('.csv'):
                    df_ps = pd.read_csv(f_ps, sep=None, engine='python', dtype=str)
                else:
                    df_ps = pd.read_excel(f_ps, dtype=str)
                
                df_amz = pd.read_excel(f_amz, dtype=str) if f_amz.name.endswith('.xlsx') else pd.read_csv(f_amz, sep='\t', encoding='latin1', dtype=str)
                df_plan = pd.read_excel(f_plan, dtype=str)

                # Limpieza de nombres de columnas
                for df in [df_ps, df_amz, df_plan]:
                    df.columns = df.columns.str.lower().str.strip()

                # Normalización de SKUs
                df_ps['sku_norm'] = normalizar_sku(df_ps['reference'])
                df_amz['sku_norm'] = normalizar_sku(df_amz['seller-sku'])
                df_plan['sku_norm'] = normalizar_sku(df_plan['sku'])

                # Filtro de Estados del Plan
                estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto"]
                df_plan_f = df_plan[df_plan['estado'].isin(estados_ok)]

                # Identificar novedades (No están en PS)
                skus_en_ps = df_ps['sku_norm'].unique()
                df_nov = df_amz[~df_amz['sku_norm'].isin(skus_en_ps)]
                
                # Unir con Plan para traer Notas y Estado
                df_final = pd.merge(df_nov, df_plan_f[['sku_norm', 'estado', 'notas']], on='sku_norm', how='inner')
                
                if not df_final.empty:
                    df_final.insert(0, "Seleccionado", True)
                    st.session_state.df_previa = df_final
                else:
                    st.warning("No se encontraron novedades que cumplan los requisitos.")
            except Exception as e:
                st.error(f"Error en el cruce: {e}")

    # --- TABLA INTERACTIVA ---
    if st.session_state.df_previa is not None:
        st.divider()
        st.subheader("📋 Auditoría de Registros")
        
        # FILTRO RÁPIDO: Solo con notas
        solo_notas = st.toggle("🎯 Mostrar solo productos con avisos en 'Notas'", value=False)
        
        df_a_mostrar = st.session_state.df_previa
        if solo_notas:
            df_a_mostrar = df_a_mostrar[df_a_mostrar['notas'].fillna('').str.strip() != ""]

        # Editor interactivo
        df_editado = st.data_editor(
            df_a_mostrar,
            column_config={
                "Seleccionado": st.column_config.CheckboxColumn("¿Procesar?", default=True),
                "seller-sku": "SKU Amazon",
                "notas": st.column_config.TextColumn("Notas Plan (Avisos Críticos)", width="large"),
                "sku_norm": None # Ocultamos columna técnica
            },
            disabled=["seller-sku", "asin1", "estado", "notas"],
            hide_index=True,
            use_container_width=True,
            key="editor_novedades"
        )

        if st.button("✅ Confirmar Selección y Pasar a Fase 2"):
            # Actualizamos el estado global con los cambios del editor
            st.session_state.df_revisado = df_editado[df_editado["Seleccionado"] == True].copy()
            st.success(f"¡Hecho! {len(st.session_state.df_revisado)} productos listos en memoria. Cambia a la pestaña Fase 2.")

# --- FASE 2: GENERAR CARGA ---
with tab2:
    st.header("2. Generador de Carga PrestaShop")
    
    if st.session_state.df_revisado is None:
        st.info("⚠️ Primero completa la revisión en la Pestaña 1.")
    else:
        st.write(f"Procesando **{len(st.session_state.df_revisado)}** productos validados.")
        
        c1, c2 = st.columns(2)
        with c1:
            f_keepa = st.file_uploader("Exportación Keepa (XLSX)", type=['xlsx'])
        with c2:
            f_img = st.file_uploader("Exportación Imágenes (CSV)", type=['csv'])
            f_cats = st.file_uploader("Mapeo Categorías (XLSX)", type=['xlsx'])

        if all([f_keepa, f_img, f_cats]):
            if st.button("🪄 Generar Fichero Final"):
                try:
                    # Carga de datos de Fase 2
                    df_k = pd.read_excel(f_keepa, dtype=str)
                    df_i = pd.read_csv(f_img, dtype=str)
                    df_c = pd.read_excel(f_cats, dtype=str)
                    df_l = st.session_state.df_revisado # Datos de Fase 1

                    for d in [df_k, df_i, df_c]:
                        d.columns = d.columns.str.lower().str.strip()

                    # Identificación de columnas
                    c_asin_k = buscar_columna(df_k, ['asin'])
                    c_ean_k = buscar_columna(df_k, ['ean'])
                    c_tit_k = buscar_columna(df_k, ['título', 'title'])
                    c_cat_k = buscar_columna(df_k, ['categorías: subcategoría'])
                    c_cat_amz = buscar_columna(df_c, ['amazon', 'origen'])
                    c_cat_ps = buscar_columna(df_c, ['prestashop', 'destino'])
                    c_asin_l = 'asin1' if 'asin1' in df_l.columns else 'asin'

                    # Cruce y Construcción
                    df_m = pd.merge(df_l, df_k, left_on=c_asin_l, right_on=c_asin_k, how='inner')

                    res = pd.DataFrame()
                    res['Product ID'] = range(900001, 900001 + len(df_m))
                    res['Active (0/1)'] = "1"
                    res['Reference #'] = df_m['seller-sku']
                    res['Name *'] = df_m[c_tit_k].str.slice(0, 128)
                    res['EAN13'] = df_m[c_ean_k] if c_ean_k else ""
                    res['Price tax included'] = "999"
                    res['Supplier'] = 'Cecotec'
                    res['Manufacturer'] = 'Cecotec'

                    # Descripción
                    cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                    res['Description'] = df_m[cols_car].fillna('').agg(' '.join, axis=1).str.slice(0, 2000)

                    # Mapeo de Categorías
                    mapeo = pd.Series(df_c[c_cat_ps].values, index=df_c[c_cat_amz].str.lower().str.strip()).to_dict()
                    res['Categories (x,y,z...)'] = df_m[c_cat_k].apply(lambda x: mapeo.get(str(x).lower().strip(), x))

                    # Imágenes
                    df_i['urls'] = df_i.drop(columns=['reference'], errors='ignore').fillna('').apply(
                        lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                    res = pd.merge(res, df_i[['reference', 'urls']].drop_duplicates('reference'), 
                                   left_on='Reference #', right_on='reference', how='left')

                    res.rename(columns={'urls': 'Image URLs (x,y,z...)'}, inplace=True)
                    res['Text when in stock'] = 'In Stock'
                    res['Available for order (0 = No, 1 = Yes)'] = "1"
                    res['Show price (0 = No, 1 = Yes)'] = "1"

                    # Exportación Final
                    csv_buf = io.StringIO()
                    res.to_csv(csv_buf, index=False, sep=',', encoding='utf-8-sig')
                    
                    st.success(f"✅ ¡ÉXITO! Fichero generado con {len(res)} productos.")
                    st.download_button("⬇️ Descargar CSV PrestaShop", csv_buf.getvalue(), "subida_final_revisada.csv", "text/csv")

                except Exception as e:
                    st.error(f"Error en Fase 2: {e}")