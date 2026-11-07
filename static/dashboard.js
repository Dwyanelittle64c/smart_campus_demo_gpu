/* 看板只展示现有业务统计；不生成模拟流量、天气或校园资产数据。 */
(() => {
  const C=Campus;
  function clock(){
    const now=new Date();
    C.text('#dashboard-time',now.toLocaleTimeString('zh-CN',{hour12:false}));
    C.text('#dashboard-date',now.toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',weekday:'short'}));
  }
  clock();setInterval(clock,1000);
  // SVG为二维看板绘制，场景和网络推理仍全部由GPU服务器完成。
  C.trafficChart=stat=>{
    const chart=C.$('#traffic-chart');if(!chart)return;
    chart.replaceChildren();
    function svg(tag,attrs,text){
      const node=document.createElementNS('http://www.w3.org/2000/svg',tag);
      for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);
      if(text!==undefined)node.textContent=text;
      chart.append(node);return node;
    }
    for(const y of [20,55,90])svg('line',{x1:15,y1:y,x2:290,y2:y,stroke:'#163a56','stroke-width':1});
    if(!stat?.buckets?.length){
      svg('text',{x:150,y:60,'text-anchor':'middle',fill:'#4f7897','font-size':10},'暂无新增目标统计');return;
    }
    const end=Math.floor(stat.elapsed/60),start=Math.max(0,end-7),buckets=[];
    for(let minute=start;minute<=end;minute++)buckets.push(stat.buckets.find(b=>b.minute===minute)||{minute,person:0,vehicle:0,bicycle:0});
    const maximum=Math.max(1,...buckets.flatMap(b=>[b.person,b.vehicle,b.bicycle]));
    buckets.forEach((bucket,i)=>{
      const x=20+i*270/buckets.length,slot=270/buckets.length;
      ['person','vehicle','bicycle'].forEach((key,j)=>{
        const value=bucket[key],height=value/maximum*65;
        const rect=svg('rect',{x:x+j*slot*.2,y:90-height,width:Math.min(16,slot*.17),height,fill:['#36cbe3','#428bf1','#e9b76e'][j]});
        const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=`第${bucket.minute}分钟 ${['行人','车辆','自行车'][j]} ${value}`;rect.append(title);
      });
      svg('text',{x:x+slot*.22,y:108,'text-anchor':'middle',fill:'#5b8bad','font-size':9},`${bucket.minute}m`);
    });
    svg('text',{x:290,y:12,'text-anchor':'end',fill:'#608fb0','font-size':9},`上界 ${maximum}`);
  };
  C.trafficChart(null);
})();
