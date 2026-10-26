"""Presenta la máquina LC-3 mediante una raíz Tkinter y sus vistas integradas.

La CLI crea ``LC3GUI``, que compone cuatro paneles concretos.
Tk invoca los callbacks registrados en menús, botones, eventos y temporizadores.
La raíz delega ensamblado en memoria y persistencia a sus componentes respectivos,
y ejecución/MMIO a ``LC3Simulator``. Conserva archivos de trabajo, control de
ejecución, FIFO y widgets globales; los paneles poseen las vistas. Los errores
capturados se muestran en diálogos,
sin restaurar necesariamente los efectos de disco o máquina ya realizados.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional, Set

from lc3.domain.isa import MASK_16, OP_JSR, OP_TRAP, TRAP_HALT
from lc3.domain.assembler import LC3Assembler, AssemblyError
from lc3.infrastructure.program_files import (
    assemble_file,
    load_obj,
    load_sym,
    write_obj_file,
)
from lc3.bootstrap import create_simulator, EXAMPLES_DIR
from lc3.presentation.gui.disassembly import DisassemblyPanel
from lc3.presentation.gui.machine_state import MachineStatePanel
from lc3.presentation.gui.console import ConsolePanel
from lc3.presentation.gui.editor import EditorPanel


class LC3GUI(tk.Tk):
    """Coordina CPU, edición, vistas y entrada dentro del bucle de eventos Tk.

    La instancia posee ``sim``, ``orig_pc``, ``current_file``, ``breakpoints``,
    ``is_running``, ``sim_speed_ms``, ``waiting_for_input``, ``input_buffer``,
    ``input_var`` y ``_step_over_target``. El simulador posee registros,
    memoria y símbolos; sus callbacks acceden al estado de esta raíz.
    Los paneles poseen árboles, entradas, etiquetas y base de desensamblado;
    la raíz conserva sólo composición y controles globales.
    ``wait_variable`` permite eventos anidados durante una lectura bloqueante;
    los lotes de ejecución continua se reprograman mediante ``after``.
    """

    def __init__(self, initial_file: Optional[str] = None):
        """Construye vistas, registra E/S y cierre, y carga fuente o ejemplo.

        La CLI invoca este constructor. Instala los cuatro callbacks del
        simulador después de construir los paneles que utilizarán;
        después carga ``initial_file`` si existe, o ``examples/hello.asm``
        en EXAMPLES_DIR. Si ambos faltan, sólo refresca las vistas.

        Args:
            initial_file: Ruta opcional de fuente o binario inicial.

        Raises:
            tk.TclError: Si Tk no puede crear la raíz o sus recursos.
        """
        super().__init__()
        self.title("Simulador y Ensamblador LC-3 (Little Computer 3)")
        self.geometry("1180x820")
        self.minsize(980, 680)

        # Configurar icono y estilo
        self._configure_styles()

        # Instancia del simulador
        self.sim = create_simulator()
        self.orig_pc = 0x3000
        self.current_file: Optional[str] = None
        self.breakpoints: Set[int] = set()

        # Variables de control de ejecución
        self.is_running = False
        self.sim_speed_ms = tk.IntVar(value=50)  # Intervalo de actualización en ms
        self.waiting_for_input = False
        self.input_buffer = []
        self.input_var = tk.StringVar(self, value="")
        self._step_over_target: Optional[int] = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Construir Interfaz
        self._create_menu()
        self._create_toolbar()
        self._create_main_panels()
        self._create_status_bar()

        # Redirigir E/S del simulador
        self.sim.output_fn = self.console.write_output
        self.sim.input_fn = self._handle_sim_input
        self.sim.has_input_fn = lambda: len(self.input_buffer) > 0
        self.sim.kbsr_poll_fn = self._on_kbsr_poll

        # Cargar archivo inicial o ejemplo si se especifica
        if initial_file and os.path.isfile(initial_file):
            self.load_file(initial_file, is_example=False)
        else:
            # Intentar cargar hello.asm por defecto si existe (como ejemplo, no como archivo de usuario)
            default_ex = str(EXAMPLES_DIR / "hello.asm")
            if os.path.isfile(default_ex):
                self.load_file(default_ex, is_example=True)
            else:
                self._update_all_views()

    def _configure_styles(self):
        """Aplica estilos desde el constructor; ignora sólo el fallo de tema."""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Estilo para botones de la barra de herramientas
        style.configure("Tool.TButton", font=("Segoe UI", 9, "bold"), padding=4)
        style.configure(
            "Accent.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=4,
            foreground="#005A9E",
        )
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure("Treeview", font=("Consolas", 10), rowheight=22)

    # =========================================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # =========================================================================

    def _create_menu(self):
        """Crea menús y registra comandos y atajos de archivo y simulación.

        Invocado por el constructor; las lambdas de ``bind`` descartan el
        evento y llaman los mismos métodos que los comandos de menú.
        """
        menubar = tk.Menu(self)

        # Menú Archivo
        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(
            label="Abrir archivo (.asm / .obj)...",
            command=self._on_open_file,
            accelerator="Ctrl+O",
        )
        menu_file.add_command(
            label="Ensamblar y Cargar archivo actual (Editor)",
            command=self._on_assemble_and_load,
            accelerator="F5",
        )
        menu_file.add_separator()
        menu_file.add_command(
            label="Cargar Ejemplo: Hello World",
            command=lambda: self._load_example("hello.asm"),
        )
        menu_file.add_command(
            label="Cargar Ejemplo: Multiplicación",
            command=lambda: self._load_example("mult.asm"),
        )
        menu_file.add_command(
            label="Cargar Ejemplo: Contador Regresivo",
            command=lambda: self._load_example("count.asm"),
        )
        menu_file.add_command(
            label="Cargar Ejemplo: Eco Interactivo",
            command=lambda: self._load_example("echo.asm"),
        )
        menu_file.add_separator()
        menu_file.add_command(label="Salir", command=self.quit, accelerator="Alt+F4")
        menubar.add_cascade(label="Archivo", menu=menu_file)

        # Menú Simulación
        menu_sim = tk.Menu(menubar, tearoff=0)
        menu_sim.add_command(
            label="Ejecutar (Run)", command=self._on_run, accelerator="F9"
        )
        menu_sim.add_command(
            label="Pausar (Pause)", command=self._on_pause, accelerator="F10"
        )
        menu_sim.add_command(
            label="Paso a Paso (Step)", command=self._on_step, accelerator="F11"
        )
        menu_sim.add_command(
            label="Paso Sobre Subrutina (Step Over)",
            command=self._on_step_over,
            accelerator="F12",
        )
        menu_sim.add_separator()
        menu_sim.add_command(
            label="Reiniciar (Reset)", command=self._on_reset, accelerator="Ctrl+R"
        )
        menu_sim.add_command(
            label="Limpiar Breakpoints", command=self._on_clear_breakpoints
        )
        menubar.add_cascade(label="Simulación", menu=menu_sim)

        # Menú Ayuda
        menu_help = tk.Menu(menubar, tearoff=0)
        menu_help.add_command(
            label="Instrucciones de la ISA LC-3", command=self._show_isa_help
        )
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
        """Crea controles y registra botones y traza de velocidad de la raíz."""
        toolbar = ttk.Frame(self, padding=(8, 6), relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        # Botones de archivo
        ttk.Button(
            toolbar, text="📂 Abrir", style="Tool.TButton", command=self._on_open_file
        ).pack(side=tk.LEFT, padx=3)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # Botones de simulación
        self.btn_run = ttk.Button(
            toolbar, text="▶️ Ejecutar", style="Accent.TButton", command=self._on_run
        )
        self.btn_run.pack(side=tk.LEFT, padx=3)

        self.btn_pause = ttk.Button(
            toolbar,
            text="⏸️ Pausar",
            style="Tool.TButton",
            command=self._on_pause,
            state=tk.DISABLED,
        )
        self.btn_pause.pack(side=tk.LEFT, padx=3)

        self.btn_step = ttk.Button(
            toolbar, text="⏭️ Paso (Step)", style="Tool.TButton", command=self._on_step
        )
        self.btn_step.pack(side=tk.LEFT, padx=3)

        self.btn_step_over = ttk.Button(
            toolbar,
            text="⏩ Paso Sobre (Next)",
            style="Tool.TButton",
            command=self._on_step_over,
        )
        self.btn_step_over.pack(side=tk.LEFT, padx=3)

        self.btn_reset = ttk.Button(
            toolbar, text="🔄 Reiniciar", style="Tool.TButton", command=self._on_reset
        )
        self.btn_reset.pack(side=tk.LEFT, padx=3)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # Control de velocidad
        ttk.Label(toolbar, text="Velocidad:").pack(side=tk.LEFT, padx=(2, 4))
        self.speed_scale = ttk.Scale(
            toolbar,
            from_=1,
            to=200,
            orient=tk.HORIZONTAL,
            variable=self.sim_speed_ms,
            length=120,
        )
        self.speed_scale.pack(side=tk.LEFT, padx=3)
        self.lbl_speed_text = ttk.Label(toolbar, text="50 ms")
        self.lbl_speed_text.pack(side=tk.LEFT, padx=(2, 8))
        self.sim_speed_ms.trace_add("write", lambda *a: self._update_speed_label())

        # Estado del procesador
        self.lbl_cpu_state = tk.Label(
            toolbar,
            text="LISTO",
            font=("Segoe UI", 9, "bold"),
            bg="#2E7D32",
            fg="white",
            padx=10,
            pady=2,
        )
        self.lbl_cpu_state.pack(side=tk.RIGHT, padx=5)

    def _update_speed_label(self):
        """Actualiza el rótulo al escribir la variable trazada en la toolbar."""
        val = self.sim_speed_ms.get()
        if val <= 5:
            self.lbl_speed_text.config(text="Máx")
        else:
            self.lbl_speed_text.config(text=f"{val} ms")

    def _create_main_panels(self):
        """Compone cuatro paneles concretos y conecta sólo sus dependencias."""
        main_paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main_paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=4)

        top_paned = ttk.PanedWindow(main_paned, orient=tk.HORIZONTAL)
        main_paned.add(top_paned, weight=3)

        left_notebook = ttk.Notebook(top_paned)
        top_paned.add(left_notebook, weight=3)
        self.disassembly = DisassemblyPanel(left_notebook, self.sim, self.breakpoints)
        self.editor = EditorPanel(
            left_notebook, self._on_assemble_editor_code, self._on_save_editor_code
        )
        left_notebook.add(self.disassembly, text=" Desensamblado / Ejecución ")
        left_notebook.add(self.editor, text=" Editor de Código Assembly ")

        self.machine_state = MachineStatePanel(
            top_paned, self.sim, self.disassembly.refresh
        )
        top_paned.add(self.machine_state, weight=2)

        bottom_frame = ttk.LabelFrame(
            main_paned, text=" Consola de E/S (Terminal LC-3) ", padding=4
        )
        main_paned.add(bottom_frame, weight=1)
        self.console = ConsolePanel(
            bottom_frame,
            self._on_console_keypress,
            self._on_entry_keypress,
            self._on_send_console_input,
        )
        self.console.pack(fill=tk.BOTH, expand=True)

    def _create_status_bar(self):
        """Crea etiquetas de estado y archivo que modifican los controladores."""
        status_bar = ttk.Frame(self, relief=tk.SUNKEN, padding=(6, 3))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_status = ttk.Label(
            status_bar, text="Listo para comenzar.", font=("Segoe UI", 9)
        )
        self.lbl_status.pack(side=tk.LEFT)

        self.lbl_file_info = ttk.Label(
            status_bar,
            text="Sin archivo cargado",
            font=("Segoe UI", 9),
            foreground="#666",
        )
        self.lbl_file_info.pack(side=tk.RIGHT)

    # =========================================================================
    # LÓGICA DE E/S DE CONSOLA Y TECLADO
    # =========================================================================

    def _on_kbsr_poll(self, has_input: bool):
        """Refleja disponibilidad de teclado notificada por MMIO de la máquina.

        Registrado como ``sim.kbsr_poll_fn`` en el constructor, también recibe
        la notificación de consumo de KBDR. Sin dato activa espera, resalta y
        enfoca; con dato retira el resaltado y, si corre, actualiza el estado.
        No consume FIFO, no bloquea ni escribe ``input_var``. Sólo ignora
        fallos al configurar el color de la entrada.

        Args:
            has_input: Disponibilidad comunicada por la máquina.
        """
        if not has_input:
            if not self.waiting_for_input:
                self.waiting_for_input = True
                self.lbl_cpu_state.config(text="ESPERANDO ENTRADA", bg="#F57C00")
                self.lbl_status.config(
                    text="Esperando entrada del teclado (sondeando KBSR en el SO LC-3)..."
                )
                self.console.set_input_highlight(True)
                self.console.focus_input()
        else:
            if self.waiting_for_input:
                self.waiting_for_input = False
                self.console.set_input_highlight(False)
                if self.is_running:
                    self.lbl_cpu_state.config(text="EJECUTANDO", bg="#1976D2")
                    self.lbl_status.config(
                        text="Carácter detectado en KBSR. Continuando ejecución..."
                    )

    def _handle_sim_input(self) -> int:
        """Consume FIFO o espera una señal Tk para satisfacer ``sim.input_fn``.

        La máquina lo invoca en lectura nativa o KBDR; se registra en el
        constructor. Devuelve primero un carácter pendiente incluso si la
        CPU está detenida. Sin dato y sin ejecución devuelve cero; en otro
        caso resalta, enfoca, habilita Pause, refresca vistas y desplaza al PC
        antes de vaciar y esperar ``input_var`` mediante ``wait_variable``.
        Teclas, envío, pausa, reset o cierre pueden señalizar esa variable.
        Al despertar retira el resaltado y consume como máximo un carácter;
        si la máquina fue detenida devuelve cero sin consumir la FIFO.
        No revierte efectos de eventos procesados durante la espera.

        Returns:
            int: Código pendiente, o cero si no hay dato o se detuvo la CPU.
        """
        # Si ya hay caracteres acumulados en el búfer, devolver el primero de inmediato
        if self.input_buffer:
            return self.input_buffer.pop(0)

        # Si el simulador ya no está en ejecución, no bloquear
        if not self.sim.running:
            return 0

        self.waiting_for_input = True
        self.lbl_cpu_state.config(text="ESPERANDO ENTRADA", bg="#F57C00")
        self.lbl_status.config(
            text="Esperando entrada del usuario (escribe en la caja y presiona Enter, o teclea en la consola)..."
        )

        # Resaltar la entrada de texto y enfocar
        self.console.set_input_highlight(True)
        self.console.focus_input()

        # Permitir que el botón de pausar y reiniciar estén activos mientras se espera entrada
        self.btn_pause.config(state=tk.NORMAL)

        # Refrescar la pantalla para que el usuario vea la instrucción actual y el cursor
        self._update_all_views()
        self.disassembly.scroll_to_pc()

        # Esperar interactivamente usando el event loop de Tkinter sin congelar la ventana
        self.input_var.set("")
        self.wait_variable(self.input_var)

        self.console.set_input_highlight(False)

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
        """Recibe KeyPress de terminal registrado en ``ConsolePanel.__init__``.

        Durante ejecución o espera añade el byte de ``event.char`` a la FIFO,
        convierte CR en LF y señala ``input_var`` sin eco local.

        Returns:
            str o None: ``"break"`` si consume la tecla; None en otro caso.
        """
        if (self.waiting_for_input or self.is_running) and event.char:
            char_code = ord(event.char)
            if char_code == 13:
                char_code = 10
            self.input_buffer.append(char_code & 0xFF)
            self.input_var.set("key_pressed")
            return "break"

    def _on_entry_keypress(self, event):
        """Recibe KeyPress de la entrada registrado en ``ConsolePanel.__init__``.

        Sólo en espera encola un byte, convierte CR en LF, vacía la entrada
        y señala ``input_var`` para sondeo o lectura bloqueante.

        Returns:
            str o None: ``"break"`` si consume la tecla; None en otro caso.
        """
        if self.waiting_for_input and event.char:
            char_code = ord(event.char)
            if char_code == 13:
                char_code = 10
            self.input_buffer.append(char_code & 0xFF)
            self.console.clear_input()
            self.input_var.set("key_pressed")
            return "break"

    def _on_send_console_input(self):
        """Encola texto y señala lectura por Return o Enviar de la consola.

        Registrado en ``ConsolePanel.__init__``; borra la entrada y encola los bytes
        del texto sin añadir terminador, o un LF si el texto estaba vacío.
        Escribe ``input_var`` aunque la CPU no esté esperando.
        """
        text = self.console.take_input_text()
        if text:
            for ch in text:
                self.input_buffer.append(ord(ch) & 0xFF)
        else:
            # Si presiona Enter sin texto, enviar código de salto de línea '\n' (10)
            self.input_buffer.append(10)

        self.input_var.set("input_received")

    # =========================================================================
    # CARGA Y ENSAMBLADO DE ARCHIVOS
    # =========================================================================

    def _on_open_file(self):
        """Abre diálogo desde menú, Ctrl+O o toolbar y carga si no se cancela."""
        path = filedialog.askopenfilename(
            title="Seleccionar programa LC-3",
            filetypes=[
                ("Archivos LC-3 (*.asm;*.obj)", "*.asm;*.obj"),
                ("Assembly (*.asm)", "*.asm"),
                ("Binario (*.obj)", "*.obj"),
                ("Todos", "*.*"),
            ],
        )
        if path:
            self.load_file(path)

    def _load_example(self, example_name: str):
        """Carga el ejemplo elegido por las lambdas del menú o muestra error.

        Resuelve el nombre bajo ``EXAMPLES_DIR`` de la composición y delega
        como ejemplo, evitando convertirlo en archivo de trabajo.
        """
        ex_path = str(EXAMPLES_DIR / example_name)
        if os.path.isfile(ex_path):
            self.load_file(ex_path, is_example=True)
        else:
            messagebox.showerror(
                "Error", f"No se encontró el ejemplo '{example_name}'."
            )

    def load_file(self, file_path: str, is_example: bool = False):
        """Pausa y carga fuente o binario desde constructor o selección de archivo.

        Cambia ``current_file`` antes de intentar leer: None para ejemplos.
        En fuente copia UTF-8 con reemplazo al editor. Un ejemplo se ensambla
        mediante ``LC3Assembler`` y carga palabras directamente; una fuente
        de usuario genera OBJ/SYM adyacentes mediante
        ``assemble_file``. Otros sufijos se tratan como binario y buscan SYM
        adyacente. La máquina carga antes de ``reset(orig)``; los ejemplos
        reemplazan símbolos y añaden los del SO.
        Errores de lectura, ensamblado o carga muestran diálogo y retornan,
        sin deshacer archivo actual, editor, salidas o carga parcial.
        En éxito actualiza origen/base, rótulos y vistas, luego desplaza al PC.

        Args:
            file_path: Ruta a interpretar por su sufijo.
            is_example: Evita guardar la ruta como trabajo de usuario.
        """
        self._on_pause()
        self.current_file = None if is_example else file_path

        if file_path.lower().endswith(".asm"):
            # Cargar texto en el editor
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self.editor.set_source(content)
            except Exception as e:
                messagebox.showerror(
                    "Error de lectura", f"No se pudo leer el archivo: {e}"
                )
                return

            # Auto-ensamblar
            try:
                if is_example:
                    assembler = LC3Assembler()
                    orig, words, symbols = assembler.assemble(content)
                    self.sim.load_words(orig, words)
                    self.sim.symbols = {addr: name for name, addr in symbols.items()}
                    self.sim.symbols.update(getattr(self.sim, "os_symbols", {}))
                    count = len(words)
                else:
                    obj_path = file_path[:-4] + ".obj"
                    orig, count = assemble_file(file_path, obj_path=obj_path)
                    load_obj(self.sim, obj_path)
                    sym_path = file_path[:-4] + ".sym"
                    load_sym(self.sim, sym_path)
                self.orig_pc = orig
                self.sim.reset(orig)
                self.lbl_status.config(
                    text=f"Ensamblado exitoso: {count} palabras desde x{orig:04X}."
                )
            except AssemblyError as e:
                messagebox.showerror("Error de Ensamblado", str(e))
                return
            except Exception as e:
                messagebox.showerror("Error", f"Fallo al cargar: {e}")
                return
        else:
            # Archivo .obj directo
            try:
                orig = load_obj(self.sim, file_path)
                sym_path = os.path.splitext(file_path)[0] + ".sym"
                load_sym(self.sim, sym_path)
                self.orig_pc = orig
                self.sim.reset(orig)
                self.lbl_status.config(text=f"Binario cargado desde x{orig:04X}.")
            except Exception as e:
                messagebox.showerror("Error al cargar binario", str(e))
                return

        display_name = (
            f"[Ejemplo] {os.path.basename(file_path)}"
            if is_example
            else os.path.basename(file_path)
        )
        self.lbl_file_info.config(text=display_name)
        self.disassembly.base_addr = self.orig_pc
        self._update_all_views()
        self.disassembly.scroll_to_pc()

    def _on_assemble_and_load(self):
        """Autoguarda y ensambla por menú Ensamblar o F5 de ``_create_menu``.

        Sólo sobrescribe ``current_file`` si acaba en .asm, usando el texto
        completo del editor. Un fallo de guardado muestra advertencia pero
        no impide llamar ``_on_assemble_editor_code``; ejemplos no tienen ruta
        de trabajo y por tanto no se sobrescriben aquí.
        """
        if self.current_file and self.current_file.lower().endswith(".asm"):
            try:
                code = self.editor.get_source()
                with open(self.current_file, "w", encoding="utf-8") as f:
                    f.write(code)
            except Exception as e:
                messagebox.showwarning(
                    "Advertencia",
                    f"No se pudo guardar automáticamente en {self.current_file}: {e}",
                )
        self._on_assemble_editor_code()

    def _on_assemble_editor_code(self):
        """Ensambla editor por su botón o por ``_on_assemble_and_load``.

        Rechaza texto vacío con advertencia. Escribe OBJ adyacente si hay
        fuente de usuario y carga ese OBJ; en otro caso carga palabras en memoria.
        No guarda fuente ni SYM. Reemplaza símbolos y
        añade SO, fija origen/base y resetea; después refresca y desplaza.
        Muestra éxito o captura errores en diálogos sin rollback y sin
        pausar por sí mismo la ejecución ya iniciada.
        """
        code = self.editor.get_source().strip()
        if not code:
            messagebox.showwarning(
                "Editor vacío", "No hay código en el editor para ensamblar."
            )
            return

        assembler = LC3Assembler()
        try:
            orig, words, symbols = assembler.assemble(code)
            # Guardar en archivo .obj
            if self.current_file and self.current_file.lower().endswith(".asm"):
                obj_path = os.path.splitext(self.current_file)[0] + ".obj"
                write_obj_file(obj_path, orig, words)
                load_obj(self.sim, obj_path)
            else:
                self.sim.load_words(orig, words)
            self.sim.symbols = {addr: name for name, addr in symbols.items()}
            self.sim.symbols.update(getattr(self.sim, "os_symbols", {}))
            self.orig_pc = orig
            self.disassembly.base_addr = orig
            self.sim.reset(orig)
            self._update_all_views()
            self.disassembly.scroll_to_pc()
            self.lbl_status.config(
                text=f"Código del editor ensamblado correctamente ({len(words)} palabras, origen x{orig:04X})."
            )
            messagebox.showinfo(
                "Éxito",
                f"Ensamblado correcto.\nPalabras generadas: {len(words)}\nOrigen: x{orig:04X}",
            )
        except AssemblyError as e:
            messagebox.showerror("Error de Ensamblado", str(e))
        except Exception as e:
            messagebox.showerror("Error Inesperado", str(e))

    def _on_save_editor_code(self):
        """Guarda texto completo por Guardar Como registrado en el editor.

        Cancelar no modifica estado; en éxito cambia ``current_file`` y su
        rótulo. Los errores de apertura/escritura se propagan al callback Tk.
        """
        path = filedialog.asksaveasfilename(
            defaultextension=".asm",
            filetypes=[("Assembly (*.asm)", "*.asm"), ("Todos", "*.*")],
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.get_source())
            self.current_file = path
            self.lbl_file_info.config(text=os.path.basename(path))

    # =========================================================================
    # ACTUALIZACIÓN DE VISTAS (REGISTROS, MEMORIA, DESENSAMBLADO)
    # =========================================================================

    def _update_all_views(self):
        """Refresca registros, desensamblado y memoria, en ese orden, sin scroll."""
        self.machine_state.refresh_registers()
        self.disassembly.refresh()
        self.machine_state.refresh_memory()

    # =========================================================================
    # CONTROL DE EJECUCIÓN (RUN, PAUSE, STEP, STEP OVER, RESET)
    # =========================================================================

    def _on_run(self):
        """Inicia lotes por Run de menú, F9 o toolbar, salvo si ya corre.

        Activa banderas de raíz y máquina, ajusta controles y llama de
        inmediato ``_run_loop``; éste programa las siguientes iteraciones.
        """
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
        """Ejecuta lotes desde Run/Next y desde su propio registro ``after``.

        Sin ejecución de raíz retorna. En espera sondea una instrucción por
        lote con demora mínima de 40 ms; normalmente ejecuta una o 40 según
        velocidad, con demora mínima de 1 ms. Comprueba HALT, breakpoints y
        destino Next alrededor de ``sim.step`` y delega detención; un BP
        inicial se omite sólo antes de ejecutar la primera instrucción.
        Al completar lote refresca vistas, desplaza al PC y programa otro
        ``after`` si sigue activo. No cancela temporizadores previos ni
        captura errores de la máquina o sus callbacks.
        """
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
                self._stop_execution(
                    f"Punto de interrupción alcanzado en x{self.sim.pc:04X}."
                )
                return

            if (
                self._step_over_target is not None
                and self.sim.pc == self._step_over_target
            ):
                target = self._step_over_target
                self._step_over_target = None
                self._stop_execution(f"Step over completado. PC en x{target:04X}.")
                return

            keep_going = self.sim.step()

            if (
                self._step_over_target is not None
                and self.sim.pc == self._step_over_target
            ):
                target = self._step_over_target
                self._step_over_target = None
                self._stop_execution(f"Step over completado. PC en x{target:04X}.")
                return

            if self.sim.pc in self.breakpoints:
                self._stop_execution(
                    f"Punto de interrupción alcanzado en x{self.sim.pc:04X}."
                )
                return

            if not keep_going:
                self._stop_execution("Procesador detenido.")
                return

            if self.waiting_for_input:
                break

        self._update_all_views()
        self.disassembly.scroll_to_pc()

        if self.is_running:
            self.after(step_delay, self._run_loop)

    def _on_pause(self):
        """Pausa por menú/F10/toolbar o por carga, Step, Next y Reset.

        Si no corre ni espera no hace nada. Detiene CPU, limpia destino Next
        y, si espera, retira resaltado y señala ``input_var`` con ``pause``;
        después delega estado visual y refresco a ``_stop_execution``.
        """
        if not self.is_running and not self.waiting_for_input:
            return
        self.sim.running = False
        self._step_over_target = None
        if self.waiting_for_input:
            self.waiting_for_input = False
            self.console.set_input_highlight(False)
            self.input_var.set("pause")
        self._stop_execution("Ejecución pausada por el usuario.")

    def _stop_execution(self, status_msg: str):
        """Detiene banderas y destino Next y restaura controles desde el bucle.

        También lo invocan Pause y Next. Retira espera/resaltado y refresca
        vistas antes del scroll, pero no señala ``input_var`` ni cancela
        llamadas ``after`` pendientes.

        Args:
            status_msg: Mensaje mostrado sin transformación en la barra.
        """
        self.is_running = False
        self.sim.running = False
        self._step_over_target = None
        if self.waiting_for_input:
            self.waiting_for_input = False
            self.console.set_input_highlight(False)
        self.btn_run.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_step.config(state=tk.NORMAL)
        self.btn_step_over.config(state=tk.NORMAL)
        self.lbl_cpu_state.config(text="PAUSADO", bg="#C62828")
        self.lbl_status.config(text=status_msg)
        self._update_all_views()
        self.disassembly.scroll_to_pc()

    def _on_step(self):
        """Ejecuta Step desde menú/F11/toolbar tras solicitar pausa.

        Fuerza ``sim.running=True`` antes de ``step``, sin activar
        ``is_running``; refresca y desplaza, sin detener de nuevo la CPU.
        """
        self._on_pause()
        self.sim.running = True
        self.sim.step()
        self._update_all_views()
        self.disassembly.scroll_to_pc()
        self.lbl_status.config(
            text=f"Paso ejecutado. Próxima instrucción en x{self.sim.pc:04X}."
        )

    def _on_step_over(self):
        """Ejecuta Next por menú/F12/toolbar, conservando breakpoints.

        Tras pausar lee instrucción mediante ``mem_read``. Para JSR/JSRR o
        TRAP distinto de HALT activa CPU e intenta hasta 200 pasos hacia PC+1;
        respeta BP y espera. Si no acaba, guarda destino y continúa mediante
        ``_run_loop``. Para otra instrucción llama ``step`` sin forzar
        ``sim.running=True``, a diferencia de Step. Refresca o detiene según
        la rama; no captura errores ni cancela temporizadores anteriores.
        """
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

            if (
                self.sim.pc == ret_addr
                or not self.sim.running
                or self.sim.pc in self.breakpoints
            ):
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
            self.disassembly.scroll_to_pc()
            self.lbl_status.config(
                text=f"Paso ejecutado. Próxima instrucción en x{self.sim.pc:04X}."
            )

    def _on_reset(self):
        """Reinicia por menú/Ctrl+R/toolbar a ``orig_pc`` mediante la máquina.

        Pausa primero, limpia destino y FIFO y restablece base/vistas.
        Señala ``reset`` sólo si aún figura una espera después de Pause;
        normalmente Pause ya la limpió y señaló ``pause``. La política de
        memoria y SO corresponde a ``sim.reset``, no a los widgets.
        """
        self._on_pause()
        self._step_over_target = None
        if self.waiting_for_input:
            self.waiting_for_input = False
            self.console.set_input_highlight(False)
            self.input_var.set("reset")
        self.input_buffer.clear()
        self.disassembly.base_addr = self.orig_pc
        self.sim.reset(self.orig_pc)
        self._update_all_views()
        self.disassembly.scroll_to_pc()
        self.lbl_cpu_state.config(text="LISTO", bg="#2E7D32")
        self.lbl_status.config(text=f"Simulador reiniciado. PC = x{self.orig_pc:04X}.")

    def _on_close(self):
        """Atiende WM_DELETE_WINDOW registrado en el constructor.

        Detiene ambas banderas, señala ``close`` si espera y destruye raíz;
        no cancela explícitamente ``after`` ni captura errores de Tk.
        El comando Salir del menú está enlazado a ``quit``, no a este método.
        """
        self.is_running = False
        self.sim.running = False
        if self.waiting_for_input:
            self.input_var.set("close")
        self.destroy()

    # =========================================================================
    # BREAKPOINTS Y EDICIÓN RÁPIDA
    # =========================================================================

    def _on_clear_breakpoints(self):
        """Vacía BP por el menú Simulación y refresca antes del aviso."""
        self.breakpoints.clear()
        self.disassembly.refresh()
        self.disassembly.scroll_to_pc()
        messagebox.showinfo(
            "Breakpoints", "Todos los puntos de interrupción han sido eliminados."
        )

    # =========================================================================
    # DIÁLOGOS DE AYUDA Y ACERCA DE
    # =========================================================================

    def _show_isa_help(self):
        """Abre referencia de sólo lectura por el comando Ayuda del menú."""
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
        """Muestra identificación del programa por Acerca de del menú Ayuda."""
        msg = (
            "Simulador y Ensamblador Pedagógico LC-3\n"
            "Arquitectura Little Computer 3 (Patt & Patel)\n\n"
            "Desarrollado en Python 3 puro con interfaz gráfica Tkinter.\n"
            "Laboratorio 3 - Arquitectura de Computadoras."
        )
        messagebox.showinfo("Acerca del Simulador LC-3", msg)
