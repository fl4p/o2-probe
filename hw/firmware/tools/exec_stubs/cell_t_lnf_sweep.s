@ Sweep o2p_cell_t_lnf() on a running probe through the EXEC mailbox.
@
@ Test B of docs/2026-09-20-testing-the-knee-above-36C.md: does the compiled
@ knee law EXECUTE correctly above 36 C, at room temperature, with no heat.
@
@ ABI (main.c execute_arbitrary_code): uint32_t fn(uint32_t arg), the blob is
@ copied to a 4-byte aligned buffer and entered with the Thumb bit set. A
@ HardFault or a timeout longjmps out, so a wrong address costs a status word
@ and not a probe.
@
@   arg[15:0]  = first t_c100, SIGNED
@   arg[31:16] = how many points
@   step       = the literal at step_lit, patched by register so the sweep can
@                be re-aimed without re-uploading the blob
@   returns 0; the floats land at `results`, read back with the wide peek
@
@ POSITION-INDEPENDENT ON PURPOSE. Everything is PC-relative (adr, ldr
@ literal), so the blob does not care where the copy lands - the one thing
@ about this that must NOT be assumed from a host build.
@ BUILD (the .bin is an artifact and is not tracked):
@   AS=~/.platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-as
@   OC=${AS%as}objcopy
@   $AS -mcpu=cortex-m0plus -mthumb -o stub.o cell_t_lnf_sweep.s
@   $OC -O binary --only-section=.text stub.o stub.bin
@ o2p_exec_sweep.py takes --stub stub.bin and PATCHES target_lit from
@ --symbol-addr, so the literal below is a placeholder, not a source of truth.
    .syntax unified
    .cpu cortex-m0plus
    .thumb
    .text
    .global _start
    .thumb_func
_start:
    push {r4, r5, r6, r7, lr}
    sxth r5, r0                 @ t_c100, sign-extended: the caller's duty
    lsrs r4, r0, #16            @ points remaining
    adr  r7, results
    ldr  r6, step_lit
loop:
    cmp  r4, #0
    beq  done
    mov  r0, r5
    ldr  r3, target_lit         @ reloaded each pass: r0-r3 are call-clobbered
    blx  r3
    stmia r7!, {r0}             @ the float's BITS, not a conversion
    adds r5, r5, r6
    subs r4, #1
    b    loop
done:
    adr  r0, results            @ REPORT the buffer address rather than assume it
    pop  {r4, r5, r6, r7, pc}
    .align 2
target_lit:
    .word 0x0800b7e5            @ o2p_cell_t_lnf | 1, from the 2b7ed0a build
step_lit:
    .word 500                   @ 5.00 C
    .align 2
results:
    .space 88
