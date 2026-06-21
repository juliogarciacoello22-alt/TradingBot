from core.checker_pro import CheckerPRO

checker = CheckerPRO()

for raw in datos_historicos:
    out = checker.process(raw)
    print(out)
