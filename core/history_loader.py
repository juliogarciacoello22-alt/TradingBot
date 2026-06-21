import json
import os

class HistoryLoader:
    def __init__(self, api):
        self.api = api

    def load_from_file(self, filename):
        """
        Loader institucional v4.
        Mantiene compatibilidad pero NO carga historial.
        Devuelve:
        - False si no existe
        - False si hay error
        - data si el archivo es válido (solo lectura)
        """

        # Archivo no existe → retorno explícito
        if not os.path.exists(filename):
            return False

        # Protección contra archivos gigantes (>10MB)
        if os.path.getsize(filename) > 10_000_000:
            print("⚠️ Archivo de historial demasiado grande — ignorado")
            return False

        try:
            with open(filename, "r") as f:
                data = json.load(f)

            # Validación mínima
            if not isinstance(data, list):
                return False

            # No cargamos nada al bot (compatibilidad)
            return data

        except Exception:
            # Silencioso pero seguro
            return False
