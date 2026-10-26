; ====================================================================
; hello.asm - Programa clásico "Hello, World!" para la arquitectura LC-3
; Utiliza el servicio TRAP x22 (PUTS) y TRAP x25 (HALT)
; CLI, GUI o pruebas cargan el programa y comienzan en x3000; no es subrutina.
; Entrega la salida al anfitrión mediante PUTS y termina mediante HALT, sin RET.
; R0 pasa el puntero; HELLO_MSG pertenece al programa y termina en palabra cero.
; ====================================================================

        .ORIG   x3000

        ; Cargar la dirección de la cadena en R0 (requerido por PUTS)
        LEA     R0, HELLO_MSG

        ; Llamada al sistema PUTS para imprimir la cadena
        PUTS

        ; Detener la ejecución
        HALT

; Datos del programa
HELLO_MSG .STRINGZ "Hello, World!\n"

        .END
