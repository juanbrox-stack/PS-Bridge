import streamlit as st
import pandas as pd
import io
import os

# --- CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Turaco PS Helper", page_icon="🐦", layout="wide")

def normalizar_sku(serie):
    """Limpia espacios, mayúsculas y quita ceros a la izquierda para comparaciones exactas."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

def buscar_columna(df, palabras_clave):
    """Busca una columna de forma flexible por palabras clave."""
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

st.title("🐦 Turaco PrestaShop Manager")
tab1, tab2 = st.tabs(["🔍 FASE 1: Identificar Novedades", "📦 FASE 2: Generar Carga PrestaShop"])

# --- FASE 1: IDENTIFICAR PRODUCTOS PARA KEEPA ---
with tab1:
    st.header("1. Buscador de Novedades")
    st.write("Sube tus archivos para saber qué productos de Amazon faltan en tu BBDD.")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        f_ps = st.file_uploader("BBDD PrestaShop (CSV/XLSX)", type=['csv', 'xlsx'], key="ps1")
    with col2:
        f_amz = st.file_uploader("Listing Amazon (TXT/XLSX)", type=['txt', 'xlsx'], key="amz1")
    with col3:
        f_plan = st.file_uploader("Plan Lanzamiento (XLSX)", type=['xlsx'], key="plan1")

    if all([f_ps, f_amz, f_plan]):
        if st.button("🚀 Ejecutar Cruce de Novedades"):
            try:
                # Lectura flexible de la BBDD (Manejo de ';' automático)
                if f_ps.name.endswith('.csv'):
                    df_ps = pd.read_csv(f_ps, sep=None, engine='python', dtype=str)
                else:
                    df_ps = pd.read_excel(f_ps, dtype=str)
                
                # Lectura de Amazon (Manejo de codificación Mac)
                if f_amz.name.endswith('.txt'):
                    df_amz = pd.read_csv(f_amz, sep='\t', encoding='latin1', dtype=str)
                else:
                    df_amz = pd.read_excel(f_amz, dtype=str)
                
                df_plan = pd.read_excel(f_plan, dtype=str)

                # Limpieza de columnas
                for df in [df_ps, df_amz, df_plan]:
                    df.columns = df.columns.str.lower().str.strip()

                # Normalización de SKUs
                df_ps['sku_norm'] = normalizar_sku(df_ps['reference'])
                df_amz['sku_norm'] = normalizar_sku(df_amz['seller-sku'])
                df_plan['sku_norm'] = normalizar_sku(df_plan['sku'])

                # Filtro por Estados del Plan
                estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto"]
                df_plan_f = df_plan[df_plan['estado'].isin(estados_ok)]

                # Identificar NO existentes en PS
                skus_en_ps = df_ps['sku_norm'].unique()
                df_nov = df_amz[~df_amz['sku_norm'].isin(skus_en_ps)]

                # Cruce final con Plan
                df_final = pd.merge(df_nov, df_plan_f[['sku_norm']], on='sku_norm', how='inner')

                if df_final.empty:
                    st.warning("No se encontraron novedades con esos estados.")
                else:
                    st.success(f"✅ Se han detectado {len(df_final)} novedades.")
                    # Usar nombres reales de tus columnas
                    col_asin = 'asin1' if 'asin1' in df_final.columns else 'asin'
                    res_keepa = df_final[['seller-sku', col_asin]]
                    
                    output = io.BytesIO()
                    res_keepa.to_excel(output, index=False)
                    st.download_button("⬇️ Descargar Lista para Keepa", output.getvalue(), "lista_para_keepa.xlsx")
                    st.dataframe(res_keepa)

            except Exception as e:
                st.error(f"Error: {e}")

# --- FASE 2: GENERADOR DE FICHERO PRESTASHOP (CORREGIDO) ---
with tab2:
    st.header("2. Constructor de Carga Final")
    st.write("Sube los resultados de Keepa e imágenes para generar el CSV de subida.")
    
    c1, c2 = st.columns(2)
    with c1:
        f_lista = st.file_uploader("Lista generada en Fase 1 (XLSX)", type=['xlsx'])
        f_keepa = st.file_uploader("Exportación Keepa (XLSX)", type=['xlsx'])
    with c2:
        f_img = st.file_uploader("Exportación Imágenes (CSV)", type=['csv'])
        f_cats = st.file_uploader("Mapeo Categorías (XLSX)", type=['xlsx'])

    if all([f_lista, f_keepa, f_img, f_cats]):
        if st.button("🪄 Generar CSV PrestaShop"):
            try:
                # 1. Carga y limpieza inicial
                df_l = pd.read_excel(f_lista, dtype=str)
                df_k = pd.read_excel(f_keepa, dtype=str)
                df_i = pd.read_csv(f_img, dtype=str)
                df_c = pd.read_excel(f_cats, dtype=str)

                for d in [df_l, df_k, df_i, df_c]:
                    d.columns = d.columns.str.lower().str.strip()

                # 2. Identificación robusta de columnas
                c_asin_k = buscar_columna(df_k, ['asin'])
                c_ean_k = buscar_columna(df_k, ['ean', 'código'])
                c_tit_k = buscar_columna(df_k, ['título', 'title', 'nombre'])
                c_cat_k = buscar_columna(df_k, ['categoría', 'category'])
                
                # Validación crítica: si c_asin_k es None, lanzamos error específico
                if not c_asin_k:
                    st.error("❌ No se encontró la columna 'ASIN' en el archivo de Keepa.")
                    st.stop()

                # 3. Cruce Lista + Keepa
                c_asin_l = 'asin1' if 'asin1' in df_l.columns else 'asin'
                df_m = pd.merge(df_l, df_k, left_on=c_asin_l, right_on=c_asin_k, how='inner')

                if df_m.empty:
                    st.warning("⚠️ No hay coincidencias entre la Lista y Keepa. Revisa los ASINs.")
                    st.stop()

                # 4. Construcción del resultado
                res = pd.DataFrame()
                res['Product ID'] = range(900001, 900001 + len(df_m))
                res['Active (0/1)'] = "1"
                res['Reference #'] = df_m['seller-sku']
                res['Name *'] = df_m[c_tit_k].str.slice(0, 128) if c_tit_k else "Producto sin nombre"
                res['EAN13'] = df_m[c_ean_k] if c_ean_k else ""
                res['Price tax included'] = "999"
                res['Supplier'] = 'Cecotec'
                res['Manufacturer'] = 'Cecotec'

                # Descripción dinámica basada en columnas que contengan 'característica'
                cols_car = [c for c in df_m.columns if 'característica' in str(c)]
                if cols_car:
                    res['Description'] = df_m[cols_car].fillna('').agg(' '.join, axis=1).str.slice(0, 2000)
                else:
                    res['Description'] = "Sin descripción disponible"

                # 5. Imágenes
                # Evitar error si no existe columna 'reference' en imágenes
                col_ref_img = buscar_columna(df_i, ['reference', 'sku', 'referencia'])
                if col_ref_img:
                    df_i['urls'] = df_i.drop(columns=[col_ref_img], errors='ignore').fillna('').apply(
                        lambda r: ','.join([str(v).strip() for v in r if str(v).strip() != '']), axis=1)
                    
                    df_i_clean = df_i[[col_ref_img, 'urls']].drop_duplicates(col_ref_img)
                    res = pd.merge(res, df_i_clean, left_on='Reference #', right_on=col_ref_img, how='left')
                    res.rename(columns={'urls': 'Image URLs (x,y,z...)'}, inplace=True)
                else:
                    res['Image URLs (x,y,z...)'] = ""

                # 6. Campos fijos y exportación
                res['Text when in stock'] = 'In Stock'
                res['Available for order (0 = No, 1 = Yes)'] = "1"
                res['Show price (0 = No, 1 = Yes)'] = "1"

                cols_f = ['Product ID', 'Active (0/1)', 'Name *', 'Price tax included', 
                          'Reference #', 'EAN13', 'Description', 'Image URLs (x,y,z...)']

                csv_res = io.StringIO()
                res[cols_f].to_csv(csv_res, index=False, sep=',', encoding='utf-8-sig')
                
                st.success(f"✅ Fichero generado con {len(res)} productos.")
                st.download_button("⬇️ Descargar CSV PrestaShop", csv_res.getvalue(), "subida_final.csv", "text/csv")
                st.dataframe(res.head())

            except Exception as e:
                st.error(f"❌ Error en Fase 2: {str(e)}")