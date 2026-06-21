import os
import ast
import importlib
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(ROOT, "core")

print("\n====================================")
print("        AUDITORÍA DEL PROYECTO")
print("====================================\n")

errors = []
unused_files = []
imports_map = {}
used_modules = set()

# -----------------------------------------
# 1. LISTAR TODOS LOS ARCHIVOS .py
# -----------------------------------------
print("📌 Escaneando archivos...\n")

py_files = []
for root, dirs, files in os.walk(ROOT):
    for f in files:
        if f.endswith(".py"):
            py_files.append(os.path.join(root, f))

for f in py_files:
    print("✔ Encontrado:", os.path.relpath(f, ROOT))

print("\n------------------------------------")
print("2. ANALIZANDO IMPORTS")
print("------------------------------------\n")

# -----------------------------------------
# 2. ANALIZAR IMPORTS DE CADA ARCHIVO
# -----------------------------------------
for file in py_files:
    rel = os.path.relpath(file, ROOT)
    imports_map[rel] = []

    try:
        with open(file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports_map[rel].append(n.name)

            elif isinstance(node, ast.ImportFrom):
                module = node.module if node.module else ""
                imports_map[rel].append(module)

    except Exception as e:
        errors.append((rel, str(e)))

# Mostrar imports
for file, imps in imports_map.items():
    print(f"📄 {file}")
    for imp in imps:
        print("   →", imp)
    print()

print("\n------------------------------------")
print("3. PROBANDO CARGA DE MÓDULOS")
print("------------------------------------\n")

# -----------------------------------------
# 3. PROBAR IMPORTAR CADA ARCHIVO
# -----------------------------------------
for file in py_files:
    module_name = os.path.splitext(os.path.relpath(file, ROOT))[0].replace("\\", ".")
    if module_name.endswith("__init__"):
        continue

    print("🔍 Probando módulo:", module_name)

    try:
        importlib.import_module(module_name)
        print("   ✔ OK")
        used_modules.add(module_name)

    except Exception as e:
        print("   ❌ ERROR:", e)
        errors.append((module_name, traceback.format_exc()))

print("\n------------------------------------")
print("4. DETECTANDO ARCHIVOS MUERTOS")
print("------------------------------------\n")

# -----------------------------------------
# 4. ARCHIVOS QUE NADIE IMPORTA
# -----------------------------------------
all_modules = set(
    os.path.splitext(os.path.relpath(f, ROOT))[0].replace("\\", ".")
    for f in py_files
)

dead_modules = all_modules - used_modules

for m in dead_modules:
    print("⚠️ Módulo no usado:", m)
    unused_files.append(m)

print("\n------------------------------------")
print("5. REPORTE FINAL")
print("------------------------------------\n")

print("📌 ERRORES ENCONTRADOS:")
if not errors:
    print("   ✔ Sin errores")
else:
    for e in errors:
        print("\n❌", e[0])
        print(e[1])

print("\n📌 ARCHIVOS NO USADOS:")
if not unused_files:
    print("   ✔ Todos los módulos están en uso")
else:
    for m in unused_files:
        print("   →", m)

print("\n====================================")
print("     AUDITORÍA COMPLETADA")
print("====================================\n")
