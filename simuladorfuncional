from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import TextIO


MEMORY_SIZE = 1 << 16
MASK_16 = 0xFFFF
N_FLAG = 0b100
Z_FLAG = 0b010
P_FLAG = 0b001


class SimulatorError(ValueError):
    """Error loading or executing an LC-3 object program."""


def sign_extend(value: int, bit_count: int) -> int:
    sign_bit = 1 << (bit_count - 1)
    return value - (1 << bit_count) if value & sign_bit else value


class LC3:
    def __init__(self, input_stream: TextIO | None = None, output_stream: TextIO | None = None):
        self.memory = [0] * MEMORY_SIZE
        self.registers = [0] * 8
        self.pc = 0
        self.cc = Z_FLAG
        self.psr = Z_FLAG
        self.halted = False
        self.steps = 0
        self.input_stream = input_stream if input_stream is not None else sys.stdin
        self.output_stream = output_stream if output_stream is not None else sys.stdout

    def load_object(self, obj: bytes) -> int:
        if len(obj) % 2:
            raise SimulatorError("El archivo .obj tiene un número impar de bytes.")
        if len(obj) < 4:
            raise SimulatorError("El archivo .obj debe incluir origen y al menos una palabra.")

        words = [
            int.from_bytes(obj[index:index + 2], byteorder="big")
            for index in range(0, len(obj), 2)
        ]
        origin = words[0]
        program_size = len(words) - 1
        if origin + program_size > MEMORY_SIZE:
            raise SimulatorError("El programa .obj excede el espacio de memoria LC-3.")

        self.memory[origin:origin + program_size] = words[1:]
        self.pc = origin
        return origin

    def load_object_file(self, path: str | Path) -> int:
        try:
            obj = Path(path).read_bytes()
        except OSError as exc:
            raise SimulatorError(f"No se pudo leer el archivo .obj: {exc}") from exc
        return self.load_object(obj)

    def run(self, max_steps: int = 1_000_000) -> int:
        if max_steps < 1:
            raise SimulatorError("El límite de instrucciones debe ser mayor que cero.")
        start_steps = self.steps
        while not self.halted and self.steps - start_steps < max_steps:
            self.step()
        if not self.halted:
            raise SimulatorError(f"Se alcanzó el límite de {max_steps} instrucciones.")
        return self.steps - start_steps

    def step(self) -> None:
        instruction_address = self.pc
        instruction = self.memory[self.pc]
        self.pc = (self.pc + 1) & MASK_16
        opcode = instruction >> 12

        if opcode == 0x0:
            condition = (instruction >> 9) & 0x7
            if condition & self.cc:
                self.pc = (self.pc + sign_extend(instruction & 0x1FF, 9)) & MASK_16
        elif opcode == 0x1:
            dr, sr1 = (instruction >> 9) & 0x7, (instruction >> 6) & 0x7
            operand = (
                sign_extend(instruction & 0x1F, 5)
                if instruction & 0x20
                else self.registers[instruction & 0x7]
            )
            self._write_register(dr, self.registers[sr1] + operand)
        elif opcode == 0x2:
            dr = (instruction >> 9) & 0x7
            address = (self.pc + sign_extend(instruction & 0x1FF, 9)) & MASK_16
            self._write_register(dr, self.memory[address])
        elif opcode == 0x3:
            sr = (instruction >> 9) & 0x7
            address = (self.pc + sign_extend(instruction & 0x1FF, 9)) & MASK_16
            self.memory[address] = self.registers[sr]
        elif opcode == 0x4:
            self.registers[7] = self.pc
            if instruction & 0x800:
                self.pc = (self.pc + sign_extend(instruction & 0x7FF, 11)) & MASK_16
            else:
                base = (instruction >> 6) & 0x7
                self.pc = self.registers[base]
        elif opcode == 0x5:
            dr, sr1 = (instruction >> 9) & 0x7, (instruction >> 6) & 0x7
            operand = (
                sign_extend(instruction & 0x1F, 5)
                if instruction & 0x20
                else self.registers[instruction & 0x7]
            )
            self._write_register(dr, self.registers[sr1] & operand)
        elif opcode == 0x6:
            dr, base = (instruction >> 9) & 0x7, (instruction >> 6) & 0x7
            address = (self.registers[base] + sign_extend(instruction & 0x3F, 6)) & MASK_16
            self._write_register(dr, self.memory[address])
        elif opcode == 0x7:
            sr, base = (instruction >> 9) & 0x7, (instruction >> 6) & 0x7
            address = (self.registers[base] + sign_extend(instruction & 0x3F, 6)) & MASK_16
            self.memory[address] = self.registers[sr]
        elif opcode == 0x8:
            self._return_from_interrupt(instruction_address)
        elif opcode == 0x9:
            dr, sr = (instruction >> 9) & 0x7, (instruction >> 6) & 0x7
            self._write_register(dr, ~self.registers[sr])
        elif opcode == 0xA:
            dr = (instruction >> 9) & 0x7
            pointer_address = (self.pc + sign_extend(instruction & 0x1FF, 9)) & MASK_16
            self._write_register(dr, self.memory[self.memory[pointer_address]])
        elif opcode == 0xB:
            sr = (instruction >> 9) & 0x7
            pointer_address = (self.pc + sign_extend(instruction & 0x1FF, 9)) & MASK_16
            self.memory[self.memory[pointer_address]] = self.registers[sr]
        elif opcode == 0xC:
            base = (instruction >> 6) & 0x7
            self.pc = self.registers[base]
        elif opcode == 0xD:
            raise SimulatorError(
                f"Opcode reservado xD en x{instruction_address:04X}."
            )
        elif opcode == 0xE:
            dr = (instruction >> 9) & 0x7
            address = (self.pc + sign_extend(instruction & 0x1FF, 9)) & MASK_16
            self._write_register(dr, address)
        elif opcode == 0xF:
            self.registers[7] = self.pc
            self._execute_trap(instruction & 0xFF)

        self.steps += 1

    def _write_register(self, register: int, value: int) -> None:
        value &= MASK_16
        self.registers[register] = value
        self._set_condition_codes(value)

    def _set_condition_codes(self, value: int) -> None:
        signed = sign_extend(value, 16)
        self.cc = N_FLAG if signed < 0 else Z_FLAG if signed == 0 else P_FLAG
        self.psr = (self.psr & ~0x7) | self.cc

    def _return_from_interrupt(self, instruction_address: int) -> None:
        stack_pointer = self.registers[6]
        if stack_pointer + 1 >= MEMORY_SIZE:
            raise SimulatorError(
                f"Pila inválida para RTI en x{instruction_address:04X}."
            )
        self.pc = self.memory[stack_pointer]
        self.psr = self.memory[stack_pointer + 1]
        self.cc = self.psr & 0x7
        self.registers[6] = (stack_pointer + 2) & MASK_16

    def _read_character(self) -> int:
        if (
            sys.platform == "win32"
            and self.input_stream is sys.stdin
            and sys.stdin.isatty()
        ):
            import msvcrt

            while True:
                character = msvcrt.getwch()
                if character not in ("\x00", "\xe0"):
                    break
                msvcrt.getwch()
        else:
            character = self.input_stream.read(1)
        if character == "":
            raise SimulatorError("No hay más caracteres disponibles en la entrada.")
        if character == "\r":
            character = "\n"
        return ord(character) & 0xFF

    def _write_text(self, text: str) -> None:
        self.output_stream.write(text)
        self.output_stream.flush()

    def _write_character(self, value: int) -> None:
        self._write_text(chr(value & 0xFF))

    def _read_string(self, address: int, packed: bool = False) -> None:
        for _ in range(MEMORY_SIZE):
            word = self.memory[address]
            if word == 0:
                return
            self._write_character(word)
            if packed:
                high_byte = word >> 8
                if high_byte:
                    self._write_character(high_byte)
            address = (address + 1) & MASK_16
        raise SimulatorError("La cadena TRAP no tiene terminador nulo en memoria.")

    def _halt(self) -> None:
        self._write_text("\nHALT\n")
        self.halted = True

    def _execute_trap(self, vector: int) -> None:
        if vector == 0x20:
            self.registers[0] = self._read_character()
            self._set_condition_codes(self.registers[1])
        elif vector == 0x21:
            self._write_character(self.registers[0])
            self._set_condition_codes(self.registers[1])
        elif vector == 0x22:
            self._read_string(self.registers[0])
            self._set_condition_codes(self.registers[1])
        elif vector == 0x23:
            self._write_text("Enter a character: ")
            self.registers[0] = self._read_character()
            self._write_character(self.registers[0])
            self._set_condition_codes(self.registers[1])
        elif vector == 0x24:
            self._read_string(self.registers[0], packed=True)
            self._set_condition_codes(self.registers[4])
        elif vector == 0x25:
            self._halt()
        else:
            self._write_text("LC-3 exception")
            self._halt()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulador funcional LC-3 para archivos .obj")
    parser.add_argument("object_file", help="Archivo .obj generado por el ensamblador")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=1_000_000,
        help="Máximo de instrucciones antes de detener una ejecución sin HALT",
    )
    parser.add_argument(
        "--input",
        help="Texto de entrada para GETC/IN; si se omite, se lee de la terminal",
    )
    args = parser.parse_args(argv)

    input_stream = io.StringIO(args.input) if args.input is not None else sys.stdin
    simulator = LC3(input_stream=input_stream, output_stream=sys.stdout)
    try:
        simulator.load_object_file(args.object_file)
        simulator.run(args.max_steps)
    except (OSError, SimulatorError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
