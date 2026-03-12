import pandas as pd
import os

def normalizar_texto(serie):
    """Limpia espacios y asegura formato texto."""
    return serie.astype(str).str.strip()

def buscar_columna(df, palabras_clave):
    """Busca una columna de forma flexible por palabras clave."""
    for col in df.columns:
        if any(palabra in str(col).lower() for palabra in palabras_clave):
            return col
    return None

def generar_fichero_prestashop():
    print("--- FASE 2: GENERANDO FICHERO FINAL PRESTASHOP ---")

    ficheros = {
        'lista': 'lista_para_keepa.xlsx',
        'keepa': 'keepa.xlsx',
        'imagenes': 'plytix_exportImagenes.csv',
        'categorias': 'ps_categories.xlsx'
    }

    if not all(os.path.exists(f) for f in ficheros.values()):
        print("❌ ERROR: Faltan archivos en la carpeta.")
        return

    try:
        print("Cargando archivos...")
        df_lista = pd.read_excel(ficheros['lista'], dtype=str)
        df_keepa = pd.read_excel(ficheros['keepa'], dtype=str)
        df_imagenes = pd.read_csv(ficheros['imagenes'], dtype=str)
        df_cats_map = pd.read_excel(ficheros['categorias'], dtype=str)

        # Limpieza de nombres de columnas
        df_lista.columns = df_lista.columns.str.lower().str.strip()
        df_keepa.columns = df_keepa.columns.str.lower().str.strip()
        df_imagenes.columns = df_imagenes.columns.str.lower().str.strip()
        df_cats_map.columns = df_cats_map.columns.str.lower().str.strip()

        # 1. IDENTIFICAR COLUMNAS EN KEEPA Y MAPEO
        col_asin_keepa = buscar_columna(df_keepa, ['asin'])
        col_ean_keepa = buscar_columna(df_keepa, ['códigos de producto: ean', 'ean'])
        col_titulo_keepa = buscar_columna(df_keepa, ['título', 'title'])
        col_cat_keepa = buscar_columna(df_keepa, ['categorías: subcategoría'])
        
        # Columnas en ps_categories.xlsx (Detección flexible)
        col_cat_amz_map = buscar_columna(df_cats_map, ['amazon', 'categoria_amazon', 'origen'])
        col_cat_ps_map = buscar_columna(df_cats_map, ['prestashop', 'nombre_ps', 'destino'])

        # 2. CRUCE: Lista + Keepa
        col_asin_lista = 'asin1' if 'asin1' in df_lista.columns else 'asin'
        df_merge = pd.merge(df_lista, df_keepa, left_on=col_asin_lista, right_on=col_asin_keepa, how='inner')

        if df_merge.empty:
            print("⚠️ No se encontró correspondencia entre tu lista y Keepa.")
            return

        # 3. CONSTRUCCIÓN DEL DATASET
        resultado = pd.DataFrame()
        resultado['Product ID'] = range(900001, 900001 + len(df_merge))
        resultado['Active (0/1)'] = "1"
        resultado['Reference #'] = df_merge['seller-sku']
        resultado['Name *'] = df_merge[col_titulo_keepa].str.slice(0, 128)
        resultado['EAN13'] = df_merge[col_ean_keepa] if col_ean_keepa else ""
        resultado['Price tax included'] = "999"
        resultado['Supplier'] = 'Cecotec'
        resultado['Manufacturer'] = 'Cecotec'

        # Descripción
        cols_caract = [c for c in df_merge.columns if 'característica' in str(c).lower()]
        cols_caract.sort(reverse=True)
        resultado['Description'] = df_merge[cols_caract].fillna('').agg(' '.join, axis=1).str.slice(0, 2000)

        # 4. LÓGICA DE CATEGORÍAS (Categoría Keepa -> Mapeo -> Fallback)
        print("Asignando categorías...")
        if col_cat_keepa and col_cat_amz_map and col_cat_ps_map:
            # Tomamos la categoría original de Keepa
            resultado['Categories (x,y,z...)'] = df_merge[col_cat_keepa].fillna('Inicio')
            
            # Intentamos mapear cada categoría
            # Creamos un diccionario de mapeo para búsqueda rápida
            mapeo_dict = pd.Series(df_cats_map[col_cat_ps_map].values, 
                                   index=df_cats_map[col_cat_amz_map].str.lower().str.strip()).to_dict()
            
            def traducir_categoria(cat_original):
                cat_limpia = str(cat_original).lower().strip()
                # Si el texto es similar o está en nuestro diccionario, lo cambiamos
                if cat_limpia in mapeo_dict:
                    return mapeo_dict[cat_limpia]
                return cat_original # Si no hay coincidencia, dejamos la de Keepa

            resultado['Categories (x,y,z...)'] = resultado['Categories (x,y,z...)'].apply(traducir_categoria)
        else:
            resultado['Categories (x,y,z...)'] = df_merge[col_cat_keepa] if col_cat_keepa else 'Inicio'

        # 5. IMÁGENES
        df_imagenes['ref_norm'] = df_merge['seller-sku'].astype(str).str.strip().str.lstrip('0') # Normalización coherente
        cols_url = [c for c in df_imagenes.columns if c not in ['reference', 'ref_norm']]
        df_imagenes['urls_unidas'] = df_imagenes[cols_url].fillna('').apply(
            lambda row: ','.join([str(val).strip() for val in row if str(val).strip() != '']), axis=1
        )
        
        # Unión de imágenes por SKU
        df_imagenes_clean = df_imagenes.drop_duplicates(subset=['reference'])
        resultado = pd.merge(resultado, df_imagenes_clean[['reference', 'urls_unidas']], 
                             left_on='Reference #', right_on='reference', how='left')
        
        resultado.rename(columns={'urls_unidas': 'Image URLs (x,y,z...)'}, inplace=True)

        # 6. CAMPOS FIJOS
        resultado['Text when in stock'] = 'In Stock'
        resultado['Available for order (0 = No, 1 = Yes)'] = "1"
        resultado['Show price (0 = No, 1 = Yes)'] = "1"

        columnas_finales = [
            'Product ID', 'Active (0/1)', 'Name *', 'Categories (x,y,z...)', 
            'Price tax included', 'Reference #', 'EAN13', 'Description', 
            'Image URLs (x,y,z...)', 'Supplier', 'Manufacturer', 
            'Text when in stock', 'Available for order (0 = No, 1 = Yes)', 'Show price (0 = No, 1 = Yes)'
        ]
        
        resultado[columnas_finales].to_csv('subida_prestashop_final.csv', index=False, sep=',', encoding='utf-8-sig')
        print(f"✅ ¡ÉXITO! Fichero generado con {len(resultado)} productos.")

    except Exception as e:
        print(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    generar_fichero_prestashop()