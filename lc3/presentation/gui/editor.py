"""Encapsula texto Assembly y acciones de editor sin poseer rutas ni máquina."""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Callable


class EditorPanel(ttk.Frame):
    """Posee el texto y delega ensamblado y guardado a callbacks de la raíz."""

    def __init__(
        self, parent, on_assemble: Callable[[], None], on_save: Callable[[], None]
    ):
        """Construye el editor y registra botones con callbacks sin argumentos.

        Args:
            parent: Notebook que contiene la pestaña.
            on_assemble: Acción de ensamblado del contenido actual.
            on_save: Acción de Guardar Como gestionada por la raíz.
        """
        super().__init__(parent)
        bar = ttk.Frame(self, padding=(4, 4))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(
            bar,
            text="⚡ Ensamblar y Cargar al Simulador",
            style="Accent.TButton",
            command=on_assemble,
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="💾 Guardar Como...", command=on_save).pack(
            side=tk.LEFT, padx=2
        )

        self.txt_editor = scrolledtext.ScrolledText(
            self,
            wrap=tk.NONE,
            font=("Consolas", 11),
            bg="#FFFFFF",
            fg="#1E1E1E",
            insertbackground="#000000",
            undo=True,
        )
        self.txt_editor.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    def get_source(self) -> str:
        """Devuelve a la raíz todo el texto, incluido el salto implícito de Tk END."""
        return self.txt_editor.get("1.0", tk.END)

    def set_source(self, source: str) -> None:
        """Reemplaza el texto a petición de la raíz al cargar un archivo."""
        self.txt_editor.delete("1.0", tk.END)
        self.txt_editor.insert("1.0", source)
