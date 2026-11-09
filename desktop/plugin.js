import le from"react";import{host as Oa,ROUTES_AREA as Ia,SIDEBAR_NAV_AREA as Ua,PALETTE_AREA as Xe}from"@hermes/plugin-sdk";import N from"react";var ue=t=>String(t).padStart(2,"0");function Xt(t){return`${t.getUTCFullYear()}-${ue(t.getUTCMonth()+1)}-${ue(t.getUTCDate())}`}function bt(t){let[e,a,n]=String(t).split("-").map(Number);return new Date(Date.UTC(e,a-1,n))}function K(t,e){let a=bt(t);return a.setUTCDate(a.getUTCDate()+e),Xt(a)}function Et(t,e){let a=bt(t),n=a.getUTCDate();a.setUTCDate(1),a.setUTCMonth(a.getUTCMonth()+e);let o=new Date(Date.UTC(a.getUTCFullYear(),a.getUTCMonth()+1,0)).getUTCDate();return a.setUTCDate(Math.min(n,o)),Xt(a)}var me=t=>(bt(t).getUTCDay()+6)%7;function Tt(t){return K(t,-me(t))}function Mt(t){return t.slice(0,8)+"01"}function Je(t){let e=bt(Mt(t));return Xt(new Date(Date.UTC(e.getUTCFullYear(),e.getUTCMonth()+1,0)))}function Qe(t,e){return Math.round((bt(e)-bt(t))/864e5)}function Bt(t,e){let a=[];for(let n=t;n<=e;n=K(n,1))a.push(n);return a}function $t(t){let e=Tt(Mt(t)),a=K(Tt(Je(t)),6),n=Bt(e,a),o=[];for(let i=0;i<n.length;i+=7)o.push(n.slice(i,i+7));return o}var vt=(t,e)=>bt(t).toLocaleDateString(void 0,{timeZone:"UTC",...e}),dt=(t,e="short")=>vt(t,{weekday:e}),Lt=(t,e="long")=>vt(t,{month:e}),yt=t=>bt(t).getUTCDate();function Gt(t){return vt(t,{weekday:"long",month:"long",day:"numeric"})}function gt(t,e){let a=!e||t.slice(0,4)===e.slice(0,4);return vt(t,{weekday:"short",month:"short",day:"numeric",...a?{}:{year:"numeric"}})}function F(t,e){if(!t)return"";let a=Qe(e,t);return a===0?"Today":a===1?"Tomorrow":a===-1?"Yesterday":a>1&&a<7?dt(t,"long"):gt(t,e)}function Kt(t,e){let a=(e-me(t)+7)%7||7;return K(t,a)}function ge(t,e,a){if(t==="month")return vt(e,{month:"long",...e.slice(0,4)!==a.slice(0,4)?{year:"numeric"}:{}});if(t==="week"){let n=Tt(e),o=K(n,6),i=n.slice(0,7)===o.slice(0,7),s=vt(n,{month:"short",day:"numeric"}),r=i?String(yt(o)):vt(o,{month:"short",day:"numeric"});return`${s} \u2013 ${r}`}return F(e,a)==="Today"?"Today":vt(e,{weekday:"long",month:"short",day:"numeric"})}var W=t=>t.scheduled||t.due||null;import rt from"react";var he=rt.createContext(null),Ot=()=>rt.useContext(he),Ze=380,fe=6;function Jt(t,e){let a=document.elementFromPoint(t,e),n=a&&a.closest("[data-at-drop]");return n?n.getAttribute("data-at-drop"):null}function Re(t){for(let e=t;e&&e!==document.body;e=e.parentElement){let a=getComputedStyle(e);if(/(auto|scroll)/.test(a.overflowY)&&e.scrollHeight>e.clientHeight)return e}return document.scrollingElement}function xe({onDrop:t,children:e}){let[a,n]=rt.useState(null),o=rt.useRef(null),i=rt.useRef(!1),s=rt.useRef(0),r=rt.useRef(null),c=v=>{let D=o.current&&o.current.over;o.current=o.current?{...o.current,...v}:null;let y=o.current;y&&r.current&&(r.current.style.transform=`translate(${y.x+12}px, ${y.y-20}px)`),y&&y.over!==D&&n(y)},l=(v,D)=>{cancelAnimationFrame(s.current);let y=document.elementFromPoint(v,D),b=y&&Re(y);if(!b)return;let h=b===document.scrollingElement?{top:0,bottom:window.innerHeight}:b.getBoundingClientRect(),S=56,T=D<h.top+S?-Math.ceil((h.top+S-D)/4):D>h.bottom-S?Math.ceil((D-(h.bottom-S))/4):0;if(!T)return;let E=()=>{o.current&&(b.scrollTop+=T,s.current=requestAnimationFrame(E))};s.current=requestAnimationFrame(E)},m=(v,D,y)=>{cancelAnimationFrame(s.current);let b=o.current;if(o.current=null,n(null),r.current&&(r.current.remove(),r.current=null),document.documentElement.classList.remove("at-dragging"),!b)return;i.current=!0,setTimeout(()=>{i.current=!1},50);let h=y?null:Jt(v,D);h&&h!==b.from&&t(b.task,h)},d=(v,D,y,b,h)=>{o.current={task:v,from:D,x:y,y:b,over:D,w:h},n(o.current);let S=document.createElement("div");if(S.className="at-drag-ghost at-vars",S.textContent=v.title,S.style.width=`${Math.min(h||260,300)}px`,S.style.transform=`translate(${y+12}px, ${b-20}px)`,document.body.appendChild(S),r.current=S,document.documentElement.classList.add("at-dragging"),navigator.vibrate)try{navigator.vibrate(8)}catch{}},f=rt.useCallback((v,D)=>({onPointerDown:y=>{if(y.pointerType!=="mouse"||y.button!==0||y.target.closest("button, input, textarea, a, [data-no-drag]"))return;let b=y.clientX,h=y.clientY,S=y.currentTarget.getBoundingClientRect().width,T=L=>{if(!o.current){if(Math.hypot(L.clientX-b,L.clientY-h)<fe)return;d(v,D,L.clientX,L.clientY,S)}c({x:L.clientX,y:L.clientY,over:Jt(L.clientX,L.clientY)}),l(L.clientX,L.clientY)},E=L=>{window.removeEventListener("pointermove",T),window.removeEventListener("pointerup",E),window.removeEventListener("keydown",I),o.current&&m(L.clientX,L.clientY,!1)},I=L=>{L.key==="Escape"&&(E({clientX:-1,clientY:-1}),m(-1,-1,!0))};window.addEventListener("pointermove",T),window.addEventListener("pointerup",E),window.addEventListener("keydown",I)},onTouchStart:y=>{if(y.target.closest("button, input, textarea, a, [data-no-drag]"))return;let b=y.touches[0],h=b.clientX,S=b.clientY,T=y.currentTarget.getBoundingClientRect().width,E={x:h,y:S},I=setTimeout(()=>{I=null,d(v,D,E.x,E.y,T)},Ze),L=R=>{let G=R.touches[0];if(E={x:G.clientX,y:G.clientY},!o.current){I&&Math.hypot(G.clientX-h,G.clientY-S)>fe&&(clearTimeout(I),I=null,ut());return}R.preventDefault(),c({x:G.clientX,y:G.clientY,over:Jt(G.clientX,G.clientY)}),l(G.clientX,G.clientY)},B=R=>{I&&clearTimeout(I),ut(),o.current&&(R.preventDefault(),m(E.x,E.y,R.type==="touchcancel"))},ut=()=>{document.removeEventListener("touchmove",L),document.removeEventListener("touchend",B),document.removeEventListener("touchcancel",B)};document.addEventListener("touchmove",L,{passive:!1}),document.addEventListener("touchend",B),document.addEventListener("touchcancel",B)},onClickCapture:y=>{i.current&&(y.stopPropagation(),y.preventDefault())},onContextMenu:y=>{o.current&&y.preventDefault()}}),[]),w=rt.useMemo(()=>({drag:a,bind:f}),[a,f]);return rt.useEffect(()=>()=>{r.current&&r.current.remove()},[]),rt.createElement(he.Provider,{value:w},e)}var ft=class extends Error{constructor(e,a,n=0){super(a||e),this.code=e||"error",this.status=n}};function ta(t){let e=t&&(t.body||t.responseText||t.message||"");if(e&&typeof e=="object")return e;let a=String(e),n=a.indexOf("{");if(n>=0)try{return JSON.parse(a.slice(n))}catch{}return null}function ea(t){if(t instanceof ft)return t;let e=ta(t),a=e&&(e.error||e.detail),n=t&&t.status||0;return a&&typeof a=="object"?new ft(a.code,a.message,n):typeof a=="string"?new ft(n===404?"not_found":"error",a,n):n===404?new ft("not_found","Not found",404):n===0||/network|failed to fetch|unreachable/i.test(String(t&&t.message))?new ft("offline","Hermes is not reachable right now.",n):new ft("error",t&&t.message||"Something went wrong",n)}var Qt=t=>{let e=Object.entries(t).filter(([,a])=>a!=null&&a!==""&&a!==!1).map(([a,n])=>`${encodeURIComponent(a)}=${encodeURIComponent(n===!0?"1":n)}`);return e.length?`?${e.join("&")}`:""},ot=encodeURIComponent;function ve(t){async function e(a,n,o){let i;try{i=await t(a,n,o)}catch(s){throw ea(s)}if(i&&i.ok===!1){let s=i.error||{};throw new ft(s.code||i.needs||"error",s.message||i.message,200)}return i}return{meta:()=>e("GET","/meta"),tasks:(a,n,{area:o,includeDone:i=!0}={})=>e("GET","/tasks"+Qt({from:a,to:n,area:o,include_done:i})),overdue:({area:a}={})=>e("GET","/overdue"+Qt({area:a})),task:a=>e("GET",`/tasks/${ot(a)}`),patch:(a,n)=>e("PATCH",`/tasks/${ot(a)}`,n),complete:a=>e("POST",`/tasks/${ot(a)}/complete`,{}),reopen:a=>e("POST",`/tasks/${ot(a)}/reopen`,{}),putBody:(a,n,o)=>e("PUT",`/tasks/${ot(a)}/body`,{body:n,expected_revision:o}),create:a=>e("POST","/tasks",a),runs:(a={})=>e("GET","/runs"+Qt(a)),run:a=>e("GET",`/runs/${ot(a)}`),approve:(a,n)=>e("POST",`/proposals/${ot(a)}/approve`,n),dismiss:a=>e("POST",`/proposals/${ot(a)}/dismiss`,{}),resume:(a,n)=>e("POST",`/runs/${ot(a)}/units/${ot(n)}/resume`,{}),settings:()=>e("GET","/settings"),patchStream:(a,n)=>e("PATCH",`/settings/streams/${ot(a)}`,n),runStream:a=>e("POST",`/settings/streams/${ot(a)}/run`,{}),patchTaskSettings:a=>e("PATCH","/settings/tasks",a)}}function X(t){switch(t&&t.code){case"stale_revision":case"retry":return"This task changed somewhere else. Reload it to see the latest version.";case"offline":return"Hermes is not reachable right now. Your change was not saved.";case"needs_due":case"due":return"Pick a date first.";case"needs_area":case"area":return"Pick an area first.";case"already_resolved":return"This proposal was already handled.";case"expired":return"This proposal expired.";case"not_production":return"This was a test run, so it cannot change tasks.";case"not_found":return"It is no longer there. It may have been moved or deleted.";default:return t&&t.message||"Something went wrong."}}import ht from"react";function be(t){let e={byId:{},today:null,loading:0,error:null,version:0},a=new Set,n=new Map,o=new Map,i=()=>{e={...e,version:e.version+1},a.forEach(m=>m())},s=m=>{e={...e,...m},i()};function r(m,d){let f={...e.byId},w=new Set;for(let v of m){if(w.add(v.task_id),n.has(v.task_id))continue;let D=f[v.task_id]||{},y=v.body!==void 0?v.body:D.revision===v.revision?D.body:void 0;f[v.task_id]={...D,...v,body:y}}if(d)for(let[v,D]of Object.entries(f))!w.has(v)&&!n.has(v)&&d(D)&&delete f[v];e={...e,byId:f}}async function c(m){s({loading:e.loading+1});try{return await m}finally{s({loading:Math.max(0,e.loading-1)})}}let l={getState:()=>e,subscribe:m=>(a.add(m),()=>a.delete(m)),setToday:m=>{m!==e.today&&s({today:m})},async loadRange(m,d){o.set(`${m}:${d}`,{from:m,to:d});let f=await c(t.tasks(m,d));return f.today&&(e={...e,today:f.today}),r(f.tasks||[],w=>{let v=W(w);return v&&v>=m&&v<=d}),s({error:null}),f},async loadOverdue(){let m=await c(t.overdue()),d=m.today||e.today;return m.today&&(e={...e,today:m.today}),r(m.tasks||[],f=>{let w=W(f);return f.status!=="done"&&f.status!=="cancelled"&&w&&w<d}),s({error:null}),m},async refresh(){let m=[...o.values()].slice(-4);try{await Promise.all([...m.map(d=>l.loadRange(d.from,d.to)),l.loadOverdue()])}catch(d){s({error:d})}},async loadTask(m){let d=await t.task(m);return r([d.task]),i(),d.task},put(m){r([m]),i()},async mutate(m,d,f){let w=e.byId[m];n.set(m,(n.get(m)||0)+1),w&&d&&(e={...e,byId:{...e.byId,[m]:{...w,...d}}},i());try{let v=await f(),D=(n.get(m)||1)-1;return D?n.set(m,D):n.delete(m),v&&v.task&&(r([v.task]),i()),v}catch(v){let D=(n.get(m)||1)-1;throw D?n.set(m,D):n.delete(m),w&&(e={...e,byId:{...e.byId,[m]:w}},i()),v}}};return l}function kt(t,e){let a=ht.useCallback(()=>e(t.getState()),[t,e]),[n,o]=ht.useState(a);return ht.useEffect(()=>(o(a()),t.subscribe(()=>o(a()))),[t,a]),n}var Zt=ht.createContext(null),H=()=>ht.useContext(Zt);function ye(t,e){let a=`alchemy-task.${t}`,[n,o]=ht.useState(()=>{try{let s=window.localStorage.getItem(a);return s===null?e:JSON.parse(s)}catch{return e}}),i=ht.useCallback(s=>{o(r=>{let c=typeof s=="function"?s(r):s;try{window.localStorage.setItem(a,JSON.stringify(c))}catch{}return c})},[a]);return[n,i]}function ke(t){let[e,a]=ht.useState(()=>typeof window<"u"?window.innerWidth:1200);return ht.useLayoutEffect(()=>{let n=t.current;if(!n)return;a(n.getBoundingClientRect().width);let o=new ResizeObserver(i=>a(i[0].contentRect.width));return o.observe(n),()=>o.disconnect()},[t]),e}import u from"react";import k from"react";var Rt={check:"M5 12.5l4.2 4.2L19 7",chevL:"M15 18l-6-6 6-6",chevR:"M9 6l6 6-6 6",chevD:"M6 9l6 6 6-6",gear:"M12 15.2a3.2 3.2 0 100-6.4 3.2 3.2 0 000 6.4z M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",x:"M6 6l12 12M18 6L6 18",plus:"M12 5v14M5 12h14",more:"M5 12h.01M12 12h.01M19 12h.01",cal:"M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z",spark:"M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z",link:"M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5",alert:"M12 9v4M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",refresh:"M20 11a8 8 0 10-2.3 5.7M20 5v6h-6",inbox:"M4 13l2.5-7h11L20 13M4 13v5a1 1 0 001 1h14a1 1 0 001-1v-5M4 13h4l1.5 2.5h5L16 13h4",edit:"M4 20h4L19 9l-4-4L4 16v4z M13.5 6.5l4 4",grip:"M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",arrowR:"M5 12h14M13 6l6 6-6 6",undo:"M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 010 11H11",dot:"M12 12h.01",list:"M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",clock:"M12 7v5l3 2 M12 21a9 9 0 100-18 9 9 0 000 18z",play:"M7 5l12 7-12 7z"};function $({name:t,size:e=16,className:a="",strokeWidth:n=1.8}){return k.createElement("svg",{className:"at-icon "+a,width:e,height:e,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:n,strokeLinecap:"round",strokeLinejoin:"round","aria-hidden":"true"},k.createElement("path",{d:Rt[t]||Rt.dot}))}var z=(...t)=>t.filter(Boolean).join(" ");function j({variant:t="default",size:e,icon:a,children:n,className:o,...i}){return k.createElement("button",{type:"button",className:z("at-btn",`at-btn-${t}`,e&&`at-btn-${e}`,o),...i},a?k.createElement($,{name:a,size:e==="sm"?14:16}):null,n?k.createElement("span",null,n):null)}function J({icon:t,label:e,className:a,size:n=16,...o}){return k.createElement("button",{type:"button",className:z("at-iconbtn",a),"aria-label":e,title:e,...o},k.createElement($,{name:t,size:n}))}function It({checked:t,onChange:e,label:a,size:n="md",tone:o}){return k.createElement("button",{type:"button",role:"checkbox","aria-checked":!!t,"aria-label":a,className:z("at-check",`at-check-${n}`,t&&"is-on",o&&`at-tone-${o}`),"data-no-drag":"",onClick:i=>{i.stopPropagation(),e(!t)}},k.createElement("svg",{viewBox:"0 0 24 24","aria-hidden":"true"},k.createElement("path",{d:Rt.check})))}function Ut({value:t,options:e,onChange:a,label:n}){return k.createElement("div",{className:"at-seg",role:"tablist","aria-label":n},e.map(o=>k.createElement("button",{key:o.value,type:"button",role:"tab","aria-selected":t===o.value,className:z("at-seg-item",t===o.value&&"is-on"),onClick:()=>a(o.value)},o.label)))}function Z({size:t=14}){return k.createElement("span",{className:"at-spinner",style:{width:t,height:t},"aria-label":"Loading"})}function pt({title:t,count:e,defaultOpen:a=!1,tone:n,children:o,right:i,className:s}){let[r,c]=k.useState(a);return k.createElement("section",{className:z("at-disc",r&&"is-open",n&&`at-tone-${n}`,s)},k.createElement("button",{type:"button",className:"at-disc-head","aria-expanded":r,onClick:()=>c(!r)},k.createElement($,{name:"chevR",size:14,className:"at-disc-chev"}),k.createElement("span",{className:"at-disc-title"},t),e!==void 0?k.createElement("span",{className:"at-count"},e):null,k.createElement("span",{className:"at-flex"}),i),r?k.createElement("div",{className:"at-disc-body"},o):null)}function st({area:t}){return k.createElement("span",{className:"at-areadot",style:{"--at-area":aa(t)},title:t})}var we=[212,152,28,280,340,188,48,252];function aa(t){if(!t)return"var(--at-faint)";let e=0;for(let a of String(t))e=e*31+a.charCodeAt(0)>>>0;return`hsl(${we[e%we.length]} 62% 56%)`}var Ne=k.createContext(null),it=()=>k.useContext(Ne);function De({rootRef:t,children:e}){let[a,n]=k.useState(null),o=k.useCallback(()=>n(r=>(r&&r.onClose&&r.onClose(),null)),[]),i=k.useCallback((r,c,l={})=>n({anchor:r,render:c,...l}),[]),s=k.useMemo(()=>({open:i,close:o}),[i,o]);return k.createElement(Ne.Provider,{value:s},e,a?k.createElement(na,{rootRef:t,...a,close:o}):null)}function na({rootRef:t,anchor:e,render:a,close:n,align:o="start",width:i}){let s=k.useRef(null),[r,c]=k.useState(null);return k.useLayoutEffect(()=>{let l=t.current,m=s.current;if(!l||!m||!e)return;let d=()=>{let w=l.getBoundingClientRect(),v=e.getBoundingClientRect?e.getBoundingClientRect():e,D=m.offsetWidth,y=m.offsetHeight,b=(o==="end"?v.right-D:v.left)-w.left;b=Math.max(8,Math.min(b,w.width-D-8));let h=v.bottom-w.top+6;h+y>w.height-8&&v.top-w.top-y-6>8&&(h=v.top-w.top-y-6),h=Math.max(8,Math.min(h,w.height-y-8)),c({left:b,top:h})};d();let f=new ResizeObserver(d);return f.observe(m),()=>f.disconnect()},[e,t,o]),k.useEffect(()=>{let l=d=>{s.current&&!s.current.contains(d.target)&&!(e&&e.contains&&e.contains(d.target))&&n()},m=d=>{d.key==="Escape"&&(d.stopPropagation(),n())};return document.addEventListener("pointerdown",l,!0),document.addEventListener("keydown",m,!0),()=>{document.removeEventListener("pointerdown",l,!0),document.removeEventListener("keydown",m,!0)}},[e,n]),k.createElement("div",{ref:s,className:"at-pop",role:"dialog",style:{left:r?r.left:-9999,top:r?r.top:-9999,width:i}},a(n))}function at({items:t,close:e}){return k.createElement("div",{className:"at-menu",role:"menu"},t.filter(Boolean).map((a,n)=>a==="-"?k.createElement("div",{key:n,className:"at-menu-sep"}):k.createElement("button",{key:n,type:"button",role:"menuitem",className:z("at-menu-item",a.danger&&"is-danger"),onClick:()=>{e(),a.run()}},a.icon?k.createElement($,{name:a.icon,size:15}):k.createElement("span",{className:"at-menu-pad"}),k.createElement("span",{className:"at-flex"},a.label),a.hint?k.createElement("span",{className:"at-menu-hint"},a.hint):null)))}function Ht(t){return[{label:"Today",date:t,hint:dt(t)},{label:"Tomorrow",date:K(t,1),hint:dt(K(t,1))},{label:"Next Monday",date:Kt(t,0),hint:gt(Kt(t,0),t).replace(/^\w+,\s*/,"")},{label:"In a week",date:K(t,7),hint:gt(K(t,7),t).replace(/^\w+,\s*/,"")}]}function St({value:t,today:e,onPick:a,onClear:n,close:o,extra:i}){let[s,r]=k.useState(Mt(t||e)),c=$t(s),l=m=>{a(m),o&&o()};return k.createElement("div",{className:"at-dp"},k.createElement("div",{className:"at-dp-quick"},Ht(e).map(m=>k.createElement("button",{key:m.label,type:"button",className:z("at-dp-q",t===m.date&&"is-on"),onClick:()=>l(m.date)},k.createElement("span",null,m.label),k.createElement("span",{className:"at-muted"},m.hint)))),k.createElement("div",{className:"at-dp-head"},k.createElement("span",{className:"at-dp-title"},Lt(s)," ",s.slice(0,4)!==e.slice(0,4)?s.slice(0,4):""),k.createElement(J,{icon:"chevL",label:"Previous month",onClick:()=>r(Et(s,-1))}),k.createElement(J,{icon:"chevR",label:"Next month",onClick:()=>r(Et(s,1))})),k.createElement("div",{className:"at-dp-grid",role:"grid"},["M","T","W","T","F","S","S"].map((m,d)=>k.createElement("span",{key:d,className:"at-dp-dow"},m)),c.flat().map(m=>k.createElement("button",{key:m,type:"button",onClick:()=>l(m),className:z("at-dp-day",m.slice(0,7)!==s.slice(0,7)&&"is-out",m===e&&"is-today",m===t&&"is-on")},yt(m)))),n||i?k.createElement("div",{className:"at-dp-foot"},i,k.createElement("span",{className:"at-flex"}),n?k.createElement(j,{size:"sm",variant:"ghost",onClick:()=>{n(),o&&o()}},"Clear"):null):null)}var Se=k.createContext(null),lt=()=>k.useContext(Se);function Ce({children:t}){let[e,a]=k.useState([]),n=k.useRef(0),o=k.useCallback(s=>a(r=>r.filter(c=>c.id!==s)),[]),i=k.useCallback((s,r={})=>{let c=++n.current;return a(l=>[...l.slice(-2),{id:c,message:s,...r}]),setTimeout(()=>o(c),r.duration||(r.undo?6500:r.tone==="error"?7e3:3500)),c},[o]);return k.createElement(Se.Provider,{value:i},t,k.createElement("div",{className:"at-toasts","aria-live":"polite"},e.map(s=>k.createElement("div",{key:s.id,className:z("at-toast",s.tone&&`at-tone-${s.tone}`)},s.tone==="error"?k.createElement($,{name:"alert",size:15}):null,k.createElement("span",{className:"at-flex"},s.message),s.undo?k.createElement("button",{type:"button",className:"at-toast-act",onClick:()=>{o(s.id),s.undo()}},"Undo"):null,s.action?k.createElement("button",{type:"button",className:"at-toast-act",onClick:()=>{o(s.id),s.action.run()}},s.action.label):null))))}var ze={urgent:0,high:1,normal:2,low:3},nt=t=>t.status==="done"||t.status==="cancelled",Te=(t,e)=>(ze[t.priority]??2)-(ze[e.priority]??2)||t.title.localeCompare(e.title);function At(){let{store:t,prefs:e}=H(),a=kt(t,oa),n=kt(t,ra);return u.useMemo(()=>{let o={},i=[];for(let s of Object.values(a)){if(e.area&&s.area!==e.area)continue;let r=W(s);r&&(!nt(s)&&n&&r<n&&i.push(s),(o[r]||(o[r]=[])).push(s))}for(let s of Object.keys(o))o[s].sort((r,c)=>Number(nt(r))-Number(nt(c))||Te(r,c));return i.sort((s,r)=>W(r).localeCompare(W(s))||Te(s,r)),{days:o,overdue:i,today:n}},[a,n,e.area])}var oa=t=>t.byId,ra=t=>t.today;function te({task:t,from:e,compact:a,showDate:n,selected:o}){let{actions:i,today:s}=H(),{bind:r}=Ot(),c=it(),l=nt(t),m=!l&&W(t)&&W(t)<s,d=t.due&&t.scheduled&&t.due!==t.scheduled,f=t.research==="pending"||t.research==="running",w=v=>{v.stopPropagation(),c.open(v.currentTarget,D=>u.createElement(sa,{task:t,close:D}),{width:236,align:"end"})};return u.createElement("div",{className:z("at-row",a&&"is-compact",l&&"is-done",o&&"is-selected"),...r(t,e),onClick:()=>{c.close(),i.open(t.task_id)},onKeyDown:v=>{v.key==="Enter"&&(c.close(),i.open(t.task_id)),v.key===" "&&v.target===v.currentTarget&&(v.preventDefault(),i.toggle(t))},tabIndex:0,role:"button","aria-label":t.title,"data-task":t.task_id},u.createElement(It,{checked:l,onChange:()=>i.toggle(t),label:l?"Mark not done":"Mark done",size:a?"sm":"md",tone:t.priority==="urgent"||t.priority==="high"?"high":void 0}),u.createElement("div",{className:"at-row-main"},u.createElement("div",{className:"at-row-title",title:a?t.title:void 0},t.title),a?null:u.createElement("div",{className:"at-row-meta"},t.area?u.createElement("span",{className:"at-meta-area"},u.createElement(st,{area:t.area}),t.area):null,n||m?u.createElement("span",{className:z("at-meta-date",m&&"is-late")},F(W(t),s)):null,d?u.createElement("span",{className:"at-meta-due"},"due ",F(t.due,s)):null,t.priority==="urgent"||t.priority==="high"?u.createElement("span",{className:"at-meta-prio"},t.priority):null,t.status==="waiting"?u.createElement("span",{className:"at-meta-status"},"waiting"):null,t.status==="in-progress"?u.createElement("span",{className:"at-meta-status is-active"},"in progress"):null,f?u.createElement("span",{className:"at-meta-research"},u.createElement($,{name:"spark",size:12}),"researching"):null)),a?null:u.createElement(J,{icon:"more",label:"Task actions",className:"at-row-more",onClick:w,"data-no-drag":""}))}function sa({task:t,close:e}){let{actions:a,today:n}=H(),[o,i]=u.useState(!1);if(o)return u.createElement(St,{value:W(t),today:n,onPick:r=>a.move(t,r),close:e});let s=Ht(n).slice(0,3).map(r=>({label:r.label,hint:r.hint,icon:"cal",run:()=>a.move(t,r.date)})).filter((r,c)=>Ht(n)[c].date!==W(t));return u.createElement("div",{className:"at-menu",role:"menu"},u.createElement("div",{className:"at-menu-label"},"Move to"),u.createElement(at,{items:s,close:e}),u.createElement("button",{type:"button",className:"at-menu-item",onClick:()=>i(!0)},u.createElement($,{name:"cal",size:15}),u.createElement("span",{className:"at-flex"},"Pick a date\u2026")),u.createElement("div",{className:"at-menu-sep"}),u.createElement(at,{close:e,items:[{label:nt(t)?"Mark not done":"Mark done",icon:"check",run:()=>a.toggle(t)},{label:"Open",icon:"arrowR",run:()=>a.open(t.task_id)}]}))}function qt({date:t,tasks:e=[],overdue:a=[],compact:n,empty:o="Nothing planned",showAdd:i}){let{today:s,prefs:r,selectedId:c}=H(),{drag:l}=Ot(),m=t===s,d=r.hideDone?e.filter(w=>!nt(w)):e,f=e.length-d.length;return u.createElement("div",{className:z("at-daylist",l&&l.over===t&&"is-over"),"data-at-drop":t},m&&a.length?u.createElement(ia,{tasks:a}):null,d.map(w=>u.createElement(te,{key:w.task_id,task:w,from:t,compact:n,selected:c===w.task_id})),!d.length&&!(m&&a.length)?u.createElement("div",{className:"at-empty-day"},f?`${f} done`:o):null,i?u.createElement(Me,{date:t}):null,l&&l.over===t&&l.from!==t?u.createElement("div",{className:"at-drop-hint"},"Move to ",F(t,s)):null)}function ia({tasks:t,defaultOpen:e=!1}){let{actions:a,today:n,selectedId:o}=H();return u.createElement(pt,{className:"at-overdue",tone:"late",title:"Overdue",count:t.length,defaultOpen:e,right:u.createElement("span",{className:"at-link",role:"button",tabIndex:0,"data-no-drag":"",onClick:i=>{i.stopPropagation(),a.moveMany(t,n)}},"Move all to today")},t.map(i=>u.createElement(te,{key:i.task_id,task:i,from:W(i),showDate:!0,selected:o===i.task_id})))}function Me({date:t,autoFocus:e,onDone:a}){let{actions:n,meta:o,prefs:i}=H(),[s,r]=u.useState(""),[c,l]=u.useState(!1),[m,d]=u.useState(!!e),f=u.useRef(null);if(u.useEffect(()=>{m&&f.current&&f.current.focus()},[m]),!m)return u.createElement("button",{type:"button",className:"at-add",onClick:()=>d(!0),"data-no-drag":""},u.createElement($,{name:"plus",size:14})," Add a task");let w=async()=>{let v=s.trim();if(!v){d(!1),a&&a();return}l(!0);let D=await n.create({title:v,date:t,area:i.area||o.default_area||void 0});l(!1),D&&(r(""),f.current&&f.current.focus())};return u.createElement("form",{className:"at-add-form","data-no-drag":"",onSubmit:v=>{v.preventDefault(),w()}},u.createElement("span",{className:"at-check at-check-md is-ghost","aria-hidden":"true"}),u.createElement("input",{ref:f,className:"at-add-input",value:s,placeholder:"New task",disabled:c,onChange:v=>r(v.target.value),onKeyDown:v=>{v.key==="Escape"&&(r(""),d(!1),a&&a())},onBlur:()=>{s.trim()||(d(!1),a&&a())}}),c?u.createElement(Z,null):null)}function la({anchor:t,narrow:e}){let{today:a,selectedId:n}=H(),{days:o,overdue:i}=At(),s=it(),{drag:r}=Ot(),c=$t(t),l=t.slice(0,7),[m,d]=u.useState(null);if(e){let b=m&&m.slice(0,7)===l?m:a.slice(0,7)===l?a:Mt(t);return u.createElement("div",{className:"at-scroll at-mmonth"},u.createElement("div",{className:"at-mmonth-dows"},["M","T","W","T","F","S","S"].map((h,S)=>u.createElement("span",{key:S},h))),u.createElement("div",{className:"at-mmonth-grid"},c.flat().map(h=>{let S=o[h]||[],T=S.filter(E=>!nt(E)).length;return u.createElement("button",{key:h,type:"button","data-at-drop":h,onClick:()=>d(h),className:z("at-mcell",h.slice(0,7)!==l&&"is-out",h===a&&"is-today",h===b&&"is-on",r&&r.over===h&&"is-over")},u.createElement("span",{className:"at-mcell-num"},yt(h)),u.createElement("span",{className:"at-mcell-dots"},S.slice(0,3).map(E=>u.createElement("i",{key:E.task_id,className:nt(E)?"is-done":""})),h===a&&i.length?u.createElement("i",{className:"is-late"}):null),T>3?u.createElement("span",{className:"at-mcell-more"},"+",T-3):null)})),u.createElement(ee,{date:b,tasks:o[b]||[],overdue:b===a?i:[]}))}let f=(b,h)=>s.open(h,S=>u.createElement(da,{date:b,close:S}),{width:360}),w=u.useRef(null),[v,D]=u.useState(110);u.useLayoutEffect(()=>{let b=w.current;if(!b)return;let h=new ResizeObserver(()=>D(b.clientHeight/c.length));return h.observe(b),()=>h.disconnect()},[c.length]);let y=v-34;return u.createElement("div",{className:"at-month"},u.createElement("div",{className:"at-month-dows"},c[0].map(b=>u.createElement("div",{key:b},dt(b)))),u.createElement("div",{ref:w,className:"at-month-grid",style:{gridTemplateRows:`repeat(${c.length}, minmax(0, 1fr))`}},c.flat().map(b=>{let h=o[b]||[],S=h.length*37<=y,T=S?h.length:Math.max(1,Math.floor(y/23)),E=h.length>T?h.slice(0,Math.max(1,T-1)):h,I=h.length-E.length,L=b===a;return u.createElement("div",{key:b,"data-at-drop":b,className:z("at-cell",b.slice(0,7)!==l&&"is-out",L&&"is-today",b<a&&"is-past",r&&r.over===b&&"is-over"),onClick:B=>{B.target.closest(".at-row")||f(b,B.currentTarget)}},u.createElement("div",{className:"at-cell-head"},u.createElement("span",{className:"at-cell-num"},yt(b)===1?`${Lt(b,"short")} 1`:yt(b)),L&&i.length?u.createElement("button",{type:"button",className:"at-chip at-tone-late","data-no-drag":"",onClick:B=>{B.stopPropagation(),f(b,B.currentTarget.closest(".at-cell"))}},i.length," overdue"):null),u.createElement("div",{className:z("at-cell-list",!S&&"is-tight")},E.map(B=>u.createElement(te,{key:B.task_id,task:B,from:b,compact:!0,selected:n===B.task_id})),I>0?u.createElement("button",{type:"button",className:"at-cell-more","data-no-drag":"",onClick:B=>{B.stopPropagation(),f(b,B.currentTarget.closest(".at-cell"))}},"+",I," more"):null))})))}function da({date:t,close:e}){let{today:a}=H(),{days:n,overdue:o}=At();return u.createElement("div",{className:"at-daypop"},u.createElement("div",{className:"at-daypop-head"},u.createElement("div",null,u.createElement("div",{className:"at-daypop-title"},F(t,a)==="Today"?"Today":dt(t,"long")),u.createElement("div",{className:"at-muted"},Gt(t))),u.createElement(J,{icon:"x",label:"Close",onClick:e})),u.createElement("div",{className:"at-daypop-body"},u.createElement(qt,{date:t,tasks:n[t]||[],overdue:t===a?o:[],showAdd:!0})))}function pa({anchor:t,narrow:e}){let{today:a}=H(),{days:n,overdue:o}=At(),i=Tt(t),s=Bt(i,K(i,6));return e?u.createElement("div",{className:"at-scroll at-days"},s.map(r=>u.createElement(ee,{key:r,date:r,tasks:n[r]||[],overdue:r===a?o:[]}))):u.createElement("div",{className:"at-week"},s.map(r=>u.createElement("div",{key:r,className:z("at-week-col",r===a&&"is-today",r<a&&"is-past")},u.createElement("div",{className:"at-week-head"},u.createElement("span",{className:"at-week-dow"},dt(r)),u.createElement("span",{className:"at-week-num"},yt(r))),u.createElement("div",{className:"at-week-body at-scroll"},u.createElement(qt,{date:r,tasks:n[r]||[],overdue:r===a?o:[],showAdd:!0})))))}function ca({anchor:t}){let{today:e}=H(),{days:a,overdue:n}=At();return u.createElement("div",{className:"at-scroll at-dayview"},u.createElement("div",{className:"at-dayview-inner"},u.createElement("header",{className:"at-dayview-head"},u.createElement("h2",null,F(t,e)==="Today"?"Today":dt(t,"long")),u.createElement("div",{className:"at-muted"},Gt(t))),u.createElement(qt,{date:t,tasks:a[t]||[],overdue:t===e?n:[],showAdd:!0})))}function ee({date:t,tasks:e,overdue:a}){let{today:n}=H(),o=F(t,n),i=o==="Today"||o==="Tomorrow"||o==="Yesterday",s=!e.length&&!a.length;return u.createElement("section",{className:z("at-daysec",t===n&&"is-today",s&&"is-empty")},u.createElement("header",{className:"at-daysec-head"},u.createElement("span",{className:"at-daysec-title"},i?o:dt(t,"long")),u.createElement("span",{className:"at-muted"},gt(t,n).replace(/^\w+,\s*/,""))),u.createElement(qt,{date:t,tasks:e,overdue:a,showAdd:!s||t===n}))}function ua({anchor:t,onReachEnd:e,length:a}){let{today:n}=H(),{days:o,overdue:i}=At(),s=Bt(t,K(t,a-1)),r=u.useRef(null);return u.useEffect(()=>{let c=r.current;if(!c)return;let l=new IntersectionObserver(m=>{m[0].isIntersecting&&e()},{rootMargin:"400px"});return l.observe(c),()=>l.disconnect()},[e]),u.createElement("div",{className:"at-scroll at-days"},s.map(c=>u.createElement(ee,{key:c,date:c,tasks:o[c]||[],overdue:c===n?i:[]})),u.createElement("div",{ref:r,className:"at-sentinel"}))}function _e({narrow:t}){let{store:e,prefs:a,setPrefs:n,meta:o,today:i}=H(),s=it(),r=a.view||(t?"day":"month"),[c,l]=u.useState(i),[m,d]=u.useState(21);u.useEffect(()=>{!c&&i&&l(i)},[i,c]);let f=c||i,w=u.useMemo(()=>{if(!f)return null;if(r==="month"){let h=$t(f);return[h[0][0],h[h.length-1][6]]}if(r==="week"){let h=Tt(f);return[h,K(h,6)]}return t?[f,K(f,m-1)]:[f,f]},[f,r,t,m]);u.useEffect(()=>{w&&(e.loadRange(w[0],w[1]).catch(()=>{}),e.loadOverdue().catch(()=>{}))},[w&&w[0],w&&w[1]]);let v=h=>{l(r==="month"?Et(f,h):r==="week"?K(f,7*h):K(f,h))};if(u.useEffect(()=>{let h=S=>{if(S.target.closest&&S.target.closest("input, textarea, [contenteditable]")||S.metaKey||S.ctrlKey||S.altKey)return;let T=S.key.toLowerCase();if(T==="t")l(i);else if(T==="d")n({view:"day"});else if(T==="w")n({view:"week"});else if(T==="m")n({view:"month"});else if(S.key==="ArrowLeft")v(-1);else if(S.key==="ArrowRight")v(1);else return;S.preventDefault()};return window.addEventListener("keydown",h),()=>window.removeEventListener("keydown",h)}),!f)return u.createElement("div",{className:"at-loading"},u.createElement(Z,{size:18}));let D=o.areas||[],y=h=>s.open(h.currentTarget,S=>u.createElement(at,{close:S,items:[{label:"All areas",icon:a.area?void 0:"check",run:()=>n({area:""})},"-",...D.map(T=>({label:T,icon:a.area===T?"check":void 0,run:()=>n({area:T})})),"-",{label:a.hideDone?"Show completed":"Hide completed",run:()=>n({hideDone:!a.hideDone})}]}),{width:200,align:"end"}),b=h=>s.open(h.currentTarget,S=>u.createElement("div",{className:"at-pop-add"},u.createElement(Me,{date:r==="day"?f:i,autoFocus:!0,onDone:S})),{width:320,align:"end"});return u.createElement("div",{className:z("at-tasks",`is-${r}`)},u.createElement("div",{className:"at-toolbar"},u.createElement("div",{className:"at-toolbar-nav"},u.createElement(j,{variant:"ghost",size:"sm",onClick:()=>l(i),disabled:f===i&&r!=="month"},"Today"),u.createElement(J,{icon:"chevL",label:"Previous",onClick:()=>v(-1)}),u.createElement(J,{icon:"chevR",label:"Next",onClick:()=>v(1)}),u.createElement("h1",{className:"at-period"},r==="day"&&t?Lt(f):ge(r,f,i))),u.createElement("div",{className:"at-toolbar-right"},u.createElement(Ut,{label:"View",value:r,onChange:h=>n({view:h}),options:[{value:"day",label:"Day"},{value:"week",label:"Week"},{value:"month",label:"Month"}]}),u.createElement("button",{type:"button",className:z("at-filter",a.area&&"is-on"),onClick:y},a.area?u.createElement(st,{area:a.area}):null,u.createElement("span",null,a.area||"All areas"),u.createElement($,{name:"chevD",size:14})),t?null:u.createElement(j,{variant:"primary",size:"sm",icon:"plus",onClick:b},"Add"))),u.createElement("div",{className:"at-viewport"},r==="month"?u.createElement(la,{anchor:f,narrow:t}):null,r==="week"?u.createElement(pa,{anchor:f,narrow:t}):null,r==="day"&&t?u.createElement(ua,{anchor:f,length:m,onReachEnd:()=>d(h=>Math.min(h+14,120))}):null,r==="day"&&!t?u.createElement(ca,{anchor:f}):null),t?u.createElement("button",{type:"button",className:"at-fab","aria-label":"Add a task",onClick:b},u.createElement($,{name:"plus",size:22})):null)}import g from"react";import ma from"react";var O=ma.createElement,ga=/^(https?:|mailto:|obsidian:|#)/i;function ct(t,e="i"){let a=[],n=String(t),o=0,i=/(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(\*[^*\s][^*]*\*|_[^_\s][^_]*_)|(\[\[[^\]]+\]\])|(\[[^\]]+\]\([^)\s]+\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/;for(;n;){let s=n.match(i);if(!s){a.push(n);break}s.index&&a.push(n.slice(0,s.index));let r=s[0],c=`${e}-${o++}`;if(s[1])a.push(O("code",{key:c},r.slice(1,-1)));else if(s[2])a.push(O("strong",{key:c},ct(r.slice(2,-2),c)));else if(s[3])a.push(O("em",{key:c},ct(r.slice(1,-1),c)));else if(s[4]){let l=r.slice(2,-2),m=l.includes("|")?l.split("|").pop():l.split("/").pop();a.push(O("span",{key:c,className:"at-md-wikilink",title:l.split("|")[0]},m))}else if(s[5]){let l=r.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/),m=l[2];a.push(ga.test(m)?O("a",{key:c,href:m,target:"_blank",rel:"noreferrer noopener"},ct(l[1],c)):l[1])}else s[6]&&a.push(O("a",{key:c,href:r,target:"_blank",rel:"noreferrer noopener"},fa(r)));n=n.slice(s.index+r.length)}return a}function fa(t){try{let e=new URL(t),a=e.pathname.length>24?e.pathname.slice(0,22)+"\u2026":e.pathname;return e.host.replace(/^www\./,"")+(a==="/"?"":a)}catch{return t}}var Yt=/^(\s*)([-*+]|\d+[.)])\s+(\[( |x|X)\]\s+)?(.*)$/;function jt(t){let e=String(t||"").replace(/\r\n?/g,`
`).split(`
`),a=[],n=0;for(;n<e.length;){let o=e[n];if(!o.trim()){n++;continue}let i=o.match(/^\s*(```|~~~)/);if(i){let c=[];for(n++;n<e.length&&!e[n].trim().startsWith(i[1]);)c.push(e[n++]);n++,a.push({type:"code",text:c.join(`
`)});continue}let s=o.match(/^(#{1,6})\s+(.*)$/);if(s){a.push({type:"heading",level:s[1].length,text:s[2].trim(),line:n}),n++;continue}if(/^\s*<!--.*-->\s*$/.test(o)){n++;continue}if(/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(o)){a.push({type:"hr"}),n++;continue}if(/^\s*\|.*\|\s*$/.test(o)&&n+1<e.length&&/^\s*\|?[\s:|-]+\|?\s*$/.test(e[n+1])&&e[n+1].includes("-")){let c=d=>d.trim().replace(/^\||\|$/g,"").split("|").map(f=>f.trim()),l=c(o),m=[];for(n+=2;n<e.length&&/^\s*\|.*\|\s*$/.test(e[n]);)m.push(c(e[n++]));a.push({type:"table",head:l,rows:m});continue}if(/^\s*>/.test(o)){let c=[];for(;n<e.length&&/^\s*>/.test(e[n]);)c.push(e[n++].replace(/^\s*>\s?/,""));a.push({type:"quote",text:c.join(" ")});continue}if(Yt.test(o)){let c=[];for(;n<e.length&&(Yt.test(e[n])||/^\s{2,}\S/.test(e[n])&&c.length);){let l=e[n].match(Yt);l?c.push({indent:Math.floor(l[1].replace(/\t/g,"  ").length/2),ordered:/\d/.test(l[2]),checkbox:l[3]?l[4].toLowerCase()==="x":null,text:l[5],line:n}):c[c.length-1].text+=" "+e[n].trim(),n++}a.push({type:"list",items:c});continue}let r=[];for(;n<e.length&&e[n].trim()&&!Yt.test(e[n])&&!/^(#{1,6})\s/.test(e[n])&&!/^\s*(```|~~~|>|\|)/.test(e[n]);)r.push(e[n++].trim());r.length?a.push({type:"p",text:r.join(" ")}):n++}return a}function Ft(t,{onToggle:e}={}){return t.map((a,n)=>{let o=`b${n}`;switch(a.type){case"heading":return O(`h${Math.min(6,a.level+2)}`,{key:o,className:"at-md-h"},ct(a.text,o));case"p":return O("p",{key:o},ct(a.text,o));case"hr":return O("hr",{key:o});case"code":return O("pre",{key:o},O("code",null,a.text));case"quote":return O("blockquote",{key:o},ct(a.text,o));case"table":return O("div",{key:o,className:"at-md-table"},O("table",null,O("thead",null,O("tr",null,a.head.map((i,s)=>O("th",{key:s},ct(i,`${o}h${s}`))))),O("tbody",null,a.rows.map((i,s)=>O("tr",{key:s},i.map((r,c)=>O("td",{key:c},ct(r,`${o}r${s}${c}`))))))));case"list":{let i=a.items[0]&&a.items[0].ordered;return O(i?"ol":"ul",{key:o,className:"at-md-list"},a.items.map((s,r)=>{let c=s.indent?{marginLeft:`${s.indent*1.25}em`}:void 0;return s.checkbox===null?O("li",{key:r,style:c},ct(s.text,`${o}${r}`)):O("li",{key:r,style:c,className:"at-md-check"+(s.checkbox?" is-done":"")},O("label",null,O("input",{type:"checkbox",checked:s.checkbox,disabled:!e,onChange:l=>e&&e(s.line,l.target.checked)}),O("span",null,ct(s.text,`${o}${r}`))))}))}default:return null}})}function Ee(t,e,a){let n=String(t).split(`
`),o=n[e]&&n[e].match(/^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\](.*)$/);return o?(n[e]=`${o[1]}[${a?"x":" "}]${o[3]}`,n.join(`
`)):t}var $e=/^\s*<!--\s*([\w-]+):start\s*-->\s*$/,Vt=/^\s*<!--\s*([\w-]+):end\s*-->\s*$/;function Le(t){let e=String(t||"").replace(/\r\n?/g,`
`).split(`
`),a=e.slice(),n=[];for(let s=0;s<e.length;s++){let r=e[s].match($e);if(!r)continue;let c=s+1;for(;c<e.length&&!(Vt.test(e[c])&&e[c].match(Vt)[1]===r[1]);)c++;if(!(c>=e.length)){n.push({name:r[1],text:e.slice(s+1,c).join(`
`).trim()});for(let l=s;l<=c;l++)a[l]="";s=c}}let o=[],i={title:"",start:0,lines:[]};return a.forEach((s,r)=>{let c=s.match(/^##\s+(.*)$/);c?(o.push(i),i={title:c[1].trim(),start:r+1,lines:[]}):i.lines.push(s)}),o.push(i),{sections:o.filter(s=>s.title||s.lines.join("").trim()).map(s=>({title:s.title,text:s.lines.join(`
`),start:s.start,folded:/^(log|history|activity)$/i.test(s.title)})),managed:n}}function Pe(t){return/dossier|research/i.test(t)?"Research":/state/i.test(t)?"Current state":t.replace(/[-_]+/g," ").replace(/^\w/,e=>e.toUpperCase())}function Ae(t){let e=String(t||"").replace(/\r\n?/g,`
`).split(`
`),a=[],n=[],o=[],i=!1;for(let r=0;r<e.length;r++){let c=e[r].match($e);if(c){let l=r+1;for(;l<e.length&&!(Vt.test(e[l])&&e[l].match(Vt)[1]===c[1]);)l++;if(l<e.length){(i?o:n).push(e.slice(r,l+1).join(`
`)),r=l;continue}}e[r].trim()&&(i=!0),a.push(e[r])}return{editable:a.join(`
`).replace(/\n{3,}/g,`

`).replace(/^\n+/,"").replace(/\s+$/,"")+`
`,top:n,bottom:o}}function Be(t,e,a){let n=[];return e.length&&n.push(e.join(`

`)),n.push(String(t).replace(/\s+$/,"")),a.length&&n.push(a.join(`

`)),`
`+n.filter(o=>o.trim()).join(`

`)+`
`}var ha=["urgent","high","normal","low"],Oe=[["open","Open"],["in-progress","In progress"],["waiting","Waiting"]];function Ie({id:t,narrow:e,onClose:a}){let{store:n,api:o,actions:i,today:s,meta:r}=H(),c=lt(),l=it(),m=g.useCallback(M=>M.byId[t],[t]),d=kt(n,m),[f,w]=g.useState(null),[v,D]=g.useState(!1),[y,b]=g.useState(!1),h=g.useCallback(()=>(w(null),b(!1),n.loadTask(t).catch(M=>w(M))),[t,n]);g.useEffect(()=>{D(!1),h()},[t]),g.useEffect(()=>{let M=q=>{q.key==="Escape"&&!q.defaultPrevented&&!v&&a()};return window.addEventListener("keydown",M),()=>window.removeEventListener("keydown",M)},[a,v]);let S=async(M,q)=>{try{await n.mutate(t,q||M,()=>o.patch(t,{...M,expected_revision:d&&d.revision}))}catch(P){(P.code==="stale_revision"||P.code==="retry")&&b(!0),c(X(P),{tone:"error"})}},T=async M=>{let q=await o.putBody(t,M,d.revision);return n.put(q.task),q.task};if(!d&&f)return g.createElement(ae,{narrow:e,onClose:a},g.createElement("div",{className:"at-panel-empty"},g.createElement($,{name:"alert",size:20}),g.createElement("p",null,X(f)),g.createElement(j,{onClick:h},"Try again")));if(!d)return g.createElement(ae,{narrow:e,onClose:a},g.createElement("div",{className:"at-panel-empty"},g.createElement(Z,{size:18})));let E=W(d),I=d.due&&d.scheduled&&d.due!==d.scheduled,L=M=>l.open(M.currentTarget,q=>g.createElement(St,{value:E,today:s,close:q,onPick:P=>i.move(d,P)}),{width:300}),B=M=>l.open(M.currentTarget,q=>g.createElement(St,{value:d.due,today:s,close:q,onPick:P=>S({due:P,keep_separate:!0},{due:P})}),{width:300}),ut=M=>l.open(M.currentTarget,q=>g.createElement(at,{close:q,items:(r.areas||[]).map(P=>({label:P,icon:P===d.area?"check":void 0,run:()=>S({area:P})}))}),{width:200}),R=M=>l.open(M.currentTarget,q=>g.createElement(at,{close:q,items:ha.map(P=>({label:P[0].toUpperCase()+P.slice(1),icon:P===(d.priority||"normal")?"check":void 0,run:()=>S({priority:P})}))}),{width:180}),G=M=>l.open(M.currentTarget,q=>g.createElement(at,{close:q,items:Oe.map(([P,wt])=>({label:wt,icon:P===d.status?"check":void 0,run:()=>S({status:P,...P==="waiting"?{reason:"Marked waiting from the Tasks UI"}:{}})}))}),{width:180});return g.createElement(ae,{narrow:e,onClose:a,actions:g.createElement(g.Fragment,null,d.loading?g.createElement(Z,null):null,g.createElement(J,{icon:"refresh",label:"Reload",onClick:h}))},y?g.createElement("div",{className:"at-banner at-tone-late"},g.createElement($,{name:"alert",size:15}),g.createElement("span",{className:"at-flex"},"This task changed somewhere else."),g.createElement(j,{size:"sm",onClick:h},"Reload")):null,g.createElement("div",{className:"at-panel-titlerow"},g.createElement(It,{checked:nt(d),onChange:()=>i.toggle(d),label:nt(d)?"Mark not done":"Mark done",size:"lg"}),g.createElement(xa,{value:d.title,done:nt(d),onSave:M=>S({title:M})})),g.createElement("div",{className:"at-fields"},g.createElement("button",{type:"button",className:z("at-field",E&&E<s&&!nt(d)&&"is-late"),onClick:L},g.createElement($,{name:"cal",size:15}),g.createElement("span",null,E?F(E,s):"No date")),g.createElement("button",{type:"button",className:"at-field",onClick:ut},g.createElement(st,{area:d.area}),g.createElement("span",null,d.area||"No area")),g.createElement("button",{type:"button",className:z("at-field",(d.priority==="high"||d.priority==="urgent")&&"is-high"),onClick:R},g.createElement("span",{className:"at-prio-glyph","data-p":d.priority||"normal"}),g.createElement("span",null,(d.priority||"normal").replace(/^\w/,M=>M.toUpperCase()))),d.status==="waiting"||d.status==="in-progress"?g.createElement("button",{type:"button",className:"at-field",onClick:G},g.createElement("span",null,d.status==="waiting"?"Waiting":"In progress")):null,I?g.createElement("button",{type:"button",className:"at-field",onClick:B},g.createElement("span",{className:"at-muted"},"Due"),g.createElement("span",null,F(d.due,s))):null),g.createElement(va,{value:d.summary||"",onSave:M=>S({summary:M})}),d.research==="pending"||d.research==="running"?g.createElement("div",{className:"at-research-note"},g.createElement($,{name:"spark",size:14})," Hermes is researching this task. Findings will appear here."):null,d.body===void 0?g.createElement("div",{className:"at-panel-loading"},g.createElement(Z,null)):v?g.createElement(ya,{task:d,onSave:T,onDone:()=>D(!1),onStale:()=>b(!0)}):g.createElement(ba,{task:d,onEdit:()=>D(!0),onToggle:async(M,q)=>{try{await T(Ee(d.body,M,q))}catch(P){P.code==="stale_revision"&&b(!0),c(X(P),{tone:"error"})}}}),g.createElement(pt,{title:"More",className:"at-more"},g.createElement("div",{className:"at-more-grid"},g.createElement("span",{className:"at-muted"},"Status"),g.createElement("button",{type:"button",className:"at-field is-plain",onClick:G},(Oe.find(([M])=>M===d.status)||[0,d.status])[1]),g.createElement("span",{className:"at-muted"},"Due date"),g.createElement("span",null,I?g.createElement("button",{type:"button",className:"at-field is-plain",onClick:B},gt(d.due,s)):g.createElement("button",{type:"button",className:"at-link",onClick:B},"Set a separate due date")),d.completed?g.createElement(g.Fragment,null,g.createElement("span",{className:"at-muted"},"Completed"),g.createElement("span",null,gt(d.completed,s))):null,d.project?g.createElement(g.Fragment,null,g.createElement("span",{className:"at-muted"},"Project"),g.createElement("span",{className:"at-mono"},String(d.project).replace(/^\[\[|\]\]$/g,"").split("/").slice(-2,-1)[0]||d.project)):null,g.createElement("span",{className:"at-muted"},"File"),g.createElement("span",{className:"at-mono at-break"},d.path))))}function ae({narrow:t,onClose:e,actions:a,children:n}){return g.createElement("aside",{className:z("at-panel",t?"is-sheet":"is-side"),"aria-label":"Task"},g.createElement("div",{className:"at-panel-bar"},t?g.createElement("span",{className:"at-grabber"}):null,g.createElement("span",{className:"at-flex"}),a,g.createElement(J,{icon:"x",label:"Close",onClick:e})),g.createElement("div",{className:"at-panel-body at-scroll"},n))}function xa({value:t,done:e,onSave:a}){let[n,o]=g.useState(t),i=g.useRef(null);g.useEffect(()=>o(t),[t]),g.useLayoutEffect(()=>{let r=i.current;r&&(r.style.height="auto",r.style.height=r.scrollHeight+"px")},[n]);let s=()=>{let r=n.replace(/\s+/g," ").trim();r&&r!==t?a(r):o(t)};return g.createElement("textarea",{ref:i,rows:1,className:z("at-title-input",e&&"is-done"),value:n,"aria-label":"Title",onChange:r=>o(r.target.value),onBlur:s,onKeyDown:r=>{r.key==="Enter"&&(r.preventDefault(),r.currentTarget.blur()),r.key==="Escape"&&(r.preventDefault(),o(t),r.currentTarget.blur())}})}function va({value:t,onSave:e}){let[a,n]=g.useState(t),o=g.useRef(null);return g.useEffect(()=>n(t),[t]),g.useLayoutEffect(()=>{let i=o.current;i&&(i.style.height="auto",i.style.height=i.scrollHeight+"px")},[a]),g.createElement("textarea",{ref:o,rows:1,className:"at-summary-input",value:a,placeholder:"Add a short summary","aria-label":"Summary",onChange:i=>n(i.target.value),onBlur:()=>{let i=a.trim();i!==t.trim()&&e(i)},onKeyDown:i=>{i.key==="Escape"&&(i.preventDefault(),n(t),i.currentTarget.blur())}})}function ba({task:t,onEdit:e,onToggle:a}){let{sections:n,managed:o}=g.useMemo(()=>Le(t.body||""),[t.body]),i=o.find(d=>/current-state/.test(d.name)),s=o.filter(d=>d!==i),r=i?{title:"Current state",text:i.text,start:0,managed:!0}:n.find(d=>/^current state$/i.test(d.title)),c=n.filter(d=>d!==r),l=d=>Ft(jt(d.text),{onToggle:(f,w)=>a(d.start+f,w)}),m=n.some(d=>d.text.trim());return g.createElement("div",{className:"at-body"},g.createElement("div",{className:"at-body-bar"},g.createElement("span",{className:"at-body-label"},"Notes"),g.createElement("span",{className:"at-flex"}),g.createElement(j,{size:"sm",variant:"ghost",icon:"edit",onClick:e},"Edit")),r&&r.text.trim()?g.createElement("div",{className:"at-state"},g.createElement("div",{className:"at-state-label"},"Current state"),g.createElement("div",{className:"at-md"},r.managed?Ft(jt(r.text)):l(r))):null,!m&&!s.length?g.createElement("button",{type:"button",className:"at-empty-notes",onClick:e},"Add notes"):null,c.map((d,f)=>d.folded?g.createElement(pt,{key:f,title:d.title,className:"at-fold"},g.createElement("div",{className:"at-md"},l(d))):g.createElement("div",{key:f,className:"at-section"},d.title&&!/^notes$/i.test(d.title)?g.createElement("h3",{className:"at-section-title"},d.title):null,g.createElement("div",{className:"at-md"},l(d)))),s.map((d,f)=>g.createElement(pt,{key:`m${f}`,title:Pe(d.name),className:"at-fold",right:g.createElement($,{name:"spark",size:13})},g.createElement("div",{className:"at-md"},Ft(jt(d.text))))))}function ya({task:t,onSave:e,onDone:a,onStale:n}){let o=lt(),i=g.useMemo(()=>Ae(t.body||""),[]),[s,r]=g.useState(i.editable),[c,l]=g.useState("saved"),m=g.useRef(s),d=g.useRef(i.editable),f=g.useRef(null),w=g.useRef(null),v=g.useCallback(async()=>{clearTimeout(f.current);let b=m.current;if(b===d.current)return l("saved"),!0;l("saving");try{return await e(Be(b,i.top,i.bottom)),d.current=b,l(m.current===b?"saved":"dirty"),!0}catch(h){return l("error"),h.code==="stale_revision"&&n(),o(X(h),{tone:"error"}),!1}},[e,n,o,i]);g.useEffect(()=>{w.current&&w.current.focus()},[]),g.useEffect(()=>()=>clearTimeout(f.current),[]);let D=b=>{r(b),m.current=b,l("dirty"),clearTimeout(f.current),f.current=setTimeout(v,1500)},y=async()=>{await v()&&a()};return g.createElement("div",{className:"at-body is-editing"},g.createElement("div",{className:"at-body-bar"},g.createElement("span",{className:"at-body-label"},"Notes"),g.createElement("span",{className:z("at-save",`is-${c}`)},c==="saving"?"Saving\u2026":c==="saved"?"Saved":c==="error"?"Not saved":"Editing"),g.createElement("span",{className:"at-flex"}),c==="error"?g.createElement(j,{size:"sm",onClick:v},"Retry"):null,g.createElement(j,{size:"sm",variant:"primary",onClick:y},"Done")),g.createElement("textarea",{ref:w,className:"at-editor",value:s,spellCheck:!0,onChange:b=>D(b.target.value),onKeyDown:b=>{(b.metaKey||b.ctrlKey)&&b.key==="s"&&(b.preventDefault(),v()),b.key==="Escape"&&(b.preventDefault(),y())}}),g.createElement("div",{className:"at-editor-hint"},"Markdown. Saves as you type.",i.top.length+i.bottom.length?" Research added by Hermes is kept as it is.":""))}import p from"react";var He=t=>(t||[]).reduce((e,a)=>e+(a.proposals||[]).filter(n=>n.state==="pending"&&!n.expired).length,0),qe=t=>String(t||"").replace(/[-_]+/g," ").replace(/\b\w/g,e=>e.toUpperCase());function oe(t){let e=t.time,a=typeof e=="number"?new Date(e*(e<1e12?1e3:1)):new Date(e);return Number.isNaN(a.getTime())?"":a.toLocaleTimeString(void 0,{hour:"numeric",minute:"2-digit"})}function Ue(t){let e=t.coverage||[];if(!e.length)return t.sources_checked&&t.sources_checked.length?`${t.sources_checked.length} sources`:"";let a=e.filter(n=>n.status==="complete").length;return a===e.length?`${a} ${a===1?"source":"sources"} checked`:`${a} of ${e.length} sources checked`}function Ye({runs:t,error:e,loading:a,reload:n}){let{today:o}=H(),[i,s]=p.useState("waiting");if(e&&e.code==="not_found")return p.createElement(ne,{icon:"inbox",title:"Discovery is not available yet",text:"This version of Alchemy Task has no discovery runs to show. Update the plugin to review discovery here."});if(!t&&a)return p.createElement("div",{className:"at-loading"},p.createElement(Z,{size:18}));if(e&&!t)return p.createElement(ne,{icon:"alert",title:"Could not load discovery",text:X(e),action:p.createElement(j,{onClick:n},"Try again")});let r=t||[];if(!r.length)return p.createElement(ne,{icon:"spark",title:"No discovery runs yet",text:p.createElement(p.Fragment,null,"Discovery reads the sources you choose and proposes tasks. To start one, ask Hermes:",p.createElement("br",null),p.createElement("q",null,"Set up a daily digest from my email and Slack at 7 AM."))});let c=d=>(d.summary?d.summary.pending:(d.proposals||[]).filter(f=>f.state==="pending").length)>0||(d.conflicts||[]).length||(d.failures||[]).length,l=i==="waiting"?r.filter(c):r,m=r[0];return p.createElement("div",{className:"at-scroll at-disco"},p.createElement("div",{className:"at-disco-inner"},p.createElement("div",{className:"at-disco-bar"},p.createElement("h1",{className:"at-period"},"Discovery"),p.createElement("span",{className:"at-flex"}),p.createElement(Ut,{label:"Show",value:i,onChange:s,options:[{value:"waiting",label:"Waiting for you"},{value:"all",label:"All runs"}]}),p.createElement(J,{icon:"refresh",label:"Refresh",onClick:n})),l.length?null:p.createElement("div",{className:"at-caughtup"},p.createElement($,{name:"check",size:18}),p.createElement("div",null,p.createElement("div",{className:"at-caughtup-title"},"All caught up"),p.createElement("div",{className:"at-muted"},"Last run: ",qe(m.stream),", ",F(m.day,o)," ",oe(m)))),l.map(d=>p.createElement(ka,{key:d.run_id,run:d,filter:i,reload:n}))))}function ne({icon:t,title:e,text:a,action:n}){return p.createElement("div",{className:"at-scroll at-disco"},p.createElement("div",{className:"at-emptystate"},p.createElement("span",{className:"at-emptystate-icon"},p.createElement($,{name:t,size:22})),p.createElement("h2",null,e),p.createElement("p",null,a),n))}function ka({run:t,filter:e,reload:a}){let{today:n}=H(),o=t.proposals||[],i=e==="waiting"?o.filter(l=>l.state==="pending"):o,s=(t.outcomes||[]).filter(l=>l.status!=="noop"),r=[...(t.conflicts||[]).map(l=>({...l,kind:"conflict"})),...t.failures||[]],c=t.mode&&t.mode!=="production";return p.createElement("article",{className:"at-run"},p.createElement("header",{className:"at-run-head"},p.createElement("div",null,p.createElement("div",{className:"at-run-title"},qe(t.stream)),p.createElement("div",{className:"at-run-sub"},p.createElement("span",null,F(t.day,n),oe(t)?` \xB7 ${oe(t)}`:""),Ue(t)?p.createElement("span",{className:z(t.degraded&&"is-late")},Ue(t)):null,c?p.createElement("span",{className:"at-badge"},"Test run"):null)),p.createElement("span",{className:"at-flex"}),t.summary&&t.summary.pending?p.createElement("span",{className:"at-count is-accent"},t.summary.pending," waiting"):null),i.length?p.createElement("div",{className:"at-proposals"},i.map(l=>p.createElement(Da,{key:l.proposal_id,p:l,run:t,reload:a,readOnly:c}))):e==="all"&&!o.length?p.createElement("div",{className:"at-run-none"},"No new proposals in this run."):null,s.length?p.createElement(pt,{title:"Updated automatically",count:s.length,className:"at-run-fold"},s.map(l=>p.createElement(Na,{key:l.unit_id,o:l,run:t,reload:a}))):null,r.length?p.createElement(pt,{title:"Needs attention",count:r.length,tone:"late",className:"at-run-fold",defaultOpen:!0},r.map((l,m)=>p.createElement("div",{key:m,className:"at-attn"},p.createElement($,{name:"alert",size:14}),p.createElement("div",null,p.createElement("div",{className:"at-attn-title"},l.title||(l.kind==="conflict"?"Several tasks match one item":"Research follow-up")),p.createElement("div",{className:"at-muted"},l.kind==="conflict"?"Nothing was changed. Ask Hermes which task this belongs to.":l.reason))))):null,p.createElement(pt,{title:"Run details",className:"at-run-fold is-quiet"},p.createElement("div",{className:"at-details"},(t.coverage||[]).map((l,m)=>p.createElement("div",{key:m,className:"at-detail-row"},p.createElement("span",{className:z("at-statusdot",l.status==="complete"?"is-ok":"is-late")}),p.createElement("span",{className:"at-flex"},l.source_key||l.source||"Source"),p.createElement("span",{className:"at-muted"},l.status==="complete"?"Checked":l.status||"Unknown"))),p.createElement("div",{className:"at-detail-row"},p.createElement("span",{className:"at-muted"},"Run"),p.createElement("span",{className:"at-flex"}),p.createElement("span",{className:"at-mono"},String(t.run_id).slice(0,12))),t.delivery&&t.delivery.state?p.createElement("div",{className:"at-detail-row"},p.createElement("span",{className:"at-muted"},"Digest"),p.createElement("span",{className:"at-flex"}),p.createElement("span",null,wa(t.delivery.state))):null)))}var wa=t=>({delivered:"Sent",host_pending:"Sent by Hermes",prepared:"Prepared",not_prepared:"Not sent",unknown:"Unknown",inflight:"Sending"})[t]||t;function Na({o:t,run:e,reload:a}){let{actions:n,api:o}=H(),i=lt(),[s,r]=p.useState(!1),c=async()=>{r(!0);try{await o.resume(e.run_id,t.unit_id),await a()}catch(m){i(X(m),{tone:"error"})}r(!1)},l=t.status==="complete";return p.createElement("div",{className:"at-outcome"},p.createElement("span",{className:z("at-statusdot",l?"is-ok":"is-late")}),p.createElement("button",{type:"button",className:"at-outcome-title",onClick:()=>t.task_id&&n.open(t.task_id)},t.title),p.createElement("span",{className:"at-flex"}),l?p.createElement("span",{className:"at-muted"},"Updated"):t.resume_action?p.createElement(j,{size:"sm",onClick:c,disabled:s},s?"Finishing\u2026":"Finish update"):p.createElement("span",{className:"at-muted"},t.status))}function Da({p:t,run:e,reload:a,readOnly:n}){let{api:o,actions:i,today:s,meta:r,store:c}=H(),l=lt(),m=it(),d=t.targets||[],f=t.kind==="selection"||d.length>1,[w,v]=p.useState(t.kind==="new"||!d.length?"create":"update"),[D,y]=p.useState(d.length===1?d[0].task_id:null),b=(r.streams||{})[e.stream]||[],[h,S]=p.useState(t.due||t.due_hint||s),[T,E]=p.useState(t.area||(b.length===1?b[0]:r.default_area)||""),[I,L]=p.useState(null),[B,ut]=p.useState(!1);if(t.state==="approved"||t.state==="complete"){let C=t.result||{},Y=t.state==="complete"||C.state==="complete";return p.createElement("div",{className:"at-prop is-resolved"},p.createElement("span",{className:z("at-statusdot",Y?"is-ok":"is-late")}),p.createElement("span",{className:"at-prop-resolved"},C.operation==="updated"?"Updated":"Created"," ",p.createElement("button",{type:"button",className:"at-linkish",onClick:()=>C.task_id&&i.open(C.task_id)},C.title||t.title)),p.createElement("span",{className:"at-flex"}),Y?p.createElement("span",{className:"at-muted"},t.ref):p.createElement("span",{className:"at-muted"},"Saving\u2026"))}if(t.state==="dismissed"||B)return p.createElement("div",{className:"at-prop is-resolved is-dismissed"},p.createElement("span",{className:"at-prop-resolved"},t.title),p.createElement("span",{className:"at-flex"}),p.createElement("span",{className:"at-muted"},"Dismissed"));let R=async C=>{if(C==="create"&&!T){l("Pick an area first.",{tone:"error"});return}let Y=d.find(mt=>mt.task_id===D);if(C==="update"&&!Y){l("Pick the task to update.",{tone:"error"});return}let xt=C==="create"?{choice:C,due:h,area:T}:{choice:C,target_task_id:Y.task_id,expected_revision:Y.revision};t.expired&&(xt.allow_expired=!0),L(C);try{let _t=(await o.approve(t.proposal_id,xt)).receipt||{};l(C==="create"?"Task created":"Task updated",_t.task_id?{action:{label:"Open",run:()=>i.open(_t.task_id)}}:{}),await a(),c.refresh()}catch(mt){l(X(mt),{tone:"error"}),(mt.code==="already_resolved"||mt.code==="stale_revision")&&a()}L(null)},G=async()=>{L("dismiss");try{await o.dismiss(t.proposal_id),ut(!0),l("Proposal dismissed"),a()}catch(C){l(X(C),{tone:"error"})}L(null)},M=C=>m.open(C.currentTarget,Y=>p.createElement(St,{value:h,today:s,onPick:S,close:Y}),{width:300}),q=C=>m.open(C.currentTarget,Y=>p.createElement(at,{close:Y,items:(r.areas||[]).map(xt=>({label:xt,icon:xt===T?"check":void 0,run:()=>E(xt)}))}),{width:200}),P=[].concat(t.new_information||[]).filter(Boolean),wt=[].concat(t.source_links||[]).filter(Boolean),Ct=t.research_disposition==="uncertain";return p.createElement("div",{className:z("at-prop",t.expired&&"is-expired")},p.createElement("div",{className:"at-prop-head"},p.createElement("span",{className:"at-prop-ref"},t.ref),p.createElement("h3",{className:"at-prop-title"},t.title),p.createElement(J,{icon:"x",label:"Dismiss",className:"at-prop-dismiss",onClick:G,disabled:!!I||n})),t.current_understanding?p.createElement("p",{className:"at-prop-text"},t.current_understanding):null,t.substantive_next_action?p.createElement("div",{className:"at-prop-next"},p.createElement("span",{className:"at-prop-label"},"Next"),p.createElement("span",null,t.substantive_next_action)):null,Ct?p.createElement("div",{className:"at-prop-uncertain"},p.createElement($,{name:"alert",size:14}),p.createElement("span",null,[].concat(t.uncertainty||[]).join(" ")||"Hermes was not sure about this one. Check it before you add it.")):null,wt.length?p.createElement("div",{className:"at-prop-links"},wt.slice(0,4).map((C,Y)=>p.createElement(Sa,{key:Y,href:C}))):null,d.length?p.createElement("div",{className:z("at-prop-targets",w==="create"&&"is-muted")},p.createElement("div",{className:"at-prop-label"},f?"Could update one of these tasks":"May update an existing task"),d.map(C=>p.createElement("label",{key:C.task_id,className:z("at-target",D===C.task_id&&w==="update"&&"is-on")},f?p.createElement("input",{type:"radio",name:t.proposal_id,checked:D===C.task_id&&w==="update",onChange:()=>{y(C.task_id),v("update")}}):p.createElement($,{name:"arrowR",size:14}),p.createElement("span",{className:"at-target-main"},p.createElement("span",{className:"at-target-title"},C.title),p.createElement("span",{className:"at-target-meta"},C.area?p.createElement(p.Fragment,null,p.createElement(st,{area:C.area}),C.area):null,W(C)?p.createElement("span",null,F(W(C),s)):null,C.status&&C.status!=="open"?p.createElement("span",null,C.status):null)),p.createElement("button",{type:"button",className:"at-link",onClick:Y=>{Y.preventDefault(),i.open(C.task_id)}},"Open"))),P.length?p.createElement("div",{className:"at-prop-addition"},p.createElement("span",{className:"at-prop-label"},"Would add"),p.createElement("ul",null,P.map((C,Y)=>p.createElement("li",{key:Y},C)))):null):P.length?p.createElement("ul",{className:"at-prop-list"},P.map((C,Y)=>p.createElement("li",{key:Y},C))):null,p.createElement("div",{className:"at-prop-actions"},w==="create"?p.createElement(p.Fragment,null,p.createElement("button",{type:"button",className:"at-field",onClick:M},p.createElement($,{name:"cal",size:14}),p.createElement("span",null,F(h,s))),p.createElement("button",{type:"button",className:z("at-field",!T&&"is-late"),onClick:q},p.createElement(st,{area:T}),p.createElement("span",null,T||"Pick area")),p.createElement("span",{className:"at-flex"}),d.length?p.createElement(j,{variant:"ghost",size:"sm",onClick:()=>v("update"),disabled:!!I},"Update instead"):null,p.createElement(j,{variant:"primary",size:"sm",icon:"plus",onClick:()=>R("create"),disabled:!!I||n},I==="create"?"Creating\u2026":"Create task")):p.createElement(p.Fragment,null,p.createElement(j,{variant:"ghost",size:"sm",onClick:()=>v("create"),disabled:!!I},"Create new instead"),p.createElement("span",{className:"at-flex"}),p.createElement(j,{variant:"primary",size:"sm",icon:"check",onClick:()=>R("update"),disabled:!!I||!D||n},I==="update"?"Updating\u2026":f?"Update selected":"Update task"))),t.expired?p.createElement("div",{className:"at-prop-foot at-muted"},"Expired ",F(t.expires,s).toLowerCase(),". You can still add it."):null)}function Sa({href:t}){let e=t;try{let n=new URL(t).host.replace(/^www\./,"");e=/slack/.test(n)?"Slack":/mail\.google|gmail/.test(n)?"Gmail":/notion/.test(n)?"Notion":/github/.test(n)?"GitHub":n}catch{}return p.createElement("a",{className:"at-srclink",href:t,target:"_blank",rel:"noreferrer noopener"},p.createElement($,{name:"link",size:12}),e)}import x from"react";var Ve=[["daily","Every day"],["weekdays","Weekdays"],["every 4 hours","Every 4 hours"],["every 3 hours","Every 3 hours"],["every 2 hours","Every 2 hours"],["hourly","Every hour"]],re=t=>t==="daily"||t==="weekdays";function je(t){let e=String(t||"").trim().toLowerCase().match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/);if(!e)return"07:00";let a=Number(e[1])%24;return e[3]==="pm"&&a<12&&(a+=12),e[3]==="am"&&a===12&&(a=0),`${String(a).padStart(2,"0")}:${e[2]||"00"}`}function Ca(t){let[e,a]=t.split(":").map(Number);return`${(e+11)%12+1}:${String(a).padStart(2,"0")} ${e<12?"AM":"PM"}`}function se({onClose:t,inline:e,narrow:a}){let{api:n}=H(),[o,i]=x.useState(null),[s,r]=x.useState(null),c=x.useCallback(()=>(r(null),n.settings().then(i,r)),[n]);x.useEffect(()=>{c()},[c]);let l=o?x.createElement(za,{data:o,reload:c}):s?x.createElement("div",{className:"at-panel-empty"},x.createElement($,{name:"alert",size:20}),x.createElement("p",null,X(s)),x.createElement(j,{onClick:c},"Try again")):x.createElement("div",{className:"at-panel-empty"},x.createElement(Z,{size:18}));return e?x.createElement("div",{className:"at-settings-inline"},l):x.createElement("aside",{className:z("at-panel",a?"is-sheet":"is-side","at-settings"),"aria-label":"Settings"},x.createElement("div",{className:"at-panel-bar"},x.createElement("span",{className:"at-panel-heading"},"Settings"),x.createElement("span",{className:"at-flex"}),x.createElement(J,{icon:"x",label:"Close",onClick:t})),x.createElement("div",{className:"at-panel-body at-scroll"},l))}function za({data:t,reload:e}){let a=t.streams||[],n=t.tasks||{};return x.createElement("div",{className:"at-settings-body"},x.createElement("section",{className:"at-set-sec"},x.createElement("h3",null,"Discovery"),x.createElement("p",{className:"at-muted"},"When each discovery stream reads its sources and proposes tasks."),a.length?a.map(o=>x.createElement(Ta,{key:o.name,s:o,reload:e})):x.createElement("div",{className:"at-set-empty"},"No streams yet. Ask Hermes: ",x.createElement("q",null,"Set up a daily digest from my email at 7 AM."))),x.createElement("section",{className:"at-set-sec"},x.createElement("h3",null,"Tasks"),x.createElement(_a,{t:n,reload:e})),x.createElement("section",{className:"at-set-sec"},x.createElement("h3",null,"Sync and storage"),x.createElement("div",{className:"at-set-grid"},x.createElement("span",{className:"at-muted"},"Workspace"),x.createElement("span",{className:"at-mono at-break"},n.workspace_root||"Not set up"),x.createElement("span",{className:"at-muted"},"Time zone"),x.createElement("span",null,n.timezone||"Hermes default"),t.sync&&t.sync.git?x.createElement(x.Fragment,null,x.createElement("span",{className:"at-muted"},"Git"),x.createElement("span",null,t.sync.git)):null,t.sync&&t.sync.reminders?x.createElement(x.Fragment,null,x.createElement("span",{className:"at-muted"},"iOS Reminders"),x.createElement("span",null,t.sync.reminders)):null),x.createElement("p",{className:"at-muted at-set-hint"},"To change sources, accounts or areas, ask Hermes in chat, for example ",x.createElement("q",null,"add my team Slack channel to the work digest"),".")))}function Ta({s:t,reload:e}){let{api:a}=H(),n=lt(),o=it(),[i,s]=x.useState(t.frequency||"daily"),[r,c]=x.useState(je(t.time||"7 AM")),[l,m]=x.useState(null),d=i!==(t.frequency||"daily")||re(i)&&r!==je(t.time||"7 AM"),f=async()=>{m("save");try{let y=await a.patchStream(t.name,re(i)?{frequency:i,time:Ca(r)}:{frequency:i});n(y.message||"Schedule updated"),await e()}catch(y){n(X(y),{tone:"error"})}m(null)},w=async()=>{m("run");try{let y=await a.runStream(t.name);n(y.message||"Discovery run started")}catch(y){n(X(y),{tone:"error"})}m(null)},v=y=>o.open(y.currentTarget,b=>x.createElement(at,{close:b,items:Ve.map(([h,S])=>({label:S,icon:h===i?"check":void 0,run:()=>s(h)}))}),{width:200}),D=t.setup_blocked_reason||(t.activation_state&&!/active|ok|ready/i.test(t.activation_state)?t.activation_state:"");return x.createElement("div",{className:"at-stream"},x.createElement("div",{className:"at-stream-head"},x.createElement("div",null,x.createElement("div",{className:"at-stream-name"},String(t.name).replace(/\b\w/g,y=>y.toUpperCase())),x.createElement("div",{className:"at-muted"},(t.areas||[]).map(y=>x.createElement("span",{key:y,className:"at-inline-area"},x.createElement(st,{area:y}),y)),t.last_run?x.createElement("span",null," \xB7 last ran ",Ma(t.last_run)):null)),x.createElement("span",{className:"at-flex"}),x.createElement(j,{size:"sm",variant:"ghost",icon:"play",onClick:w,disabled:!!l},l==="run"?"Starting\u2026":"Run now")),x.createElement("div",{className:"at-stream-sched"},x.createElement("button",{type:"button",className:"at-field",onClick:v},x.createElement($,{name:"clock",size:14}),x.createElement("span",null,(Ve.find(([y])=>y===i)||[0,i])[1]),x.createElement($,{name:"chevD",size:13})),re(i)?x.createElement("label",{className:"at-field at-timefield"},x.createElement("span",{className:"at-muted"},"at"),x.createElement("input",{type:"time",value:r,step:300,onChange:y=>c(y.target.value||r)})):null,t.timezone?x.createElement("span",{className:"at-muted at-tz"},t.timezone.replace(/_/g," ")):null,x.createElement("span",{className:"at-flex"}),d?x.createElement(j,{size:"sm",variant:"primary",onClick:f,disabled:!!l},l==="save"?"Saving\u2026":"Save"):null),(t.sources||[]).length?x.createElement("div",{className:"at-stream-sources"},(t.sources||[]).map(y=>x.createElement("span",{key:y.name,className:"at-chip",title:y.scope},y.name))):null,D?x.createElement("div",{className:"at-banner at-tone-late"},x.createElement($,{name:"alert",size:14}),x.createElement("span",null,D)):null)}function Ma(t){let e=typeof t=="number"?new Date(t*(t<1e12?1e3:1)):new Date(t);if(Number.isNaN(e.getTime()))return"";let a=Math.round((Date.now()-e.getTime())/6e4);return a<60?`${Math.max(1,a)} min ago`:a<1440?`${Math.round(a/60)} h ago`:e.toLocaleDateString(void 0,{month:"short",day:"numeric"})}function _a({t,reload:e}){let{api:a,meta:n}=H(),o=lt(),i=it(),s=async c=>{try{await a.patchTaskSettings(c),o("Saved"),await e()}catch(l){o(X(l),{tone:"error"})}};return x.createElement("div",{className:"at-set-grid"},x.createElement("span",{className:"at-muted"},"Default area"),x.createElement("span",null,x.createElement("button",{type:"button",className:"at-field",onClick:c=>i.open(c.currentTarget,l=>x.createElement(at,{close:l,items:(n.areas||[]).map(m=>({label:m,icon:m===t.default_area?"check":void 0,run:()=>s({default_area:m})}))}),{width:200})},x.createElement(st,{area:t.default_area}),x.createElement("span",null,t.default_area||"None"),x.createElement($,{name:"chevD",size:13}))),x.createElement("span",{className:"at-muted"},"Research new tasks"),x.createElement("span",null,x.createElement("button",{type:"button",role:"switch","aria-checked":!!t.research_by_default,className:z("at-switch",t.research_by_default&&"is-on"),onClick:()=>s({research_by_default:!t.research_by_default})},x.createElement("i",null))))}var Ea=720,$a=3e4;function ie(t){return N.createElement(Ce,null,N.createElement(La,{...t}))}function La({transport:t,host:e,initialView:a,settingsOnly:n}){let o=t,i=lt(),s=N.useRef(null),c=ke(s)<Ea,l=N.useMemo(()=>be(o),[o]),m=kt(l,Pa),d=kt(l,Aa),[f,w]=N.useState(null),[v,D]=N.useState(null),[y,b]=N.useState(a==="discovery"?"discovery":"tasks"),[h,S]=N.useState(a==="settings"),[T,E]=N.useState(null),[I,L]=ye("prefs",{view:null,area:"",hideDone:!1}),B=I,ut=N.useCallback(A=>L(U=>({...U,...A})),[L]),[R,G]=N.useState(null),[M,q]=N.useState(null),[P,wt]=N.useState(!1),Ct=N.useCallback(()=>o.meta().then(A=>{w(A),D(null),l.setToday(A.today)},D),[o,l]),C=N.useCallback(async()=>{wt(!0);try{let A=await o.runs();G(A.runs||[]),q(null)}catch(A){q(A)}wt(!1)},[o]);N.useEffect(()=>{Ct(),C()},[Ct,C]),N.useEffect(()=>{let A=()=>{document.visibilityState==="visible"&&(Ct(),l.refresh(),C())},U=setInterval(A,$a);return window.addEventListener("focus",A),()=>{clearInterval(U),window.removeEventListener("focus",A)}},[Ct,C,l]),N.useEffect(()=>{let A=U=>{let tt=U.detail;(tt==="discovery"||tt==="tasks")&&b(tt),tt==="settings"&&S(!0)};return window.addEventListener("alchemy-task:open",A),()=>window.removeEventListener("alchemy-task:open",A)},[]);let Y=N.useMemo(()=>{let A=_=>_.status==="done"||_.status==="cancelled",U=_=>i(X(_),{tone:"error"}),tt=_=>l.mutate(_.task_id,{status:"done",completed:l.getState().today},()=>o.complete(_.task_id)),Nt=_=>l.mutate(_.task_id,{status:"open",completed:null},()=>o.reopen(_.task_id)),zt=(_,V,et)=>l.mutate(_.task_id,{scheduled:V,due:et},()=>o.patch(_.task_id,V===et?{date:V}:{scheduled:V,due:et,keep_separate:!0}));return{open:_=>E(_),async toggle(_){try{A(_)?(await Nt(_),i("Marked not done",{undo:()=>tt(_).catch(U)})):(await tt(_),i(`Done: ${_.title}`,{undo:()=>Nt(_).catch(U)}))}catch(V){U(V)}},async move(_,V){let et={scheduled:_.scheduled||null,due:_.due||null};if(!(W(_)===V&&(!_.due||_.due===V)))try{await zt(_,V,V),i(`Moved to ${F(V,l.getState().today)}`,{undo:()=>zt({..._,scheduled:V,due:V},et.scheduled||et.due,et.due||et.scheduled).catch(U)})}catch(Q){U(Q)}},async moveMany(_,V){let et=_.slice(),Q=0;for(let Dt of et)try{await zt(Dt,V,V),Q++}catch(Wt){U(Wt);break}Q&&i(`Moved ${Q} ${Q===1?"task":"tasks"} to ${F(V,l.getState().today).toLowerCase()}`,{undo:async()=>{for(let Dt of et.slice(0,Q))try{await zt({...Dt,scheduled:V,due:V},Dt.scheduled||Dt.due,Dt.due||Dt.scheduled)}catch(Wt){U(Wt);break}}})},async create({title:_,date:V,area:et}){try{let Q=await o.create({title:_,date:V,area:et});return Q.task&&l.put(Q.task),i(Q.task&&Q.task.research==="pending"?"Added. Hermes is researching it.":"Added",{action:Q.task?{label:"Open",run:()=>E(Q.task.task_id)}:void 0}),!0}catch(Q){return U(Q),!1}}}},[o,l,i]),xt=N.useCallback((A,U)=>Y.move(A,U),[Y]),mt=He(R),_t=N.useMemo(()=>({api:o,store:l,meta:f||{},today:m||f&&f.today,prefs:B,setPrefs:ut,actions:Y,selectedId:T,narrow:c,host:e}),[o,l,f,m,B,ut,Y,T,c,e]);N.useLayoutEffect(()=>{let A=s.current;if(!A)return;let U=()=>{let Nt=getComputedStyle(document.documentElement);Nt.getPropertyValue("--color-foreground").trim()||Nt.getPropertyValue("--ui-text-primary").trim()||(A.style.removeProperty("--at-fg"),A.style.setProperty("--at-fg",getComputedStyle(A).color))};U();let tt=new MutationObserver(U);return tt.observe(document.documentElement,{attributes:!0,attributeFilter:["class","style","data-theme"]}),()=>tt.disconnect()},[]);let[de,pe]=N.useState(null);N.useLayoutEffect(()=>{let A=s.current;if(!A||n)return;let U=()=>{let tt=A.parentElement,Nt=tt?tt.getBoundingClientRect().height:0;if(e==="desktop"&&Nt>300){pe(null);return}let zt=A.getBoundingClientRect().top,ce=window.visualViewport&&window.visualViewport.height||window.innerHeight;pe(Math.max(420,Math.round(ce-Math.max(0,zt)-8)))};return U(),window.addEventListener("resize",U),window.visualViewport&&window.visualViewport.addEventListener("resize",U),()=>{window.removeEventListener("resize",U),window.visualViewport&&window.visualViewport.removeEventListener("resize",U)}},[e,n]);let Ke=!f&&v?N.createElement(Fe,{icon:"alert",title:"Alchemy Task is not responding",text:X(v)}):!f||!_t.today?N.createElement("div",{className:"at-loading"},N.createElement(Z,{size:18})):f.configured===!1?N.createElement(Fe,{icon:"list",title:"Set up your tasks",text:N.createElement(N.Fragment,null,"Alchemy Task is installed but not set up yet. In chat, ask Hermes: ",N.createElement("q",null,"Set up my tasks."))}):n?N.createElement(se,{inline:!0,narrow:c}):N.createElement(N.Fragment,null,N.createElement("nav",{className:"at-appbar"},N.createElement("div",{className:"at-tabs",role:"tablist"},N.createElement("button",{type:"button",role:"tab","aria-selected":y==="tasks",className:z("at-tab",y==="tasks"&&"is-on"),onClick:()=>b("tasks")},"Tasks"),N.createElement("button",{type:"button",role:"tab","aria-selected":y==="discovery",className:z("at-tab",y==="discovery"&&"is-on"),onClick:()=>b("discovery")},"Discovery",mt?N.createElement("span",{className:"at-badge-dot"},mt):null)),N.createElement("span",{className:"at-flex"}),d?N.createElement(Z,{size:12}):null,N.createElement(J,{icon:"gear",label:"Settings",className:z(h&&"is-on"),onClick:()=>{E(null),S(A=>!A)}})),N.createElement("div",{className:z("at-main",T&&!c&&"has-panel",h&&!c&&"has-panel")},y==="tasks"?N.createElement(_e,{narrow:c}):N.createElement(Ye,{runs:R,error:M,loading:P,reload:C})),T?N.createElement(Ie,{id:T,narrow:c,onClose:()=>E(null)}):null,h&&!T?N.createElement(se,{narrow:c,onClose:()=>S(!1)}):null);return N.createElement(Zt.Provider,{value:_t},N.createElement("div",{ref:s,className:z("at-root at-vars",c&&"is-narrow",`host-${e}`,n&&"is-settings-only"),style:de?{height:de}:void 0},N.createElement(xe,{onDrop:xt},N.createElement(De,{rootRef:s},Ke))))}var Pa=t=>t.today,Aa=t=>t.loading>0;function Fe({icon:t,title:e,text:a}){return N.createElement("div",{className:"at-emptystate is-full"},N.createElement("span",{className:"at-emptystate-icon"},N.createElement($,{name:t,size:22})),N.createElement("h2",null,e),N.createElement("p",null,a))}var We=`/* Alchemy Task UI. Every color comes from the host theme: the web dashboard's --color-* tokens or the
   desktop app's --ui-* tokens, with neutral fallbacks. Everything is scoped under .at- classes. */

.at-vars {
  --at-fg: var(--color-foreground, var(--ui-text-primary, currentColor));
  --at-fg2: var(--color-text-secondary, var(--ui-text-secondary, color-mix(in srgb, var(--at-fg) 78%, transparent)));
  --at-muted: var(--color-muted-foreground, var(--ui-text-tertiary, color-mix(in srgb, var(--at-fg) 56%, transparent)));
  --at-faint: var(--ui-text-quaternary, color-mix(in srgb, var(--at-fg) 34%, transparent));
  --at-line: var(--color-border, var(--ui-stroke-secondary, color-mix(in srgb, var(--at-fg) 11%, transparent)));
  --at-line-soft: color-mix(in srgb, var(--at-line) 60%, transparent);
  --at-accent: var(--color-primary, var(--ui-accent, #4f6ef7));
  --at-accent-fg: var(--color-primary-foreground, #fff);
  --at-surface: var(--color-popover, var(--ui-bg-elevated, var(--color-card, var(--at-canvas))));
  --at-canvas: var(--color-background, var(--background, var(--ui-bg-editor, transparent)));
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
.at-root :where(*, *::before, *::after) { box-sizing: border-box; }
.at-root :where(button, input, textarea) { font: inherit; color: inherit; }
.at-root :where(h1, h2, h3, p) { margin: 0; }
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
.at-period { font-size: 20px; font-weight: 650; letter-spacing: -0.015em; margin-left: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
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
.at-mcell.is-on .at-mcell-num { background: var(--at-press); box-shadow: inset 0 0 0 1.5px var(--at-fg); }
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
  padding: 9px 9px 9px 16px; border-radius: 12px;
  background: var(--at-surface); color: var(--at-fg); border: 1px solid var(--at-line);
  box-shadow: var(--at-shadow-lg); font-size: 13.5px; font-weight: 500;
  animation: at-toast .24s var(--at-ease);
}
.at-toast span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@keyframes at-toast { from { opacity: 0; transform: translateY(8px) scale(.98); } }
.at-toast.at-tone-error .at-icon { color: var(--at-late); }
.at-toast-act { flex: none; height: 28px; padding: 0 11px; border: 0; border-radius: 7px; cursor: pointer; background: var(--at-soft); color: var(--at-accent); font-weight: 650; font-size: 13px; }
.at-toast-act:hover { background: var(--at-press); }

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
  font-size: 20px; line-height: 1.3; font-weight: 650; letter-spacing: -0.015em;
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
.at-section-title { font-size: 14px; font-weight: 650; margin: 14px 0 4px; }
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
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; line-height: 1.6;
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
.at-disco-bar .at-period { margin-left: 0; }
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
.at-prop-title { flex: 1; margin: 0; font-size: 15px; font-weight: 650; line-height: 1.35; letter-spacing: -0.005em; }
.at-prop-dismiss { margin: -5px -6px 0 0; color: var(--at-faint); }
.at-prop-text { margin: 6px 0 0 36px; color: var(--at-fg2); font-size: 13.5px; }
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
.at-set-hint { margin-top: 12px; line-height: 1.5; }
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
`;var Ge="alchemy-task-ui-styles",An={id:"alchemy-task",name:"Alchemy Task",register(t){if(!document.getElementById(Ge)){let i=document.createElement("style");i.id=Ge,i.textContent=We,document.head.appendChild(i),t.onDispose(()=>i.remove())}let e=ve((i,s,r)=>t.rest(s,r===void 0?{method:i}:{method:i,body:r})),a=null,n=i=>{a=i,Oa.navigate("/alchemy-task"),window.dispatchEvent(new CustomEvent("alchemy-task:open",{detail:i}))},o=()=>le.createElement(ie,{transport:e,host:"desktop",initialView:a});t.registerMany([{id:"page",area:Ia,data:{path:"/alchemy-task"},render:()=>le.createElement(o,null)},{id:"nav",area:Ua,data:{path:"/alchemy-task",label:"Tasks",codicon:"checklist"}},{id:"open-tasks",area:Xe,data:{id:"alchemy-task-open",label:"Open tasks",keywords:["tasks","today","calendar","alchemy"],run:()=>n("tasks")}},{id:"open-discovery",area:Xe,data:{id:"alchemy-task-discovery",label:"Review discovery proposals",keywords:["discovery","digest","proposals","alchemy"],run:()=>n("discovery")}}]),typeof t.registerSettingsPage=="function"&&t.registerSettingsPage({id:"settings",title:"Alchemy Task",icon:"checklist",render:()=>le.createElement(ie,{transport:e,host:"desktop",settingsOnly:!0})})}};export{An as default};
