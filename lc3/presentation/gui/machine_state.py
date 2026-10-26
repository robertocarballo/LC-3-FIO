"""Proyecta y edita registros y memoria para la raíz gráfica.

El panel posee sus widgets y diálogos; notifica cambios de memoria mediante
un callback concreto, sin conocer la aplicación ni otros paneles.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

from lc3.domain.isa import MASK_16, FL_NEG, FL_ZRO, FL_POS, to_int16, to_uint16
from lc3.domain.machine import LC3Simulator


class MachineStatePanel(ttk.Frame):
    """Posee vistas de CPU/memoria y modifica la máquina sólo al aceptar edición."""

    def __init__(
        self, parent, sim: LC3Simulator, on_memory_changed: Callable[[], None]
    ):
        """Compone tablas para la raíz y registra navegación y edición Double-1.

        Args:
            parent: División derecha de la composición.
            sim: Máquina cuyos valores se muestran y editan.
            on_memory_changed: Notificación tras refrescar una edición de memoria.
        """
        super().__init__(parent, padding=(4, 0))
        self.sim = sim
        self.on_memory_changed = on_memory_changed
        frame_reg = ttk.LabelFrame(self, text=" Registros de la CPU ", padding=6)
        frame_reg.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))

        # Tabla R0-R7
        columns = ("reg", "hex", "signed", "unsigned")
        self.tree_reg = ttk.Treeview(
            frame_reg, columns=columns, show="headings", height=8, selectmode="browse"
        )
        self.tree_reg.heading("reg", text="Reg")
        self.tree_reg.heading("hex", text="Hex")
        self.tree_reg.heading("signed", text="Dec (Signo)")
        self.tree_reg.heading("unsigned", text="Dec (Sin Signo)")

        self.tree_reg.column("reg", width=45, anchor=tk.CENTER)
        self.tree_reg.column("hex", width=75, anchor=tk.CENTER)
        self.tree_reg.column("signed", width=95, anchor=tk.E)
        self.tree_reg.column("unsigned", width=95, anchor=tk.E)

        for i in range(8):
            self.tree_reg.insert(
                "", tk.END, iid=f"r{i}", values=(f"R{i}", "x0000", "0", "0")
            )
        self.tree_reg.pack(fill=tk.X, pady=2)
        self.tree_reg.bind("<Double-1>", self.edit_register)

        # Frame de Estado (PC, CC, Instrucciones)
        frame_cc = ttk.Frame(frame_reg, padding=(2, 4))
        frame_cc.pack(fill=tk.X)

        self.lbl_pc_val = ttk.Label(
            frame_cc, text="PC: x3000", font=("Segoe UI", 10, "bold")
        )
        self.lbl_pc_val.pack(side=tk.LEFT, padx=6)

        ttk.Label(frame_cc, text="CC:").pack(side=tk.LEFT, padx=(10, 2))
        self.badge_n = tk.Label(
            frame_cc,
            text="N",
            font=("Segoe UI", 9, "bold"),
            bg="#E0E0E0",
            fg="#9E9E9E",
            width=2,
        )
        self.badge_n.pack(side=tk.LEFT, padx=1)
        self.badge_z = tk.Label(
            frame_cc,
            text="Z",
            font=("Segoe UI", 9, "bold"),
            bg="#4CAF50",
            fg="white",
            width=2,
        )
        self.badge_z.pack(side=tk.LEFT, padx=1)
        self.badge_p = tk.Label(
            frame_cc,
            text="P",
            font=("Segoe UI", 9, "bold"),
            bg="#E0E0E0",
            fg="#9E9E9E",
            width=2,
        )
        self.badge_p.pack(side=tk.LEFT, padx=1)

        self.lbl_cycles = ttk.Label(frame_cc, text="Ciclos: 0", font=("Segoe UI", 9))
        self.lbl_cycles.pack(side=tk.RIGHT, padx=6)

        # Frame de Memoria
        frame_mem = ttk.LabelFrame(self, text=" Explorador de Memoria ", padding=6)
        frame_mem.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        mem_nav = ttk.Frame(frame_mem)
        mem_nav.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
        ttk.Label(mem_nav, text="Dirección:").pack(side=tk.LEFT, padx=2)
        self.ent_mem_addr = ttk.Entry(mem_nav, width=8, font=("Consolas", 10))
        self.ent_mem_addr.pack(side=tk.LEFT, padx=2)
        self.ent_mem_addr.insert(0, "x3000")
        self.ent_mem_addr.bind("<Return>", lambda e: self.refresh_memory())
        ttk.Button(mem_nav, text="Ver", width=4, command=self.refresh_memory).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(
            mem_nav, text="◀ -16", width=5, command=lambda: self.shift_memory(-16)
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            mem_nav, text="+16 ▶", width=5, command=lambda: self.shift_memory(16)
        ).pack(side=tk.LEFT, padx=2)

        columns_mem = ("addr", "hex", "dec", "char", "label")
        self.tree_mem = ttk.Treeview(
            frame_mem,
            columns=columns_mem,
            show="headings",
            height=8,
            selectmode="browse",
        )
        self.tree_mem.heading("addr", text="Dirección")
        self.tree_mem.heading("hex", text="Hex")
        self.tree_mem.heading("dec", text="Decimal")
        self.tree_mem.heading("char", text="ASCII")
        self.tree_mem.heading("label", text="Símbolo")

        self.tree_mem.column("addr", width=75, anchor=tk.CENTER)
        self.tree_mem.column("hex", width=70, anchor=tk.CENTER)
        self.tree_mem.column("dec", width=80, anchor=tk.E)
        self.tree_mem.column("char", width=60, anchor=tk.CENTER)
        self.tree_mem.column("label", width=95, anchor=tk.W)

        scroll_mem_y = ttk.Scrollbar(
            frame_mem, orient=tk.VERTICAL, command=self.tree_mem.yview
        )
        self.tree_mem.configure(yscrollcommand=scroll_mem_y.set)

        self.tree_mem.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_mem_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_mem.bind("<Double-1>", self.edit_memory)

    def refresh_registers(self):
        """Proyecta registros, PC, contador y CC de la máquina en sus widgets."""
        # Actualizar R0 a R7
        for i in range(8):
            val = self.sim.reg[i]
            s_val = to_int16(val)
            self.tree_reg.item(
                f"r{i}", values=(f"R{i}", f"x{val:04X}", f"{s_val}", f"{val}")
            )

        # Actualizar PC y Ciclos
        self.lbl_pc_val.config(text=f"PC: x{self.sim.pc:04X}")
        self.lbl_cycles.config(text=f"Ciclos: {self.sim.instruction_count}")

        # Actualizar insignias de CC
        cc = self.sim.cond
        self.badge_n.config(
            bg="#F44336" if (cc & FL_NEG) else "#E0E0E0",
            fg="white" if (cc & FL_NEG) else "#9E9E9E",
        )
        self.badge_z.config(
            bg="#4CAF50" if (cc & FL_ZRO) else "#E0E0E0",
            fg="white" if (cc & FL_ZRO) else "#9E9E9E",
        )
        self.badge_p.config(
            bg="#2196F3" if (cc & FL_POS) else "#E0E0E0",
            fg="white" if (cc & FL_POS) else "#9E9E9E",
        )

    def refresh_memory(self, start_addr: Optional[int] = None):
        """Reconstruye 24 palabras con wraparound y lectura directa sin MMIO.

        Args:
            start_addr: Inicio explícito; si falta, lee hexadecimal de la
                entrada, retirando x/X/#, o usa x3000 ante ``ValueError``.
        """
        if start_addr is None:
            raw = (
                self.ent_mem_addr.get()
                .strip()
                .replace("x", "")
                .replace("X", "")
                .replace("#", "")
            )
            try:
                start_addr = int(raw, 16) & MASK_16
            except ValueError:
                start_addr = 0x3000

        self.tree_mem.delete(*self.tree_mem.get_children())
        for i in range(24):
            addr = (start_addr + i) & MASK_16
            val = self.sim.memory[addr]
            s_val = to_int16(val)
            byte_val = val & 0xFF
            char_repr = chr(byte_val) if 32 <= byte_val <= 126 else "."
            sym = self.sim.symbols.get(addr, "")

            self.tree_mem.insert(
                "",
                tk.END,
                iid=f"mem_{addr}",
                values=(
                    f"x{addr:04X}",
                    f"x{val:04X}",
                    f"{s_val}",
                    f"'{char_repr}'",
                    sym,
                ),
            )

    def shift_memory(self, delta: int):
        """Desplaza entrada y vista por botones ±16 del panel de memoria.

        Args:
            delta: Desplazamiento sumado módulo 65536 a la dirección visual.

        Ignora la entrada no hexadecimal sin modificarla.
        """
        raw = (
            self.ent_mem_addr.get()
            .strip()
            .replace("x", "")
            .replace("X", "")
            .replace("#", "")
        )
        try:
            curr = int(raw, 16) & MASK_16
            new_addr = (curr + delta) & MASK_16
            self.ent_mem_addr.delete(0, tk.END)
            self.ent_mem_addr.insert(0, f"x{new_addr:04X}")
            self.refresh_memory(new_addr)
        except ValueError:
            pass

    def edit_register(self, event):
        """Abre edición modal por Double-1 registrado en la tabla de registros.

        Captura registro y widgets en ``apply_val``; Tk llama esa función
        local mediante Aceptar o Return, no por invocación automática del
        contenedor. No pausa CPU; Cancelar sólo destruye el diálogo.
        """
        item = self.tree_reg.identify_row(event.y)
        if not item:
            return
        reg_num = int(item[1])  # 'r0' -> 0
        curr_val = self.sim.reg[reg_num]

        val_dialog = tk.Toplevel(self.winfo_toplevel())
        val_dialog.title(f"Modificar R{reg_num}")
        val_dialog.geometry("300x120")
        val_dialog.resizable(False, False)
        val_dialog.transient(self.winfo_toplevel())
        val_dialog.grab_set()

        ttk.Label(
            val_dialog,
            text=f"Nuevo valor para R{reg_num} (hex ej: x1234 o dec ej: #42):",
        ).pack(pady=8)
        ent = ttk.Entry(val_dialog, font=("Consolas", 10))
        ent.pack(pady=4)
        ent.insert(0, f"x{curr_val:04X}")
        ent.focus_set()

        def apply_val():
            """Aplica registro desde Aceptar/Return del diálogo contenedor.

            Convierte x/0x como hex, # como decimal y el resto como hex;
            enmascara a 16 bits, actualiza CC en la máquina, refresca sólo
            registros y cierra. ``ValueError`` muestra error sin cerrar;
            no captura otros fallos ni revierte mutaciones ya realizadas.
            """
            token = ent.get().strip()
            try:
                if token.upper().startswith("X") or token.upper().startswith("0X"):
                    val = int(token.upper().replace("0X", "").replace("X", ""), 16)
                elif token.startswith("#"):
                    val = int(token[1:], 10)
                else:
                    val = int(token, 16)
                self.sim.reg[reg_num] = to_uint16(val)
                self.sim.update_flags(reg_num)
                self.refresh_registers()
                val_dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Valor numérico no válido.")

        btn_box = ttk.Frame(val_dialog)
        btn_box.pack(pady=6)
        ttk.Button(btn_box, text="Aceptar", command=apply_val).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(btn_box, text="Cancelar", command=val_dialog.destroy).pack(
            side=tk.LEFT, padx=4
        )
        ent.bind("<Return>", lambda e: apply_val())

    def edit_memory(self, event):
        """Abre edición modal por Double-1 registrado en la tabla de memoria.

        Captura dirección y widgets para ``apply_mem``, invocado después
        por Aceptar/Return. No pausa CPU; Cancelar destruye el diálogo.
        """
        item = self.tree_mem.identify_row(event.y)
        if not item:
            return
        addr_str = self.tree_mem.item(item, "values")[0].replace("x", "")
        addr = int(addr_str, 16)
        curr_val = self.sim.memory[addr]

        val_dialog = tk.Toplevel(self.winfo_toplevel())
        val_dialog.title(f"Modificar Memoria x{addr:04X}")
        val_dialog.geometry("320x120")
        val_dialog.resizable(False, False)
        val_dialog.transient(self.winfo_toplevel())
        val_dialog.grab_set()

        ttk.Label(
            val_dialog, text=f"Nuevo valor para mem[x{addr:04X}] (hex ej: x002A o #42):"
        ).pack(pady=8)
        ent = ttk.Entry(val_dialog, font=("Consolas", 10))
        ent.pack(pady=4)
        ent.insert(0, f"x{curr_val:04X}")
        ent.focus_set()

        def apply_mem():
            """Escribe memoria desde Aceptar/Return del diálogo contenedor.

            Convierte x/0x y texto desnudo como hex y # como decimal.
            Delega a ``sim.mem_write`` con sus efectos MMIO y callbacks;
            después refresca memoria, invoca ``on_memory_changed`` y cierra,
            en ese orden.
            Captura ``ValueError`` con aviso sin cerrar ni revertir efectos;
            las demás excepciones se propagan al callback Tk.
            """
            token = ent.get().strip()
            try:
                if token.upper().startswith("X") or token.upper().startswith("0X"):
                    val = int(token.upper().replace("0X", "").replace("X", ""), 16)
                elif token.startswith("#"):
                    val = int(token[1:], 10)
                else:
                    val = int(token, 16)
                self.sim.mem_write(addr, val)
                self.refresh_memory()
                self.on_memory_changed()
                val_dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Valor numérico no válido.")

        btn_box = ttk.Frame(val_dialog)
        btn_box.pack(pady=6)
        ttk.Button(btn_box, text="Aceptar", command=apply_mem).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(btn_box, text="Cancelar", command=val_dialog.destroy).pack(
            side=tk.LEFT, padx=4
        )
        ent.bind("<Return>", lambda e: apply_mem())
