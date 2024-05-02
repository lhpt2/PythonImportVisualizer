from typing import Callable, Dict
import sys

# example filterfunction to filter modules that import other modules
def parent_mod_filter_func(mod_dict: Dict) -> Dict:
        temp = dict(mod_dict)
        for name, _ in mod_dict.items(): 
                if not parent_filter(name):
                        del temp[name]
        return temp 


        return mod_dict

def parent_filter(modname: str) -> bool:
        return not (is_test_module(modname) or is_logging_module(modname))

# example filterfunction for filtering specific module
# return false to exclude module 
def import_mod_filter_func(modname: str, parentname: str) -> bool:
        return not (is_test_module(parentname) or is_logging_module(parentname))


is_test_module: Callable[[str], bool] = lambda modname: '.tests' in modname

is_logging_module: Callable[[str], bool] = lambda modname: 'logging' in modname