from typing import Callable, Dict
import sys

def eprint(*args, **kwargs):
        print(*args, file=sys.stderr, **kwargs)

# function to edit mod_dict and filter out modules from project tree (will be parsed for imports)
def parent_mod_filter_func(mod_dict: Dict) -> Dict:
        temp = dict(mod_dict)
        for name, _ in mod_dict.items(): 
                if not parent_filter(name):
                        del temp[name]
        return temp 

# example filter function for listed modules in project tree
# return false to exclude module
def parent_filter(modname: str) -> bool:
        # example filter logic
        #return not (is_test_module(modname) or is_logging_module(modname) or is_django_module(modname))
        return True

# example filterfunction for filtering specific module
# return false to exclude module 
def import_mod_filter_func(modname: str, parentname: str) -> bool:
        # Example filter logic
        #return not (is_test_module(parentname) or is_logging_module(parentname) or is_django_module(parentname))
        return True


is_test_module: Callable[[str], bool] = lambda modname: '.tests' in modname

is_logging_module: Callable[[str], bool] = lambda modname: 'logging' in modname

is_django_module: Callable[[str], bool] = lambda modname: 'django' in modname