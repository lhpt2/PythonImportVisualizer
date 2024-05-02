from typing import Callable
import sys

# example filterfunction for filtering specific module
def modfilterfunc(modname: str, parentname: str) -> bool:
        return not is_test_module(parentname)

# filterfunction for filtering specific top module
#def pkgfilterfunc(topmodname: str) -> bool:
#        return True

is_test_module: Callable[[str], bool] = lambda modname: '.tests' in modname