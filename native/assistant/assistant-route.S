// OS4.0.0.6 EEA only. Other processes and missing opt-in retain original behavior.
.text
.global route
route:
  sub sp, sp, #64
  stp x19, x30, [sp, #48]
  mov x0, #-100
  adr x1, cmdline
  mov x2, #0
  mov x3, #0
  mov x8, #56
  svc #0
  tbnz x0, #63, original
  mov x19, x0
  mov x1, sp
  mov x2, #14
  mov x8, #63
  svc #0
  mov x9, x0
  mov x0, x19
  mov x8, #57
  svc #0
  cmp x9, #14
  b.ne original
  adr x10, home_name
  ldr x11, [sp]
  ldr x12, [x10]
  cmp x11, x12
  b.ne original
  ldr w11, [sp, #8]
  ldr w12, [x10, #8]
  cmp w11, w12
  b.ne original
  ldrh w11, [sp, #12]
  ldrh w12, [x10, #12]
  cmp w11, w12
  b.ne original
  mov x0, #-100
  adr x1, marker
  mov x2, #0
  mov x3, #0
  mov x8, #56
  svc #0
  tbnz x0, #63, original
  mov x8, #57
  svc #0
  mov x0, #0
  adr x1, property_reload
  adrp x9, dlsym_got
  ldr x9, [x9, :lo12:dlsym_got]
  blr x9
  cbz x0, original
  // Exact libc hash pinned by installer: private per-process override flag.
  mov x9, #0x3459
  movk x9, #0x8, lsl #16
  add x0, x0, x9
  ldurb w9, [x0, #-1]
  cmp w9, #1
  b.ne original
  mov w9, #1
  strb w9, [x0]
  mov w0, #0
  ldp x19, x30, [sp, #48]
  add sp, sp, #64
  ret
original:
  ldp x19, x30, [sp, #48]
  add sp, sp, #64
  adrp x8, original_cache_page
  b original_resume
cmdline: .asciz "/proc/self/cmdline"
home_name: .asciz "com.miui.home"
marker: .asciz "/data/user_de/0/com.miui.home/files/.os4-assistant-route"

property_reload: .asciz "__system_properties_zygote_reload"
