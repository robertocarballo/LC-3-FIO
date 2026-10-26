"""Encapsula terminal, entrada y foco sin coordinar ejecución ni FIFO."""

import tkinter as tk
from tkinter import ttk, scrolledtext


class ConsolePanel(ttk.Frame):
    """Posee widgets de E/S y entrega eventos directamente a la raíz."""

    def __init__(self, parent, on_keypress, on_entry_keypress, on_send):
        """Construye terminal para la raíz y registra teclas y envío.

        KeyPress conserva el retorno del callback, incluido ``"break"``.
        Return y Enviar llaman ``on_send`` sin argumentos.

        Args:
            parent: Marco inferior de la composición.
            on_keypress: Handler de teclas de terminal.
            on_entry_keypress: Handler de teclas de la entrada.
            on_send: Acción de consumo del texto por la raíz.
        """
        super().__init__(parent)
        self.txt_console = scrolledtext.ScrolledText(
            self,
            wrap=tk.CHAR,
            font=("Consolas", 10),
            bg="#1E1E1E",
            fg="#E0E0E0",
            insertbackground="#FFFFFF",
            height=6,
        )
        self.txt_console.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 4))
        self.txt_console.bind("<KeyPress>", on_keypress)

        input_frame = ttk.Frame(self)
        input_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(input_frame, text="Entrada de teclado:").pack(side=tk.LEFT, padx=2)
        self.ent_console_in = ttk.Entry(input_frame, font=("Consolas", 10))
        self.ent_console_in.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.ent_console_in.bind("<Return>", lambda e: on_send())
        self.ent_console_in.bind("<KeyPress>", on_entry_keypress)

        ttk.Button(input_frame, text="Enviar", command=on_send).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(input_frame, text="Limpiar Consola", command=self.clear_output).pack(
            side=tk.RIGHT, padx=2
        )

    def write_output(self, text: str):
        """Añade salida y desplaza la terminal desde ``sim.output_fn``.

        Registrado por la raíz tras componer los paneles, lo invoca la máquina para salida nativa
        o DDR; no transforma el texto ni captura errores de widgets.
        """
        self.txt_console.insert(tk.END, text)
        self.txt_console.see(tk.END)

    def clear_output(self):
        """Borra sólo salida por el botón Limpiar registrado en la consola."""
        self.txt_console.delete("1.0", tk.END)

    def take_input_text(self) -> str:
        """Entrega a la raíz el texto pendiente y borra la entrada, sin añadir LF."""
        text = self.ent_console_in.get()
        self.ent_console_in.delete(0, tk.END)
        return text

    def clear_input(self) -> None:
        """Borra la entrada cuando la raíz consume una tecla durante espera."""
        self.ent_console_in.delete(0, tk.END)

    def set_input_highlight(self, waiting: bool) -> None:
        """Resalta o restaura entrada; conserva la captura de fallos de estilo Tk."""
        try:
            self.ent_console_in.config(background="#FFF9C4" if waiting else "#FFFFFF")
        except Exception:
            pass

    def focus_input(self) -> None:
        """Enfoca entrada a petición de la raíz, sin cambiar resaltado ni espera."""
        self.ent_console_in.focus_set()
