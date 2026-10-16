"""Regression for libxposed's one process listener across three settings pages."""
from pathlib import Path
import tempfile,subprocess,unittest
P=Path(__file__).resolve().parents[1]
class FrameworkServiceTest(unittest.TestCase):
 def test_cached_connection_page_navigation_and_death(self):
  with tempfile.TemporaryDirectory(prefix='framework-service-') as d:
   p=Path(d)
   sources={
    'io/github/libxposed/service/XposedService.java':'package io.github.libxposed.service; public class XposedService {}',
    'io/github/libxposed/service/XposedServiceHelper.java':'''package io.github.libxposed.service;
public class XposedServiceHelper {
 public interface OnServiceListener {void onServiceBind(XposedService s);void onServiceDied(XposedService s);}
 public static int registrations;public static OnServiceListener listener;public static XposedService cached=new XposedService();
 public static void registerListener(OnServiceListener l){registrations++;listener=l;if(cached!=null){l.onServiceBind(cached);cached=null;}}
}''',
    'Test.java':'''import io.github.libxposed.service.*;import local.xuanyuan.unified.FrameworkService;
public class Test {
 static class Page implements XposedServiceHelper.OnServiceListener {XposedService service;int binds,deaths;public void onServiceBind(XposedService s){service=s;binds++;}public void onServiceDied(XposedService s){if(service==s)service=null;deaths++;}}
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] args){
  Page settings=new Page(),preset=new Page(),push=new Page();
  FrameworkService.addListener(settings);check(settings.service!=null);
  FrameworkService.addListener(preset);FrameworkService.addListener(push);
  check(XposedServiceHelper.registrations==1&&preset.service==settings.service&&push.service==settings.service);
  XposedService old=settings.service,next=new XposedService();XposedServiceHelper.listener.onServiceBind(next);
  XposedServiceHelper.listener.onServiceDied(old);check(settings.service==next&&preset.service==next&&push.service==next);
  XposedServiceHelper.listener.onServiceDied(next);check(settings.service==null&&preset.service==null&&push.service==null);
  Page reopened=new Page();FrameworkService.addListener(reopened);check(reopened.binds==0&&XposedServiceHelper.registrations==1);
  XposedServiceHelper.listener.onServiceBind(next);check(reopened.service==next&&preset.binds==3);
 }
}'''}
   files=[]
   for n,s in sources.items():q=p/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(s);files.append(str(q))
   subprocess.run(['javac','-d',str(p),*files,str(P/'src/local/xuanyuan/unified/FrameworkService.java')],check=True,capture_output=True)
   subprocess.run(['java','-cp',str(p),'Test'],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
