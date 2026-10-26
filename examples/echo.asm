; ====================================================================
; echo.asm - Eco de teclado interactivo en LC-3
; Lee caracteres ingresados y los repite en pantalla hasta ingresar 'q'
; Demuestra TRAP IN (x23), TRAP OUT (x21) y comparación de caracteres
; CLI o GUI comienzan en x3000; IN/PUTS/OUT delegan E/S al SO y MMIO.
; ECHO_LOOP consume una tecla por vuelta y modifica R0-R2/CC; no es subrutina.
; EXIT_ECHO recibe la comparación igual a 'q', imprime despedida y ejecuta HALT.
; ====================================================================

        .ORIG   x3000

        LEA     R0, WELCOME_MSG
        PUTS

ECHO_LOOP
        IN                      ; Pide un carácter, lo muestra y lo guarda en R0

        ; Comparar con 'q' (ASCII 113)
        ; Para comparar R0 == 'q', restamos ASCII('q') sumando su complemento a dos
        LD      R1, NEG_Q
        ADD     R2, R0, R1      ; R2 = R0 - 'q'
        BRz     EXIT_ECHO       ; Si la resta es cero, el usuario ingresó 'q'

        ; Imprimir mensaje de eco
        ST      R0, CHAR_BUF    ; Guardar carácter
        LEA     R0, ECHO_MSG
        PUTS
        LD      R0, CHAR_BUF
        OUT
        LD      R0, NEWLINE
        OUT

        BRnzp   ECHO_LOOP

EXIT_ECHO
        LEA     R0, BYE_MSG
        PUTS
        HALT

; Datos
; Mensajes/constantes pertenecen al programa; CHAR_BUF conserva la tecla de
; una vuelta mientras PUTS usa R0 como puntero. 'q' no pasa por ese eco adicional.
WELCOME_MSG .STRINGZ "Programa Eco LC-3. Ingresa un caracter (presiona 'q' para salir):\n"
ECHO_MSG    .STRINGZ "\n -> Has ingresado: "
BYE_MSG     .STRINGZ "\nAdios!\n"
NEG_Q       .FILL   #-113       ; Complemento a dos de 'q' (113)
NEWLINE     .FILL   #10
CHAR_BUF    .BLKW   #1

        .END
