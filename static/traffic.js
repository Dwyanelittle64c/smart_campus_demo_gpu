/* 交通：服务器素材/上传/浏览器采集统一通过相同 GPU 服务，统计与画面同帧更新。 */
(() => {
  const C=Campus,$=C.$;let socket=null,expected=null,source=null,cameraTimer=null,captureBusy=false,captureSequence=0,captureGeneration=0,starting=false;
  const states={idle:'未开始',starting:'准备中',running:'检测中',paused:'已暂停',stopped:'已停止',ended:'已结束',error:'发生错误'};
  const view=new C.FrameView($('#traffic-image'),$('#traffic-placeholder'),async(meta)=>{
    if(meta.source_id!==expected)return;
    display(meta.statistics);C.text('#traffic-state','GPU 检测中');
    C.text('#traffic-info',`${meta.device} · 检测处理能力 ${meta.processing_fps.toFixed(1)} FPS · ${meta.timebase} ${meta.timestamp.toFixed(1)}秒 · 输入序号 ${meta.source_sequence}`);
    $('#traffic-module').dataset.frameId=meta.frame_id;$('#traffic-module').dataset.sourceId=meta.source_id;
  });
  function display(stat){
    if(!stat)return;
    document.querySelectorAll('[data-group]').forEach(row=>{const cells=row.querySelectorAll('td');['current','cumulative','minute_new'].forEach((key,i)=>cells[i].textContent=stat[key][row.dataset.group]);});
    C.text('#traffic-buckets',JSON.stringify(stat.buckets,null,2));
    C.trafficChart?.(stat);
  }
  function open(){
    if(!C.sid||socket?.readyState<2)return;
    const connection=C.ws('traffic');
    socket=connection;
    connection.binaryType='arraybuffer';
    connection.onopen=()=>{
      if(socket===connection)connection.send(JSON.stringify({session_id:C.sid}));
    };
    connection.onmessage=event=>{
      if(socket!==connection)return;
      if(typeof event.data==='string'){
        const message=JSON.parse(event.data);
        if(message.error)C.text('#traffic-error',message.error);
      }else view.accept(event.data);
    };
    connection.onclose=()=>{
      if(socket!==connection)return;
      socket=null;
      if(C.sid&&expected)setTimeout(open,1000);
    };
  }
  async function command(body){
    const result=await C.api('traffic/control/',{method:'POST',body});
    if(expected!==result.source_id){
      expected=result.source_id;view.close();view.reset(expected);
      $('#traffic-image').removeAttribute('src');$('#traffic-image').hidden=true;$('#traffic-placeholder').hidden=false;
    }
    display(result);C.text('#traffic-state',states[result.status]||result.status);return result;
  }
  async function stop(){
    captureGeneration++;clearInterval(cameraTimer);cameraTimer=null;C.Camera.release('traffic');
    if(source?.type==='camera'){view.close();$('#traffic-image').removeAttribute('src');$('#traffic-image').hidden=true;$('#traffic-placeholder').hidden=false;}
    if(C.sid){const result=await command({action:'stop'});C.text('#traffic-state','已停止');return result;}
  }
  async function start(spec){
    if(starting)throw new Error('交通启动中，请等待');starting=true;$('#traffic-start').disabled=true;
    try{
      if(!spec){
        const type=$('#traffic-source').value;
        if(type==='upload'){
          const file=$('#traffic-file').files[0];if(!file)throw new Error('请先选择本机视频文件');
          const form=new FormData();form.append('video',file);C.text('#traffic-state','视频上传中…');const asset=await C.api('traffic/upload/',{method:'POST',body:form});spec={type:'video',asset_id:asset.asset_id};
        }else spec=type==='rtsp'?{type,url:$('#traffic-rtsp').value}:{type,asset_id:'vtest'};
      }
      captureGeneration++;clearInterval(cameraTimer);C.Camera.release('traffic');
      if(spec.type==='camera')await C.Camera.acquire('traffic');
      source=spec;await command({action:'start',source:spec});open();C.text('#traffic-error','');
      if(spec.type==='camera'){
        captureSequence=0;
        const generation=captureGeneration,sourceId=expected;
        cameraTimer=setInterval(async()=>{
          if(captureBusy||!C.Camera.stream||socket?.readyState!==1||socket.bufferedAmount>1000000)return;
          captureBusy=true;const at=performance.now();
          try{
            const video=$('#camera-preview'),original=[video.videoWidth,video.videoHeight],scale=Math.min(1,640/video.videoWidth,480/video.videoHeight);
            const blob=await C.Camera.photo();
            const packet=await C.pack({
              protocol_version:1,
              source_id:sourceId,
              sequence:++captureSequence,
              capture_ms:at,
              timebase:'browser-monotonic-ms',
              original_resolution:original,
              resolution:[Math.round(original[0]*scale),Math.round(original[1]*scale)]
            },blob);
            // 异步编码完成后再核对代次，停用/切源期间的迟到帧不得继续上传。
            if(generation===captureGeneration&&socket?.readyState===1&&C.Camera.users.has('traffic'))socket.send(packet);
          }
          catch(error){C.text('#traffic-error',error.message);}finally{captureBusy=false;}
        },100);
      }
    }catch(error){C.text('#traffic-error',error.message);C.Camera.release('traffic');throw error;}
    finally{starting=false;$('#traffic-start').disabled=false;}
  }
  function guard(fn){return async()=>{try{await fn();}catch(error){C.text('#traffic-error',error.message);}};}
  $('#traffic-start').onclick=guard(()=>start());$('#traffic-stop').onclick=guard(stop);
  $('#traffic-pause').onclick=guard(()=>command({action:'pause'}));$('#traffic-reset').onclick=guard(async()=>{await stop();await command({action:'reset'});});
  $('#traffic-full-roi').onclick=guard(()=>command({action:'roi',roi:[0,0,1,1]}));
  $('#traffic-source').onchange=()=>{const value=$('#traffic-source').value;$('#traffic-file').hidden=value!=='upload';$('#traffic-rtsp').hidden=value!=='rtsp';};
  const overlay=$('#traffic-roi');let initial=null;
  function point(event){
    // object-fit:contain的黑边不属于原图；仅图内起点可开启ROI拖拽。
    const box=overlay.getBoundingClientRect(),image=$('#traffic-image');if(!image.naturalWidth)return null;
    const scale=Math.min(box.width/image.naturalWidth,box.height/image.naturalHeight),width=image.naturalWidth*scale,height=image.naturalHeight*scale;
    const left=(box.width-width)/2,top=(box.height-height)/2,x=(event.clientX-box.left-left)/width,y=(event.clientY-box.top-top)/height;
    return {x:Math.max(0,Math.min(1,x)),y:Math.max(0,Math.min(1,y)),inside:x>=0&&x<=1&&y>=0&&y<=1,left,top,width,height};
  }
  overlay.onpointerdown=event=>{const value=point(event);if(event.button!==0||!value?.inside)return;event.preventDefault();initial=value;overlay.setPointerCapture(event.pointerId);overlay.width=overlay.clientWidth;overlay.height=overlay.clientHeight;};
  overlay.onpointermove=event=>{if(!initial)return;const value=point(event),ctx=overlay.getContext('2d');ctx.clearRect(0,0,overlay.width,overlay.height);ctx.strokeStyle='#e9c85f';ctx.lineWidth=2;ctx.strokeRect(initial.left+initial.x*initial.width,initial.top+initial.y*initial.height,(value.x-initial.x)*initial.width,(value.y-initial.y)*initial.height);};
  overlay.addEventListener('pointerup',async event=>{
    if(!initial)return;const end=point(event),start=initial;initial=null;overlay.getContext('2d').clearRect(0,0,overlay.width,overlay.height);
    const roi=[Math.min(start.x,end.x),Math.min(start.y,end.y),Math.max(start.x,end.x),Math.max(start.y,end.y)];
    try{await command({action:'roi',roi});C.text('#traffic-error','ROI 已更新，本轮跟踪与计数重置');}catch(error){C.text('#traffic-error',error.message);}
  });
  overlay.onpointercancel=()=>initial=null;
  C.onControl(connected=>{if(!connected){socket?.close();socket=null;captureGeneration++;clearInterval(cameraTimer);C.Camera.release('traffic');C.text('#traffic-state','后端断开 / 已释放');}else if(C.capabilities.modules.traffic)open();});
  setInterval(async()=>{if(!C.sid||!C.capabilities?.modules.traffic)return;try{const result=await C.api('traffic/status/');C.text('#traffic-state',states[result.status]||result.status);if(result.error)C.text('#traffic-error',result.error);if(!expected){expected=result.source_id;view.reset(expected);}if(['stopped','ended','error','idle'].includes(result.status))display(result);}catch(error){C.text('#traffic-error',error.message);}},1000);
  C.traffic={start,stop,startDemo:()=>start({type:'video',asset_id:'vtest'})};
})();
