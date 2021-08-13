#!/usr/bin/python3

import sys
from llvm.core import *
import llvm
from getopt import getopt

debug = False
asm_output = False

def get_array_type(t):
    size = 1
    while isinstance(t, ArrayType):
        size *= t.count
        t = t.element
    return size, t

def get_struct_offset(t, index=None):
    return sum(get_size(tt)[0] for tt in t.elements[:index])

def get_size(t):
    if isinstance(t, ArrayType):
        return get_array_type(t)
    elif isinstance(t, StructType):
        return get_struct_offset(t), t
    elif isinstance(t, (IntegerType,PointerType)):
        return 1, t
    else:
        raise Exception('type not implemented: %s' % t)

class Value(int):
    __str__ = lambda self: '*' * self.depth + str(int(self)) + \
        ('d' if self.direct else '')
    @staticmethod
    def get_variable(inst, scope):
        t = inst.type
        if isinstance(t, PointerType):
            size, t = get_size(t.pointee)
            start_depth = 1
        else:
            size = 1
            start_depth = 0
        res = get_value(scope.alloc(size), t, size, start_depth)
        scope.vars[inst] = res
        return res

def Constant(x):
    res = Value(x)
    res.depth = 0
    return res
def Ref(x, direct=True):
    res = Value(x)
    res.depth = 1
    res.direct = direct
    return res

def get_value(value, t, size=1, start_depth=0):
    res = Value(value)
    res.depth = start_depth
    res.direct = True
    while isinstance(t, PointerType):
        res.depth += 1
        t = t.pointee
    return res

class BasicBlock(object):
    def __init__(self, basic_block, function):
        self.function = function
        self.vars = function.vars
        self.name = basic_block.name
        self.instructions = []
        self.exit = None
        self.redundant = len(basic_block.instructions) == 1 and \
            basic_block.instructions[0].opcode_name == 'br' and \
            len(basic_block.instructions[0].operands) == 1
        self.phi_inst = []
        for inst in basic_block.instructions:
            op = inst.opcode_name
            if op == 'alloca':
                self.alloca(inst)
            elif op == 'store':
                self.store(inst)
            elif op == 'load':
                self.load(inst)
            elif op == 'ret':
                self.ret(inst)
            elif op in ('add', 'mul'):
                self.binary(inst, op)
            elif op == 'getelementptr':
                self.getelementptr(inst)
            elif op == 'icmp':
                self.icmp(inst)
            elif op == 'ashr':
                self.ashr(inst)
            elif op == 'shl':
                self.shl(inst)
            elif op in ('zext', 'sext', 'bitcast', 'trunc'):
                self.zext(inst)
            elif op == 'br':
                self.br(inst)
            elif op == 'call':
                self.call(inst)
            elif op == 'sub':
                self.sub(inst)
            elif op == 'phi':
                self.phi(inst)
            elif op == 'and':
                self.and_(inst)
            else:
                raise Exception('not implemented: %s' % op)
    def __len__(self):
        return len(self.instructions)
    def get_var(self, inst):
        if inst not in self.vars:
            self.vars[inst] = Value.get_variable(inst, self)
        return self.vars[inst]
    def alloc(self, size):
        return self.function.alloc(size)
    def alloca(self, inst):
        return Value.get_variable(inst, self)
    def compute_constant_expr(self, expr):
        base = self.vars[expr.operands[0]]
        offset = 0
        t = expr.operands[0].type.pointee
        for index in expr.operands[1:-1]:
            offset += index.s_ext_value
            offset *= t.count
            t = t.element
        offset += expr.operands[-1].s_ext_value
        res = get_value(base + offset, t, start_depth=1)
        res.direct = True
        return res
    def store_direct(self, dest, src):
        if isinstance(src, ConstantInt):
            code = ('store_const', dest, src.s_ext_value, 0)
        elif src not in self.vars:
            if src.operands[0] in self.vars:
                code = ('store_const', dest, self.vars[src.operands[0]], 0)
            else:
                code = lambda: self.store_direct(dest, src)
        else:
            if self.vars[src].direct:
                code = ('store_const', dest, self.vars[src], 0)
            else:
                code = ('mov', dest, self.vars[src], 0)
            if debug:
                print(code, file=sys.stderr)
                print(dest, self.vars[src], file=sys.stderr)
                print(src, file=sys.stderr)
        return code
    def store(self, inst):
        if isinstance(inst.operands[1], ConstantExpr):
            dest = self.compute_constant_expr(inst.operands[1])
        else:
            dest = self.vars[inst.operands[1]]
        src = inst.operands[0]
        if dest.direct:
            code = self.store_direct(dest, src)
        else:
            if isinstance(src, ConstantInt):
                code = ('store_const_ind', 0, src.s_ext_value, dest)
            else:
                code = ('store', 0, self.vars[src], dest)
        self.instructions.append(code)
    def load(self, inst):
        if isinstance(inst.operands[0], ConstantExpr):
            src = self.compute_constant_expr(inst.operands[0])
            src.direct = False
            self.vars[inst] = src
        else:
            src = self.vars[inst.operands[0]]
            if src.direct:
                self.vars[inst] = Value(src)
                self.vars[inst].depth = src.depth
                self.vars[inst].direct = False
                # dest = self.alloca(inst)
                # code = ('mov', dest, src, 0)
                # self.instructions.append(code)
            else:
                dest = Value(self.alloc(1))
                dest.depth = src.depth - 1
                dest.direct = False
                self.vars[inst] = dest
                code = ('load', dest, 0, src)
                self.instructions.append(code)
    def binary(self, inst, op, operands=None):
        dest = Ref(self.alloc(1), False)
        self.vars[inst] = dest
        src = [None] * 2
        n_const = 0
        for i,operand in enumerate(operands or inst.operands):
            if isinstance(operand, ConstantInt):
                src[1] = src[0]
                src[0] = operand.s_ext_value
                n_const += 1
            elif isinstance(operand, Argument):
                src[i] = self.alloc(1)
                self.vars[operand] = src[i]
            elif operand.opcode_name == 'inttoptr':
                src[1] = src[0]
                src[0] = operand.operands[0].s_ext_value
                n_const += 1
            else:
                if operand in self.vars:
                    src[i] = self.vars[operand]
                else:
                    src[i] = self.vars[operand.operands[0]]
        if n_const == 1:
            if op in ('ult', 'ule') and src[0] >= 0:
                op += '_pos'
            op += '_const'
        elif n_const == 2:
            raise Exception('not implemented: two constants')
        code = (op, dest, src[0], src[1])
        self.instructions.append(code)
    def add(self, inst, operands=None):
        self.binary(inst, 'add', operands)
    def mul(self, inst):
        self.binary(inst, 'mul')
    def and_(self, inst):
        self.binary(inst, 'and_')
    def getelementptr(self, inst):
        base = self.vars[inst.operands[0]]
        offset = inst.operands[-1]
        t = inst.operands[0].type.pointee
        if isinstance(t, ArrayType):
            step = get_array_type(t.element)[0]
        else:
            step = 1
        if isinstance(offset, ConstantInt):
            if isinstance(t, StructType):
                abs_offset = get_struct_offset(t, offset.s_ext_value)
            else:
                abs_offset = step * offset.s_ext_value
            if base.direct:
                self.vars[inst] = Value(base + abs_offset)
                self.vars[inst].direct = True
            else:
                res = Value(self.alloc(1))
                code = ('add_const', res, abs_offset, base)
                self.instructions.append(code)
                self.vars[inst] = res
                self.vars[inst].direct = False
        else:
            res = Value(self.alloc(1))
            if step == 1:
                tmp = self.vars[offset]
            else:
                tmp = Value(self.alloc(1))
                code = ('mul_const', tmp, step, self.vars[offset])
                self.instructions.append(code)
            if base.direct:
                code = ('add_const', res, base, tmp)
            else:
                code = ('add', res, base, tmp)
            self.instructions.append(code)
            self.vars[inst] = res
            self.vars[inst].direct = False
        self.vars[inst].depth = base.depth
    def icmp(self, inst):
        operands = inst.operands
        is_const = [isinstance(operand, ConstantInt) for operand in operands]
        has_const = sum(is_const)
        reverse = is_const[0]
        if inst.predicate in (ICMP_SLT, ICMP_SLE, ICMP_ULT, ICMP_ULE):
            if reverse:
                op = 'g'
            else:
                op = 'l'
        elif inst.predicate in (ICMP_SGT, ICMP_SGE):
            if has_const:
                if reverse:
                    op = 'l'
                else:
                    op = 'g'
            else:
                op = 'l'
                reverse = True
        elif inst.predicate == ICMP_EQ:
            op = 'eq'
        elif inst.predicate == ICMP_NE:
            op = 'ne'
        else:
            raise Exception('comparison not implemented: %s' % inst)
        if inst.predicate in (ICMP_SLT, ICMP_SGT, ICMP_ULT, ICMP_UGT):
            op += 't'
        elif inst.predicate in (ICMP_SLE, ICMP_SGE, ICMP_ULE, ICMP_UGE):
            op += 'e'
        if inst.predicate in (ICMP_ULT, ICMP_UGT, ICMP_ULE, ICMP_UGE):
            op = 'u' + op
        if reverse:
            operands.reverse()
        self.binary(inst, op, operands)
    def ashr(self, inst):
        if isinstance(inst.operands[1], ConstantInt):
            n = self.vars[inst.operands[0]]
            by = inst.operands[1].s_ext_value
            if by == 0:
                self.vars[inst] = n
            else:
                res = Ref(self.alloc(1), False)
                if by == 1:
                    code = ('shr1', res, 0, n)
                else:
                    code = ('shr_const', res, by, n)
                self.instructions.append(code)
                self.vars[inst] = res
        else:
            res = Ref(self.alloc(1), False)
            if isinstance(inst.operands[0], ConstantInt):
                n = Ref(self.alloc(1), False)
                code = ('store_const', n, inst.operands[0].s_ext_value, 0)
                self.instructions.append(code)
            else:
                n = self.vars[inst.operands[0]]
            code = ('shr', res, self.vars[inst.operands[1]], n)
            self.instructions.append(code)
            self.vars[inst] = res
    def shl(self, inst):
        res = Ref(self.alloc(1), False)
        by = inst.operands[1]
        if isinstance(by, ConstantInt):
            code = ('mul_const', res, 1 << by.s_ext_value, \
                        self.vars[inst.operands[0]])
        else:
            if isinstance(inst.operands[0], ConstantInt):
                n = Ref(self.alloc(1), False)
                code = ('store_const', n, inst.operands[0].s_ext_value, 0)
                self.instructions.append(code)
            else:
                n = self.vars[inst.operands[0]]
            code = ('shl', res, self.vars[by], n)
        self.instructions.append(code)
        self.vars[inst] = res
    def zext(self, inst):
        self.vars[inst] = self.get_var(inst.operands[0])
    def sub(self, inst):
        res = Ref(self.alloc(1), False)
        if isinstance(inst.operands[0], ConstantInt):
            code = ('sub_const', res, inst.operands[0].s_ext_value, \
                        self.vars[inst.operands[1]])
        else:
            if isinstance(inst.operands[1], ConstantInt):
                code = ('rsub_const', res, inst.operands[1].s_ext_value, \
                            self.vars[inst.operands[0]])
            else:
                code = ('sub', res, self.vars[inst.operands[0]], \
                            self.vars[inst.operands[1]])
        self.instructions.append(code)
        self.vars[inst] = res
    def br(self, inst):
        self.exit = inst
    def ret(self, inst):
        if inst.operands:
            src = inst.operands[0]
            code = self.store_direct(self.function.return_value, src)
            self.instructions.append(code)
        code = ['jmp_ind', 0, 0, self.function.return_address]
        self.instructions.append(code)
        self.function.exit = code
    def call(self, inst):
        if inst.operands[-1].name.startswith('llvm.'):
            return
        code = [list(self.store_direct(0, operand)) \
                    for operand,t in zip(inst.operands[:-1], \
                                             inst.operands[-1].type.pointee.args)]
        tmp = get_value(self.alloc(1), \
                            inst.operands[-1].type.pointee.return_type, start_depth=1)
        tmp.direct = False
        code += [['store_const', 0, 0, 0], \
                    ['jmp', 0, 0, 0], \
                    ['mov', tmp, 0, 0]]
        self.vars[inst] = tmp
        self.function.program.calls.append((inst, code, self, \
                                                len(self.instructions) + 2))
        self.instructions += code
    def phi(self, inst):
        self.phi_inst.append(inst)
        self.vars[inst] = Ref(self.alloc(1), False)

class Function(object):
    def __init__(self, function, program):
        self.program = program
        self.name = function.name
        self.return_value = program.alloc(1)
        self.return_address = program.alloc(1)
        self.exit = None
        self.vars = program.vars
        self.args = []
        for arg in function.args:
            a = get_value(program.alloc(1), arg.type, start_depth=1)
            a.direct = False
            self.args.append(a)
            self.vars[arg] = a
        self.basic_blocks = []
        self.basic_block_ref = {}
        for basic_block in function.basic_blocks:
            bb = BasicBlock(basic_block, self)
            self.basic_blocks.append(bb)
            self.basic_block_ref[basic_block] = bb
        start = 0
        for i,bb in enumerate(self.basic_blocks):
            if bb.redundant:
                continue
            bb.start = start
            if bb.exit is None:
                start += len(bb)
            else:
                operands = bb.exit.operands
                skip_br = len(operands) == 1 and \
                    not self.basic_block_ref[operands[0]].redundant and \
                    len(self.basic_blocks) > i + 1 and \
                    self.basic_block_ref[operands[0]] == self.basic_blocks[i+1]
                if skip_br:
                    # no need for jump, straight to next block
                    bb.exit = None
                next_blocks = operands if len(operands) == 1 else operands[1:]
                for next_block in next_blocks:
                    for phi in self.basic_block_ref[next_block].phi_inst:
                        for i in range(phi.incoming_count):
                            if self.basic_block_ref[phi.get_incoming_block(i)] \
                               is bb:
                                code = bb.store_direct(self.vars[phi], \
                                                       phi.get_incoming_value(i))
                                bb.instructions.append(code)
                                break
                start += len(bb) + (1 - skip_br)
        self.length = start
        for bb in self.basic_blocks:
            for i,code in enumerate(bb.instructions):
                if callable(code):
                    bb.instructions[i] = code()
    def link(self):
        for bb in self.basic_blocks[:-1]:
            if bb.exit is not None and not bb.redundant:
                operands = bb.exit.operands
                def get_start(i):
                    next = operands[i]
                    while self.basic_block_ref[next].redundant:
                        next = next.instructions[0].operands[0]
                    return self.start + self.basic_block_ref[next].start
                if len(operands) == 1:
                    code = ('jmp', get_start(0), 0, 0)
                else:
                    code = ('br', get_start(2), get_start(1), \
                                self.vars[bb.exit.operands[0]])
                bb.instructions.append(code)
    def __len__(self):
        return self.length
    def alloc(self, size):
        return self.program.alloc(size)
    def output(self):
        print('# %s()' % self.name)
        for bb in self.basic_blocks:
            if bb.instructions:
                print('\t# %s:' % bb.name)
            for i,instruction in enumerate(bb.instructions):
                if asm_output:
                    print('\t\t', instruction[0], \
                        ' '.join(str(int(x)) for x in instruction[1:]), \
                        '#', self.start + bb.start + i)
                else:
                    print('\t\t', instruction, ', #', self.start + bb.start + i)

class Program(object):
    def __init__(self, module, N):
        self.N = N
        self.vars = {}
        self.n_vars = 0
        self.initial_data = {}
        for var in module.global_variables:
            if not var.global_constant:
                v = Value.get_variable(var, self)
                init = var.initializer
                if isinstance(init, ConstantInt):
                    if init.s_ext_value != 0:
                        raise Exception('not implemented: variable initialization')
                elif isinstance(init, ConstantAggregateZero):
                    pass
                elif isinstance(init, ConstantDataArray):
                    raise Exception('not implemented: array initialization')
                else:
                    raise Exception('not implemented: unknown initialization')
        self.n_global_vars = self.n_vars
        self.calls = []
        self.functions = []
        self.function_ref = {}
        for function in module.functions:
            f = Function(function, self)
            self.functions.append(f)
            self.function_ref[function] = f
        start = 0
        for f in self.functions:
            f.start = start
            start += len(f)
            f.link()
        self.length = start
        for inst,code,bb,offset in self.calls:
            called_function = self.function_ref[inst.called_function]
            for i,arg in enumerate(called_function.args):
                code[i][1] = arg
            n_args = len(called_function.args)
            code[n_args+0][1] = called_function.return_address
            code[n_args+0][2] = bb.function.start + bb.start + offset + n_args
            code[n_args+1][1] = called_function.start
            code[n_args+2][2] = called_function.return_value
        try:
            self.main = self.function_ref[module.get_function_named('main')]
            self.check = self.main.return_value
        except llvm.LLVMException:
            self.main = self.functions[0]
            self.check = 2
        self.main.exit[:] = ['jmp', self.length, 0, 0]
        if debug:
            self.debug()
    def alloc(self, size):
        loc = self.n_vars
        self.n_vars += size
        return loc
    def output(self):
        if not asm_output:
            print('start =', self.main.start)
            print('check =', repr(self.check))
            print('n_vars =', max(self.n_vars, self.N))
            print('n_global_vars =', self.n_global_vars)
            print('code = [')
        for function in self.functions:
            function.output()
        if not asm_output:
            print(']')
    def debug(self):
        for v,x in self.vars.items():
            print(x, '\t', v, file=sys.stderr)

opts, args = getopt(sys.argv[1:], 'aN:')
N = float('-inf')

for opt,value in opts:
    if opt == '-a':
        asm_output = True
    elif opt == '-N':
        N = int(value)

program = Program(Module.from_bitcode(open(args[0], 'rb')), N)
program.output()
