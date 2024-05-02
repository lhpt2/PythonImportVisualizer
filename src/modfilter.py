from typing import Callable
import sys

# example filterfunction for filtering specific module
def modfilterfunc(modname: str, parentname: str) -> bool:
        if not is_test_module(parentname):
                return True
        else:
                print("MODNAME: ", parentname, file=sys.stderr) 
                return False

# filterfunction for filtering specific top module
#def pkgfilterfunc(topmodname: str) -> bool:
#        return True

is_test_module: Callable[[str], bool] = lambda modname: '.tests' in modname