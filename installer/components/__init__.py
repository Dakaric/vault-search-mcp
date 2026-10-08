from types import ModuleType

from installer.components import index, model, ollama, register, vault

COMPONENTS: tuple[ModuleType, ...] = (ollama, model, vault, index, register)
