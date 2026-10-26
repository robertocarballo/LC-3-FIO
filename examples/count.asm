; ====================================================================
; count.asm - Cuenta regresiva de '9' a '0' e imprime cada dígito
; Demuestra bucles, manipulación de código ASCII y llamadas OUT
; CLI o GUI inician en x3000; OUT delega la salida al SO/MMIO y HALT detiene.
; No retorna a un llamador: modifica R0-R2/CC y su slot SAVED_R0.
; ====================================================================

        .ORIG   x3000

        ; R1 = Contador de repeticiones (10 dígitos: del 9 al 0)
        AND     R1, R1, #0
        ADD     R1, R1, #10

        ; R0 = Carácter ASCII inicial ('9' = #57 o x39)
        LD      R0, CHAR_NINE

; PRINT_LOOP emite dígito y espacio, incluido el espacio posterior a '0'.
PRINT_LOOP
        OUT                     ; Imprime el carácter en R0

        ; Imprimir espacio entre números
        LD      R2, SPACE_CHAR
        ST      R0, SAVED_R0    ; Guardar R0 temporalmente
        ADD     R0, R2, #0
        OUT
        LD      R0, SAVED_R0    ; Restaurar R0

        ; Decrementar el carácter ('9' -> '8' -> ...)
        ADD     R0, R0, #-1

        ; Decrementar contador de ciclo
        ADD     R1, R1, #-1
        BRp     PRINT_LOOP      ; Repetir mientras R1 > 0

        ; Imprimir salto de línea final
        LD      R0, NEWLINE
        OUT

        HALT

; Constantes y variables
; SAVED_R0 pertenece al bucle: preserva el dígito mientras OUT recibe el espacio.
CHAR_NINE   .FILL   #57         ; ASCII de '9'
SPACE_CHAR  .FILL   #32         ; ASCII de ' '
NEWLINE     .FILL   #10         ; ASCII de '\n'
SAVED_R0    .BLKW   #1

        .END
