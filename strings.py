#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import idc, idaapi, idautils
import common
import sys

'''
String defining fuctionality

# Indicators of string loads
mov     ebx, offset aWire ; "wire" # Get string
mov     [esp], ebx
mov     dword ptr [esp+4], 4 # String length

mov     ebx, offset unk_8608FD5 # Get string
mov     [esp+8], ebx
mov     dword ptr [esp+0Ch], 0Eh # String length

mov     ebx, offset unk_86006E6 # Get string
mov     [esp+10h], ebx
mov     dword ptr [esp+14h], 5 # String length

mov     ebx, 861143Ch
mov     dword ptr [esp+0F0h+var_E8+4], ebx
mov     [esp+0F0h+var_E0], 19h

# Found in newer versions of golang binaries

lea     rax, unk_8FC736
mov     [rsp+38h+var_18], rax
mov     [rsp+38h+var_10], 1Dh

lea     rdx, unk_8F6E82
mov     [rsp+40h+var_38], rdx
mov     [rsp+40h+var_30], 13h

lea     eax, unk_82410F0
mov     [esp+94h+var_8C], eax
mov     [esp+94h+var_88], 2
'''

# Currently it's normally ebx, but could in theory be anything - seen ebp
VALID_REGS = ['eax', 'ebx', 'ebp', 'rax', 'rcx', 'r10', 'rdx']

# Currently it's normally esp, but could in theory be anything - seen eax
VALID_DEST = ['esp', 'eax', 'ecx', 'edx', 'rsp']


def is_string_patt(addr):
    # Check for first parts instruction and what it is loading -- also ignore function pointers we may have renamed
    if (idc.print_insn_mnem(addr) != 'mov' and idc.print_insn_mnem(addr) != 'lea') \
            and (idc.get_operand_type(addr, 1) != 2 or idc.get_operand_type(addr, 1) != 5) \
            or idc.print_operand(addr, 1)[-4:] == '_ptr':
        return False

    # Validate that the string offset actually exists inside the binary
    if idc.get_segm_name(idc.get_operand_value(addr, 1)) is None:
        return False

    # Could be unk_, asc_, 'offset ', XXXXh, ignored ones are loc_ or inside []
    if idc.print_operand(addr, 0) in VALID_REGS \
            and not ('[' in idc.print_operand(addr, 1) or 'loc_' in idc.print_operand(addr, 1)) \
            and (('offset ' in idc.print_operand(addr, 1) or 'h' in idc.print_operand(addr, 1)) \
                 or ('unk' == idc.print_operand(addr, 1)[:3])):
        from_reg = idc.print_operand(addr, 0)
        # Check for second part
        addr_2 = idc.find_code(addr, idaapi.SEARCH_DOWN)
        try:
            dest_reg = idc.print_operand(addr_2, 0)[
                       idc.print_operand(addr_2, 0).index('[') + 1:idc.print_operand(addr_2, 0).index('[') + 4]
        except ValueError:
            return False

        if idc.print_insn_mnem(addr_2) == 'mov' and dest_reg in VALID_DEST \
                and ('[%s' % dest_reg) in idc.print_operand(addr_2, 0) \
                and idc.print_operand(addr_2, 1) == from_reg:
            # Check for last part, could be improved
            addr_3 = idc.find_code(addr_2, idaapi.SEARCH_DOWN)
            # get_operand_type 1 is a register, potentially we can just check that get_operand_type returned 5?
            if idc.print_insn_mnem(addr_3) == 'mov' \
                    and (
                    ('[%s+' % dest_reg) in idc.print_operand(addr_3, 0) or idc.print_operand(addr_3, 0) in VALID_DEST) \
                    and 'offset ' not in idc.print_operand(addr_3, 1) and 'dword ptr ds' not in idc.print_operand(
                addr_3, 1) \
                    and idc.get_operand_type(addr_3, 1) != 1 and idc.get_operand_type(addr_3,
                                                                                      1) != 2 and idc.get_operand_type(
                addr_3, 1) != 4:
                try:
                    dumb_int_test = idc.get_operand_value(addr_3, 1)
                    if dumb_int_test > 0 and dumb_int_test < sys.maxsize:
                        return True
                except ValueError:
                    return False

    return False


'''
Parse string pointer:

pattern:

mov     rcx, cs:qword_BC2908 ; str len
mov     rdx, cs:off_BC2900 ; str pointer
mov     [rsp+0A8h+var_90], rdx
mov     [rsp+0A8h+var_88], rcx
call    github_com_rs_zerolog_internal_json_Encoder_AppendKey
'''


def parse_str_ptr(addr):
    if idc.print_insn_mnem(addr) != 'mov':
        return False

    # Validate that the string offset actually exists inside the binary
    if idc.get_segm_name(idc.get_operand_value(addr, 1)) is None:
        return False

    # Check the operands' type:
    # - first one must be a register;
    # - second one must be a memory address
    if idc.get_operand_type(addr, 0) != 1 or idc.get_operand_type(addr, 1) != 2:
        return False

    addr_2 = idc.find_code(addr, idaapi.SEARCH_DOWN)
    # same operands' type for addr_2
    if idc.print_insn_mnem(addr_2) != 'mov' or idc.get_operand_type(addr_2, 0) != 1 or idc.get_operand_type(addr_2,
                                                                                                            1) != 2:
        return False

    opnd_val_1 = idc.get_operand_value(addr, 1)
    opnd_val_2 = idc.get_operand_value(addr_2, 1)
    opnd_diff = opnd_val_1 - opnd_val_2
    # The 2 operands, one of addr of string length, another one is the addr of string pointer
    # and they must be side by side
    if opnd_diff != common.ADDR_SZ and opnd_diff != -common.ADDR_SZ:
        return False

    if opnd_diff > 0:
        str_len_addr, str_ptr_addr = opnd_val_1, opnd_val_2
    else:
        str_len_addr, str_ptr_addr = opnd_val_2, opnd_val_1

    str_len = common.read_mem(str_len_addr)
    str_ptr = common.read_mem(str_ptr_addr)
    str_addr = common.read_mem(str_ptr)

    # set max str len
    if str_len > 64:
        return False

    if 'rodata' not in idc.get_segm_name(str_ptr) and 'text' not in idc.get_segm_name(str_ptr):
        return False

    common._debug("------------------------------")
    common._debug("Possible str ptr:")
    common._debug("Code addr: 0x%x , str_ptr_addr: 0x%x , str_len_addr: 0x%x" % (addr, str_ptr_addr, str_len_addr))
    common._debug("str_addr: 0x%x , str_len: 0x%x" % (str_ptr, str_len))
    # if create_string(str_addr, str_len):
    if str_len > 1:
        if idc.create_strlit(str_ptr, str_ptr + str_len):
            idaapi.auto_wait()
            if opnd_diff > 0:
                idc.set_cmt(addr, "length: %d" % str_len, 0)
                idaapi.add_dref(addr_2, str_ptr, idaapi.dr_O)
            else:
                idc.set_cmt(addr_2, "length: %d" % str_len, 0)
                idaapi.add_dref(addr, str_ptr, idaapi.dr_O)
            idaapi.auto_wait()
            return True

    return False


def create_string(addr, string_len):
    # if idaapi.get_segm_name(addr) is None:
    if idc.get_segm_name(addr) is None:
        common._debug('Cannot load a string which has no segment - not creating string @ 0x%02x' % addr)
        return False

    common._debug('Found string load @ 0x%x with length of %d' % (addr, string_len))
    # This may be overly aggressive if we found the wrong area...
    if idc.get_str_type(addr) is not None and idc.get_strlit_contents(addr) is not None and len(
            idc.get_strlit_contents(addr)) != string_len:
        common._debug('It appears that there is already a string present @ 0x%x' % addr)
        idc.del_items(addr, idc.DELIT_SIMPLE, string_len)
        idaapi.auto_wait()

    if idc.get_strlit_contents(addr) is None and idc.create_strlit(addr, addr + string_len):
        idaapi.auto_wait()
        return True
    else:
        # If something is already partially analyzed (incorrectly) we need to MakeUnknown it
        idc.del_items(addr, idc.DELIT_SIMPLE, string_len)
        idaapi.auto_wait()
        if idc.create_strlit(addr, addr + string_len):
            idaapi.auto_wait()
            return True
        common._debug('Unable to make a string @ 0x%x with length of %d' % (addr, string_len))

    return False


def create_offset(addr):
    if idc.op_plain_offset(addr, 1, 0):
        return True
    else:
        common._debug('Unable to make an offset for string @ 0x%x ' % addr)

    return False


def parse_strings():
    strings_added = 0
    retry = []

    # text_seg = common.get_text_seg()
    # if text_seg is None:
    #    common._debug('Failed to get text segment')
    #    return strings_added

    # This may be inherently flawed as it will only search for defined functions
    # and as of IDA Pro 6.95 it fails to autoanalyze many GO functions, currently
    # this works well since we redefine/find (almost) all the functions prior to
    # this being used. Could be worth a strategy rethink later one or on diff archs
    for segea in idautils.Segments():
        for addr in idautils.Functions(segea, idc.get_segm_end(segea)):
            # for addr in idautils.Functions(text_seg.start_ea, text_seg.end_ea):
            name = idc.get_func_name(addr)
            end_addr = idautils.Chunks(addr).__next__()[1]
            if (end_addr < addr):
                common._error('Unable to find good end for the function %s' % name)
                pass

            common._debug('Found function %s starting/ending @ 0x%x 0x%x' % (name, addr, end_addr))

            while addr <= end_addr:
                if parse_str_ptr(addr):
                    strings_added += 1
                    addr = idc.find_code(addr, idaapi.SEARCH_DOWN)
                elif is_string_patt(addr):
                    if 'rodata' not in idc.get_segm_name(addr) and 'text' not in idc.get_segm_name(addr):
                        common._debug('Should a string be in the %s section?' % idc.get_segm_name(addr))
                    string_addr = idc.get_operand_value(addr, 1)
                    addr_3 = idc.find_code(idc.find_code(addr, idaapi.SEARCH_DOWN), idaapi.SEARCH_DOWN)
                    string_len = idc.get_operand_value(addr_3, 1)
                    common._info(hex(addr_3) + ":" + hex(string_len))
                    if string_len > 1:
                        if create_string(string_addr, string_len):
                            if create_offset(addr):
                                strings_added += 1
                        else:
                            # There appears to be something odd that goes on with IDA making some strings, always works
                            # the second time, so lets just force a retry...
                            retry.append((addr, string_addr, string_len))

                    # Skip the extra mov lines since we know it won't be a load on any of them
                    addr = idc.find_code(addr_3, idaapi.SEARCH_DOWN)
                else:
                    addr = idc.find_code(addr, idaapi.SEARCH_DOWN)

    for instr_addr, string_addr, string_len in retry:
        if create_string(string_addr, string_len):
            if create_offset(instr_addr):
                strings_added += 1
        else:
            common._error('Unable to make a string @ 0x%x with length of %d for usage in function @ 0x%x' % (
                string_addr, string_len, instr_addr))

    return strings_added
