"""Presenta instrucciones y breakpoints para la composición de ``LC3GUI``.

Lee la máquina sin MMIO; no controla ejecución ni importa otros paneles.
"""

import tkinter as tk
from tkinter import ttk
from typing import Set

from lc3.domain.isa import MASK_16, MEMORY_SIZE, disassemble_instruction
from lc3.domain.machine import LC3Simulator


class DisassemblyPanel(ttk.Frame):
    """Posee árbol, búsqueda y base visual; toma prestados máquina y breakpoints."""

    def __init__(self, parent, sim: LC3Simulator, breakpoints: Set[int]):
        """Construye la vista para la raíz y registra navegación y Double-1.

        Args:
            parent: Contenedor Tk de la pestaña.
            sim: Máquina consultada sin modificar sus registros ni memoria.
            breakpoints: Conjunto de la raíz que Double-1 modifica in situ.
        """
        super().__init__(parent)
        self.sim = sim
        self.breakpoints = breakpoints
        self.base_addr = 0x3000
        bar = ttk.Frame(self, padding=(4, 4))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="🎯 Ir a PC Actual", command=self.scroll_to_pc).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Label(bar, text="Ir a Dirección:").pack(side=tk.LEFT, padx=(10, 2))
        self.ent_jump_addr = ttk.Entry(bar, width=8, font=("Consolas", 10))
        self.ent_jump_addr.pack(side=tk.LEFT, padx=2)
        self.ent_jump_addr.insert(0, "x3000")
        self.ent_jump_addr.bind("<Return>", lambda e: self.jump_to_address())
        ttk.Button(bar, text="Ir", command=self.jump_to_address).pack(
            side=tk.LEFT, padx=2
        )

        ttk.Label(
            bar,
            text="(Doble clic en fila o columna BP para alternar breakpoint)",
            font=("Segoe UI", 8, "italic"),
            foreground="#666",
        ).pack(side=tk.RIGHT, padx=5)

        # Treeview de instrucciones
        columns = ("bp", "addr", "code", "instr", "label")
        self.tree_disasm = ttk.Treeview(
            self, columns=columns, show="headings", selectmode="browse"
        )
        self.tree_disasm.heading("bp", text="BP")
        self.tree_disasm.heading("addr", text="Dirección")
        self.tree_disasm.heading("code", text="Hex")
        self.tree_disasm.heading("instr", text="Instrucción")
        self.tree_disasm.heading("label", text="Etiqueta")

        self.tree_disasm.column("bp", width=36, anchor=tk.CENTER)
        self.tree_disasm.column("addr", width=80, anchor=tk.CENTER)
        self.tree_disasm.column("code", width=75, anchor=tk.CENTER)
        self.tree_disasm.column("instr", width=220, anchor=tk.W)
        self.tree_disasm.column("label", width=140, anchor=tk.W)

        scroll_y = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self.tree_disasm.yview
        )
        self.tree_disasm.configure(yscrollcommand=scroll_y.set)

        self.tree_disasm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Configurar colores para PC activo y Breakpoints
        self.tree_disasm.tag_configure(
            "pc_active",
            background="#C8E6C9",
            foreground="#000000",
            font=("Consolas", 10, "bold"),
        )
        self.tree_disasm.tag_configure("bp_set", foreground="#D32F2F")

        # Evento para alternar breakpoint
        self.tree_disasm.bind("<Double-1>", self.toggle_breakpoint)

    def refresh(self):
        """Reconstruye hasta 140 filas leyendo memoria directa, sin efectos MMIO.

        Ajusta la base visual si el PC queda fuera del intervalo cercano;
        delega decodificación al núcleo y marca símbolos, PC y breakpoints.
        """
        # Desensamblar un rango relevante alrededor del PC o desde la dirección base
        self.tree_disasm.delete(*self.tree_disasm.get_children())

        # Si el PC está fuera del bloque actual, mover la base de visualización
        cur_base = self.base_addr
        if not (cur_base - 2 <= self.sim.pc < cur_base + 120):
            cur_base = max(0, self.sim.pc - 2)
            self.base_addr = cur_base

        start_addr = max(0, cur_base - 2)
        end_addr = min(MEMORY_SIZE, start_addr + 140)

        for addr in range(start_addr, end_addr):
            instr = self.sim.memory[addr]
            dis = disassemble_instruction(instr, addr, self.sim.symbols)
            label = f"{self.sim.symbols[addr]}:" if addr in self.sim.symbols else ""
            has_bp = "●" if addr in self.breakpoints else ""

            tags = []
            if addr == self.sim.pc:
                tags.append("pc_active")
            if addr in self.breakpoints:
                tags.append("bp_set")

            item_id = f"addr_{addr}"
            self.tree_disasm.insert(
                "",
                tk.END,
                iid=item_id,
                values=(has_bp, f"x{addr:04X}", f"x{instr:04X}", dis, label),
                tags=tags,
            )

    def scroll_to_pc(self):
        """Selecciona y muestra PC desde botón de desensamblado o controladores.

        Reconstruye antes el árbol si no contiene la fila; no cambia el PC.
        """
        item_id = f"addr_{self.sim.pc}"
        if not self.tree_disasm.exists(item_id):
            self.refresh()
        if self.tree_disasm.exists(item_id):
            self.tree_disasm.see(item_id)
            self.tree_disasm.selection_set(item_id)

    def jump_to_address(self):
        """Busca dirección por botón Ir o Return de ``__init__``.

        Interpreta hexadecimal, incluso tras retirar #, y enmascara a 16 bits.
        Cambia base y selección, no CPU; ignora ``ValueError``. El refresco
        puede volver a acercar la base al PC si éste queda fuera de rango.
        """
        raw = (
            self.ent_jump_addr.get()
            .strip()
            .replace("x", "")
            .replace("X", "")
            .replace("#", "")
        )
        try:
            addr = int(raw, 16) & MASK_16
            self.base_addr = addr
            self.refresh()
            item_id = f"addr_{addr}"
            if self.tree_disasm.exists(item_id):
                self.tree_disasm.see(item_id)
                self.tree_disasm.selection_set(item_id)
        except ValueError:
            pass

    def toggle_breakpoint(self, event):
        """Alterna BP por Double-1 registrado en ``__init__``.

        Usa la fila bajo ``event.y``, modifica el conjunto de la raíz y
        refresca/desplaza; fila ausente o dirección inválida no hace cambios.
        """
        item = self.tree_disasm.identify_row(event.y)
        if not item:
            return
        addr_str = self.tree_disasm.item(item, "values")[1].replace("x", "")
        try:
            addr = int(addr_str, 16)
            if addr in self.breakpoints:
                self.breakpoints.remove(addr)
            else:
                self.breakpoints.add(addr)
            self.refresh()
            self.scroll_to_pc()
        except ValueError:
            pass
