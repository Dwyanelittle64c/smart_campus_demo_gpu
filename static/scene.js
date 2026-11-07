/* GS：持续相机控制与二进制图片独立，按完成帧号显示；真实浏览器基准从首帧后预热起算。 */
(() => {
  const C=Campus,$=C.$;let socket=null,active=false,dirty=false,camera={yaw:0,pitch:0,zoom:1,pan:[0,0,0]},drag=null,controls=null;
  let requestId=0,lastSent=0,changedAt=0,reconnects=0,frameTimes=[],coreTimes=[],bench=null,preparing=false;
  const view=new C.FrameView($('#scene-image'),$('#scene-placeholder'),async(meta,blob,received,displayed)=>{
    controls=meta.camera_control;
    frameTimes.push(displayed);
    coreTimes=coreTimes.filter(sample=>displayed-sample.at<2000);
    coreTimes.push({at:displayed,ms:meta.core_ms});
    C.text('#scene-count',`${meta.original} / ${meta.actual} / ${meta.visible}`);
    C.text('#scene-resolution',`${meta.resolution.join(' × ')} / SH ${meta.sh_degree}`);
    C.text('#scene-core',`${meta.core_ms.toFixed(2)} ms`);
    C.text('#scene-core-fps',(1000/C.stats(coreTimes.map(sample=>sample.ms)).mean).toFixed(1));
    C.text('#scene-latency',`${(displayed-meta.client_time).toFixed(1)} ms`);
    C.text('#scene-device',`${meta.gpu_name} · ${meta.device} · 全量/公开配置 ${meta.actual} 高斯 · SH ${meta.sh_degree}（素材可用 ${meta.available_sh_degree}）`);
    C.text('#scene-state','GPU 连续帧');C.text('#scene-error','');
    $('#scene-module').dataset.frameId=meta.frame_id;$('#scene-module').dataset.epoch=meta.epoch;
    if(bench){
      if(bench.started===null){bench.started=displayed+2000;bench.ends=bench.started+bench.duration*1000;}
      if(displayed>=bench.started && displayed<=bench.ends){
        bench.frames.push({...meta,hash:await C.hash(blob),bytes:blob.size,received_ms:received-bench.started,
          displayed_ms:displayed-bench.started,latency_ms:displayed-meta.client_time,decode_commit_ms:displayed-received});
      }
    }
  });
  function open(){
    if(!C.sid||!active||socket?.readyState<2)return;
    C.text('#scene-state','连接中 / 首次加载…');
    const connection=C.ws('scene');
    socket=connection;
    connection.binaryType='arraybuffer';
    connection.onopen=()=>{
      if(socket!==connection)return;
      connection.send(JSON.stringify({session_id:C.sid}));
      dirty=true;
    };
    connection.onmessage=event=>{
      if(socket!==connection)return;
      if(typeof event.data==='string'){
        const message=JSON.parse(event.data);
        if(message.epoch){view.reset(message.epoch);dirty=true;}
        if(message.error){C.text('#scene-state','场景不可用');C.text('#scene-error',message.error);}
      }else view.accept(event.data);
    };
    connection.onclose=()=>{
      // 快速停止后重开时，旧连接的迟到事件不能覆盖当前连接。
      if(socket!==connection)return;
      socket=null;
      C.text('#scene-state',active?'连接已断开':'已停止');
      if(active&&C.sid){
        reconnects++;
        setTimeout(open,Math.min(4000,500*reconnects));
      }
    };
  }
  function schedule(){dirty=true;changedAt=performance.now();}
  function start(){
    active=true;
    changedAt=performance.now();
    if(!C.sid)C.text('#scene-state','等待 GPU 后端重连');
    open();
    schedule();
  }
  function stop(){
    active=false;
    dirty=false;
    socket?.close();
    socket=null;
    view.close();
    C.text('#scene-state','已停止');
  }
  function reset(){camera={yaw:0,pitch:0,zoom:1,pan:[0,0,0]};changedAt=performance.now();if(socket?.readyState===1)socket.send(JSON.stringify({op:'reset',state:camera,client_time:changedAt,request_id:++requestId}));else schedule();}
  const viewport=$('#scene-viewport');
  // 使用原图在object-fit中的实际大小，黑边不影响平移速度。
  function imageSize(){
    const image=$('#scene-image'),box=viewport.getBoundingClientRect();
    const scale=Math.min(box.width/(image.naturalWidth||640),box.height/(image.naturalHeight||480));
    return [(image.naturalWidth||640)*scale,(image.naturalHeight||480)*scale];
  }
  function translated(base,dx,dy,basis){
    const [width,height]=imageSize();
    return base.map((value,i)=>value-basis.right[i]*dx/width*basis.world_per_image_x-basis.down[i]*dy/height*basis.world_per_image_y);
  }
  viewport.addEventListener('contextmenu',event=>event.preventDefault());
  viewport.addEventListener('pointerdown',event=>{
    if(![0,1,2].includes(event.button)||bench)return;
    event.preventDefault();viewport.focus({preventScroll:true});
    drag={x:event.clientX,y:event.clientY,...camera,pan:[...camera.pan],panning:event.button!==0||event.shiftKey,basis:controls};
    viewport.classList.add('dragging');viewport.setPointerCapture(event.pointerId);
  });
  viewport.addEventListener('pointermove',event=>{
    if(!drag)return;
    const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
    if(drag.panning){
      if(!drag.basis)return;
      camera.pan=translated(drag.pan,dx,dy,drag.basis);
    }else{
      camera.yaw=drag.yaw-dx*.007;
      camera.pitch=Math.max(-1.3,Math.min(1.3,drag.pitch-dy*.007));
    }
    schedule();
  });
  function endDrag(){if(drag){drag=null;schedule();}viewport.classList.remove('dragging');}
  viewport.addEventListener('pointerup',endDrag);
  viewport.addEventListener('pointercancel',endDrag);
  viewport.addEventListener('lostpointercapture',endDrag);
  viewport.addEventListener('keydown',event=>{
    if(bench||!controls)return;
    const step=event.shiftKey?60:20;
    const delta={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]}[event.key];
    if(!delta)return;
    event.preventDefault();camera.pan=translated(camera.pan,...delta,controls);schedule();
  });
  viewport.addEventListener('dragstart',event=>event.preventDefault());
  viewport.addEventListener('wheel',event=>{event.preventDefault();if(bench)return;camera.zoom=Math.max(.2,Math.min(8,camera.zoom*Math.exp(event.deltaY*.0015)));schedule();},{passive:false});
  $('#scene-start').onclick=start;$('#scene-stop').onclick=stop;$('#scene-reset').onclick=reset;
  $('#scene-in').onclick=()=>{camera.zoom=Math.max(.2,camera.zoom/1.15);schedule();};$('#scene-out').onclick=()=>{camera.zoom=Math.min(8,camera.zoom*1.15);schedule();};
  C.onControl(connected=>{
    if(!connected){
      socket?.close();
      socket=null;
      view.reset(null);
      C.text('#scene-state',active?'后端断开 / 等待重连':'已停止');
    }else if(C.capabilities.modules.scene&&active)open();
  });
  // 显式验收会实际驱动相机/交通/公开照片推理；从首帧后预热2秒开始。
  async function benchmark(){
    if(bench||preparing)return;preparing=true;$('#benchmark-start').disabled=true;
    const mode=$('#benchmark-mode').value;
    try{
      if(!C.sid)throw new Error('请先连接 GPU 后端');
      if(mode!=='gs-only'&&mode!=='stability'){
        if(!C.traffic)throw new Error('交通模块未启用');
        await C.traffic.stop();await C.traffic.startDemo();
        const deadline=performance.now()+30000;
        while(true){const status=await C.api('traffic/status/');if(status.status==='error')throw new Error(status.error);if(status.frame_id>0&&status.status==='running')break;if(performance.now()>deadline)throw new Error('交通未在30秒内实际出帧');await new Promise(r=>setTimeout(r,100));}
      }else if(C.traffic){await C.traffic.stop();}
      if(mode==='gs-traffic-face'){
        if(!C.face)throw new Error('人脸模块未启用');
        await C.face.ensureDemo();
      }
      await C.api('diagnostics/start/',{method:'POST',body:{}});
      const trafficStart=C.traffic?await C.api('traffic/status/'):null;
      bench={mode,duration:mode==='stability'?600:60,started:null,ends:Infinity,animation:performance.now(),frames:[],
        faceEvents:[],facePending:false,nextFace:performance.now()+10000,trafficStart,reconnectStart:reconnects,clientDropStart:view.dropped};
      $('#benchmark-result').hidden=true;start();
    }catch(error){C.text('#benchmark-state',error.message);$('#benchmark-start').disabled=false;}
    finally{preparing=false;}
  }
  // 仅已解码并提交的不同JPEG计入成绩，保存原始帧和资源，便于独立复核。
  async function finish(){
    const result=bench;if(!result||result.finishing)return;result.finishing=true;dirty=false;
    try{
      while(result.facePending)await new Promise(r=>setTimeout(r,30));
      const frames=result.frames,hashes=new Set(frames.map(f=>f.hash)),bytes=frames.reduce((n,f)=>n+f.bytes,0);
      const report={mode:result.mode,duration_seconds:result.duration,visibility:document.visibilityState,user_agent:navigator.userAgent,
        frame_count:frames.length,distinct_frames:hashes.size,web_fps:hashes.size/result.duration,
        core_ms:C.stats(frames.map(f=>f.core_ms)),latency_ms:C.stats(frames.map(f=>f.latency_ms)),
        decode_commit_ms:C.stats(frames.map(f=>f.decode_commit_ms)),jpeg_bytes:bytes,mbps:bytes*8/result.duration/1e6,
        client_overwritten:view.dropped-result.clientDropStart,reconnects:reconnects-result.reconnectStart,
        traffic_start:result.trafficStart,traffic_end:C.traffic?await C.api('traffic/status/'):null,face_events:result.faceEvents,frames};
      await C.api('diagnostics/report/',{method:'POST',body:report});
      C.text('#benchmark-state',`完成：${report.web_fps.toFixed(2)} 个不同新帧/秒，延迟P95 ${report.latency_ms.p95.toFixed(1)}ms`);
      C.text('#benchmark-result',JSON.stringify({...report,frames:`${frames.length}条原始帧已保存`},null,2));$('#benchmark-result').hidden=false;
    }catch(error){C.text('#benchmark-state',`验收保存失败：${error.message}`);}
    finally{bench=null;$('#benchmark-start').disabled=false;}
  }
  function tick(now){
    if(bench&&!bench.finishing){
      if(now<bench.ends){
        const t=(now-bench.animation)/1000;camera={yaw:.75*Math.sin(t*.7),pitch:.13*Math.sin(t*.4),zoom:.9+.1*Math.sin(t*.35),pan:[0,0,0]};schedule();
        C.text('#benchmark-state',bench.started===null?'等待真实首帧，再预热2秒…':`${bench.mode}：剩余 ${Math.max(0,Math.ceil((bench.ends-now)/1000))} 秒`);
        if(bench.mode==='gs-traffic-face'&&now>=bench.nextFace&&!bench.facePending){
          bench.facePending=true;bench.nextFace=now+10000;const running=bench;
          C.face.recognizeDemo('obama-2012.jpg',false).then(event=>running.faceEvents.push(event)).catch(error=>running.faceEvents.push({error:error.message})).finally(()=>running.facePending=false);
        }
      }else finish();
    }
    if(active&&dirty&&socket?.readyState===1&&socket.bufferedAmount<8192&&now-lastSent>=22){
      socket.send(JSON.stringify({op:'camera',request_id:++requestId,client_time:changedAt,state:camera}));dirty=false;lastSent=now;
    }
    frameTimes=frameTimes.filter(t=>now-t<2000);C.text('#scene-web-fps',frameTimes.length>1?((frameTimes.length-1)*1000/(now-frameTimes[0])).toFixed(1):'0.0');
    requestAnimationFrame(tick);
  }
  $('#benchmark-start').onclick=benchmark;requestAnimationFrame(tick);C.scene={start,stop,reset};
})();
