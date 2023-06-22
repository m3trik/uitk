# !/usr/bin/python
# coding=utf-8
import importlib
import pkgutil
import inspect


__package__ = "uitk.widgets.mixins"


# Define a dictionary to map class names to their respective modules
CLASS_TO_MODULE = {}

# Build the CLASS_TO_MODULE dictionary by iterating over all submodules of the package
for importer, modname, ispkg in pkgutil.walk_packages(__path__, __name__ + "."):
    module = importlib.import_module(modname)
    for name, obj in module.__dict__.items():
        if inspect.isclass(obj):
            CLASS_TO_MODULE[obj.__name__] = modname

# Define a dictionary to store imported module objects
IMPORTED_MODULES = {}


def __getattr__(name):
    # Check if the requested attribute is a class we need to import
    if name in CLASS_TO_MODULE:
        module_name = CLASS_TO_MODULE[name]
        if module_name not in IMPORTED_MODULES:
            # If the module hasn't been imported yet, import it and add it to the dictionary
            module = importlib.import_module(module_name)
            IMPORTED_MODULES[module_name] = module
        else:
            module = IMPORTED_MODULES[module_name]
        # Return the requested class object from the module
        return getattr(module, name)

    # If the requested attribute is not a class we handle, raise an AttributeError
    raise AttributeError(f"module {__package__} has no attribute '{name}'")


# --------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------

"""
EXAMPLE USE CASE:
import uitk.widgets as wgts

wgts.PushButton #get a specific widget.
"""

# --------------------------------------------------------------------------------------------
# deprecated:
# --------------------------------------------------------------------------------------------


# def __getattr__(attr_name):
# 	"""This function dynamically imports a module and returns an attribute from the module.

# 	Parameters:
# 		attr_name (str): The name of the attribute to be imported. The name should be in the format
# 					'module_name.attribute_name' or just 'attribute_name'.
# 	Returns:
# 		(obj) The attribute specified by the `attr_name` argument.

# 	:Raises:
# 		AttributeError: If the specified attribute is not found in the original module.

# 	Example:
# 		<package>.__getattr__('module1.attribute1') #returns: <attribute1 value>
# 		<package>.__getattr__('attribute1') #returns: <attribute1 value>
# 	"""
# 	try:
# 		module = __import__(f"{__package__}.{attr_name}", fromlist=[f"{attr_name}"])
# 		setattr(sys.modules[__name__], attr_name, getattr(module, attr_name))
# 		return getattr(module, attr_name)

# 	except ModuleNotFoundError as error:
# 		raise AttributeError(f"Module '{__package__}' has no attribute '{attr_name}'") from error
