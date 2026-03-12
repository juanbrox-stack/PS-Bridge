import streamlit as st
import pandas as pd
import io

def normalizar(serie):
    """Limpia espacios, convierte a mayúsculas y quita ceros a la izquierda para comparar SKUs."""
    return serie.astype(str).str.strip().str.upper().str.lstrip('0')

st.title("🔍 Paso 1: Identificador de Novedades")
st.write("Compara Amazon vs PrestaShop y filtra por el Plan de Lanzamiento.")

# Carga de archivos
col1, col2, col3 = st.columns(3)
with col1:
    file_ps = st.file_uploader("1. BBDD PrestaShop (CSV/XLSX)", type=['csv', 'xlsx'])
with col2:
    file_amz = st.file_uploader("2. Listing Amazon (TXT/XLSX)", type=['txt', 'xlsx'])
with col3:
    file_plan = st.file_uploader("3. Plan Lanzamiento (XLSX)", type=['xlsx'])

if all([file_ps, file_amz, file_plan]):
    if st.button("🔎 Buscar Novedades"):
        try:
            # Lectura de BBDD PrestaShop (Manejo de separador ';' según tu captura)
            if file_ps.name.endswith('.csv'):
                df_ps = pd.read_csv(file_ps, sep=None, engine='python', dtype=str)
            else:
                df_ps = pd.read_excel(file_ps, dtype=str)
            
            # Lectura de Amazon
            if file_amz.name.endswith('.txt'):
                df_amz = pd.read_csv(file_amz, sep='\t', encoding='latin1', dtype=str)
            else:
                df_amz = pd.read_excel(file_amz, dtype=str)
                
            df_plan = pd.read_excel(file_plan, dtype=str)

            # Limpiar columnas
            df_ps.columns = df_ps.columns.str.lower().str.strip()
            df_amz.columns = df_amz.columns.str.lower().str.strip()
            df_plan.columns = df_plan.columns.str.lower().str.strip()

            # Normalización de SKUs para cruce infalible
            df_ps['sku_norm'] = normalizar(df_ps['reference'])
            df_amz['sku_norm'] = normalizar(df_amz['seller-sku'])
            df_plan['sku_norm'] = normalizar(df_plan['sku'])

            # 1. Filtrar estados del Plan de Lanzamiento
            estados_ok = ["Lanzamiento Completo", "Carrusel Enriquecidas", "Completo con Texto", "Fotos Rodaje SIN texto"]
            df_plan_filtrado = df_plan[df_plan['estado'].isin(estados_ok)]

            # 2. Identificar qué NO está en PrestaShop
            skus_en_ps = df_ps['sku_norm'].unique()
            df_novedades = df_amz[~df_amz['sku_norm'].isin(skus_en_ps)]

            # 3. Cruce final: Novedades que están aprobadas en el Plan
            df_final = pd.merge(df_novedades, df_plan_filtrado[['sku_norm']], on='sku_norm', how='inner')

            if df_final.empty:
                st.warning("⚠️ No se han encontrado novedades que coincidan con los estados del Plan.")
            else:
                st.success(f"✅ ¡Éxito! Se han detectado {len(df_final)} productos nuevos listos para Keepa.")
                
                # Preparar descarga
                output = df_final[['seller-sku', 'asin1']] # Ajustado a tus nombres de columna
                buffer = io.BytesIO()
                output.to_excel(buffer, index=False)
                
                st.download_button(
                    label="⬇️ Descargar lista para Keepa",
                    data=buffer.getvalue(),
                    file_name="lista_para_keepa.xlsx",
                    mime="application/vnd.ms-excel"
                )
                st.dataframe(output) # Vista previa

        except Exception as e:
            st.error(f"Error en el proceso: {e}")