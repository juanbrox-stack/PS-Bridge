import pandas as pd
import os

def identificar_novedades():
    print("--- FASE 1: BUSCANDO PRODUCTOS PARA KEEPA ---")
    
    # Configuración de nombres de archivos
    f_plan = 'PlanLanzamiento.xlsx'
    f_amazon = 'listing_amazon.txt'
    f_ps_db = 'prestashop_db.xlsx'

    # Verificación de que los archivos están en la carpeta
    if not all(os.path.exists(f) for f in [f_plan, f_amazon, f_ps_db]):
        print("❌ ERROR: No se encuentran los archivos. Revisa que estén en /PS-Novedades")
        return

    try:
        print("Leyendo archivos...")
        # Carga de Excel
        df_plan = pd.read_excel(f_plan, dtype=str)
        df_ps_db = pd.read_excel(f_ps_db, dtype=str)
        
        # Carga de Amazon TXT (Probando codificaciones para Mac)
        try:
            df_amazon = pd.read_csv(f_amazon, sep='\t', encoding='utf-8', dtype=str)
        except:
            df_amazon = pd.read_csv(f_amazon, sep='\t', encoding='latin1', dtype=str)

        # Limpiar nombres de columnas (minúsculas y sin espacios)
        df_amazon.columns = df_amazon.columns.str.lower().str.strip()
        df_ps_db.columns = df_ps_db.columns.str.lower().str.strip()
        df_plan.columns = df_plan.columns.str.lower().str.strip()

        # --- DEFINICIÓN DE COLUMNAS SEGÚN TUS FICHEROS ---
        col_sku_amz = 'seller-sku'
        col_asin_amz = 'asin1'    # <--- Actualizado a tu nombre real
        col_ref_ps = 'reference'
        col_sku_plan = 'sku'
        col_est_plan = 'estado'

        # Validar que las columnas existen
        if col_sku_amz not in df_amazon.columns or col_asin_amz not in df_amazon.columns:
            print(f"❌ Error: Columnas no encontradas en Amazon. Detectadas: {list(df_amazon.columns)}")
            return

        # --- PROCESO DE CRUCE ---
        # Normalización (Quitar ceros a la izquierda y espacios)
        df_ps_db['ref_norm'] = df_ps_db[col_ref_ps].str.strip().str.lstrip('0')
        df_amazon['sku_norm'] = df_amazon[col_sku_amz].str.strip().str.lstrip('0')
        df_plan['sku_norm'] = df_plan[col_sku_plan].str.strip().str.lstrip('0')

        # Filtrar estados válidos del Plan
        estados_validos = [
            "Lanzamiento Completo", "Carrusel Enriquecidas", 
            "Completo con Texto", "Fotos Rodaje SIN texto"
        ]
        df_plan_filtrado = df_plan[df_plan[col_est_plan].isin(estados_validos)]
        
        # Identificar qué NO está en PrestaShop
        skus_en_ps = df_ps_db['ref_norm'].unique()
        df_nuevos = df_amazon[~df_amazon['sku_norm'].isin(skus_en_ps)].copy()
        
        # Cruce final con el Plan de Lanzamiento
        df_final = pd.merge(df_nuevos, df_plan_filtrado, on='sku_norm', how='inner')

        if df_final.empty:
            print("⚠️ No hay novedades con los estados seleccionados en el Plan.")
        else:
            # Exportación para Keepa
            columnas_salida = [col_sku_amz, col_asin_amz]
            df_final[columnas_salida].to_excel('lista_para_keepa.xlsx', index=False)
            
            print(f"✅ ¡ÉXITO! Se han detectado {len(df_final)} productos nuevos.")
            print(f"📁 Fichero generado: lista_para_keepa.xlsx")
            print("\nPróximo paso: Sube esta lista a Keepa y guarda el resultado como 'keepa.xlsx'.")

    except Exception as e:
        print(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    identificar_novedades()