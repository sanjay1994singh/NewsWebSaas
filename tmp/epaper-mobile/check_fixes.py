import os,json,re
from pathlib import Path
from types import SimpleNamespace
from datetime import date
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.template.loader import render_to_string
from django.test import override_settings
import requests
from playwright.sync_api import sync_playwright
url='https://pressnexa.live-app.in/p/national24/epaper/'
r=requests.get(url,timeout=25);r.raise_for_status()
pages=json.loads(re.search(r'<script id="readerPages" type="application/json">(.*?)</script>',r.text,re.S).group(1))
context=dict(tenant=SimpleNamespace(public_name='National 24',slug='national24'),edition=SimpleNamespace(title='E-Paper',city='Mathura',edition_name='Main',publication_date=date(2026,9,6),allow_download=True,slug='test-edition'),pages=pages,initial_page=pages[0],initial_index=0,share_url=url,edition_url=url,site_home_url='https://pressnexa.live-app.in/',reader_home_url=url,bookmark_key='fix-qa',cities=['Mathura'],edition_names=['Main'],selected_date='2026-09-06')
with override_settings(STORAGES={'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
    html=render_to_string('epaper/reader.html',context)
    empty=render_to_string('epaper/reader.html',{**context,'pages':[],'edition':None,'initial_page':None})
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge')
    for w,h in [(390,844),(1440,1000)]:
        page=browser.new_page(viewport={'width':w,'height':h},device_scale_factor=2,is_mobile=w<701,has_touch=w<701)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/static/epaper/**',lambda route:route.fulfill(path=str(Path('static/epaper')/route.request.url.split('/static/epaper/')[1].split('?')[0])))
        page.route(url,lambda route:route.fulfill(body=html,content_type='text/html'))
        page.goto(url,wait_until='networkidle',timeout=60000)
        page.wait_for_function('document.querySelector("#pageImage").naturalWidth>0')
        if w<701:
            result=page.evaluate("""() => {
              const stage=document.querySelector('#stage'),img=document.querySelector('#pageImage');
              let r=img.getBoundingClientRect();const x=r.left+r.width*.55,y=r.top+r.height*.48;
              const fire=(type,d)=>stage.dispatchEvent(new TouchEvent(type,{bubbles:true,cancelable:true,touches:d?[new Touch({identifier:1,target:stage,clientX:x-d,clientY:y}),new Touch({identifier:2,target:stage,clientX:x+d,clientY:y})]:[],changedTouches:[]}));
              const before={u:(x-r.left)/r.width,v:(y-r.top)/r.height};fire('touchstart',35);fire('touchmove',70);
              r=img.getBoundingClientRect();const after={u:(x-r.left)/r.width,v:(y-r.top)/r.height};fire('touchend',0);
              return {before,after,zoom:document.querySelector('#zoomLabel').textContent};
            }""")
            assert result['zoom']=='200%',result
            assert abs(result['before']['u']-result['after']['u'])<.005,result
            assert abs(result['before']['v']-result['after']['v'])<.005,result
        else:
            page.evaluate('window.scrollTo(0,700)')
            page.locator('.pager [data-action="next"]').click()
            page.wait_for_function('document.querySelector("#pageSelect").value==="1"')
            assert page.evaluate("document.querySelector('#paper').getBoundingClientRect().top >= document.querySelector('.toolbar').getBoundingClientRect().bottom")
        page.locator('[data-action="clip"]').click()
        box=page.locator('#pageImage').bounding_box()
        x=max(10,box['x']+box['width']*.15);y=max(120,box['y']+60)
        coords=page.evaluate("""([x,y])=>{const r=document.querySelector('#pageImage').getBoundingClientRect();return {x:(x-r.x)/r.width,y:(y-r.y)/r.height,w:140/r.width,h:160/r.height}}""",[x,y])
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+140,y+160,steps=10);page.mouse.up()
        page.wait_for_selector('#clipDialog[open]',timeout=30000)
        result=page.evaluate("""async c=>{
            const data=JSON.parse(document.querySelector('#readerPages').textContent),idx=+document.querySelector('#pageSelect').value;
            const load=src=>new Promise((res,rej)=>{const i=new Image();i.crossOrigin='anonymous';i.onload=()=>res(i);i.onerror=rej;i.src=src});
            const src=await load(data[idx].zoom),actual=await load(document.querySelector('#clipDownload').href);
            const expected=document.createElement('canvas');expected.width=Math.round(c.w*src.naturalWidth);expected.height=Math.round(c.h*src.naturalHeight);
            expected.getContext('2d').drawImage(src,Math.round(c.x*src.naturalWidth),Math.round(c.y*src.naturalHeight),expected.width,expected.height,0,0,expected.width,expected.height);
            const got=document.createElement('canvas');got.width=actual.width;got.height=actual.height;got.getContext('2d').drawImage(actual,0,0);
            const a=expected.getContext('2d').getImageData(0,0,expected.width,expected.height).data,b=got.getContext('2d').getImageData(0,0,got.width,got.height).data;
            return {match:a.length===b.length&&a.every((v,i)=>v===b[i]),size:[actual.width,actual.height]};
        }""",coords)
        assert result['match'],result
        assert not errors,errors
        print('PASS',w,'pixel-exact crop',result['size'],'and focal zoom/header offset',flush=True)
        page.locator('#clipDialog [data-close]').click()
        if w<701:
            page.unroute(url);page.route(url,lambda route:route.fulfill(body=empty,content_type='text/html'))
            page.goto(url,wait_until='networkidle')
            assert page.locator('.reader-identity').is_visible()
            assert not page.locator('.brandbar').is_visible()
            page.evaluate("document.querySelector('.filters').addEventListener('submit',e=>{e.preventDefault();window.didSubmit=true})")
            page.locator('input[type=date]').fill('2026-09-08')
            assert page.evaluate('window.didSubmit===true')
            print('PASS no-edition branding and date recovery',flush=True)
        page.close()
    browser.close()

