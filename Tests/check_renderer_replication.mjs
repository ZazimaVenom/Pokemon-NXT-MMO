import * as varietyPresentation from '../Client/app/varieties.js';
/** Actual renderer state under delayed local-map fetches; no browser pixels simulated. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=fs.readFileSync(new URL('../Client/app/renderer.js',import.meta.url),'utf8');
const entity=(id,map='johto_3_0',follower=id===1?'fr_152':'fr_4',x=id)=>({id,username:id===1?'Akumavenom':'Spidermight',map,x,y:10,fx:x-1,fy:10,direction:'down',appearance:0,follower,shiny:false,busy:false,surf:false});
const mapData=id=>({id,width:30,height:30,spawn:[10,10],objects:[],image:id+'.png'});
function harness(){
 const requests=[];
 const context=vm.createContext({...varietyPresentation,Map,performance:{now:()=>100},ResizeObserver:class{observe(){}},Image:class{complete=true;naturalWidth=64;},requestAnimationFrame(){},fetch:url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject})),console});
 vm.runInContext(source.replace(/^import .*?;\n/gm,'').replace('export class WorldRenderer','class WorldRenderer')+'\nglobalThis.Renderer=WorldRenderer;',context);
 const content={objects:{kanto:{0:{image:'trainer.png'}}},species:{fr_152:{icon:'chikorita.png'},fr_4:{icon:'charmander.png'},fr_1:{icon:'bulbasaur.png'}}};
 const r=new context.Renderer({getContext:()=>({}),addEventListener(){}},content,()=>{});
 const resolve=(index,id)=>requests[index].resolve({ok:true,json:async()=>mapData(id)});
 return {r,requests,resolve};
}
test('first scene received before map assets finish retains both distinct followers',async()=>{
 const {r,resolve}=harness();const pending=r.loadMap('johto_3_0',entity(1));
 r.scene({map:'johto_3_0',players:[entity(1),entity(2)],gone:[]});resolve(0,'johto_3_0');assert.equal(await pending,true);
 assert.equal(r.players.size,2);assert.equal(r.players.get(1).follower,'fr_152');assert.equal(r.players.get(2).follower,'fr_4');
});
test('pending snapshot folds latest movement, lead changes, and departure in order',async()=>{
 const {r,resolve}=harness();const pending=r.loadMap('johto_3_0',entity(1));
 r.scene({map:'johto_3_0',players:[entity(2)],gone:[]});
 r.entity(entity(1,'johto_3_0','fr_4',8));
 r.scene({map:'johto_3_0',players:[entity(1,'johto_3_0','fr_1',9)],gone:[2]});
 resolve(0,'johto_3_0');await pending;
 assert.equal(r.players.size,1);assert.equal(r.players.get(1).x,9);assert.equal(r.players.get(1).follower,'fr_1');
});
test('map arrival seeds the owner without waiting for a second scene',async()=>{
 const {r,resolve}=harness();const pending=r.loadMap('johto_3_0',entity(1));resolve(0,'johto_3_0');await pending;
 assert.equal(r.players.get(1).username,'Akumavenom');
});
test('rapid A to B to A transition rejects stale completion and old-map entities',async()=>{
 const {r,resolve}=harness();const a=r.loadMap('johto_3_0',entity(1));
 r.scene({map:'johto_3_0',players:[entity(2)],gone:[]});
 const b=r.loadMap('kanto_3_0',entity(1,'kanto_3_0'));
 r.scene({map:'johto_3_0',players:[entity(2)],gone:[]});
 const last=r.loadMap('johto_3_0',entity(1,'johto_3_0','fr_152',12));
 r.scene({map:'kanto_3_0',players:[entity(2,'kanto_3_0')],gone:[]});
 resolve(1,'kanto_3_0');assert.equal(await b,false);resolve(0,'johto_3_0');assert.equal(await a,false);
 resolve(2,'johto_3_0');assert.equal(await last,true);assert.equal(r.players.size,1);assert.equal(r.players.get(1).x,12);
});
test('session reset invalidates pending map, owner identity and player hit targets',async()=>{
 const {r,resolve}=harness();r.active=true;r.selfId=1;r.hits=[{kind:'player',id:2}];
 const loading=r.loadMap('johto_3_0',entity(1));r.scene({map:'johto_3_0',players:[entity(2)],gone:[]});r.resetSession();
 resolve(0,'johto_3_0');assert.equal(await loading,false);assert.equal(r.players.size,0);assert.equal(r.map,null);assert.equal(r.selfId,null);assert.equal(r.hits.length,0);assert.equal(r.active,false);
});
test('loaded map applies a stationary follower switch only to its owning entity',async()=>{
 const {r,resolve}=harness();const loading=r.loadMap('johto_3_0',entity(1));resolve(0,'johto_3_0');await loading;
 r.scene({map:'johto_3_0',players:[entity(1),entity(2)],gone:[]});r.scene({map:'johto_3_0',players:[entity(2,'johto_3_0','fr_1')],gone:[]});
 assert.equal(r.players.get(1).follower,'fr_152');assert.equal(r.players.get(2).follower,'fr_1');
 r.scene({map:'johto_3_0',players:[],gone:[2]});assert.equal(r.players.has(2),false);
});
test('a failed retired map request cannot clear the current map or its players',async()=>{
 const {r,requests,resolve}=harness();const old=r.loadMap('kanto_3_0',entity(1,'kanto_3_0'));
 const current=r.loadMap('johto_3_0',entity(1));resolve(1,'johto_3_0');assert.equal(await current,true);
 requests[0].reject(Error('old fetch failed'));assert.equal(await old,false);assert.equal(r.map.id,'johto_3_0');assert.equal(r.players.get(1).follower,'fr_152');
});
test('a current map failure clears pending entities rather than displaying stale players',async()=>{
 const {r,requests}=harness();const pending=r.loadMap('johto_3_0',entity(1));r.scene({map:'johto_3_0',players:[entity(2)],gone:[]});
 requests[0].reject(Error('missing map'));await assert.rejects(pending,/missing map/);assert.equal(r.pendingMap,null);assert.equal(r.map,null);assert.equal(r.players.size,0);
});

test('private cut flags hide only a matching tree, not rocks, peers or another map',()=>{
 const {r}=harness(),tree={id:7,graphics:95},rock={id:8,graphics:96};
 r.map={...mapData('kanto_3_19'),objects:[tree,rock]};r.hits=[{kind:'npc',id:7,map:r.map.id},{kind:'npc',id:8,map:r.map.id},{kind:'player',id:2}];
 r.setCutTrees({'kanto_3_19':[7,8]});assert.equal(r.objectVisible(tree),false);assert.equal(r.objectVisible(rock),true);assert.equal(r.objectVisible(tree,'johto_3_19'),true);assert.deepEqual(r.hits.map(h=>h.id),[8,2]);
 assert.equal(r.map.objects.length,2);r.resetSession();assert.equal(r.cutTrees.size,0);assert.equal(r.objectVisible(tree,'kanto_3_19'),true);
});
test('cuts survive an in-flight map load and the next frame excludes both sprite and click target',async()=>{
 const {r,resolve}=harness();const loading=r.loadMap('johto_3_0',entity(1));r.setCutTrees({'johto_3_0':[7]});resolve(0,'johto_3_0');await loading;
 const tree={id:7,graphics:95,x:2,y:2},rock={id:8,graphics:96,x:3,y:2};r.map.objects=[tree,rock];
 r.content.objects.johto={95:{image:'tree.png',width:16,height:16,frames:1},96:{image:'rock.png',width:16,height:16,frames:1}};
 const drawn=[];r.ctx=new Proxy({drawImage:(img)=>drawn.push(img.src)}, {get:(o,k)=>k in o?o[k]:()=>{}});r.players.clear();r.active=true;r.width=400;r.height=400;r.dpr=1;r.rootFont=16;r.map.spawn=[2,2];r.frame(101);
 assert.equal(r.objectVisible(tree),false);assert.equal(r.hits.some(h=>h.id===7),false);assert.equal(r.hits.some(h=>h.id===8),true);assert.equal(drawn.includes('assets/tree.png'),false);assert.equal(drawn.includes('assets/rock.png'),true);assert.equal(r.hits[0].map,'johto_3_0');
});
test('a fresh authoritative snapshot replaces rather than merges private flags',()=>{
 const {r}=harness();r.setCutTrees({'kanto_3_19':[7,true,'8',-1,256]});assert.equal(r.cutTrees.get('kanto_3_19').size,1);r.setCutTrees({});assert.equal(r.cutTrees.size,0);r.setCutTrees(null);assert.equal(r.cutTrees.size,0);
});

test('owner story completion hides only its authored Sudowoodo object and resets cleanly',()=>{
 const {r}=harness(),tree={id:3,graphics:98,storyEvent:'johto_sudowoodo'},other={id:4,graphics:98};r.map={...mapData('johto_2_23'),objects:[tree,other]};r.hits=[{kind:'npc',id:3,map:r.map.id},{kind:'npc',id:4,map:r.map.id}];r.setStoryEvents(['johto_sudowoodo',7,null]);assert.equal(r.objectVisible(tree),false);assert.equal(r.objectVisible(other),true);assert.deepEqual(r.hits.map(h=>h.id),[4]);r.setStoryEvents([]);assert.equal(r.objectVisible(tree),true);r.setStoryEvents(['johto_sudowoodo']);r.resetSession();assert.equal(r.storyEvents.size,0);assert.equal(r.objectVisible(tree),true);
});

test('owner field-item collection hides only the matching Poké Ball and resets cleanly',()=>{
 const {r}=harness(),ball={id:6,graphics:92,itemPickup:'johto_3_7:6'},other={id:7,graphics:92,itemPickup:'johto_3_7:7'};r.map={...mapData('johto_3_7'),objects:[ball,other]};r.hits=[{kind:'npc',id:6,map:r.map.id},{kind:'npc',id:7,map:r.map.id}];
 r.setItemPickups(['johto_3_7:6',7,null]);assert.equal(r.objectVisible(ball),false);assert.equal(r.objectVisible(other),true);assert.deepEqual(r.hits.map(h=>h.id),[7]);r.setItemPickups([]);assert.equal(r.objectVisible(ball),true);r.setItemPickups(['johto_3_7:6']);r.resetSession();assert.equal(r.itemPickups.size,0);assert.equal(r.objectVisible(ball),true);
});

test('native door tiles replace immutable door art with ground before actors and retain private map scope',()=>{
 const {r}=harness();r.map={...mapData('kanto_1_48'),overlay:'old-overlay.png',fieldTiles:{821:{ground:'door-open.png',overlay:null}}};
 r.setFieldTiles('kanto_1_48',[{x:5,y:8,metatile:821},{x:-1,y:8,metatile:821},{x:6,y:8,metatile:999}]);
 assert.equal(r.activeFieldTiles().length,1);
 const drawn=[],clips=[];r.ctx=new Proxy({drawImage:(img)=>drawn.push(img.src),clip:rule=>clips.push(rule)}, {get:(o,k)=>k in o?o[k]:()=>{}});r.active=true;r.width=500;r.height=500;r.dpr=1;r.rootFont=16;r.frame(101);
 assert.ok(drawn.includes('assets/door-open.png'));assert.ok(drawn.indexOf('assets/door-open.png')<drawn.indexOf('assets/old-overlay.png'));assert.deepEqual(clips,['evenodd']);
 r.map={...mapData('kanto_1_49'),fieldTiles:r.map.fieldTiles};assert.equal(r.activeFieldTiles().length,0);
 r.resetSession();assert.equal(r.fieldTiles.tiles.length,0);
});

test('conditional ground gift removal prunes click targets without removing the shared native object',()=>{
 const {r}=harness(),fossil={id:1,graphics:98,x:5,y:3},npc={id:2,graphics:30,x:6,y:3};r.map={...mapData('kanto_1_3'),objects:[fossil,npc]};
 r.hits=[{kind:'npc',id:1,map:r.map.id},{kind:'npc',id:2,map:r.map.id},{kind:'player',id:5}];r.setRemovedObjects({'kanto_1_3':[1]});
 assert.equal(r.objectVisible(fossil),false);assert.equal(r.objectVisible(fossil,'johto_1_3'),true);assert.equal(r.objectVisible(npc),true);assert.deepEqual(r.hits.map(h=>h.id),[2,5]);assert.equal(r.map.objects.length,2);
 r.resetSession();assert.equal(r.removedObjects.size,0);
});

function surfCanvas(r){const calls=[];r.ctx=new Proxy({drawImage:(img,...args)=>calls.push(['image',img.src,...args]),ellipse:(...args)=>calls.push(['ellipse',...args]),translate:(...args)=>calls.push(['translate',...args]),scale:(...args)=>calls.push(['scale',...args]),measureText:text=>({width:text.length*7})},{get:(o,k)=>k in o?o[k]:()=>{}});r.content.objects.kanto[0]={image:'trainer.png',width:16,height:32,frames:18,visibleTop:12};r.content.species.fr_7={name:'Squirtle',icon:'squirtle-icon.png',front:'squirtle-front.png',varieties:{shiny:{front:'squirtle-shiny.png'}}};r.content.species.fr_130={name:'Gyarados',icon:'gyarados-icon.png',front:'gyarados-front.png',varieties:{shadow:{front:'gyarados-shadow.png'}}};r.content.species.fr_152.icon='chikorita.png';r.active=true;r.width=800;r.height=800;r.dpr=1;r.rootFont=16;r.scale=2;return calls;}
test('surfing draws the replicated Water partner below a seated rider and suppresses its walking follower',()=>{
 const {r}=harness();r.map=mapData('johto_3_0');const calls=surfCanvas(r),surfer={...entity(1),surf:true,surfPokemon:{species:'fr_7',variety:'shiny',name:'Squirtle'}};r.entity(surfer,true);r.selfId=1;r.frame(100);const images=calls.filter(c=>c[0]==='image'),mount=images.findIndex(c=>c[1]==='assets/squirtle-shiny.png'),rider=images.findIndex(c=>c[1]==='assets/trainer.png');assert.ok(mount>=0);assert.ok(rider>mount,'Water partner is drawn before the rider');assert.equal(images.some(c=>c[1]==='assets/chikorita.png'),false);assert.ok(calls.filter(c=>c[0]==='ellipse').length>=3,'water base plus two bounded ripple rings');assert.equal(images[rider][5],15,'native rider crop keeps head/torso and removes standing feet');assert.equal(r.hits.some(hit=>hit.kind==='player'&&hit.id===1),true);
});
test('different surfing peers retain independent Water species and variety artwork',()=>{
 const {r}=harness();r.map=mapData('johto_3_0');const calls=surfCanvas(r);r.entity({...entity(1),surf:true,surfPokemon:{species:'fr_7',variety:'shiny'}},true);r.entity({...entity(2),surf:true,surfPokemon:{species:'fr_130',variety:'shadow'},direction:'right'},true);r.frame(100);const paths=calls.filter(c=>c[0]==='image').map(c=>c[1]);assert.ok(paths.includes('assets/squirtle-shiny.png'));assert.ok(paths.includes('assets/gyarados-shadow.png'));assert.equal(paths.includes('assets/charmander.png'),false);assert.ok(calls.some(c=>c[0]==='scale'&&c[1]===-1),'right-facing mount/rider share their direction');
});
test('confirmed dismount restores the regular follower and never keeps a stale Surf partner visible',()=>{
 const {r}=harness();r.map=mapData('johto_3_0');const calls=surfCanvas(r),surfer={...entity(1),surf:true,surfPokemon:{species:'fr_7',variety:'shiny'}};r.entity(surfer,true);r.frame(100);calls.length=0;r.entity({...surfer,surf:false,x:4},true);r.frame(100);const paths=calls.filter(c=>c[0]==='image').map(c=>c[1]);assert.ok(paths.includes('assets/chikorita.png'));assert.equal(paths.includes('assets/squirtle-shiny.png'),false);
});
test('Surf rendering rejects wrong-map entities and never substitutes the walking lead for missing mount data',()=>{
 const {r}=harness();r.map=mapData('johto_3_0');const calls=surfCanvas(r);assert.equal(r.drawSurfRider({...entity(1,'kanto_3_0'),surf:true,surfPokemon:{species:'fr_7'}},50,70,2,100),false);assert.equal(calls.length,0);r.drawSurfRider({...entity(1),surf:true},50,70,2,100);assert.equal(calls.some(c=>c[0]==='image'&&c[1]==='assets/chikorita.png'),false);assert.equal(calls.some(c=>c[0]==='image'&&c[1]==='assets/squirtle-front.png'),false);
});
test('reduced motion freezes Surf bob and ripples while preserving the actual partner and variety',()=>{
 const {r}=harness();r.map=mapData('johto_3_0');const calls=surfCanvas(r);r.motionPreference={matches:true};const surfer={...entity(1),surf:true,surfPokemon:{species:'fr_7',variety:'shiny'}};r.drawSurfRider(surfer,50,70,2,100);const first=structuredClone(calls);calls.length=0;r.drawSurfRider(surfer,50,70,2,99999);assert.deepEqual(calls,first);assert.ok(calls.some(c=>c[0]==='image'&&c[1]==='assets/squirtle-shiny.png'));
});
