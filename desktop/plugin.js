import le from"react";import{host as Oa,ROUTES_AREA as Ia,SIDEBAR_NAV_AREA as Ua,PALETTE_AREA as Xe}from"@hermes/plugin-sdk";import S from"react";var ue=t=>String(t).padStart(2,"0");function Wt(t){return`${t.getUTCFullYear()}-${ue(t.getUTCMonth()+1)}-${ue(t.getUTCDate())}`}function bt(t){let[e,a,n]=String(t).split("-").map(Number);return new Date(Date.UTC(e,a-1,n))}function K(t,e){let a=bt(t);return a.setUTCDate(a.getUTCDate()+e),Wt(a)}function _t(t,e){let a=bt(t),n=a.getUTCDate();a.setUTCDate(1),a.setUTCMonth(a.getUTCMonth()+e);let o=new Date(Date.UTC(a.getUTCFullYear(),a.getUTCMonth()+1,0)).getUTCDate();return a.setUTCDate(Math.min(n,o)),Wt(a)}var me=t=>(bt(t).getUTCDay()+6)%7;function Tt(t){return K(t,-me(t))}function zt(t){return t.slice(0,8)+"01"}function Je(t){let e=bt(zt(t));return Wt(new Date(Date.UTC(e.getUTCFullYear(),e.getUTCMonth()+1,0)))}function Qe(t,e){return Math.round((bt(e)-bt(t))/864e5)}function Bt(t,e){let a=[];for(let n=t;n<=e;n=K(n,1))a.push(n);return a}function Et(t){let e=Tt(zt(t)),a=K(Tt(Je(t)),6),n=Bt(e,a),o=[];for(let i=0;i<n.length;i+=7)o.push(n.slice(i,i+7));return o}var vt=(t,e)=>bt(t).toLocaleDateString(void 0,{timeZone:"UTC",...e}),dt=(t,e="short")=>vt(t,{weekday:e}),$t=(t,e="long")=>vt(t,{month:e}),yt=t=>bt(t).getUTCDate();function Ft(t){return vt(t,{weekday:"long",month:"long",day:"numeric"})}function gt(t,e){let a=!e||t.slice(0,4)===e.slice(0,4);return vt(t,{weekday:"short",month:"short",day:"numeric",...a?{}:{year:"numeric"}})}function W(t,e){if(!t)return"";let a=Qe(e,t);return a===0?"Today":a===1?"Tomorrow":a===-1?"Yesterday":a>1&&a<7?dt(t,"long"):gt(t,e)}function Xt(t,e){let a=(e-me(t)+7)%7||7;return K(t,a)}function ge(t,e,a){if(t==="month")return vt(e,{month:"long",...e.slice(0,4)!==a.slice(0,4)?{year:"numeric"}:{}});if(t==="week"){let n=Tt(e),o=K(n,6),i=n.slice(0,7)===o.slice(0,7),s=vt(n,{month:"short",day:"numeric"}),r=i?String(yt(o)):vt(o,{month:"short",day:"numeric"});return`${s} \u2013 ${r}`}return W(e,a)==="Today"?"Today":vt(e,{weekday:"long",month:"short",day:"numeric"})}var F=t=>t.scheduled||t.due||null;import ot from"react";var he=ot.createContext(null),Ot=()=>ot.useContext(he),Ze=380,fe=6;function Gt(t,e){let a=document.elementFromPoint(t,e),n=a&&a.closest("[data-at-drop]");return n?n.getAttribute("data-at-drop"):null}function Re(t){for(let e=t;e&&e!==document.body;e=e.parentElement){let a=getComputedStyle(e);if(/(auto|scroll)/.test(a.overflowY)&&e.scrollHeight>e.clientHeight)return e}return document.scrollingElement}function xe({onDrop:t,children:e}){let[a,n]=ot.useState(null),o=ot.useRef(null),i=ot.useRef(!1),s=ot.useRef(0),r=ot.useRef(null),p=v=>{let N=o.current&&o.current.over;o.current=o.current?{...o.current,...v}:null;let y=o.current;y&&r.current&&(r.current.style.transform=`translate(${y.x+12}px, ${y.y-20}px)`),y&&y.over!==N&&n(y)},l=(v,N)=>{cancelAnimationFrame(s.current);let y=document.elementFromPoint(v,N),b=y&&Re(y);if(!b)return;let f=b===document.scrollingElement?{top:0,bottom:window.innerHeight}:b.getBoundingClientRect(),D=56,z=N<f.top+D?-Math.ceil((f.top+D-N)/4):N>f.bottom-D?Math.ceil((N-(f.bottom-D))/4):0;if(!z)return;let E=()=>{o.current&&(b.scrollTop+=z,s.current=requestAnimationFrame(E))};s.current=requestAnimationFrame(E)},u=(v,N,y)=>{cancelAnimationFrame(s.current);let b=o.current;if(o.current=null,n(null),r.current&&(r.current.remove(),r.current=null),document.documentElement.classList.remove("at-dragging"),!b)return;i.current=!0,setTimeout(()=>{i.current=!1},50);let f=y?null:Gt(v,N);f&&f!==b.from&&t(b.task,f)},m=(v,N,y,b,f)=>{o.current={task:v,from:N,x:y,y:b,over:N,w:f},n(o.current);let D=document.createElement("div");if(D.className="at-drag-ghost at-vars",D.textContent=v.title,D.style.width=`${Math.min(f||260,300)}px`,D.style.transform=`translate(${y+12}px, ${b-20}px)`,document.body.appendChild(D),r.current=D,document.documentElement.classList.add("at-dragging"),navigator.vibrate)try{navigator.vibrate(8)}catch{}},x=ot.useCallback((v,N)=>({onPointerDown:y=>{if(y.pointerType!=="mouse"||y.button!==0||y.target.closest("button, input, textarea, a, [data-no-drag]"))return;let b=y.clientX,f=y.clientY,D=y.currentTarget.getBoundingClientRect().width,z=L=>{if(!o.current){if(Math.hypot(L.clientX-b,L.clientY-f)<fe)return;m(v,N,L.clientX,L.clientY,D)}p({x:L.clientX,y:L.clientY,over:Gt(L.clientX,L.clientY)}),l(L.clientX,L.clientY)},E=L=>{window.removeEventListener("pointermove",z),window.removeEventListener("pointerup",E),window.removeEventListener("keydown",O),o.current&&u(L.clientX,L.clientY,!1)},O=L=>{L.key==="Escape"&&(E({clientX:-1,clientY:-1}),u(-1,-1,!0))};window.addEventListener("pointermove",z),window.addEventListener("pointerup",E),window.addEventListener("keydown",O)},onTouchStart:y=>{if(y.target.closest("button, input, textarea, a, [data-no-drag]"))return;let b=y.touches[0],f=b.clientX,D=b.clientY,z=y.currentTarget.getBoundingClientRect().width,E={x:f,y:D},O=setTimeout(()=>{O=null,m(v,N,E.x,E.y,z)},Ze),L=R=>{let G=R.touches[0];if(E={x:G.clientX,y:G.clientY},!o.current){O&&Math.hypot(G.clientX-f,G.clientY-D)>fe&&(clearTimeout(O),O=null,ut());return}R.preventDefault(),p({x:G.clientX,y:G.clientY,over:Gt(G.clientX,G.clientY)}),l(G.clientX,G.clientY)},A=R=>{O&&clearTimeout(O),ut(),o.current&&(R.preventDefault(),u(E.x,E.y,R.type==="touchcancel"))},ut=()=>{document.removeEventListener("touchmove",L),document.removeEventListener("touchend",A),document.removeEventListener("touchcancel",A)};document.addEventListener("touchmove",L,{passive:!1}),document.addEventListener("touchend",A),document.addEventListener("touchcancel",A)},onClickCapture:y=>{i.current&&(y.stopPropagation(),y.preventDefault())},onContextMenu:y=>{o.current&&y.preventDefault()}}),[]),w=ot.useMemo(()=>({drag:a,bind:x}),[a,x]);return ot.useEffect(()=>()=>{r.current&&r.current.remove()},[]),ot.createElement(he.Provider,{value:w},e)}var ft=class extends Error{constructor(e,a,n=0){super(a||e),this.code=e||"error",this.status=n}};function ta(t){let e=t&&(t.body||t.responseText||t.message||"");if(e&&typeof e=="object")return e;let a=String(e),n=a.indexOf("{");if(n>=0)try{return JSON.parse(a.slice(n))}catch{}return null}function ea(t){if(t instanceof ft)return t;let e=ta(t),a=e&&(e.error||e.detail),n=t&&t.status||0;return a&&typeof a=="object"?new ft(a.code,a.message,n):typeof a=="string"?new ft(n===404?"not_found":"error",a,n):n===404?new ft("not_found","Not found",404):n===0||/network|failed to fetch|unreachable/i.test(String(t&&t.message))?new ft("offline","Hermes is not reachable right now.",n):new ft("error",t&&t.message||"Something went wrong",n)}var Kt=t=>{let e=Object.entries(t).filter(([,a])=>a!=null&&a!==""&&a!==!1).map(([a,n])=>`${encodeURIComponent(a)}=${encodeURIComponent(n===!0?"1":n)}`);return e.length?`?${e.join("&")}`:""},nt=encodeURIComponent;function ve(t){async function e(a,n,o){let i;try{i=await t(a,n,o)}catch(s){throw ea(s)}if(i&&i.ok===!1){let s=i.error||{};throw new ft(s.code||i.needs||"error",s.message||i.message,200)}return i}return{meta:()=>e("GET","/meta"),tasks:(a,n,{area:o,includeDone:i=!0}={})=>e("GET","/tasks"+Kt({from:a,to:n,area:o,include_done:i})),overdue:({area:a}={})=>e("GET","/overdue"+Kt({area:a})),task:a=>e("GET",`/tasks/${nt(a)}`),patch:(a,n)=>e("PATCH",`/tasks/${nt(a)}`,n),complete:a=>e("POST",`/tasks/${nt(a)}/complete`,{}),reopen:a=>e("POST",`/tasks/${nt(a)}/reopen`,{}),putBody:(a,n,o)=>e("PUT",`/tasks/${nt(a)}/body`,{body:n,expected_revision:o}),create:a=>e("POST","/tasks",a),runs:(a={})=>e("GET","/runs"+Kt(a)),run:a=>e("GET",`/runs/${nt(a)}`),approve:(a,n)=>e("POST",`/proposals/${nt(a)}/approve`,n),dismiss:a=>e("POST",`/proposals/${nt(a)}/dismiss`,{}),resume:(a,n)=>e("POST",`/runs/${nt(a)}/units/${nt(n)}/resume`,{}),settings:()=>e("GET","/settings"),patchStream:(a,n)=>e("PATCH",`/settings/streams/${nt(a)}`,n),runStream:a=>e("POST",`/settings/streams/${nt(a)}/run`,{}),patchTaskSettings:a=>e("PATCH","/settings/tasks",a)}}function X(t){switch(t&&t.code){case"stale_revision":case"retry":return"This task changed somewhere else. Reload it to see the latest version.";case"offline":return"Hermes is not reachable right now. Your change was not saved.";case"needs_due":case"due":return"Pick a date first.";case"needs_area":case"area":return"Pick an area first.";case"already_resolved":return"This proposal was already handled.";case"expired":return"This proposal expired.";case"not_production":return"This was a test run, so it cannot change tasks.";case"not_found":return"It is no longer there. It may have been moved or deleted.";default:return t&&t.message||"Something went wrong."}}import ht from"react";function be(t){let e={byId:{},today:null,loading:0,error:null,version:0},a=new Set,n=new Map,o=new Map,i=()=>{e={...e,version:e.version+1},a.forEach(u=>u())},s=u=>{e={...e,...u},i()};function r(u,m){let x={...e.byId},w=new Set;for(let v of u){if(w.add(v.task_id),n.has(v.task_id))continue;let N=x[v.task_id]||{},y=v.body!==void 0?v.body:N.revision===v.revision?N.body:void 0;x[v.task_id]={...N,...v,body:y}}if(m)for(let[v,N]of Object.entries(x))!w.has(v)&&!n.has(v)&&m(N)&&delete x[v];e={...e,byId:x}}async function p(u){s({loading:e.loading+1});try{return await u}finally{s({loading:Math.max(0,e.loading-1)})}}let l={getState:()=>e,subscribe:u=>(a.add(u),()=>a.delete(u)),setToday:u=>{u!==e.today&&s({today:u})},async loadRange(u,m){o.set(`${u}:${m}`,{from:u,to:m});let x=await p(t.tasks(u,m));return x.today&&(e={...e,today:x.today}),r(x.tasks||[],w=>{let v=F(w);return v&&v>=u&&v<=m}),s({error:null}),x},async loadOverdue(){let u=await p(t.overdue()),m=u.today||e.today;return u.today&&(e={...e,today:u.today}),r(u.tasks||[],x=>{let w=F(x);return x.status!=="done"&&x.status!=="cancelled"&&w&&w<m}),s({error:null}),u},async refresh(){let u=[...o.values()].slice(-4);try{await Promise.all([...u.map(m=>l.loadRange(m.from,m.to)),l.loadOverdue()])}catch(m){s({error:m})}},async loadTask(u){let m=await t.task(u);return r([m.task]),i(),m.task},put(u){r([u]),i()},async mutate(u,m,x){let w=e.byId[u];n.set(u,(n.get(u)||0)+1),w&&m&&(e={...e,byId:{...e.byId,[u]:{...w,...m}}},i());try{let v=await x(),N=(n.get(u)||1)-1;return N?n.set(u,N):n.delete(u),v&&v.task&&(r([v.task]),i()),v}catch(v){let N=(n.get(u)||1)-1;throw N?n.set(u,N):n.delete(u),w&&(e={...e,byId:{...e.byId,[u]:w}},i()),v}}};return l}function kt(t,e){let a=ht.useCallback(()=>e(t.getState()),[t,e]),[n,o]=ht.useState(a);return ht.useEffect(()=>(o(a()),t.subscribe(()=>o(a()))),[t,a]),n}var Jt=ht.createContext(null),U=()=>ht.useContext(Jt);function ye(t,e){let a=`alchemy-task.${t}`,[n,o]=ht.useState(()=>{try{let s=window.localStorage.getItem(a);return s===null?e:JSON.parse(s)}catch{return e}}),i=ht.useCallback(s=>{o(r=>{let p=typeof s=="function"?s(r):s;try{window.localStorage.setItem(a,JSON.stringify(p))}catch{}return p})},[a]);return[n,i]}function ke(t){let[e,a]=ht.useState(()=>typeof window<"u"?window.innerWidth:1200);return ht.useLayoutEffect(()=>{let n=t.current;if(!n)return;a(n.getBoundingClientRect().width);let o=new ResizeObserver(i=>a(i[0].contentRect.width));return o.observe(n),()=>o.disconnect()},[t]),e}import c from"react";import k from"react";var Qt={check:"M5 12.5l4.2 4.2L19 7",chevL:"M15 18l-6-6 6-6",chevR:"M9 6l6 6-6 6",chevD:"M6 9l6 6 6-6",gear:"M12 15.2a3.2 3.2 0 100-6.4 3.2 3.2 0 000 6.4z M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",x:"M6 6l12 12M18 6L6 18",plus:"M12 5v14M5 12h14",more:"M5 12h.01M12 12h.01M19 12h.01",cal:"M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z",spark:"M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z",link:"M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5",alert:"M12 9v4M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",refresh:"M20 11a8 8 0 10-2.3 5.7M20 5v6h-6",inbox:"M4 13l2.5-7h11L20 13M4 13v5a1 1 0 001 1h14a1 1 0 001-1v-5M4 13h4l1.5 2.5h5L16 13h4",edit:"M4 20h4L19 9l-4-4L4 16v4z M13.5 6.5l4 4",grip:"M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",arrowR:"M5 12h14M13 6l6 6-6 6",undo:"M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 010 11H11",dot:"M12 12h.01",list:"M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",clock:"M12 7v5l3 2 M12 21a9 9 0 100-18 9 9 0 000 18z",play:"M7 5l12 7-12 7z"};function $({name:t,size:e=16,className:a="",strokeWidth:n=1.8}){return k.createElement("svg",{className:"at-icon "+a,width:e,height:e,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:n,strokeLinecap:"round",strokeLinejoin:"round","aria-hidden":"true"},k.createElement("path",{d:Qt[t]||Qt.dot}))}var T=(...t)=>t.filter(Boolean).join(" ");function V({variant:t="default",size:e,icon:a,children:n,className:o,...i}){return k.createElement("button",{type:"button",className:T("at-btn",`at-btn-${t}`,e&&`at-btn-${e}`,o),...i},a?k.createElement($,{name:a,size:e==="sm"?14:16}):null,n?k.createElement("span",null,n):null)}function J({icon:t,label:e,className:a,size:n=16,...o}){return k.createElement("button",{type:"button",className:T("at-iconbtn",a),"aria-label":e,title:e,...o},k.createElement($,{name:t,size:n}))}function It({checked:t,onChange:e,label:a,size:n="md",tone:o}){return k.createElement("button",{type:"button",role:"checkbox","aria-checked":!!t,"aria-label":a,className:T("at-check",`at-check-${n}`,t&&"is-on",o&&`at-tone-${o}`),"data-no-drag":"",onClick:i=>{i.stopPropagation(),e(!t)}},k.createElement("svg",{viewBox:"0 0 24 24","aria-hidden":"true"},k.createElement("path",{d:Qt.check})))}function Ut({value:t,options:e,onChange:a,label:n}){return k.createElement("div",{className:"at-seg",role:"tablist","aria-label":n},e.map(o=>k.createElement("button",{key:o.value,type:"button",role:"tab","aria-selected":t===o.value,className:T("at-seg-item",t===o.value&&"is-on"),onClick:()=>a(o.value)},o.label)))}function Z({size:t=14}){return k.createElement("span",{className:"at-spinner",style:{width:t,height:t},"aria-label":"Loading"})}function pt({title:t,count:e,defaultOpen:a=!1,tone:n,children:o,right:i,className:s}){let[r,p]=k.useState(a);return k.createElement("section",{className:T("at-disc",r&&"is-open",n&&`at-tone-${n}`,s)},k.createElement("button",{type:"button",className:"at-disc-head","aria-expanded":r,onClick:()=>p(!r)},k.createElement($,{name:"chevR",size:14,className:"at-disc-chev"}),k.createElement("span",{className:"at-disc-title"},t),e!==void 0?k.createElement("span",{className:"at-count"},e):null,k.createElement("span",{className:"at-flex"}),i),r?k.createElement("div",{className:"at-disc-body"},o):null)}function rt({area:t}){return k.createElement("span",{className:"at-areadot",style:{"--at-area":aa(t)},title:t})}var we=[212,152,28,280,340,188,48,252];function aa(t){if(!t)return"var(--at-faint)";let e=0;for(let a of String(t))e=e*31+a.charCodeAt(0)>>>0;return`hsl(${we[e%we.length]} 62% 56%)`}var Ne=k.createContext(null),st=()=>k.useContext(Ne);function De({rootRef:t,children:e}){let[a,n]=k.useState(null),o=k.useCallback(()=>n(r=>(r&&r.onClose&&r.onClose(),null)),[]),i=k.useCallback((r,p,l={})=>n({anchor:r,render:p,...l}),[]),s=k.useMemo(()=>({open:i,close:o}),[i,o]);return k.createElement(Ne.Provider,{value:s},e,a?k.createElement(na,{rootRef:t,...a,close:o}):null)}function na({rootRef:t,anchor:e,render:a,close:n,align:o="start",width:i}){let s=k.useRef(null),[r,p]=k.useState(null);return k.useLayoutEffect(()=>{let l=t.current,u=s.current;if(!l||!u||!e)return;let m=()=>{let w=l.getBoundingClientRect(),v=e.getBoundingClientRect?e.getBoundingClientRect():e,N=u.offsetWidth,y=u.offsetHeight,b=(o==="end"?v.right-N:v.left)-w.left;b=Math.max(8,Math.min(b,w.width-N-8));let f=v.bottom-w.top+6;f+y>w.height-8&&v.top-w.top-y-6>8&&(f=v.top-w.top-y-6),f=Math.max(8,Math.min(f,w.height-y-8)),p({left:b,top:f})};m();let x=new ResizeObserver(m);return x.observe(u),()=>x.disconnect()},[e,t,o]),k.useEffect(()=>{let l=m=>{s.current&&!s.current.contains(m.target)&&!(e&&e.contains&&e.contains(m.target))&&n()},u=m=>{m.key==="Escape"&&(m.stopPropagation(),n())};return document.addEventListener("pointerdown",l,!0),document.addEventListener("keydown",u,!0),()=>{document.removeEventListener("pointerdown",l,!0),document.removeEventListener("keydown",u,!0)}},[e,n]),k.createElement("div",{ref:s,className:"at-pop",role:"dialog",style:{left:r?r.left:-9999,top:r?r.top:-9999,width:i}},a(n))}function et({items:t,close:e}){return k.createElement("div",{className:"at-menu",role:"menu"},t.filter(Boolean).map((a,n)=>a==="-"?k.createElement("div",{key:n,className:"at-menu-sep"}):k.createElement("button",{key:n,type:"button",role:"menuitem",className:T("at-menu-item",a.danger&&"is-danger"),onClick:()=>{e(),a.run()}},a.icon?k.createElement($,{name:a.icon,size:15}):k.createElement("span",{className:"at-menu-pad"}),k.createElement("span",{className:"at-flex"},a.label),a.hint?k.createElement("span",{className:"at-menu-hint"},a.hint):null)))}function Ht(t){return[{label:"Today",date:t,hint:dt(t)},{label:"Tomorrow",date:K(t,1),hint:dt(K(t,1))},{label:"Next Monday",date:Xt(t,0),hint:gt(Xt(t,0),t).replace(/^\w+,\s*/,"")},{label:"In a week",date:K(t,7),hint:gt(K(t,7),t).replace(/^\w+,\s*/,"")}]}function Dt({value:t,today:e,onPick:a,onClear:n,close:o,extra:i}){let[s,r]=k.useState(zt(t||e)),p=Et(s),l=u=>{a(u),o&&o()};return k.createElement("div",{className:"at-dp"},k.createElement("div",{className:"at-dp-quick"},Ht(e).map(u=>k.createElement("button",{key:u.label,type:"button",className:T("at-dp-q",t===u.date&&"is-on"),onClick:()=>l(u.date)},k.createElement("span",null,u.label),k.createElement("span",{className:"at-muted"},u.hint)))),k.createElement("div",{className:"at-dp-head"},k.createElement("span",{className:"at-dp-title"},$t(s)," ",s.slice(0,4)!==e.slice(0,4)?s.slice(0,4):""),k.createElement(J,{icon:"chevL",label:"Previous month",onClick:()=>r(_t(s,-1))}),k.createElement(J,{icon:"chevR",label:"Next month",onClick:()=>r(_t(s,1))})),k.createElement("div",{className:"at-dp-grid",role:"grid"},["M","T","W","T","F","S","S"].map((u,m)=>k.createElement("span",{key:m,className:"at-dp-dow"},u)),p.flat().map(u=>k.createElement("button",{key:u,type:"button",onClick:()=>l(u),className:T("at-dp-day",u.slice(0,7)!==s.slice(0,7)&&"is-out",u===e&&"is-today",u===t&&"is-on")},yt(u)))),n||i?k.createElement("div",{className:"at-dp-foot"},i,k.createElement("span",{className:"at-flex"}),n?k.createElement(V,{size:"sm",variant:"ghost",onClick:()=>{n(),o&&o()}},"Clear"):null):null)}var Se=k.createContext(null),it=()=>k.useContext(Se);function Ce({children:t}){let[e,a]=k.useState([]),n=k.useRef(0),o=k.useCallback(s=>a(r=>r.filter(p=>p.id!==s)),[]),i=k.useCallback((s,r={})=>{let p=++n.current;return a(l=>[...l.slice(-2),{id:p,message:s,...r}]),setTimeout(()=>o(p),r.duration||(r.undo?6500:r.tone==="error"?7e3:3500)),p},[o]);return k.createElement(Se.Provider,{value:i},t,k.createElement("div",{className:"at-toasts","aria-live":"polite"},e.map(s=>k.createElement("div",{key:s.id,className:T("at-toast",s.tone&&`at-tone-${s.tone}`)},s.tone==="error"?k.createElement($,{name:"alert",size:15}):null,k.createElement("span",{className:"at-flex"},s.message),s.undo?k.createElement("button",{type:"button",className:"at-toast-act",onClick:()=>{o(s.id),s.undo()}},"Undo"):null,s.action?k.createElement("button",{type:"button",className:"at-toast-act",onClick:()=>{o(s.id),s.action.run()}},s.action.label):null))))}var Te={urgent:0,high:1,normal:2,low:3},at=t=>t.status==="done"||t.status==="cancelled",ze=(t,e)=>(Te[t.priority]??2)-(Te[e.priority]??2)||t.title.localeCompare(e.title);function Pt(){let{store:t,prefs:e}=U(),a=kt(t,oa),n=kt(t,ra);return c.useMemo(()=>{let o={},i=[];for(let s of Object.values(a)){if(e.area&&s.area!==e.area)continue;let r=F(s);r&&(!at(s)&&n&&r<n&&i.push(s),(o[r]||(o[r]=[])).push(s))}for(let s of Object.keys(o))o[s].sort((r,p)=>Number(at(r))-Number(at(p))||ze(r,p));return i.sort((s,r)=>F(r).localeCompare(F(s))||ze(s,r)),{days:o,overdue:i,today:n}},[a,n,e.area])}var oa=t=>t.byId,ra=t=>t.today;function Zt({task:t,from:e,compact:a,showDate:n,selected:o}){let{actions:i,today:s}=U(),{bind:r}=Ot(),p=st(),l=at(t),u=!l&&F(t)&&F(t)<s,m=t.due&&t.scheduled&&t.due!==t.scheduled,x=t.research==="pending"||t.research==="running",w=v=>{v.stopPropagation(),p.open(v.currentTarget,N=>c.createElement(sa,{task:t,close:N}),{width:236,align:"end"})};return c.createElement("div",{className:T("at-row",a&&"is-compact",l&&"is-done",o&&"is-selected"),...r(t,e),onClick:()=>i.open(t.task_id),onKeyDown:v=>{v.key==="Enter"&&i.open(t.task_id),v.key===" "&&v.target===v.currentTarget&&(v.preventDefault(),i.toggle(t))},tabIndex:0,role:"button","aria-label":t.title,"data-task":t.task_id},c.createElement(It,{checked:l,onChange:()=>i.toggle(t),label:l?"Mark not done":"Mark done",size:a?"sm":"md",tone:t.priority==="urgent"||t.priority==="high"?"high":void 0}),c.createElement("div",{className:"at-row-main"},c.createElement("div",{className:"at-row-title",title:a?t.title:void 0},t.title),a?null:c.createElement("div",{className:"at-row-meta"},t.area?c.createElement("span",{className:"at-meta-area"},c.createElement(rt,{area:t.area}),t.area):null,n||u?c.createElement("span",{className:T("at-meta-date",u&&"is-late")},W(F(t),s)):null,m?c.createElement("span",{className:"at-meta-due"},"due ",W(t.due,s)):null,t.priority==="urgent"||t.priority==="high"?c.createElement("span",{className:"at-meta-prio"},t.priority):null,t.status==="waiting"?c.createElement("span",{className:"at-meta-status"},"waiting"):null,t.status==="in-progress"?c.createElement("span",{className:"at-meta-status is-active"},"in progress"):null,x?c.createElement("span",{className:"at-meta-research"},c.createElement($,{name:"spark",size:12}),"researching"):null)),a?null:c.createElement(J,{icon:"more",label:"Task actions",className:"at-row-more",onClick:w,"data-no-drag":""}))}function sa({task:t,close:e}){let{actions:a,today:n}=U(),[o,i]=c.useState(!1);if(o)return c.createElement(Dt,{value:F(t),today:n,onPick:r=>a.move(t,r),close:e});let s=Ht(n).slice(0,3).map(r=>({label:r.label,hint:r.hint,icon:"cal",run:()=>a.move(t,r.date)})).filter((r,p)=>Ht(n)[p].date!==F(t));return c.createElement("div",{className:"at-menu",role:"menu"},c.createElement("div",{className:"at-menu-label"},"Move to"),c.createElement(et,{items:s,close:e}),c.createElement("button",{type:"button",className:"at-menu-item",onClick:()=>i(!0)},c.createElement($,{name:"cal",size:15}),c.createElement("span",{className:"at-flex"},"Pick a date\u2026")),c.createElement("div",{className:"at-menu-sep"}),c.createElement(et,{close:e,items:[{label:at(t)?"Mark not done":"Mark done",icon:"check",run:()=>a.toggle(t)},{label:"Open",icon:"arrowR",run:()=>a.open(t.task_id)}]}))}function qt({date:t,tasks:e=[],overdue:a=[],compact:n,empty:o="Nothing planned",showAdd:i}){let{today:s,prefs:r,selectedId:p}=U(),{drag:l}=Ot(),u=t===s,m=r.hideDone?e.filter(w=>!at(w)):e,x=e.length-m.length;return c.createElement("div",{className:T("at-daylist",l&&l.over===t&&"is-over"),"data-at-drop":t},u&&a.length?c.createElement(ia,{tasks:a}):null,m.map(w=>c.createElement(Zt,{key:w.task_id,task:w,from:t,compact:n,selected:p===w.task_id})),!m.length&&!(u&&a.length)?c.createElement("div",{className:"at-empty-day"},x?`${x} done`:o):null,i?c.createElement(Me,{date:t}):null,l&&l.over===t&&l.from!==t?c.createElement("div",{className:"at-drop-hint"},"Move to ",W(t,s)):null)}function ia({tasks:t,defaultOpen:e=!1}){let{actions:a,today:n,selectedId:o}=U();return c.createElement(pt,{className:"at-overdue",tone:"late",title:"Overdue",count:t.length,defaultOpen:e,right:c.createElement("span",{className:"at-link",role:"button",tabIndex:0,"data-no-drag":"",onClick:i=>{i.stopPropagation(),a.moveMany(t,n)}},"Move all to today")},t.map(i=>c.createElement(Zt,{key:i.task_id,task:i,from:F(i),showDate:!0,selected:o===i.task_id})))}function Me({date:t,autoFocus:e,onDone:a}){let{actions:n,meta:o,prefs:i}=U(),[s,r]=c.useState(""),[p,l]=c.useState(!1),[u,m]=c.useState(!!e),x=c.useRef(null);if(c.useEffect(()=>{u&&x.current&&x.current.focus()},[u]),!u)return c.createElement("button",{type:"button",className:"at-add",onClick:()=>m(!0),"data-no-drag":""},c.createElement($,{name:"plus",size:14})," Add a task");let w=async()=>{let v=s.trim();if(!v){m(!1),a&&a();return}l(!0);let N=await n.create({title:v,date:t,area:i.area||o.default_area||void 0});l(!1),N&&(r(""),x.current&&x.current.focus())};return c.createElement("form",{className:"at-add-form","data-no-drag":"",onSubmit:v=>{v.preventDefault(),w()}},c.createElement("span",{className:"at-check at-check-md is-ghost","aria-hidden":"true"}),c.createElement("input",{ref:x,className:"at-add-input",value:s,placeholder:"New task",disabled:p,onChange:v=>r(v.target.value),onKeyDown:v=>{v.key==="Escape"&&(r(""),m(!1),a&&a())},onBlur:()=>{s.trim()||(m(!1),a&&a())}}),p?c.createElement(Z,null):null)}function la({anchor:t,narrow:e}){let{today:a,selectedId:n}=U(),{days:o,overdue:i}=Pt(),s=st(),{drag:r}=Ot(),p=Et(t),l=t.slice(0,7),[u,m]=c.useState(null);if(e){let b=u&&u.slice(0,7)===l?u:a.slice(0,7)===l?a:zt(t);return c.createElement("div",{className:"at-scroll at-mmonth"},c.createElement("div",{className:"at-mmonth-dows"},["M","T","W","T","F","S","S"].map((f,D)=>c.createElement("span",{key:D},f))),c.createElement("div",{className:"at-mmonth-grid"},p.flat().map(f=>{let D=o[f]||[],z=D.filter(E=>!at(E)).length;return c.createElement("button",{key:f,type:"button","data-at-drop":f,onClick:()=>m(f),className:T("at-mcell",f.slice(0,7)!==l&&"is-out",f===a&&"is-today",f===b&&"is-on",r&&r.over===f&&"is-over")},c.createElement("span",{className:"at-mcell-num"},yt(f)),c.createElement("span",{className:"at-mcell-dots"},D.slice(0,3).map(E=>c.createElement("i",{key:E.task_id,className:at(E)?"is-done":""})),f===a&&i.length?c.createElement("i",{className:"is-late"}):null),z>3?c.createElement("span",{className:"at-mcell-more"},"+",z-3):null)})),c.createElement(Rt,{date:b,tasks:o[b]||[],overdue:b===a?i:[]}))}let x=(b,f)=>s.open(f,D=>c.createElement(da,{date:b,close:D}),{width:360}),w=c.useRef(null),[v,N]=c.useState(110);c.useLayoutEffect(()=>{let b=w.current;if(!b)return;let f=new ResizeObserver(()=>N(b.clientHeight/p.length));return f.observe(b),()=>f.disconnect()},[p.length]);let y=v-34;return c.createElement("div",{className:"at-month"},c.createElement("div",{className:"at-month-dows"},p[0].map(b=>c.createElement("div",{key:b},dt(b)))),c.createElement("div",{ref:w,className:"at-month-grid",style:{gridTemplateRows:`repeat(${p.length}, minmax(0, 1fr))`}},p.flat().map(b=>{let f=o[b]||[],D=f.length*37<=y,z=D?f.length:Math.max(1,Math.floor(y/23)),E=f.length>z?f.slice(0,Math.max(1,z-1)):f,O=f.length-E.length,L=b===a;return c.createElement("div",{key:b,"data-at-drop":b,className:T("at-cell",b.slice(0,7)!==l&&"is-out",L&&"is-today",b<a&&"is-past",r&&r.over===b&&"is-over"),onClick:A=>{A.target.closest(".at-row")||x(b,A.currentTarget)}},c.createElement("div",{className:"at-cell-head"},c.createElement("span",{className:"at-cell-num"},yt(b)===1?`${$t(b,"short")} 1`:yt(b)),L&&i.length?c.createElement("button",{type:"button",className:"at-chip at-tone-late","data-no-drag":"",onClick:A=>{A.stopPropagation(),x(b,A.currentTarget.closest(".at-cell"))}},i.length," overdue"):null),c.createElement("div",{className:T("at-cell-list",!D&&"is-tight")},E.map(A=>c.createElement(Zt,{key:A.task_id,task:A,from:b,compact:!0,selected:n===A.task_id})),O>0?c.createElement("button",{type:"button",className:"at-cell-more","data-no-drag":"",onClick:A=>{A.stopPropagation(),x(b,A.currentTarget.closest(".at-cell"))}},"+",O," more"):null))})))}function da({date:t,close:e}){let{today:a}=U(),{days:n,overdue:o}=Pt();return c.createElement("div",{className:"at-daypop"},c.createElement("div",{className:"at-daypop-head"},c.createElement("div",null,c.createElement("div",{className:"at-daypop-title"},W(t,a)==="Today"?"Today":dt(t,"long")),c.createElement("div",{className:"at-muted"},Ft(t))),c.createElement(J,{icon:"x",label:"Close",onClick:e})),c.createElement("div",{className:"at-daypop-body"},c.createElement(qt,{date:t,tasks:n[t]||[],overdue:t===a?o:[],showAdd:!0})))}function pa({anchor:t,narrow:e}){let{today:a}=U(),{days:n,overdue:o}=Pt(),i=Tt(t),s=Bt(i,K(i,6));return e?c.createElement("div",{className:"at-scroll at-days"},s.map(r=>c.createElement(Rt,{key:r,date:r,tasks:n[r]||[],overdue:r===a?o:[]}))):c.createElement("div",{className:"at-week"},s.map(r=>c.createElement("div",{key:r,className:T("at-week-col",r===a&&"is-today",r<a&&"is-past")},c.createElement("div",{className:"at-week-head"},c.createElement("span",{className:"at-week-dow"},dt(r)),c.createElement("span",{className:"at-week-num"},yt(r))),c.createElement("div",{className:"at-week-body at-scroll"},c.createElement(qt,{date:r,tasks:n[r]||[],overdue:r===a?o:[],showAdd:!0})))))}function ca({anchor:t}){let{today:e}=U(),{days:a,overdue:n}=Pt();return c.createElement("div",{className:"at-scroll at-dayview"},c.createElement("div",{className:"at-dayview-inner"},c.createElement("header",{className:"at-dayview-head"},c.createElement("h2",null,W(t,e)==="Today"?"Today":dt(t,"long")),c.createElement("div",{className:"at-muted"},Ft(t))),c.createElement(qt,{date:t,tasks:a[t]||[],overdue:t===e?n:[],showAdd:!0})))}function Rt({date:t,tasks:e,overdue:a}){let{today:n}=U(),o=W(t,n),i=o==="Today"||o==="Tomorrow"||o==="Yesterday",s=!e.length&&!a.length;return c.createElement("section",{className:T("at-daysec",t===n&&"is-today",s&&"is-empty")},c.createElement("header",{className:"at-daysec-head"},c.createElement("span",{className:"at-daysec-title"},i?o:dt(t,"long")),c.createElement("span",{className:"at-muted"},gt(t,n).replace(/^\w+,\s*/,""))),c.createElement(qt,{date:t,tasks:e,overdue:a,showAdd:!s||t===n}))}function ua({anchor:t,onReachEnd:e,length:a}){let{today:n}=U(),{days:o,overdue:i}=Pt(),s=Bt(t,K(t,a-1)),r=c.useRef(null);return c.useEffect(()=>{let p=r.current;if(!p)return;let l=new IntersectionObserver(u=>{u[0].isIntersecting&&e()},{rootMargin:"400px"});return l.observe(p),()=>l.disconnect()},[e]),c.createElement("div",{className:"at-scroll at-days"},s.map(p=>c.createElement(Rt,{key:p,date:p,tasks:o[p]||[],overdue:p===n?i:[]})),c.createElement("div",{ref:r,className:"at-sentinel"}))}function _e({narrow:t}){let{store:e,prefs:a,setPrefs:n,meta:o,today:i}=U(),s=st(),r=a.view||(t?"day":"month"),[p,l]=c.useState(i),[u,m]=c.useState(21);c.useEffect(()=>{!p&&i&&l(i)},[i,p]);let x=p||i,w=c.useMemo(()=>{if(!x)return null;if(r==="month"){let f=Et(x);return[f[0][0],f[f.length-1][6]]}if(r==="week"){let f=Tt(x);return[f,K(f,6)]}return t?[x,K(x,u-1)]:[x,x]},[x,r,t,u]);c.useEffect(()=>{w&&(e.loadRange(w[0],w[1]).catch(()=>{}),e.loadOverdue().catch(()=>{}))},[w&&w[0],w&&w[1]]);let v=f=>{l(r==="month"?_t(x,f):r==="week"?K(x,7*f):K(x,f))};if(c.useEffect(()=>{let f=D=>{if(D.target.closest&&D.target.closest("input, textarea, [contenteditable]")||D.metaKey||D.ctrlKey||D.altKey)return;let z=D.key.toLowerCase();if(z==="t")l(i);else if(z==="d")n({view:"day"});else if(z==="w")n({view:"week"});else if(z==="m")n({view:"month"});else if(D.key==="ArrowLeft")v(-1);else if(D.key==="ArrowRight")v(1);else return;D.preventDefault()};return window.addEventListener("keydown",f),()=>window.removeEventListener("keydown",f)}),!x)return c.createElement("div",{className:"at-loading"},c.createElement(Z,{size:18}));let N=o.areas||[],y=f=>s.open(f.currentTarget,D=>c.createElement(et,{close:D,items:[{label:"All areas",icon:a.area?void 0:"check",run:()=>n({area:""})},"-",...N.map(z=>({label:z,icon:a.area===z?"check":void 0,run:()=>n({area:z})})),"-",{label:a.hideDone?"Show completed":"Hide completed",run:()=>n({hideDone:!a.hideDone})}]}),{width:200,align:"end"}),b=f=>s.open(f.currentTarget,D=>c.createElement("div",{className:"at-pop-add"},c.createElement(Me,{date:r==="day"?x:i,autoFocus:!0,onDone:D})),{width:320,align:"end"});return c.createElement("div",{className:T("at-tasks",`is-${r}`)},c.createElement("div",{className:"at-toolbar"},c.createElement("div",{className:"at-toolbar-nav"},c.createElement(V,{variant:"ghost",size:"sm",onClick:()=>l(i),disabled:x===i&&r!=="month"},"Today"),c.createElement(J,{icon:"chevL",label:"Previous",onClick:()=>v(-1)}),c.createElement(J,{icon:"chevR",label:"Next",onClick:()=>v(1)}),c.createElement("h1",{className:"at-period"},r==="day"&&t?$t(x):ge(r,x,i))),c.createElement("div",{className:"at-toolbar-right"},c.createElement(Ut,{label:"View",value:r,onChange:f=>n({view:f}),options:[{value:"day",label:"Day"},{value:"week",label:"Week"},{value:"month",label:"Month"}]}),c.createElement("button",{type:"button",className:T("at-filter",a.area&&"is-on"),onClick:y},a.area?c.createElement(rt,{area:a.area}):null,c.createElement("span",null,a.area||"All areas"),c.createElement($,{name:"chevD",size:14})),t?null:c.createElement(V,{variant:"primary",size:"sm",icon:"plus",onClick:b},"Add"))),c.createElement("div",{className:"at-viewport"},r==="month"?c.createElement(la,{anchor:x,narrow:t}):null,r==="week"?c.createElement(pa,{anchor:x,narrow:t}):null,r==="day"&&t?c.createElement(ua,{anchor:x,length:u,onReachEnd:()=>m(f=>Math.min(f+14,120))}):null,r==="day"&&!t?c.createElement(ca,{anchor:x}):null),t?c.createElement("button",{type:"button",className:"at-fab","aria-label":"Add a task",onClick:b},c.createElement($,{name:"plus",size:22})):null)}import g from"react";import ma from"react";var B=ma.createElement,ga=/^(https?:|mailto:|obsidian:|#)/i;function ct(t,e="i"){let a=[],n=String(t),o=0,i=/(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(\*[^*\s][^*]*\*|_[^_\s][^_]*_)|(\[\[[^\]]+\]\])|(\[[^\]]+\]\([^)\s]+\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/;for(;n;){let s=n.match(i);if(!s){a.push(n);break}s.index&&a.push(n.slice(0,s.index));let r=s[0],p=`${e}-${o++}`;if(s[1])a.push(B("code",{key:p},r.slice(1,-1)));else if(s[2])a.push(B("strong",{key:p},ct(r.slice(2,-2),p)));else if(s[3])a.push(B("em",{key:p},ct(r.slice(1,-1),p)));else if(s[4]){let l=r.slice(2,-2),u=l.includes("|")?l.split("|").pop():l.split("/").pop();a.push(B("span",{key:p,className:"at-md-wikilink",title:l.split("|")[0]},u))}else if(s[5]){let l=r.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/),u=l[2];a.push(ga.test(u)?B("a",{key:p,href:u,target:"_blank",rel:"noreferrer noopener"},ct(l[1],p)):l[1])}else s[6]&&a.push(B("a",{key:p,href:r,target:"_blank",rel:"noreferrer noopener"},fa(r)));n=n.slice(s.index+r.length)}return a}function fa(t){try{let e=new URL(t),a=e.pathname.length>24?e.pathname.slice(0,22)+"\u2026":e.pathname;return e.host.replace(/^www\./,"")+(a==="/"?"":a)}catch{return t}}var Yt=/^(\s*)([-*+]|\d+[.)])\s+(\[( |x|X)\]\s+)?(.*)$/;function te(t){let e=String(t||"").replace(/\r\n?/g,`
`).split(`
`),a=[],n=0;for(;n<e.length;){let o=e[n];if(!o.trim()){n++;continue}let i=o.match(/^\s*(```|~~~)/);if(i){let p=[];for(n++;n<e.length&&!e[n].trim().startsWith(i[1]);)p.push(e[n++]);n++,a.push({type:"code",text:p.join(`
`)});continue}let s=o.match(/^(#{1,6})\s+(.*)$/);if(s){a.push({type:"heading",level:s[1].length,text:s[2].trim(),line:n}),n++;continue}if(/^\s*<!--.*-->\s*$/.test(o)){n++;continue}if(/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(o)){a.push({type:"hr"}),n++;continue}if(/^\s*\|.*\|\s*$/.test(o)&&n+1<e.length&&/^\s*\|?[\s:|-]+\|?\s*$/.test(e[n+1])&&e[n+1].includes("-")){let p=m=>m.trim().replace(/^\||\|$/g,"").split("|").map(x=>x.trim()),l=p(o),u=[];for(n+=2;n<e.length&&/^\s*\|.*\|\s*$/.test(e[n]);)u.push(p(e[n++]));a.push({type:"table",head:l,rows:u});continue}if(/^\s*>/.test(o)){let p=[];for(;n<e.length&&/^\s*>/.test(e[n]);)p.push(e[n++].replace(/^\s*>\s?/,""));a.push({type:"quote",text:p.join(" ")});continue}if(Yt.test(o)){let p=[];for(;n<e.length&&(Yt.test(e[n])||/^\s{2,}\S/.test(e[n])&&p.length);){let l=e[n].match(Yt);l?p.push({indent:Math.floor(l[1].replace(/\t/g,"  ").length/2),ordered:/\d/.test(l[2]),checkbox:l[3]?l[4].toLowerCase()==="x":null,text:l[5],line:n}):p[p.length-1].text+=" "+e[n].trim(),n++}a.push({type:"list",items:p});continue}let r=[];for(;n<e.length&&e[n].trim()&&!Yt.test(e[n])&&!/^(#{1,6})\s/.test(e[n])&&!/^\s*(```|~~~|>|\|)/.test(e[n]);)r.push(e[n++].trim());r.length?a.push({type:"p",text:r.join(" ")}):n++}return a}function ee(t,{onToggle:e}={}){return t.map((a,n)=>{let o=`b${n}`;switch(a.type){case"heading":return B(`h${Math.min(6,a.level+2)}`,{key:o,className:"at-md-h"},ct(a.text,o));case"p":return B("p",{key:o},ct(a.text,o));case"hr":return B("hr",{key:o});case"code":return B("pre",{key:o},B("code",null,a.text));case"quote":return B("blockquote",{key:o},ct(a.text,o));case"table":return B("div",{key:o,className:"at-md-table"},B("table",null,B("thead",null,B("tr",null,a.head.map((i,s)=>B("th",{key:s},ct(i,`${o}h${s}`))))),B("tbody",null,a.rows.map((i,s)=>B("tr",{key:s},i.map((r,p)=>B("td",{key:p},ct(r,`${o}r${s}${p}`))))))));case"list":{let i=a.items[0]&&a.items[0].ordered;return B(i?"ol":"ul",{key:o,className:"at-md-list"},a.items.map((s,r)=>{let p=s.indent?{marginLeft:`${s.indent*1.25}em`}:void 0;return s.checkbox===null?B("li",{key:r,style:p},ct(s.text,`${o}${r}`)):B("li",{key:r,style:p,className:"at-md-check"+(s.checkbox?" is-done":"")},B("label",null,B("input",{type:"checkbox",checked:s.checkbox,disabled:!e,onChange:l=>e&&e(s.line,l.target.checked)}),B("span",null,ct(s.text,`${o}${r}`))))}))}default:return null}})}function Ee(t,e,a){let n=String(t).split(`
`),o=n[e]&&n[e].match(/^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\](.*)$/);return o?(n[e]=`${o[1]}[${a?"x":" "}]${o[3]}`,n.join(`
`)):t}var $e=/^\s*<!--\s*([\w-]+):start\s*-->\s*$/,jt=/^\s*<!--\s*([\w-]+):end\s*-->\s*$/;function Le(t){let e=String(t||"").replace(/\r\n?/g,`
`).split(`
`),a=e.slice(),n=[];for(let s=0;s<e.length;s++){let r=e[s].match($e);if(!r)continue;let p=s+1;for(;p<e.length&&!(jt.test(e[p])&&e[p].match(jt)[1]===r[1]);)p++;if(!(p>=e.length)){n.push({name:r[1],text:e.slice(s+1,p).join(`
`).trim()});for(let l=s;l<=p;l++)a[l]="";s=p}}let o=[],i={title:"",start:0,lines:[]};return a.forEach((s,r)=>{let p=s.match(/^##\s+(.*)$/);p?(o.push(i),i={title:p[1].trim(),start:r+1,lines:[]}):i.lines.push(s)}),o.push(i),{sections:o.filter(s=>s.title||s.lines.join("").trim()).map(s=>({title:s.title,text:s.lines.join(`
`),start:s.start,folded:/^(log|history|activity)$/i.test(s.title)})),managed:n}}function Pe(t){return/dossier|research/i.test(t)?"Research":/state/i.test(t)?"Current state":t.replace(/[-_]+/g," ").replace(/^\w/,e=>e.toUpperCase())}function Ae(t){let e=String(t||"").replace(/\r\n?/g,`
`).split(`
`),a=[],n=[],o=[],i=!1;for(let r=0;r<e.length;r++){let p=e[r].match($e);if(p){let l=r+1;for(;l<e.length&&!(jt.test(e[l])&&e[l].match(jt)[1]===p[1]);)l++;if(l<e.length){(i?o:n).push(e.slice(r,l+1).join(`
`)),r=l;continue}}e[r].trim()&&(i=!0),a.push(e[r])}return{editable:a.join(`
`).replace(/\n{3,}/g,`

`).replace(/^\n+/,"").replace(/\s+$/,"")+`
`,top:n,bottom:o}}function Be(t,e,a){let n=[];return e.length&&n.push(e.join(`

`)),n.push(String(t).replace(/\s+$/,"")),a.length&&n.push(a.join(`

`)),`
`+n.filter(o=>o.trim()).join(`

`)+`
`}var ha=["urgent","high","normal","low"],Oe=[["open","Open"],["in-progress","In progress"],["waiting","Waiting"]];function Ie({id:t,narrow:e,onClose:a}){let{store:n,api:o,actions:i,today:s,meta:r}=U(),p=it(),l=st(),u=g.useCallback(M=>M.byId[t],[t]),m=kt(n,u),[x,w]=g.useState(null),[v,N]=g.useState(!1),[y,b]=g.useState(!1),f=g.useCallback(()=>(w(null),b(!1),n.loadTask(t).catch(M=>w(M))),[t,n]);g.useEffect(()=>{N(!1),f()},[t]),g.useEffect(()=>{let M=H=>{H.key==="Escape"&&!H.defaultPrevented&&!v&&a()};return window.addEventListener("keydown",M),()=>window.removeEventListener("keydown",M)},[a,v]);let D=async(M,H)=>{try{await n.mutate(t,H||M,()=>o.patch(t,{...M,expected_revision:m&&m.revision}))}catch(P){(P.code==="stale_revision"||P.code==="retry")&&b(!0),p(X(P),{tone:"error"})}},z=async M=>{let H=await o.putBody(t,M,m.revision);return n.put(H.task),H.task};if(!m&&x)return g.createElement(ae,{narrow:e,onClose:a},g.createElement("div",{className:"at-panel-empty"},g.createElement($,{name:"alert",size:20}),g.createElement("p",null,X(x)),g.createElement(V,{onClick:f},"Try again")));if(!m)return g.createElement(ae,{narrow:e,onClose:a},g.createElement("div",{className:"at-panel-empty"},g.createElement(Z,{size:18})));let E=F(m),O=m.due&&m.scheduled&&m.due!==m.scheduled,L=M=>l.open(M.currentTarget,H=>g.createElement(Dt,{value:E,today:s,close:H,onPick:P=>i.move(m,P)}),{width:300}),A=M=>l.open(M.currentTarget,H=>g.createElement(Dt,{value:m.due,today:s,close:H,onPick:P=>D({due:P,keep_separate:!0},{due:P})}),{width:300}),ut=M=>l.open(M.currentTarget,H=>g.createElement(et,{close:H,items:(r.areas||[]).map(P=>({label:P,icon:P===m.area?"check":void 0,run:()=>D({area:P})}))}),{width:200}),R=M=>l.open(M.currentTarget,H=>g.createElement(et,{close:H,items:ha.map(P=>({label:P[0].toUpperCase()+P.slice(1),icon:P===(m.priority||"normal")?"check":void 0,run:()=>D({priority:P})}))}),{width:180}),G=M=>l.open(M.currentTarget,H=>g.createElement(et,{close:H,items:Oe.map(([P,wt])=>({label:wt,icon:P===m.status?"check":void 0,run:()=>D({status:P,...P==="waiting"?{reason:"Marked waiting from the Tasks UI"}:{}})}))}),{width:180});return g.createElement(ae,{narrow:e,onClose:a,actions:g.createElement(g.Fragment,null,m.loading?g.createElement(Z,null):null,g.createElement(J,{icon:"refresh",label:"Reload",onClick:f}))},y?g.createElement("div",{className:"at-banner at-tone-late"},g.createElement($,{name:"alert",size:15}),g.createElement("span",{className:"at-flex"},"This task changed somewhere else."),g.createElement(V,{size:"sm",onClick:f},"Reload")):null,g.createElement("div",{className:"at-panel-titlerow"},g.createElement(It,{checked:at(m),onChange:()=>i.toggle(m),label:at(m)?"Mark not done":"Mark done",size:"lg"}),g.createElement(xa,{value:m.title,done:at(m),onSave:M=>D({title:M})})),g.createElement("div",{className:"at-fields"},g.createElement("button",{type:"button",className:T("at-field",E&&E<s&&!at(m)&&"is-late"),onClick:L},g.createElement($,{name:"cal",size:15}),g.createElement("span",null,E?W(E,s):"No date")),g.createElement("button",{type:"button",className:"at-field",onClick:ut},g.createElement(rt,{area:m.area}),g.createElement("span",null,m.area||"No area")),g.createElement("button",{type:"button",className:T("at-field",(m.priority==="high"||m.priority==="urgent")&&"is-high"),onClick:R},g.createElement("span",{className:"at-prio-glyph","data-p":m.priority||"normal"}),g.createElement("span",null,(m.priority||"normal").replace(/^\w/,M=>M.toUpperCase()))),m.status==="waiting"||m.status==="in-progress"?g.createElement("button",{type:"button",className:"at-field",onClick:G},g.createElement("span",null,m.status==="waiting"?"Waiting":"In progress")):null,O?g.createElement("button",{type:"button",className:"at-field",onClick:A},g.createElement("span",{className:"at-muted"},"Due"),g.createElement("span",null,W(m.due,s))):null),g.createElement(va,{value:m.summary||"",onSave:M=>D({summary:M})}),m.research==="pending"||m.research==="running"?g.createElement("div",{className:"at-research-note"},g.createElement($,{name:"spark",size:14})," Hermes is researching this task. Findings will appear here."):null,m.body===void 0?g.createElement("div",{className:"at-panel-loading"},g.createElement(Z,null)):v?g.createElement(ya,{task:m,onSave:z,onDone:()=>N(!1),onStale:()=>b(!0)}):g.createElement(ba,{task:m,onEdit:()=>N(!0),onToggle:async(M,H)=>{try{await z(Ee(m.body,M,H))}catch(P){P.code==="stale_revision"&&b(!0),p(X(P),{tone:"error"})}}}),g.createElement(pt,{title:"More",className:"at-more"},g.createElement("div",{className:"at-more-grid"},g.createElement("span",{className:"at-muted"},"Status"),g.createElement("button",{type:"button",className:"at-field is-plain",onClick:G},(Oe.find(([M])=>M===m.status)||[0,m.status])[1]),g.createElement("span",{className:"at-muted"},"Due date"),g.createElement("span",null,O?g.createElement("button",{type:"button",className:"at-field is-plain",onClick:A},gt(m.due,s)):g.createElement("button",{type:"button",className:"at-link",onClick:A},"Set a separate due date")),m.completed?g.createElement(g.Fragment,null,g.createElement("span",{className:"at-muted"},"Completed"),g.createElement("span",null,gt(m.completed,s))):null,m.project?g.createElement(g.Fragment,null,g.createElement("span",{className:"at-muted"},"Project"),g.createElement("span",{className:"at-mono"},String(m.project).replace(/^\[\[|\]\]$/g,"").split("/").slice(-2,-1)[0]||m.project)):null,g.createElement("span",{className:"at-muted"},"File"),g.createElement("span",{className:"at-mono at-break"},m.path))))}function ae({narrow:t,onClose:e,actions:a,children:n}){return g.createElement("aside",{className:T("at-panel",t?"is-sheet":"is-side"),"aria-label":"Task"},g.createElement("div",{className:"at-panel-bar"},t?g.createElement("span",{className:"at-grabber"}):null,g.createElement("span",{className:"at-flex"}),a,g.createElement(J,{icon:"x",label:"Close",onClick:e})),g.createElement("div",{className:"at-panel-body at-scroll"},n))}function xa({value:t,done:e,onSave:a}){let[n,o]=g.useState(t),i=g.useRef(null);g.useEffect(()=>o(t),[t]),g.useLayoutEffect(()=>{let r=i.current;r&&(r.style.height="auto",r.style.height=r.scrollHeight+"px")},[n]);let s=()=>{let r=n.replace(/\s+/g," ").trim();r&&r!==t?a(r):o(t)};return g.createElement("textarea",{ref:i,rows:1,className:T("at-title-input",e&&"is-done"),value:n,"aria-label":"Title",onChange:r=>o(r.target.value),onBlur:s,onKeyDown:r=>{r.key==="Enter"&&(r.preventDefault(),r.currentTarget.blur()),r.key==="Escape"&&(r.preventDefault(),o(t),r.currentTarget.blur())}})}function va({value:t,onSave:e}){let[a,n]=g.useState(t),o=g.useRef(null);return g.useEffect(()=>n(t),[t]),g.useLayoutEffect(()=>{let i=o.current;i&&(i.style.height="auto",i.style.height=i.scrollHeight+"px")},[a]),g.createElement("textarea",{ref:o,rows:1,className:"at-summary-input",value:a,placeholder:"Add a short summary","aria-label":"Summary",onChange:i=>n(i.target.value),onBlur:()=>{let i=a.trim();i!==t.trim()&&e(i)},onKeyDown:i=>{i.key==="Escape"&&(i.preventDefault(),n(t),i.currentTarget.blur())}})}function ba({task:t,onEdit:e,onToggle:a}){let{sections:n,managed:o}=g.useMemo(()=>Le(t.body||""),[t.body]),i=n.find(l=>/^current state$/i.test(l.title)),s=n.filter(l=>l!==i),r=l=>ee(te(l.text),{onToggle:(u,m)=>a(l.start+u,m)}),p=n.some(l=>l.text.trim());return g.createElement("div",{className:"at-body"},g.createElement("div",{className:"at-body-bar"},g.createElement("span",{className:"at-body-label"},"Notes"),g.createElement("span",{className:"at-flex"}),g.createElement(V,{size:"sm",variant:"ghost",icon:"edit",onClick:e},"Edit")),i&&i.text.trim()?g.createElement("div",{className:"at-state"},g.createElement("div",{className:"at-state-label"},"Current state"),g.createElement("div",{className:"at-md"},r(i))):null,!p&&!o.length?g.createElement("button",{type:"button",className:"at-empty-notes",onClick:e},"Add notes"):null,s.map((l,u)=>l.folded?g.createElement(pt,{key:u,title:l.title,className:"at-fold"},g.createElement("div",{className:"at-md"},r(l))):g.createElement("div",{key:u,className:"at-section"},l.title&&!/^notes$/i.test(l.title)?g.createElement("h3",{className:"at-section-title"},l.title):null,g.createElement("div",{className:"at-md"},r(l)))),o.map((l,u)=>g.createElement(pt,{key:`m${u}`,title:Pe(l.name),className:"at-fold",right:g.createElement($,{name:"spark",size:13})},g.createElement("div",{className:"at-md"},ee(te(l.text))))))}function ya({task:t,onSave:e,onDone:a,onStale:n}){let o=it(),i=g.useMemo(()=>Ae(t.body||""),[]),[s,r]=g.useState(i.editable),[p,l]=g.useState("saved"),u=g.useRef(s),m=g.useRef(i.editable),x=g.useRef(null),w=g.useRef(null),v=g.useCallback(async()=>{clearTimeout(x.current);let b=u.current;if(b===m.current)return l("saved"),!0;l("saving");try{return await e(Be(b,i.top,i.bottom)),m.current=b,l(u.current===b?"saved":"dirty"),!0}catch(f){return l("error"),f.code==="stale_revision"&&n(),o(X(f),{tone:"error"}),!1}},[e,n,o,i]);g.useEffect(()=>{w.current&&w.current.focus()},[]),g.useEffect(()=>()=>clearTimeout(x.current),[]);let N=b=>{r(b),u.current=b,l("dirty"),clearTimeout(x.current),x.current=setTimeout(v,1500)},y=async()=>{await v()&&a()};return g.createElement("div",{className:"at-body is-editing"},g.createElement("div",{className:"at-body-bar"},g.createElement("span",{className:"at-body-label"},"Notes"),g.createElement("span",{className:T("at-save",`is-${p}`)},p==="saving"?"Saving\u2026":p==="saved"?"Saved":p==="error"?"Not saved":"Editing"),g.createElement("span",{className:"at-flex"}),p==="error"?g.createElement(V,{size:"sm",onClick:v},"Retry"):null,g.createElement(V,{size:"sm",variant:"primary",onClick:y},"Done")),g.createElement("textarea",{ref:w,className:"at-editor",value:s,spellCheck:!0,onChange:b=>N(b.target.value),onKeyDown:b=>{(b.metaKey||b.ctrlKey)&&b.key==="s"&&(b.preventDefault(),v()),b.key==="Escape"&&(b.preventDefault(),y())}}),g.createElement("div",{className:"at-editor-hint"},"Markdown. Saves as you type.",i.top.length+i.bottom.length?" Research added by Hermes is kept as it is.":""))}import d from"react";var He=t=>(t||[]).reduce((e,a)=>e+(a.proposals||[]).filter(n=>n.state==="pending"&&!n.expired).length,0),qe=t=>String(t||"").replace(/[-_]+/g," ").replace(/\b\w/g,e=>e.toUpperCase());function oe(t){let e=t.time,a=typeof e=="number"?new Date(e*(e<1e12?1e3:1)):new Date(e);return Number.isNaN(a.getTime())?"":a.toLocaleTimeString(void 0,{hour:"numeric",minute:"2-digit"})}function Ue(t){let e=t.coverage||[];if(!e.length)return t.sources_checked&&t.sources_checked.length?`${t.sources_checked.length} sources`:"";let a=e.filter(n=>n.status==="complete").length;return a===e.length?`${a} ${a===1?"source":"sources"} checked`:`${a} of ${e.length} sources checked`}function Ye({runs:t,error:e,loading:a,reload:n}){let{today:o}=U(),[i,s]=d.useState("waiting");if(e&&e.code==="not_found")return d.createElement(ne,{icon:"inbox",title:"Discovery is not available yet",text:"This version of Alchemy Task has no discovery runs to show. Update the plugin to review discovery here."});if(!t&&a)return d.createElement("div",{className:"at-loading"},d.createElement(Z,{size:18}));if(e&&!t)return d.createElement(ne,{icon:"alert",title:"Could not load discovery",text:X(e),action:d.createElement(V,{onClick:n},"Try again")});let r=t||[];if(!r.length)return d.createElement(ne,{icon:"spark",title:"No discovery runs yet",text:d.createElement(d.Fragment,null,"Discovery reads the sources you choose and proposes tasks. To start one, ask Hermes:",d.createElement("br",null),d.createElement("q",null,"Set up a daily digest from my email and Slack at 7 AM."))});let p=m=>(m.summary?m.summary.pending:(m.proposals||[]).filter(x=>x.state==="pending").length)>0||(m.conflicts||[]).length||(m.failures||[]).length,l=i==="waiting"?r.filter(p):r,u=r[0];return d.createElement("div",{className:"at-scroll at-disco"},d.createElement("div",{className:"at-disco-inner"},d.createElement("div",{className:"at-disco-bar"},d.createElement("h1",{className:"at-period"},"Discovery"),d.createElement("span",{className:"at-flex"}),d.createElement(Ut,{label:"Show",value:i,onChange:s,options:[{value:"waiting",label:"Waiting for you"},{value:"all",label:"All runs"}]}),d.createElement(J,{icon:"refresh",label:"Refresh",onClick:n})),l.length?null:d.createElement("div",{className:"at-caughtup"},d.createElement($,{name:"check",size:18}),d.createElement("div",null,d.createElement("div",{className:"at-caughtup-title"},"All caught up"),d.createElement("div",{className:"at-muted"},"Last run: ",qe(u.stream),", ",W(u.day,o)," ",oe(u)))),l.map(m=>d.createElement(ka,{key:m.run_id,run:m,filter:i,reload:n}))))}function ne({icon:t,title:e,text:a,action:n}){return d.createElement("div",{className:"at-scroll at-disco"},d.createElement("div",{className:"at-emptystate"},d.createElement("span",{className:"at-emptystate-icon"},d.createElement($,{name:t,size:22})),d.createElement("h2",null,e),d.createElement("p",null,a),n))}function ka({run:t,filter:e,reload:a}){let{today:n}=U(),o=t.proposals||[],i=e==="waiting"?o.filter(l=>l.state==="pending"):o,s=(t.outcomes||[]).filter(l=>l.status!=="noop"),r=[...(t.conflicts||[]).map(l=>({...l,kind:"conflict"})),...t.failures||[]],p=t.mode&&t.mode!=="production";return d.createElement("article",{className:"at-run"},d.createElement("header",{className:"at-run-head"},d.createElement("div",null,d.createElement("div",{className:"at-run-title"},qe(t.stream)),d.createElement("div",{className:"at-run-sub"},d.createElement("span",null,W(t.day,n),oe(t)?` \xB7 ${oe(t)}`:""),Ue(t)?d.createElement("span",{className:T(t.degraded&&"is-late")},Ue(t)):null,p?d.createElement("span",{className:"at-badge"},"Test run"):null)),d.createElement("span",{className:"at-flex"}),t.summary&&t.summary.pending?d.createElement("span",{className:"at-count is-accent"},t.summary.pending," waiting"):null),i.length?d.createElement("div",{className:"at-proposals"},i.map(l=>d.createElement(Da,{key:l.proposal_id,p:l,run:t,reload:a,readOnly:p}))):e==="all"&&!o.length?d.createElement("div",{className:"at-run-none"},"No new proposals in this run."):null,s.length?d.createElement(pt,{title:"Updated automatically",count:s.length,className:"at-run-fold"},s.map(l=>d.createElement(Na,{key:l.unit_id,o:l,run:t,reload:a}))):null,r.length?d.createElement(pt,{title:"Needs attention",count:r.length,tone:"late",className:"at-run-fold",defaultOpen:!0},r.map((l,u)=>d.createElement("div",{key:u,className:"at-attn"},d.createElement($,{name:"alert",size:14}),d.createElement("div",null,d.createElement("div",{className:"at-attn-title"},l.title||(l.kind==="conflict"?"Several tasks match one item":"Research follow-up")),d.createElement("div",{className:"at-muted"},l.kind==="conflict"?"Nothing was changed. Ask Hermes which task this belongs to.":l.reason))))):null,d.createElement(pt,{title:"Run details",className:"at-run-fold is-quiet"},d.createElement("div",{className:"at-details"},(t.coverage||[]).map((l,u)=>d.createElement("div",{key:u,className:"at-detail-row"},d.createElement("span",{className:T("at-statusdot",l.status==="complete"?"is-ok":"is-late")}),d.createElement("span",{className:"at-flex"},l.source_key||l.source||"Source"),d.createElement("span",{className:"at-muted"},l.status==="complete"?"Checked":l.status||"Unknown"))),d.createElement("div",{className:"at-detail-row"},d.createElement("span",{className:"at-muted"},"Run"),d.createElement("span",{className:"at-flex"}),d.createElement("span",{className:"at-mono"},String(t.run_id).slice(0,12))),t.delivery&&t.delivery.state?d.createElement("div",{className:"at-detail-row"},d.createElement("span",{className:"at-muted"},"Digest"),d.createElement("span",{className:"at-flex"}),d.createElement("span",null,wa(t.delivery.state))):null)))}var wa=t=>({delivered:"Sent",host_pending:"Sent by Hermes",prepared:"Prepared",not_prepared:"Not sent",unknown:"Unknown",inflight:"Sending"})[t]||t;function Na({o:t,run:e,reload:a}){let{actions:n,api:o}=U(),i=it(),[s,r]=d.useState(!1),p=async()=>{r(!0);try{await o.resume(e.run_id,t.unit_id),await a()}catch(u){i(X(u),{tone:"error"})}r(!1)},l=t.status==="complete";return d.createElement("div",{className:"at-outcome"},d.createElement("span",{className:T("at-statusdot",l?"is-ok":"is-late")}),d.createElement("button",{type:"button",className:"at-outcome-title",onClick:()=>t.task_id&&n.open(t.task_id)},t.title),d.createElement("span",{className:"at-flex"}),l?d.createElement("span",{className:"at-muted"},"Updated"):t.resume_action?d.createElement(V,{size:"sm",onClick:p,disabled:s},s?"Finishing\u2026":"Finish update"):d.createElement("span",{className:"at-muted"},t.status))}function Da({p:t,run:e,reload:a,readOnly:n}){let{api:o,actions:i,today:s,meta:r,store:p}=U(),l=it(),u=st(),m=t.targets||[],x=t.kind==="selection"||m.length>1,[w,v]=d.useState(t.kind==="new"||!m.length?"create":"update"),[N,y]=d.useState(m.length===1?m[0].task_id:null),b=(r.streams||{})[e.stream]||[],[f,D]=d.useState(t.due||t.due_hint||s),[z,E]=d.useState(t.area||(b.length===1?b[0]:r.default_area)||""),[O,L]=d.useState(null),[A,ut]=d.useState(!1);if(t.state==="approved"||t.state==="complete"){let C=t.result||{},q=t.state==="complete"||C.state==="complete";return d.createElement("div",{className:"at-prop is-resolved"},d.createElement("span",{className:T("at-statusdot",q?"is-ok":"is-late")}),d.createElement("span",{className:"at-prop-resolved"},C.operation==="updated"?"Updated":"Created"," ",d.createElement("button",{type:"button",className:"at-linkish",onClick:()=>C.task_id&&i.open(C.task_id)},C.title||t.title)),d.createElement("span",{className:"at-flex"}),q?d.createElement("span",{className:"at-muted"},t.ref):d.createElement("span",{className:"at-muted"},"Saving\u2026"))}if(t.state==="dismissed"||A)return d.createElement("div",{className:"at-prop is-resolved is-dismissed"},d.createElement("span",{className:"at-prop-resolved"},t.title),d.createElement("span",{className:"at-flex"}),d.createElement("span",{className:"at-muted"},"Dismissed"));let R=async C=>{if(C==="create"&&!z){l("Pick an area first.",{tone:"error"});return}let q=m.find(mt=>mt.task_id===N);if(C==="update"&&!q){l("Pick the task to update.",{tone:"error"});return}let xt=C==="create"?{choice:C,due:f,area:z}:{choice:C,target_task_id:q.task_id,expected_revision:q.revision};t.expired&&(xt.allow_expired=!0),L(C);try{let Mt=(await o.approve(t.proposal_id,xt)).receipt||{};l(C==="create"?"Task created":"Task updated",Mt.task_id?{action:{label:"Open",run:()=>i.open(Mt.task_id)}}:{}),await a(),p.refresh()}catch(mt){l(X(mt),{tone:"error"}),(mt.code==="already_resolved"||mt.code==="stale_revision")&&a()}L(null)},G=async()=>{L("dismiss");try{await o.dismiss(t.proposal_id),ut(!0),l("Proposal dismissed"),a()}catch(C){l(X(C),{tone:"error"})}L(null)},M=C=>u.open(C.currentTarget,q=>d.createElement(Dt,{value:f,today:s,onPick:D,close:q}),{width:300}),H=C=>u.open(C.currentTarget,q=>d.createElement(et,{close:q,items:(r.areas||[]).map(xt=>({label:xt,icon:xt===z?"check":void 0,run:()=>E(xt)}))}),{width:200}),P=[].concat(t.new_information||[]).filter(Boolean),wt=[].concat(t.source_links||[]).filter(Boolean),St=t.research_disposition==="uncertain";return d.createElement("div",{className:T("at-prop",t.expired&&"is-expired")},d.createElement("div",{className:"at-prop-head"},d.createElement("span",{className:"at-prop-ref"},t.ref),d.createElement("h3",{className:"at-prop-title"},t.title),d.createElement(J,{icon:"x",label:"Dismiss",className:"at-prop-dismiss",onClick:G,disabled:!!O||n})),t.current_understanding?d.createElement("p",{className:"at-prop-text"},t.current_understanding):null,t.substantive_next_action?d.createElement("div",{className:"at-prop-next"},d.createElement("span",{className:"at-prop-label"},"Next"),d.createElement("span",null,t.substantive_next_action)):null,St?d.createElement("div",{className:"at-prop-uncertain"},d.createElement($,{name:"alert",size:14}),d.createElement("span",null,[].concat(t.uncertainty||[]).join(" ")||"Hermes was not sure about this one. Check it before you add it.")):null,wt.length?d.createElement("div",{className:"at-prop-links"},wt.slice(0,4).map((C,q)=>d.createElement(Sa,{key:q,href:C}))):null,m.length?d.createElement("div",{className:T("at-prop-targets",w==="create"&&"is-muted")},d.createElement("div",{className:"at-prop-label"},x?"Could update one of these tasks":"May update an existing task"),m.map(C=>d.createElement("label",{key:C.task_id,className:T("at-target",N===C.task_id&&w==="update"&&"is-on")},x?d.createElement("input",{type:"radio",name:t.proposal_id,checked:N===C.task_id&&w==="update",onChange:()=>{y(C.task_id),v("update")}}):d.createElement($,{name:"arrowR",size:14}),d.createElement("span",{className:"at-target-main"},d.createElement("span",{className:"at-target-title"},C.title),d.createElement("span",{className:"at-target-meta"},C.area?d.createElement(d.Fragment,null,d.createElement(rt,{area:C.area}),C.area):null,F(C)?d.createElement("span",null,W(F(C),s)):null,C.status&&C.status!=="open"?d.createElement("span",null,C.status):null)),d.createElement("button",{type:"button",className:"at-link",onClick:q=>{q.preventDefault(),i.open(C.task_id)}},"Open"))),P.length?d.createElement("div",{className:"at-prop-addition"},d.createElement("span",{className:"at-prop-label"},"Would add"),d.createElement("ul",null,P.map((C,q)=>d.createElement("li",{key:q},C)))):null):P.length?d.createElement("ul",{className:"at-prop-list"},P.map((C,q)=>d.createElement("li",{key:q},C))):null,d.createElement("div",{className:"at-prop-actions"},w==="create"?d.createElement(d.Fragment,null,d.createElement("button",{type:"button",className:"at-field",onClick:M},d.createElement($,{name:"cal",size:14}),d.createElement("span",null,W(f,s))),d.createElement("button",{type:"button",className:T("at-field",!z&&"is-late"),onClick:H},d.createElement(rt,{area:z}),d.createElement("span",null,z||"Pick area")),d.createElement("span",{className:"at-flex"}),m.length?d.createElement(V,{variant:"ghost",size:"sm",onClick:()=>v("update"),disabled:!!O},"Update instead"):null,d.createElement(V,{variant:"primary",size:"sm",icon:"plus",onClick:()=>R("create"),disabled:!!O||n},O==="create"?"Creating\u2026":"Create task")):d.createElement(d.Fragment,null,d.createElement(V,{variant:"ghost",size:"sm",onClick:()=>v("create"),disabled:!!O},"Create new instead"),d.createElement("span",{className:"at-flex"}),d.createElement(V,{variant:"primary",size:"sm",icon:"check",onClick:()=>R("update"),disabled:!!O||!N||n},O==="update"?"Updating\u2026":x?"Update selected":"Update task"))),t.expired?d.createElement("div",{className:"at-prop-foot at-muted"},"Expired ",W(t.expires,s).toLowerCase(),". You can still add it."):null)}function Sa({href:t}){let e=t;try{let n=new URL(t).host.replace(/^www\./,"");e=/slack/.test(n)?"Slack":/mail\.google|gmail/.test(n)?"Gmail":/notion/.test(n)?"Notion":/github/.test(n)?"GitHub":n}catch{}return d.createElement("a",{className:"at-srclink",href:t,target:"_blank",rel:"noreferrer noopener"},d.createElement($,{name:"link",size:12}),e)}import h from"react";var je=[["daily","Every day"],["weekdays","Weekdays"],["every 4 hours","Every 4 hours"],["every 3 hours","Every 3 hours"],["every 2 hours","Every 2 hours"],["hourly","Every hour"]],re=t=>t==="daily"||t==="weekdays";function Ve(t){let e=String(t||"").trim().toLowerCase().match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/);if(!e)return"07:00";let a=Number(e[1])%24;return e[3]==="pm"&&a<12&&(a+=12),e[3]==="am"&&a===12&&(a=0),`${String(a).padStart(2,"0")}:${e[2]||"00"}`}function Ca(t){let[e,a]=t.split(":").map(Number);return`${(e+11)%12+1}:${String(a).padStart(2,"0")} ${e<12?"AM":"PM"}`}function se({onClose:t,inline:e,narrow:a}){let{api:n}=U(),[o,i]=h.useState(null),[s,r]=h.useState(null),p=h.useCallback(()=>(r(null),n.settings().then(i,r)),[n]);h.useEffect(()=>{p()},[p]);let l=o?h.createElement(Ta,{data:o,reload:p}):s?h.createElement("div",{className:"at-panel-empty"},h.createElement($,{name:"alert",size:20}),h.createElement("p",null,X(s)),h.createElement(V,{onClick:p},"Try again")):h.createElement("div",{className:"at-panel-empty"},h.createElement(Z,{size:18}));return e?h.createElement("div",{className:"at-settings-inline"},l):h.createElement("aside",{className:T("at-panel",a?"is-sheet":"is-side","at-settings"),"aria-label":"Settings"},h.createElement("div",{className:"at-panel-bar"},h.createElement("span",{className:"at-panel-heading"},"Settings"),h.createElement("span",{className:"at-flex"}),h.createElement(J,{icon:"x",label:"Close",onClick:t})),h.createElement("div",{className:"at-panel-body at-scroll"},l))}function Ta({data:t,reload:e}){let a=t.streams||[],n=t.tasks||{};return h.createElement("div",{className:"at-settings-body"},h.createElement("section",{className:"at-set-sec"},h.createElement("h3",null,"Discovery"),h.createElement("p",{className:"at-muted"},"When each discovery stream reads its sources and proposes tasks."),a.length?a.map(o=>h.createElement(za,{key:o.name,s:o,reload:e})):h.createElement("div",{className:"at-set-empty"},"No streams yet. Ask Hermes: ",h.createElement("q",null,"Set up a daily digest from my email at 7 AM."))),h.createElement("section",{className:"at-set-sec"},h.createElement("h3",null,"Tasks"),h.createElement(_a,{t:n,reload:e})),h.createElement("section",{className:"at-set-sec"},h.createElement("h3",null,"Sync and storage"),h.createElement("div",{className:"at-set-grid"},h.createElement("span",{className:"at-muted"},"Workspace"),h.createElement("span",{className:"at-mono at-break"},n.workspace_root||"Not set up"),h.createElement("span",{className:"at-muted"},"Time zone"),h.createElement("span",null,n.timezone||"Hermes default"),t.sync&&t.sync.git?h.createElement(h.Fragment,null,h.createElement("span",{className:"at-muted"},"Git"),h.createElement("span",null,t.sync.git)):null,t.sync&&t.sync.reminders?h.createElement(h.Fragment,null,h.createElement("span",{className:"at-muted"},"iOS Reminders"),h.createElement("span",null,t.sync.reminders)):null),h.createElement("p",{className:"at-muted at-set-hint"},"To change sources, accounts or areas, ask Hermes in chat, for example ",h.createElement("q",null,"add my team Slack channel to the work digest"),".")))}function za({s:t,reload:e}){let{api:a}=U(),n=it(),o=st(),[i,s]=h.useState(t.frequency||"daily"),[r,p]=h.useState(Ve(t.time||"7 AM")),[l,u]=h.useState(null),m=i!==(t.frequency||"daily")||re(i)&&r!==Ve(t.time||"7 AM"),x=async()=>{u("save");try{let y=await a.patchStream(t.name,re(i)?{frequency:i,time:Ca(r)}:{frequency:i});n(y.message||"Schedule updated"),await e()}catch(y){n(X(y),{tone:"error"})}u(null)},w=async()=>{u("run");try{let y=await a.runStream(t.name);n(y.message||"Discovery run started")}catch(y){n(X(y),{tone:"error"})}u(null)},v=y=>o.open(y.currentTarget,b=>h.createElement(et,{close:b,items:je.map(([f,D])=>({label:D,icon:f===i?"check":void 0,run:()=>s(f)}))}),{width:200}),N=t.setup_blocked_reason||(t.activation_state&&!/active|ok|ready/i.test(t.activation_state)?t.activation_state:"");return h.createElement("div",{className:"at-stream"},h.createElement("div",{className:"at-stream-head"},h.createElement("div",null,h.createElement("div",{className:"at-stream-name"},String(t.name).replace(/\b\w/g,y=>y.toUpperCase())),h.createElement("div",{className:"at-muted"},(t.areas||[]).map(y=>h.createElement("span",{key:y,className:"at-inline-area"},h.createElement(rt,{area:y}),y)),t.last_run?h.createElement("span",null," \xB7 last ran ",Ma(t.last_run)):null)),h.createElement("span",{className:"at-flex"}),h.createElement(V,{size:"sm",variant:"ghost",icon:"play",onClick:w,disabled:!!l},l==="run"?"Starting\u2026":"Run now")),h.createElement("div",{className:"at-stream-sched"},h.createElement("button",{type:"button",className:"at-field",onClick:v},h.createElement($,{name:"clock",size:14}),h.createElement("span",null,(je.find(([y])=>y===i)||[0,i])[1]),h.createElement($,{name:"chevD",size:13})),re(i)?h.createElement("label",{className:"at-field at-timefield"},h.createElement("span",{className:"at-muted"},"at"),h.createElement("input",{type:"time",value:r,step:300,onChange:y=>p(y.target.value||r)})):null,t.timezone?h.createElement("span",{className:"at-muted at-tz"},t.timezone.replace(/_/g," ")):null,h.createElement("span",{className:"at-flex"}),m?h.createElement(V,{size:"sm",variant:"primary",onClick:x,disabled:!!l},l==="save"?"Saving\u2026":"Save"):null),(t.sources||[]).length?h.createElement("div",{className:"at-stream-sources"},(t.sources||[]).map(y=>h.createElement("span",{key:y.name,className:"at-chip",title:y.scope},y.name))):null,N?h.createElement("div",{className:"at-banner at-tone-late"},h.createElement($,{name:"alert",size:14}),h.createElement("span",null,N)):null)}function Ma(t){let e=typeof t=="number"?new Date(t*(t<1e12?1e3:1)):new Date(t);if(Number.isNaN(e.getTime()))return"";let a=Math.round((Date.now()-e.getTime())/6e4);return a<60?`${Math.max(1,a)} min ago`:a<1440?`${Math.round(a/60)} h ago`:e.toLocaleDateString(void 0,{month:"short",day:"numeric"})}function _a({t,reload:e}){let{api:a,meta:n}=U(),o=it(),i=st(),s=async p=>{try{await a.patchTaskSettings(p),o("Saved"),await e()}catch(l){o(X(l),{tone:"error"})}};return h.createElement("div",{className:"at-set-grid"},h.createElement("span",{className:"at-muted"},"Default area"),h.createElement("span",null,h.createElement("button",{type:"button",className:"at-field",onClick:p=>i.open(p.currentTarget,l=>h.createElement(et,{close:l,items:(n.areas||[]).map(u=>({label:u,icon:u===t.default_area?"check":void 0,run:()=>s({default_area:u})}))}),{width:200})},h.createElement(rt,{area:t.default_area}),h.createElement("span",null,t.default_area||"None"),h.createElement($,{name:"chevD",size:13}))),h.createElement("span",{className:"at-muted"},"Research new tasks"),h.createElement("span",null,h.createElement("button",{type:"button",role:"switch","aria-checked":!!t.research_by_default,className:T("at-switch",t.research_by_default&&"is-on"),onClick:()=>s({research_by_default:!t.research_by_default})},h.createElement("i",null))))}var Ea=720,$a=3e4;function ie(t){return S.createElement(Ce,null,S.createElement(La,{...t}))}function La({transport:t,host:e,initialView:a,settingsOnly:n}){let o=t,i=it(),s=S.useRef(null),p=ke(s)<Ea,l=S.useMemo(()=>be(o),[o]),u=kt(l,Pa),m=kt(l,Aa),[x,w]=S.useState(null),[v,N]=S.useState(null),[y,b]=S.useState(a==="discovery"?"discovery":"tasks"),[f,D]=S.useState(a==="settings"),[z,E]=S.useState(null),[O,L]=ye("prefs",{view:null,area:"",hideDone:!1}),A=O,ut=S.useCallback(I=>L(Y=>({...Y,...I})),[L]),[R,G]=S.useState(null),[M,H]=S.useState(null),[P,wt]=S.useState(!1),St=S.useCallback(()=>o.meta().then(I=>{w(I),N(null),l.setToday(I.today)},N),[o,l]),C=S.useCallback(async()=>{wt(!0);try{let I=await o.runs();G(I.runs||[]),H(null)}catch(I){H(I)}wt(!1)},[o]);S.useEffect(()=>{St(),C()},[St,C]),S.useEffect(()=>{let I=()=>{document.visibilityState==="visible"&&(St(),l.refresh(),C())},Y=setInterval(I,$a);return window.addEventListener("focus",I),()=>{clearInterval(Y),window.removeEventListener("focus",I)}},[St,C,l]),S.useEffect(()=>{let I=Y=>{let lt=Y.detail;(lt==="discovery"||lt==="tasks")&&b(lt),lt==="settings"&&D(!0)};return window.addEventListener("alchemy-task:open",I),()=>window.removeEventListener("alchemy-task:open",I)},[]);let q=S.useMemo(()=>{let I=_=>_.status==="done"||_.status==="cancelled",Y=_=>i(X(_),{tone:"error"}),lt=_=>l.mutate(_.task_id,{status:"done",completed:l.getState().today},()=>o.complete(_.task_id)),At=_=>l.mutate(_.task_id,{status:"open",completed:null},()=>o.reopen(_.task_id)),Ct=(_,j,tt)=>l.mutate(_.task_id,{scheduled:j,due:tt},()=>o.patch(_.task_id,j===tt?{date:j}:{scheduled:j,due:tt,keep_separate:!0}));return{open:_=>E(_),async toggle(_){try{I(_)?(await At(_),i("Marked not done",{undo:()=>lt(_).catch(Y)})):(await lt(_),i(`Done: ${_.title}`,{undo:()=>At(_).catch(Y)}))}catch(j){Y(j)}},async move(_,j){let tt={scheduled:_.scheduled||null,due:_.due||null};if(!(F(_)===j&&(!_.due||_.due===j)))try{await Ct(_,j,j),i(`Moved to ${W(j,l.getState().today)}`,{undo:()=>Ct({..._,scheduled:j,due:j},tt.scheduled||tt.due,tt.due||tt.scheduled).catch(Y)})}catch(Q){Y(Q)}},async moveMany(_,j){let tt=_.slice(),Q=0;for(let Nt of tt)try{await Ct(Nt,j,j),Q++}catch(Vt){Y(Vt);break}Q&&i(`Moved ${Q} ${Q===1?"task":"tasks"} to ${W(j,l.getState().today).toLowerCase()}`,{undo:async()=>{for(let Nt of tt.slice(0,Q))try{await Ct({...Nt,scheduled:j,due:j},Nt.scheduled||Nt.due,Nt.due||Nt.scheduled)}catch(Vt){Y(Vt);break}}})},async create({title:_,date:j,area:tt}){try{let Q=await o.create({title:_,date:j,area:tt});return Q.task&&l.put(Q.task),i(Q.task&&Q.task.research==="pending"?"Added. Hermes is researching it.":"Added",{action:Q.task?{label:"Open",run:()=>E(Q.task.task_id)}:void 0}),!0}catch(Q){return Y(Q),!1}}}},[o,l,i]),xt=S.useCallback((I,Y)=>q.move(I,Y),[q]),mt=He(R),Mt=S.useMemo(()=>({api:o,store:l,meta:x||{},today:u||x&&x.today,prefs:A,setPrefs:ut,actions:q,selectedId:z,narrow:p,host:e}),[o,l,x,u,A,ut,q,z,p,e]),[de,pe]=S.useState(null);S.useLayoutEffect(()=>{let I=s.current;if(!I||n)return;let Y=()=>{let lt=I.parentElement,At=lt?lt.getBoundingClientRect().height:0;if(e==="desktop"&&At>300){pe(null);return}let Ct=I.getBoundingClientRect().top,ce=window.visualViewport&&window.visualViewport.height||window.innerHeight;pe(Math.max(420,Math.round(ce-Math.max(0,Ct)-8)))};return Y(),window.addEventListener("resize",Y),window.visualViewport&&window.visualViewport.addEventListener("resize",Y),()=>{window.removeEventListener("resize",Y),window.visualViewport&&window.visualViewport.removeEventListener("resize",Y)}},[e,n]);let Ke=!x&&v?S.createElement(We,{icon:"alert",title:"Alchemy Task is not responding",text:X(v)}):!x||!Mt.today?S.createElement("div",{className:"at-loading"},S.createElement(Z,{size:18})):x.configured===!1?S.createElement(We,{icon:"list",title:"Set up your tasks",text:S.createElement(S.Fragment,null,"Alchemy Task is installed but not set up yet. In chat, ask Hermes: ",S.createElement("q",null,"Set up my tasks."))}):n?S.createElement(se,{inline:!0,narrow:p}):S.createElement(S.Fragment,null,S.createElement("nav",{className:"at-appbar"},S.createElement("div",{className:"at-tabs",role:"tablist"},S.createElement("button",{type:"button",role:"tab","aria-selected":y==="tasks",className:T("at-tab",y==="tasks"&&"is-on"),onClick:()=>b("tasks")},"Tasks"),S.createElement("button",{type:"button",role:"tab","aria-selected":y==="discovery",className:T("at-tab",y==="discovery"&&"is-on"),onClick:()=>b("discovery")},"Discovery",mt?S.createElement("span",{className:"at-badge-dot"},mt):null)),S.createElement("span",{className:"at-flex"}),m?S.createElement(Z,{size:12}):null,S.createElement(J,{icon:"gear",label:"Settings",className:T(f&&"is-on"),onClick:()=>{E(null),D(I=>!I)}})),S.createElement("div",{className:T("at-main",z&&!p&&"has-panel",f&&!p&&"has-panel")},y==="tasks"?S.createElement(_e,{narrow:p}):S.createElement(Ye,{runs:R,error:M,loading:P,reload:C})),z?S.createElement(Ie,{id:z,narrow:p,onClose:()=>E(null)}):null,f&&!z?S.createElement(se,{narrow:p,onClose:()=>D(!1)}):null);return S.createElement(Jt.Provider,{value:Mt},S.createElement("div",{ref:s,className:T("at-root at-vars",p&&"is-narrow",`host-${e}`,n&&"is-settings-only"),style:de?{height:de}:void 0},S.createElement(xe,{onDrop:xt},S.createElement(De,{rootRef:s},Ke))))}var Pa=t=>t.today,Aa=t=>t.loading>0;function We({icon:t,title:e,text:a}){return S.createElement("div",{className:"at-emptystate is-full"},S.createElement("span",{className:"at-emptystate-icon"},S.createElement($,{name:t,size:22})),S.createElement("h2",null,e),S.createElement("p",null,a))}var Fe=`/* Alchemy Task UI. Every color comes from the host theme: the web dashboard's --color-* tokens or the
   desktop app's --ui-* tokens, with neutral fallbacks. Everything is scoped under .at- classes. */

.at-vars {
  --at-fg: var(--color-foreground, var(--ui-text-primary, #1c1c1e));
  --at-fg2: var(--color-text-secondary, var(--ui-text-secondary, color-mix(in srgb, var(--at-fg) 78%, transparent)));
  --at-muted: var(--color-muted-foreground, var(--ui-text-tertiary, color-mix(in srgb, var(--at-fg) 56%, transparent)));
  --at-faint: var(--ui-text-quaternary, color-mix(in srgb, var(--at-fg) 34%, transparent));
  --at-line: var(--color-border, var(--ui-stroke-secondary, color-mix(in srgb, var(--at-fg) 11%, transparent)));
  --at-line-soft: color-mix(in srgb, var(--at-line) 60%, transparent);
  --at-accent: var(--color-primary, var(--ui-accent, #4f6ef7));
  --at-accent-fg: var(--color-primary-foreground, #fff);
  --at-surface: var(--color-popover, var(--ui-bg-elevated, var(--color-card, #fff)));
  --at-canvas: var(--color-background, var(--ui-bg-editor, transparent));
  --at-hover: var(--ui-row-hover-background, color-mix(in srgb, var(--at-fg) 5%, transparent));
  --at-press: var(--ui-row-active-background, color-mix(in srgb, var(--at-fg) 9%, transparent));
  --at-soft: color-mix(in srgb, var(--at-fg) 4.5%, transparent);
  --at-late: var(--color-warning, var(--ui-orange, #d9822b));
  --at-ok: var(--color-success, var(--ui-green, #34a853));
  --at-danger: var(--color-destructive, var(--ui-red, #e5484d));
  --at-radius: 10px;
  --at-shadow: 0 1px 2px rgba(0, 0, 0, .06), 0 8px 28px rgba(0, 0, 0, .14);
  --at-shadow-lg: 0 2px 6px rgba(0, 0, 0, .08), 0 24px 64px rgba(0, 0, 0, .22);
  --at-ease: cubic-bezier(.2, .8, .2, 1);
}

.at-root {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 420px;
  height: 100%;
  overflow: hidden;
  color: var(--at-fg);
  font-size: 14px;
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
  letter-spacing: -0.003em;
}
.at-root *, .at-root *::before, .at-root *::after { box-sizing: border-box; }
.at-root button { font: inherit; color: inherit; }
.at-root input, .at-root textarea { font: inherit; color: inherit; }
.at-root h1, .at-root h2, .at-root h3, .at-root p { margin: 0; }
.at-root.is-settings-only { height: auto; overflow: visible; min-height: 0; }

.at-flex { flex: 1 1 auto; min-width: 0; }
.at-muted { color: var(--at-muted); }
.at-mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.at-break { word-break: break-all; }
.at-scroll { overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch; scrollbar-width: thin; }
.at-icon { flex: none; display: block; }
.at-loading { flex: 1; display: grid; place-items: center; min-height: 200px; }
.at-spinner {
  display: inline-block; flex: none; border-radius: 50%;
  border: 1.6px solid var(--at-line); border-top-color: var(--at-muted);
  animation: at-spin .8s linear infinite;
}
@keyframes at-spin { to { transform: rotate(360deg); } }

/* ------------------------------------------------------------------ app bar */
.at-appbar {
  display: flex; align-items: center; gap: 8px; flex: none;
  height: 48px; padding: 0 16px 0 12px;
  border-bottom: 1px solid var(--at-line-soft);
}
.at-tabs { display: flex; gap: 2px; height: 100%; }
.at-tab {
  position: relative; display: inline-flex; align-items: center; gap: 7px;
  padding: 0 10px; border: 0; background: none; cursor: pointer;
  font-weight: 550; font-size: 14px; color: var(--at-muted);
  transition: color .15s;
}
.at-tab:hover { color: var(--at-fg); }
.at-tab.is-on { color: var(--at-fg); }
.at-tab.is-on::after {
  content: ''; position: absolute; left: 10px; right: 10px; bottom: -1px; height: 2px;
  border-radius: 2px; background: var(--at-fg);
}
.at-badge-dot {
  min-width: 18px; height: 18px; padding: 0 5px; border-radius: 999px;
  display: inline-grid; place-items: center;
  background: var(--at-accent); color: var(--at-accent-fg);
  font-size: 11px; font-weight: 650; font-variant-numeric: tabular-nums;
}
.at-main { flex: 1; min-height: 0; display: flex; flex-direction: column; transition: margin-right .22s var(--at-ease); }
.at-main.has-panel { margin-right: min(440px, 46%); }

/* ------------------------------------------------------------------ controls */
.at-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px; flex: none;
  height: 32px; padding: 0 12px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--at-line); background: var(--at-surface);
  font-weight: 550; font-size: 13px; white-space: nowrap;
  transition: background .15s, border-color .15s, opacity .15s, transform .08s;
}
.at-btn:hover { background: var(--at-hover); }
.at-btn:active { transform: translateY(.5px); }
.at-btn:disabled { opacity: .45; cursor: default; }
.at-btn-sm { height: 28px; padding: 0 10px; font-size: 12.5px; border-radius: 7px; }
.at-btn-primary { background: var(--at-accent); border-color: transparent; color: var(--at-accent-fg); }
.at-btn-primary:hover { background: color-mix(in srgb, var(--at-accent) 88%, black); }
.at-btn-ghost { background: transparent; border-color: transparent; color: var(--at-fg2); }
.at-btn-ghost:hover { background: var(--at-hover); color: var(--at-fg); }

.at-iconbtn {
  display: inline-grid; place-items: center; flex: none;
  width: 30px; height: 30px; border-radius: 8px; border: 0; background: transparent;
  color: var(--at-muted); cursor: pointer; transition: background .15s, color .15s;
}
.at-iconbtn:hover, .at-iconbtn.is-on { background: var(--at-hover); color: var(--at-fg); }
.at-iconbtn:disabled { opacity: .35; cursor: default; }

.at-seg {
  display: inline-flex; padding: 2px; gap: 2px; border-radius: 9px;
  background: var(--at-soft); flex: none;
}
.at-seg-item {
  height: 28px; padding: 0 12px; border: 0; border-radius: 7px; background: transparent; cursor: pointer;
  font-size: 13px; font-weight: 550; color: var(--at-muted); transition: background .15s, color .15s, box-shadow .15s;
}
.at-seg-item:hover { color: var(--at-fg); }
.at-seg-item.is-on { background: var(--at-surface); color: var(--at-fg); box-shadow: 0 1px 2px rgba(0, 0, 0, .1), 0 0 0 .5px var(--at-line); }

.at-field, .at-filter {
  display: inline-flex; align-items: center; gap: 6px; flex: none; max-width: 100%;
  height: 30px; padding: 0 11px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--at-line); background: transparent;
  font-size: 13px; color: var(--at-fg2); white-space: nowrap;
  transition: background .15s, border-color .15s, color .15s;
}
.at-field:hover, .at-filter:hover { background: var(--at-hover); color: var(--at-fg); }
.at-field.is-late { color: var(--at-late); border-color: color-mix(in srgb, var(--at-late) 45%, transparent); }
.at-field.is-high { color: var(--at-late); }
.at-field.is-plain { border-color: transparent; padding: 0 8px; margin-left: -8px; }
.at-filter.is-on { border-color: color-mix(in srgb, var(--at-fg) 22%, transparent); color: var(--at-fg); }
.at-timefield input { border: 0; background: transparent; outline: none; padding: 0; width: 7.2em; font-variant-numeric: tabular-nums; }

.at-link { border: 0; background: none; padding: 0; cursor: pointer; color: var(--at-accent); font-size: 12.5px; font-weight: 550; white-space: nowrap; }
.at-link:hover { text-decoration: underline; }
.at-linkish { border: 0; background: none; padding: 0; cursor: pointer; font-weight: 550; text-align: left; }
.at-linkish:hover { text-decoration: underline; }

.at-chip {
  display: inline-flex; align-items: center; gap: 4px; height: 20px; padding: 0 7px; border-radius: 999px;
  border: 0; font-size: 11.5px; font-weight: 600; background: var(--at-soft); color: var(--at-fg2); cursor: pointer; white-space: nowrap;
}
.at-chip.at-tone-late { background: color-mix(in srgb, var(--at-late) 15%, transparent); color: var(--at-late); }
.at-count {
  display: inline-grid; place-items: center; min-width: 20px; height: 20px; padding: 0 6px; border-radius: 999px;
  background: var(--at-soft); color: var(--at-fg2); font-size: 11.5px; font-weight: 650; font-variant-numeric: tabular-nums;
}
.at-count.is-accent { background: color-mix(in srgb, var(--at-accent) 14%, transparent); color: var(--at-accent); }
.at-badge { display: inline-flex; align-items: center; height: 18px; padding: 0 6px; border-radius: 5px; background: var(--at-soft); font-size: 11px; font-weight: 600; color: var(--at-muted); }
.at-areadot { display: inline-block; flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--at-area); }
.at-statusdot { display: inline-block; flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--at-faint); }
.at-statusdot.is-ok { background: var(--at-ok); }
.at-statusdot.is-late { background: var(--at-late); }

.at-switch {
  position: relative; width: 38px; height: 22px; border-radius: 999px; border: 0; cursor: pointer;
  background: color-mix(in srgb, var(--at-fg) 18%, transparent); transition: background .18s;
}
.at-switch i { position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, .25); transition: transform .2s var(--at-ease); }
.at-switch.is-on { background: var(--at-accent); }
.at-switch.is-on i { transform: translateX(16px); }

/* checkbox */
.at-check {
  position: relative; flex: none; display: inline-grid; place-items: center;
  width: 20px; height: 20px; padding: 0; margin: 0; border-radius: 50%; cursor: pointer;
  border: 1.6px solid color-mix(in srgb, var(--at-fg) 34%, transparent); background: transparent;
  transition: border-color .15s, background .18s var(--at-ease), transform .12s;
}
.at-check svg { width: 13px; height: 13px; fill: none; stroke: var(--at-accent-fg); stroke-width: 3; stroke-linecap: round; stroke-linejoin: round;
  stroke-dasharray: 22; stroke-dashoffset: 22; transition: stroke-dashoffset .22s var(--at-ease) .04s; }
.at-check:hover { border-color: var(--at-accent); }
.at-check:hover svg { stroke: var(--at-accent); stroke-dashoffset: 0; opacity: .5; }
.at-check:active { transform: scale(.9); }
.at-check.is-on { background: var(--at-accent); border-color: var(--at-accent); }
.at-check.is-on svg { stroke: var(--at-accent-fg); stroke-dashoffset: 0; opacity: 1; }
.at-check.at-tone-high:not(.is-on) { border-color: color-mix(in srgb, var(--at-late) 70%, transparent); }
.at-check-sm { width: 14px; height: 14px; border-width: 1.4px; }
.at-check-sm svg { width: 9px; height: 9px; stroke-width: 3.4; }
.at-check-lg { width: 24px; height: 24px; }
.at-check-lg svg { width: 15px; height: 15px; }
.at-check.is-ghost { border-style: dashed; cursor: default; }

/* ------------------------------------------------------------------ toolbar */
.at-tasks { flex: 1; min-height: 0; display: flex; flex-direction: column; position: relative; }
.at-toolbar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap; flex: none;
  padding: 14px 20px 12px;
}
.at-toolbar-nav { display: flex; align-items: center; gap: 2px; min-width: 0; }
.at-toolbar-nav .at-btn { margin-right: 6px; }
.at-toolbar-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.at-period { font-size: 20px; font-weight: 650; letter-spacing: -0.015em; margin-left: 10px !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.at-viewport { flex: 1; min-height: 0; display: flex; flex-direction: column; }

/* ------------------------------------------------------------------ rows */
.at-row {
  position: relative; display: flex; align-items: flex-start; gap: 11px;
  padding: 9px 8px 9px 10px; border-radius: 9px; cursor: pointer; outline: none;
  transition: background .12s, opacity .2s;
  user-select: none; -webkit-user-select: none; -webkit-touch-callout: none;
}
.at-row:hover { background: var(--at-hover); }
.at-row:focus-visible { box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--at-accent) 55%, transparent); }
.at-row.is-selected { background: var(--at-press); }
.at-row > .at-check { margin-top: 1px; }
.at-row-main { flex: 1; min-width: 0; }
.at-row-title { font-size: 14px; font-weight: 450; color: var(--at-fg); overflow-wrap: anywhere; transition: color .2s; }
.at-row.is-done .at-row-title { color: var(--at-faint); text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--at-fg) 25%, transparent); }
.at-row-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; margin-top: 2px; font-size: 12px; color: var(--at-muted); }
.at-row.is-done .at-row-meta { opacity: .6; }
.at-meta-area { display: inline-flex; align-items: center; gap: 5px; }
.at-meta-date.is-late, .at-meta-prio { color: var(--at-late); }
.at-meta-prio { font-weight: 600; text-transform: capitalize; }
.at-meta-status { text-transform: capitalize; }
.at-meta-status.is-active { color: var(--at-accent); }
.at-meta-research { display: inline-flex; align-items: center; gap: 4px; color: var(--at-accent); }
.at-row-more { opacity: 0; margin: -4px -2px -4px 0; transition: opacity .15s; }
.at-row:hover .at-row-more, .at-row:focus-within .at-row-more, .at-root.is-narrow .at-row-more { opacity: 1; }
.at-root.is-narrow .at-row-more { color: var(--at-faint); }

.at-row.is-compact { gap: 6px; padding: 3px 5px; border-radius: 6px; align-items: flex-start; }
.at-row.is-compact > .at-check { margin-top: 2.5px; }
.at-row.is-compact .at-row-title {
  font-size: 12.5px; line-height: 1.35;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.at-daylist { position: relative; display: flex; flex-direction: column; gap: 1px; border-radius: 12px; transition: background .15s, box-shadow .15s; min-height: 8px; }
.at-daylist.is-over, .at-cell.is-over, .at-mcell.is-over {
  background: color-mix(in srgb, var(--at-accent) 9%, transparent);
  box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--at-accent) 55%, transparent);
}
.at-drop-hint { padding: 6px 10px; font-size: 12px; font-weight: 600; color: var(--at-accent); }
.at-empty-day { padding: 9px 10px; font-size: 13px; color: var(--at-faint); }
.at-add {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 10px; margin-top: 1px;
  border: 0; border-radius: 9px; background: transparent; cursor: pointer; text-align: left;
  font-size: 13.5px; color: var(--at-faint); transition: background .12s, color .12s;
}
.at-add .at-icon { width: 20px; }
.at-add:hover { background: var(--at-hover); color: var(--at-fg2); }
.at-add-form { display: flex; align-items: center; gap: 11px; padding: 7px 8px 7px 10px; border-radius: 9px; background: var(--at-soft); }
.at-add-input { flex: 1; min-width: 0; border: 0; background: transparent; outline: none; font-size: 14px; padding: 2px 0; }
.at-add-input::placeholder { color: var(--at-faint); }
.at-pop-add { padding: 6px; }

/* disclosure */
.at-disc { border-radius: 10px; }
.at-disc-head {
  display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px 10px;
  border: 0; background: none; cursor: pointer; border-radius: 9px; text-align: left;
  font-size: 13px; font-weight: 600; color: var(--at-fg2);
}
.at-disc-head:hover { background: var(--at-hover); }
.at-disc-chev { transition: transform .18s var(--at-ease); color: var(--at-muted); }
.at-disc.is-open > .at-disc-head .at-disc-chev { transform: rotate(90deg); }
.at-disc-body { padding: 2px 0 6px; animation: at-fade .18s var(--at-ease); }
@keyframes at-fade { from { opacity: 0; transform: translateY(-3px); } }
.at-overdue { margin-bottom: 4px; background: color-mix(in srgb, var(--at-late) 6%, transparent); }
.at-overdue > .at-disc-head { color: var(--at-late); }
.at-overdue > .at-disc-head .at-disc-chev { color: var(--at-late); }
.at-overdue .at-count { background: color-mix(in srgb, var(--at-late) 16%, transparent); color: var(--at-late); }
.at-overdue .at-link { color: var(--at-late); opacity: 0; transition: opacity .15s; }
.at-overdue.is-open .at-link, .at-overdue .at-disc-head:hover .at-link, .at-root.is-narrow .at-overdue .at-link { opacity: 1; }
.at-overdue .at-disc-body { padding: 0 4px 6px; }

/* ------------------------------------------------------------------ month */
.at-month { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 0 20px 16px; }
.at-month-dows { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); padding: 0 0 6px; }
.at-month-dows > div { padding: 0 8px; font-size: 11.5px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--at-muted); }
.at-month-grid {
  flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(7, minmax(0, 1fr));
  border: 1px solid var(--at-line-soft); border-radius: 12px; overflow: hidden;
}
.at-cell {
  position: relative; min-width: 0; min-height: 96px; display: flex; flex-direction: column; gap: 2px;
  padding: 6px 4px 4px; cursor: pointer; overflow: hidden;
  border-right: 1px solid var(--at-line-soft); border-bottom: 1px solid var(--at-line-soft);
  transition: background .12s;
}
.at-cell:nth-child(7n) { border-right: 0; }
.at-cell:hover { background: color-mix(in srgb, var(--at-fg) 2.5%, transparent); }
.at-cell.is-out { background: color-mix(in srgb, var(--at-fg) 1.8%, transparent); }
.at-cell.is-out .at-cell-num { color: var(--at-faint); }
.at-cell-head { display: flex; align-items: center; gap: 6px; padding: 0 4px 2px; min-height: 24px; }
.at-cell-num { font-size: 12.5px; font-weight: 550; color: var(--at-fg2); font-variant-numeric: tabular-nums; line-height: 24px; min-width: 24px; }
.at-cell.is-past:not(.is-out) .at-cell-num { color: var(--at-muted); }
.at-cell.is-today .at-cell-num {
  display: inline-grid; place-items: center; height: 24px; padding: 0 7px; border-radius: 999px;
  background: var(--at-accent); color: var(--at-accent-fg); font-weight: 650;
}
.at-cell-list { display: flex; flex-direction: column; gap: 1px; min-height: 0; overflow: hidden; }
.at-cell-list.is-tight .at-row-title { -webkit-line-clamp: 1; }
.at-cell-list.is-tight .at-row.is-compact { padding-top: 2px; padding-bottom: 2px; }
.at-cell-more { align-self: flex-start; margin: 1px 0 0 5px; padding: 1px 6px; border: 0; background: none; border-radius: 5px; cursor: pointer; font-size: 11.5px; font-weight: 600; color: var(--at-muted); }
.at-cell-more:hover { background: var(--at-hover); color: var(--at-fg); }

.at-daypop { display: flex; flex-direction: column; max-height: min(560px, 70vh); }
.at-daypop-head { display: flex; align-items: flex-start; gap: 8px; padding: 14px 14px 8px 18px; }
.at-daypop-head > div { flex: 1; }
.at-daypop-title { font-size: 17px; font-weight: 650; letter-spacing: -0.01em; }
.at-daypop-head .at-muted { font-size: 12.5px; }
.at-daypop-body { padding: 0 8px 10px; overflow-y: auto; }

/* phone month */
.at-mmonth { flex: 1; padding: 0 12px 96px; }
.at-mmonth-dows, .at-mmonth-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
.at-mmonth-dows span { text-align: center; font-size: 11px; font-weight: 600; color: var(--at-muted); padding-bottom: 4px; }
.at-mmonth-grid { gap: 2px; margin-bottom: 12px; }
.at-mcell {
  position: relative; display: flex; flex-direction: column; align-items: center; gap: 3px;
  height: 50px; padding-top: 5px; border: 0; border-radius: 10px; background: transparent; cursor: pointer;
}
.at-mcell-num { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; font-size: 15px; font-weight: 500; font-variant-numeric: tabular-nums; }
.at-mcell.is-out .at-mcell-num { color: var(--at-faint); }
.at-mcell.is-today .at-mcell-num { color: var(--at-accent); font-weight: 700; }
.at-mcell.is-on .at-mcell-num { background: var(--at-fg); color: var(--at-canvas, #fff); }
.at-mcell.is-today.is-on .at-mcell-num { background: var(--at-accent); color: var(--at-accent-fg); }
.at-mcell-dots { display: flex; gap: 3px; height: 5px; }
.at-mcell-dots i { width: 5px; height: 5px; border-radius: 50%; background: color-mix(in srgb, var(--at-fg) 45%, transparent); }
.at-mcell-dots i.is-done { background: color-mix(in srgb, var(--at-fg) 18%, transparent); }
.at-mcell-dots i.is-late { background: var(--at-late); }
.at-mcell-more { position: absolute; right: 3px; top: 2px; font-size: 9.5px; color: var(--at-muted); }

/* ------------------------------------------------------------------ week */
.at-week { flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 0; padding: 0 12px 12px; }
.at-week-col { display: flex; flex-direction: column; min-height: 0; min-width: 0; padding: 0 4px; border-right: 1px solid var(--at-line-soft); }
.at-week-col:last-child { border-right: 0; }
.at-week-head { display: flex; align-items: baseline; gap: 6px; padding: 4px 8px 10px; }
.at-week-dow { font-size: 11.5px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--at-muted); }
.at-week-num { font-size: 20px; font-weight: 600; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.at-week-col.is-past .at-week-num { color: var(--at-muted); }
.at-week-col.is-today .at-week-num { color: var(--at-accent); }
.at-week-col.is-today .at-week-dow { color: var(--at-accent); }
.at-week-body { flex: 1; min-height: 0; }
.at-week-body .at-daylist { min-height: 100%; }
.at-week .at-row { padding: 7px 6px 7px 7px; gap: 9px; }
.at-week .at-row-title { font-size: 13.5px; }
.at-week .at-check { width: 18px; height: 18px; }

/* ------------------------------------------------------------------ day + scroll of days */
.at-dayview { flex: 1; min-height: 0; }
.at-dayview-inner { max-width: 720px; margin: 0 auto; padding: 6px 24px 64px; }
.at-dayview-head { padding: 4px 10px 14px; }
.at-dayview-head h2 { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
.at-days { flex: 1; min-height: 0; padding: 0 8px 104px; }
.at-daysec { padding: 2px 0 10px; }
.at-daysec-head {
  position: sticky; top: 0; z-index: 2; display: flex; align-items: baseline; gap: 8px;
  padding: 10px 10px 6px; background: var(--at-canvas);
  backdrop-filter: saturate(1.4) blur(8px); -webkit-backdrop-filter: saturate(1.4) blur(8px);
}
.at-daysec-title { font-size: 15px; font-weight: 650; letter-spacing: -0.01em; }
.at-daysec-head .at-muted { font-size: 12.5px; }
.at-daysec.is-today .at-daysec-title { color: var(--at-accent); }
.at-daysec.is-empty { padding-bottom: 0; }
.at-daysec.is-empty .at-daysec-head { position: static; padding-top: 6px; padding-bottom: 0; }
.at-daysec.is-empty .at-daysec-title { font-size: 13.5px; font-weight: 550; color: var(--at-muted); }
.at-daysec.is-empty .at-empty-day { padding-top: 2px; padding-bottom: 6px; font-size: 12.5px; }
.at-sentinel { height: 1px; }

.at-fab {
  position: absolute; right: 18px; bottom: calc(18px + env(safe-area-inset-bottom, 0px)); z-index: 20;
  width: 54px; height: 54px; border-radius: 50%; border: 0; cursor: pointer;
  display: grid; place-items: center; background: var(--at-accent); color: var(--at-accent-fg);
  box-shadow: 0 6px 18px color-mix(in srgb, var(--at-accent) 40%, transparent), 0 2px 4px rgba(0, 0, 0, .15);
  transition: transform .15s var(--at-ease);
}
.at-fab:active { transform: scale(.94); }

/* ------------------------------------------------------------------ overlays */
.at-pop {
  position: absolute; z-index: 60; max-width: calc(100% - 16px);
  background: var(--at-surface); color: var(--at-fg);
  border: 1px solid var(--at-line); border-radius: 13px; box-shadow: var(--at-shadow-lg);
  animation: at-pop .16s var(--at-ease);
}
@keyframes at-pop { from { opacity: 0; transform: translateY(-4px) scale(.98); } }
.at-menu { padding: 5px; display: flex; flex-direction: column; }
.at-menu .at-menu { padding: 0; }
.at-menu-label { padding: 6px 10px 4px; font-size: 11px; font-weight: 650; letter-spacing: .05em; text-transform: uppercase; color: var(--at-muted); }
.at-menu-item {
  display: flex; align-items: center; gap: 10px; width: 100%; height: 34px; padding: 0 10px;
  border: 0; border-radius: 8px; background: none; cursor: pointer; text-align: left; font-size: 13.5px;
}
.at-menu-item:hover { background: var(--at-hover); }
.at-menu-item .at-icon { color: var(--at-muted); }
.at-menu-item.is-danger { color: var(--at-danger); }
.at-menu-pad { width: 15px; flex: none; }
.at-menu-hint { color: var(--at-muted); font-size: 12px; }
.at-menu-sep { height: 1px; margin: 4px 6px; background: var(--at-line-soft); }

.at-dp { padding: 8px; }
.at-dp-quick { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding-bottom: 8px; border-bottom: 1px solid var(--at-line-soft); margin-bottom: 6px; }
.at-dp-q {
  display: flex; flex-direction: column; align-items: flex-start; gap: 0; padding: 7px 10px;
  border: 0; border-radius: 9px; background: var(--at-soft); cursor: pointer; text-align: left; font-size: 13px; font-weight: 550;
}
.at-dp-q .at-muted { font-size: 11.5px; font-weight: 450; }
.at-dp-q:hover { background: var(--at-press); }
.at-dp-q.is-on { box-shadow: inset 0 0 0 1.5px var(--at-accent); }
.at-dp-head { display: flex; align-items: center; gap: 2px; padding: 2px 2px 4px 8px; }
.at-dp-title { flex: 1; font-weight: 650; font-size: 13.5px; }
.at-dp-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }
.at-dp-dow { text-align: center; font-size: 11px; font-weight: 600; color: var(--at-muted); padding: 2px 0 4px; }
.at-dp-day {
  height: 34px; border: 0; border-radius: 9px; background: none; cursor: pointer;
  font-size: 13px; font-variant-numeric: tabular-nums; transition: background .1s;
}
.at-dp-day:hover { background: var(--at-hover); }
.at-dp-day.is-out { color: var(--at-faint); }
.at-dp-day.is-today { color: var(--at-accent); font-weight: 700; }
.at-dp-day.is-on { background: var(--at-accent); color: var(--at-accent-fg); font-weight: 650; }
.at-dp-foot { display: flex; align-items: center; gap: 8px; padding-top: 6px; margin-top: 6px; border-top: 1px solid var(--at-line-soft); }

.at-toasts {
  position: absolute; left: 50%; bottom: calc(20px + env(safe-area-inset-bottom, 0px)); z-index: 80;
  transform: translateX(-50%); display: flex; flex-direction: column; align-items: center; gap: 8px;
  width: min(460px, calc(100% - 24px)); pointer-events: none;
}
.at-root.is-narrow .at-toasts { bottom: calc(86px + env(safe-area-inset-bottom, 0px)); }
.at-toast {
  pointer-events: auto; display: flex; align-items: center; gap: 10px; max-width: 100%;
  padding: 10px 10px 10px 16px; border-radius: 12px;
  background: color-mix(in srgb, var(--at-fg) 92%, transparent); color: var(--at-canvas, #fff);
  box-shadow: var(--at-shadow); font-size: 13.5px; font-weight: 500;
  animation: at-toast .24s var(--at-ease);
}
.at-toast span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@keyframes at-toast { from { opacity: 0; transform: translateY(8px) scale(.98); } }
.at-toast.at-tone-error .at-icon { color: var(--at-late); }
.at-toast-act { flex: none; height: 28px; padding: 0 10px; border: 0; border-radius: 7px; cursor: pointer; background: color-mix(in srgb, var(--at-canvas, #fff) 16%, transparent); color: inherit; font-weight: 650; font-size: 13px; }
.at-toast-act:hover { background: color-mix(in srgb, var(--at-canvas, #fff) 26%, transparent); }

.at-drag-ghost {
  position: fixed; left: 0; top: 0; z-index: 2147483000; pointer-events: none;
  padding: 9px 14px; border-radius: 10px; font-size: 13.5px; font-weight: 550;
  background: var(--at-surface); color: var(--at-fg); border: 1px solid var(--at-line);
  box-shadow: var(--at-shadow-lg); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  rotate: -1.5deg;
}
html.at-dragging, html.at-dragging * { cursor: grabbing !important; }
html.at-dragging .at-row { pointer-events: none; }
html.at-dragging { -webkit-user-select: none; user-select: none; }

/* ------------------------------------------------------------------ panel */
.at-panel {
  position: absolute; z-index: 40; display: flex; flex-direction: column;
  background: var(--at-surface); color: var(--at-fg);
}
.at-panel.is-side {
  top: 0; right: 0; bottom: 0; width: min(440px, 46%);
  border-left: 1px solid var(--at-line-soft); box-shadow: -12px 0 40px rgba(0, 0, 0, .06);
  animation: at-slide .22s var(--at-ease);
}
@keyframes at-slide { from { transform: translateX(24px); opacity: 0; } }
.at-panel.is-sheet {
  left: 0; right: 0; bottom: 0; top: 10px; border-radius: 16px 16px 0 0;
  box-shadow: 0 -10px 40px rgba(0, 0, 0, .2);
  animation: at-sheet .28s var(--at-ease);
}
@keyframes at-sheet { from { transform: translateY(40px); opacity: .4; } }
.at-panel-bar { display: flex; align-items: center; gap: 4px; flex: none; height: 48px; padding: 0 10px 0 16px; position: relative; }
.at-panel-heading { font-size: 15px; font-weight: 650; }
.at-grabber { position: absolute; left: 50%; top: 6px; width: 36px; height: 4px; margin-left: -18px; border-radius: 4px; background: var(--at-line); }
.at-panel-body { flex: 1; min-height: 0; padding: 0 22px 48px; }
.at-panel-empty { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 64px 12px; color: var(--at-muted); text-align: center; }
.at-panel-loading { padding: 24px 0; }

.at-panel-titlerow { display: flex; align-items: flex-start; gap: 12px; padding: 2px 0 12px; }
.at-panel-titlerow .at-check { margin-top: 4px; }
.at-title-input {
  flex: 1; min-width: 0; resize: none; overflow: hidden; border: 0; outline: none; background: transparent; padding: 0;
  font-size: 20px !important; line-height: 1.3; font-weight: 650 !important; letter-spacing: -0.015em;
  border-radius: 6px;
}
.at-title-input:focus { box-shadow: 0 0 0 6px var(--at-soft); background: var(--at-soft); }
.at-title-input.is-done { color: var(--at-muted); text-decoration: line-through; }
.at-fields { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 0 14px 36px; }
.at-prio-glyph { width: 8px; height: 8px; border-radius: 2px; background: var(--at-faint); }
.at-prio-glyph[data-p=urgent] { background: var(--at-danger); }
.at-prio-glyph[data-p=high] { background: var(--at-late); }
.at-prio-glyph[data-p=low] { background: transparent; box-shadow: inset 0 0 0 1.5px var(--at-faint); }
.at-summary-input {
  display: block; width: 100%; resize: none; overflow: hidden; border: 0; outline: none; background: transparent;
  padding: 8px 10px; margin: 0 0 10px; border-radius: 9px; font-size: 14px; line-height: 1.5; color: var(--at-fg2);
}
.at-summary-input:hover { background: var(--at-soft); }
.at-summary-input:focus { background: var(--at-soft); color: var(--at-fg); }
.at-summary-input::placeholder { color: var(--at-faint); }
.at-research-note { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; padding: 9px 12px; border-radius: 10px; font-size: 13px; background: color-mix(in srgb, var(--at-accent) 8%, transparent); color: var(--at-accent); }
.at-banner { display: flex; align-items: center; gap: 8px; padding: 9px 12px; margin-bottom: 12px; border-radius: 10px; font-size: 13px; background: var(--at-soft); }
.at-banner.at-tone-late { background: color-mix(in srgb, var(--at-late) 11%, transparent); color: var(--at-late); }
.at-banner .at-btn { color: var(--at-fg); }

.at-body { border-top: 1px solid var(--at-line-soft); padding-top: 10px; }
.at-body-bar { display: flex; align-items: center; gap: 8px; min-height: 32px; margin-bottom: 4px; }
.at-body-label { font-size: 11.5px; font-weight: 650; letter-spacing: .05em; text-transform: uppercase; color: var(--at-muted); }
.at-save { font-size: 12px; color: var(--at-muted); }
.at-save.is-error { color: var(--at-late); }
.at-state { margin: 4px 0 14px; padding: 12px 14px; border-radius: 11px; background: var(--at-soft); }
.at-state-label { font-size: 11.5px; font-weight: 650; letter-spacing: .05em; text-transform: uppercase; color: var(--at-muted); margin-bottom: 4px; }
.at-section { margin-bottom: 8px; }
.at-section-title { font-size: 14px; font-weight: 650; margin: 14px 0 4px !important; }
.at-fold { margin: 6px -10px 0; }
.at-fold .at-disc-body { padding: 0 10px 8px; }
.at-more { margin: 16px -10px 0; border-top: 1px solid var(--at-line-soft); padding-top: 8px; }
.at-more .at-disc-body { padding: 4px 10px 8px; }
.at-more-grid, .at-set-grid { display: grid; grid-template-columns: max-content 1fr; gap: 10px 18px; align-items: center; font-size: 13px; }
.at-empty-notes { display: block; width: 100%; padding: 12px; border: 1px dashed var(--at-line); border-radius: 10px; background: none; cursor: pointer; color: var(--at-faint); text-align: left; }
.at-empty-notes:hover { color: var(--at-fg2); background: var(--at-soft); }

.at-editor {
  display: block; width: 100%; min-height: 320px; resize: vertical; padding: 14px; border-radius: 11px;
  border: 1px solid var(--at-line); background: var(--at-canvas); outline: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important; font-size: 13px !important; line-height: 1.6;
}
.at-editor:focus { border-color: color-mix(in srgb, var(--at-accent) 60%, transparent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--at-accent) 15%, transparent); }
.at-editor-hint { margin-top: 6px; font-size: 12px; color: var(--at-faint); }

/* markdown */
.at-md { font-size: 14px; line-height: 1.6; color: var(--at-fg2); overflow-wrap: anywhere; }
.at-md p { margin: 0 0 8px; }
.at-md .at-md-h { margin: 14px 0 4px; font-size: 13.5px; font-weight: 650; color: var(--at-fg); }
.at-md a { color: var(--at-accent); text-decoration: none; }
.at-md a:hover { text-decoration: underline; }
.at-md code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; padding: 1px 5px; border-radius: 5px; background: var(--at-soft); }
.at-md pre { margin: 0 0 10px; padding: 10px 12px; border-radius: 9px; background: var(--at-soft); overflow-x: auto; }
.at-md pre code { padding: 0; background: none; }
.at-md blockquote { margin: 0 0 8px; padding-left: 12px; border-left: 2px solid var(--at-line); color: var(--at-muted); }
.at-md hr { border: 0; border-top: 1px solid var(--at-line-soft); margin: 12px 0; }
.at-md-list { margin: 0 0 8px; padding-left: 1.3em; }
.at-md-list li { margin: 2px 0; }
.at-md-check { list-style: none; margin-left: -1.3em !important; }
.at-md-check label { display: flex; align-items: flex-start; gap: 9px; cursor: pointer; padding: 2px 0; }
.at-md-check input { appearance: none; -webkit-appearance: none; flex: none; width: 16px; height: 16px; margin: 3px 0 0; border-radius: 5px; border: 1.5px solid color-mix(in srgb, var(--at-fg) 34%, transparent); cursor: pointer; display: grid; place-items: center; transition: background .15s, border-color .15s; }
.at-md-check input:checked { background: var(--at-accent); border-color: var(--at-accent); }
.at-md-check input:checked::after { content: ''; width: 8px; height: 4px; border: 2px solid var(--at-accent-fg); border-top: 0; border-right: 0; transform: translateY(-1px) rotate(-45deg); }
.at-md-check.is-done span { color: var(--at-faint); text-decoration: line-through; }
.at-md-table { overflow-x: auto; margin: 0 0 10px; }
.at-md table { border-collapse: collapse; font-size: 13px; min-width: 100%; }
.at-md th, .at-md td { padding: 6px 10px; border-bottom: 1px solid var(--at-line-soft); text-align: left; vertical-align: top; }
.at-md th { font-weight: 650; color: var(--at-fg); }
.at-md-wikilink { color: var(--at-accent); }

/* ------------------------------------------------------------------ discovery */
.at-disco { flex: 1; min-height: 0; }
.at-disco-inner { max-width: 780px; margin: 0 auto; padding: 14px 20px 80px; }
.at-disco-bar { display: flex; align-items: center; gap: 10px; padding: 0 0 18px; }
.at-disco-bar .at-period { margin-left: 0 !important; }
.at-caughtup { display: flex; align-items: center; gap: 14px; padding: 18px 20px; border-radius: 14px; background: var(--at-soft); margin-bottom: 20px; }
.at-caughtup > .at-icon { color: var(--at-ok); }
.at-caughtup-title { font-weight: 650; }
.at-run { margin-bottom: 30px; }
.at-run-head { display: flex; align-items: center; gap: 10px; padding: 0 2px 10px; }
.at-run-title { font-size: 16px; font-weight: 650; letter-spacing: -0.01em; }
.at-run-sub { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12.5px; color: var(--at-muted); margin-top: 1px; }
.at-run-sub .is-late { color: var(--at-late); }
.at-run-none { padding: 12px 16px; border-radius: 12px; background: var(--at-soft); color: var(--at-muted); font-size: 13px; }
.at-proposals { display: flex; flex-direction: column; gap: 10px; }
.at-run-fold { margin-top: 6px; }
.at-run-fold.is-quiet > .at-disc-head { color: var(--at-muted); font-weight: 550; }
.at-run-fold.at-tone-late > .at-disc-head { color: var(--at-late); }

.at-prop {
  position: relative; padding: 15px 16px 13px; border-radius: 14px;
  border: 1px solid var(--at-line); background: var(--at-surface);
  box-shadow: 0 1px 2px rgba(0, 0, 0, .04);
  animation: at-fade .2s var(--at-ease);
}
.at-prop.is-expired { opacity: .82; }
.at-prop-head { display: flex; align-items: flex-start; gap: 10px; }
.at-prop-ref { flex: none; margin-top: 2px; min-width: 26px; height: 20px; padding: 0 6px; border-radius: 6px; display: grid; place-items: center; font-size: 11.5px; font-weight: 700; background: var(--at-soft); color: var(--at-muted); font-variant-numeric: tabular-nums; }
.at-prop-title { flex: 1; font-size: 15px !important; font-weight: 650; line-height: 1.35; letter-spacing: -0.005em; }
.at-prop-dismiss { margin: -5px -6px 0 0; color: var(--at-faint); }
.at-prop-text { margin: 6px 0 0 36px !important; color: var(--at-fg2); font-size: 13.5px; }
.at-prop-next { display: flex; gap: 10px; margin: 8px 0 0 36px; font-size: 13.5px; }
.at-prop-label { flex: none; font-size: 11px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--at-muted); padding-top: 2px; }
.at-prop-uncertain { display: flex; gap: 8px; margin: 10px 0 0 36px; padding: 8px 10px; border-radius: 9px; font-size: 13px; background: color-mix(in srgb, var(--at-late) 9%, transparent); color: var(--at-late); }
.at-prop-uncertain .at-icon { margin-top: 2px; }
.at-prop-links { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 0 36px; }
.at-srclink { display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 9px; border-radius: 999px; background: var(--at-soft); color: var(--at-fg2); font-size: 12px; font-weight: 550; text-decoration: none; }
.at-srclink:hover { background: var(--at-press); color: var(--at-fg); }
.at-prop-targets { margin: 12px 0 0 36px; padding: 10px; border-radius: 11px; background: var(--at-soft); transition: opacity .15s; }
.at-prop-targets.is-muted { opacity: .55; }
.at-prop-targets > .at-prop-label { display: block; padding: 0 4px 6px; }
.at-target { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 9px; cursor: pointer; background: var(--at-surface); border: 1px solid transparent; margin-top: 4px; }
.at-target.is-on { border-color: color-mix(in srgb, var(--at-accent) 55%, transparent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--at-accent) 12%, transparent); }
.at-target input { accent-color: var(--at-accent); margin: 0; }
.at-target > .at-icon { color: var(--at-accent); }
.at-target-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.at-target-title { font-weight: 600; font-size: 13.5px; }
.at-target-meta { display: flex; align-items: center; gap: 6px 10px; flex-wrap: wrap; font-size: 12px; color: var(--at-muted); }
.at-target-meta .at-areadot { margin-right: -4px; }
.at-prop-addition { display: flex; gap: 10px; padding: 10px 4px 2px; font-size: 13px; }
.at-prop-addition ul, .at-prop-list { margin: 0; padding-left: 1.1em; color: var(--at-fg2); }
.at-prop-list { margin: 8px 0 0 36px; font-size: 13.5px; }
.at-prop-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 14px 0 0 36px; }
.at-prop-foot { margin: 8px 0 0 36px; font-size: 12px; }
.at-prop.is-resolved { display: flex; align-items: center; gap: 10px; padding: 11px 14px; box-shadow: none; background: transparent; border-color: var(--at-line-soft); }
.at-prop.is-dismissed .at-prop-resolved { color: var(--at-faint); text-decoration: line-through; }
.at-prop-resolved { font-size: 13.5px; color: var(--at-fg2); }
.at-outcome { display: flex; align-items: center; gap: 10px; padding: 8px 12px; font-size: 13.5px; }
.at-outcome-title { border: 0; background: none; padding: 0; cursor: pointer; text-align: left; font-weight: 550; }
.at-outcome-title:hover { text-decoration: underline; }
.at-attn { display: flex; gap: 10px; padding: 8px 12px; font-size: 13.5px; }
.at-attn > .at-icon { color: var(--at-late); margin-top: 3px; }
.at-attn-title { font-weight: 600; }
.at-details { padding: 4px 12px 8px; display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
.at-detail-row { display: flex; align-items: center; gap: 10px; }

.at-emptystate { max-width: 440px; margin: 0 auto; padding: 72px 24px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; }
.at-emptystate.is-full { flex: 1; justify-content: center; }
.at-emptystate-icon { width: 48px; height: 48px; border-radius: 14px; display: grid; place-items: center; background: var(--at-soft); color: var(--at-muted); margin-bottom: 4px; }
.at-emptystate h2 { font-size: 17px; font-weight: 650; }
.at-emptystate p { color: var(--at-muted); font-size: 14px; line-height: 1.55; }
.at-root q { color: var(--at-fg); font-style: normal; }
.at-root q::before { content: '\u201C'; }
.at-root q::after { content: '\u201D'; }

/* ------------------------------------------------------------------ settings */
.at-settings-body { display: flex; flex-direction: column; gap: 26px; padding-top: 4px; }
.at-set-sec h3 { font-size: 13px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--at-muted); margin-bottom: 4px; }
.at-set-sec > p { font-size: 13px; margin-bottom: 12px; }
.at-set-hint { margin-top: 12px !important; line-height: 1.5; }
.at-set-empty { padding: 14px; border-radius: 12px; background: var(--at-soft); font-size: 13px; color: var(--at-muted); }
.at-stream { padding: 14px; border-radius: 13px; border: 1px solid var(--at-line); margin-bottom: 10px; display: flex; flex-direction: column; gap: 12px; }
.at-stream-head { display: flex; align-items: flex-start; gap: 10px; }
.at-stream-name { font-weight: 650; font-size: 14.5px; }
.at-stream-head .at-muted { font-size: 12.5px; display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; }
.at-inline-area { display: inline-flex; align-items: center; gap: 5px; }
.at-stream-sched { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.at-tz { font-size: 12px; }
.at-stream-sources { display: flex; flex-wrap: wrap; gap: 6px; }
.at-stream-sources .at-chip { cursor: default; height: 22px; font-weight: 550; }
.at-settings-inline { padding: 8px 4px; }

/* ------------------------------------------------------------------ narrow */
.at-root.is-narrow { font-size: 15px; }
.at-root.is-narrow .at-appbar { height: 46px; padding: 0 8px 0 6px; }
.at-root.is-narrow .at-toolbar { padding: 10px 12px 8px; gap: 8px; }
.at-root.is-narrow .at-toolbar-nav { width: 100%; }
.at-root.is-narrow .at-toolbar-right { width: 100%; margin-left: 0; }
.at-root.is-narrow .at-toolbar-right .at-seg { flex: 1; }
.at-root.is-narrow .at-toolbar-right .at-seg-item { flex: 1; }
.at-root.is-narrow .at-period { font-size: 22px; }
.at-root.is-narrow .at-row { padding: 11px 8px 11px 10px; gap: 12px; }
.at-root.is-narrow .at-row-title { font-size: 15px; }
.at-root.is-narrow .at-check { width: 22px; height: 22px; }
.at-root.is-narrow .at-check-lg { width: 26px; height: 26px; }
.at-root.is-narrow .at-panel-body { padding: 0 18px 56px; }
.at-root.is-narrow .at-disco-inner { padding: 12px 12px 80px; }
.at-root.is-narrow .at-prop { padding: 14px 14px 12px; }
.at-root.is-narrow .at-prop-text, .at-root.is-narrow .at-prop-next, .at-root.is-narrow .at-prop-links,
.at-root.is-narrow .at-prop-targets, .at-root.is-narrow .at-prop-actions, .at-root.is-narrow .at-prop-uncertain,
.at-root.is-narrow .at-prop-list, .at-root.is-narrow .at-prop-foot { margin-left: 0; }
.at-root.is-narrow .at-disco-bar { flex-wrap: wrap; }
.at-root.is-narrow .at-fields { padding-left: 0; }

@media (prefers-reduced-motion: reduce) {
  .at-root *, .at-pop, .at-panel, .at-toast { animation: none !important; transition: none !important; }
}
`;var Ge="alchemy-task-ui-styles",An={id:"alchemy-task",name:"Alchemy Task",register(t){if(!document.getElementById(Ge)){let i=document.createElement("style");i.id=Ge,i.textContent=Fe,document.head.appendChild(i),t.onDispose(()=>i.remove())}let e=ve((i,s,r)=>t.rest(s,r===void 0?{method:i}:{method:i,body:r})),a=null,n=i=>{a=i,Oa.navigate("/alchemy-task"),window.dispatchEvent(new CustomEvent("alchemy-task:open",{detail:i}))},o=()=>le.createElement(ie,{transport:e,host:"desktop",initialView:a});t.registerMany([{id:"page",area:Ia,data:{path:"/alchemy-task"},render:()=>le.createElement(o,null)},{id:"nav",area:Ua,data:{path:"/alchemy-task",label:"Tasks",codicon:"checklist"}},{id:"open-tasks",area:Xe,data:{title:"Alchemy Task: Open tasks",run:()=>n("tasks")}},{id:"open-discovery",area:Xe,data:{title:"Alchemy Task: Review discovery",run:()=>n("discovery")}}]),typeof t.registerSettingsPage=="function"&&t.registerSettingsPage({id:"settings",title:"Alchemy Task",render:()=>le.createElement(ie,{transport:e,host:"desktop",settingsOnly:!0})})}};export{An as default};
