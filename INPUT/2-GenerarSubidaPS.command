#!/bin/bash
cd "$(dirname "$0")"
python3 generador_ps.py
echo "Proceso terminado. El fichero 'subida_prestashop_final.csv' está listo."
read -n 1