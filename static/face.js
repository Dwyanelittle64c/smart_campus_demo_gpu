/* 人员与历史均存 GPU 后端；照片与浏览器采集共用幂等按钮提交接口。 */
(() => {
  const C=Campus,$=C.$;let busy=false;
  async function refresh(){
    if(!C.sid||!C.capabilities?.modules.face)return;
    try{
      const events=await C.api('face/history/'),container=$('#face-history');container.replaceChildren();
      const people=await C.api('face/people/');
      const passed=events.filter(event=>event.passed).length;
      const ratio=events.length?Math.round(passed/events.length*100):0;
      C.text('#face-people-count',people.length);
      C.text('#face-event-count',events.length);
      C.text('#face-unknown-count',events.length-passed);
      C.text('#face-ratio',events.length?`${ratio}%`:'—');
      $('#face-ratio-ring').style.setProperty('--ratio',`${ratio}%`);
      if(!events.length){const p=document.createElement('p');p.className='empty';p.textContent='新实例暂无识别记录';container.append(p);}
      for(const event of events.slice(0,100)){
        const card=document.createElement('article');card.className=event.passed?'pass':'';
        const title=document.createElement('b');title.textContent=`${event.passed?'通过':'不通过'} · ${event.name}`;card.append(title);
        const time=document.createElement('time');time.textContent=event.time;card.append(time);
        const info=document.createElement('div');info.textContent=`余弦 ${event.score.toFixed(3)} / 阈值 ${event.threshold}`;card.append(info);
        for(const kind of ['scene','face','candidate']){const image=document.createElement('img');image.src=event[kind+'_url'];image.alt=kind==='candidate'?'最相似登记候选':'现场快照';card.append(image);}
        card.onclick=()=>show(event);container.append(card);
      }
    }catch(error){C.text('#face-error',error.message);}
  }
  function show(event){
    C.text('#result-title',`${event.passed?'通过':'不通过'} · ${event.name}`);$('#result-title').className=event.passed?'pass':'fail';
    C.text('#result-description',`余弦相似度 ${event.score.toFixed(4)}，阈值 ${event.threshold}。${event.passed?'':'最相似候选未通过匹配：'+event.candidate_name}`);
    ['scene','face','candidate'].forEach(kind=>$('#result-'+kind).src=event[kind+'_url']);C.text('#result-candidate-label',event.passed?'登记人脸':'最相似候选，未通过');
    if(!$('#result-dialog').open)$('#result-dialog').showModal();
  }
  async function submit(action,blob,name='',popup=true){
    // 一次按钮动作生成一个幂等ID；服务端也合并同ID的在途/持久结果。
    if(busy)throw new Error('人脸任务处理中，请等待');
    if(!blob)throw new Error('请先选择照片');busy=true;
    document.querySelectorAll('#face-dialog button,#people-dialog button').forEach(b=>b.disabled=true);
    const form=new FormData();
    form.append('action',action);
    form.append('photo',blob,'photo.jpg');
    form.append('name',name);
    form.append('request_id',crypto.randomUUID().replaceAll('-',''));
    try{
      const result=await C.api('face/submit/',{method:'POST',body:form});
      if(action==='recognize'){
        if(popup)show(result);
        await refresh();
      }
      return result;
    }finally{
      busy=false;
      document.querySelectorAll('#face-dialog button,#people-dialog button').forEach(button=>button.disabled=false);
    }
  }
  async function people(){
    const records=await C.api('face/people/'),container=$('#people-list');container.replaceChildren();
    if(!records.length){const p=document.createElement('p');p.textContent='当前为空库，请录入单人照片';container.append(p);}
    for(const person of records){
      const row=document.createElement('div');row.className='person';const image=document.createElement('img');image.src=person.face_url;image.alt='登记人脸';
      const name=document.createElement('span');name.textContent=person.name;const button=document.createElement('button');button.textContent='删除人员';button.className='danger';
      button.onclick=async()=>{try{await C.api('face/delete/',{method:'POST',body:{id:person.id}});await people();}catch(error){C.text('#enroll-error',error.message);}};
      row.append(image,name,button);container.append(row);
    }
  }
  function guard(selector,fn){return async()=>{C.text(selector,'');try{await fn();}catch(error){C.text(selector,error.message);}};}
  async function ensureDemo(){
    const records=await C.api('face/people/');if(records.some(p=>p.name==='公开示例 · Barack Obama'))return;
    await submit('enroll',await C.sample('obama-2009.jpg'),'公开示例 · Barack Obama',false);
  }
  async function recognizeDemo(name,popup=true){return submit('recognize',await C.sample(name),'',popup);}
  $('#people-open').onclick=guard('#face-error',async()=>{await people();$('#people-dialog').showModal();});
  $('#face-open').onclick=()=>$('#face-dialog').showModal();
  $('#enroll-submit').onclick=guard('#enroll-error',async()=>{await submit('enroll',$('#enroll-file').files[0],$('#enroll-name').value);await people();C.text('#enroll-error','录入完成');});
  $('#enroll-demo').onclick=guard('#enroll-error',async()=>{await ensureDemo();await people();C.text('#enroll-error','公开示例录入完成（2009不同拍摄用于登记）');});
  $('#recognize-submit').onclick=guard('#recognize-error',()=>submit('recognize',$('#recognize-file').files[0]));
  $('#recognize-demo-same').onclick=guard('#recognize-error',()=>recognizeDemo('obama-2012.jpg'));
  $('#recognize-demo-other').onclick=guard('#recognize-error',()=>recognizeDemo('biden-2021.jpg'));
  $('#face-camera-open').onclick=guard('#recognize-error',()=>C.Camera.acquire('face'));
  $('#face-camera-submit').onclick=guard('#recognize-error',async()=>submit('recognize',await C.Camera.photo()));
  $('#face-camera-close').onclick=()=>C.Camera.release('face');$('#face-dialog').addEventListener('close',()=>C.Camera.release('face'));
  $('#history-clear').onclick=guard('#face-error',async()=>{await C.api('face/clear/',{method:'POST',body:{}});await refresh();});
  C.onControl(connected=>{if(connected)refresh();else C.Camera.release('face');});
  C.face={ensureDemo,recognizeDemo,refresh};
})();
