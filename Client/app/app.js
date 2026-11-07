import {BattleFX} from './battle_fx.js';
import {VARIETY_KEYS,frontSprite,varietyKey,varietyDefinition,pokemonName,eventPokemon,followerPokemon} from './varieties.js';
import {WorldRenderer} from './renderer.js';
import {GameAudio} from './audio.js';
import {mountAudioControls} from './audio_controls.js';
let aiDashboard=null,aiDashboardView='activity';
const audio=new GameAudio();
let audioControls=null,audioSavePending=null,audioSaving=false;
const $=id=>document.getElementById(id);
const h=(tag,attributes={},...children)=>{const node=document.createElement(tag);for(const [key,value] of Object.entries(attributes)){if(value==null)continue;if(key==='class')node.className=value;else if(key.startsWith('on'))node.addEventListener(key.slice(2).toLowerCase(),value);else if(key==='text')node.textContent=value;else if(key==='disabled')node.disabled=!!value;else if(key==='checked')node.checked=!!value;else node.setAttribute(key,String(value));}for(const child of children.flat()){if(child!=null)node.append(child instanceof Node?child:document.createTextNode(String(child)));}return node;};
const button=(text,fn,classes='secondary',disabled=false)=>h('button',{type:'button',class:classes,onClick:fn,disabled},text);
const TYPES=['Normal','Fighting','Flying','Poison','Ground','Rock','Bug','Ghost','Steel','Mystery','Fire','Water','Grass','Electric','Psychic','Ice','Dragon','Dark','Fairy'];
let content,config,renderer,ws,connecting=null,hello=null,session=null,state=null,mode='login',starter='fr_1',loggingIn=false,deliberateLogout=false,authAttempt=0,authTimer=null;
let battleFX=null,battleSubmitting=false,battleSubmitTimer=null,battleEffectsDisabled=false;
let surfPending=null;
let modalKind='',activeBattle=null,trade=null,invite=null,mapSerial=0,own=null,channel='general',sequence=0,pendingMove=0,nextStep=0;
const chats={general:[],trade:[]},mutedNames=new Set(),keys=new Map();
let inspectedUid=null,reminderView=null,collectionView='party',collectionSearch='',collectionVariety='all',dexSearch='',dexFilter='all';
function toast(message,kind='info'){const node=h('div',{class:'toast '+kind},message);$('toasts').append(node);while($('toasts').children.length>5)$('toasts').firstChild.remove();setTimeout(()=>node.remove(),6500);}
function money(n){return '₽ '+Number(n||0).toLocaleString();}
// The legacy back argument is intentionally ignored: both battle sides use fronts.
function sprite(mon,back=false){return frontSprite(content,mon);}
function monName(mon){return pokemonName(content,mon);}
function varietyBadge(mon){const v=varietyDefinition(content,mon);return v.key==='normal'?null:h('span',{class:'variety-badge variety-'+v.key,style:'--variety-color:'+v.color,title:v.label+' variety'},v.label);}
function send(op,data={}){if(!ws||ws.readyState!==WebSocket.OPEN||!session){toast('The world connection is not ready.','error');return false;}ws.send(JSON.stringify({op,...data}));return true;}
function connection(status,text){$('status-dot').className='status-dot '+status;$('connection-label').textContent=text;$('connection-address').textContent=config?config.host+':'+config.port+(config.tls?' · TLS':' · Private LAN / localhost'):'';}
async function connect(){
 if(connecting)return connecting;if(ws?.readyState===WebSocket.OPEN&&hello)return hello;
 connecting=new Promise((resolve,reject)=>{
  connection('','Connecting to world…');hello=null;const socket=new WebSocket(config.endpoint,'nxt.v1');ws=socket;
  const timer=setTimeout(()=>{socket.close();reject(Error('The world server did not respond. Start the server and check Client/config.ini.'));},12000);
  socket.addEventListener('message',event=>{if(ws!==socket||socket.readyState!==WebSocket.OPEN)return;let packet;try{packet=JSON.parse(event.data);}catch{toast('The server sent an unreadable packet.','error');return;}
   if(packet.type==='hello'){clearTimeout(timer);hello=packet;connection('online',packet.world+' · '+packet.online+' online');$('auth-submit').disabled=loggingIn;resolve(packet);}else handle(packet);
  });
  socket.addEventListener('open',()=>{});
  socket.addEventListener('error',()=>{clearTimeout(timer);reject(Error('Cannot reach the world server. Check its address, firewall and TLS certificate.'));});
  socket.addEventListener('close',()=>{clearTimeout(timer);if(ws!==socket)return;hello=null;setAuthBusy(false);connection('offline','World connection closed');
   if(session&&!deliberateLogout){surfPending=null;resetBattlePresentation();mapSerial++;audio.setScene('disconnected');keys.clear();renderer.resetSession?.();renderer.active=false;closeModal(true);$('battle-dialog').close();$('audio-dialog').close();$('disconnect-overlay').classList.remove('hidden');}
   else if(!session)$('auth-submit').textContent=mode==='register'?'Create account & enter':'Reconnect & enter world';
   reject(Error('The world connection was closed. Reconnect to try again.'));
  });
 });
 try{return await connecting;}finally{connecting=null;}
}
function setAuthBusy(busy){if(!busy){clearTimeout(authTimer);authTimer=null;}loggingIn=busy;for(const id of ['username','password','home','appearance','login-tab','register-tab','auth-submit'])$(id).disabled=busy;for(const choice of $('starters').children)choice.disabled=busy;}
async function authenticate(event){event.preventDefault();if(loggingIn)return;
 // Freeze exactly the visible choices before any network wait. Region and starter
 // are independent selections; reconnecting must never silently substitute either.
 const attempt=++authAttempt,request={op:'auth',mode,username:$('username').value.trim(),password:$('password').value,pack:content.pack,home:$('home').value,starter,appearance:Number($('appearance').value)};
 setAuthBusy(true);$('auth-error').textContent='';$('auth-submit').textContent=request.mode==='register'?'Creating your trainer…':'Entering world…';
 try{const greeting=await connect();if(attempt!==authAttempt)return;if(greeting.pack!==content.pack)throw Error('This client content pack does not match the server. Install the client supplied with this server build.');
  if(!ws||ws.readyState!==WebSocket.OPEN)throw Error('The world connection was closed. Reconnect to try again.');const socket=ws;socket.send(JSON.stringify(request));
  authTimer=setTimeout(()=>{if(attempt!==authAttempt||ws!==socket||!loggingIn)return;authAttempt++;setAuthBusy(false);hello=null;socket.close(1000,'Authentication response timed out');$('auth-error').textContent=request.mode==='register'?'No account creation result arrived. The account may already exist: choose Log in and use the same username and password.':'No login result arrived. Reconnect and try logging in again.';$('auth-submit').textContent=mode==='register'?'Create account & enter':'Reconnect & enter world';},45000);
 }catch(error){if(attempt!==authAttempt)return;setAuthBusy(false);$('auth-error').textContent=error.message;$('auth-submit').textContent=mode==='register'?'Create account & enter':'Enter world';}
}
function setMode(value){if(loggingIn)return;mode=value;for(const id of ['login','register']){$(id+'-tab').classList.toggle('selected',id===mode);$(id+'-tab').setAttribute('aria-selected',String(id===mode));}$('registration-options').classList.toggle('hidden',mode!=='register');$('login-title').textContent=mode==='register'?'Every trainer starts somewhere.':'Welcome back, trainer.';$('login-description').textContent=mode==='register'?'Choose a home region and your first partner. Any partner can start in either region.':'Your team is waiting. Connect to begin.';$('auth-submit').textContent=mode==='register'?'Create account & enter':'Enter world';$('password').autocomplete=mode==='register'?'new-password':'current-password';$('auth-error').textContent='';}
function registrationSummary(){$('registration-summary').textContent='Your first partner: '+content.species[starter].name+' · Starting region: '+$('home').value;$('registration-surf-guide').textContent=($('home').value==='Kanto'?'Earn Koga’s Soul Badge in Fuchsia City':'Earn Morty’s Fog Badge in Ecruteak City')+', then bring a Water-type Pokémon in your party to Surf. No HM move is required.';}
function starterChoices(){const box=$('starters');box.replaceChildren();for(const key of content.starters){const sp=content.species[key];const b=button('',()=>{if(loggingIn)return;starter=key;starterChoices();audio.inspectPokemon(key);},'starter-choice'+(starter===key?' selected':''),loggingIn);b.title=sp.name;b.setAttribute('aria-pressed',String(starter===key));b.append(h('img',{src:'assets/'+sp.front,alt:sp.name}),h('span',{},sp.name));box.append(b);}registrationSummary();}
function handle(p){
 if(!session&&!['joined','error','notice'].includes(p.type))return;
 if(session&&p.ownerId!=null&&p.ownerId!==session.id)return;
 if(['map','move'].includes(p.type)&&p.entity?.id!==session?.id)return;
 switch(p.type){
  case 'joined':surfPending=null;itemPending=null;bagSearch='';bagPocket='all';bagMode='owned';bagSelected='';bagBuyQuantity=1;itemView=null;resetBattlePresentation();mapSerial++;keys.clear();renderer.resetSession?.();renderer.setRemovedObjects?.({});audio.setBattle(null);audio.setScene('world');session=p;state=null;inspectedUid=null;collectionView='party';collectionSearch='';collectionVariety='all';dexSearch='';dexFilter='all';closeModal(true);$('party-list').replaceChildren();$('collection-count').textContent='Loading…';$('party-count').textContent='Loading…';$('money').textContent='Loading…';deliberateLogout=false;setAuthBusy(false);sequence=0;pendingMove=0;activeBattle=null;trade=null;invite=null;own=null;$('password').value='';$('login').classList.add('hidden');$('game').classList.remove('hidden');$('disconnect-overlay').classList.add('hidden');$('trainer-name').textContent=p.username;$('passport-name').textContent=p.username;$('world-title').textContent=p.world;$('population').textContent=p.online+' / '+p.cap;$('world-status').textContent='Authoritative world connected';renderer.selfId=p.id;renderer.active=true;renderer.players.clear();renderer.resize();$('surf-button').disabled=true;$('surf-button').textContent='Surf';$('surf-status').textContent='Checking your regional Surf licence…';$('atlas-button').disabled=false;chats.general=[];chats.trade=[];toast(p.motd);break;
  case 'map':loadMap(p);break;
  case 'scene':renderer.scene(p);if(session)$('population').textContent=p.online+' / '+session.cap;break;
  case 'move':if(p.seq>=pendingMove)pendingMove=0;audio.movement(p,own);own=p.entity;if(surfPending&&(p.surfRequestId===surfPending.id||own.surf||own.map!==surfPending.map))surfPending=null;renderer.entity(p.entity);if(state){if(Number.isInteger(p.repelSteps))state.repelSteps=p.repelSteps;if(p.surfContext)state.surfContext=p.surfContext;if(p.surfRequestId)state.surfRequestId=p.surfRequestId;if(p.itemContext){state.itemContext=p.itemContext;renderer.setFieldTiles?.(p.itemContext.fieldMap,p.itemContext.fieldTiles);}}if(state?.adventure&&typeof p.pcAvailable==='boolean'){state.adventure.pcAvailable=p.pcAvailable;if(!p.pcAvailable&&modalKind==='collection'&&collectionView==='storage')closeModal(true);}if(modalKind==='npc')closeModal(true);updateCoordinates();break;
  case 'state':if(state&&Number.isSafeInteger(p.revision)&&p.revision<state.revision)return;state=p;if(surfPending&&p.surfRequestId===surfPending.id)surfPending=null;if(itemPending&&p.itemReceipt===itemPending.id)itemPending=null;renderer.setCutTrees(p.adventure?.cutTrees);renderer.setStoryEvents(p.adventure?.storyEvents);renderer.setItemPickups(p.adventure?.itemPickups);renderer.setRemovedObjects?.(p.adventure?.removedObjects);renderer.setObjectMoves?.(p.adventure?.objectMoves);renderer.setFieldTiles?.(p.itemContext?.fieldMap,p.itemContext?.fieldTiles);updateParty();refreshOwnerModal();break;
  case 'chat_history':chats[p.channel]=(p.messages||[]).slice(-150);if(channel===p.channel)renderChat();break;
  case 'audio':audio.handleEvents(p);break;
  case 'chat':if(!mutedNames.has(p.username)){if(audio.settings.chat&&p.username!==session?.username)audio.ui('chat');chats[p.channel].push(p);if(chats[p.channel].length>150)chats[p.channel].shift();if(channel===p.channel)renderChat();}break;
  case 'notice':toast(p.message);break;
  case 'error':if(surfPending&&((p.operation==='surf'&&p.requestId===surfPending.id)||(!p.operation&&!p.requestId)))surfPending=null;updateAdventureAccess();itemPending=null;if(activeBattle){battleSubmitting=false;clearTimeout(battleSubmitTimer);if(!battleFX?.busy)renderBattle();}audio.ui('error');if(p.login||!session){setAuthBusy(false);if(p.login&&!session){hello=null;ws?.close(1000,'Authentication rejected');}$('auth-error').textContent=p.message;$('auth-submit').textContent=mode==='register'?'Create account & enter':'Enter world';}else{toast(p.message,'error');if(modalKind==='npc')closeModal(true);else refreshOwnerModal();}break;
  case 'pong':$('latency').textContent=Math.max(0,Math.round(performance.now()-p.nonce))+' ms';break;
  case 'invite':audio.ui('invite');showInvite(p);break;
  case 'invite_expired':if(invite?.id===p.id){invite=null;if(modalKind==='invite')closeModal(true);toast('That invitation is no longer available.');}break;
  case 'dialog':audio.ui('dialog');showNpcDialog(p);break;
  case 'battle':{itemPending=null;const b=p.battle;if(activeBattle?.id===b.id&&Number(b.audio?.revision)<Number(activeBattle.audio?.revision))break;const same=battleFX?.matches(b);if(b.waiting||b.ended||!same){battleSubmitting=false;clearTimeout(battleSubmitTimer);}audio.setBattle(b);activeBattle=b;if($('modal').open)closeModal(true);if(!(same&&battleFX?.busy))renderBattle();break;}
  case 'trade':trade=p.trade;renderTrade();break;
  case 'trade_done':if(trade?.id===p.id){trade=null;if(modalKind==='trade')closeModal(true);}toast(p.message,p.success?'info':'warn');break;
  case 'ai.dashboard':aiDashboard=p.dashboard;renderAIDashboard();break;
 }
}
async function loadMap(p){surfPending=null;const serial=++mapSerial;keys.clear();pendingMove=0;if(['npc','collection','pokemon','reminder','atlas'].includes(modalKind))closeModal(true);if(state?.adventure)state.adventure.pcAvailable=false;$('map-loading').classList.remove('hidden');$('map-name').textContent=p.name;$('map-region').textContent=p.region;$('map-source').textContent=p.region+' · Adventure';own=p.entity;updateAdventureAccess();audio.setMap(p.id,!!p.entity.surf);
 try{const loaded=await renderer.loadMap(p.id,p.entity);if(!loaded||serial!==mapSerial||!session)return;renderer.resize();if(['warp','travel','home','rescue'].includes(p.transition))audio.ui('warp');updateCoordinates();}catch(error){if(serial===mapSerial&&session)toast(error.message,'error');}finally{if(serial===mapSerial)$('map-loading').classList.add('hidden');}
}
function updateCoordinates(){if(own)$('coords').textContent=own.x+', '+own.y+(own.surf?' · SURF':'');updateAdventureAccess();}
function updateAdventureAccess(){
 if(!session)return;$('atlas-button').disabled=false;
 const button=$('surf-button'),status=$('surf-status'),context=state?.surfContext,readyMap=!!own&&renderer?.map?.id===own.map&&!renderer.pendingMap,contextCurrent=!!context&&context.map===own?.map&&context.origin?.x===own?.x&&context.origin?.y===own?.y,active=!!own?.surf,partner=active?own.surfPokemon:context?.partner,name=partner?monName(partner):'your Water Pokémon';
 let label='Surf',reason='Checking your regional Surf licence…';
 if(active){label='Surfing with '+name;reason='Use the movement keys to travel on water. Step onto a walkable shore to dismount.';}
 else if(surfPending){label='Boarding…';reason='Waiting for the world to confirm your Surf entry.';}
 else if(!readyMap||!contextCurrent){reason='Waiting for the current shoreline and party information.';}
 else if(context.available){label='Surf with '+name;reason='Board '+name+' at the '+(context.shoreline?.direction||'nearby')+' shoreline. No HM move is needed.';}
 else reason=context.reason||'Earn this region’s Surf badge and bring a Water-type Pokémon in your party.';
 button.textContent=label;button.disabled=active||!!surfPending||!readyMap||!contextCurrent||!context?.available||!!pendingMove;button.title=reason;button.setAttribute('aria-describedby','surf-status');button.setAttribute('aria-busy',String(!!surfPending));button.classList.toggle('surf-ready',!button.disabled);button.classList.toggle('surf-active',active);status.textContent=reason;status.classList.toggle('active',active);status.classList.toggle('ready',!button.disabled);
}
function requestSurf(){
 const context=state?.surfContext;
 if(!session||!state||(state.ownerId!=null&&state.ownerId!==session.id)||!own||surfPending||own.surf||pendingMove||!context?.available||context.map!==own.map||context.origin?.x!==own.x||context.origin?.y!==own.y||renderer.pendingMap||renderer.map?.id!==own.map||activeBattle||trade||invite||$('modal').open||$('battle-dialog').open||$('audio-dialog').open)return;
 const request={map:own.map,requestId:itemRequestId(),x:context.origin.x,y:context.origin.y,direction:context.origin.direction};
 if(send('surf',request)){surfPending={id:request.requestId,map:own.map,owner:session.id};keys.clear();updateAdventureAccess();}
}

function canTravelTo(map){if(!session||map.playable===false)return false;if(session.alphaAtlas)return true;const a=state?.adventure;return [1,2,3].includes(map.mapType)&&!!a?.unlocks?.includes('travel_pass')&&(a.visited.includes(map.id)||Object.values(content.homes||{}).includes(map.id));}
function hpBar(mon){const percent=Math.max(0,Math.min(100,100*mon.hp/mon.maxHp));const fill=h('div',{class:'hp-fill'+(percent<20?' critical':percent<50?' low':'')});fill.style.width=percent+'%';return h('div',{class:'hp-track',role:'meter','aria-label':monName(mon)+' HP','aria-valuemin':0,'aria-valuemax':mon.maxHp,'aria-valuenow':mon.hp},fill);}
function updateParty(){if(!state)return;updateAdventureAccess();$('money').textContent=money(state.money);$('collection-count').textContent=state.creatures.length+' owned';$('party-count').textContent=state.party.length+' / 6';const list=$('party-list');list.replaceChildren();
 for(let i=0;i<6;i++){const uid=state.party[i],mon=state.creatures.find(m=>m.uid===uid);if(!mon){list.append(h('div',{class:'party-empty'},'Empty party slot'));continue;}
  const ratio=Math.max(0,Math.min(100,100*(mon.exp-mon.levelExp)/Math.max(1,mon.nextExp-mon.levelExp)));const xp=h('div',{class:'xp-fill'});xp.style.width=ratio+'%';
  const card=h('div',{class:'party-card'+(i===0?' lead':''),title:'Click to inspect '+monName(mon),role:'button',tabindex:0,onClick:()=>showPokemon(mon),onKeydown:e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showPokemon(mon);}}},h('img',{class:'party-icon',src:sprite(mon),alt:monName(mon)}),h('div',{class:'party-info'},h('div',{class:'party-name'},h('strong',{},monName(mon)),h('span',{},'Lv. '+mon.level)),h('div',{class:'party-meta'},h('span',{class:i===0?'lead-label':''},i===0?'FOLLOWING':mon.status||'READY'),h('span',{},mon.hp+' / '+mon.maxHp+' HP')),hpBar(mon),h('div',{class:'xp-track'},xp),(mon.pendingLearn?.length||(mon.evolutions||[]).some(e=>!e.deferred))?h('span',{class:'growth-tag'},'Growth choices ready'):null));list.append(card);
 }
}
function requestAIDashboard(view='activity'){
 if(!canOpen())return;
 aiDashboardView=view;send('ai.dashboard');
 const body=openModal(view==='ladder'?'Ranking ladder':view==='rivals'?'Rivals hub':'AI activity','ai','min(62rem,94vw)');
 body.append(h('p',{class:'modal-description'},'Loading the persistent autonomous trainer network…'));
}
function aiChallengeButton(bot){return button('Battle',()=>{if(send('ai.challenge',{id:bot.id}))closeModal(true);},'primary small');}
function renderAIDashboard(){
 if(!aiDashboard||modalKind!=='ai')return;
 const d=aiDashboard,body=$('modal-body');body.replaceChildren();
 $('modal-title').textContent=aiDashboardView==='ladder'?'Ranking ladder':aiDashboardView==='rivals'?'Rivals hub':'AI activity';
 body.append(h('div',{class:'ai-kpis'},
  h('div',{},h('span',{},'AUTONOMOUS TRAINERS'),h('strong',{},String(d.population))),
  h('div',{},h('span',{},'YOUR RATING'),h('strong',{},d.human.rating+' · '+d.human.tier)),
  h('div',{},h('span',{},'YOUR LADDER RANK'),h('strong',{},'#'+d.human.rank)),
  h('div',{},h('span',{},'TOP AI RATING'),h('strong',{},String(d.topRating)))));
 const tabs=h('div',{class:'segmented ai-tabs'},
  button('Activity',()=>{aiDashboardView='activity';renderAIDashboard();},aiDashboardView==='activity'?'selected':''),
  button('Ladder',()=>{aiDashboardView='ladder';renderAIDashboard();},aiDashboardView==='ladder'?'selected':''),
  button('Rivals',()=>{aiDashboardView='rivals';renderAIDashboard();},aiDashboardView==='rivals'?'selected':''));
 body.append(tabs);const list=h('div',{class:'ai-list'});body.append(list);
 if(aiDashboardView==='activity'){
  for(const a of d.activity)list.append(h('article',{class:'ai-row'},
   h('div',{},h('strong',{},a.actor),h('p',{},a.summary),h('small',{},new Date(a.time*1000).toLocaleString())),
   h('span',{class:'rating-delta '+(a.after>=a.before?'up':'down')},(a.after>=a.before?'+':'')+(a.after-a.before))));
  if(!d.activity.length)list.append(h('p',{class:'empty-state'},'Autonomous activity will appear as the population begins operating.'));
 }else if(aiDashboardView==='ladder'){
  let rank=1;
  for(const b of d.ladder)list.append(h('article',{class:'ai-row ladder-row'},
   h('span',{class:'rank-number'},'#'+rank++),
   h('div',{},h('strong',{},b.username),h('small',{},b.autonomous?b.tier+' · '+b.wins+'W / '+b.losses+'L · '+b.collection+' Pokémon':b.tier+' · '+b.wins+'W / '+b.losses+'L · HUMAN TRAINER')),
   h('strong',{class:'rating-number'},String(b.rating)),b.autonomous?aiChallengeButton(b):h('span',{class:'ai-human-pill'},'HUMAN')));
 }else{
  for(const b of d.rivals)list.append(h('article',{class:'ai-row ladder-row'},
   h('div',{},h('strong',{},b.username),h('small',{},b.tier+' · '+b.rating+' rating · rivalry '+b.rivalry),h('p',{},b.battles+' battles · You '+b.humanWins+'–'+b.aiWins+' '+b.username)),
   aiChallengeButton(b)));
  if(!d.rivals.length)list.append(h('p',{class:'empty-state'},'Battle autonomous trainers to build persistent rivalries.'));
 }
}
function renderChat(){const box=$('chat-messages');const nearBottom=box.scrollTop+box.clientHeight>=box.scrollHeight-40;box.replaceChildren();const messages=chats[channel]||[];if(!messages.length)box.append(h('p',{class:'chat-line system'},channel==='general'?'Welcome to General. This channel reaches trainers throughout the world.':'Trade chat is global. Arrange a meeting, then click the trainer to open a secure exchange.'));
 for(const m of messages){if(mutedNames.has(m.username))continue;const time=new Date(m.time*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});box.append(h('div',{class:'chat-line '+channel},h('time',{},time),h('span',{class:'chat-name'},m.username),h('span',{},m.text)));}
 if(nearBottom||messages.length<10)box.scrollTop=box.scrollHeight;
}
function changeChannel(value){channel=value;$('chat-general').classList.toggle('selected',value==='general');$('chat-trade').classList.toggle('selected',value==='trade');$('chat-prefix').textContent=value.toUpperCase();renderChat();$('chat-input').focus();}
function openModal(title,kind,width=''){keys.clear();modalKind=kind;$('modal-title').textContent=title;$('modal').style.width=width;$('modal').setAttribute('data-view',kind);$('modal-eyebrow').textContent=kind==='trade'?'SECURE TRAINER EXCHANGE':kind==='bag'?'TRAINER ESSENTIALS':'POKEMON NXT MMO';$('modal-body').replaceChildren();$('context-menu').classList.add('hidden');if(!$('modal').open)$('modal').showModal();return $('modal-body');}
function closeModal(force=false){if(!force&&modalKind==='trade'&&trade){send('trade',{id:trade.id,action:'cancel'});return;}if(!force&&modalKind==='invite'&&invite){send('invite.answer',{id:invite.id,accept:false});invite=null;}$('modal').close();modalKind='';}
function canOpen(){return !!session&&!!state&&!activeBattle&&!$('battle-dialog').open&&!trade&&!invite;}
function refreshOwnerModal(){
 const kind=modalKind,focus=document.activeElement,focusKey=focus?.getAttribute?.('data-focus'),selection=focus?.selectionStart,scroll=$('modal-body').scrollTop,bagScroll=$('modal-body').querySelector?.('.bag-list')?.scrollTop||0;
 if(kind==='collection')showCollection();else if(kind==='bag')showBag();else if(kind==='item')showItemAction();else if(kind==='journal')showJournal();else if(kind==='dex')showDex();else if(kind==='pokemon'||kind==='reminder'){const mon=state?.creatures.find(m=>m.uid===inspectedUid);if(mon){if(kind==='reminder')showMoveReminder(mon);else showPokemon(mon,false);}else closeModal(true);}
 if(kind===modalKind){$('modal-body').scrollTop=scroll;const list=$('modal-body').querySelector?.('.bag-list');if(list)list.scrollTop=bagScroll;if(focusKey){const next=$('modal-body').querySelector?.('[data-focus="'+focusKey+'"]');next?.focus({preventScroll:true});if(Number.isInteger(selection)&&next?.setSelectionRange)next.setSelectionRange(selection,selection);}}
}
// UI actions belong to the rendered owner and map. The server independently
// rechecks ownership, proximity and busy state before committing any mutation.
function commandButton(label,op,data,classes='secondary',disabled=false,mapBound=false){
 const owner=session?.id,map=own?.map,serial=mapSerial,kind=modalKind,itemCommand=ITEM_COMMANDS.has(op);
 const b=button(itemCommand&&itemPending?'Saving…':label,()=>{
  if(b.disabled||(itemCommand&&itemPending)||session?.id!==owner||modalKind!==kind||!canOpen()||(mapBound&&(own?.map!==map||mapSerial!==serial))){return;}
  if(data.uid&&!state.creatures.some(m=>m.uid===data.uid)){toast('That Pokémon is no longer in your collection.','error');return;}
  if(op==='pc'&&!state.adventure?.pcAvailable){toast('Use a PC inside a Pokémon Center to move Pokémon between your party and storage.');return;}
  const request=itemCommand?{...data,requestId:itemRequestId()}:data;if(send(op,request)){if(itemCommand)itemPending={id:request.requestId,owner};b.disabled=true;b.setAttribute('aria-busy','true');}
 },classes,disabled||(itemCommand&&!!itemPending));
 return b;
}
function showPokemon(mon,playCry=true){
 if(!canOpen())return;mon=state.creatures.find(m=>m.uid===mon.uid);if(!mon)return;inspectedUid=mon.uid;if(playCry)audio.inspectPokemon(mon.species);
 const body=openModal(monName(mon),'pokemon'),sp=content.species[mon.species];
 body.append(h('div',{class:'pokemon-summary'},h('img',{src:sprite(mon),alt:monName(mon)}),h('div',{},h('span',{class:'eyebrow'},state.party.includes(mon.uid)?'YOUR PARTY':'PC STORAGE'),h('h3',{},varietyDefinition(content,mon).label+' · Level '+mon.level),h('p',{},[...new Set(sp.types)].map(t=>TYPES[t]).join(' / ')),h('p',{},mon.nature+' nature · Original trainer: '+mon.originalTrainer),h('p',{},'EXP '+mon.exp.toLocaleString()+' · Next level '+mon.nextExp.toLocaleString()))),hpBar(mon));
 if(mon.varietyArtAvailable===false)body.append(h('p',{class:'variety-art-note',role:'note'},'Your '+varietyDefinition(content,mon).label+' identity is preserved. This extra form has no supplied variety artwork, so its regular front is shown.'));
 const stats=h('div',{class:'help-grid'});stats.append(h('div',{},h('h3',{},'Stats'),h('p',{},['HP','Attack','Defense','Speed','Sp. Attack','Sp. Defense'].map((n,i)=>n+': '+mon.stats[i]).join(' · '))));
 const moves=h('div',{},h('h3',{},'Moves'));for(const m of mon.moves)moves.append(h('p',{},content.moves[m.id].name+' · '+m.pp+'/'+maximumPP(m)+' PP'+((m.ppUps||0)?' · '+m.ppUps+'/3 PP upgrades':'')));stats.append(moves);body.append(stats);
 const pending=mon.pendingLearn?.[0];
 if(pending){
  const section=h('section',{class:'growth-panel'},h('span',{class:'eyebrow'},'A NEW MOVE · LV. '+pending.level),h('h3',{},monName(mon)+' wants to learn '+pending.name+'.'),h('p',{class:'modal-description'},mon.moves.length<4?'There is room for another move.':'Choose one move to forget, or keep the current moves.'));
  const actions=h('div',{class:'move-grid'});
  if(mon.moves.length<4)actions.append(commandButton('Learn '+pending.name,'pokemon.learn',{uid:mon.uid,move:pending.move,slot:mon.moves.length},'primary'));
  else for(let i=0;i<mon.moves.length;i++){const current=content.moves[mon.moves[i].id];actions.append(commandButton('Forget '+current.name,'pokemon.learn',{uid:mon.uid,move:pending.move,slot:i},'move-button'));}
  section.append(actions,h('div',{class:'modal-actions'},commandButton('Do not learn this move','pokemon.learn',{uid:mon.uid,move:pending.move,slot:null},'quiet')));
  if(mon.pendingLearn.length>1)section.append(h('p',{class:'mini-note'},(mon.pendingLearn.length-1)+' more move choices are waiting.'));body.append(section);
 }
 body.append(h('section',{class:'growth-panel'},h('h3',{},'Training & held item'),h('p',{},'Held: '+(mon.heldItemName||'None')+' · Friendship: '+(mon.friendship??70)+'/255'),h('p',{},'EVs: '+(mon.evs||[0,0,0,0,0,0]).join(' / ')+' (HP / Attack / Defense / Speed / Sp. Attack / Sp. Defense)'),h('p',{},'Regular ability slot: '+((mon.abilitySlot||0)+1)+(mon.abilityId?' · Ability #'+mon.abilityId:'')),h('p',{},Object.keys(mon.condition||{}).length?'Condition: '+Object.entries(mon.condition).map(([k,v])=>k+' '+v).join(' · '):''),mon.heldItemId?commandButton('Take held item','item.take',{uid:mon.uid,expectedHeld:mon.heldItemId},'secondary'):null));
 if(mon.heldMail)body.append(h('blockquote',{class:'held-mail'},h('span',{},'HELD MAIL'),h('p',{},mon.heldMail)));
 appendLearnset(body,mon);
 for(const option of mon.evolutions||[]){
  const target=content.species[option.target],item=option.item?content.items[option.item]:null;
  const section=h('section',{class:'growth-panel evolution-panel'},h('span',{class:'eyebrow'},option.deferred?'EVOLUTION PAUSED':'READY TO EVOLVE'),h('div',{class:'evolution-choice'},h('img',{src:sprite({...mon,species:option.target}),alt:option.name}),h('div',{},h('h3',{},monName(mon)+' → '+monName({...mon,species:option.target,name:option.name})),h('p',{class:'modal-description'},option.deferred?'You can resume this evolution whenever you are ready.':option.item?'Uses one '+(item?.name||option.item)+'.':'Your partner is ready for its next form.'))));
  if(varietyKey(mon)!=='normal'&&!target.varieties?.[varietyKey(mon)]&&!(varietyKey(mon)==='shiny'&&target.shiny))section.append(h('p',{class:'variety-art-note'},'This extra form has no supplied '+varietyDefinition(content,mon).label+' front. Evolution keeps its variety and follower effect, but displays its regular front.'));
  const actions=h('div',{class:'modal-actions'});
  if(option.deferred)actions.append(commandButton('Resume evolution','pokemon.evolution.resume',{uid:mon.uid,target:option.target},'secondary'));
  else{actions.append(commandButton('Not now','pokemon.evolution.defer',{uid:mon.uid,target:option.target},'quiet'));actions.append(commandButton('Evolve into '+option.name,'pokemon.evolve',{uid:mon.uid,target:option.target,item:option.item},'primary',!!option.item&&!state.items[option.item]));}
  section.append(actions);body.append(section);
 }
 const actions=h('div',{class:'modal-actions'});if(state.party.includes(mon.uid)&&state.party[0]!==mon.uid)actions.append(commandButton('Make first partner','party',{party:[mon.uid,...state.party.filter(id=>id!==mon.uid)]},'primary'));
 actions.append(button('Back to party & storage',()=>showCollection()));body.append(actions);
}
function appendLearnset(body,mon){
 const entries=[...(mon.levelUpMoves||[])].sort((a,b)=>a.level-b.level),known=new Set(mon.moves.map(m=>m.id)),pending=new Set((mon.pendingLearn||[]).map(m=>m.move)),eligible=new Set((mon.relearnMoves||[]).map(m=>m.move));
 const section=h('section',{class:'learnset-panel'},h('span',{class:'eyebrow'},'LEVEL-UP MOVES'),h('h3',{},content.species[mon.species].name+'’s learnset'));
 if(!Array.isArray(mon.levelUpMoves)){section.append(h('p',{class:'modal-description'},'Move details are unavailable from this world server.'));body.append(section);return;}
 const next=entries.find(m=>m.level>mon.level&&!known.has(m.move)&&!pending.has(m.move));
 section.append(h('p',{class:'next-move'},next?'Next move: '+next.name+' at Lv. '+next.level:entries.some(m=>m.level>mon.level)?'All upcoming level-up moves are already known or awaiting a choice.':'No more level-up moves for this form.'),h('p',{class:'mini-note'},'Levels apply to this Pokémon’s current form. Evolving can change its learnset.'));
 const table=h('table',{class:'learnset-table'},h('thead',{},h('tr',{},h('th',{scope:'col'},'Level'),h('th',{scope:'col'},'Move'),h('th',{scope:'col'},'Status')))),rows=h('tbody');
 for(const entry of entries){const label=known.has(entry.move)?'Known':pending.has(entry.move)?'Pending choice':entry.level>mon.level?'Upcoming':eligible.has(entry.move)?'Move Reminder':'Reached';rows.append(h('tr',{},h('td',{},'Lv. '+entry.level),h('td',{},entry.name),h('td',{},h('span',{class:'learnset-status'+(label==='Known'?' known':label==='Pending choice'?' pending':'')},label))));}
 table.append(rows);if(entries.length)section.append(table);else section.append(h('p',{class:'modal-description'},'This form has no level-up moves.'));
 const owner=session,snapshot=state,uid=mon.uid,open=button('Open Move Reminder',()=>{if(open.disabled||session!==owner||state!==snapshot||!canOpen()||modalKind!=='pokemon'||inspectedUid!==uid)return;showMoveReminder(mon);},'secondary',pending.size>0||!eligible.size);
 section.append(h('div',{class:'modal-actions'},open),h('p',{class:'mini-note'},pending.size?'Finish the pending move choices above before using the Move Reminder.':eligible.size?'Recover a missed or forgotten level-up move. You choose the move and its slot.':'No forgotten level-up moves are available at this level.'));body.append(section);
}
function showMoveReminder(mon,moveId=null,slot=null){
 if(!canOpen())return;mon=state.creatures.find(m=>m.uid===mon.uid);if(!mon){closeModal(true);return;}inspectedUid=mon.uid;
 if(mon.pendingLearn?.length){showPokemon(mon,false);return;}
 const eligible=(mon.relearnMoves||[]).filter(m=>m.level<=mon.level&&!mon.moves.some(current=>current.id===m.move)),selected=eligible.find(m=>m.move===moveId);
 const body=openModal('Move Reminder · '+monName(mon),'reminder'),owner=session,snapshot=state,view={};reminderView=view;let submitted=false;const controls=[];
 // Each step belongs to one rendered state and session. A state refresh returns
 // to move selection, so a stale confirmation can never replace a changed slot.
 const action=(label,fn,classes='secondary')=>{const b=button(label,()=>{if(b.disabled||submitted||session!==owner||state!==snapshot||reminderView!==view||modalKind!=='reminder'||inspectedUid!==mon.uid||!canOpen()||!state.creatures.some(m=>m.uid===mon.uid))return;fn();},classes);controls.push(b);return b;};
 const submit=chosenSlot=>{if(send('pokemon.remember',{uid:mon.uid,move:selected.move,slot:chosenSlot})){submitted=true;for(const b of controls)b.disabled=true;body.append(h('p',{class:'mini-note',role:'status'},'Waiting for the world to confirm the move…'));}};
 body.append(h('p',{class:'modal-description'},'Choose a missed or forgotten level-up move for '+monName(mon)+'’s current form. Your current moves stay in place until you confirm a choice.'));
 if(!selected){
  body.append(h('h3',{},'1. Choose a move'));const choices=h('div',{class:'move-grid reminder-choices'});
  for(const entry of eligible)choices.append(action(entry.name+' · Lv. '+entry.level,()=>showMoveReminder(mon,entry.move),'move-button'));
  body.append(choices);if(!eligible.length)body.append(h('p',{class:'empty-state'},'No forgotten level-up moves are available at this level.'));
 }else if(slot===null){
  body.append(h('h3',{},'2. Choose a slot for '+selected.name),h('p',{class:'mini-note'},'Available from Lv. '+selected.level+'. Select an empty slot or a move to replace.'));
  const choices=h('div',{class:'move-grid reminder-choices'});
  if(mon.moves.length<4)choices.append(action('Use empty slot '+(mon.moves.length+1),()=>submit(mon.moves.length),'primary'));
  for(let i=0;i<mon.moves.length;i++){const current=content.moves[mon.moves[i].id];choices.append(action('Replace '+(current?.name||'Move '+mon.moves[i].id)+' · Slot '+(i+1),()=>showMoveReminder(mon,selected.move,i),'move-button'));}body.append(choices);
  body.append(h('div',{class:'modal-actions'},action('Choose another move',()=>showMoveReminder(mon),'quiet')));
 }else if(Number.isInteger(slot)&&slot>=0&&slot<mon.moves.length){
  const current=content.moves[mon.moves[slot].id],name=current?.name||'Move '+mon.moves[slot].id;
  body.append(h('section',{class:'growth-panel reminder-confirmation'},h('span',{class:'eyebrow'},'CONFIRM MOVE REPLACEMENT'),h('h3',{},'Forget '+name+' and remember '+selected.name+'?'),h('p',{class:'modal-description'},monName(mon)+' will replace slot '+(slot+1)+'. Its other moves will stay the same.'),h('div',{class:'modal-actions'},action('Keep '+name,()=>showMoveReminder(mon,selected.move),'quiet'),action('Confirm: remember '+selected.name,()=>submit(slot),'primary'))));
 }
 body.append(h('div',{class:'modal-actions'},action('Back to Pokémon',()=>showPokemon(mon,false),'quiet')));
}
function showCollection(view){
 if(!canOpen())return;if(view==='party'||view==='storage')collectionView=view;
 const pc=state.adventure?.pcAvailable===true,body=openModal('Party & Pokémon storage','collection');
 body.append(h('p',{class:'modal-description'},pc?'PC connected. Deposit or withdraw Pokémon below. Keep at least one healthy partner in your party.':'Party order determines your follower. Visit a Pokémon Center and use its PC to deposit or withdraw Pokémon.'));
 const tabs=h('div',{class:'segmented',role:'tablist','aria-label':'Party or storage'});
 for(const [id,label] of [['party','Party · '+state.party.length+' / 6'],['storage','PC storage · '+(state.creatures.length-state.party.length)]]){const tab=button(label,()=>showCollection(id),id===collectionView?'selected':'');tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(id===collectionView));tabs.append(tab);}
 const search=h('input',{placeholder:'Find an owned Pokémon…','aria-label':'Search your Pokémon','data-focus':'collection-search'});search.value=collectionSearch;
 const varietyFilter=h('select',{'aria-label':'Filter Pokémon variety','data-focus':'collection-variety'},h('option',{value:'all'},'All varieties'),VARIETY_KEYS.map(v=>h('option',{value:v},varietyDefinition(content,{variety:v}).label)));varietyFilter.value=collectionVariety;const grid=h('div',{class:'content-grid collection-grid'}),count=h('p',{class:'mini-note',role:'status'});body.append(tabs,h('div',{class:'collection-controls'},search,varietyFilter),count,grid);
 const refresh=()=>{
  collectionSearch=search.value;collectionVariety=varietyFilter.value;const term=collectionSearch.trim().toLowerCase();let mons=collectionView==='party'?state.party.map(uid=>state.creatures.find(m=>m.uid===uid)).filter(Boolean):state.creatures.filter(m=>!state.party.includes(m.uid));mons=mons.filter(m=>collectionVariety==='all'||varietyKey(m)===collectionVariety);mons=mons.filter(m=>(monName(m)+' '+content.species[m.species].name).toLowerCase().includes(term));grid.replaceChildren();count.textContent=mons.length+' Pokémon'+(collectionView==='storage'&&!pc?' · Viewing storage; connect to a PC to transfer.':'');
  if(!mons.length){grid.append(h('p',{class:'empty-state'},term||collectionVariety!=='all'?'No owned Pokémon match your search and variety filter.':collectionView==='storage'?'Your PC storage is empty. New captures go here when your party is full.':'No matching party members.'));return;}
  for(const mon of mons){
   const inParty=state.party.includes(mon.uid),lead=state.party[0]===mon.uid,actions=h('div',{class:'row'});
   actions.append(button('Inspect',()=>showPokemon(mon),'secondary'));
   if(inParty)actions.append(commandButton(lead?'Following':'Make lead','party',{party:[mon.uid,...state.party.filter(x=>x!==mon.uid)]},'secondary',lead));
   const transfer=inParty?commandButton('Deposit','pc',{action:'deposit',uid:mon.uid},'quiet',!pc||!state.party.some(id=>id!==mon.uid&&state.creatures.some(m=>m.uid===id&&m.hp>0)),true):commandButton('Withdraw','pc',{action:'withdraw',uid:mon.uid},'secondary',!pc||state.party.length>=6,true);
   const pending=(mon.pendingLearn?.length||0)+(mon.evolutions||[]).filter(e=>!e.deferred).length;
   grid.append(h('article',{class:'collection-card'},h('img',{src:sprite(mon),alt:monName(mon)}),h('strong',{},monName(mon)),varietyBadge(mon),h('span',{},'Lv. '+mon.level+' · '+mon.hp+'/'+mon.maxHp+' HP'),hpBar(mon),h('span',{},inParty?'Party slot '+(state.party.indexOf(mon.uid)+1):'Safely stored'),pending?h('span',{class:'growth-tag'},'New growth choices'):null,actions,h('div',{class:'row'},transfer)));
  }
 };search.addEventListener('input',refresh);varietyFilter.addEventListener('change',refresh);refresh();
}
function showJournal(){
 if(!canOpen())return;const a=state.adventure,body=openModal('Adventure journal','journal','min(62rem,94vw)');if(!a){body.append(h('p',{class:'empty-state'},'Your adventure record is loading.'));return;}
 const badges=(a.regions||[]).flatMap(r=>r.badges||[]),earned=badges.filter(b=>b.earned).length;
 body.append(h('p',{class:'modal-description'},'Your journey through Kanto and Johto. Challenge trainers, earn badges and collect rewards as your adventure grows.'),h('div',{class:'journal-summary'},h('div',{},h('strong',{},earned+' / '+badges.length),h('span',{},'Gym badges')),h('div',{},h('strong',{},a.trainers?.count??0),h('span',{},'Trainers defeated')),h('div',{},h('strong',{},a.visited?.length||0),h('span',{},'Places visited'))));
 for(const region of a.regions||[]){
  const panel=h('section',{class:'journal-region'},h('div',{class:'section-heading'},h('h3',{},region.name),h('span',{class:'muted'},(region.badges||[]).filter(b=>b.earned).length+' / '+(region.badges||[]).length+' badges'))),grid=h('div',{class:'badge-grid'});
  for(const badge of region.badges||[])grid.append(h('article',{class:'badge-card'+(badge.earned?' earned':''),'aria-label':badge.name+(badge.earned?' earned':' not yet earned')},h('span',{class:'badge-symbol','aria-hidden':'true'},badge.earned?'★':String(badge.order)),h('strong',{},badge.name),h('span',{},badge.leader),h('small',{},badge.earned?'EARNED':'GYM CHALLENGE')));panel.append(grid);
  if(region.nextGym){const gym=region.nextGym;panel.append(h('p',{class:'next-gym'},'Next challenge: '+(typeof gym==='string'?gym:gym.name||gym.leader||'Visit the next gym')));}else panel.append(h('p',{class:'next-gym'},'All regional gym badges earned.'));body.append(panel);
 }
 const surfLicences=h('section',{class:'journal-region'},h('h3',{},'Surf — regional licences'));
 for(const [region,name,leader,city,badge] of [['kanto','Kanto','Koga','Fuchsia City','Soul Badge'],['johto','Johto','Morty','Ecruteak City','Fog Badge']]){const unlocked=(a.unlocks||[]).includes('surf_'+region);surfLicences.append(h('article',{class:'field-move-row'},h('strong',{},name),h('span',{class:'pill'+(unlocked?' mint':'')},unlocked?'SURF LICENCE EARNED':'SURF LOCKED'),h('p',{},unlocked?'Bring a Water-type party member to a shoreline and use Surf.':'Defeat '+leader+' in '+city+' and earn the '+badge+'.')));}
 surfLicences.append(h('p',{class:'mini-note'},'Surf uses a Water-type Pokémon in your party without teaching an HM move. Step onto land to dismount.'));body.append(surfLicences);
 if(a.fieldMoves?.length){
  const field=h('section',{class:'journal-region'},h('h3',{},'HM Cut — regional licences'));
  for(const move of a.fieldMoves)field.append(h('article',{class:'field-move-row'},h('strong',{},move.region==='kanto'?'Kanto':'Johto'),h('span',{class:'pill'+(move.unlocked?' mint':'')},move.unlocked?'CUT UNLOCKED':'CUT LOCKED'),h('p',{},move.unlocked?'Cut small HM trees in this region. Cleared paths persist for your character.':'Defeat '+move.leader+' in '+move.city+' and earn the '+move.badgeName+'.')));
  field.append(h('p',{class:'mini-note'},'Cut is learned automatically as a field ability. It does not replace a partner’s battle moves. Each region requires its own badge.'));body.append(field);
 }
 if(a.story?.length){
  const story=h('section',{class:'journal-region'},h('h3',{},'Johto story progress'));
  for(const event of a.story){const status=event.cleared?'PATH CLEARED':event.ready?'READY':event.badgeEarned?'KEY ITEM NEEDED':'LOCKED';const detail=event.cleared?'Sudowoodo has been dealt with. Route 36 stays clear for this character.':event.ready?'Use the '+event.itemName+' on the odd tree on Route 36.':event.badgeEarned?'Obtain the '+event.itemName+' and return to Route 36.':'Defeat '+event.leader+' in '+event.city+' and earn the '+event.requiredBadgeName+'.';story.append(h('article',{class:'field-move-row'},h('strong',{},event.title),h('span',{class:'pill'+(event.cleared||event.ready?' mint':'')},status),h('p',{},detail)));}
  story.append(h('p',{class:'mini-note'},'Story obstacles are owner-only. Your key-item progress and cleared path are saved to your character and do not open the route for other trainers.'));body.append(story);
 }
 body.append(h('h3',{class:'journal-heading'},'Adventure goals'));
 for(const goal of a.goals||[]){
  const progress=Math.min(goal.target,Math.max(0,goal.current)),fill=h('div');fill.style.width=Math.min(100,100*progress/Math.max(1,goal.target))+'%';
  const reward=goal.reward||{},rewards=[reward.money?money(reward.money):'',...Object.entries(reward.items||{}).map(([id,n])=>(content.items[id]?.name||id)+' × '+n)].filter(Boolean).join(' · ');
  body.append(h('article',{class:'goal-card'+(goal.claimed?' claimed':'')},h('div',{class:'section-heading'},h('h3',{},goal.title),h('span',{class:'pill'+(goal.complete?' mint':'')},goal.claimed?'CLAIMED':progress+' / '+goal.target)),h('p',{},goal.description),h('div',{class:'goal-track',role:'progressbar','aria-label':goal.title,'aria-valuemin':0,'aria-valuemax':goal.target,'aria-valuenow':progress},fill),h('div',{class:'goal-reward'},h('span',{},rewards||'Adventure milestone'),commandButton(goal.claimed?'Reward collected':goal.complete?'Claim reward':'In progress','journal.claim',{id:goal.id},goal.complete&&!goal.claimed?'primary small':'quiet small',!goal.complete||goal.claimed))));
 }
 if(a.unlocks?.length)body.append(h('section',{class:'journal-region'},h('h3',{},'Exploration unlocks'),h('p',{class:'modal-description'},a.unlocks.map(id=>id.replace(/[_-]/g,' ')).join(' · '))));
}
function showDex(){
 if(!canOpen())return;const dex=state.adventure?.dex||{seen:[],caught:[]},seen=new Set([...dex.seen,...dex.caught]),caught=new Set(dex.caught),body=openModal('Pokédex','dex','min(60rem,94vw)');
 body.append(h('p',{class:'modal-description'},'Your field record grows when you meet and catch Pokémon. Species you have not encountered remain undiscovered.'),h('div',{class:'journal-summary dex-summary'},h('div',{},h('strong',{},seen.size),h('span',{},'Species seen')),h('div',{},h('strong',{},caught.size),h('span',{},'Species caught'))));
 const search=h('input',{placeholder:'Search discovered Pokémon…','aria-label':'Search discovered Pokémon','data-focus':'dex-search'});search.value=dexSearch;
 const filter=h('select',{'aria-label':'Pokédex record filter','data-focus':'dex-filter'},h('option',{value:'all'},'All discoveries'),h('option',{value:'caught'},'Caught'),h('option',{value:'seen'},'Seen, not caught'));filter.value=dexFilter;
 const grid=h('div',{class:'content-grid dex-grid'}),count=h('p',{class:'mini-note',role:'status'});body.append(h('div',{class:'atlas-controls'},search,filter),count,grid);
 const refresh=()=>{
  dexSearch=search.value;dexFilter=filter.value;const term=dexSearch.trim().toLowerCase();const entries=[...seen].filter(id=>content.species[id]).filter(id=>dexFilter==='caught'?caught.has(id):dexFilter==='seen'?!caught.has(id):true).filter(id=>(content.species[id].name+' '+id).toLowerCase().includes(term)).sort((a,b)=>content.species[a].name.localeCompare(content.species[b].name));
  grid.replaceChildren();count.textContent=entries.length+' matching discoveries';
  if(!entries.length)grid.append(h('p',{class:'empty-state'},'No discoveries match this view. Explore the world to add more entries.'));
  for(const id of entries){const sp=content.species[id],owned=caught.has(id),card=button('',()=>{audio.inspectPokemon(id);},'dex-card');card.setAttribute('aria-label',sp.name+' · '+(owned?'caught':'seen')+' · Play cry');card.append(h('img',{src:'assets/'+sp.front,alt:sp.name}),h('strong',{},sp.name),h('span',{class:owned?'caught-mark':'muted'},owned?'● CAUGHT':'SEEN'),h('small',{},[...new Set(sp.types)].map(t=>TYPES[t]).join(' / ')));const seenVariants=state.adventure?.dex?.varieties?.seen?.[id]||[],caughtVariants=state.adventure?.dex?.varieties?.caught?.[id]||[];if(seenVariants.length){const chips=h('div',{class:'dex-varieties'});for(const v of VARIETY_KEYS.filter(v=>seenVariants.includes(v))){const def=varietyDefinition(content,{variety:v});chips.append(h('span',{class:'dex-variety'+(caughtVariants.includes(v)?' owned':''),style:'--variety-color:'+def.color,title:def.label+(caughtVariants.includes(v)?' caught':' seen')},(caughtVariants.includes(v)?'● ':'○ ')+def.label));}card.append(chips);}grid.append(card);}
 };search.addEventListener('input',refresh);filter.addEventListener('change',refresh);refresh();
}
// Owner-only item flows. UI eligibility is guidance; the server independently
// validates every use, source identity, target, stack, location and receipt.
let itemPending=null;
const ITEM_COMMANDS=new Set(['buy','use','sell','item.give','item.take','item.service']);
let bagSearch='',bagPocket='all',bagMode='owned',bagSort='pocket',bagSelected='',bagBuyQuantity=1,itemView=null;
const BAG_POCKETS=[['all','All items','All'],['items','Items','I'],['key','Key Items','K'],['balls','Poké Balls','●'],['machines','TM Case','TM'],['berries','Berry Pouch','B']];
function itemPocket(item){const p=item.pocketName||item.pocket;if(['key-items','key',2].includes(p)||item.keyItem)return 'key';if(['poke-balls','balls',3].includes(p)||item.mechanics?.effect==='capture')return 'balls';if(['tm-hm','machines',4].includes(p)||item.mechanics?.effect==='machine')return 'machines';if(['berries',5].includes(p))return 'berries';return 'items';}
function itemPocketName(item){return BAG_POCKETS.find(([key])=>key===itemPocket(item))?.[1]||'Items';}
function itemIcon(item,large=false){const pocket=itemPocket(item),frame=h('span',{class:'bag-icon'+(large?' large':'')+' pocket-'+pocket,'aria-hidden':'true'});if(item.icon){const img=h('img',{src:'assets/'+item.icon,alt:'',loading:'lazy'});img.addEventListener('error',()=>{img.remove();frame.textContent=BAG_POCKETS.find(([key])=>key===pocket)?.[2]||'I';},{once:true});frame.append(img);}else frame.textContent=BAG_POCKETS.find(([key])=>key===pocket)?.[2]||'I';return frame;}
function itemOrigin(item){return item.source==='kanto'?'Kanto':item.source==='johto'?'Johto':'';}
function itemRule(key){const item=content.items[key]||{};return item.mechanics||(item.capture?{effect:'capture',battle:true}:item.heal?{effect:'medicine',field:true,battle:true,target:'pokemon',heal:item.heal}:item.evolutionStone?{effect:'evolution',field:true,target:'pokemon',description:'Evolution item — choose a compatible Pokémon.'}:item.keyItem?{effect:'story',field:true,reusable:true}:{});}
function itemRequestId(){return globalThis.crypto?.randomUUID?.()||('item-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));}
function maximumPP(move){return move.maxPp??Math.floor((content.moves[move.id]?.pp||0)*(5+(move.ppUps||0))/5);}
function itemTargetReason(key,mon,action='use',battle=false){
 const r=itemRule(key),effect=r.effect,sp=content.species[mon.species],moves=mon.moves||[];
 if(action==='give')return mon.heldItemKey===key?'Already holding this item':'';
 if(action==='reserve')return '';
 if(action==='feed')return (mon.condition?.sheen||0)>=255?'Too full for another Pokéblock':'';
 if(effect==='medicine'){
  if(mon.hp<=0)return 'Fainted — needs a revival item';
  if(r.heal&&mon.hp<mon.maxHp)return '';
  if(mon.status&&(r.cure?.includes('all')||r.cure?.includes(mon.status)))return '';
  if(battle&&(r.cure?.includes('all')||r.cure?.includes('confusion')||r.cure?.includes('infatuation')))return ''; // Confusion is validated from private battle state.
  return 'No HP or status effect needed';
 }
 if(effect==='revive')return mon.hp>0?'Not fainted':'';
 if(effect==='pp')return moves.some(m=>m.pp<maximumPP(m))?'':'All moves have full PP';
 if(effect==='ppboost')return moves.some(m=>m.id!==166&&(content.moves[m.id]?.pp||0)>1&&(m.ppUps||0)<3)?'':'No upgradeable move';
 if(effect==='vitamin')return (mon.evs?.[r.stat]||0)>=100||(mon.evs||[]).reduce((a,b)=>a+b,0)>=510?'EV limit reached':'';
 if(effect==='level')return mon.level>=100?'Already level 100':'';
 if(effect==='ability'){if(!(sp.abilities?.length>=2&&sp.abilities[0]&&sp.abilities[1]&&sp.abilities[0]!==sp.abilities[1]))return 'No second regular ability';const next=sp.abilities[1-(mon.abilitySlot||0)];return next>=1&&next<=77?'':'Destination ability is not supported by this battle engine';}
 if(effect==='machine')return !sp.machines?.includes(key)?'Incompatible':moves.some(m=>m.id===r.move)?'Already knows this move':'';
 if(effect==='evolution')return (mon.evolutions||[]).some(e=>!e.deferred&&e.item===(r.evolutionAlias||key))?'':'No available evolution with this item';
 return '';
}
function itemPokemonSelector(key,action,selected,change,battle=false,roster=null){
 const mons=roster||state.creatures.filter(m=>content.items[key]?.source!=='kanto'||state.party.includes(m.uid)).sort((a,b)=>(state.party.includes(b.uid)?1:0)-(state.party.includes(a.uid)?1:0));
 const usable=mons.filter(m=>!itemTargetReason(key,m,action,battle));let mon=usable.find(m=>m.uid===selected)||usable[0];
 const select=h('select',{'aria-label':'Item target Pokémon','data-focus':'item-target'});
 for(const m of mons){const why=itemTargetReason(key,m,action,battle);select.append(h('option',{value:m.uid,disabled:!!why},monName(m)+' · Lv. '+m.level+' · '+m.hp+'/'+m.maxHp+' HP'+(why?' — '+why:'')));}
 if(mon)select.value=mon.uid;else{select.prepend(h('option',{value:''},'No compatible Pokémon'));select.value='';select.disabled=true;}
 select.addEventListener('change',()=>change(select.value));return {select,mon};
}
function showBag(){
 if(!canOpen())return;
 const body=openModal('Your Bag','bag','min(74rem,96vw)'),nearMart=state.itemContext?.mart??(session.alphaAtlas||(renderer.map?.id===own?.map&&!renderer.pendingMap&&renderer.map.objects.some(n=>n.graphics===68&&Math.max(Math.abs(n.x-own.x),Math.abs(n.y-own.y))<=2)));
 const all=Object.entries(content.items).map(([key,item])=>({key,item,quantity:state.items[key]||0,pocket:itemPocket(item)}));
 for(const [reserve,entry] of Object.entries(state.heldReserve||{}))if(entry.quantity>0)all.push({key:'reserve:'+reserve,reserve,item:{name:entry.name,description:'Held item from '+(entry.source==='kanto'?'Kanto':'Johto')+'. Its original held effect is preserved.',source:entry.source,mechanics:{held:true}},quantity:entry.quantity,pocket:'items'});
 const owned=all.filter(row=>row.quantity>0),types=owned.length,units=owned.reduce((n,row)=>n+row.quantity,0);
 const summary=h('div',{class:'bag-summary'},h('div',{class:'bag-summary-copy'},h('p',{class:'bag-kicker'},'READY FOR THE NEXT ROUTE'),h('p',{},h('strong',{},types+' item types'),h('span',{},' · '+units.toLocaleString()+' in your Bag'))),h('div',{class:'bag-wallet'},h('span',{},'YOUR MONEY'),h('strong',{},money(state.money))));
 const status=h('div',{class:'bag-status'},h('span',{class:'bag-location'+(nearMart?' available':'')},h('span',{class:'bag-status-dot','aria-hidden':'true'}),nearMart?'Poké Mart services available':'Buy and sell near a Poké Mart clerk'));
 if(state.repelSteps)status.append(h('span',{class:'bag-repel'},'Repel · '+state.repelSteps+' steps left'));
 if(state.itemContext?.safari)status.append(h('span',{class:'bag-repel'},'Safari Game · '+state.itemContext.safari.balls+' balls · '+state.itemContext.safari.steps+' steps left'));
 const modes=h('div',{class:'bag-modes','aria-label':'Bag view'}),ownedButton=button('My items',()=>{bagMode='owned';bagSelected='';showBag();},bagMode==='owned'?'selected':''),shopButton=button('Mart supplies',()=>{bagMode='shop';bagSelected='';showBag();},bagMode==='shop'?'selected':'');
 ownedButton.setAttribute('aria-pressed',String(bagMode==='owned'));shopButton.setAttribute('aria-pressed',String(bagMode==='shop'));ownedButton.setAttribute('data-focus','bag-owned');shopButton.setAttribute('data-focus','bag-shop');modes.append(ownedButton,shopButton);
 const shopStock=Array.isArray(state.itemContext?.shopItems)?new Set(state.itemContext.shopItems):null,available=bagMode==='owned'?owned:all.filter(row=>!row.reserve&&row.item.buyable!==false&&(!shopStock||shopStock.has(row.key))),tabs=h('div',{class:'bag-pockets',role:'tablist','aria-label':'Bag pockets'}),tabButtons=[];
 for(const [id,label,glyph] of BAG_POCKETS){const count=available.filter(row=>id==='all'||row.pocket===id).length;const tab=button('',()=>{bagPocket=id;bagSelected='';showBag();$('modal-body').querySelector?.('[data-focus="bag-pocket-'+id+'"]')?.focus({preventScroll:true});},'bag-pocket'+(bagPocket===id?' selected':''));tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(bagPocket===id));tab.setAttribute('tabindex',bagPocket===id?'0':'-1');tab.setAttribute('data-focus','bag-pocket-'+id);tab.setAttribute('id','bag-pocket-'+id);tab.setAttribute('aria-controls','bag-panel');tab.append(h('span',{class:'bag-pocket-symbol','aria-hidden':'true'},glyph),h('span',{},label),h('span',{class:'bag-pocket-count'},count));tabs.append(tab);tabButtons.push(tab);}
 tabs.addEventListener('keydown',event=>{const current=tabButtons.indexOf(document.activeElement);if(current<0)return;let index;if(event.key==='ArrowRight')index=(current+1)%tabButtons.length;else if(event.key==='ArrowLeft')index=(current+tabButtons.length-1)%tabButtons.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=tabButtons.length-1;else return;event.preventDefault();tabButtons[index].click();});
 const search=h('input',{type:'search',placeholder:'Search names, effects or moves…','aria-label':'Search Bag','data-focus':'bag-search',autocomplete:'off',spellcheck:'false'});search.value=bagSearch;
 const clear=button('Clear',()=>{bagSearch='';search.value='';draw();search.focus();},'quiet bag-search-clear');clear.setAttribute('aria-label','Clear Bag search');
 const sort=h('select',{'aria-label':'Sort Bag','data-focus':'bag-sort'},h('option',{value:'pocket'},'Pocket order'),h('option',{value:'name'},'Name A–Z'),h('option',{value:'quantity'},'Quantity: high to low'));sort.value=bagSort;
 const toolbar=h('div',{class:'bag-toolbar'},h('div',{class:'bag-search-wrap'},h('span',{'aria-hidden':'true',class:'bag-search-symbol'},'⌕'),search,clear),sort,modes);
 const results=h('p',{class:'bag-result-count',role:'status','aria-live':'polite'}),list=h('div',{class:'bag-list','aria-label':'Items in this pocket'}),detail=h('section',{class:'bag-detail','aria-label':'Selected item details'}),workspace=h('div',{class:'bag-workspace',id:'bag-panel',role:'tabpanel','aria-labelledby':'bag-pocket-'+bagPocket},h('div',{class:'bag-list-panel'},h('div',{class:'bag-list-heading'},h('span',{},bagMode==='shop'?'AVAILABLE SUPPLIES':'ITEM'),h('span',{},'OWNED')),list),detail);
 body.append(summary,status,tabs,toolbar,results,workspace);
 let visible=[];
 const showDetail=row=>{
  detail.replaceChildren();detail.setAttribute('data-item',row?.key||'');if(!row){detail.append(h('div',{class:'bag-detail-empty'},h('span',{'aria-hidden':'true'},'◇'),h('h3',{},'A little room for adventure'),h('p',{},bagSearch?'Try another name or effect, or check a different pocket.':bagMode==='owned'?'Items you pick up will appear here. Check Mart supplies when you need to restock.':'There are no shop supplies in this pocket.')));return;}
  const {key,item,quantity,reserve}=row,r=itemRule(key),origin=itemOrigin(item),tags=h('div',{class:'bag-item-tags'},h('span',{},itemPocketName(item)));if(origin)tags.append(h('span',{},origin));if(r.reusable||item.keyItem)tags.append(h('span',{},'Reusable'));
  detail.append(h('div',{class:'bag-detail-top'},itemIcon(item,true),h('span',{class:'bag-detail-stock'},h('strong',{},quantity),h('span',{},'IN BAG'))),tags,h('h3',{},item.name),h('p',{class:'bag-item-description'},r.description||item.description||'A useful item for your adventure.'));
  if(r.effect==='machine'&&content.moves[r.move]){const move=content.moves[r.move];detail.append(h('div',{class:'bag-move'},h('strong',{},move.name),h('span',{},TYPES[move.type]||'Move'),h('div',{},h('span',{},'POWER ',h('b',{},move.power||'—')),h('span',{},'ACCURACY ',h('b',{},move.accuracy?move.accuracy+'%':'—')),h('span',{},'PP ',h('b',{},move.pp)))));}
  const actions=h('div',{class:'bag-detail-actions item-actions'}),open=(label,action='use')=>button(label,()=>showItemAction({key,action}),'secondary',!quantity);
  if(reserve)actions.append(button('Give to Pokémon…',()=>showItemAction({key:null,action:'reserve',reserve}),'primary'));
  else{
   if(r.field&&!['apricorn','coincase','coin','pokeblocks','journal','story','key','case','mail'].includes(r.effect)){const label={machine:'Teach…',evolution:'Evolve…',escape:'Escape…',repel:'Activate…',bicycle:'Ride / dismount…',itemfinder:'Search nearby…',fishing:'Cast line…',fossil:'Revive fossil…',encounterflute:'Play flute…',vsseeker:'Seek a rematch…'}[r.effect]||'Use…';actions.append(open(label));}
   if(r.held||r.effect==='mail')actions.append(open('Give to Pokémon…','give'));
   if(r.effect==='capture')detail.append(h('p',{class:'bag-usage-note'},r.safariOnly?'USE ONLY IN THE SAFARI GAME':'THROW IN WILD BATTLE'));
   if(r.effect==='tera')detail.append(h('p',{class:'bag-usage-note'},'TERASTALLIZE WITH AN ATTACK'));
   if(r.effect==='journal'){if(key==='fr_townmap')actions.append(button('Open Town Map',showAtlas,'primary',!quantity));else if(key==='fr_teachytv')actions.append(button('Watch trainer guide',showHelp,'primary',!quantity));else if(key==='fr_famechecker')actions.append(button('Open adventure record',showJournal,'primary',!quantity));else actions.append(button('Open Pokédex',showDex,'secondary',!quantity),button('Open adventure record',showJournal,'secondary',!quantity));}
   if(r.effect==='case'&&key==='fr_powderjar')actions.append(open('Inspect Powder Jar…','service'));
   else if(r.effect==='case'){const target=(r.nativeRole||key).includes('berry')?'berries':'machines';actions.append(button(target==='berries'?'Open Berry Pouch':'Open TM Case',()=>{bagPocket=target;bagSearch='';bagMode='owned';bagSelected='';showBag();},'primary',!quantity));}
   if(['coincase','fr_coincase','pokeblockcas'].includes(key)||r.effect==='coin')actions.append(open(key==='pokeblockcas'?'Open Pokéblock Case…':'Open Coin Case…','service'));
   if(key==='whtapricorn')actions.append(open('Make Fast Ball…','craft'));
   if(r.effect==='story')actions.append(open(key==='squirtbottle'?'Use on Route 36…':key==='fr_liftkey'?'Choose elevator floor…':'Use…'));
   if(r.battle&&!r.field&&!['capture','tera'].includes(r.effect))detail.append(h('p',{class:'bag-usage-note'},'USE IN BATTLE'));
   if(r.effect==='key')detail.append(h('p',{class:'bag-context-note'},'Keep this item in your Bag. Its use depends on where you are in your adventure.'));
  }
  detail.append(actions);
  if(!reserve&&r.sellPrice>0){const sale=h('div',{class:'bag-value'},h('div',{},h('span',{},'SELL VALUE'),h('strong',{},money(r.sellPrice)+' each')),button('Sell…',()=>showItemAction({key,action:'sell'}),'quiet',!quantity||!nearMart));detail.append(sale);}
  if(!reserve&&item.buyable!==false){const purchase=h('div',{class:'bag-purchase'},h('div',{class:'bag-purchase-heading'},h('span',{},'RESTOCK'),h('strong',{},money(item.price)+' each'))),qty=h('input',{type:'number',min:1,max:Math.min(99,999-quantity,Math.floor(state.money/Math.max(1,item.price))),step:1,'aria-label':'Quantity to buy','data-focus':'bag-buy-quantity'});qty.value=String(bagBuyQuantity);const buyArea=h('div',{class:'bag-buy-action'});const drawBuy=()=>{bagBuyQuantity=Number(qty.value);const n=bagBuyQuantity,valid=Number.isSafeInteger(n)&&n>0&&n<=99&&n+quantity<=999&&n*item.price<=state.money;buyArea.replaceChildren(commandButton('Buy'+(Number.isSafeInteger(n)&&n>0?' '+n+' · '+money(n*item.price):''),'buy',{item:key,quantity:n},'primary',!nearMart||!valid||!!shopStock&&!shopStock.has(key),true));};qty.addEventListener('input',drawBuy);purchase.append(h('div',{class:'bag-buy-controls'},h('label',{},'Quantity',qty),buyArea));drawBuy();if(!nearMart)purchase.append(h('p',{},'Stand near a Poké Mart clerk to buy.'));else if(shopStock&&!shopStock.has(key))purchase.append(h('p',{},'This shop does not stock this item.'));detail.append(purchase);}
  if(!reserve&&item.buyable===false&&!(r.sellPrice>0))detail.append(h('p',{class:'bag-no-sale'},item.keyItem||row.pocket==='key'?'An important item. Cannot be sold.':'Cannot be bought or sold.'));
 };
 const selectRow=(key,focus=false)=>{if(bagSelected!==key)bagBuyQuantity=1;bagSelected=key;for(const node of list.children){const selected=node.getAttribute('data-bag-item')===key;node.classList.toggle('selected',selected);node.setAttribute('aria-pressed',String(selected));node.setAttribute('tabindex',selected?'0':'-1');if(selected&&focus)node.focus({preventScroll:false});}showDetail(visible.find(row=>row.key===key));};
 const draw=()=>{bagSearch=search.value;bagSort=sort.value;const term=bagSearch.trim().toLocaleLowerCase();clear.disabled=!term;visible=available.filter(row=>(bagPocket==='all'||row.pocket===bagPocket)&&(!term||(row.item.name+' '+(row.item.description||'')+' '+(row.item.mechanics?.description||'')+' '+(content.moves[row.item.mechanics?.move]?.name||'')+' '+itemOrigin(row.item)).toLocaleLowerCase().includes(term)));visible.sort((a,b)=>bagSort==='quantity'?(b.quantity-a.quantity||a.item.name.localeCompare(b.item.name)):bagSort==='name'?a.item.name.localeCompare(b.item.name):BAG_POCKETS.findIndex(p=>p[0]===a.pocket)-BAG_POCKETS.findIndex(p=>p[0]===b.pocket)||(a.item.sourceId||999)-(b.item.sourceId||999)||a.item.name.localeCompare(b.item.name));list.replaceChildren();if(!visible.some(row=>row.key===bagSelected))bagSelected=visible[0]?.key||'';results.textContent=visible.length+' '+(visible.length===1?'item':'items')+(term?' matching “'+bagSearch.trim()+'”':'')+' · '+(BAG_POCKETS.find(p=>p[0]===bagPocket)?.[1]||'All items');
  for(const row of visible){const selected=row.key===bagSelected,node=button('',()=>selectRow(row.key),'bag-list-item'+(selected?' selected':''));node.setAttribute('data-bag-item',row.key);node.setAttribute('data-focus','bag-item-'+row.key);node.setAttribute('aria-pressed',String(selected));node.setAttribute('tabindex',selected?'0':'-1');node.setAttribute('aria-label',row.item.name+', '+row.quantity+' owned'+(itemOrigin(row.item)?', '+itemOrigin(row.item):''));node.append(itemIcon(row.item),h('span',{class:'bag-list-copy'},h('strong',{},row.item.name),h('small',{},itemPocketName(row.item)+(itemOrigin(row.item)?' · '+itemOrigin(row.item):''))),h('span',{class:'bag-quantity'},'× '+row.quantity));list.append(node);}
  if(!visible.length){const empty=h('div',{class:'bag-list-empty'},h('strong',{},term?'No matching items':'This pocket is empty'),h('p',{},term?'Try a shorter search or another pocket.':'Picked-up items are organised here.'));if(bagPocket!=='all')empty.append(button('Search all pockets',()=>{bagPocket='all';showBag();},'quiet'));list.append(empty);}showDetail(visible.find(row=>row.key===bagSelected));
 };
 list.addEventListener('keydown',event=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key)||!visible.length)return;event.preventDefault();let index=visible.findIndex(row=>row.key===bagSelected);index=event.key==='Home'?0:event.key==='End'?visible.length-1:Math.max(0,Math.min(visible.length-1,index+(event.key==='ArrowDown'?1:-1)));selectRow(visible[index].key,true);});
 search.addEventListener('input',draw);sort.addEventListener('change',draw);draw();
}

function showItemAction(view=itemView){
 if(!canOpen()||!view)return;itemView={...view};const {key,action='use'}=itemView,item=content.items[key],r=itemRule(key),entry=state.heldReserve?.[view.reserve];if(!item&&!entry){showBag();return;}
 const body=openModal((item?.name||entry.name)+' · '+({give:'Give',reserve:'Give',sell:'Sell',service:'Case',craft:'Craft',feed:'Feed'}[action]||'Use'),'item'),qty=item?(state.items[key]||0):entry.quantity;
 body.append(h('div',{class:'bag-action-intro'},itemIcon(item||{name:entry.name},true),h('div',{},h('p',{},r.description||item?.description||'Preserves the original source-specific held effect.'),h('strong',{},qty+' available in your Bag'))));if(itemPending)body.append(h('p',{class:'item-pending-note',role:'status'},'Saving your item action… Please wait for the world to confirm.'));
 const foot=()=>body.append(h('div',{class:'modal-actions'},button('Back to Bag',showBag,'quiet')));
 const commit=(label,op,data,disabled=false,mapBound=false)=>{if(mapBound)data.map=own?.map;return commandButton(label,op,data,'primary',disabled||qty<1,mapBound);};
 if(action==='sell'){
  const amount=h('input',{type:'number',min:1,max:qty,value:view.quantity??1,'aria-label':'Quantity to sell','data-focus':'item-sell-quantity'}),total=h('p',{class:'mini-note'}),area=h('div',{class:'modal-actions'});
  amount.value=String(view.quantity??1);const refresh=()=>{const n=Number(amount.value);itemView.quantity=n;const valid=Number.isInteger(n)&&n>0&&n<=qty;total.textContent=valid?'You receive '+money(n*r.sellPrice)+'.':'Enter an owned quantity.';area.replaceChildren(commit('Confirm sale','sell',{item:key,quantity:n},!valid||!state.itemContext?.mart,true));};amount.addEventListener('input',refresh);body.append(amount,total,area);refresh();foot();return;
 }
 if(action==='craft'){body.append(h('p',{},'Kurt trades one White Apricorn for one Fast Ball at his house in Azalea Town. This is the NXT crafting service.'),commit('Make one Fast Ball','item.service',{item:key,action:'craft'},!state.itemContext?.apricorn,true));foot();return;}
 if(action==='service'&&key==='fr_powderjar'){
  const powder=Number(state.itemContext?.berryPowder??state.berryPowder??0),nearMerchant=!!state.itemContext?.powderMerchant;
  body.append(h('div',{class:'coin-balance'},h('span',{},'BERRY POWDER IN YOUR JAR'),h('strong',{},powder.toLocaleString()+' units')),h('p',{class:'modal-description'},'Exchange stored Berry Powder for medicine at the powder merchant’s house in Cerulean City.'),h('p',{class:'field-move-note'},'Berry Crush is not available yet. Berry Powder cannot currently be earned through that minigame.'));
  if(!nearMerchant)body.append(h('p',{class:'mini-note'},'Visit the Berry Powder merchant to make an exchange.'));
  const prizes=state.itemContext?.powderPrizes||[];
  if(prizes.length)body.append(h('h3',{class:'coin-prizes-title'},'Medicine exchange'));
  for(const prize of prizes){const definition=content.items[prize.reward],exchange=commit('Exchange','item.service',{item:key,action:'medicine',reward:prize.reward},!nearMerchant||powder<prize.powder||(state.items[prize.reward]||0)>=999,true);exchange.setAttribute('aria-label','Exchange Berry Powder for '+(prize.name||definition?.name||prize.reward));body.append(h('article',{class:'coin-prize'},itemIcon(definition||{}),h('div',{},h('strong',{},prize.name||definition?.name||prize.reward),h('p',{},Number(prize.powder).toLocaleString()+' powder · 1 item'),h('small',{},(state.items[prize.reward]||0)+' in your Bag')),exchange));}
  foot();return;
 }
 if(action==='service'&&item?.source==='kanto'&&r.effect==='coincase'){
  body.append(h('div',{class:'coin-balance'},h('span',{},'COINS IN YOUR CASE'),h('strong',{},Number(state.coins||0).toLocaleString()+' / 9,999')),h('p',{class:'modal-description'},'Buy coins at Celadon Game Corner. Exchange them at the prize counters next door.'));
  const buys=h('div',{class:'item-actions'});for(const n of [50,500])buys.append(commit('Buy '+n+' coins · '+money(20*n),'item.service',{item:key,action:'buycoins',quantity:n},!state.itemContext?.coinCounter||state.money<20*n||(state.coins||0)+n>9999,true));body.append(buys);
  if(!state.itemContext?.coinCounter)body.append(h('p',{class:'mini-note'},'Visit the Game Corner coin seller to buy coins.'));
  const prizes=state.itemContext?.coinPrizes||[];if(prizes.length)body.append(h('h3',{class:'coin-prizes-title'},'Celadon prizes'));
  for(const prize of prizes){const definition=prize.kind==='pokemon'?content.species[prize.reward]:content.items[prize.reward],visual=prize.kind==='pokemon'?h('img',{class:'coin-pokemon',src:'assets/'+definition?.front,alt:''}):itemIcon(definition||{});body.append(h('article',{class:'coin-prize'},visual,h('div',{},h('strong',{},prize.name||definition?.name||prize.reward),h('p',{},prize.coins.toLocaleString()+' coins'+(prize.level?' · Lv. '+prize.level:'')),!prize.available?h('small',{},'Visit the matching prize counter'):null),commit('Exchange','item.service',{item:key,action:'prize',reward:prize.reward,kind:prize.kind},!prize.available||(state.coins||0)<prize.coins||(prize.kind==='item'&&(state.items[prize.reward]||0)>=999),true)));}
  foot();return;
 }
 if(action==='service'&&key==='coincase'){
  const mart=!!state.itemContext?.mart;body.append(h('h3',{},(state.coins||0)+' / 9,999 coins'),h('p',{},'NXT exchange service at a Poké Mart. One coin costs '+money(20)+'. No gambling.'));
  const buys=h('div',{class:'item-actions'});for(const n of [50,100,500])buys.append(commit('Buy '+n+' coins','item.service',{item:key,action:'buycoins',quantity:n},!mart||state.money<20*n||(state.coins||0)+n>9999,true));body.append(buys);
  for(const [reward,cost] of Object.entries({greatball:60,ultraball:120,timerball:100,netball:100,rarecandy:500}))body.append(h('article',{class:'item-row'},h('p',{},content.items[reward].name+' · '+cost+' coins'),commit('Exchange for '+content.items[reward].name,'item.service',{item:key,action:'prize',reward},!mart||(state.coins||0)<cost||(state.items[reward]||0)>=999,true)));
  if(!mart)body.append(h('p',{class:'mini-note'},'Approach a Poké Mart clerk to use the exchange.'));foot();return;
 }
 if(action==='service'&&key==='pokeblockcas'){
  const blocks=state.pokeblocks||[];body.append(h('h3',{},blocks.length+' / 40 Pokéblocks'),h('p',{},'NXT recipes: one Sitrus Berry makes a Beauty block; one Lum Berry makes a Smart block. Feeding adds 20 condition, 10 sheen and friendship.'));
  for(const berry of ['sitrusberry','lumberry'])body.append(commit('Blend '+content.items[berry].name,'item.service',{item:key,action:'blend',berry},!state.items[berry]||blocks.length>=40));
  for(const block of blocks)body.append(h('article',{class:'item-row'},h('p',{},block.flavor+' · '+block.power+' condition · '+block.feel+' sheen'),button('Feed block…',()=>showItemAction({key,action:'feed',block:block.id}),'secondary')));foot();return;
 }
 let mon=null;
 if(['give','reserve','feed'].includes(action)||['pokemon','move','machine'].includes(r.target)){
  const chosen=itemPokemonSelector(key,action,view.uid,uid=>showItemAction({...itemView,uid,slot:undefined,target:undefined}));mon=chosen.mon;itemView.uid=mon?.uid;body.append(h('label',{},'Choose your Pokémon',chosen.select));
  if(!mon){body.append(h('p',{class:'empty-state'},'No Pokémon can receive this effect now. Nothing will be consumed.'));foot();return;}
  body.append(h('p',{class:'mini-note'},monName(mon)+' · '+mon.hp+'/'+mon.maxHp+' HP · '+(mon.status||'No major status')+' · Held: '+(mon.heldItemName||'None')));
 }
 if(action==='give'||action==='reserve'){
  const giving={...(action==='reserve'?{reserve:view.reserve}:{item:key}),uid:mon.uid,expectedHeld:mon.heldItemId||0};
  if(r.effect==='mail'){const message=h('input',{type:'text',maxlength:144,placeholder:'A message for your Pokémon…','aria-label':'Mail message','data-focus':'item-mail-message'});message.value=view.message||'';const sync=()=>{itemView.message=message.value;if(message.value.trim())giving.message=message.value;else delete giving.message;};message.addEventListener('input',sync);sync();body.append(h('label',{},'Message (optional · 144 characters)',message),h('p',{class:'mini-note'},'Your message stays with the Pokémon holding this Mail. Leave blank to keep a previously saved message.'));}
  body.append(h('p',{},'The previous held item is returned to your Bag or source-specific reserve. Nothing is discarded.'),commit('Confirm held item','item.give',giving));foot();return;
 }
 if(action==='feed'){
  const block=(state.pokeblocks||[]).find(b=>b.id===view.block);body.append(h('p',{},'Condition: '+JSON.stringify(mon.condition||{})),commit('Feed selected block','item.service',{item:key,action:'feed',block:view.block,uid:mon.uid},!block));foot();return;
 }
 const payload={item:key,...(mon?{uid:mon.uid}:{})};let disabled=false;
 if(key==='fr_liftkey'){
  const destinations=state.itemContext?.elevatorDestinations||[];disabled=!destinations.length;
  if(destinations.length){const selector=h('select',{'aria-label':'Elevator destination','data-focus':'item-elevator-floor'});for(const floor of destinations)selector.append(h('option',{value:floor.id},floor.label));const selected=destinations.find(floor=>floor.id===view.destination)||destinations[0];selector.value=selected.id;payload.destination=selected.id;itemView.destination=selected.id;selector.addEventListener('change',()=>showItemAction({...itemView,destination:selector.value}));body.append(h('label',{},'Choose your destination',selector),h('p',{class:'modal-description'},'Set the floor, then step through the elevator doors.'));}
  else body.append(h('p',{class:'modal-description'},'Enter the Rocket Hideout elevator to choose a destination. Keep the Lift Key in your Bag.'));
 }

 if(r.target==='move'||r.effect==='machine'){
  const selection=h('select',{'aria-label':'Item move slot','data-focus':'item-move'}),valid=[];
  for(let i=0;i<mon.moves.length;i++){const m=mon.moves[i],move=content.moves[m.id];const allowed=r.effect==='machine'||r.effect==='ppboost'?(r.effect==='machine'||(m.id!==166&&move.pp>1&&(m.ppUps||0)<3)):m.pp<maximumPP(m);if(allowed)valid.push(i);selection.append(h('option',{value:i,disabled:!allowed},(r.effect==='machine'?'Replace ':'')+move.name+' · '+m.pp+'/'+maximumPP(m)+' PP'));}
  if(r.effect==='machine'&&mon.moves.length<4){valid.unshift(mon.moves.length);selection.prepend(h('option',{value:mon.moves.length},'Learn in empty slot'));}
  const slot=valid.includes(view.slot)?view.slot:valid[0];selection.value=slot??'';disabled=slot==null;selection.disabled=disabled;payload.slot=slot;if(slot<mon.moves.length)payload.expectedMove=mon.moves[slot].id;
  selection.addEventListener('change',()=>showItemAction({...itemView,slot:Number(selection.value)}));body.append(h('label',{},r.effect==='machine'?'Choose a slot for '+content.moves[r.move].name:'Choose the move',selection));
  if(r.effect==='machine')body.append(h('p',{class:'mini-note'},'Confirming replaces only the chosen move. '+(r.reusable?'This HM is reusable.':'One TM is consumed on success.')));
 }
 if(r.effect==='evolution'){
  const options=(mon.evolutions||[]).filter(e=>!e.deferred&&e.item===(r.evolutionAlias||key)),selection=h('select',{'aria-label':'Evolution target'});for(const e of options)selection.append(h('option',{value:e.target},e.name));const selected=options.find(e=>e.target===view.target)||options[0];payload.target=selected?.target;disabled=!selected;selection.value=payload.target||'';selection.addEventListener('change',()=>showItemAction({...itemView,target:selection.value}));body.append(h('label',{},'Confirm evolved form',selection));
 }
 if(r.effect==='repel'){disabled=(state.repelSteps||0)>0;body.append(h('p',{},disabled?'A Repel is active: '+state.repelSteps+' steps remain.':'Prevents encounters below your first party Pokémon’s level for '+r.steps+' successful steps.'));}
 if(r.effect==='escape'){disabled=!state.itemContext?.escape;body.append(h('p',{},disabled?'Escape Rope can be used inside a suitable cave or dungeon.':'Returns to this dungeon’s recorded entrance. One Escape Rope is consumed on success.'));}
 if(r.effect==='fossil'){disabled=!state.itemContext?.fossilLab||!!state.itemContext?.fossilPending;body.append(h('p',{},state.itemContext?.fossilPending?'A fossil is already being restored. Leave the lab and return to the scientist to collect your Pokémon.':'Give this fossil to the restoration scientist at Cinnabar Lab. Leave the room and return to collect the revived Pokémon.'));}
 if(r.effect==='vsseeker'){const charge=state.itemContext?.vsSeekerCharge||0;disabled=charge<100;body.append(h('p',{},'VS Seeker charge: '+charge+' / 100 steps.'),h('p',{},disabled?'Walk to recharge, then use it near trainers you have already defeated.':'Searches for nearby defeated trainers who are ready for a rematch.'));}
 if(r.effect==='bicycle')body.append(h('p',{},state.itemContext?.bicycle?'You are riding your Bicycle. Confirm to get off.':'Ride faster on permitted outdoor routes. You cannot ride inside buildings or while surfing.'));
 if(r.effect==='fishing')body.append(h('p',{},'Face an adjacent water tile and cast your line. A successful bite starts a wild battle.'));
 if(r.effect==='itemfinder')body.append(h('p',{},'Checks the area for hidden items. Follow the signal, face the nearby tile, then press E to pick it up.'));
 if(['bicycle','fishing','itemfinder','fossil','encounterflute','vsseeker'].includes(r.effect)&&own?.map&&!own.map.startsWith('kanto_')){disabled=true;body.append(h('p',{class:'mini-note'},'Use this FireRed field item in Kanto.'));}
 body.append(commit(key==='fr_liftkey'?'Confirm floor':r.effect==='machine'?'Confirm teaching':r.effect==='evolution'?'Confirm evolution':'Confirm use','use',payload,disabled,['escape','story','bicycle','fishing','itemfinder','fossil','encounterflute','pokeflute','vsseeker'].includes(r.effect)));foot();
}
function appendBattleItems(options,b){
 const inventory=b.items||state.items||{},select=h('select',{'aria-label':'Battle item'},h('option',{value:''},'Choose an item…')),detail=h('div',{class:'battle-item-detail'});
 for(const [key,item] of Object.entries(content.items)){const r=itemRule(key);if(!inventory[key]||!r.battle||r.effect==='tera'||r.safariOnly&&!b.safari||r.effect==='capture'&&b.kind!=='wild')continue;const mod=b.captureModifiers?.[key];select.append(h('option',{value:key},item.name+' × '+inventory[key]+(mod!=null?' · '+(['masterball','fr_masterball'].includes(key)?'Guaranteed':Number(mod).toFixed(1)+'×'):'')));}
 select.disabled=b.waiting;
 const render=(uid=null,slot=null)=>{detail.replaceChildren();const key=select.value,item=content.items[key];if(!item)return;const r=itemRule(key);detail.append(h('p',{class:'mini-note'},item.description||r.description||''));const data={item:key};let mon=null,disabled=false;
  if(['pokemon','move'].includes(r.target)){const chosen=itemPokemonSelector(key,'use',uid,next=>render(next,null),true,b.party);mon=chosen.mon;detail.append(chosen.select);data.uid=mon?.uid;disabled=!mon;}
  if(mon&&r.target==='move'){
   const moves=h('select',{'aria-label':'Battle item move'}),eligible=[];for(let i=0;i<mon.moves.length;i++){const move=mon.moves[i],ok=move.pp<maximumPP(move);if(ok)eligible.push(i);moves.append(h('option',{value:i,disabled:!ok},content.moves[move.id].name+' · '+move.pp+'/'+maximumPP(move)+' PP'));}const index=eligible.includes(slot)?slot:eligible[0];moves.value=index??'';data.slot=index;data.expectedMove=mon.moves[index]?.id;disabled=index==null;moves.disabled=disabled;moves.addEventListener('change',()=>render(mon.uid,Number(moves.value)));detail.append(moves);
  }
  const apply=button(r.effect==='capture'?'Throw '+item.name:'Use '+item.name,()=>battleAction(r.effect==='capture'?'capture':'item',data),'primary',b.waiting||disabled);detail.append(apply);
 };
 select.addEventListener('change',()=>render());options.append(select,detail);
}

function showAtlas(){if(!session||trade||$('battle-dialog').open)return;const body=openModal('World atlas','atlas','min(66rem,93vw)');body.append(h('p',{class:'modal-description'},session.alphaAtlas?'Exploration travel is enabled on this world. Choose a destination in Kanto or Johto / Sigma. Some original scripted exits are still in development.':state?.adventure?.unlocks.includes('travel_pass')?'Your Travel Pass is ready. Return to discovered outdoor waypoints or either starting town. Enter buildings and other interiors through their doors.':'Explore the atlas and discover routes on foot. Earn two gym badges to unlock travel between discovered outdoor waypoints and the starting towns. Enter interiors through their doors.'));const search=h('input',{placeholder:'Search a town, route, cave or map ID…','aria-label':'Search atlas'}),filter=h('select',{'aria-label':'Atlas region'},h('option',{value:'featured'},'Towns & routes'),h('option',{value:'kanto'},'Kanto · FireRed'),h('option',{value:'johto'},'Johto / Sigma'),h('option',{value:'all'},'All extracted maps'));const grid=h('div',{class:'content-grid'}),count=h('p',{class:'mini-note'});body.append(h('div',{class:'atlas-controls'},search,filter),count,grid);
 const refresh=()=>{const term=search.value.trim().toLowerCase();let maps=Object.values(content.maps).filter(m=>filter.value==='featured'?[1,2,3].includes(m.mapType):filter.value==='all'||m.id.startsWith(filter.value));maps=maps.filter(m=>(filter.value==='all'||m.playable!==false)&&(m.name+' '+m.id).toLowerCase().includes(term));maps.sort((a,b)=>((b.id==='kanto_3_0'||b.id==='johto_3_0')?1:0)-((a.id==='kanto_3_0'||a.id==='johto_3_0')?1:0)||a.name.localeCompare(b.name)||a.id.localeCompare(b.id));count.textContent=maps.length+' destinations · '+(maps.length>120?'Showing first 120; refine your search.':'Select a destination to travel.');grid.replaceChildren();for(const m of maps.slice(0,120)){const card=button('',()=>{send('travel',{map:m.id});closeModal(true);},'map-card'+(m.id==='kanto_3_0'||m.id==='johto_3_0'?' featured':''),!canTravelTo(m));card.append(h('span',{class:'eyebrow'},m.region),h('strong',{},m.name),h('small',{},m.playable===false?'Unavailable':canTravelTo(m)?'Travel to this waypoint':![1,2,3].includes(m.mapType)?'Enter through its door':state?.adventure?.visited.includes(m.id)?'Discovered · Travel Pass required':'Not yet visited'));grid.append(card);}};search.addEventListener('input',refresh);filter.addEventListener('change',refresh);refresh();}
function showHelp(){if(!canOpen())return;const body=openModal('Controls & adventure guide','help');const entries=[['Pokémon varieties','Ancient, Metallic, Shiny, Mystic and Shadow are rare cosmetic identities rolled by the server after the map chooses a species and level. Captures keep their variety through storage, trading and evolution. Search your collection by variety name. Followers keep their normal sprite with coloured sparkles; reduced-motion mode uses static markers. All player-side battle sprites use horizontally flipped fronts.'],['Surf with your partner','Earn Koga’s Soul Badge for Kanto, or Morty’s Fog Badge for Johto. Bring a Water-type Pokémon in your party; it does not need to know Surf. Stand on a shore near water and use the Surf button. The server chooses your first Water-type party member, including a fainted partner. Movement carries you across water with that Pokémon; step onto a walkable shore to dismount. Each region requires its own badge.'],['HM Cut','Defeat Misty in Kanto or Bugsy in Johto to learn Cut automatically for that region. Click a nearby small HM tree (or press E), then choose Cut tree. A locked button explains the badge requirement. Only your character’s tree and collision are removed, including after relogging.'],['Route 36 odd tree','Defeat Whitney in Goldenrod City to earn the Plain Badge and saved SquirtBottle. Approach the odd tree on Route 36, interact with it and choose Use SquirtBottle to battle Lv. 20 Sudowoodo. Defeat or capture it to clear that path permanently for your character; running or losing leaves it blocked.'],['Explore','WASD or arrow keys move. E interacts with a nearby object or character. Visible and hidden field items are saved per character in Kanto and Johto / Sigma. Use the Itemfinder to check for nearby hidden items, then face the tile and press E. Walk into tall grass for encounters, or use Search for wild on an encounter tile.'],['Meet trainers','Click another trainer or their nameplate. Challenge starts a friendly duel; Trade opens a two-sided exchange after they accept.'],['Build your team','P opens your party and PC storage. Inspect a Pokémon for move-learning and evolution choices. Party order controls your follower. Deposit and withdraw at a Pokémon Center PC.'],['Battle','Choose a move, switch partners or use an item. Throw balls in wild battles to catch Pokémon. Trainer battles cannot be fled. Friendly duels do not spend items or persist HP loss.'],['Visit a Pokémon Center','Enter a Pokémon Center, approach Nurse Joy and press E. Ask her to heal your party and restore their HP and PP. You can access Pokémon storage there, too.'],['Your adventure','J opens badges and adventure goals. Claim completed goal rewards from your journal. G opens the Pokédex, where your encounters and catches are recorded. M opens the world atlas; B opens supplies.'],['Saving','Your progress saves automatically on the server. Save now requests an extra save. Log back in with the same account to continue your adventure.'],['Display & chat','Enter focuses chat; Escape leaves a text field. + and − adjust crisp integer world zoom. F11 toggles fullscreen. Sound controls are in the top bar and battles.']];body.append(h('div',{class:'help-grid'},entries.map(([title,text])=>h('div',{},h('h3',{},title),h('p',{},text)))));body.append(h('p',{class:'mini-note'},'Adventure alpha: Johto / Sigma NPC talk text is restored from the reviewed ROM, while original story-script control flow, all abilities and every advanced move effect are not yet recreated. Exploration helpers depend on the world configuration.'));}
function showNpcDialog(p){
 if(!canOpen()||(p.map&&p.map!==own?.map)||renderer.pendingMap)return;const body=openModal(p.title,'npc');body.append(h('p',{class:'modal-description'},p.message));
 const actions=h('div',{class:'modal-actions'});
 for(const action of p.actions||[]){
  if(action==='shop')actions.append(button('Open supplies',showBag,'primary'));
  else if(action==='apricorn')actions.append(button('Make a Fast Ball',()=>showItemAction({key:'whtapricorn',action:'craft'}),'primary'));
  else if(action==='cut'){
   const locked=(p.disabledActions||[]).includes('cut')||!p.fieldMove?.unlocked||p.fieldMove?.cleared;
   const label=p.fieldMove?.cleared?'Tree already cleared':locked?'Cut tree — locked':'Cut tree';
   const cut=commandButton(label,'npc',{npc:p.npc,map:p.map,action:'cut'},'primary cut-tree-button',!!locked,true);
   cut.setAttribute('aria-disabled',String(!!locked));
   if(locked)cut.setAttribute('title',p.fieldMove?.cleared?'Already cleared for your character.':'Requires '+(p.fieldMove?.badgeName||'the regional badge')+'.');
   actions.append(cut);
   body.append(h('p',{class:'field-move-note'},'Personal path: cutting is saved for your character only. Other trainers still see and must cut their own tree.'));
  }
  else if(action==='squirtbottle'){
   const locked=(p.disabledActions||[]).includes('squirtbottle')||!p.storyEvent?.ready||p.storyEvent?.cleared;
   const label=p.storyEvent?.cleared?'Route already clear':!p.storyEvent?.badgeEarned?'Use SquirtBottle — Plain Badge required':!p.storyEvent?.itemOwned?'Use SquirtBottle — not obtained':'Use SquirtBottle';
   const use=commandButton(label,'npc',{npc:p.npc,map:p.map,action:'squirtbottle'},'primary story-event-button',!!locked,true);use.setAttribute('aria-disabled',String(!!locked));
   if(locked)use.setAttribute('title',p.storyEvent?.cleared?'Already cleared for this character.':!p.storyEvent?.badgeEarned?'Defeat '+(p.storyEvent?.leader||'the Gym Leader')+' and earn the '+(p.storyEvent?.requiredBadgeName||'required badge')+'.':'You do not have the '+(p.storyEvent?.itemName||'required Key Item')+'.');
   actions.append(use);body.append(h('p',{class:'field-move-note'},'Personal story path: defeating or catching this Pokémon clears the obstacle only for your character. The SquirtBottle is not consumed.'));
  }
  else if(action==='push_boulder'||action==='smash_rock')actions.append(commandButton(action==='push_boulder'?'Push boulder':'Smash rock','npc',{npc:p.npc,map:p.map,action},'primary',(p.disabledActions||[]).includes(action),true));
  else if(action==='safari_enter')actions.append(commandButton('Enter Safari Game · ₽500','npc',{npc:p.npc,map:p.map,action},'primary',(p.disabledActions||[]).includes(action)||state.money<500,true));
  else if(action==='pokeflute'||action==='fossil_collect')actions.append(commandButton(action==='pokeflute'?'Play Poké Flute':'Collect revived Pokémon','npc',{npc:p.npc,map:p.map,action},'primary',(p.disabledActions||[]).includes(action),true));
  else if(action==='battle')actions.append(commandButton('Challenge trainer','npc',{npc:p.npc,action:'battle'},'primary',false,true));
  else if(action==='heal'){
   body.append(h('div',{class:'nurse-care'},h('span',{class:'care-symbol','aria-hidden':'true'},'♥'),h('div',{},h('h3',{},'A little rest for your partners'),h('p',{},'Nurse Joy will restore your party’s HP, PP and status. Would you like her to take care of them?'))));
   actions.append(commandButton('Yes, please heal my party','npc',{npc:p.npc,action:'heal'},'primary',false,true));
  }else if(action==='pc')actions.append(button('Open Pokémon storage',()=>showCollection('storage'),'secondary',!state.adventure?.pcAvailable));
 }
 for(const gift of p.giftOptions||[]){const item=content.items[gift.item],row=h('div',{class:'npc-gift'});if(item)row.append(itemIcon(item));row.append(h('div',{},h('strong',{},item?.name||gift.label||'Item gift'),h('p',{},gift.ready?'Ready to receive':gift.reason||'Continue your adventure to receive this item.')),commandButton(gift.label||'Receive item','npc',{npc:p.npc,map:p.map,action:'gift:'+gift.id},'primary',!gift.ready,true));body.append(row);}
 actions.append(button('Close',()=>closeModal(true),'quiet'));body.append(actions);
}
function interact(){if(!renderer.map||!own||renderer.pendingMap||renderer.map.id!==own.map)return;send('interact',{map:own.map});}
function picked(hit,x,y){if(!session||$('modal').open||$('battle-dialog').open)return;if(hit.kind==='npc'){if(renderer.pendingMap||renderer.map?.id!==own?.map||hit.map!==own.map||!renderer.objectVisible(renderer.map.objects.find(n=>n.id===hit.id)))return;send('npc',{npc:hit.id,map:own.map});return;}const player=renderer.players.get(hit.id);if(!player||hit.id===session.id)return;const menu=$('context-menu');menu.replaceChildren(h('div',{class:'menu-title'},player.username));if(player.autonomous){menu.append(h('div',{class:'menu-meta'},(player.tier||'Ranked')+' · '+(player.rating||1000)+' rating'),button('Battle autonomous trainer',()=>{send('ai.challenge',{id:player.aiId});menu.classList.add('hidden');},'primary'));}else menu.append(button('Challenge to a duel',()=>{send('invite',{kind:'challenge',target:player.id});menu.classList.add('hidden');}),button('Trade Pokemon & items',()=>{send('invite',{kind:'trade',target:player.id});menu.classList.add('hidden');}));menu.append(button('View first partner',()=>{menu.classList.add('hidden');const sp=content.species[player.follower];const body=openModal(player.username+'’s first partner','inspect');if(sp){const partner=followerPokemon(player);body.append(h('article',{class:'collection-card'},h('img',{src:sprite(partner),alt:monName(partner)}),h('strong',{},monName(partner)),varietyBadge(partner),h('span',{},'Follower of '+player.username),h('p',{class:'mini-note'},varietyKey(partner)==='normal'?'Regular field sprite.':'Normal field sprite with '+varietyDefinition(content,partner).label.toLowerCase()+'-coloured sparkles.')));}}),button(mutedNames.has(player.username)?'Unmute chat locally':'Mute chat locally',()=>{if(mutedNames.has(player.username))mutedNames.delete(player.username);else mutedNames.add(player.username);renderChat();menu.classList.add('hidden');},'quiet'));menu.classList.remove('hidden');menu.style.left=Math.min(x,innerWidth-menu.offsetWidth-12)+'px';menu.style.top=Math.min(y,innerHeight-menu.offsetHeight-12)+'px';}
function showInvite(p){if(trade||$('battle-dialog').open){send('invite.answer',{id:p.id,accept:false});return;}invite=p;const body=openModal(p.kind==='trade'?'Trade invitation':'Trainer challenge','invite');body.append(h('p',{class:'modal-description'},p.trainer+(p.kind==='trade'?' would like to trade with you.':' challenged you to a friendly duel.')));body.append(h('p',{class:'mini-note'},'Invitation expires after '+p.seconds+' seconds. You must stay nearby.'),h('div',{class:'modal-actions'},button('Decline',()=>{send('invite.answer',{id:p.id,accept:false});invite=null;closeModal(true);},'quiet'),button('Accept invitation',()=>{send('invite.answer',{id:p.id,accept:true});invite=null;closeModal(true);},'primary')));}
function renderTrade(){if(!trade||!state)return;const t=trade,body=openModal('Trade with '+t.otherName,'trade','min(62rem,94vw)');const both=t.ready.length===2;body.append(h('p',{class:'trade-warning'},both?'Both offers are locked. Check the Pokemon, items and money on BOTH sides before final confirmation. Any offer edit resets both confirmations.':'Nothing moves until both trainers lock their offers and confirm the exact same exchange. You can cancel before the final commit.'));
 const sides=h('div',{class:'trade-grid'});for(const id of [t.you,t.other]){const offer=t.offers[id],box=h('section',{class:'trade-side'},h('h3',{},id===t.you?'Your offer':t.otherName+'’s offer')),detail=h('div',{class:'trade-offer'});for(const mon of offer.pokemon)detail.append(h('div',{class:'offer-mon'},h('img',{src:sprite(mon),alt:monName(mon)}),h('span',{},monName(mon)+' · Lv. '+mon.level)));for(const [key,n] of Object.entries(offer.items))if(n)detail.append(h('p',{class:'offer-item'},content.items[key].name+' × '+n));if(offer.money)detail.append(h('p',{class:'offer-item'},money(offer.money)));if(!offer.pokemon.length&&!Object.values(offer.items).some(Boolean)&&!offer.money)detail.append(h('p',{class:'mini-note'},'No assets offered.'));box.append(detail,h('div',{class:'trade-status'},t.confirmed.includes(id)?'✓ FINAL CONFIRMATION RECEIVED':t.ready.includes(id)?'✓ OFFER LOCKED':'EDITING OFFER'));sides.append(box);}body.append(sides);
 const ownOffer=t.offers[t.you],editor=h('section',{class:'trade-editor'},h('h3',{},'Edit your offer')),picker=h('div',{class:'trade-picker'}),selected=new Set(ownOffer.pokemon.map(m=>m.uid));for(const mon of state.creatures){const check=h('input',{type:'checkbox',checked:selected.has(mon.uid),'data-mon':mon.uid});picker.append(h('label',{},check,monName(mon)+' · Lv. '+mon.level));}editor.append(h('p',{class:'mini-note'},'Select up to six Pokemon. A trade may not leave either trainer without a Pokemon.'),picker);
 const numbers=h('div',{class:'trade-numbers'});const cash=h('input',{type:'number',min:0,max:state.money,step:1,value:ownOffer.money||0,'aria-label':'Money offered'});numbers.append(h('div',{},h('label',{},'Money · own '+money(state.money)),cash));const itemInputs={};for(const [key,item] of Object.entries(content.items)){if(item.tradable===false||!(state.items[key]||0))continue;const input=h('input',{type:'number',min:0,max:state.items[key]||0,step:1,value:ownOffer.items[key]||0,'aria-label':item.name+' offered'});itemInputs[key]=input;numbers.append(h('div',{},h('label',{},item.name+' · own '+(state.items[key]||0)),input));}editor.append(numbers);
 function apply(){const pokemon=[...picker.querySelectorAll('input:checked')].map(i=>i.dataset.mon);if(pokemon.length>6){toast('You can offer at most six Pokemon.','error');return;}const items={};for(const [key,input] of Object.entries(itemInputs)){const n=Number(input.value);if(!Number.isSafeInteger(n)||n<0){toast('Item quantities must be whole, non-negative numbers.','error');return;}if(n)items[key]=n;}const amount=Number(cash.value);if(!Number.isSafeInteger(amount)||amount<0){toast('Money must be a whole, non-negative number.','error');return;}send('trade',{id:t.id,action:'offer',revision:t.revision,offer:{pokemon,items,money:amount}});}
 editor.append(h('div',{class:'modal-actions'},button('Apply edited offer',apply,'secondary')));body.append(editor,h('p',{class:'digest-note'},'Offer revision '+t.revision+' · Verification '+t.digest.slice(0,24)+'… · '+t.seconds+' seconds remaining'));
 const lockButton=button(t.ready.includes(t.you)?'Your offer is locked':'Lock current offer',()=>send('trade',{id:t.id,action:'lock',revision:t.revision}),'secondary',t.ready.includes(t.you));
 const confirmButton=button(t.confirmed.includes(t.you)?'Waiting for final confirmation':'Confirm this exact exchange',()=>send('trade',{id:t.id,action:'confirm',revision:t.revision,digest:t.digest}),'primary',!both||t.confirmed.includes(t.you));
 const draftNote=h('p',{class:'mini-note hidden'},'Unsubmitted changes: apply your edited offer before locking or confirming. The offer panels above show the last server-accepted exchange.');
 editor.append(draftNote);editor.addEventListener('input',()=>{lockButton.disabled=true;confirmButton.disabled=true;draftNote.classList.remove('hidden');});
 body.append(h('div',{class:'modal-actions'},button('Cancel exchange',()=>send('trade',{id:t.id,action:'cancel'}),'quiet danger'),lockButton,confirmButton));
}
function combatCard(mon,side){return h('div',{class:'combat-card '+side},h('div',{class:'party-name'},h('strong',{},monName(mon)),h('span',{},'Lv. '+mon.level)),h('div',{class:'party-meta'},h('span',{},mon.status?mon.status.toUpperCase():'HP'),h('span',{},mon.hp+' / '+mon.maxHp)),hpBar(mon));}
function resetBattlePresentation(){battleFX?.reset();battleEffectsDisabled=false;battleSubmitting=false;clearTimeout(battleSubmitTimer);battleSubmitTimer=null;}
function disableBattleEffects(error){battleEffectsDisabled=true;battleFX?.reset();console.warn('Battle animations disabled; authoritative battle controls remain available.',error);}
function battleAction(action,extra={}){
 if(!activeBattle||activeBattle.ended||activeBattle.waiting||battleSubmitting||battleFX?.busy)return;
 try{if(!send('battle',{id:activeBattle.id,action,...extra}))return;battleSubmitting=true;const id=activeBattle.id;battleSubmitTimer=setTimeout(()=>{if(activeBattle?.id!==id)return;battleSubmitting=false;if(!battleFX?.busy)renderBattle();toast('Still waiting for the world server. Check your connection if the turn does not resolve.','warn');},12000);renderBattle();}catch(error){battleSubmitting=false;toast('The action could not be sent. Reconnect and try again.','error');renderBattle();}
}
function appendSafariActions(choices,b){
 const safari=b.safari;choices.append(h('div',{class:'safari-summary'},h('span',{},'SAFARI GAME'),h('strong',{},safari.balls+' Safari Balls left')),h('p',{class:'modal-description'},safari.baitTurns?'The wild Pokémon is eating.':safari.rockTurns?'The wild Pokémon is angry!':'Watch carefully and choose your approach.'));
 const actions=h('div',{class:'move-grid safari-actions'},button('Throw Safari Ball',()=>battleAction('capture',{item:'fr_safariball'}),'primary',b.waiting||safari.balls<1),button('Throw Bait',()=>battleAction('bait'),'secondary',b.waiting),button('Throw Rock',()=>battleAction('rock'),'secondary',b.waiting),button('Run',()=>battleAction('run'),'quiet danger',b.waiting));choices.append(actions,h('p',{class:'mini-note'},'Bait encourages Pokémon to stay but makes them harder to catch. Rocks improve the catch chance but may scare them away.'));
}
function renderBattle(){if(!activeBattle||battleFX?.busy&&battleFX.matches(activeBattle))return;battleFX??=new BattleFX();keys.clear();const b=activeBattle,root=$('battle-content');root.replaceChildren();root.append(h('header',{class:'battle-head'},h('div',{},h('span',{class:'eyebrow'},b.safari?'SAFARI ZONE':b.kind==='duel'?'FRIENDLY TRAINER DUEL':b.kind==='trainer'?'TRAINER BATTLE':'WILD ENCOUNTER'),h('h2',{},session.username+' vs '+b.opponentName)),h('div',{class:'toolbar-actions'},button('Sound',()=>audioControls?.open(),'quiet small'),h('span',{class:'pill'},b.ended?'BATTLE COMPLETE':'TURN '+b.turn+' · '+b.seconds+'s'))));const stage=h('div',{class:'battle-stage'},h('img',{class:'battle-sprite enemy','data-variety':varietyKey(b.opponent),src:sprite(b.opponent),alt:monName(b.opponent)}),h('img',{class:'battle-sprite you','data-variety':varietyKey(b.you),src:sprite(b.you,true),alt:monName(b.you)}),combatCard(b.opponent,'enemy'),combatCard(b.you,'you'));if(b.safari){stage.classList.add('safari-stage');stage.append(h('div',{class:'safari-stage-label'},'SAFARI ZONE',h('strong',{},b.safari.balls+' balls remaining')));}root.append(stage);const log=h('div',{class:'battle-log',role:'log'});for(const text of b.log)log.append(h('p',{},text));const choices=h('fieldset',{class:'battle-choice-panel','aria-label':'Battle actions'});
 if(b.ended){const result={caught:'A new partner joins your journey!',won:'Victory!',lost:'Your team fought bravely.',escaped:'You returned to the world.'}[b.result]||'Battle complete.';choices.append(h('h3',{class:'battle-result'},result),h('p',{class:'modal-description'},b.kind==='duel'?'Friendly duel finished. Your persistent party health and supplies were not spent.':'The world server has saved the completed actions.'),button('Return to adventure',()=>{resetBattlePresentation();$('battle-dialog').close();activeBattle=null;audio.setBattle(null);},'primary wide'));
 }else if(b.safari){appendSafariActions(choices,b);
 }else{
  if(b.waiting)choices.append(h('div',{class:'battle-wait'},'Action submitted. Waiting for the other trainer…'));
  const tera=h('input',{type:'checkbox','aria-label':'Terastallize with attack',disabled:b.waiting||!b.canTera});if(b.canTera)choices.append(h('label',{class:'tera-option'},tera,' Terastallize with attack · '+TYPES[b.teraType]+' (NXT adaptation)'));
  const moves=h('div',{class:'move-grid'});for(let i=0;i<b.you.moves.length;i++){const slot=b.you.moves[i],move=content.moves[slot.id];const enabled=b.usable.includes(i);const btn=button('',()=>battleAction('attack',{slot:i,...(tera.checked?{tera:true}:{})}),'move-button',b.waiting||!enabled);btn.title=enabled?'Use '+move.name:slot.pp<=0?'No PP remaining':'This move’s advanced effect is not implemented in this alpha.';btn.append(h('strong',{},move.name),h('small',{},h('span',{},TYPES[move.type]),h('span',{},slot.pp+' / '+maximumPP(slot)+' PP')));moves.append(btn);}if(!b.usable.length)moves.append(button('Struggle',()=>battleAction('attack',{slot:-1,...(tera.checked?{tera:true}:{})}),'move-button',b.waiting));choices.append(moves);
  const switcher=h('select',{'aria-label':'Switch active Pokemon'},h('option',{value:''},'Switch partner…'));for(const m of b.party)if(m.uid!==b.you.uid&&m.hp>0)switcher.append(h('option',{value:m.uid},monName(m)+' · Lv. '+m.level));switcher.disabled=b.waiting;switcher.addEventListener('change',()=>{if(switcher.value)battleAction('switch',{uid:switcher.value});});const options=h('div',{class:'battle-options'},switcher);
  if(b.kind!=='duel')appendBattleItems(options,b);
  options.append(button(b.kind==='duel'?'Forfeit':b.kind==='trainer'?'Cannot flee trainer battles':'Run',()=>battleAction('run'),'quiet danger',b.waiting||b.canRun===false||b.kind==='trainer'));choices.append(options,h('p',{class:'mini-note'},b.kind==='duel'?'A friendly match. No money or items are wagered.':'Choose a ball, or select an item and its target before confirming. Held items activate automatically when their conditions are met.'));
 }
 root.append(h('div',{class:'battle-controls'},log,choices));
 // Open the usable battle before starting optional presentation effects.
 if(!$('battle-dialog').open)$('battle-dialog').showModal();
 let started=false;try{if(!battleEffectsDisabled)started=battleFX.play(b,stage,{moveName:id=>content.moves[id]?.name||'Move',showSpecies:(image,event,side)=>{if(!image||!content.species[event.species])return;const current=side==='you'?b.you:b.opponent;const shown=eventPokemon(b,event,side);image.src=sprite(shown);image.alt=monName(shown);image.setAttribute('data-variety',varietyKey(shown));const card=stage.querySelector('.combat-card.'+side);if(card)card.style.visibility=current.species===event.species&&(!event.uid||current.uid===event.uid)&&varietyKey(current)===varietyKey(shown)?'':'hidden';},done:()=>{if(activeBattle?.id===b.id&&session)renderBattle();},failed:error=>{disableBattleEffects(error);if(activeBattle?.id===b.id&&session)renderBattle();}});else battleFX.skip(b);}catch(error){disableBattleEffects(error);renderBattle();return;}
 choices.disabled=!!(started||battleFX.busy||battleSubmitting);if(started||battleFX.busy||battleSubmitting)choices.prepend(h('p',{class:'battle-presentation-status',role:'status'},battleSubmitting?'Sending your action…':'Resolving the turn…'));
 log.scrollTop=log.scrollHeight;
}
function logout(){surfPending=null;resetBattlePresentation();mapSerial++;authAttempt++;setAuthBusy(false);audio.setScene('title');audio.setBattle(null);setMode('login');deliberateLogout=true;keys.clear();renderer.resetSession?.();renderer.active=false;if(ws)ws.close(1000,'User logout');session=null;state=null;own=null;trade=null;invite=null;activeBattle=null;renderer.players.clear();closeModal(true);$('battle-dialog').close();$('audio-dialog').close();$('disconnect-overlay').classList.add('hidden');$('game').classList.add('hidden');$('login').classList.remove('hidden');$('auth-submit').disabled=false;$('auth-submit').textContent='Enter world';connection('offline','Reconnect to continue your journey');}
function setupInput(){
 $('auth-form').addEventListener('submit',authenticate);$('login-tab').addEventListener('click',()=>setMode('login'));$('register-tab').addEventListener('click',()=>setMode('register'));$('reconnect').addEventListener('click',()=>{if(!loggingIn)connect().catch(e=>{$('auth-error').textContent=e.message;connection('offline','World server is unavailable');});});
 $('home').addEventListener('change',()=>{if(loggingIn)return;registrationSummary();audio.setRegion($('home').value);});
 $('logout').addEventListener('click',logout);$('disconnect-login').addEventListener('click',logout);$('modal-close').addEventListener('click',()=>closeModal());$('modal').addEventListener('cancel',e=>{e.preventDefault();closeModal();});$('battle-dialog').addEventListener('cancel',e=>{e.preventDefault();if(activeBattle?.ended){resetBattlePresentation();activeBattle=null;$('battle-dialog').close();audio.setBattle(null);}});
 $('chat-general').addEventListener('click',()=>changeChannel('general'));$('chat-trade').addEventListener('click',()=>changeChannel('trade'));$('chat-form').addEventListener('submit',e=>{e.preventDefault();const text=$('chat-input').value.trim();if(text&&send('chat',{channel,text}))$('chat-input').value='';});
 for(const [id,fn] of [['atlas-button',showAtlas],['collection-button',showCollection],['bag-button',showBag],['help-button',showHelp],['journal-button',showJournal],['dex-button',showDex],['ai-activity-button',()=>requestAIDashboard('activity')],['ladder-button',()=>requestAIDashboard('ladder')],['rivals-button',()=>requestAIDashboard('rivals')],['surf-button',requestSurf],['search-button',()=>send('encounter')],['save-button',()=>send('save')],['unstuck-button',()=>send('unstuck')]])$(id).addEventListener('click',fn);
 $('zoom-out').addEventListener('click',()=>renderer.setScale(renderer.scale-1));$('zoom-in').addEventListener('click',()=>renderer.setScale(renderer.scale+1));
 document.addEventListener('click',e=>{if(!e.target.closest('#context-menu')&&e.target!==$('world-canvas'))$('context-menu').classList.add('hidden');});
 const directions={w:'up',arrowup:'up',s:'down',arrowdown:'down',a:'left',arrowleft:'left',d:'right',arrowright:'right'};
 document.addEventListener('keydown',e=>{
  const key=e.key.toLowerCase(),typing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);if(e.key==='F11'){e.preventDefault();if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen().catch(()=>{});return;}
  if(typing){if(key==='escape'){document.activeElement.blur();keys.clear();}return;}if(!session)return;if($('modal').open||$('battle-dialog').open||$('audio-dialog').open)return;
  if(directions[key]){e.preventDefault();if(!e.repeat){keys.set(key,directions[key]);stepNow();}return;}if(e.repeat)return;
  if(key==='enter'){e.preventDefault();$('chat-input').focus();keys.clear();}else if(key==='e')interact();else if(key==='m')showAtlas();else if(key==='p')showCollection();else if(key==='b')showBag();else if(key==='j')showJournal();else if(key==='g')showDex();else if(key==='?'||key==='h')showHelp();else if(key==='+'||key==='=')renderer.setScale(renderer.scale+1);else if(key==='-')renderer.setScale(renderer.scale-1);
 });document.addEventListener('keyup',e=>keys.delete(e.key.toLowerCase()));window.addEventListener('blur',()=>keys.clear());
 function stepNow(){if(!session||!own||!keys.size||!renderer.map||renderer.pendingMap||renderer.map.id!==own.map||$('modal').open||$('battle-dialog').open||$('audio-dialog').open||!$('disconnect-overlay').classList.contains('hidden'))return;if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))return;const now=performance.now();if(pendingMove&&now-nextStep>1500)pendingMove=0;if(pendingMove||now<nextStep)return;const direction=[...keys.values()].at(-1);sequence++;pendingMove=sequence;nextStep=now+(state?.itemContext?.stepMs||session.stepMs||160)+5;send('move',{direction,seq:sequence});}
 setInterval(stepNow,16);
 setInterval(()=>{if(session){send('ping',{nonce:performance.now()});$('zoom-value').textContent=renderer.scale+'×';$('render-status').textContent=renderer.fps+' FPS · '+(window.devicePixelRatio||1)+'× DPI';}},2500);
}

async function persistAudioSettings(settings){
 audioSavePending={...settings};
 if(audioSaving)return;
 audioSaving=true;
 try{
  while(audioSavePending){
   const current=audioSavePending;audioSavePending=null;
   try{
    const response=await fetch('/audio-settings?token='+encodeURIComponent(config.nonce),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(current),keepalive:true});
    if(!response.ok)throw Error('Audio preferences could not be saved.');
    const saved=await response.json();audioControls?.setPersistence(saved.persisted===true);
   }catch{audioControls?.setPersistence(false);}
  }
 }finally{audioSaving=false;}
}

async function boot(){
 try{const [bootResponse,contentResponse]=await Promise.all([fetch('/bootstrap'),fetch('assets/world/client.json')]);if(!bootResponse.ok||!contentResponse.ok)throw Error('Start the game using Pokemon NXT MMO.exe. Do not open index.html directly.');[config,content]=await Promise.all([bootResponse.json(),contentResponse.json()]);if(config.uiScale)document.documentElement.style.fontSize=(14*config.uiScale)+'px';renderer=new WorldRenderer($('world-canvas'),content,picked);if(config.pixelScale)renderer.manualScale=config.pixelScale;starterChoices();setupInput();audioControls=mountAudioControls(audio);if(config.audioPersistenceMessage)audioControls.setPersistence(false);audio.init({settings:config.audio,onSettingsChange:persistAudioSettings}).catch(()=>{});audio.setScene('title');$('boot').classList.add('hidden');$('login').classList.remove('hidden');setMode('login');
  const heartbeat=()=>fetch('/heartbeat?token='+encodeURIComponent(config.nonce),{method:'POST',keepalive:true}).catch(()=>{});heartbeat();setInterval(heartbeat,15000);connect().catch(error=>{connection('offline','World server is unavailable');$('auth-error').textContent=error.message;$('auth-submit').disabled=false;});
 }catch(error){$('boot-message').textContent=error.message;console.error(error);}
}
boot();
