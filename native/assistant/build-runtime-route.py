from pathlib import Path
import hashlib,struct,subprocess
b=Path(__file__).resolve().parent
src=b/'live/libhyper_os_core_system_private.dylib.so'
d=bytearray(src.read_bytes())
assert hashlib.sha256(d).hexdigest()=='a7de453780f33d2dec0cfca8832d218ee798f3208df06af36744f416313afa1f'
subprocess.run([str(b/'ndk/bin/clang'),'--target=aarch64-linux-android35','-nostdlib','-static','-Wl,-Ttext=0x44500,--entry=route,--defsym=original_resume=0x38ed8,--defsym=original_cache_page=0x4c000,--defsym=dlsym_got=0x4aab8','-o',str(b/'assistant-route.elf'),str(b/'assistant-route.S')],check=True)
e=(b/'assistant-route.elf').read_bytes();off=struct.unpack_from('<Q',e,40)[0];sz,n,ns=struct.unpack_from('<HHH',e,58)
sh=[struct.unpack_from('<IIQQQQIIQQ',e,off+i*sz) for i in range(n)]
names=e[sh[ns][4]:sh[ns][4]+sh[ns][5]]
code=next(e[s[4]:s[4]+s[5]] for s in sh if names[s[0]:].split(b'\0')[0]==b'.text')
start=0x44500;end=start+len(code)
assert end<0x45000 and not any(d[start:end])
assert struct.unpack_from('<I',d,0x38ed4)[0]==0x900000a8
struct.pack_into('<I',d,0x38ed4,0x14000000+((start-0x38ed4)//4))
d[start:end]=code
ph=struct.unpack_from('<Q',d,32)[0];psz,pn=struct.unpack_from('<HH',d,54)
for i in range(pn):
 p=ph+i*psz
 if struct.unpack_from('<IIQ',d,p)==(1,5,0):
  assert struct.unpack_from('<QQ',d,p+32)==(0x44498,0x44498)
  struct.pack_into('<QQ',d,p+32,end,end)
out=b/'assistant-runtime.so';out.write_bytes(d)
print('route bytes',len(code),'sha256',hashlib.sha256(d).hexdigest())
