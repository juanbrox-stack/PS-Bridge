import os
import glob

def limpiar_carpeta():
    print("--- LIMPIEZA DE ARCHIVOS TEMPORALES ---")
    
    # Archivos que queremos BORRAR para dejar la carpeta limpia
    archivos_a_borrar = [
        'lista_para_keepa.xlsx',
        'keepa.xlsx',
        'plytix_exportImagenes.csv',
        'subida_prestashop_final.csv',
        'listing_amazon.txt',
        'prestashop_db.xlsx'
    ]
    
    confirmacion = input("¿Estás seguro de que quieres borrar los archivos de datos actuales? (s/n): ")
    
    if confirmacion.lower() == 's':
        count = 0
        for f in archivos_a_borrar:
            if os.path.exists(f):
                os.remove(f)
                print(f"Eliminado: {f}")
                count += 1
        
        print(f"\n✅ Carpeta lista. Se han eliminado {count} archivos.")
        print("Los scripts y 'ps_categories.xlsx' se han mantenido a salvo.")
    else:
        print("Operación cancelada.")

if __name__ == "__main__":
    limpiar_carpeta()