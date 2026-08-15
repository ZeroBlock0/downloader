from .modules import GalleryModule, NetworkModule, RandomImageApiModule


def build_registry():
    return {module.name: module for module in (GalleryModule(), NetworkModule(), RandomImageApiModule())}
