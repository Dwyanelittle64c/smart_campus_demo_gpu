/* 公共职责：CSRF 同源网关、控制租约、二进制帧解码、共享浏览器摄像头。浏览器不执行算法。 */
window.Campus = (() => {
  const C = {sid:null,capabilities:null,listeners:[],socket:null,retries:0,busy:false};
  C.$ = selector => document.querySelector(selector);
  C.text = (selector,value) => {const el=C.$(selector);if(el)el.textContent=value;};
  // 同源HTTP入口：写请求附CSRF和控制租约，实例令牌永远由Web服务添加。
  C.api = async (path,{method='GET',body=null}={}) => {
    const headers={};
    if(method==='POST'){
      headers['X-CSRFToken']=decodeURIComponent(document.cookie.split('; ').find(v=>v.startsWith('csrftoken='))?.split('=')[1]||'');
      if(!C.sid)throw new Error('未取得 GPU 控制会话，请检查后端连接');
      headers['X-Control-Session']=C.sid;
    }
    if(body && !(body instanceof FormData)){headers['Content-Type']='application/json';body=JSON.stringify(body);}
    const response=await fetch('/api/'+path,{method,body,headers,cache:'no-store'});
    const result=await response.json().catch(()=>({error:`请求失败 (${response.status})`}));
    if(!response.ok||result.error)throw new Error(result.error||'后端操作失败');
    return result.data;
  };
  C.sample=async name=>{const r=await fetch('/api/face/sample/'+name);if(!r.ok)throw new Error('公开测试照片不可用');return r.blob();};
  C.ws = (path) => new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/${path}`);
  C.onControl = fn=>{
    C.listeners.push(fn);
    if(C.sid && C.capabilities)fn(true);
  };
  C.connect = () => {
    if(C.socket && C.socket.readyState<2)return;
    C.text('#connection-state','正在连接 GPU 后端…');
    const socket=C.ws('control');C.socket=socket;
    socket.onmessage=async event=>{
      const message=JSON.parse(event.data);
      if(message.error){C.text('#global-error',message.error);C.busy=message.error.includes('另一控制');return;}
      if(message.type!=='control')return;
      C.sid=message.session_id;C.retries=0;C.busy=false;
      try{
        C.capabilities=await C.api('capabilities/');
        for(const [module,enabled] of Object.entries(C.capabilities.modules)){
          const element=C.$(`#${module}-module`);if(element)element.hidden=!enabled;
        }
        C.$('.workspace').classList.toggle('single',!Object.values(C.capabilities.modules).every(Boolean));
        C.text('#connection-state',C.capabilities.instance_name);C.text('#global-error','');
        C.listeners.forEach(fn=>fn(true));
      }catch(error){C.text('#global-error',error.message);}
    };
    socket.onclose=()=>{
      if(C.socket!==socket)return;
      C.sid=null;C.listeners.forEach(fn=>fn(false));
      C.text('#connection-state','GPU 后端已断开');
      if(!C.busy && C.retries<10){const delay=Math.min(8000,500*2**C.retries++);setTimeout(C.connect,delay);}
    };
    socket.onerror=()=>C.text('#global-error','GPU 后端未连接；页面可用，请检查服务或 SSH 隧道');
  };
  setInterval(()=>{if(C.socket?.readyState===1)C.socket.send(JSON.stringify({op:'ping'}));},5000);
  C.$('#reconnect').onclick=()=>{C.busy=false;C.retries=0;C.connect();};
  document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>C.$('#'+button.dataset.close).close());
  C.pack = async(meta,blob)=>{
    const encoded=new TextEncoder().encode(JSON.stringify(meta)),buffer=new ArrayBuffer(12+encoded.length+blob.size),view=new DataView(buffer);
    new Uint8Array(buffer,0,4).set([83,67,71,49]);view.setUint32(4,encoded.length,true);view.setUint32(8,blob.size,true);
    new Uint8Array(buffer,12,encoded.length).set(encoded);new Uint8Array(buffer,12+encoded.length).set(new Uint8Array(await blob.arrayBuffer()));return buffer;
  };
  C.unpack = buffer=>{
    const view=new DataView(buffer);if(view.byteLength<12||view.getUint32(0)!==0x53434731)throw new Error('帧协议错误');
    const ml=view.getUint32(4,true),pl=view.getUint32(8,true);if(12+ml+pl!==view.byteLength||ml>131072)throw new Error('帧长度错误');
    return {meta:JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,12,ml))),blob:new Blob([new Uint8Array(buffer,12+ml,pl)],{type:'image/jpeg'})};
  };
  C.stats = values=>{if(!values.length)return {mean:0,p50:0,p95:0};const sorted=[...values].sort((a,b)=>a-b);return {mean:values.reduce((a,b)=>a+b,0)/values.length,p50:sorted[Math.floor(sorted.length*.5)],p95:sorted[Math.min(sorted.length-1,Math.floor(sorted.length*.95))]};};
  C.hash=async blob=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer())),b=>b.toString(16).padStart(2,'0')).join('');
  C.FrameView=class {
    /* 单解码项 + 一个可覆盖待办，异步 decode 不会堆积，也不会让旧 epoch 覆盖新流。 */
    constructor(image,placeholder,callback){
      this.image=image;
      this.placeholder=placeholder;
      this.callback=callback;
      this.epoch=null;
      this.last=0;
      this.pending=null;
      this.decoding=false;
      this.dropped=0;
      this.url=null;
    }
    reset(epoch){
      this.epoch=epoch;
      this.last=0;
      this.pending=null;
    }
    accept(buffer){
      if(this.pending)this.dropped++;
      this.pending={buffer,received:performance.now()};
      if(!this.decoding)this.process();
    }
    async process(){
      this.decoding=true;
      while(this.pending){
        const item=this.pending;
        this.pending=null;
        let url=null;
        try{
          const {meta,blob}=C.unpack(item.buffer);
          if(meta.epoch!==this.epoch||meta.frame_id<=this.last)continue;
          url=URL.createObjectURL(blob);
          const next=new Image();
          next.src=url;
          await next.decode();
          await new Promise(resolve=>requestAnimationFrame(resolve));
          if(meta.epoch!==this.epoch||meta.frame_id<=this.last){
            URL.revokeObjectURL(url);
            continue;
          }
          const old=this.url;
          this.image.src=url;
          this.url=url;
          this.image.hidden=false;
          this.placeholder.hidden=true;
          if(old)URL.revokeObjectURL(old);
          this.last=meta.frame_id;
          await this.callback(meta,blob,item.received,performance.now());
        }catch(error){
          if(url&&url!==this.url)URL.revokeObjectURL(url);
          console.error(error);
        }
      }
      this.decoding=false;
    }
    close(){
      this.pending=null;
      this.epoch=null;
      if(this.url){
        URL.revokeObjectURL(this.url);
        this.url=null;
      }
    }
  };
  // 两个模块引用同一真实设备；最后一个消费者退出时才停止所有tracks。
  C.Camera={stream:null,users:new Set(),opening:null,revision:0,
    async acquire(user){
      if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia)throw new Error('摄像头需要 localhost 或 HTTPS 安全页面');
      this.users.add(user);
      if(!this.stream){
        if(!this.opening){const revision=this.revision;this.opening=(async()=>{
          const device=C.$('#camera-device').value;
          let expired=false,timer;
          const request=navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:15,max:20},...(device?{deviceId:{exact:device}}:{})},audio:false});
          // 用户忽略浏览器许可时promise可能永不完成；只取消本轮，迟到的授权流也立即关闭。
          request.then(stream=>{if(expired)stream.getTracks().forEach(track=>track.stop());},()=>{});
          let stream;
          try{stream=await Promise.race([request,new Promise((_,reject)=>{timer=setTimeout(()=>{expired=true;reject(new Error('摄像头授权超时，请在普通浏览器允许访问后重试'));},15000);})]);}
          finally{clearTimeout(timer);}
          if(!this.users.size||this.revision!==revision){stream.getTracks().forEach(track=>track.stop());throw new Error('摄像头开启已取消');}
          this.stream=stream;
          C.$('#camera-panel').hidden=false;
          C.$('#camera-preview').srcObject=this.stream;
          await C.$('#camera-preview').play();
          const devices=await navigator.mediaDevices.enumerateDevices();C.$('#camera-device').replaceChildren();
          devices.filter(d=>d.kind==='videoinput').forEach(d=>{const o=document.createElement('option');o.value=d.deviceId;o.textContent=d.label||'摄像头';C.$('#camera-device').append(o);});
          C.$('#camera-device').value=this.stream.getVideoTracks()[0].getSettings().deviceId;C.$('#camera-device').disabled=true;
        })().finally(()=>{this.opening=null;});}
        try{await this.opening;}catch(error){this.release(user);throw new Error(`摄像头未开启：${error.message||error.name}，请检查授权或设备`);}
      }
      this.users.add(user);C.$('#camera-panel').hidden=false;return this.stream;
    },
    release(user){
      this.users.delete(user);
      if(!this.users.size){
        this.revision++;
        if(this.stream)this.stream.getTracks().forEach(track=>track.stop());
        this.stream=null;
        C.$('#camera-preview').srcObject=null;
        C.$('#camera-panel').hidden=true;
        C.$('#camera-device').disabled=false;
      }
    },
    async photo(){
      if(!this.stream)throw new Error('请先启用浏览器摄像头');
      const video=C.$('#camera-preview');if(!video.videoWidth)throw new Error('摄像头尚未出图');
      const ratio=Math.min(1,640/video.videoWidth,480/video.videoHeight),canvas=document.createElement('canvas');canvas.width=Math.round(video.videoWidth*ratio);canvas.height=Math.round(video.videoHeight*ratio);
      canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);return new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.82));
    }
  };
  C.$('#camera-close').onclick=()=>{for(const user of [...C.Camera.users])C.Camera.release(user);C.traffic?.stop();};
  window.addEventListener('pagehide',()=>{for(const user of [...C.Camera.users])C.Camera.release(user);C.socket?.close();});
  setTimeout(C.connect,0);return C;
})();
