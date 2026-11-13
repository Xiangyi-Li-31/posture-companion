"""Allow collection when the build interpreter cannot open a display/Tcl shell."""


def pre_find_module_path(hook_api):
    # Tcl/Tk data and binaries are added explicitly in PostureCompanion.spec.
    return None
