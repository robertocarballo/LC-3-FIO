; ====================================================================
; mult.asm - Multiplicación de dos números por sumas sucesivas en LC-3
; Calcula RESULT = NUM1 * NUM2
; R1 = NUM1 (multiplicando)
; R2 = NUM2 (multiplicador / contador de ciclo)
; R3 = Acumulador del producto
; CLI, GUI y pruebas comienzan en x3000; no hay retorno de subrutina.
; LOOP decrementa R2 hasta cero (el ejemplo usa 7); no valida signo/rango.
; DONE publica el acumulador de 16 bits en RESULT antes de PUTS y HALT.
; ====================================================================

        .ORIG   x3000

        ; Inicializar registros
        LD      R1, NUM1        ; Cargar multiplicando (6)
        LD      R2, NUM2        ; Cargar multiplicador (7)
        AND     R3, R3, #0      ; R3 = 0 (acumulador)

        ; Verificar si el multiplicador es cero
LOOP    ADD     R2, R2, #0      ; Actualizar flags con R2
        BRz     DONE            ; Si R2 == 0, terminar

        ; Acumular R1 en R3
        ADD     R3, R3, R1      ; R3 = R3 + R1
        ADD     R2, R2, #-1     ; R2 = R2 - 1
        BRnzp   LOOP            ; Repetir ciclo

        ; Guardar resultado en memoria
DONE    ST      R3, RESULT

        ; Imprimir mensaje de éxito
        LEA     R0, MSG
        PUTS

        HALT

; Datos
; NUM1/NUM2 son entradas propias; RESULT es la salida persistente en memoria.
; MSG sólo anuncia finalización: el programa no convierte ni imprime el producto.
NUM1    .FILL   #6
NUM2    .FILL   #7
RESULT  .BLKW   #1
MSG     .STRINGZ "Multiplicacion completada. Resultado guardado en RESULT.\n"

        .END
