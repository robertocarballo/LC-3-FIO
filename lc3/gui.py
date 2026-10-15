"""
lc3_gui.py - Interfaz Gráfica de Usuario (GUI) para el simulador y ensamblador LC-3.
Desarrollada en Tkinter puro, con visualización de registros, flags CC, memoria,
desensamblado con breakpoints interactivos, consola de E/S y editor integrado.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional, Dict, Set

from .core import (
    MASK_16, MEMORY_SIZE,
    FL_POS, FL_ZRO, FL_NEG,
    to_uint16, to_int16, get_cc_name, disassemble_instruction,
    OP_JSR, OP_TRAP, TRAP_HALT, TRAP_GETC, TRAP_IN
)
from .assembler import LC3Assembler, AssemblyError, assemble_file
from .sim import LC3Simulator


class LC3GUI(tk.Tk):
    def __init__(self, initial_file: Optional[str] = None):
        super().__init__()
        self.title("Simulador y Ensamblador LC-3 (Little Computer 3)")
        self.geometry("1180x820")
        self.minsize(980, 680)

        # Configurar icono y estilo
        self._configure_styles()

        # Instancia del simulador
        self.sim = LC3Simulator()
        self.orig_pc = 0x3000
        self.disasm_base_addr = 0x3000
        self.current_file: Optional[str] = None
        self.breakpoints: Set[int] = set()

        # Variables de control de ejecución
        self.is_running = False
        self.sim_speed_ms = tk.IntVar(value=50)  # Intervalo de actualización en ms
        self.waiting_for_input = False
        self.input_buffer = []
        self.input_var = tk.StringVar(self, value="")
        self._step_over_target: Optional[int] = None

        # Redirigir E/S del simulador
        self.sim.output_fn = self._handle_sim_output
        self.sim.input_fn = self._handle_sim_input
        self.sim.has_input_fn = lambda: len(self.input_buffer) > 0
        self.sim.kbsr_poll_fn = self._on_kbsr_poll

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Construir Interfaz
        self._create_menu()
        self._create_toolbar()
        self._create_main_panels()
        self._create_status_bar()

        # Cargar archivo inicial o ejemplo si se especifica
        if initial_file and os.path.isfile(initial_file):
            self.load_file(initial_file)
        else:
            # Intentar cargar hello.asm por defecto si existe
            default_ex = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "hello.asm")
            if os.path.isfile(default_ex):
                self.load_file(default_ex)
            else:
                self._update_all_views()

    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Estilo para botones de la barra de herramientas
        style.configure("Tool.TButton", font=("Segoe UI", 9, "bold"), padding=4)
        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"), padding=4, foreground="#005A9E")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure("Treeview", font=("Consolas", 10), rowheight=22)

    # =========================================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # =========================================================================

    def _create_menu(self):
        menubar = tk.Menu(self)

        # Menú Archivo
        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(label="Abrir archivo (.asm / .obj)...", command=self._on_open_file, accelerator="Ctrl+O")
        menu_file.add_command(label="Ensamblar y Cargar archivo actual", command=self._on_assemble_and_load, accelerator="F5")
        menu_file.add_separator()
        menu_file.add_command(label="Cargar Ejemplo: Hello World", command=lambda: self._load_example("hello.asm"))
        menu_file.add_command(label="Cargar Ejemplo: Multiplicación", command=lambda: self._load_example("mult.asm"))
        menu_file.add_command(label="Cargar Ejemplo: Contador Regresivo", command=lambda: self._load_example("count.asm"))
        menu_file.add_command(label="Cargar Ejemplo: Eco Interactivo", command=lambda: self._load_example("echo.asm"))
        menu_file.add_separator()
        menu_file.add_command(label="Salir", command=self.quit, accelerator="Alt+F4")
        menubar.add_cascade(label="Archivo", menu=menu_file)

        # Menú Simulación
        menu_sim = tk.Menu(menubar, tearoff=0)
        menu_sim.add_command(label="Ejecutar (Run)", command=self._on_run, accelerator="F9")
        menu_sim.add_command(label="Pausar (Pause)", command=self._on_pause, accelerator="F10")
        menu_sim.add_command(label="Paso a Paso (Step)", command=self._on_step, accelerator="F11")
        menu_sim.add_command(label="Paso Sobre Subrutina (Step Over)", command=self._on_step_over, accelerator="F12")
        menu_sim.add_separator()
        menu_sim.add_command(label="Reiniciar (Reset)", command=self._on_reset, accelerator="Ctrl+R")
        menu_sim.add_command(label="Limpiar Breakpoints", command=self._on_clear_breakpoints)
        menubar.add_cascade(label="Simulación", menu=menu_sim)

        # Menú Ayuda
        menu_help = tk.Menu(menubar, tearoff=0)
        menu_help.add_command(label="Instrucciones de la ISA LC-3", command=self._show_isa_help)
        menu_help.add_command(label="Acerca de", command=self._show_about)
        menubar.add_cascade(label="Ayuda", menu=menu_help)

        self.config(menu=menubar)

        # Atajos de teclado
        self.bind("<Control-o>", lambda e: self._on_open_file())
        self.bind("<F5>", lambda e: self._on_assemble_and_load())
        self.bind("<F9>", lambda e: self._on_run())
        self.bind("<F10>", lambda e: self._on_pause())
        self.bind("<F11>", lambda e: self._on_step())
        self.bind("<F12>", lambda e: self._on_step_over())
        self.bind("<Control-r>", lambda e: self._on_reset())

    def _create_toolbar(self):
        toolbar = ttk.Frame(self, padding=(8, 6), relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        # Botones de archivo
        ttk.Button(toolbar, text="📂 Abrir", style="Tool.TButton", command=self._on_open_file).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="⚙️ Ensamblar y Cargar", style="Tool.TButton", command=self._on_assemble_and_load).pack(side=tk.LEFT, padx=3)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # Botones de simulación
        self.btn_run = ttk.Button(toolbar, text="▶️ Ejecutar", style="Accent.TButton", command=self._on_run)
        self.btn_run.pack(side=tk.LEFT, padx=3)

        self.btn_pause = ttk.Button(toolbar, text="⏸️ Pausar", style="Tool.TButton", command=self._on_pause, state=tk.DISABLED)
        self.btn_pause.pack(side=tk.LEFT, padx=3)

        self.btn_step = ttk.Button(toolbar, text="⏭️ Paso (Step)", style="Tool.TButton", command=self._on_step)
        self.btn_step.pack(side=tk.LEFT, padx=3)

        self.btn_step_over = ttk.Button(toolbar, text="⏩ Paso Sobre (Next)", style="Tool.TButton", command=self._on_step_over)
        self.btn_step_over.pack(side=tk.LEFT, padx=3)

        self.btn_reset = ttk.Button(toolbar, text="🔄 Reiniciar", style="Tool.TButton", command=self._on_reset)
        self.btn_reset.pack(side=tk.LEFT, padx=3)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # Control de velocidad
        ttk.Label(toolbar, text="Velocidad:").pack(side=tk.LEFT, padx=(2, 4))
        self.speed_scale = ttk.Scale(
            toolbar, from_=1, to=200, orient=tk.HORIZONTAL,
            variable=self.sim_speed_ms, length=120
        )
        self.speed_scale.pack(side=tk.LEFT, padx=3)
        self.lbl_speed_text = ttk.Label(toolbar, text="50 ms")
        self.lbl_speed_text.pack(side=tk.LEFT, padx=(2, 8))
        self.sim_speed_ms.trace_add("write", lambda *a: self._update_speed_label())

        # Estado del procesador
        self.lbl_cpu_state = tk.Label(
            toolbar, text="LISTO", font=("Segoe UI", 9, "bold"),
            bg="#2E7D32", fg="white", padx=10, pady=2
        )
        self.lbl_cpu_state.pack(side=tk.RIGHT, padx=5)

    def _update_speed_label(self):
        val = self.sim_speed_ms.get()
        if val <= 5:
            self.lbl_speed_text.config(text="Máx")
        else:
            self.lbl_speed_text.config(text=f"{val} ms")

    def _create_main_panels(self):
        main_paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main_paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=4)

        # Parte superior dividida horizontalmente (Izquierda: Código/Editor, Derecha: Registros/Memoria)
        top_paned = ttk.PanedWindow(main_paned, orient=tk.HORIZONTAL)
        main_paned.add(top_paned, weight=3)

        # Panel Izquierdo: Notebook con "Desensamblado" y "Editor Assembly"
        left_notebook = ttk.Notebook(top_paned)
        top_paned.add(left_notebook, weight=3)

        self.tab_disasm = ttk.Frame(left_notebook)
        self.tab_editor = ttk.Frame(left_notebook)
        left_notebook.add(self.tab_disasm, text=" Desensamblado / Ejecución ")
        left_notebook.add(self.tab_editor, text=" Editor de Código Assembly ")

        self._build_disasm_tab()
        self._build_editor_tab()

        # Panel Derecho: Registros y Memoria
        right_frame = ttk.Frame(top_paned, padding=(4, 0))
        top_paned.add(right_frame, weight=2)
        self._build_registers_and_memory(right_frame)

        # Panel Inferior: Consola de Entrada/Salida
        bottom_frame = ttk.LabelFrame(main_paned, text=" Consola de E/S (Terminal LC-3) ", padding=4)
        main_paned.add(bottom_frame, weight=1)
        self._build_console(bottom_frame)

    def _build_disasm_tab(self):
        # Barra superior del desensamblado: búsqueda y salto a PC
        bar = ttk.Frame(self.tab_disasm, padding=(4, 4))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="🎯 Ir a PC Actual", command=self._scroll_to_pc).pack(side=tk.LEFT, padx=2)
        ttk.Label(bar, text="Ir a Dirección:").pack(side=tk.LEFT, padx=(10, 2))
        self.ent_jump_addr = ttk.Entry(bar, width=8, font=("Consolas", 10))
        self.ent_jump_addr.pack(side=tk.LEFT, padx=2)
        self.ent_jump_addr.insert(0, "x3000")
        self.ent_jump_addr.bind("<Return>", lambda e: self._jump_to_address())
        ttk.Button(bar, text="Ir", command=self._jump_to_address).pack(side=tk.LEFT, padx=2)

        ttk.Label(bar, text="(Doble clic en fila o columna BP para alternar breakpoint)", font=("Segoe UI", 8, "italic"), foreground="#666").pack(side=tk.RIGHT, padx=5)

        # Treeview de instrucciones
        columns = ("bp", "addr", "code", "instr", "label")
        self.tree_disasm = ttk.Treeview(self.tab_disasm, columns=columns, show="headings", selectmode="browse")
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

        scroll_y = ttk.Scrollbar(self.tab_disasm, orient=tk.VERTICAL, command=self.tree_disasm.yview)
        self.tree_disasm.configure(yscrollcommand=scroll_y.set)

        self.tree_disasm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Configurar colores para PC activo y Breakpoints
        self.tree_disasm.tag_configure("pc_active", background="#C8E6C9", foreground="#000000", font=("Consolas", 10, "bold"))
        self.tree_disasm.tag_configure("bp_set", foreground="#D32F2F")

        # Evento para alternar breakpoint
        self.tree_disasm.bind("<Double-1>", self._on_disasm_double_click)

    def _build_editor_tab(self):
        bar = ttk.Frame(self.tab_editor, padding=(4, 4))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="⚡ Ensamblar y Cargar al Simulador", style="Accent.TButton", command=self._on_assemble_editor_code).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="💾 Guardar Como...", command=self._on_save_editor_code).pack(side=tk.LEFT, padx=2)

        self.txt_editor = scrolledtext.ScrolledText(
            self.tab_editor, wrap=tk.NONE, font=("Consolas", 11),
            bg="#FFFFFF", fg="#1E1E1E", insertbackground="#000000", undo=True
        )
        self.txt_editor.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    def _build_registers_and_memory(self, parent):
        # Frame de Registros
        frame_reg = ttk.LabelFrame(parent, text=" Registros de la CPU ", padding=6)
        frame_reg.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))

        # Tabla R0-R7
        columns = ("reg", "hex", "signed", "unsigned")
        self.tree_reg = ttk.Treeview(frame_reg, columns=columns, show="headings", height=8, selectmode="browse")
        self.tree_reg.heading("reg", text="Reg")
        self.tree_reg.heading("hex", text="Hex")
        self.tree_reg.heading("signed", text="Dec (Signo)")
        self.tree_reg.heading("unsigned", text="Dec (Sin Signo)")

        self.tree_reg.column("reg", width=45, anchor=tk.CENTER)
        self.tree_reg.column("hex", width=75, anchor=tk.CENTER)
        self.tree_reg.column("signed", width=95, anchor=tk.E)
        self.tree_reg.column("unsigned", width=95, anchor=tk.E)

        for i in range(8):
            self.tree_reg.insert("", tk.END, iid=f"r{i}", values=(f"R{i}", "x0000", "0", "0"))
        self.tree_reg.pack(fill=tk.X, pady=2)
        self.tree_reg.bind("<Double-1>", self._on_edit_register)

        # Frame de Estado (PC, CC, Instrucciones)
        frame_cc = ttk.Frame(frame_reg, padding=(2, 4))
        frame_cc.pack(fill=tk.X)

        self.lbl_pc_val = ttk.Label(frame_cc, text="PC: x3000", font=("Segoe UI", 10, "bold"))
        self.lbl_pc_val.pack(side=tk.LEFT, padx=6)

        ttk.Label(frame_cc, text="CC:").pack(side=tk.LEFT, padx=(10, 2))
        self.badge_n = tk.Label(frame_cc, text="N", font=("Segoe UI", 9, "bold"), bg="#E0E0E0", fg="#9E9E9E", width=2)
        self.badge_n.pack(side=tk.LEFT, padx=1)
        self.badge_z = tk.Label(frame_cc, text="Z", font=("Segoe UI", 9, "bold"), bg="#4CAF50", fg="white", width=2)
        self.badge_z.pack(side=tk.LEFT, padx=1)
        self.badge_p = tk.Label(frame_cc, text="P", font=("Segoe UI", 9, "bold"), bg="#E0E0E0", fg="#9E9E9E", width=2)
        self.badge_p.pack(side=tk.LEFT, padx=1)

        self.lbl_cycles = ttk.Label(frame_cc, text="Ciclos: 0", font=("Segoe UI", 9))
        self.lbl_cycles.pack(side=tk.RIGHT, padx=6)

        # Frame de Memoria
        frame_mem = ttk.LabelFrame(parent, text=" Explorador de Memoria ", padding=6)
        frame_mem.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        mem_nav = ttk.Frame(frame_mem)
        mem_nav.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
        ttk.Label(mem_nav, text="Dirección:").pack(side=tk.LEFT, padx=2)
        self.ent_mem_addr = ttk.Entry(mem_nav, width=8, font=("Consolas", 10))
        self.ent_mem_addr.pack(side=tk.LEFT, padx=2)
        self.ent_mem_addr.insert(0, "x3000")
        self.ent_mem_addr.bind("<Return>", lambda e: self._on_navigate_mem())
        ttk.Button(mem_nav, text="Ver", width=4, command=self._on_navigate_mem).pack(side=tk.LEFT, padx=2)
        ttk.Button(mem_nav, text="◀ -16", width=5, command=lambda: self._shift_mem_view(-16)).pack(side=tk.LEFT, padx=2)
        ttk.Button(mem_nav, text="+16 ▶", width=5, command=lambda: self._shift_mem_view(16)).pack(side=tk.LEFT, padx=2)

        columns_mem = ("addr", "hex", "dec", "char", "label")
        self.tree_mem = ttk.Treeview(frame_mem, columns=columns_mem, show="headings", height=8, selectmode="browse")
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

        scroll_mem_y = ttk.Scrollbar(frame_mem, orient=tk.VERTICAL, command=self.tree_mem.yview)
        self.tree_mem.configure(yscrollcommand=scroll_mem_y.set)

        self.tree_mem.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_mem_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_mem.bind("<Double-1>", self._on_edit_memory)

    def _build_console(self, parent):
        self.txt_console = scrolledtext.ScrolledText(
            parent, wrap=tk.CHAR, font=("Consolas", 10),
            bg="#1E1E1E", fg="#E0E0E0", insertbackground="#FFFFFF", height=6
        )
        self.txt_console.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 4))
        self.txt_console.bind("<KeyPress>", self._on_console_keypress)

        input_frame = ttk.Frame(parent)
        input_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(input_frame, text="Entrada de teclado:").pack(side=tk.LEFT, padx=2)
        self.ent_console_in = ttk.Entry(input_frame, font=("Consolas", 10))
        self.ent_console_in.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.ent_console_in.bind("<Return>", lambda e: self._on_send_console_input())
        self.ent_console_in.bind("<KeyPress>", self._on_entry_keypress)

        ttk.Button(input_frame, text="Enviar", command=self._on_send_console_input).pack(side=tk.LEFT, padx=2)
        ttk.Button(input_frame, text="Limpiar Consola", command=self._on_clear_console).pack(side=tk.RIGHT, padx=2)

    def _create_status_bar(self):
        status_bar = ttk.Frame(self, relief=tk.SUNKEN, padding=(6, 3))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_status = ttk.Label(status_bar, text="Listo para comenzar.", font=("Segoe UI", 9))
        self.lbl_status.pack(side=tk.LEFT)

        self.lbl_file_info = ttk.Label(status_bar, text="Sin archivo cargado", font=("Segoe UI", 9), foreground="#666")
        self.lbl_file_info.pack(side=tk.RIGHT)

    # =========================================================================
    # LÓGICA DE E/S DE CONSOLA Y TECLADO
    # =========================================================================

    def _handle_sim_output(self, text: str):
        """Callback llamado por el simulador al imprimir caracteres (OUT, PUTS, DDR)."""
        self.txt_console.insert(tk.END, text)
        self.txt_console.see(tk.END)

    def _on_kbsr_poll(self, has_input: bool):
        """Callback invocado cuando el procesador LC-3 sondea KBSR (xFE00)."""
        if not has_input:
            if not self.waiting_for_input:
                self.waiting_for_input = True
                self.lbl_cpu_state.config(text="ESPERANDO ENTRADA", bg="#F57C00")
                self.lbl_status.config(text="Esperando entrada del teclado (sondeando KBSR en el SO LC-3)...")
                try:
                    self.ent_console_in.config(background="#FFF9C4")
                except Exception:
                    pass
                self.ent_console_in.focus_set()
        else:
            if self.waiting_for_input:
                self.waiting_for_input = False
                try:
                    self.ent_console_in.config(background="#FFFFFF")
                except Exception:
                    pass
                if self.is_running:
                    self.lbl_cpu_state.config(text="EJECUTANDO", bg="#1976D2")
                    self.lbl_status.config(text="Carácter detectado en KBSR. Continuando ejecución...")

    def _handle_sim_input(self) -> int:
        """Callback llamado por el simulador para leer un carácter (GETC, IN, KBDR)."""
        # Si ya hay caracteres acumulados en el búfer, devolver el primero de inmediato
        if self.input_buffer:
            return self.input_buffer.pop(0)

        # Si el simulador ya no está en ejecución, no bloquear
        if not self.sim.running:
            return 0

        self.waiting_for_input = True
        self.lbl_cpu_state.config(text="ESPERANDO ENTRADA", bg="#F57C00")
        self.lbl_status.config(text="Esperando entrada del usuario (escribe en la caja y presiona Enter, o teclea en la consola)...")
        
        # Resaltar la entrada de texto y enfocar
        try:
            self.ent_console_in.config(background="#FFF9C4")
        except Exception:
            pass
        self.ent_console_in.focus_set()

        # Permitir que el botón de pausar y reiniciar estén activos mientras se espera entrada
        self.btn_pause.config(state=tk.NORMAL)

        # Refrescar la pantalla para que el usuario vea la instrucción actual y el cursor
        self._update_all_views()
        self._scroll_to_pc()

        # Esperar interactivamente usando el event loop de Tkinter sin congelar la ventana
        self.input_var.set("")
        self.wait_variable(self.input_var)

        try:
            self.ent_console_in.config(background="#FFFFFF")
        except Exception:
            pass

        self.waiting_for_input = False

        if not self.sim.running:
            self.lbl_cpu_state.config(text="PAUSADO", bg="#C62828")
            return 0

        self.lbl_cpu_state.config(text="EJECUTANDO", bg="#1976D2")
        self.lbl_status.config(text="Carácter recibido. Continuando ejecución...")

        if self.input_buffer:
            return self.input_buffer.pop(0)
        return 0

    def _on_console_keypress(self, event):
        """Permite ingresar un carácter presionando una tecla directamente en el área de terminal."""
        if (self.waiting_for_input or self.is_running) and event.char:
            char_code = ord(event.char)
            if char_code == 13:
                char_code = 10
            self.input_buffer.append(char_code & 0xFF)
            self.input_var.set("key_pressed")
            return "break"

    def _on_entry_keypress(self, event):
        """Captura la pulsación de una tecla individual para sondeo inmediato en GETC / IN."""
        if self.waiting_for_input and event.char:
            char_code = ord(event.char)
            if char_code == 13:
                char_code = 10
            self.input_buffer.append(char_code & 0xFF)
            self.ent_console_in.delete(0, tk.END)
            self.input_var.set("key_pressed")
            return "break"

    def _on_send_console_input(self):
        """Envía el contenido ingresado en la caja de texto al búfer de entrada."""
        text = self.ent_console_in.get()
        self.ent_console_in.delete(0, tk.END)
        if text:
            for ch in text:
                self.input_buffer.append(ord(ch) & 0xFF)
        else:
            # Si presiona Enter sin texto, enviar código de salto de línea '\n' (10)
            self.input_buffer.append(10)

        self.input_var.set("input_received")

    def _on_clear_console(self):
        self.txt_console.delete("1.0", tk.END)

    # =========================================================================
    # CARGA Y ENSAMBLADO DE ARCHIVOS
    # =========================================================================

    def _on_open_file(self):
        path = filedialog.askopenfilename(
            title="Seleccionar programa LC-3",
            filetypes=[("Archivos LC-3 (*.asm;*.obj)", "*.asm;*.obj"), ("Assembly (*.asm)", "*.asm"), ("Binario (*.obj)", "*.obj"), ("Todos", "*.*")]
        )
        if path:
            self.load_file(path)

    def _load_example(self, example_name: str):
        ex_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", example_name)
        if os.path.isfile(ex_path):
            self.load_file(ex_path)
        else:
            messagebox.showerror("Error", f"No se encontró el ejemplo '{example_name}'.")

    def load_file(self, file_path: str):
        """Carga un archivo .asm o .obj en el simulador y editor."""
        self._on_pause()
        self.current_file = file_path

        if file_path.lower().endswith(".asm"):
            # Cargar texto en el editor
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self.txt_editor.delete("1.0", tk.END)
                self.txt_editor.insert("1.0", content)
            except Exception as e:
                messagebox.showerror("Error de lectura", f"No se pudo leer el archivo: {e}")
                return

            # Auto-ensamblar
            try:
                obj_path = file_path[:-4] + ".obj"
                orig, count = assemble_file(file_path, obj_path=obj_path)
                self.sim.load_obj(obj_path)
                sym_path = file_path[:-4] + ".sym"
                self.sim.load_sym(sym_path)
                self.orig_pc = orig
                self.sim.reset(orig)
                self.lbl_status.config(text=f"Ensamblado exitoso: {count} palabras desde x{orig:04X}.")
            except AssemblyError as e:
                messagebox.showerror("Error de Ensamblado", str(e))
                return
            except Exception as e:
                messagebox.showerror("Error", f"Fallo al cargar: {e}")
                return
        else:
            # Archivo .obj directo
            try:
                orig = self.sim.load_obj(file_path)
                sym_path = os.path.splitext(file_path)[0] + ".sym"
                self.sim.load_sym(sym_path)
                self.orig_pc = orig
                self.sim.reset(orig)
                self.lbl_status.config(text=f"Binario cargado desde x{orig:04X}.")
            except Exception as e:
                messagebox.showerror("Error al cargar binario", str(e))
                return

        self.lbl_file_info.config(text=os.path.basename(file_path))
        self.disasm_base_addr = self.orig_pc
        self._update_all_views()
        self._scroll_to_pc()

    def _on_assemble_and_load(self):
        if self.current_file and self.current_file.lower().endswith(".asm"):
            self.load_file(self.current_file)
        else:
            self._on_assemble_editor_code()

    def _on_assemble_editor_code(self):
        """Ensambla el texto escrito actualmente en la pestaña del editor."""
        code = self.txt_editor.get("1.0", tk.END).strip()
        if not code:
            messagebox.showwarning("Editor vacío", "No hay código en el editor para ensamblar.")
            return

        assembler = LC3Assembler()
        try:
            orig, words, symbols = assembler.assemble(code)
            # Guardar temporalmente en un archivo para que sim lo mantenga
            temp_obj = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_temp_editor.obj")
            assembler.write_obj_file(temp_obj, orig, words)
            self.sim.load_obj(temp_obj)
            self.sim.symbols = {addr: name for name, addr in symbols.items()}
            self.sim.symbols.update(getattr(self.sim, "os_symbols", {}))
            self.orig_pc = orig
            self.disasm_base_addr = orig
            self.sim.reset(orig)
            self._update_all_views()
            self._scroll_to_pc()
            self.lbl_status.config(text=f"Código del editor ensamblado correctamente ({len(words)} palabras, origen x{orig:04X}).")
            messagebox.showinfo("Éxito", f"Ensamblado correcto.\nPalabras generadas: {len(words)}\nOrigen: x{orig:04X}")
        except AssemblyError as e:
            messagebox.showerror("Error de Ensamblado", str(e))
        except Exception as e:
            messagebox.showerror("Error Inesperado", str(e))

    def _on_save_editor_code(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".asm",
            filetypes=[("Assembly (*.asm)", "*.asm"), ("Todos", "*.*")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt_editor.get("1.0", tk.END))
            self.current_file = path
            self.lbl_file_info.config(text=os.path.basename(path))

    # =========================================================================
    # ACTUALIZACIÓN DE VISTAS (REGISTROS, MEMORIA, DESENSAMBLADO)
    # =========================================================================

    def _update_all_views(self):
        self._update_registers_view()
        self._update_disasm_view()
        self._update_memory_view()

    def _update_registers_view(self):
        # Actualizar R0 a R7
        for i in range(8):
            val = self.sim.reg[i]
            s_val = to_int16(val)
            self.tree_reg.item(f"r{i}", values=(f"R{i}", f"x{val:04X}", f"{s_val}", f"{val}"))

        # Actualizar PC y Ciclos
        self.lbl_pc_val.config(text=f"PC: x{self.sim.pc:04X}")
        self.lbl_cycles.config(text=f"Ciclos: {self.sim.instruction_count}")

        # Actualizar insignias de CC
        cc = self.sim.cond
        self.badge_n.config(bg="#F44336" if (cc & FL_NEG) else "#E0E0E0", fg="white" if (cc & FL_NEG) else "#9E9E9E")
        self.badge_z.config(bg="#4CAF50" if (cc & FL_ZRO) else "#E0E0E0", fg="white" if (cc & FL_ZRO) else "#9E9E9E")
        self.badge_p.config(bg="#2196F3" if (cc & FL_POS) else "#E0E0E0", fg="white" if (cc & FL_POS) else "#9E9E9E")

    def _update_disasm_view(self):
        # Desensamblar un rango relevante alrededor del PC o desde la dirección base
        self.tree_disasm.delete(*self.tree_disasm.get_children())

        # Si el PC está fuera del bloque actual, mover la base de visualización
        cur_base = getattr(self, "disasm_base_addr", self.orig_pc)
        if not (cur_base - 2 <= self.sim.pc < cur_base + 120):
            cur_base = max(0, self.sim.pc - 2)
            self.disasm_base_addr = cur_base

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
                "", tk.END, iid=item_id,
                values=(has_bp, f"x{addr:04X}", f"x{instr:04X}", dis, label),
                tags=tags
            )

    def _scroll_to_pc(self):
        item_id = f"addr_{self.sim.pc}"
        if not self.tree_disasm.exists(item_id):
            self._update_disasm_view()
        if self.tree_disasm.exists(item_id):
            self.tree_disasm.see(item_id)
            self.tree_disasm.selection_set(item_id)

    def _jump_to_address(self):
        raw = self.ent_jump_addr.get().strip().replace("x", "").replace("X", "").replace("#", "")
        try:
            addr = int(raw, 16) & MASK_16
            self.disasm_base_addr = addr
            self._update_disasm_view()
            item_id = f"addr_{addr}"
            if self.tree_disasm.exists(item_id):
                self.tree_disasm.see(item_id)
                self.tree_disasm.selection_set(item_id)
        except ValueError:
            pass

    def _update_memory_view(self, start_addr: Optional[int] = None):
        if start_addr is None:
            raw = self.ent_mem_addr.get().strip().replace("x", "").replace("X", "").replace("#", "")
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
                "", tk.END, iid=f"mem_{addr}",
                values=(f"x{addr:04X}", f"x{val:04X}", f"{s_val}", f"'{char_repr}'", sym)
            )

    def _on_navigate_mem(self):
        self._update_memory_view()

    def _shift_mem_view(self, delta: int):
        raw = self.ent_mem_addr.get().strip().replace("x", "").replace("X", "").replace("#", "")
        try:
            curr = int(raw, 16) & MASK_16
            new_addr = (curr + delta) & MASK_16
            self.ent_mem_addr.delete(0, tk.END)
            self.ent_mem_addr.insert(0, f"x{new_addr:04X}")
            self._update_memory_view(new_addr)
        except ValueError:
            pass

    # =========================================================================
    # CONTROL DE EJECUCIÓN (RUN, PAUSE, STEP, STEP OVER, RESET)
    # =========================================================================

    def _on_run(self):
        if self.is_running:
            return
        self.is_running = True
        self.sim.running = True
        self.btn_run.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_step.config(state=tk.DISABLED)
        self.btn_step_over.config(state=tk.DISABLED)
        self.lbl_cpu_state.config(text="EJECUTANDO", bg="#1976D2")
        self.lbl_status.config(text="Ejecución continua iniciada...")
        self._run_loop()

    def _run_loop(self):
        """Bucle de ejecución temporizado para mantener la interfaz reactiva."""
        if not self.is_running:
            return

        delay = self.sim_speed_ms.get()
        # Si estamos esperando entrada del teclado por sondeo, no consumimos CPU en vano
        if self.waiting_for_input:
            batch_size = 1
            step_delay = max(40, delay)
        else:
            batch_size = 1 if delay > 15 else 40
            step_delay = max(1, delay)

        for _ in range(batch_size):
            if not self.sim.running:
                self._stop_execution("Detenido por HALT.")
                return

            if self.sim.pc in self.breakpoints and self.sim.instruction_count > 0:
                self._stop_execution(f"Punto de interrupción alcanzado en x{self.sim.pc:04X}.")
                return

            if self._step_over_target is not None and self.sim.pc == self._step_over_target:
                target = self._step_over_target
                self._step_over_target = None
                self._stop_execution(f"Step over completado. PC en x{target:04X}.")
                return

            keep_going = self.sim.step()

            if self._step_over_target is not None and self.sim.pc == self._step_over_target:
                target = self._step_over_target
                self._step_over_target = None
                self._stop_execution(f"Step over completado. PC en x{target:04X}.")
                return

            if self.sim.pc in self.breakpoints:
                self._stop_execution(f"Punto de interrupción alcanzado en x{self.sim.pc:04X}.")
                return

            if not keep_going:
                self._stop_execution("Procesador detenido.")
                return

            if self.waiting_for_input:
                break

        self._update_all_views()
        self._scroll_to_pc()

        if self.is_running:
            self.after(step_delay, self._run_loop)

    def _on_pause(self):
        if not self.is_running and not self.waiting_for_input:
            return
        self.sim.running = False
        self._step_over_target = None
        if self.waiting_for_input:
            self.waiting_for_input = False
            try:
                self.ent_console_in.config(background="#FFFFFF")
            except Exception:
                pass
            self.input_var.set("pause")
        self._stop_execution("Ejecución pausada por el usuario.")

    def _stop_execution(self, status_msg: str):
        self.is_running = False
        self.sim.running = False
        self._step_over_target = None
        if self.waiting_for_input:
            self.waiting_for_input = False
            try:
                self.ent_console_in.config(background="#FFFFFF")
            except Exception:
                pass
        self.btn_run.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_step.config(state=tk.NORMAL)
        self.btn_step_over.config(state=tk.NORMAL)
        self.lbl_cpu_state.config(text="PAUSADO", bg="#C62828")
        self.lbl_status.config(text=status_msg)
        self._update_all_views()
        self._scroll_to_pc()

    def _on_step(self):
        self._on_pause()
        self.sim.running = True
        self.sim.step()
        self._update_all_views()
        self._scroll_to_pc()
        self.lbl_status.config(text=f"Paso ejecutado. Próxima instrucción en x{self.sim.pc:04X}.")

    def _on_step_over(self):
        """Pasa por encima de subrutinas o TRAPs (Step Over)."""
        self._on_pause()
        instr = self.sim.mem_read(self.sim.pc)
        op = (instr >> 12) & 0xF
        trapvect = instr & 0xFF

        is_sub = (op == OP_JSR) or (op == OP_TRAP and trapvect != TRAP_HALT)

        if is_sub:
            ret_addr = (self.sim.pc + 1) & MASK_16
            self.sim.running = True
            steps = 0
            while self.sim.running and self.sim.pc != ret_addr and steps < 200:
                if self.sim.pc in self.breakpoints:
                    break
                if self.waiting_for_input:
                    break
                self.sim.step()
                steps += 1

            if self.sim.pc == ret_addr or not self.sim.running or self.sim.pc in self.breakpoints:
                self._stop_execution(f"Step over completado. PC en x{self.sim.pc:04X}.")
            else:
                # Subrutina larga o esperando entrada de E/S por sondeo
                self._step_over_target = ret_addr
                self.is_running = True
                self.btn_run.config(state=tk.DISABLED)
                self.btn_pause.config(state=tk.NORMAL)
                self.btn_step.config(state=tk.DISABLED)
                self.btn_step_over.config(state=tk.DISABLED)
                if not self.waiting_for_input:
                    self.lbl_cpu_state.config(text="EJECUTANDO", bg="#1976D2")
                self._run_loop()
        else:
            self.sim.step()
            self._update_all_views()
            self._scroll_to_pc()
            self.lbl_status.config(text=f"Paso ejecutado. Próxima instrucción en x{self.sim.pc:04X}.")

    def _on_reset(self):
        self._on_pause()
        self._step_over_target = None
        if self.waiting_for_input:
            self.waiting_for_input = False
            try:
                self.ent_console_in.config(background="#FFFFFF")
            except Exception:
                pass
            self.input_var.set("reset")
        self.input_buffer.clear()
        self.disasm_base_addr = self.orig_pc
        self.sim.reset(self.orig_pc)
        self._update_all_views()
        self._scroll_to_pc()
        self.lbl_cpu_state.config(text="LISTO", bg="#2E7D32")
        self.lbl_status.config(text=f"Simulador reiniciado. PC = x{self.orig_pc:04X}.")

    def _on_close(self):
        """Manejador de cierre seguro de la ventana para desbloquear bucles de espera."""
        self.is_running = False
        self.sim.running = False
        if self.waiting_for_input:
            self.input_var.set("close")
        self.destroy()

    # =========================================================================
    # BREAKPOINTS Y EDICIÓN RÁPIDA
    # =========================================================================

    def _on_disasm_double_click(self, event):
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
            self._update_disasm_view()
            self._scroll_to_pc()
        except ValueError:
            pass

    def _on_clear_breakpoints(self):
        self.breakpoints.clear()
        self._update_disasm_view()
        self._scroll_to_pc()
        messagebox.showinfo("Breakpoints", "Todos los puntos de interrupción han sido eliminados.")

    def _on_edit_register(self, event):
        item = self.tree_reg.identify_row(event.y)
        if not item:
            return
        reg_num = int(item[1])  # 'r0' -> 0
        curr_val = self.sim.reg[reg_num]

        val_dialog = tk.Toplevel(self)
        val_dialog.title(f"Modificar R{reg_num}")
        val_dialog.geometry("300x120")
        val_dialog.resizable(False, False)
        val_dialog.transient(self)
        val_dialog.grab_set()

        ttk.Label(val_dialog, text=f"Nuevo valor para R{reg_num} (hex ej: x1234 o dec ej: #42):").pack(pady=8)
        ent = ttk.Entry(val_dialog, font=("Consolas", 10))
        ent.pack(pady=4)
        ent.insert(0, f"x{curr_val:04X}")
        ent.focus_set()

        def apply_val():
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
                self._update_registers_view()
                val_dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Valor numérico no válido.")

        btn_box = ttk.Frame(val_dialog)
        btn_box.pack(pady=6)
        ttk.Button(btn_box, text="Aceptar", command=apply_val).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_box, text="Cancelar", command=val_dialog.destroy).pack(side=tk.LEFT, padx=4)
        ent.bind("<Return>", lambda e: apply_val())

    def _on_edit_memory(self, event):
        item = self.tree_mem.identify_row(event.y)
        if not item:
            return
        addr_str = self.tree_mem.item(item, "values")[0].replace("x", "")
        addr = int(addr_str, 16)
        curr_val = self.sim.memory[addr]

        val_dialog = tk.Toplevel(self)
        val_dialog.title(f"Modificar Memoria x{addr:04X}")
        val_dialog.geometry("320x120")
        val_dialog.resizable(False, False)
        val_dialog.transient(self)
        val_dialog.grab_set()

        ttk.Label(val_dialog, text=f"Nuevo valor para mem[x{addr:04X}] (hex ej: x002A o #42):").pack(pady=8)
        ent = ttk.Entry(val_dialog, font=("Consolas", 10))
        ent.pack(pady=4)
        ent.insert(0, f"x{curr_val:04X}")
        ent.focus_set()

        def apply_mem():
            token = ent.get().strip()
            try:
                if token.upper().startswith("X") or token.upper().startswith("0X"):
                    val = int(token.upper().replace("0X", "").replace("X", ""), 16)
                elif token.startswith("#"):
                    val = int(token[1:], 10)
                else:
                    val = int(token, 16)
                self.sim.mem_write(addr, val)
                self._update_memory_view()
                self._update_disasm_view()
                val_dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Valor numérico no válido.")

        btn_box = ttk.Frame(val_dialog)
        btn_box.pack(pady=6)
        ttk.Button(btn_box, text="Aceptar", command=apply_mem).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_box, text="Cancelar", command=val_dialog.destroy).pack(side=tk.LEFT, padx=4)
        ent.bind("<Return>", lambda e: apply_mem())

    # =========================================================================
    # DIÁLOGOS DE AYUDA Y ACERCA DE
    # =========================================================================

    def _show_isa_help(self):
        info = """Referencia Rápida de la ISA LC-3:

Instrucciones Aritméticas / Lógicas:
  ADD DR, SR1, SR2       ; DR = SR1 + SR2
  ADD DR, SR1, imm5      ; DR = SR1 + imm5 (-16 a 15)
  AND DR, SR1, SR2       ; DR = SR1 AND SR2
  AND DR, SR1, imm5      ; DR = SR1 AND imm5
  NOT DR, SR             ; DR = NOT(SR)

Instrucciones de Salto y Control:
  BR{n,z,p} LABEL        ; Salta si condición coincide
  JMP BaseR              ; PC = BaseR
  RET                    ; Retorno de subrutina (JMP R7)
  JSR LABEL              ; R7 = PC, PC = LABEL
  JSRR BaseR             ; R7 = PC, PC = BaseR

Instrucciones de Memoria:
  LD  DR, LABEL          ; DR = mem[LABEL] (relativo a PC)
  LDI DR, LABEL          ; DR = mem[mem[LABEL]] (indirecto)
  LDR DR, BaseR, offset6 ; DR = mem[BaseR + offset6]
  LEA DR, LABEL          ; DR = dirección de LABEL
  ST  SR, LABEL          ; mem[LABEL] = SR
  STI SR, LABEL          ; mem[mem[LABEL]] = SR
  STR SR, BaseR, offset6 ; mem[BaseR + offset6] = SR

Servicios TRAP:
  GETC (x20)  Lee 1 carácter sin eco en R0
  OUT  (x21)  Imprime carácter en R0[7:0]
  PUTS (x22)  Imprime cadena apuntada por R0
  IN   (x23)  Pide carácter con mensaje y eco
  HALT (x25)  Detiene la máquina
"""
        win = tk.Toplevel(self)
        win.title("Referencia de la ISA LC-3")
        win.geometry("500x520")
        txt = scrolledtext.ScrolledText(win, font=("Consolas", 10), wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert("1.0", info)
        txt.config(state=tk.DISABLED)

    def _show_about(self):
        msg = (
            "Simulador y Ensamblador Pedagógico LC-3\n"
            "Arquitectura Little Computer 3 (Patt & Patel)\n\n"
            "Desarrollado en Python 3 puro con interfaz gráfica Tkinter.\n"
            "Laboratorio 3 - Arquitectura de Computadoras."
        )
        messagebox.showinfo("Acerca del Simulador LC-3", msg)


def main():
    initial = sys.argv[1] if len(sys.argv) > 1 else None
    app = LC3GUI(initial_file=initial)
    app.mainloop()


if __name__ == "__main__":
    main()
