# example filterfunction for filtering specific module
def modfilterfunc(modname: str, parentname: str) -> bool:
        return True

# filterfunction for filtering specific top module
def pkgfilterfunc(topmodname: str) -> bool:
        return True