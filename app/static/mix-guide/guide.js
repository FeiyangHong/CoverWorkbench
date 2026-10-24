(() => {
'use strict';
const root=document.getElementById('mixGuideRoot');if(!root)return;
const base='/mix-guide/';
const clearPositions={"reverb": {"predelay": [9, 48], "space": [36, 48], "decay": [51, 48], "brightness": [66, 48], "ducking": [80, 48], "mix": [93, 48]}, "delay": {"time": [12, 48], "sync": [31, 48], "feedback": [51, 48], "wet": [72, 48], "mix": [91, 48]}, "eq": {"shape": [14, 48], "freq": [38, 48], "gain": [62, 48], "q": [86, 48]}, "comp": {"threshold": [14, 48], "ratio": [38, 48], "attack": [62, 48], "release": [86, 48]}, "deess": {"threshold": [14, 48], "range": [38, 48], "mode": [62, 48], "audition": [86, 48]}};
const crops={"reverb": {"image": "reverb-controls.png", "crop": [0, 36, 853, 184], "full": [853, 616]}, "delay": {"image": "delay-controls.png", "crop": [300, 250, 930, 395], "full": [962, 576]}, "eq": {"image": "eq-controls.png", "crop": [390, 345, 860, 505], "full": [902, 540]}, "comp": {"image": "comp-controls.png", "crop": [10, 245, 645, 400], "full": [742, 611]}, "deess": {"image": "deess-controls.png", "crop": [18, 195, 448, 395], "full": [642, 420]}};
let imageMode='clear', audioDemo=null;
const plugins={
 routing:{name:'Studio One · 混音台',image:'routing.svg',type:'路由示意图',source:'https://pae-web.presonusmusic.com/downloads/products/pdf/StudioOne3ReferenceManual_12102015.pdf',points:[
 ['plateSend','Vocal Plate Send','这条人声的混响发送量',18,55,'在主声通道的「发送」找到 Vocal Plate。向下调，送入混响的人声就更少。其他人声的发送量保持各自设置。'],
 ['delaySend','Vocal Delay Send','这条人声的回声发送量',18,69,'在主声通道的「发送」找到 Vocal Delay，旧工程可能叫 Vocal Timeless。想只在句尾出现回声，可以给发送量画自动化。'],
 ['plateReturn','Vocal Plate Fader','所有混响的返回音量',65,39,'降低 Vocal Plate 效果通道的推子，所有送入这条效果通道的混响都会一起变轻。'],
 ['delayMute','M / Mute','检查延迟返回静音',86,71,'检查 Vocal Delay 效果通道的 M。Studio Vocal Delay 初始模板的延迟返回默认静音；需要回声时再取消静音。']]},
 reverb:{name:'FabFilter Pro-R 2',image:'pro-r2.png',type:'插件实拍',source:'https://www.fabfilter.com/help/pro-r/using/maincontrols',points:[
 ['space','Space','空间与衰减时间',49.6,16.6,'Space 同时改变空间模型和衰减时间，中央黄色秒数是最终混响时间。缩短后，句尾消失得更快。'],
 ['decay','Decay Rate','微调尾音长度',56.5,11,'在选定 Space 后，调低 Decay Rate 缩短尾音；它是比例，不是秒数。读取 Space 中央的最终秒数。'],
 ['predelay','Predelay','原声与混响之间的间隔',6.2,16.6,'增加 Predelay，让歌词先出现、混响稍后进入。少量预延迟能帮助保留字头清晰度。'],
 ['brightness','Brightness','混响尾音的明暗',65.4,13,'降低可让混响更暗、更柔和。它改变的是混响音色；主声本体的高频仍由主声 EQ 决定。'],
 ['ducking','Ducking','唱的时候让混响退后',84.8,15.6,'增加 Ducking 时，输入人声出现会压低混响，句间再浮现。过多会让空间感忽隐忽现。'],
 ['mix','Mix','发送效果使用纯湿声',93.4,15.4,'在当前发送路由中，Mix 通常设为 100%。效果多少主要用发送量和返回推子控制；若直接插在人声上，不能照搬这个规则。']]},
 delay:{name:'FabFilter Timeless 3',image:'timeless3.png',type:'插件实拍',source:'https://www.fabfilter.com/help/timeless/using/delaycontrols',points:[
 ['time','Delay / Delay Offset','每次回声的间隔',49.9,53.5,'未同步时调整毫秒；开启 Delay Sync 后按宿主速度同步，主旋钮成为 Offset。Sync 设 1/8 或 1/4 后，Offset 100% 对应所选时值。'],
 ['sync','Delay Sync','按歌曲节拍重复',55.7,51.4,'Delay 大旋钮右上附近的小同步按钮。先确认 Studio One 歌曲 BPM，再选择 1/8 或 1/4 等时值。图中按钮位置随缩放可能略变。'],
 ['feedback','Feedback','回声衰减与重复长度',63.2,56.9,'降低 Feedback，回声更快消失；增加会延长重复。可以从 20–30% 试起。高反馈可能不断积累音量。'],
 ['wet','Wet Level','湿声输出电平',83.4,56.9,'Wet 旋钮设置回声本身的输出电平。旁边的 Mix 滑条另行控制干湿比例；Wet 的电平不是 Mix 百分比。'],
 ['mix','Mix','发送效果使用纯湿声',89,56.9,'Wet 旋钮右侧的 Mix 滑条控制干湿比例。当前发送路由中通常设为 100%，再用主声发送量控制回声多少。']]},
 eq:{name:'FabFilter Pro-Q 3',image:'pro-q3.png',type:'插件实拍',source:'https://www.fabfilter.com/help/ffproq3-manual.pdf',points:[
 ['freq','Freq','选择要处理的频率',59.2,80.2,'先选中一个频点，下方显示对应控制。Freq 选择频率；左右拖动图中的点也能改变频率。'],
 ['gain','Gain','增强或削弱多少',68.5,78.9,'向下削弱，向上增强。首次用 Bell 较宽地调整 1–2 dB，旁通比较。低切滤波器不使用 Gain 调节。'],
 ['q','Q','影响范围的宽窄',78.5,80.2,'Q 小，范围更宽；Q 大，范围更窄。音色调整从较宽的范围开始，避免对每个正常谐波都做窄削。'],
 ['shape','Bell / Shape','选择滤波形状',50.4,80.8,'Bell 用于局部增减，Low Cut 用于低切，High Shelf 用于高频整体增减。先选中频点，再展开形状菜单。']]},
 comp:{name:'FabFilter Pro-C 2',image:'pro-c2.png',type:'插件实拍',source:'https://www.fabfilter.com/downloads/pdf/help/ffproc2-manual.pdf',points:[
 ['threshold','Threshold','从多响开始压缩',10.1,47.1,'通常向下降低阈值会让更多声音触发压缩。看 GR（增益衰减），并听弱句是否仍有起伏。'],
 ['ratio','Ratio','压缩的力度',25.3,47.1,'比例越高，超过阈值的部分受到更强控制。从 2:1–3:1 的温和比例试起；不同 Style 下可用参数会不同。'],
 ['attack','Attack','多快开始压缩',51.9,47.1,'越快，字头越容易被压住。可以从 10–30 ms 试听；出现发闷或失去力度时，尝试放慢。'],
 ['release','Release / Auto Release','多快恢复音量',66.8,47.1,'Release 决定压缩后多久恢复。启用 Auto Release 时由插件自动调整。注意听是否有不自然的抽吸感。']]},
 deess:{name:'FabFilter Pro-DS',image:'pro-ds.png',type:'插件实拍',source:'https://www.fabfilter.com/help/pro-ds/using/basiccontrols',points:[
 ['threshold','Threshold','齿音触发门槛',13.1,59,'调低，让 s、sh 等齿音能被抓住；结合检测试听，避免元音也经常被处理。'],
 ['range','Range','最多减轻多少齿音',32.4,59,'控制去齿音幅度，可从 2–4 dB 的范围试起。咬字变含糊时减小 Range 或提高 Threshold。'],
 ['mode','Single Vocal','单条人声检测模式',51.7,67.4,'独立人声通道使用 Single Vocal。Allround 用于更一般的素材；它的检测方式不同。'],
 ['audition','Audition','试听检测频段',23,89.3,'打开下方 Audition，检查所选检测频段里是否主要是齿音。它用于寻找范围，调整完成后关闭。']]}
};
const goals=[
 ['tail','space','混响拖尾太长','上一句的尾音盖住了下一句。','reverb','space','缩短 Space；选好空间后，用 Decay Rate 微调。','最终尾音约 1–2 秒作为试调起点。','在句尾和下一句开始处听：空间还在，歌词没有被拖尾盖住。','仅降低发送量会变轻，但不会改变尾音本身的长度。'],
 ['wash','space','混响太多、人声发远','希望更贴近、更干净。','routing','plateSend','先降低这条主声的 Vocal Plate 发送量。','从当前值每次降低 2–3 dB 比较。','把伴奏一起播放，听主声是否靠前而不显得完全干燥。','如果所有人声都太湿，可降低 Vocal Plate 返回推子；它会一起影响其他声部。'],
 ['clarity','space','有空间感，但歌词不清楚','字头被混响包住了。','reverb','predelay','适当增加 Predelay，让原声先出来。','可从 20–50 ms 试起。','听辅音和字头是否更清楚，同时句尾仍有空间。','太长会像多出一次独立回声；也要检查尾音时间和发送量。'],
 ['brightverb','space','混响尾音刺耳','s、sh 的尾音被拉得很亮。','reverb','brightness','降低 Brightness，让混响尾音暗一些。','每次少量向下调整。','听尾音是否柔和，同时主声没有变闷。','如果主声本体就刺耳，应处理主声的 Pro-Q 3 或 Pro-DS。'],
 ['duck','space','唱时干净，停下来有尾音','想保留句间的空间。','reverb','ducking','适当增加 Ducking。','从小量开始，循环一句带停顿的歌词。','听有歌词时混响退后、停顿时自然浮现。','过多可能出现效果声忽大忽小，先确认发送量不过大。'],
 ['echo','delay','回声重复太久','一句结束后还在不断重复。','delay','feedback','降低 Feedback，让重复更快消失。','可以从 20–30% 试起。','听句尾重复是否自然衰减，不覆盖下一句。','Feedback 决定衰减；想只让回声轻一点，降低延迟发送量。'],
 ['rhythm','delay','回声想跟着节拍走','想让每次重复落在节奏上。','delay','sync','开启 Delay Sync，选择 1/8 或 1/4；Offset 先用 100%。','先核对 Studio One 的歌曲 BPM。','听每次重复是否与鼓点和句尾呼应。','同步使用宿主 BPM，不能自动判断你的音频实际速度。'],
 ['quietecho','delay','回声太响、抢歌词','回声存在感太强。','routing','delaySend','降低这条主声的 Vocal Delay 发送量。','从当前值每次降低 2–3 dB 比较。','先让回声清楚可闻，再收回到伴奏中自然的位置。','旧工程可能叫 Vocal Timeless；返回推子会影响所有送入的人声。'],
 ['noecho','delay','怎么调都听不到回声','先检查静音与路由。','routing','delayMute','检查返回通道 M、发送启用状态和发送电平。','Studio Vocal Delay 模板的延迟返回默认静音。','确认能听见后，逐步降低到合适的效果量。','还要检查 Timeless 是否旁通，以及 Wet 湿声电平与 Mix 干湿比例是否合适。'],
 ['ending','delay','只想在句尾加回声','句中清楚，最后一个字有重复。','routing','delaySend','为 Vocal Delay 发送量画自动化：句中低、句尾高、随后收回。','先只处理一句，确认自动化读取模式。','听句尾的回声能接住空隙，下一句又恢复干净。','发送提高的时间要覆盖目标字；回声的重复间隔仍由 Timeless 决定。'],
 ['mud','tone','人声闷、糊、挤在一起','低中频堆得太厚。','eq','freq','在人声 Pro-Q 3 检查 200–500 Hz，用 Bell 较宽地小幅削减。','先试 −1 至 −3 dB，Q 约 0.7–1.4。','带伴奏比较：歌词更清楚，但没有失去温暖和厚度。','不是每条人声都需要削这里；薄了就退回。'],
 ['harsh','tone','人声刺耳、像在喊','某些元音或高音扎耳朵。','eq','gain','检查约 2–5 kHz，找到刺耳处后小幅削减。','先试 −1 至 −2 dB，使用较宽的 Bell。','比较高音是否更顺，同时歌词仍然清楚。','只在 s、sh 时刺耳，优先检查 Pro-DS。不要把所有高频一起大幅削掉。'],
 ['air','tone','想增加一点空气感','人声稍暗，希望更通透。','eq','shape','用 High Shelf 在约 10–14 kHz 轻微提升。','从 +1 dB 开始。','听是否更开阔，同时没有把齿音和分离伪影一起放大。','先确认问题不是人声太小或混响太多；增加高频并不总能解决。'],
 ['nose','tone','鼻音、箱子感明显','某段中频特别突出。','eq','freq','检查约 700 Hz–1.5 kHz，用 Bell 找到突出处再小幅削减。','每次约 −1 dB 试听。','听鼻音减轻后，声音仍有辨识度。','频谱上的峰可能是正常谐波；不用把曲线削平。'],
 ['level','dynamics','人声忽大忽小','响句太冲，弱句又被伴奏盖住。','comp','threshold','先保留风格设置，调整 Threshold，观察 GR。','响句先尝试约 2–4 dB 的增益衰减。','人声更稳定，但仍保留强弱表情；对比时匹配前后音量。','如果只是个别字，可以先做音量自动化；压缩不能代替所有句间平衡。'],
 ['flat','dynamics','压缩后字头没劲、发闷','想保留演唱的起音。','comp','attack','适当放慢 Attack，再检查压缩量。','可从 10–30 ms 范围试听。','听字头恢复清楚，但响句没有突然冲出来。','已经开启自动时间或特定 Style 时，先看界面里哪些参数实际可用。'],
 ['sibilance','dynamics','s、sh 的齿音太刺耳','只有辅音特别突出。','deess','range','单条主声使用 Single Vocal，调整 Threshold 与 Range。','Range 从 2–4 dB 试起。','齿音柔和了，但咬字仍清楚，没有“大舌头”的感觉。','先用 Audition 找检测范围，再关闭试听回到整段人声。'],
 ['wetmix','space','Mix、Wet 和发送量怎么分','同样调“效果多少”，影响却不同。','reverb','mix','发送效果通常用 Mix 100%；用发送量和返回推子决定效果总量。','先确认插件放在独立 FX 效果通道。','原人声保持稳定，调整发送时只有空间感随之改变。','直接插在人声上的效果器不照搬 Mix 100%；Timeless 的 Wet 电平和 Mix 百分比也不同。']
].map(([id,category,title,symptom,plugin,control,action,start,listen,note])=>({id,category,title,symptom,plugin,control,action,start,listen,note}));
const cats={all:'全部',space:'空间与混响',delay:'回声与节奏',tone:'音色与频段',dynamics:'动态与齿音'};
let selected=goals[0],selectedPlugin=selected.plugin,selectedControl=selected.control,category='all',query='';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
root.innerHTML=`<div class="mg-hero"><div><span class="mg-eyebrow">THE MIXING COMPANION</span><h2>听到问题，找到旋钮。</h2><p>从你想改变的声音出发，在 Studio One 里一步步调整。</p></div><div class="mg-hero-note"><span>01 选目标</span><span>02 看位置</span><span>03 听变化</span></div></div><div class="mg-intro"><span>图示只用于对照学习，调整请在 Studio One 中完成。</span><a href="/mix-guide/index.html" target="_blank" rel="noopener">独立窗口打开 ↗</a></div><div class="mg-layout"><aside class="mg-browser"><label class="mg-search"><span>你想调整什么？</span><input id="mgSearch" type="search" placeholder="例如：混响、刺耳、句尾…" autocomplete="off"></label><div class="mg-categories" role="group" aria-label="混音问题分类">${Object.entries(cats).map(([id,name])=>`<button data-mg-category="${id}" aria-pressed="${id==='all'}">${name}</button>`).join('')}</div><div id="mgGoals" class="mg-goals" role="group" aria-label="选择声音问题"></div></aside><div class="mg-content"><div class="mg-top-grid"><article id="mgAdvice" class="mg-advice" aria-live="polite"></article><section id="mgAudioDemo" class="mg-audio" aria-label="混音前后试听"></section></div><section class="mg-visual"><div class="mg-visual-heading"><div><span class="mg-eyebrow">FIND THE CONTROL</span><h3>照着界面找位置</h3></div><div class="mg-visual-actions"><button id="mgBackToGoal" class="mg-secondary" hidden>回到目标图示</button><button id="mgZoom" class="mg-secondary">完整界面 ↗</button></div></div><div id="mgPluginTabs" class="mg-plugin-tabs" role="group" aria-label="插件图示">${Object.entries(plugins).map(([id,p])=>`<button data-mg-plugin="${id}" aria-pressed="false">${esc(p.name.replace('FabFilter ',''))}</button>`).join('')}</div><div class="mg-view-mode" role="group" aria-label="图示清晰度"><button data-mg-view="clear" aria-pressed="true">清晰控件图</button><button data-mg-view="photo" aria-pressed="false">实拍局部对照</button><span>完整界面按需打开，局部截图不拉伸放大。</span></div><div class="mg-preview-grid"><div class="mg-figure-column"><div id="mgImage" class="mg-image"></div><p id="mgImageCaption" class="mg-caption"></p></div><div class="mg-parameter-column"><div id="mgControls" class="mg-controls" role="group" aria-label="选择要了解的旋钮"></div><div id="mgControlDetail" class="mg-control-detail" aria-live="polite"></div></div></div><div class="mg-image-bottom"><small>图中参数是界面示例；试调数值需要按声库、伴奏和歌曲速度判断。</small><a id="mgOfficial" target="_blank" rel="noopener noreferrer">官方参数说明 ↗</a></div></section><section class="mg-basics"><h3>每次只改一件事，耳朵会更容易判断。</h3><div><p><b>先找对通道</b>主声的 EQ 改主声音色；Vocal Plate 改混响，Vocal Delay 改回声。</p><p><b>循环 15–30 秒</b>选一段带完整歌词与句尾停顿的片段，带着伴奏听。</p><p><b>匹配前后音量</b>旁通比较，避免把“更响”误当成“更好”。每次改一个参数。</p></div></section></div></div><dialog id="mgZoomDialog" class="mg-zoom-dialog" aria-labelledby="mgZoomTitle"><div class="mg-zoom-head"><strong id="mgZoomTitle">插件图示</strong><div><button id="mgZoomOut" aria-label="缩小图示">−</button><output id="mgZoomValue">100%</output><button id="mgZoomIn" aria-label="放大图示">＋</button><button id="mgZoomClose">关闭</button></div></div><div class="mg-zoom-scroll"><div id="mgZoomImage" class="mg-image"></div></div><p class="mg-caption">完整实拍界面 · 100% 对应原始像素；继续放大不会增加截图细节。可滚动查看，按 Esc 关闭。</p><div id="mgZoomDetail" class="mg-control-detail" aria-live="polite"></div></dialog>`;
const $=s=>root.querySelector(s),$$=s=>[...root.querySelectorAll(s)];
const nativePanel=document.createElement('section');nativePanel.className='mg-audio mg-native';nativePanel.id='mgNative';nativePanel.setAttribute('aria-label','真实 FabFilter 人声试听');$('.mg-content').prepend(nativePanel);
const nativeDemo=window.CWNativeMix?.mount(nativePanel);
function renderGoals(){const matches=goals.filter(g=>(category==='all'||g.category===category)&&`${g.title} ${g.symptom} ${g.action} ${plugins[g.plugin].name}`.toLowerCase().includes(query));$('#mgGoals').innerHTML=matches.length?matches.map(g=>`<button data-mg-goal="${g.id}" aria-pressed="${g.id===selected.id}"><strong>${esc(g.title)}</strong><small>${esc(g.symptom)}</small><span>↗</span></button>`).join(''):'<p class="mg-empty">没有找到这个问题。试试“混响”“回声”“齿音”，或切换到“全部”。</p>';$$('[data-mg-goal]').forEach(b=>b.onclick=()=>{selected=goals.find(g=>g.id===b.dataset.mgGoal);selectedPlugin=selected.plugin;selectedControl=selected.control;renderGoals();renderAdvice();renderPlugin();audioDemo?.selectForGoal(selected.id,selected.category);});}
function renderAdvice(){const g=selected,p=plugins[g.plugin];const path=g.plugin==='routing'?'混音台 → 主声发送 / FX 返回':(['reverb','delay'].includes(g.plugin)?`混音台 → ${g.plugin==='reverb'?'Vocal Plate':'Vocal Delay / Vocal Timeless'} → 插入 → ${p.name}`:`混音台 → 目标人声通道 → 插入 → ${p.name}`);$('#mgAdvice').innerHTML=`<div class="mg-advice-heading"><span class="mg-pill">${cats[g.category]}</span><small>建议起点 · 试听后调整</small></div><h3>${esc(g.title)}</h3><p class="mg-action">${esc(g.action)}</p><div class="mg-path">${esc(path)}</div><div class="mg-listen-grid"><div><span>先这样试</span><p>${esc(g.start)}</p></div><div><span>调完听什么</span><p>${esc(g.listen)}</p></div></div><p class="mg-watch"><b>容易混淆</b>${esc(g.note)}</p>`;}
function figure(full=false){
 const p=plugins[selectedPlugin];let src=base+'images/'+p.image,positions={};
 if(!full&&selectedPlugin!=='routing'){
  if(imageMode==='clear'){src=base+'diagrams/'+selectedPlugin+'.svg';positions=clearPositions[selectedPlugin];}
  else{const c=crops[selectedPlugin],box=c.crop;src=base+'images/'+c.image;positions=Object.fromEntries(p.points.map(([id,,,x,y])=>[id,[(x*c.full[0]/100-box[0])/(box[2]-box[0])*100,(y*c.full[1]/100-box[1])/(box[3]-box[1])*100]]));}
 }
 const alt=full?p.type:imageMode==='clear'?'原创清晰控件教学示意（非插件截图）':'插件实拍局部';
 return `<img src="${src}" alt="${esc(p.name)} · ${alt}" draggable="false">${p.points.map(([id,en,cn,x,y],i)=>{const pos=positions[id]||[x,y];return `<button class="mg-hotspot ${id===selectedControl?'active':''}" style="left:${pos[0]}%;top:${pos[1]}%" data-mg-point="${id}" aria-label="${esc(en+'：'+cn)}" aria-pressed="${id===selectedControl}">${i+1}</button>`;}).join('')}`;
}
function bindPoints(container){container.querySelectorAll('[data-mg-point]').forEach(b=>b.onclick=()=>{selectedControl=b.dataset.mgPoint;renderControl();});}
function renderPlugin(){const p=plugins[selectedPlugin];$$('[data-mg-plugin]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mgPlugin===selectedPlugin)));$('#mgImage').innerHTML=figure();bindPoints($('#mgImage'));$('#mgBackToGoal').hidden=selectedPlugin===selected.plugin;$('#mgImageCaption').textContent=p.name+' · '+(selectedPlugin==='routing'?'路由示意，非实际界面':imageMode==='clear'?'原创控件教学图，非插件截图；实际位置请切换实拍对照。':'本机界面局部，保持原始像素；英文参数名可在右侧直接阅读。');$('#mgImage').style.maxWidth=selectedPlugin==='routing'?'640px':imageMode==='photo'?(crops[selectedPlugin].crop[2]-crops[selectedPlugin].crop[0])+'px':'960px';$('#mgOfficial').href=p.source;renderControl();}
function renderControl(){const p=plugins[selectedPlugin],point=p.points.find(v=>v[0]===selectedControl)||p.points[0];selectedControl=point[0];$('#mgControls').innerHTML=p.points.map(([id,en,cn],i)=>`<button data-mg-control="${id}" aria-pressed="${id===selectedControl}"><span>${i+1}</span>${esc(en)}<small>${esc(cn)}</small></button>`).join('');$$('[data-mg-control]').forEach(b=>b.onclick=()=>{selectedControl=b.dataset.mgControl;renderControl();});$$('[data-mg-point]').forEach(b=>{const active=b.dataset.mgPoint===selectedControl;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});const text=`<span class="mg-eyebrow">${esc(point[1])}</span><h4>${esc(point[2])}</h4><p>${esc(point[5])}</p>`;$('#mgControlDetail').innerHTML=text;$('#mgZoomDetail').innerHTML=text;}
$('#mgBackToGoal').onclick=()=>{selectedPlugin=selected.plugin;selectedControl=selected.control;renderPlugin();};
let zoom=100;
function updateZoom(){const image=$('#mgZoomImage');const fullWidth=crops[selectedPlugin]?.full[0]||960;image.style.width=(fullWidth*zoom/100)+'px';$('#mgZoomValue').textContent=zoom+'%';$('#mgZoomOut').disabled=zoom<=100;$('#mgZoomIn').disabled=zoom>=250;}
$$('[data-mg-category]').forEach(b=>b.onclick=()=>{category=b.dataset.mgCategory;$$('[data-mg-category]').forEach(v=>v.setAttribute('aria-pressed',String(v===b)));renderGoals();});
$('#mgSearch').oninput=e=>{query=e.target.value.trim().toLowerCase();renderGoals();};
$$('[data-mg-plugin]').forEach(b=>b.onclick=()=>{selectedPlugin=b.dataset.mgPlugin;selectedControl=plugins[selectedPlugin].points[0][0];renderPlugin();});
$('#mgZoom').onclick=()=>{zoom=100;$('#mgZoomImage').innerHTML=figure(true);bindPoints($('#mgZoomImage'));$('#mgZoomTitle').textContent=plugins[selectedPlugin].name;updateZoom();renderControl();$('#mgZoomDialog').showModal();};
$('#mgZoomIn').onclick=()=>{zoom=Math.min(250,zoom+25);updateZoom();};$('#mgZoomOut').onclick=()=>{zoom=Math.max(100,zoom-25);updateZoom();};$('#mgZoomClose').onclick=()=>$('#mgZoomDialog').close();
$$('[data-mg-view]').forEach(button=>button.onclick=()=>{imageMode=button.dataset.mgView;$$('[data-mg-view]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));renderPlugin();});
audioDemo=window.CWMixAudio?.mount($('#mgAudioDemo'));
root.addEventListener('cw-mix-demo-control',event=>{const {plugin,control}=event.detail;if(!plugins[plugin]?.points.some(p=>p[0]===control))return;selectedPlugin=plugin;selectedControl=control;renderPlugin();});
root.addEventListener('cw-mix-play',event=>{if(event.detail==='native')audioDemo?.pause();else nativeDemo?.pause();});
document.addEventListener('visibilitychange',()=>{if(document.hidden){audioDemo?.pause();nativeDemo?.pause();}});
const panel=root.closest('.tab-panel');if(panel)new MutationObserver(()=>{if(panel.hidden){audioDemo?.pause();nativeDemo?.pause();}}).observe(panel,{attributes:true,attributeFilter:['hidden']});
renderGoals();renderAdvice();renderPlugin();audioDemo?.selectForGoal(selected.id,selected.category);
})();
