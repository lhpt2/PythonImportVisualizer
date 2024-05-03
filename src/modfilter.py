from typing import Callable, Dict
import sys

def eprint(content, end="\n"):
        print(content, file=sys.stderr, end=end)

# example filterfunction to filter modules that import other modules
def parent_mod_filter_func(mod_dict: Dict) -> Dict:
        temp = dict(mod_dict)
        for name, _ in mod_dict.items(): 
                if not parent_filter(name):
                        del temp[name]
        return temp 

def parent_filter(modname: str) -> bool:
        return not (is_test_module(modname) or is_logging_module(modname) or is_django_module(modname))

# example filterfunction for filtering specific module
# return false to exclude module 
def import_mod_filter_func(modname: str, parentname: str) -> bool:
        return not (is_test_module(parentname) or is_logging_module(parentname) or is_django_module(modname))


is_test_module: Callable[[str], bool] = lambda modname: '.tests' in modname

is_logging_module: Callable[[str], bool] = lambda modname: 'logging' in modname

is_django_module: Callable[[str], bool] = lambda modname: 'django' in modname