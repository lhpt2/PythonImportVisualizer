#!/usr/bin/env python3
""" Visualize the import relationships of a python project. """


import argparse
import dis
import graphviz
import importlib.util
import matplotlib.colors as mc
import networkx as nx
import os
import platform
import sys
from collections import defaultdict
from libinfo import is_std_lib_module
from modulefinder import ModuleFinder, Module as MFModule
from matplotlib.colors import hsv_to_rgb
from networkx.drawing.nx_pydot import write_dot
from pyvis.network import Network
from typing import Callable


if importlib.util.find_spec('modfilter', __package__) is not None:
    import modfilter
else:
    modfilter = None

# actual opcodes
LOAD_CONST = dis.opmap["LOAD_CONST"]
IMPORT_NAME = dis.opmap["IMPORT_NAME"]
STORE_NAME = dis.opmap["STORE_NAME"]
STORE_GLOBAL = dis.opmap["STORE_GLOBAL"]
POP_TOP = dis.opmap["POP_TOP"]
POP_BLOCK = dis.opmap["POP_BLOCK"]
STORE_OPS = STORE_NAME, STORE_GLOBAL
EXTENDED_ARG = dis.EXTENDED_ARG
HAVE_ARGUMENT = dis.HAVE_ARGUMENT

# enum identifiers for scan_opcodes()
STORE = "store"
ABS_IMPORT = "absolute_import"
REL_IMPORT = "relative_import"

# Python 2 or 3 (int)
PY_VERSION = sys.version_info[0]

# Output file for dag visualization
DAG_OUT = "dag.dot"

# System Names
LINUX_SYSTEM_NAME   = "Linux"
DARWIN_SYSTEM_NAME  = "Darwin"
JAVA_SYSTEM_NAME    = "Java"
WINDOWS_SYSTEM_NAME = "Windows"

# function for logging (to stderr)
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def abs_mod_name(module, root_dir):
    """ From a Module's absolute path, and the root directory, return a
    string with how that module would be imported from a script in the root
    directory.

    Example: abs_mod_name(Module('/path/to/mod.py'), '/path') -> 'to.mod'
    NOTE: no trailing '/' in root_dir
    """

    abs_path = os.path.abspath(module.__file__)
    rel_path = abs_path[len(root_dir) :]

    current_system = platform.system()
    if current_system is WINDOWS_SYSTEM_NAME:
        path_parts = rel_path.split("\\")[1:]
    else:
        path_parts = rel_path.split("/")[1:]

    path_parts[-1] = path_parts[-1][:-3]
    if path_parts[-1] == "__init__":
        del path_parts[-1]
    mod_name = ".".join(path_parts)
    return mod_name

def get_modules_from_file(script, root_dir=None, use_sys_path=False):
    """ Use ModuleFinder.load_file() to get module imports for the given
    script.

    :param script: the script we're getting modules from
    :param root_dir: the project's root dir, if different from script's dir
    :param use_sys_path: use the system PATH when looking for module defs, this
    may be useful if you want to add stdlib modules
    :rtype: {str(module name): Module}
    """
    # script = os.path.abspath(script)
    if not root_dir:
        root_dir = os.path.dirname(script)
    path = [root_dir]
    if use_sys_path:
        path.append(sys.path[:])

    finder = ModuleFinder(path)
    finder.load_file(script)
    modules = finder.modules

    if not use_sys_path:
        # Filter out standard library imports
        modules = {
            name: mod
            for name, mod in modules.items()
            if not is_std_lib_module(name, PY_VERSION)
        }

    # All the module names have to be as references from the root directory
    # modules = {abs_mod_name(mod, root_dir): mod for mod in modules.values()}

    return modules

def get_modules_in_dir(root_dir, ignore_venv=True):
    """ Walk a directory recursively and get the module imports for all .py
    files in the directory.
    """
    root_dir = os.path.abspath(root_dir)
    mods = {}

    for top, dir, files in os.walk(root_dir):
        if ignore_venv and ("venv" in top or "virt" in top):
            continue
        for nm in files:
            if nm[-3:] == ".py":
                mod_file = os.path.abspath(os.path.join(top, nm))
                mod_path = os.path.dirname(mod_file)
                mod_name = mod_file[len(root_dir) + 1 :].replace("/", ".")[:-3]
                # if "__init__" in mod_name:
                #     mod_name = mod_name.replace(".__init__", "")
                if "__init__" not in mod_name and mod_name not in mods:
                    mod = Module(mod_name, file=mod_file, path=mod_path)
                    mods[mod_name] = mod
    return mods

class Module(MFModule, object):
    """ Extension of modulefinder.ModuleFinder to add custom attrs. """

    def __init__(self, *args, **kwargs):
        super(Module, self).__init__(*args, **kwargs)

        # keys = the fully qualified names of this module's direct imports
        # value = list of names imported from that module
        self.direct_imports = {}

def _unpack_opargs(code):
    """ Step through the python bytecode and generate a tuple (int, int, int):
    (operation_index, operation_byte, argument_byte) for each operation.
    """
    extended_arg = 0
    if PY_VERSION == 3:
        for i in range(0, len(code), 2):
            op = code[i]
            if op >= HAVE_ARGUMENT:
                next_code = code[i + 1]
                arg = next_code | extended_arg
                extended_arg = (arg << 8) if op == EXTENDED_ARG else 0
            else:
                arg = None
            yield (i, op, arg)
    elif PY_VERSION == 2:
        i = 0
        while i < len(code):
            op = ord(code[i])
            if op >= HAVE_ARGUMENT:
                arg = ord(code[i + 1])
                i += 3
            else:
                arg = None
                i += 1
            yield (i, op, arg)
    # Python 1?

def scan_opcodes(compiled):
    """
    This function is stolen w/ slight modifications from the standard library
    modulefinder.

    From a compiled code object, generate reports of relevant operations:
    storing variables, absolute imports, and relative imports.

    Return types are a bit tricky, type = (str, tuple):
        (STORE, (<name:str>,))
            - ex: (STORE, "x")
            - source that generated this: `x = 1`
        (ABS_IMPORT, (<names:tuple(str)>, <namespace:str>))
            - ex: (ABS_IMPORT, ("foo","bar"), "path.to.module")
            - `from path.to.module import foo, bar`
        (REL_IMPORT, (<level:int>, <names:tuple(str)>,
        <namespace:str>))
            - ex: (REL_IMPORT, (2, ("up",), "")
            - `from .. import up`
            - (an import of "up" from the immediate parent directory, level=2)
            - (level=1 means the module's own directory)
    """
    code = compiled.co_code
    names = compiled.co_names
    consts = compiled.co_consts
    opargs = [(op, arg) for _, op, arg in _unpack_opargs(code) if op != EXTENDED_ARG]
    for i, (op, oparg) in enumerate(opargs):
        if op in STORE_OPS:
            yield STORE, (names[oparg],)
            continue
        if (
            op == IMPORT_NAME
            and i >= 2
            and opargs[i - 1][0] == opargs[i - 2][0] == LOAD_CONST
        ):
            level = consts[opargs[i - 2][1]]
            fromlist = consts[opargs[i - 1][1]] or []
            if level == 0 or level == -1:
                yield ABS_IMPORT, (fromlist, names[oparg])
            else:
                yield REL_IMPORT, (level, fromlist, names[oparg])
            continue

def get_fq_immediate_deps(all_mods, module, modfilterfunc: Callable[[str, str], bool]=lambda name, parentname: True):
    """
    From a Module, using the module's absolute path, compile the code and then
    search through it for the imports and get a list of the immediately
    imported (do not recurse to find those module's imports as well) modules'
    fully qualified names. Returns the specific names imported (the y, z in
    `from x import y,z`) as a list for the key's value.

    Returns:
        {<module name:str>: <list of names imported from the module:list(str)>}
    """
    fq_deps = defaultdict(list)

    with open(module.__file__, "r") as fp:
        path = os.path.dirname(module.__file__)
        compiled = compile(fp.read() + "\n", path, "exec")
        for op, args in scan_opcodes(compiled):

            if op == STORE:
                # TODO
                pass

            if op == ABS_IMPORT:
                names, top = args
                if (
                    (not is_std_lib_module(top.split(".")[0], PY_VERSION)
                    or top in all_mods)
                    and modfilterfunc("", top)
                ):
                    if not names:
                        fq_deps[top].append([])
                    for name in names:
                        fq_name = top + "." + name
                        if not modfilterfunc(name, top):
                            eprint("EXCLUDE: ", top, "->", name)
                            continue

                        if fq_name in all_mods:
                            # just to make sure it's in the dict
                            fq_deps[fq_name].append([])
                        else:
                            fq_deps[top].append(name)

            if op == REL_IMPORT:
                # TODO
                pass

    return fq_deps

def add_immediate_deps_to_modules(mod_dict, modfilterfunc: Callable[[str, str], bool]=lambda name, parentname: True):
    """ Take a module dictionary, and add the names of the modules directly
    imported by each module in the dictionary, and add them to the module's
    direct_imports.
    """
    for name, module in sorted(mod_dict.items()):
        fq_deps = get_fq_immediate_deps(mod_dict, module, modfilterfunc=modfilterfunc)
        module.direct_imports = fq_deps

def mod_dict_to_dag(mod_dict, graph_name):
    """ Take a module dictionary, and return a graphviz.Digraph object
    representing the module import relationships. """
    dag = graphviz.Digraph(graph_name, format="pdf")
    # Vendor modules, AKA third-party modules
    vendor_mods = set()
    for name, module in mod_dict.items():
        for di in module.direct_imports:
            # Vendor modules and edges get a different color
            attrs = {}
            if di not in mod_dict:
                attrs["color"] = "blue"
                if di not in vendor_mods:
                    dag.node(di, **attrs)
                    vendor_mods.add(di)
            dag.edge(name, di, **attrs)
    return dag

def get_args():
    """ Parse and return command line args. """
    parser = argparse.ArgumentParser(
        description="Visualize imports of a given" " python script."
    )
    parser.add_argument(
        "path",
        type=str,
        help="main python script/entry point for project, or"
        " the root directory of the project",
    )
    parser.add_argument(
        "-r",
        "--root",
        dest="alt_root",
        type=str,
        help="alternate root, if the project root differs from"
        " the directory that the main script is in",
    )
    parser.add_argument(
        "-d",
        "--dot",
        dest="dotfile",
        type=str,
        help="generate dotfile of graph",
    )
    # TODO implement ability to ignore certain modules
    # parser.add_argument('-i', '--ignore', dest='ignorefile', type=str,
    # help='file that contains names of modules to ignore')
    return parser.parse_args()

def generate_pyvis_visualization(mod_dict, dotfile=''):
    def get_hex_color_of_shade(value):
        if value < 0 or value > 1:
            raise ValueError("Input value must be between 0 and 1")
        
        scaled_val = value * 100

        if scaled_val <= 50:
            r = 255
            g = int(255*scaled_val/50)
            b = 0
        else:
            r = int(255*(100-scaled_val)/50)
            g = 255
            b = 0

        return "#%s%s%s" % tuple([hex(c)[2:].rjust(2, "0") for c in (r, g, b)])

    def normaliz_between_n1_1(min, max, val):
        if min == max:
            return 0
        else:
            zero_min = val - min
            scaled_val = zero_min / (max-min)
            return scaled_val

    # Networkx graph for editing graph
    nx_graph = nx.Graph()

    modules_in_graph = set()
    for name, module in mod_dict.items():
        # Check if module not already in graph from di
        if name not in modules_in_graph:
            nx_graph.add_node(name)
            modules_in_graph.add(name)
        else:
            nx_graph.nodes[name]['color'] = 'red'

        for di in module.direct_imports:
            # Check if di not already in graph
            if di not in modules_in_graph:
                nx_graph.add_node(di)
                modules_in_graph.add(di)

            # Add edge from name to di
            nx_graph.add_edge(name, di)

    # Get max/min degree to normaliz between -1 and 1
    max_degree = -1
    min_degree = 10000
    first = True
    for node in nx_graph.nodes:
        if first:
            max_degree = nx_graph.degree(node)
            min_degree = nx_graph.degree(node)
            first = False
        else:
            max_degree = max(max_degree, nx_graph.degree(node))
            min_degree = min(min_degree, nx_graph.degree(node))

    # Check number of edges in a node
    for node in nx_graph.nodes:
        norm_val = normaliz_between_n1_1(min_degree, max_degree, nx_graph.degree(node))
        size = 20 + 35 * norm_val 
        nx_graph.nodes[node]['size'] = size
        nx_graph.nodes[node]['color'] = get_hex_color_of_shade(norm_val)

    if dotfile:
        nx.draw(nx_graph)
        write_dot(nx_graph, dotfile)

    net = Network(directed=True)
    net.from_nx(nx_graph)
    net.show_buttons()
    net.toggle_physics(True)
    net.show('mygraph.html', notebook=False)

def main():

    endnotice = False

    args = get_args()
    if args.path[-3:] == ".py":
        script = args.path
        root_dir = os.path.dirname(args.path)
        if args.alt_root:
            root_dir = args.alt_root
        mod_dict = get_modules_from_file(script, root_dir=root_dir)
    else:
        root_dir = args.path
        mod_dict = get_modules_in_dir(root_dir)

    # check for filterfunction callback to be present, else use stub lambda
    if modfilter is None:
        add_immediate_deps_to_modules(mod_dict)
    else:
        match hasattr(modfilter, "parent_mod_filter_func"):
            case True:
                mod_dict = modfilter.parent_mod_filter_func(mod_dict)
        match hasattr(modfilter, "import_mod_filter_func"):
            case False:
                add_immediate_deps_to_modules(mod_dict)
            case True:
                add_immediate_deps_to_modules(mod_dict, modfilterfunc=modfilter.import_mod_filter_func)

        # print notice to either implement one of the callbacks or consider removing modfilter module
        if not hasattr(modfilter, "parent_mod_filter_func") and hasattr(modfilter, "import_mod_filter_func"):
            endnotice = True

    print("Module dependencies:")
    for name, module in sorted(mod_dict.items()):
        print("\n" + name)
        for dep in module.direct_imports:
            print("    " + dep)

    project_name = os.path.basename(os.path.abspath(root_dir))

    # Creates the Graphvis visualization
    # dag = mod_dict_to_dag(mod_dict, project_name)
    # dag.view()

    # Creates the pyvis visualization
    if args.dotfile is not None:
        generate_pyvis_visualization(mod_dict, dotfile=args.dotfile)
    else:
        generate_pyvis_visualization(mod_dict)

    if endnotice:
        eprint("Notice: consider adding one of the filter functions (parent_mod_filter_func or import_mod_filter_func) to modfilter module or removing modfilter module completely.")

if __name__ == "__main__":
    main()