#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <cstdint>
#include <array>
#include <unordered_map>
#include <vector>

using namespace std;

constexpr uint32_t MEMORY_SIZE = 65536;
constexpr uint16_t PC_START = 0x3000;

// Registers
enum {
    R_R0 = 0,
    R_R1,
    R_R2,
    R_R3,
    R_R4,
    R_R5,
    R_R6,
    R_R7,
    R_PC,  // Program Counter
    R_COND, // Condition Flag
    R_COUNT // Total number of registers
};

// Condition flags
enum {
    FL_POS = 1 << 0,
    FL_ZRO = 1 << 1,
    FL_NEG = 1 << 2
};

// Opcodes
enum {
    OP_BR = 0,
    OP_ADD,
    OP_LD,
    OP_ST,
    OP_JSR,
    OP_AND,
    OP_LDR,
    OP_STR,
    OP_RTI,
    OP_NOT,
    OP_LDI,
    OP_STI,
    OP_JMP,
    OP_RES,
    OP_LEA,
    OP_TRAP
};

array<uint16_t, MEMORY_SIZE> memory;
array<uint16_t, R_COUNT> reg;
int instructionCount = 0;

unordered_map<string, uint16_t> labelTable;

void updateFlags(uint16_t r) {
    if (reg[r] == 0) {
        reg[R_COND] = FL_ZRO;
    } else if (reg[r] >> 15) {
        reg[R_COND] = FL_NEG;
    } else {
        reg[R_COND] = FL_POS;
    }
}

uint16_t signExtend(uint16_t x, int bitCount) {
    if ((x >> (bitCount - 1)) & 1) {
        x |= (0xFFFF << bitCount);
    }
    return x;
}

void executeInstruction() {
    bool running = true;
    while (running) {
        uint16_t instr = memory[reg[R_PC]++];
        uint16_t op = instr >> 12;
        instructionCount++;

        switch (op) {
            case OP_ADD: {
                uint16_t r0 = (instr >> 9) & 0x7;
                uint16_t r1 = (instr >> 6) & 0x7;
                uint16_t immFlag = (instr >> 5) & 0x1;

                if (immFlag) {
                    uint16_t imm5 = signExtend(instr & 0x1F, 5);
                    reg[r0] = reg[r1] + imm5;
                } else {
                    uint16_t r2 = instr & 0x7;
                    reg[r0] = reg[r1] + reg[r2];
                }
                updateFlags(r0);
                break;
            }
            case OP_AND: {
                uint16_t r0 = (instr >> 9) & 0x7;
                uint16_t r1 = (instr >> 6) & 0x7;
                uint16_t immFlag = (instr >> 5) & 0x1;

                if (immFlag) {
                    uint16_t imm5 = signExtend(instr & 0x1F, 5);
                    reg[r0] = reg[r1] & imm5;
                } else {
                    uint16_t r2 = instr & 0x7;
                    reg[r0] = reg[r1] & reg[r2];
                }
                updateFlags(r0);
                break;
            }
            case OP_NOT: {
                uint16_t r0 = (instr >> 9) & 0x7;
                uint16_t r1 = (instr >> 6) & 0x7;
                reg[r0] = ~reg[r1];
                updateFlags(r0);
                break;
            }
            case OP_BR: {
                uint16_t pcOffset = signExtend(instr & 0x1FF, 9);
                uint16_t condFlag = (instr >> 9) & 0x7;

                if (condFlag & reg[R_COND]) {
                    reg[R_PC] += pcOffset;
                }
                break;
            }
            case OP_JMP: {
                uint16_t r1 = (instr >> 6) & 0x7;
                reg[R_PC] = reg[r1];
                break;
            }
            case OP_LD: {
                uint16_t r0 = (instr >> 9) & 0x7;
                uint16_t pcOffset = signExtend(instr & 0x1FF, 9);
                reg[r0] = memory[reg[R_PC] + pcOffset];
                updateFlags(r0);
                break;
            }
            case OP_ST: {
                uint16_t r0 = (instr >> 9) & 0x7;
                uint16_t pcOffset = signExtend(instr & 0x1FF, 9);
                memory[reg[R_PC] + pcOffset] = reg[r0];
                break;
            }
            case OP_TRAP: {
                running = false;
                break;
            }
            default: {
                cout << "Unknown instruction" << endl;
                running = false;
                break;
            }
        }
    }
}

bool loadProgram(const string& filename) {
    ifstream file(filename);
    if (!file) {
        cerr << "Error: Could not open file " << filename << endl;
        return false;
    }

    string line;
    uint16_t address = PC_START;

    while (getline(file, line)) {
        if (line.empty() || line[0] == '#') {
            continue;
        }

        stringstream ss;
        ss << hex << line;
        uint16_t instruction;
        ss >> instruction;

        if (address < MEMORY_SIZE) {
            memory[address++] = instruction;
        } else {
            cerr << "Error: Memory overflow, program too large" << endl;
            return false;
        }
    }

    file.close();
    return true;
}

uint16_t assembleInstruction(const string& opcode, const vector<string>& operands) {
    // Implement assembly parsing logic for each opcode
    // For simplicity, only example cases shown

    if (opcode == "ADD") {
        uint16_t r0 = stoi(operands[0].substr(1)); // parse "R0" as 0, "R1" as 1, etc.
        uint16_t r1 = stoi(operands[1].substr(1));
        uint16_t r2 = stoi(operands[2].substr(1));
        return (OP_ADD << 12) | (r0 << 9) | (r1 << 6) | r2;
    }
    // Add more opcode handling here as needed
    return 0;
}

bool parseAndAssemble(const string& filename) {
    ifstream file(filename);
    if (!file) {
        cerr << "Error: Could not open file " << filename << endl;
        return false;
    }

    string line;
    uint16_t address = PC_START;
    while (getline(file, line)) {
        if (line.empty() || line[0] == '#') {
            continue;
        }

        stringstream ss(line);
        string opcode;
        vector<string> operands;

        ss >> opcode;
        string operand;
        while (ss >> operand) {
            operands.push_back(operand);
        }

        uint16_t instruction = assembleInstruction(opcode, operands);
        if (address < MEMORY_SIZE) {
            memory[address++] = instruction;
        } else {
            cerr << "Error: Memory overflow, program too large" << endl;
            return false;
        }
    }

    file.close();
    return true;
}

void printRegisters() {
    cout << "Registers after execution:" << endl;
    for (int i = 0; i < R_COUNT; ++i) {
        switch (i) {
            case R_PC:
                cout << "PC   : " << hex << reg[R_PC] << " (hex), " << dec << static_cast<int16_t>(reg[R_PC]) << " (signed)" << endl;
                break;
            case R_COND:
                cout << "COND : " << hex << reg[R_COND] << " (hex)" << endl;
                break;
            default:
                cout << "R" << i << "   : " << hex << reg[i] << " (hex), " << dec << static_cast<int16_t>(reg[i]) << " (signed)" << endl;
                break;
        }
    }
    cout << dec;
}

int main() {
    reg[R_PC] = PC_START;

    string filename;
    cout << "Enter the filename of the LC-3 program (with .txt or .asm extension): ";
    cin >> filename;

    if (filename.substr(filename.find_last_of(".") + 1) == "txt") {
        if (!loadProgram(filename)) {
            cerr << "Failed to load the program. Exiting..." << endl;
            return 1;
        }
    } else if (filename.substr(filename.find_last_of(".") + 1) == "asm") {
        if (!parseAndAssemble(filename)) {
            cerr << "Failed to assemble the program. Exiting..." << endl;
            return 1;
        }
    } else {
        cerr << "Unsupported file type. Exiting..." << endl;
        return 1;
    }

    executeInstruction();
    printRegisters();
    cout << "Total number of executed instructions: " << instructionCount << endl;

    return 0;
}

