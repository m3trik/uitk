# !/usr/bin/python
# coding=utf-8
# import os
# import importlib
# import pkgutil
# import inspect


# --------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# deprecated:
# --------------------------------------------------------------------------------------------

# __package__ = "uitk.widgets"
# __path__ = [os.path.abspath(os.path.dirname(__file__))]

# # Define a dictionary to map class names to their respective modules
# CLASS_TO_MODULE = {}

# # Build the CLASS_TO_MODULE dictionary by iterating over all submodules of the package
# for importer, modname, ispkg in pkgutil.walk_packages(__path__, __name__ + "."):
#     module = importlib.import_module(modname)
#     for name, obj in module.__dict__.items():
#         if inspect.isclass(obj):
#             CLASS_TO_MODULE[obj.__name__] = modname

# # Define a dictionary to store imported module objects
# IMPORTED_MODULES = {}


# def __getattr__(name):
#     # Check if the requested attribute is a class we need to import
#     if name in CLASS_TO_MODULE:
#         module_name = CLASS_TO_MODULE[name]
#         if module_name not in IMPORTED_MODULES:
#             # If the module hasn't been imported yet, import it and add it to the dictionary
#             module = importlib.import_module(module_name)
#             IMPORTED_MODULES[module_name] = module
#         else:
#             module = IMPORTED_MODULES[module_name]
#         # Return the requested class object from the module
#         return getattr(module, name)

#     # If the requested attribute is not a class we handle, raise an AttributeError
#     raise AttributeError(f"module {__package__} has no attribute '{name}'")
