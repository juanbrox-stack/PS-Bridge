import streamlit as st
import pandas as pd
import io

# Configuración de página
st.set_page_config(page_title="Generador PrestaShop", page_icon="🛍️")

def buscar_columna(df, palabras_clave):
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

st.title("🛠️ Generador de Carga PrestaShop")
st.write("Sube los archivos necesarios para generar el CSV de importación.")

# 1. Carga de archivos en la barra lateral
st.sidebar.header("📂 Archivos de Entrada")
file_lista = st.sidebar.file_uploader("1. Lista para Keepa (Excel)", type=['xlsx'])
file_keepa = st.sidebar.file_uploader("2. Exportación Keepa (Excel)", type=['xlsx'])
file_img = st.sidebar.file_uploader("3. Exportación Imágenes (CSV)", type=['csv'])
file_cats = st.sidebar.file_uploader("4. Mapeo Categorías (Excel)", type=['xlsx'])

if all([file_lista, file_keepa, file_img, file_cats]):
    if st.button("🚀 Procesar y Generar Fichero"):
        try:
            # Carga de datos
            df_lista = pd.read_excel(file_lista, dtype=str)
            df_keepa = pd.read_excel(file_keepa, dtype=str)
            df_imagenes = pd.read_csv(file_img, dtype=str)
            df_cats_map = pd.read_excel(file_cats, dtype=str)

            # Estandarización de columnas
            for df in [df_lista, df_keepa, df_imagenes, df_cats_map]:
                df.columns = df.columns.str.lower().str.strip()

            # Identificación de columnas clave
            col_asin_keepa = buscar_columna(df_keepa, ['asin'])
            col_ean_keepa = buscar_columna(df_keepa, ['códigos de producto: ean', 'ean'])
            col_titulo_keepa = buscar_columna(df_keepa, ['título', 'title'])
            col_cat_keepa = buscar_columna(df_keepa, ['categorías: subcategoría'])
            col_cat_amz_map = buscar_columna(df_cats_map, ['amazon', 'categoria_amazon', 'origen'])
            col_cat_ps_map = buscar_columna(df_cats_map, ['prestashop', 'nombre_ps', 'destino'])
            col_asin_lista = 'asin1' if 'asin1' in df_lista.columns else 'asin'

            # Cruce de datos
            df_merge = pd.merge(df_lista, df_keepa, left_on=col_asin_lista, right_on=col_asin_keepa, how='inner')

            if df_merge.empty:
                st.error("No se encontró correspondencia entre la lista y Keepa.")
            else:
                # Construcción del resultado
                resultado = pd.DataFrame()
                resultado['Product ID'] = range(900001, 900001 + len(df_merge))
                resultado['Active (0/1)'] = "1"
                resultado['Reference #'] = df_merge['seller-sku']
                resultado['Name *'] = df_merge[col_titulo_keepa].str.slice(0, 128)
                resultado['EAN13'] = df_merge[col_ean_keepa] if col_ean_keepa else ""
                resultado['Price tax included'] = "999"
                resultado['Supplier'] = 'Cecotec'
                resultado['Manufacturer'] = 'Cecotec'

                # Descripción (características)
                cols_caract = [c for c in df_merge.columns if 'característica' in str(c).lower()]
                resultado['Description'] = df_merge[cols_caract].fillna('').agg(' '.join, axis=1).str.slice(0, 2000)

                # Mapeo de categorías
                if all([col_cat_keepa, col_cat_amz_map, col_cat_ps_map]):
                    mapeo_dict = pd.Series(df_cats_map[col_cat_ps_map].values, 
                                           index=df_cats_map[col_cat_amz_map].str.lower().str.strip()).to_dict()
                    def traducir(cat):
                        cat_l = str(cat).lower().strip()
                        return mapeo_dict.get(cat_l, cat)
                    resultado['Categories (x,y,z...)'] = df_merge[col_cat_keepa].apply(traducir)
                else:
                    resultado['Categories (x,y,z...)'] = df_merge[col_cat_keepa] if col_cat_keepa else 'Inicio'

                # Imágenes
                df_imagenes['urls_unidas'] = df_imagenes.drop(columns=['reference'], errors='ignore').fillna('').apply(
                    lambda row: ','.join([str(val).strip() for val in row if str(val).strip() != '']), axis=1
                )
                df_img_clean = df_imagenes.drop_duplicates(subset=['reference'])
                resultado = pd.merge(resultado, df_img_clean[['reference', 'urls_unidas']], 
                                     left_on='Reference #', right_on='reference', how='left')

                # Preparación final
                resultado.rename(columns={'urls_unidas': 'Image URLs (x,y,z...)'}, inplace=True)
                resultado['Text when in stock'] = 'In Stock'
                resultado['Available for order (0 = No, 1 = Yes)'] = "1"
                resultado['Show price (0 = No, 1 = Yes)'] = "1"

                cols_final = ['Product ID', 'Active (0/1)', 'Name *', 'Categories (x,y,z...)', 
                              'Price tax included', 'Reference #', 'EAN13', 'Description', 
                              'Image URLs (x,y,z...)', 'Supplier', 'Manufacturer', 
                              'Text when in stock', 'Available for order (0 = No, 1 = Yes)', 'Show price (0 = No, 1 = Yes)']

                # Descarga del archivo
                csv_buffer = io.StringIO()
                resultado[cols_final].to_csv(csv_buffer, index=False, sep=',', encoding='utf-8-sig')
                
                st.success(f"✅ ¡Procesado con éxito! {len(resultado)} productos listos.")
                st.download_button(
                    label="⬇️ Descargar CSV para PrestaShop",
                    data=csv_buffer.getvalue(),
                    file_name="subida_prestashop_final.csv",
                    mime="text/csv"
                )

        except Exception as e:
            st.error(f"Error procesando los datos: {e}")
else:
    st.info("Por favor, sube los 4 archivos en la barra lateral para comenzar.")