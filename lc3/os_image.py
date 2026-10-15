"""
lc3_os.py - Sistema Operativo y Rutinas de Servicio TRAP para la arquitectura LC-3.
Implementa la Tabla de Vectores de Trap y el código assembly real del SO en memoria,
emulando el sondeo (polling) sobre registros MMIO (KBSR, KBDR, DSR, DDR, MCR).
"""

from typing import Dict, Tuple, List
from .core import (
    TRAP_GETC, TRAP_OUT, TRAP_PUTS, TRAP_IN, TRAP_PUTSP, TRAP_HALT,
    MR_KBSR, MR_KBDR, MR_DSR, MR_DDR, MR_MCR
)
from .assembler import LC3Assembler

# Direcciones base de las rutinas de servicio del Sistema Operativo en memoria
OS_START_ADDR = 0x0200

# Código fuente en ensamblador del Sistema Operativo LC-3
LC3_OS_ASM = """
        .ORIG   x0200

; ====================================================================
; TRAP x20: GETC_HANDLER
; Lee un carácter del teclado sondeando KBSR (xFE00) hasta que haya tecla lista.
; Retorna el código ASCII en R0[7:0]. No hace eco en pantalla.
; ====================================================================
GETC_HANDLER
        LDI     R0, OS_KBSR_PTR     ; Leer registro de estado del teclado
        BRzp    GETC_HANDLER        ; Si bit 15 es 0 (no hay tecla), seguir sondeando
        LDI     R0, OS_KBDR_PTR     ; Leer carácter de datos del teclado
        RET

OS_KBSR_PTR     .FILL   xFE00
OS_KBDR_PTR     .FILL   xFE02


; ====================================================================
; TRAP x21: OUT_HANDLER
; Sondea DSR (xFE04) hasta que la pantalla esté lista y escribe R0[7:0] en DDR (xFE06).
; ====================================================================
OUT_HANDLER
        ST      R1, OUT_SAVED_R1    ; Preservar R1
OUT_POLL
        LDI     R1, OS_DSR_PTR      ; Leer registro de estado de pantalla
        BRzp    OUT_POLL            ; Si bit 15 es 0 (ocupado), seguir sondeando
        STI     R0, OS_DDR_PTR      ; Escribir carácter en registro de datos de pantalla
        LD      R1, OUT_SAVED_R1    ; Restaurar R1
        RET

OS_DSR_PTR      .FILL   xFE04
OS_DDR_PTR      .FILL   xFE06
OUT_SAVED_R1    .FILL   x0000


; ====================================================================
; TRAP x22: PUTS_HANDLER
; Imprime una cadena terminada en nulo (x0000) apuntada por R0.
; Sondea DSR para cada carácter y lo envía a DDR.
; ====================================================================
PUTS_HANDLER
        ST      R0, PUTS_SAVED_R0   ; Preservar registros
        ST      R1, PUTS_SAVED_R1
        ST      R2, PUTS_SAVED_R2
        ADD     R1, R0, #0          ; R1 = puntero a la cadena

PUTS_CHAR_LOOP
        LDR     R0, R1, #0          ; R0 = carácter actual mem[R1]
        BRz     PUTS_FINISHED       ; Si es carácter nulo (0), terminar

PUTS_POLL_DSR
        LDI     R2, OS_DSR_PTR_P    ; Sondeo de DSR
        BRzp    PUTS_POLL_DSR
        STI     R0, OS_DDR_PTR_P    ; Escribir carácter a pantalla
        ADD     R1, R1, #1          ; Avanzar puntero al siguiente carácter
        BRnzp   PUTS_CHAR_LOOP

PUTS_FINISHED
        LD      R0, PUTS_SAVED_R0   ; Restaurar registros
        LD      R1, PUTS_SAVED_R1
        LD      R2, PUTS_SAVED_R2
        RET

OS_DSR_PTR_P    .FILL   xFE04
OS_DDR_PTR_P    .FILL   xFE06
PUTS_SAVED_R0   .FILL   x0000
PUTS_SAVED_R1   .FILL   x0000
PUTS_SAVED_R2   .FILL   x0000


; ====================================================================
; TRAP x23: IN_HANDLER
; Muestra un mensaje en pantalla solicitando un carácter, sondea el teclado,
; hace eco del carácter en pantalla y lo retorna en R0.
; ====================================================================
IN_HANDLER
        ST      R7, IN_SAVED_R7     ; Preservar R7 (dirección de retorno del usuario)
        ST      R1, IN_SAVED_R1
        LEA     R0, IN_PROMPT_MSG   ; Cargar mensaje de solicitud
        JSR     PUTS_HANDLER        ; Mostrar aviso utilizando la rutina de PUTS

IN_WAIT_KEY
        LDI     R0, OS_KBSR_PTR_I   ; Sondeo de teclado
        BRzp    IN_WAIT_KEY
        LDI     R0, OS_KBDR_PTR_I   ; Leer carácter ingresado

        JSR     OUT_HANDLER         ; Hacer eco del carácter en pantalla

        LD      R1, IN_SAVED_R1     ; Restaurar registros
        LD      R7, IN_SAVED_R7
        RET

OS_KBSR_PTR_I   .FILL   xFE00
OS_KBDR_PTR_I   .FILL   xFE02
IN_SAVED_R7     .FILL   x0000
IN_SAVED_R1     .FILL   x0000
IN_PROMPT_MSG   .STRINGZ "Input a character: "


; ====================================================================
; TRAP x24: PUTSP_HANDLER
; Imprime una cadena empaquetada (2 caracteres por palabra de memoria).
; ====================================================================
PUTSP_HANDLER
        ST      R0, PUTSP_SAVED_R0
        ST      R1, PUTSP_SAVED_R1
        ST      R2, PUTSP_SAVED_R2
        ST      R3, PUTSP_SAVED_R3
        ST      R4, PUTSP_SAVED_R4
        ADD     R1, R0, #0          ; R1 = puntero a cadena

PUTSP_LOOP
        LDR     R2, R1, #0          ; R2 = palabra con 2 caracteres
        BRz     PUTSP_DONE          ; Si la palabra es 0, fin de cadena

        ; Extraer y enviar primer carácter (bits [7:0])
        LD      R3, OS_MASK_00FF
        AND     R0, R2, R3
        BRz     PUTSP_DONE
PUTSP_POLL1
        LDI     R3, OS_DSR_PTR_SP
        BRzp    PUTSP_POLL1
        STI     R0, OS_DDR_PTR_SP

        ; Extraer y enviar segundo carácter (bits [15:8])
        ; Desplazar los 8 bits superiores hacia la derecha usando rotación de signo
        AND     R0, R0, #0          ; R0 acumulará el carácter superior
        AND     R3, R3, #0
        ADD     R3, R3, #8          ; R3 = contador de 8 bits
PUTSP_SHIFT_LOOP
        ADD     R0, R0, R0          ; R0 = R0 << 1
        ADD     R2, R2, #0          ; Comprobar bit de signo de R2
        BRzp    PUTSP_SHIFT_NO_BIT
        ADD     R0, R0, #1          ; Bit 15 era 1, sumarlo a R0
PUTSP_SHIFT_NO_BIT
        ADD     R2, R2, R2          ; R2 = R2 << 1 (siguiente bit a posición de signo)
        ADD     R3, R3, #-1
        BRp     PUTSP_SHIFT_LOOP

        ; Si el segundo carácter es nulo (0), no imprimirlo y terminar
        ADD     R0, R0, #0
        BRz     PUTSP_DONE

PUTSP_POLL2
        LDI     R3, OS_DSR_PTR_SP
        BRzp    PUTSP_POLL2
        STI     R0, OS_DDR_PTR_SP

        ADD     R1, R1, #1          ; Avanzar al siguiente par de caracteres
        BRnzp   PUTSP_LOOP

PUTSP_DONE
        LD      R0, PUTSP_SAVED_R0
        LD      R1, PUTSP_SAVED_R1
        LD      R2, PUTSP_SAVED_R2
        LD      R3, PUTSP_SAVED_R3
        LD      R4, PUTSP_SAVED_R4
        RET

OS_DSR_PTR_SP   .FILL   xFE04
OS_DDR_PTR_SP   .FILL   xFE06
OS_MASK_00FF    .FILL   x00FF
PUTSP_SAVED_R0  .FILL   x0000
PUTSP_SAVED_R1  .FILL   x0000
PUTSP_SAVED_R2  .FILL   x0000
PUTSP_SAVED_R3  .FILL   x0000
PUTSP_SAVED_R4  .FILL   x0000


; ====================================================================
; TRAP x25: HALT_HANDLER
; Imprime el mensaje de parada y desactiva el bit 15 del registro MCR (xFFFE)
; lo que detiene el reloj del procesador.
; ====================================================================
HALT_HANDLER
        ST      R7, HALT_SAVED_R7
        ST      R0, HALT_SAVED_R0
        ST      R1, HALT_SAVED_R1

        LEA     R0, HALT_MSG_TEXT   ; Mostrar mensaje de procesador detenido
        JSR     PUTS_HANDLER

        ; Modificar Machine Control Register (MCR) en xFFFE: limpiar bit 15
        LDI     R0, OS_MCR_PTR
        LD      R1, MCR_CLOCK_MASK  ; x7FFF (bit 15 en 0)
        AND     R0, R0, R1
        STI     R0, OS_MCR_PTR      ; Desactivar reloj (detiene la simulación)

        LD      R0, HALT_SAVED_R0
        LD      R1, HALT_SAVED_R1
        LD      R7, HALT_SAVED_R7
        RET

OS_MCR_PTR      .FILL   xFFFE
MCR_CLOCK_MASK  .FILL   x7FFF
HALT_SAVED_R7   .FILL   x0000
HALT_SAVED_R0   .FILL   x0000
HALT_SAVED_R1   .FILL   x0000
HALT_MSG_TEXT   .STRINGZ "\\n*** HALT: Procesador detenido por instruccion TRAP x25 (SO LC-3) ***\\n"

        .END
"""

# Caché para la imagen del Sistema Operativo
_CACHED_OS_IMAGE = None
_CACHED_OS_SYMBOLS = None


def get_os_image() -> Tuple[Dict[int, int], Dict[int, str]]:
    """
    Ensambla y compila el Sistema Operativo LC-3.
    Retorna:
      (memory_map, symbol_map)
      donde memory_map es {direccion: palabra_16bit} y symbol_map es {direccion: etiqueta}.
    """
    global _CACHED_OS_IMAGE, _CACHED_OS_SYMBOLS
    if _CACHED_OS_IMAGE is not None:
        return _CACHED_OS_IMAGE.copy(), _CACHED_OS_SYMBOLS.copy()

    assembler = LC3Assembler()
    orig, words, symbols = assembler.assemble(LC3_OS_ASM)

    memory_map: Dict[int, int] = {}

    # 1. Cargar las palabras de código del SO en memoria
    for i, word in enumerate(words):
        memory_map[orig + i] = word

    # 2. Configurar la Tabla de Vectores de Trap (Trap Vector Table: x0000 - x00FF)
    # Específicamente los vectores x20 a x25 apuntando a sus manejadores correspondientes
    vector_table = {
        TRAP_GETC:  symbols["GETC_HANDLER"],
        TRAP_OUT:   symbols["OUT_HANDLER"],
        TRAP_PUTS:  symbols["PUTS_HANDLER"],
        TRAP_IN:    symbols["IN_HANDLER"],
        TRAP_PUTSP: symbols["PUTSP_HANDLER"],
        TRAP_HALT:  symbols["HALT_HANDLER"],
    }

    for vect, handler_addr in vector_table.items():
        memory_map[vect] = handler_addr

    # Mapeo invertido de símbolos {direccion: nombre}
    symbol_map = {addr: name for name, addr in symbols.items()}
    symbol_map[TRAP_GETC]  = "VEC_GETC (x20)"
    symbol_map[TRAP_OUT]   = "VEC_OUT (x21)"
    symbol_map[TRAP_PUTS]  = "VEC_PUTS (x22)"
    symbol_map[TRAP_IN]    = "VEC_IN (x23)"
    symbol_map[TRAP_PUTSP] = "VEC_PUTSP (x24)"
    symbol_map[TRAP_HALT]  = "VEC_HALT (x25)"

    _CACHED_OS_IMAGE = memory_map
    _CACHED_OS_SYMBOLS = symbol_map
    return memory_map.copy(), symbol_map.copy()
