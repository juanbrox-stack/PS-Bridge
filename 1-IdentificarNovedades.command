#!/bin/bash
cd "$(dirname "$0")"
python3 paso1_identificar.py
echo "Proceso terminado. Pulsa cualquier tecla para cerrar."
read -n 1