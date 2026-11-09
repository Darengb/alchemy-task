import de from"react";import{host as Ia,ROUTES_AREA as Oa,SIDEBAR_NAV_AREA as Ua,PALETTE_AREA as Xe}from"@hermes/plugin-sdk";import C from"react";var me=t=>String(t).padStart(2,"0");function Xt(t){return`${t.getUTCFullYear()}-${me(t.getUTCMonth()+1)}-${me(t.getUTCDate())}`}function bt(t){let[e,a,n]=String(t).split("-").map(Number);return new Date(Date.UTC(e,a-1,n))}function X(t,e){let a=bt(t);return a.setUTCDate(a.getUTCDate()+e),Xt(a)}function _t(t,e){let a=bt(t),n=a.getUTCDate();a.setUTCDate(1),a.setUTCMonth(a.getUTCMonth()+e);let o=new Date(Date.UTC(a.getUTCFullYear(),a.getUTCMonth()+1,0)).getUTCDate();return a.setUTCDate(Math.min(n,o)),Xt(a)}var ge=t=>(bt(t).getUTCDay()+6)%7;function zt(t){return X(t,-ge(t))}function Tt(t){return t.slice(0,8)+"01"}function Je(t){let e=bt(Tt(t));return Xt(new Date(Date.UTC(e.getUTCFullYear(),e.getUTCMonth()+1,0)))}function Qe(t,e){return Math.round((bt(e)-bt(t))/864e5)}function At(t,e){let a=[];for(let n=t;n<=e;n=X(n,1))a.push(n);return a}function $t(t){let e=zt(Tt(t)),a=X(zt(Je(t)),6),n=At(e,a),o=[];for(let i=0;i<n.length;i+=7)o.push(n.slice(i,i+7));return o}var vt=(t,e)=>bt(t).toLocaleDateString(void 0,{timeZone:"UTC",...e}),dt=(t,e="short")=>vt(t,{weekday:e}),Bt=(t,e="long")=>vt(t,{month:e}),yt=t=>bt(t).getUTCDate();function Gt(t){return vt(t,{weekday:"long",month:"long",day:"numeric"})}function mt(t,e){let a=!e||t.slice(0,4)===e.slice(0,4);return vt(t,{weekday:"short",month:"short",day:"numeric",...a?{}:{year:"numeric"}})}function W(t,e){if(!t)return"";let a=Qe(e,t);return a===0?"Today":a===1?"Tomorrow":a===-1?"Yesterday":a>1&&a<7?dt(t,"long"):mt(t,e)}function Kt(t,e){let a=(e-ge(t)+7)%7||7;return X(t,a)}function Jt(t,e,a){if(t==="month")return vt(e,{month:"long",...e.slice(0,4)!==a.slice(0,4)?{year:"numeric"}:{}});if(t==="week"){let n=zt(e),o=X(n,6),i=n.slice(0,7)===o.slice(0,7),s=vt(n,{month:"short",day:"numeric"}),r=i?String(yt(o)):vt(o,{month:"short",day:"numeric"});return`${s} \u2013 ${r}`}return W(e,a)==="Today"?"Today":vt(e,{weekday:"long",month:"short",day:"numeric"})}var V=t=>t.scheduled||t.due||null;import rt from"react";var he=rt.createContext(null),It=()=>rt.useContext(he),Ze=380,fe=6;function Qt(t,e){let a=document.elementFromPoint(t,e),n=a&&a.closest("[data-at-drop]");return n?n.getAttribute("data-at-drop"):null}function Re(t){for(let e=t;e&&e!==document.body;e=e.parentElement){let a=getComputedStyle(e);if(/(auto|scroll)/.test(a.overflowY)&&e.scrollHeight>e.clientHeight)return e}return document.scrollingElement}function xe({onDrop:t,children:e}){let[a,n]=rt.useState(null),o=rt.useRef(null),i=rt.useRef(!1),s=rt.useRef(0),r=rt.useRef(null),u=f=>{let D=o.current&&o.current.over;o.current=o.current?{...o.current,...f}:null;let b=o.current;b&&r.current&&(r.current.style.transform=`translate(${b.x+12}px, ${b.y-20}px)`),b&&b.over!==D&&n(b)},l=(f,D)=>{cancelAnimationFrame(s.current);let b=document.elementFromPoint(f,D),T=b&&Re(b);if(!T)return;let z=T===document.scrollingElement?{top:0,bottom:window.innerHeight}:T.getBoundingClientRect(),v=56,N=D<z.top+v?-Math.ceil((z.top+v-D)/4):D>z.bottom-v?Math.ceil((D-(z.bottom-v))/4):0;if(!N)return;let S=()=>{o.current&&(T.scrollTop+=N,s.current=requestAnimationFrame(S))};s.current=requestAnimationFrame(S)},g=(f,D,b)=>{cancelAnimationFrame(s.current);let T=o.current;if(o.current=null,n(null),r.current&&(r.current.remove(),r.current=null),document.documentElement.classList.remove("at-dragging"),!T)return;i.current=!0,setTimeout(()=>{i.current=!1},50);let z=b?null:Qt(f,D);z&&z!==T.from&&t(T.task,z)},d=(f,D,b,T,z)=>{o.current={task:f,from:D,x:b,y:T,over:D,w:z},n(o.current);let v=document.createElement("div");if(v.className="at-drag-ghost at-vars",v.textContent=f.title,v.style.transform=`translate(${b+12}px, ${T-20}px)`,document.body.appendChild(v),r.current=v,document.documentElement.classList.add("at-dragging"),navigator.vibrate)try{navigator.vibrate(8)}catch{}},y=rt.useCallback((f,D)=>({onPointerDown:b=>{if(b.pointerType!=="mouse"||b.button!==0||b.target.closest("button, input, textarea, a, [data-no-drag]"))return;let T=b.clientX,z=b.clientY,v=b.currentTarget.getBoundingClientRect().width,N=L=>{if(!o.current){if(Math.hypot(L.clientX-T,L.clientY-z)<fe)return;d(f,D,L.clientX,L.clientY,v)}u({x:L.clientX,y:L.clientY,over:Qt(L.clientX,L.clientY)}),l(L.clientX,L.clientY)},S=L=>{window.removeEventListener("pointermove",N),window.removeEventListener("pointerup",S),window.removeEventListener("keydown",_),o.current&&g(L.clientX,L.clientY,!1)},_=L=>{L.key==="Escape"&&(S({clientX:-1,clientY:-1}),g(-1,-1,!0))};window.addEventListener("pointermove",N),window.addEventListener("pointerup",S),window.addEventListener("keydown",_)},onTouchStart:b=>{if(b.target.closest("button, input, textarea, a, [data-no-drag]"))return;let T=b.touches[0],z=T.clientX,v=T.clientY,N=b.currentTarget.getBoundingClientRect().width,S={x:z,y:v},_=setTimeout(()=>{_=null,d(f,D,S.x,S.y,N)},Ze),L=B=>{let j=B.touches[0];if(S={x:j.clientX,y:j.clientY},!o.current){_&&Math.hypot(j.clientX-z,j.clientY-v)>fe&&(clearTimeout(_),_=null,nt());return}B.preventDefault(),u({x:j.clientX,y:j.clientY,over:Qt(j.clientX,j.clientY)}),l(j.clientX,j.clientY)},J=B=>{_&&clearTimeout(_),nt(),o.current&&(B.preventDefault(),g(S.x,S.y,B.type==="touchcancel"))},nt=()=>{document.removeEventListener("touchmove",L),document.removeEventListener("touchend",J),document.removeEventListener("touchcancel",J)};document.addEventListener("touchmove",L,{passive:!1}),document.addEventListener("touchend",J),document.addEventListener("touchcancel",J)},onClickCapture:b=>{i.current&&(b.stopPropagation(),b.preventDefault())},onContextMenu:b=>{o.current&&b.preventDefault()}}),[]),k=rt.useMemo(()=>({drag:a,bind:y}),[a,y]);return rt.useEffect(()=>()=>{r.current&&r.current.remove()},[]),rt.createElement(he.Provider,{value:k},e)}var gt=class extends Error{constructor(e,a,n=0){super(a||e),this.code=e||"error",this.status=n}};function ta(t){let e=t&&(t.body||t.responseText||t.message||"");if(e&&typeof e=="object")return e;let a=String(e),n=a.indexOf("{");if(n>=0)try{return JSON.parse(a.slice(n))}catch{}return null}function ea(t){if(t instanceof gt)return t;let e=ta(t),a=e&&(e.error||e.detail),n=t&&t.status||0;return a&&typeof a=="object"?new gt(a.code,a.message,n):typeof a=="string"?new gt(n===404?"not_found":"error",a,n):n===404?new gt("not_found","Not found",404):n===0||/network|failed to fetch|unreachable/i.test(String(t&&t.message))?new gt("offline","Hermes is not reachable right now.",n):new gt("error",t&&t.message||"Something went wrong",n)}var Zt=t=>{let e=Object.entries(t).filter(([,a])=>a!=null&&a!==""&&a!==!1).map(([a,n])=>`${encodeURIComponent(a)}=${encodeURIComponent(n===!0?"1":n)}`);return e.length?`?${e.join("&")}`:""},ot=encodeURIComponent;function ve(t){async function e(a,n,o){let i;try{i=await t(a,n,o)}catch(s){throw ea(s)}if(i&&i.ok===!1){let s=i.error||{};throw new gt(s.code||i.needs||"error",s.message||i.message,200)}return i}return{meta:()=>e("GET","/meta"),tasks:(a,n,{area:o,includeDone:i=!0}={})=>e("GET","/tasks"+Zt({from:a,to:n,area:o,include_done:i})),overdue:({area:a}={})=>e("GET","/overdue"+Zt({area:a})),task:a=>e("GET",`/tasks/${ot(a)}`),patch:(a,n)=>e("PATCH",`/tasks/${ot(a)}`,n),complete:a=>e("POST",`/tasks/${ot(a)}/complete`,{}),reopen:a=>e("POST",`/tasks/${ot(a)}/reopen`,{}),putBody:(a,n,o)=>e("PUT",`/tasks/${ot(a)}/body`,{body:n,expected_revision:o}),create:a=>e("POST","/tasks",a),runs:(a={})=>e("GET","/runs"+Zt(a)),run:a=>e("GET",`/runs/${ot(a)}`),approve:(a,n)=>e("POST",`/proposals/${ot(a)}/approve`,n),dismiss:a=>e("POST",`/proposals/${ot(a)}/dismiss`,{}),resume:(a,n)=>e("POST",`/runs/${ot(a)}/units/${ot(n)}/resume`,{}),settings:()=>e("GET","/settings"),patchStream:(a,n)=>e("PATCH",`/settings/streams/${ot(a)}`,n),runStream:a=>e("POST",`/settings/streams/${ot(a)}/run`,{}),patchTaskSettings:a=>e("PATCH","/settings/tasks",a)}}function F(t){switch(t&&t.code){case"stale_revision":case"retry":return"This task changed somewhere else. Reload it to see the latest version.";case"offline":return"Hermes is not reachable right now. Your change was not saved.";case"needs_due":case"due":return"Pick a date first.";case"needs_area":case"area":return"Pick an area first.";case"already_resolved":return"This proposal was already handled.";case"expired":return"This proposal expired.";case"not_production":return"This was a test run, so it cannot change tasks.";case"not_found":return"It is no longer there. It may have been moved or deleted.";default:return t&&t.message||"Something went wrong."}}import ft from"react";function be(t){let e={byId:{},today:null,loading:0,error:null,version:0},a=new Set,n=new Map,o=new Map,i=()=>{e={...e,version:e.version+1},a.forEach(g=>g())},s=g=>{e={...e,...g},i()};function r(g,d){let y={...e.byId},k=new Set;for(let f of g){if(k.add(f.task_id),n.has(f.task_id))continue;let D=y[f.task_id]||{},b=f.body!==void 0?f.body:D.revision===f.revision?D.body:void 0;y[f.task_id]={...D,...f,body:b}}if(d)for(let[f,D]of Object.entries(y))!k.has(f)&&!n.has(f)&&d(D)&&delete y[f];e={...e,byId:y}}async function u(g){s({loading:e.loading+1});try{return await g}finally{s({loading:Math.max(0,e.loading-1)})}}let l={getState:()=>e,subscribe:g=>(a.add(g),()=>a.delete(g)),setToday:g=>{g!==e.today&&s({today:g})},async loadRange(g,d){o.set(`${g}:${d}`,{from:g,to:d});let y=await u(t.tasks(g,d));return y.today&&(e={...e,today:y.today}),r(y.tasks||[],k=>{let f=V(k);return f&&f>=g&&f<=d}),s({error:null}),y},async loadOverdue(){let g=await u(t.overdue()),d=g.today||e.today;return g.today&&(e={...e,today:g.today}),r(g.tasks||[],y=>{let k=V(y);return y.status!=="done"&&y.status!=="cancelled"&&k&&k<d}),s({error:null}),g},async refresh(){let g=[...o.values()].slice(-4);try{await Promise.all([...g.map(d=>l.loadRange(d.from,d.to)),l.loadOverdue()])}catch(d){s({error:d})}},async loadTask(g){let d=await t.task(g);return r([d.task]),i(),d.task},put(g){r([g]),i()},async mutate(g,d,y){let k=e.byId[g];n.set(g,(n.get(g)||0)+1),k&&d&&(e={...e,byId:{...e.byId,[g]:{...k,...d}}},i());try{let f=await y(),D=(n.get(g)||1)-1;return D?n.set(g,D):n.delete(g),f&&f.task&&(r([f.task]),i()),f}catch(f){let D=(n.get(g)||1)-1;throw D?n.set(g,D):n.delete(g),k&&(e={...e,byId:{...e.byId,[g]:k}},i()),f}}};return l}function kt(t,e){let a=ft.useCallback(()=>e(t.getState()),[t,e]),[n,o]=ft.useState(a);return ft.useEffect(()=>(o(a()),t.subscribe(()=>o(a()))),[t,a]),n}var Rt=ft.createContext(null),H=()=>ft.useContext(Rt);function ye(t,e){let a=`alchemy-task.${t}`,[n,o]=ft.useState(()=>{try{let s=window.localStorage.getItem(a);return s===null?e:JSON.parse(s)}catch{return e}}),i=ft.useCallback(s=>{o(r=>{let u=typeof s=="function"?s(r):s;try{window.localStorage.setItem(a,JSON.stringify(u))}catch{}return u})},[a]);return[n,i]}function ke(t){let[e,a]=ft.useState(()=>typeof window<"u"?window.innerWidth:1200);return ft.useLayoutEffect(()=>{let n=t.current;if(!n)return;a(n.getBoundingClientRect().width);let o=new ResizeObserver(i=>a(i[0].contentRect.width));return o.observe(n),()=>o.disconnect()},[t]),e}import c from"react";import w from"react";var te={check:"M5 12.5l4.2 4.2L19 7",chevL:"M15 18l-6-6 6-6",chevR:"M9 6l6 6-6 6",chevD:"M6 9l6 6 6-6",gear:"M12 15.2a3.2 3.2 0 100-6.4 3.2 3.2 0 000 6.4z M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",x:"M6 6l12 12M18 6L6 18",plus:"M12 5v14M5 12h14",more:"M5 12h.01M12 12h.01M19 12h.01",cal:"M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z",spark:"M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z",link:"M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5",alert:"M12 9v4M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",refresh:"M20 11a8 8 0 10-2.3 5.7M20 5v6h-6",inbox:"M4 13l2.5-7h11L20 13M4 13v5a1 1 0 001 1h14a1 1 0 001-1v-5M4 13h4l1.5 2.5h5L16 13h4",edit:"M4 20h4L19 9l-4-4L4 16v4z M13.5 6.5l4 4",grip:"M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",arrowR:"M5 12h14M13 6l6 6-6 6",undo:"M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 010 11H11",dot:"M12 12h.01",list:"M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",clock:"M12 7v5l3 2 M12 21a9 9 0 100-18 9 9 0 000 18z",play:"M7 5l12 7-12 7z"};function A({name:t,size:e=16,className:a="",strokeWidth:n=1.8}){return w.createElement("svg",{className:"at-icon "+a,width:e,height:e,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:n,strokeLinecap:"round",strokeLinejoin:"round","aria-hidden":"true"},w.createElement("path",{d:te[t]||te.dot}))}var E=(...t)=>t.filter(Boolean).join(" ");function Y({variant:t="default",size:e,icon:a,children:n,className:o,...i}){return w.createElement("button",{type:"button",className:E("at-btn",`at-btn-${t}`,e&&`at-btn-${e}`,o),...i},a?w.createElement(A,{name:a,size:e==="sm"?14:16}):null,n?w.createElement("span",null,n):null)}function G({icon:t,label:e,className:a,size:n=16,...o}){return w.createElement("button",{type:"button",className:E("at-iconbtn",a),"aria-label":e,title:e,...o},w.createElement(A,{name:t,size:n}))}function Ot({checked:t,onChange:e,label:a,size:n="md",tone:o}){return w.createElement("button",{type:"button",role:"checkbox","aria-checked":!!t,"aria-label":a,className:E("at-check",`at-check-${n}`,t&&"is-on",o&&`at-tone-${o}`),"data-no-drag":"",onClick:i=>{i.stopPropagation(),e(!t)}},w.createElement("svg",{viewBox:"0 0 24 24","aria-hidden":"true"},w.createElement("path",{d:te.check})))}function Ut({value:t,options:e,onChange:a,label:n}){return w.createElement("div",{className:"at-seg",role:"tablist","aria-label":n},e.map(o=>w.createElement("button",{key:o.value,type:"button",role:"tab","aria-selected":t===o.value,className:E("at-seg-item",t===o.value&&"is-on"),onClick:()=>a(o.value)},o.label)))}function Z({size:t=14}){return w.createElement("span",{className:"at-spinner",style:{width:t,height:t},"aria-label":"Loading"})}function pt({title:t,count:e,defaultOpen:a=!1,tone:n,children:o,right:i,className:s}){let[r,u]=w.useState(a);return w.createElement("section",{className:E("at-disc",r&&"is-open",n&&`at-tone-${n}`,s)},w.createElement("button",{type:"button",className:"at-disc-head","aria-expanded":r,onClick:()=>u(!r)},w.createElement(A,{name:"chevR",size:14,className:"at-disc-chev"}),w.createElement("span",{className:"at-disc-title"},t),e!==void 0?w.createElement("span",{className:"at-count"},e):null,w.createElement("span",{className:"at-flex"}),i),r?w.createElement("div",{className:"at-disc-body"},o):null)}function st({area:t}){return w.createElement("span",{className:"at-areadot",style:{"--at-area":aa(t)},title:t})}var we=[212,152,28,280,340,188,48,252];function aa(t){if(!t)return"var(--at-faint)";let e=0;for(let a of String(t))e=e*31+a.charCodeAt(0)>>>0;return`hsl(${we[e%we.length]} 62% 56%)`}var Ne=w.createContext(null),it=()=>w.useContext(Ne);function De({rootRef:t,children:e}){let[a,n]=w.useState(null),o=w.useCallback(()=>n(r=>(r&&r.onClose&&r.onClose(),null)),[]),i=w.useCallback((r,u,l={})=>n({anchor:r,render:u,...l}),[]),s=w.useMemo(()=>({open:i,close:o}),[i,o]);return w.createElement(Ne.Provider,{value:s},e,a?w.createElement(na,{rootRef:t,...a,close:o}):null)}function na({rootRef:t,anchor:e,render:a,close:n,align:o="start",width:i}){let s=w.useRef(null),[r,u]=w.useState(null);return w.useLayoutEffect(()=>{let l=t.current,g=s.current;if(!l||!g||!e)return;let d=()=>{let k=l.getBoundingClientRect(),f=e.getBoundingClientRect?e.getBoundingClientRect():e,D=g.offsetWidth,b=g.offsetHeight,T=(o==="end"?f.right-D:f.left)-k.left;T=Math.max(8,Math.min(T,k.width-D-8));let z=f.bottom-k.top+6;z+b>k.height-8&&f.top-k.top-b-6>8&&(z=f.top-k.top-b-6),z=Math.max(8,Math.min(z,k.height-b-8)),u({left:T,top:z})};d();let y=new ResizeObserver(d);return y.observe(g),()=>y.disconnect()},[e,t,o]),w.useEffect(()=>{let l=d=>{s.current&&!s.current.contains(d.target)&&!(e&&e.contains&&e.contains(d.target))&&n()},g=d=>{d.key==="Escape"&&(d.stopPropagation(),n())};return document.addEventListener("pointerdown",l,!0),document.addEventListener("keydown",g,!0),()=>{document.removeEventListener("pointerdown",l,!0),document.removeEventListener("keydown",g,!0)}},[e,n]),w.createElement("div",{ref:s,className:"at-pop",role:"dialog",style:{left:r?r.left:-9999,top:r?r.top:-9999,width:i}},a(n))}function et({items:t,close:e}){return w.createElement("div",{className:"at-menu",role:"menu"},t.filter(Boolean).map((a,n)=>a==="-"?w.createElement("div",{key:n,className:"at-menu-sep"}):w.createElement("button",{key:n,type:"button",role:"menuitem",className:E("at-menu-item",a.danger&&"is-danger"),onClick:()=>{e(),a.run()}},a.icon?w.createElement(A,{name:a.icon,size:15}):w.createElement("span",{className:"at-menu-pad"}),w.createElement("span",{className:"at-flex"},a.label),a.hint?w.createElement("span",{className:"at-menu-hint"},a.hint):null)))}function Ht(t){return[{label:"Today",date:t,hint:dt(t)},{label:"Tomorrow",date:X(t,1),hint:dt(X(t,1))},{label:"Next Monday",date:Kt(t,0),hint:mt(Kt(t,0),t).replace(/^\w+,\s*/,"")},{label:"In a week",date:X(t,7),hint:mt(X(t,7),t).replace(/^\w+,\s*/,"")}]}function St({value:t,today:e,onPick:a,onClear:n,close:o,extra:i}){let[s,r]=w.useState(Tt(t||e)),u=$t(s),l=g=>{a(g),o&&o()};return w.createElement("div",{className:"at-dp"},w.createElement("div",{className:"at-dp-quick"},Ht(e).map(g=>w.createElement("button",{key:g.label,type:"button",className:E("at-dp-q",t===g.date&&"is-on"),onClick:()=>l(g.date)},w.createElement("span",null,g.label),w.createElement("span",{className:"at-muted"},g.hint)))),w.createElement("div",{className:"at-dp-head"},w.createElement("span",{className:"at-dp-title"},Bt(s)," ",s.slice(0,4)!==e.slice(0,4)?s.slice(0,4):""),w.createElement(G,{icon:"chevL",label:"Previous month",onClick:()=>r(_t(s,-1))}),w.createElement(G,{icon:"chevR",label:"Next month",onClick:()=>r(_t(s,1))})),w.createElement("div",{className:"at-dp-grid",role:"grid"},["M","T","W","T","F","S","S"].map((g,d)=>w.createElement("span",{key:d,className:"at-dp-dow"},g)),u.flat().map(g=>w.createElement("button",{key:g,type:"button",onClick:()=>l(g),className:E("at-dp-day",g.slice(0,7)!==s.slice(0,7)&&"is-out",g===e&&"is-today",g===t&&"is-on")},yt(g)))),n||i?w.createElement("div",{className:"at-dp-foot"},i,w.createElement("span",{className:"at-flex"}),n?w.createElement(Y,{size:"sm",variant:"ghost",onClick:()=>{n(),o&&o()}},"Clear"):null):null)}var Se=w.createContext(null),lt=()=>w.useContext(Se);function Ce({children:t}){let[e,a]=w.useState([]),n=w.useRef(0),o=w.useCallback(s=>a(r=>r.filter(u=>u.id!==s)),[]),i=w.useCallback((s,r={})=>{let u=++n.current;return a(l=>[...l.slice(-2),{id:u,message:s,...r}]),setTimeout(()=>o(u),r.duration||(r.undo?6500:r.tone==="error"?7e3:3500)),u},[o]);return w.createElement(Se.Provider,{value:i},t,w.createElement("div",{className:"at-toasts","aria-live":"polite"},e.map(s=>w.createElement("div",{key:s.id,className:E("at-toast",s.tone&&`at-tone-${s.tone}`)},s.tone==="error"?w.createElement(A,{name:"alert",size:15}):null,w.createElement("span",{className:"at-flex"},s.message),s.undo?w.createElement("button",{type:"button",className:"at-toast-act",onClick:()=>{o(s.id),s.undo()}},"Undo"):null,s.action?w.createElement("button",{type:"button",className:"at-toast-act",onClick:()=>{o(s.id),s.action.run()}},s.action.label):null))))}var ze={urgent:0,high:1,normal:2,low:3},at=t=>t.status==="done"||t.status==="cancelled",Te=(t,e)=>(ze[t.priority]??2)-(ze[e.priority]??2)||t.title.localeCompare(e.title);function Pt(){let{store:t,prefs:e}=H(),a=kt(t,oa),n=kt(t,ra);return c.useMemo(()=>{let o={},i=[];for(let s of Object.values(a)){if(e.area&&s.area!==e.area)continue;let r=V(s);r&&(!at(s)&&n&&r<n&&i.push(s),(o[r]||(o[r]=[])).push(s))}for(let s of Object.keys(o))o[s].sort((r,u)=>Number(at(r))-Number(at(u))||Te(r,u));return i.sort((s,r)=>V(r).localeCompare(V(s))||Te(s,r)),{days:o,overdue:i,today:n}},[a,n,e.area])}var oa=t=>t.byId,ra=t=>t.today;function ee({task:t,from:e,compact:a,showDate:n,selected:o}){let{actions:i,today:s}=H(),{bind:r}=It(),u=it(),l=at(t),g=!l&&V(t)&&V(t)<s,d=t.due&&t.scheduled&&t.due!==t.scheduled,y=t.research==="pending"||t.research==="running",k=f=>{f.stopPropagation(),u.open(f.currentTarget,D=>c.createElement(sa,{task:t,close:D}),{width:236,align:"end"})};return c.createElement("div",{className:E("at-row",a&&"is-compact",l&&"is-done",o&&"is-selected",g&&"is-late"),...r(t,e),onClick:()=>{u.close(),i.open(t.task_id)},onKeyDown:f=>{f.key==="Enter"&&(u.close(),i.open(t.task_id)),f.key===" "&&f.target===f.currentTarget&&(f.preventDefault(),i.toggle(t))},tabIndex:0,role:"button","aria-label":t.title,"data-task":t.task_id},c.createElement(Ot,{checked:l,onChange:()=>i.toggle(t),label:l?"Mark not done":"Mark done",size:a?"sm":"md",tone:g||t.priority==="urgent"||t.priority==="high"?"high":void 0}),c.createElement("div",{className:"at-row-main"},c.createElement("div",{className:"at-row-title",title:a?t.title:void 0},t.title),a?null:c.createElement("div",{className:"at-row-meta"},t.area?c.createElement("span",{className:"at-meta-area"},c.createElement(st,{area:t.area}),t.area):null,n?c.createElement("span",{className:E("at-meta-date",g&&"is-late")},W(V(t),s)):null,d?c.createElement("span",{className:"at-meta-due"},"due ",W(t.due,s)):null,t.priority==="urgent"||t.priority==="high"?c.createElement("span",{className:"at-meta-prio"},t.priority):null,t.status==="waiting"?c.createElement("span",{className:"at-meta-status"},"waiting"):null,t.status==="in-progress"?c.createElement("span",{className:"at-meta-status is-active"},"in progress"):null,y?c.createElement("span",{className:"at-meta-research"},c.createElement(A,{name:"spark",size:12}),"researching"):null)),a?null:c.createElement(G,{icon:"more",label:"Task actions",className:"at-row-more",onClick:k,"data-no-drag":""}))}function sa({task:t,close:e}){let{actions:a,today:n}=H(),[o,i]=c.useState(!1);if(o)return c.createElement(St,{value:V(t),today:n,onPick:r=>a.move(t,r),close:e});let s=Ht(n).slice(0,3).map(r=>({label:r.label,hint:r.hint,icon:"cal",run:()=>a.move(t,r.date)})).filter((r,u)=>Ht(n)[u].date!==V(t));return c.createElement("div",{className:"at-menu",role:"menu"},c.createElement("div",{className:"at-menu-label"},"Move to"),c.createElement(et,{items:s,close:e}),c.createElement("button",{type:"button",className:"at-menu-item",onClick:()=>i(!0)},c.createElement(A,{name:"cal",size:15}),c.createElement("span",{className:"at-flex"},"Pick a date\u2026")),c.createElement("div",{className:"at-menu-sep"}),c.createElement(et,{close:e,items:[{label:at(t)?"Mark not done":"Mark done",icon:"check",run:()=>a.toggle(t)},{label:"Open",icon:"arrowR",run:()=>a.open(t.task_id)}]}))}function qt({date:t,tasks:e=[],overdue:a=[],compact:n,empty:o="Nothing planned",showAdd:i}){let{today:s,prefs:r,selectedId:u}=H(),{drag:l}=It(),g=t===s,d=r.hideDone?e.filter(k=>!at(k)):e,y=e.length-d.length;return c.createElement("div",{className:E("at-daylist",l&&l.over===t&&"is-over"),"data-at-drop":t},g&&a.length?c.createElement(ia,{tasks:a}):null,d.map(k=>c.createElement(ee,{key:k.task_id,task:k,from:t,compact:n,selected:u===k.task_id})),!d.length&&!(g&&a.length)?c.createElement("div",{className:"at-empty-day"},y?`${y} done`:o):null,i?c.createElement(Me,{date:t}):null,l&&l.over===t&&l.from!==t?c.createElement("div",{className:"at-drop-hint"},"Move to ",W(t,s)):null)}function ia({tasks:t,defaultOpen:e=!1}){let{actions:a,today:n,selectedId:o}=H();return c.createElement(pt,{className:"at-overdue",tone:"late",title:"Overdue",count:t.length,defaultOpen:e,right:c.createElement("span",{className:"at-link",role:"button",tabIndex:0,"data-no-drag":"",onClick:i=>{i.stopPropagation(),a.moveMany(t,n)}},"Move all to today")},t.map(i=>c.createElement(ee,{key:i.task_id,task:i,from:V(i),showDate:!0,selected:o===i.task_id})))}function Me({date:t,autoFocus:e,onDone:a}){let{actions:n,meta:o,prefs:i}=H(),[s,r]=c.useState(""),[u,l]=c.useState(!1),[g,d]=c.useState(!!e),y=c.useRef(null);if(c.useEffect(()=>{g&&y.current&&y.current.focus()},[g]),!g)return c.createElement("button",{type:"button",className:"at-add",onClick:()=>d(!0),"data-no-drag":""},c.createElement(A,{name:"plus",size:14})," Add a task");let k=async()=>{let f=s.trim();if(!f){d(!1),a&&a();return}l(!0);let D=await n.create({title:f,date:t,area:i.area||o.default_area||void 0});l(!1),D&&(r(""),y.current&&y.current.focus())};return c.createElement("form",{className:"at-add-form","data-no-drag":"",onSubmit:f=>{f.preventDefault(),k()}},c.createElement("span",{className:"at-check at-check-md is-ghost","aria-hidden":"true"}),c.createElement("input",{ref:y,className:"at-add-input",value:s,placeholder:"New task",disabled:u,onChange:f=>r(f.target.value),onKeyDown:f=>{f.key==="Escape"&&(r(""),d(!1),a&&a())},onBlur:()=>{s.trim()||(d(!1),a&&a())}}),u?c.createElement(Z,null):null)}function la({anchor:t,narrow:e}){let{today:a,selectedId:n}=H(),{days:o,overdue:i}=Pt(),s=it(),{drag:r}=It(),u=$t(t),l=t.slice(0,7),[g,d]=c.useState(null);if(e){let v=g&&g.slice(0,7)===l?g:a.slice(0,7)===l?a:Tt(t);return c.createElement("div",{className:"at-scroll at-mmonth"},c.createElement("div",{className:"at-mmonth-dows"},["M","T","W","T","F","S","S"].map((N,S)=>c.createElement("span",{key:S},N))),c.createElement("div",{className:"at-mmonth-grid"},u.flat().map(N=>{let S=o[N]||[],_=S.filter(L=>!at(L)).length;return c.createElement("button",{key:N,type:"button","data-at-drop":N,onClick:()=>d(N),className:E("at-mcell",N.slice(0,7)!==l&&"is-out",N===a&&"is-today",N===v&&"is-on",r&&r.over===N&&"is-over")},c.createElement("span",{className:"at-mcell-num"},yt(N)),c.createElement("span",{className:"at-mcell-dots"},S.slice(0,3).map(L=>c.createElement("i",{key:L.task_id,className:at(L)?"is-done":""})),N===a&&i.length?c.createElement("i",{className:"is-late"}):null),_>3?c.createElement("span",{className:"at-mcell-more"},"+",_-3):null)})),c.createElement(ae,{date:v,tasks:o[v]||[],overdue:v===a?i:[]}))}let y=(v,N)=>s.open(N,S=>c.createElement(da,{date:v,close:S}),{width:360}),k=c.useRef(null),[f,D]=c.useState(110),[b,T]=c.useState(160);c.useLayoutEffect(()=>{let v=k.current;if(!v)return;let N=new ResizeObserver(()=>{D(v.clientHeight/u.length),T(v.clientWidth/7)});return N.observe(v),()=>N.disconnect()},[u.length]);let z=f-34;return c.createElement("div",{className:"at-month"},c.createElement("div",{className:"at-month-dows"},u[0].map(v=>c.createElement("div",{key:v},dt(v)))),c.createElement("div",{ref:k,className:"at-month-grid",style:{gridTemplateRows:`repeat(${u.length}, minmax(0, 1fr))`}},u.flat().map(v=>{let N=o[v]||[],S=N.length*37<=z,_=S?N.length:Math.max(1,Math.floor(z/23)),L=N.length>_?N.slice(0,Math.max(1,_-1)):N,J=N.length-L.length,nt=v===a;return c.createElement("div",{key:v,"data-at-drop":v,className:E("at-cell",v.slice(0,7)!==l&&"is-out",nt&&"is-today",v<a&&"is-past",r&&r.over===v&&"is-over"),onClick:B=>{B.target.closest(".at-row")||y(v,B.currentTarget)}},c.createElement("div",{className:"at-cell-head"},c.createElement("span",{className:"at-cell-num"},yt(v)===1?`${Bt(v,"short")} 1`:yt(v)),nt&&i.length?c.createElement("button",{type:"button",className:"at-chip at-tone-late","data-no-drag":"",title:`${i.length} overdue`,onClick:B=>{B.stopPropagation(),y(v,B.currentTarget.closest(".at-cell"))}},b<140?`${i.length} late`:`${i.length} overdue`):null),c.createElement("div",{className:E("at-cell-list",!S&&"is-tight")},L.map(B=>c.createElement(ee,{key:B.task_id,task:B,from:v,compact:!0,selected:n===B.task_id})),J>0?c.createElement("button",{type:"button",className:"at-cell-more","data-no-drag":"",onClick:B=>{B.stopPropagation(),y(v,B.currentTarget.closest(".at-cell"))}},"+",J," more"):null))})))}function da({date:t,close:e}){let{today:a}=H(),{days:n,overdue:o}=Pt();return c.createElement("div",{className:"at-daypop"},c.createElement("div",{className:"at-daypop-head"},c.createElement("div",null,c.createElement("div",{className:"at-daypop-title"},W(t,a)==="Today"?"Today":dt(t,"long")),c.createElement("div",{className:"at-muted"},Gt(t))),c.createElement(G,{icon:"x",label:"Close",onClick:e})),c.createElement("div",{className:"at-daypop-body"},c.createElement(qt,{date:t,tasks:n[t]||[],overdue:t===a?o:[],showAdd:!0})))}function pa({anchor:t,narrow:e}){let{today:a}=H(),{days:n,overdue:o}=Pt(),i=zt(t),s=At(i,X(i,6));return e?c.createElement("div",{className:"at-scroll at-days"},s.map(r=>c.createElement(ae,{key:r,date:r,tasks:n[r]||[],overdue:r===a?o:[]}))):c.createElement("div",{className:"at-week"},s.map(r=>c.createElement("div",{key:r,className:E("at-week-col",r===a&&"is-today",r<a&&"is-past")},c.createElement("div",{className:"at-week-head"},c.createElement("span",{className:"at-week-dow"},dt(r)),c.createElement("span",{className:"at-week-num"},yt(r))),c.createElement("div",{className:"at-week-body at-scroll"},c.createElement(qt,{date:r,tasks:n[r]||[],overdue:r===a?o:[],showAdd:!0})))))}function ca({anchor:t}){let{today:e}=H(),{days:a,overdue:n}=Pt();return c.createElement("div",{className:"at-scroll at-dayview"},c.createElement("div",{className:"at-dayview-inner"},c.createElement("header",{className:"at-dayview-head"},c.createElement("h2",null,W(t,e)==="Today"?"Today":dt(t,"long")),c.createElement("div",{className:"at-muted"},Gt(t))),c.createElement(qt,{date:t,tasks:a[t]||[],overdue:t===e?n:[],showAdd:!0})))}function ae({date:t,tasks:e,overdue:a}){let{today:n}=H(),o=W(t,n),i=o==="Today"||o==="Tomorrow"||o==="Yesterday",s=!e.length&&!a.length;return c.createElement("section",{className:E("at-daysec",t===n&&"is-today",s&&"is-empty")},c.createElement("header",{className:"at-daysec-head"},c.createElement("span",{className:"at-daysec-title"},i?o:dt(t,"long")),c.createElement("span",{className:"at-muted"},mt(t,n).replace(/^\w+,\s*/,""))),c.createElement(qt,{date:t,tasks:e,overdue:a,showAdd:!s||t===n}))}function ua({anchor:t,onReachEnd:e,length:a}){let{today:n}=H(),{days:o,overdue:i}=Pt(),s=At(t,X(t,a-1)),r=c.useRef(null);return c.useEffect(()=>{let u=r.current;if(!u)return;let l=new IntersectionObserver(g=>{g[0].isIntersecting&&e()},{rootMargin:"400px"});return l.observe(u),()=>l.disconnect()},[e]),c.createElement("div",{className:"at-scroll at-days"},s.map(u=>c.createElement(ae,{key:u,date:u,tasks:o[u]||[],overdue:u===n?i:[]})),c.createElement("div",{ref:r,className:"at-sentinel"}))}function Ee({narrow:t}){let{store:e,prefs:a,setPrefs:n,meta:o,today:i}=H(),s=it(),r=a.view||(t?"day":"month"),[u,l]=c.useState(i),[g,d]=c.useState(21),y=c.useCallback(()=>d(v=>Math.min(v+14,120)),[]);c.useEffect(()=>{!u&&i&&l(i)},[i,u]);let k=u||i,f=c.useMemo(()=>{if(!k)return null;if(r==="month"){let v=$t(k);return[v[0][0],v[v.length-1][6]]}if(r==="week"){let v=zt(k);return[v,X(v,6)]}return t?[k,X(k,g-1)]:[k,k]},[k,r,t,g]);c.useEffect(()=>{f&&(e.loadRange(f[0],f[1]).catch(()=>{}),e.loadOverdue().catch(()=>{}))},[f&&f[0],f&&f[1]]);let D=v=>{l(r==="month"?_t(k,v):r==="week"?X(k,7*v):X(k,v))};if(c.useEffect(()=>{let v=N=>{if(N.target.closest&&N.target.closest("input, textarea, [contenteditable]")||N.metaKey||N.ctrlKey||N.altKey)return;let S=N.key.toLowerCase();if(S==="t")l(i);else if(S==="d")n({view:"day"});else if(S==="w")n({view:"week"});else if(S==="m")n({view:"month"});else if(N.key==="ArrowLeft")D(-1);else if(N.key==="ArrowRight")D(1);else return;N.preventDefault()};return window.addEventListener("keydown",v),()=>window.removeEventListener("keydown",v)}),!k)return c.createElement("div",{className:"at-loading"},c.createElement(Z,{size:18}));let b=o.areas||[],T=v=>s.open(v.currentTarget,N=>c.createElement(et,{close:N,items:[{label:"All areas",icon:a.area?void 0:"check",run:()=>n({area:""})},"-",...b.map(S=>({label:S,icon:a.area===S?"check":void 0,run:()=>n({area:S})})),"-",{label:a.hideDone?"Show completed":"Hide completed",run:()=>n({hideDone:!a.hideDone})}]}),{width:200,align:"end"}),z=v=>s.open(v.currentTarget,N=>c.createElement("div",{className:"at-pop-add"},c.createElement(Me,{date:r==="day"?k:i,autoFocus:!0,onDone:N})),{width:320,align:"end"});return c.createElement("div",{className:E("at-tasks",`is-${r}`)},c.createElement("div",{className:"at-toolbar"},c.createElement("div",{className:"at-toolbar-nav"},c.createElement(Y,{variant:"ghost",size:"sm",onClick:()=>l(i),disabled:k===i&&r!=="month"},"Today"),c.createElement(G,{icon:"chevL",label:"Previous",onClick:()=>D(-1)}),c.createElement(G,{icon:"chevR",label:"Next",onClick:()=>D(1)}),c.createElement("h1",{className:"at-period"},r==="day"?Jt("month",k,i):Jt(r,k,i))),c.createElement("div",{className:"at-toolbar-right"},c.createElement(Ut,{label:"View",value:r,onChange:v=>n({view:v}),options:[{value:"day",label:"Day"},{value:"week",label:"Week"},{value:"month",label:"Month"}]}),c.createElement("button",{type:"button",className:E("at-filter",a.area&&"is-on"),onClick:T},a.area?c.createElement(st,{area:a.area}):null,c.createElement("span",null,a.area||"All areas"),c.createElement(A,{name:"chevD",size:14})),t?null:c.createElement(Y,{variant:"primary",size:"sm",icon:"plus",onClick:z},"Add"))),c.createElement("div",{className:"at-viewport"},r==="month"?c.createElement(la,{anchor:k,narrow:t}):null,r==="week"?c.createElement(pa,{anchor:k,narrow:t}):null,r==="day"&&t?c.createElement(ua,{anchor:k,length:g,onReachEnd:y}):null,r==="day"&&!t?c.createElement(ca,{anchor:k}):null),t?c.createElement("button",{type:"button",className:"at-fab","aria-label":"Add a task",onClick:z},c.createElement(A,{name:"plus",size:22})):null)}import m from"react";import ma from"react";var O=ma.createElement,ga=/^(https?:|mailto:|obsidian:|#)/i;function ct(t,e="i"){let a=[],n=String(t),o=0,i=/(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(\*[^*\s][^*]*\*|_[^_\s][^_]*_)|(\[\[[^\]]+\]\])|(\[[^\]]+\]\([^)\s]+\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/;for(;n;){let s=n.match(i);if(!s){a.push(n);break}s.index&&a.push(n.slice(0,s.index));let r=s[0],u=`${e}-${o++}`;if(s[1])a.push(O("code",{key:u},r.slice(1,-1)));else if(s[2])a.push(O("strong",{key:u},ct(r.slice(2,-2),u)));else if(s[3])a.push(O("em",{key:u},ct(r.slice(1,-1),u)));else if(s[4]){let l=r.slice(2,-2),g=l.includes("|")?l.split("|").pop():l.split("/").pop();a.push(O("span",{key:u,className:"at-md-wikilink",title:l.split("|")[0]},g))}else if(s[5]){let l=r.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/),g=l[2];a.push(ga.test(g)?O("a",{key:u,href:g,target:"_blank",rel:"noreferrer noopener"},ct(l[1],u)):l[1])}else s[6]&&a.push(O("a",{key:u,href:r,target:"_blank",rel:"noreferrer noopener"},fa(r)));n=n.slice(s.index+r.length)}return a}function fa(t){try{let e=new URL(t),a=e.pathname.length>24?e.pathname.slice(0,22)+"\u2026":e.pathname;return e.host.replace(/^www\./,"")+(a==="/"?"":a)}catch{return t}}var Yt=/^(\s*)([-*+]|\d+[.)])\s+(\[( |x|X)\]\s+)?(.*)$/;function Vt(t){let e=String(t||"").replace(/\r\n?/g,`
`).split(`
`),a=[],n=0;for(;n<e.length;){let o=e[n];if(!o.trim()){n++;continue}let i=o.match(/^\s*(```|~~~)/);if(i){let u=[];for(n++;n<e.length&&!e[n].trim().startsWith(i[1]);)u.push(e[n++]);n++,a.push({type:"code",text:u.join(`
`)});continue}let s=o.match(/^(#{1,6})\s+(.*)$/);if(s){a.push({type:"heading",level:s[1].length,text:s[2].trim(),line:n}),n++;continue}if(/^\s*<!--.*-->\s*$/.test(o)){n++;continue}if(/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(o)){a.push({type:"hr"}),n++;continue}if(/^\s*\|.*\|\s*$/.test(o)&&n+1<e.length&&/^\s*\|?[\s:|-]+\|?\s*$/.test(e[n+1])&&e[n+1].includes("-")){let u=d=>d.trim().replace(/^\||\|$/g,"").split("|").map(y=>y.trim()),l=u(o),g=[];for(n+=2;n<e.length&&/^\s*\|.*\|\s*$/.test(e[n]);)g.push(u(e[n++]));a.push({type:"table",head:l,rows:g});continue}if(/^\s*>/.test(o)){let u=[];for(;n<e.length&&/^\s*>/.test(e[n]);)u.push(e[n++].replace(/^\s*>\s?/,""));a.push({type:"quote",text:u.join(" ")});continue}if(Yt.test(o)){let u=[];for(;n<e.length&&(Yt.test(e[n])||/^\s{2,}\S/.test(e[n])&&u.length);){let l=e[n].match(Yt);l?u.push({indent:Math.floor(l[1].replace(/\t/g,"  ").length/2),ordered:/\d/.test(l[2]),checkbox:l[3]?l[4].toLowerCase()==="x":null,text:l[5],line:n}):u[u.length-1].text+=" "+e[n].trim(),n++}a.push({type:"list",items:u});continue}let r=[];for(;n<e.length&&e[n].trim()&&!Yt.test(e[n])&&!/^(#{1,6})\s/.test(e[n])&&!/^\s*(```|~~~|>|\|)/.test(e[n]);)r.push(e[n++].trim());r.length?a.push({type:"p",text:r.join(" ")}):n++}return a}function Ft(t,{onToggle:e}={}){return t.map((a,n)=>{let o=`b${n}`;switch(a.type){case"heading":return O(`h${Math.min(6,a.level+2)}`,{key:o,className:"at-md-h"},ct(a.text,o));case"p":return O("p",{key:o},ct(a.text,o));case"hr":return O("hr",{key:o});case"code":return O("pre",{key:o},O("code",null,a.text));case"quote":return O("blockquote",{key:o},ct(a.text,o));case"table":return O("div",{key:o,className:"at-md-table"},O("table",null,O("thead",null,O("tr",null,a.head.map((i,s)=>O("th",{key:s},ct(i,`${o}h${s}`))))),O("tbody",null,a.rows.map((i,s)=>O("tr",{key:s},i.map((r,u)=>O("td",{key:u},ct(r,`${o}r${s}${u}`))))))));case"list":{let i=a.items[0]&&a.items[0].ordered;return O(i?"ol":"ul",{key:o,className:"at-md-list"},a.items.map((s,r)=>{let u=s.indent?{marginLeft:`${s.indent*1.25}em`}:void 0;return s.checkbox===null?O("li",{key:r,style:u},ct(s.text,`${o}${r}`)):O("li",{key:r,style:u,className:"at-md-check"+(s.checkbox?" is-done":"")},O("label",null,O("input",{type:"checkbox",checked:s.checkbox,disabled:!e,onChange:l=>e&&e(s.line,l.target.checked)}),O("span",null,ct(s.text,`${o}${r}`))))}))}default:return null}})}function _e(t,e,a){let n=String(t).split(`
`),o=n[e]&&n[e].match(/^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\](.*)$/);return o?(n[e]=`${o[1]}[${a?"x":" "}]${o[3]}`,n.join(`
`)):t}var $e=/^\s*<!--\s*([\w-]+):start\s*-->\s*$/,Wt=/^\s*<!--\s*([\w-]+):end\s*-->\s*$/;function Le(t){let e=String(t||"").replace(/\r\n?/g,`
`).split(`
`),a=e.slice(),n=[];for(let s=0;s<e.length;s++){let r=e[s].match($e);if(!r)continue;let u=s+1;for(;u<e.length&&!(Wt.test(e[u])&&e[u].match(Wt)[1]===r[1]);)u++;if(!(u>=e.length)){n.push({name:r[1],text:e.slice(s+1,u).join(`
`).trim()});for(let l=s;l<=u;l++)a[l]="";s=u}}let o=[],i={title:"",start:0,lines:[]};return a.forEach((s,r)=>{let u=s.match(/^##\s+(.*)$/);u?(o.push(i),i={title:u[1].trim(),start:r+1,lines:[]}):i.lines.push(s)}),o.push(i),{sections:o.filter(s=>s.title||s.lines.join("").trim()).map(s=>({title:s.title,text:s.lines.join(`
`),start:s.start,folded:/^(log|history|activity)$/i.test(s.title)})),managed:n}}function Pe(t){return/dossier|research/i.test(t)?"Research":/state/i.test(t)?"Current state":t.replace(/[-_]+/g," ").replace(/^\w/,e=>e.toUpperCase())}function Ae(t){let e=String(t||"").replace(/\r\n?/g,`
`).split(`
`),a=[],n=[],o=[],i=!1;for(let r=0;r<e.length;r++){let u=e[r].match($e);if(u){let l=r+1;for(;l<e.length&&!(Wt.test(e[l])&&e[l].match(Wt)[1]===u[1]);)l++;if(l<e.length){(i?o:n).push(e.slice(r,l+1).join(`
`)),r=l;continue}}e[r].trim()&&(i=!0),a.push(e[r])}return{editable:a.join(`
`).replace(/\n{3,}/g,`

`).replace(/^\n+/,"").replace(/\s+$/,"")+`
`,top:n,bottom:o}}function Be(t,e,a){let n=[];return e.length&&n.push(e.join(`

`)),n.push(String(t).replace(/\s+$/,"")),a.length&&n.push(a.join(`

`)),`
`+n.filter(o=>o.trim()).join(`

`)+`
`}var ha=["urgent","high","normal","low"],Ie=[["open","Open"],["in-progress","In progress"],["waiting","Waiting"]];function Oe({id:t,narrow:e,onClose:a}){let{store:n,api:o,actions:i,today:s,meta:r}=H(),u=lt(),l=it(),g=m.useCallback(x=>x.byId[t],[t]),d=kt(n,g),[y,k]=m.useState(null),[f,D]=m.useState(!1),[b,T]=m.useState(!1),z=m.useCallback(()=>(k(null),T(!1),n.loadTask(t).catch(x=>k(x))),[t,n]);m.useEffect(()=>{D(!1),z()},[t]);let v=!!d&&d.body===void 0;m.useEffect(()=>{v&&!y&&z()},[v]),m.useEffect(()=>{if(f)return;let x=()=>n.loadTask(t).catch(()=>{}),M=setInterval(()=>{document.visibilityState==="visible"&&x()},3e4);return window.addEventListener("focus",x),()=>{clearInterval(M),window.removeEventListener("focus",x)}},[t,f,n]),m.useEffect(()=>{let x=M=>{M.key==="Escape"&&!M.defaultPrevented&&!f&&a()};return window.addEventListener("keydown",x),()=>window.removeEventListener("keydown",x)},[a,f]);let N=m.useRef(null),S=async()=>{if(!f||!N.current)return!0;let x=await N.current();return x&&D(!1),x},_=async(x,M)=>{if(await S())try{await n.mutate(t,M||x,()=>o.patch(t,{...x,expected_revision:d&&d.revision}))}catch($){($.code==="stale_revision"||$.code==="retry")&&T(!0),u(F($),{tone:"error"})}},L=async(x,M)=>{let $=await o.putBody(t,x,M);return n.put($.task),$.task},J=m.useRef(Promise.resolve()),nt=(x,M)=>{J.current=J.current.then(async()=>{let $=n.getState().byId[t];if(!(!$||$.body===void 0))try{await L(_e($.body,x,M),$.revision)}catch(Q){Q.code==="stale_revision"&&T(!0),u(F(Q),{tone:"error"})}})};if(!d&&y)return m.createElement(ne,{narrow:e,onClose:a},m.createElement("div",{className:"at-panel-empty"},m.createElement(A,{name:"alert",size:20}),m.createElement("p",null,F(y)),m.createElement(Y,{onClick:z},"Try again")));if(!d)return m.createElement(ne,{narrow:e,onClose:a},m.createElement("div",{className:"at-panel-empty"},m.createElement(Z,{size:18})));let B=V(d),j=d.due&&d.scheduled&&d.due!==d.scheduled,Mt=x=>l.open(x.currentTarget,M=>m.createElement(St,{value:B,today:s,close:M,onPick:async $=>{await S()&&i.move(n.getState().byId[t]||d,$)}}),{width:300}),ht=x=>l.open(x.currentTarget,M=>m.createElement(St,{value:d.due,today:s,close:M,onPick:$=>_({due:$,keep_separate:!0},{due:$})}),{width:300}),xt=x=>l.open(x.currentTarget,M=>m.createElement(et,{close:M,items:(r.areas||[]).map($=>({label:$,icon:$===d.area?"check":void 0,run:()=>_({area:$})}))}),{width:200}),wt=x=>l.open(x.currentTarget,M=>m.createElement(et,{close:M,items:ha.map($=>({label:$[0].toUpperCase()+$.slice(1),icon:$===(d.priority||"normal")?"check":void 0,run:()=>_({priority:$})}))}),{width:180}),ut=x=>l.open(x.currentTarget,M=>m.createElement(et,{close:M,items:Ie.map(([$,Q])=>({label:Q,icon:$===d.status?"check":void 0,run:()=>_({status:$,...$==="waiting"?{reason:"Marked waiting from the Tasks UI"}:{}})}))}),{width:180});return m.createElement(ne,{narrow:e,onClose:a,actions:m.createElement(m.Fragment,null,d.loading?m.createElement(Z,null):null,m.createElement(G,{icon:"refresh",label:"Reload",onClick:z}))},b?m.createElement("div",{className:"at-banner at-tone-late"},m.createElement(A,{name:"alert",size:15}),m.createElement("span",{className:"at-flex"},"This task changed somewhere else."),m.createElement(Y,{size:"sm",onClick:z},"Reload")):null,m.createElement("div",{className:"at-panel-titlerow"},m.createElement(Ot,{checked:at(d),onChange:async()=>{await S()&&i.toggle(n.getState().byId[t]||d)},label:at(d)?"Mark not done":"Mark done",size:"lg"}),m.createElement(xa,{value:d.title,done:at(d),onSave:x=>_({title:x})})),m.createElement("div",{className:"at-fields"},m.createElement("button",{type:"button",className:E("at-field",B&&B<s&&!at(d)&&"is-late"),onClick:Mt},m.createElement(A,{name:"cal",size:15}),m.createElement("span",null,B?W(B,s):"No date")),m.createElement("button",{type:"button",className:"at-field",onClick:xt},m.createElement(st,{area:d.area}),m.createElement("span",null,d.area||"No area")),m.createElement("button",{type:"button",className:E("at-field",(d.priority==="high"||d.priority==="urgent")&&"is-high"),onClick:wt},m.createElement("span",{className:"at-prio-glyph","data-p":d.priority||"normal"}),m.createElement("span",null,(d.priority||"normal").replace(/^\w/,x=>x.toUpperCase()))),d.status==="waiting"||d.status==="in-progress"?m.createElement("button",{type:"button",className:"at-field",onClick:ut},m.createElement("span",null,d.status==="waiting"?"Waiting":"In progress")):null,j?m.createElement("button",{type:"button",className:"at-field",onClick:ht},m.createElement("span",{className:"at-muted"},"Due"),m.createElement("span",null,W(d.due,s))):null),m.createElement(va,{value:d.summary||"",onSave:x=>_({summary:x})}),d.research==="pending"||d.research==="running"?m.createElement("div",{className:"at-research-note"},m.createElement(A,{name:"spark",size:14})," Hermes is researching this task. Findings will appear here."):null,f?m.createElement(ya,{task:d,onSave:L,onDone:()=>D(!1),onStale:()=>T(!0),flushRef:N}):d.body===void 0?m.createElement("div",{className:"at-panel-loading"},m.createElement(Z,null)):m.createElement(ba,{task:d,onEdit:()=>D(!0),onToggle:nt}),m.createElement(pt,{title:"More",className:"at-more"},m.createElement("div",{className:"at-more-grid"},m.createElement("span",{className:"at-muted"},"Status"),m.createElement("button",{type:"button",className:"at-field is-plain",onClick:ut},(Ie.find(([x])=>x===d.status)||[0,d.status])[1]),m.createElement("span",{className:"at-muted"},"Due date"),m.createElement("span",null,j?m.createElement("button",{type:"button",className:"at-field is-plain",onClick:ht},mt(d.due,s)):m.createElement("button",{type:"button",className:"at-link",onClick:ht},"Set a separate due date")),d.completed?m.createElement(m.Fragment,null,m.createElement("span",{className:"at-muted"},"Completed"),m.createElement("span",null,mt(d.completed,s))):null,d.project?m.createElement(m.Fragment,null,m.createElement("span",{className:"at-muted"},"Project"),m.createElement("span",{className:"at-mono"},String(d.project).replace(/^\[\[|\]\]$/g,"").split("/").slice(-2,-1)[0]||d.project)):null,m.createElement("span",{className:"at-muted"},"File"),m.createElement("span",{className:"at-mono at-break"},d.path))))}function ne({narrow:t,onClose:e,actions:a,children:n}){return m.createElement("aside",{className:E("at-panel",t?"is-sheet":"is-side"),"aria-label":"Task"},m.createElement("div",{className:"at-panel-bar"},t?m.createElement("span",{className:"at-grabber"}):null,m.createElement("span",{className:"at-flex"}),a,m.createElement(G,{icon:"x",label:"Close",onClick:e})),m.createElement("div",{className:"at-panel-body at-scroll"},n))}function xa({value:t,done:e,onSave:a}){let[n,o]=m.useState(t),i=m.useRef(null);m.useEffect(()=>o(t),[t]),m.useLayoutEffect(()=>{let r=i.current;r&&(r.style.height="auto",r.style.height=r.scrollHeight+"px")},[n]);let s=()=>{let r=n.replace(/\s+/g," ").trim();r&&r!==t?a(r):o(t)};return m.createElement("textarea",{ref:i,rows:1,className:E("at-title-input",e&&"is-done"),value:n,"aria-label":"Title",onChange:r=>o(r.target.value),onBlur:s,onKeyDown:r=>{r.key==="Enter"&&(r.preventDefault(),r.currentTarget.blur()),r.key==="Escape"&&(r.preventDefault(),o(t),r.currentTarget.blur())}})}function va({value:t,onSave:e}){let[a,n]=m.useState(t),o=m.useRef(null);return m.useEffect(()=>n(t),[t]),m.useLayoutEffect(()=>{let i=o.current;i&&(i.style.height="auto",i.style.height=i.scrollHeight+"px")},[a]),m.createElement("textarea",{ref:o,rows:1,className:"at-summary-input",value:a,placeholder:"Add a short summary","aria-label":"Summary",onChange:i=>n(i.target.value),onBlur:()=>{let i=a.trim();i!==t.trim()&&e(i)},onKeyDown:i=>{i.key==="Escape"&&(i.preventDefault(),n(t),i.currentTarget.blur())}})}function ba({task:t,onEdit:e,onToggle:a}){let{sections:n,managed:o}=m.useMemo(()=>Le(t.body||""),[t.body]),i=o.find(d=>/current-state/.test(d.name)),s=o.filter(d=>d!==i),r=i?{title:"Current state",text:i.text,start:0,managed:!0}:n.find(d=>/^current state$/i.test(d.title)),u=n.filter(d=>d!==r),l=d=>Ft(Vt(d.text),{onToggle:(y,k)=>a(d.start+y,k)}),g=n.some(d=>d.text.trim());return m.createElement("div",{className:"at-body"},m.createElement("div",{className:"at-body-bar"},m.createElement("span",{className:"at-body-label"},"Notes"),m.createElement("span",{className:"at-flex"}),m.createElement(Y,{size:"sm",variant:"ghost",icon:"edit",onClick:e},"Edit")),r&&r.text.trim()?m.createElement("div",{className:"at-state"},m.createElement("div",{className:"at-state-label"},"Current state"),m.createElement("div",{className:"at-md"},r.managed?Ft(Vt(r.text)):l(r))):null,!g&&!s.length?m.createElement("button",{type:"button",className:"at-empty-notes",onClick:e},"Add notes"):null,u.map((d,y)=>d.folded?m.createElement(pt,{key:y,title:d.title,className:"at-fold"},m.createElement("div",{className:"at-md"},l(d))):m.createElement("div",{key:y,className:"at-section"},d.title&&!/^notes$/i.test(d.title)?m.createElement("h3",{className:"at-section-title"},d.title):null,m.createElement("div",{className:"at-md"},l(d)))),s.map((d,y)=>m.createElement(pt,{key:`m${y}`,title:Pe(d.name),className:"at-fold",right:m.createElement(A,{name:"spark",size:13})},m.createElement("div",{className:"at-md"},Ft(Vt(d.text))))))}function ya({task:t,onSave:e,onDone:a,onStale:n,flushRef:o}){let i=lt(),s=m.useMemo(()=>Ae(t.body||""),[]),r=m.useRef(t.revision),u=m.useRef(Promise.resolve(!0)),[l,g]=m.useState(s.editable),[d,y]=m.useState("saved"),k=m.useRef(l),f=m.useRef(s.editable),D=m.useRef(null),b=m.useRef(null),T=m.useCallback(()=>(clearTimeout(D.current),u.current=u.current.then(async()=>{let S=k.current;if(S===f.current)return y(_=>_==="error"?_:"saved"),!0;y("saving");try{let _=await e(Be(S,s.top,s.bottom),r.current);return r.current=_.revision,f.current=S,y(k.current===S?"saved":"dirty"),!0}catch(_){return y("error"),_.code==="stale_revision"&&n(),i(F(_),{tone:"error"}),!1}}),u.current),[e,n,i,s]);m.useEffect(()=>{if(o)return o.current=T,()=>{o.current=null}},[o,T]);let z=t.revision&&r.current&&t.revision!==r.current&&d!=="saving";m.useEffect(()=>{b.current&&b.current.focus()},[]),m.useEffect(()=>()=>clearTimeout(D.current),[]);let v=S=>{g(S),k.current=S,y("dirty"),clearTimeout(D.current),D.current=setTimeout(T,1500)},N=async()=>{await T()&&a()};return m.createElement("div",{className:"at-body is-editing"},m.createElement("div",{className:"at-body-bar"},m.createElement("span",{className:"at-body-label"},"Notes"),m.createElement("span",{className:E("at-save",`is-${d}`)},d==="saving"?"Saving\u2026":d==="saved"?"Saved":d==="error"?"Not saved":"Editing"),m.createElement("span",{className:"at-flex"}),d==="error"?m.createElement(Y,{size:"sm",variant:"ghost",onClick:a},"Discard changes"):null,d==="error"&&!z?m.createElement(Y,{size:"sm",onClick:T},"Retry"):null,m.createElement(Y,{size:"sm",variant:"primary",onClick:N},"Done")),z?m.createElement("div",{className:"at-banner at-tone-late"},m.createElement(A,{name:"alert",size:15}),m.createElement("span",{className:"at-flex"},"This task changed while you were editing. Your text is kept here and will not overwrite it. Copy what you need, then choose Discard changes to see the latest version.")):null,m.createElement("textarea",{ref:b,className:"at-editor",value:l,spellCheck:!0,onChange:S=>v(S.target.value),onKeyDown:S=>{(S.metaKey||S.ctrlKey)&&S.key==="s"&&(S.preventDefault(),T()),S.key==="Escape"&&(S.preventDefault(),N())}}),m.createElement("div",{className:"at-editor-hint"},"Markdown. Saves as you type.",s.top.length+s.bottom.length?" Research added by Hermes is kept as it is.":""))}import p from"react";var He=t=>(t||[]).reduce((e,a)=>e+(a.proposals||[]).filter(n=>n.state==="pending"&&!n.expired).length,0),qe=t=>String(t||"").replace(/[-_]+/g," ").replace(/\b\w/g,e=>e.toUpperCase());function re(t){let e=t.time,a=typeof e=="number"?new Date(e*(e<1e12?1e3:1)):new Date(e);return Number.isNaN(a.getTime())?"":a.toLocaleTimeString(void 0,{hour:"numeric",minute:"2-digit"})}function Ue(t){let e=t.coverage||[];if(!e.length)return t.sources_checked&&t.sources_checked.length?`${t.sources_checked.length} sources`:"";let a=e.filter(n=>n.status==="complete").length;return a===e.length?`${a} ${a===1?"source":"sources"} checked`:`${a} of ${e.length} sources checked`}function Ye({runs:t,error:e,loading:a,reload:n}){let{today:o}=H(),[i,s]=p.useState("waiting");if(e&&e.code==="not_found")return p.createElement(oe,{icon:"inbox",title:"Discovery is not available yet",text:"This version of Alchemy Task has no discovery runs to show. Update the plugin to review discovery here."});if(!t&&a)return p.createElement("div",{className:"at-loading"},p.createElement(Z,{size:18}));if(e&&!t)return p.createElement(oe,{icon:"alert",title:"Could not load discovery",text:F(e),action:p.createElement(Y,{onClick:n},"Try again")});let r=t||[];if(!r.length)return p.createElement(oe,{icon:"spark",title:"No discovery runs yet",text:p.createElement(p.Fragment,null,"Discovery reads the sources you choose and proposes tasks. To start one, ask Hermes:",p.createElement("br",null),p.createElement("q",null,"Set up a daily digest from my email and Slack at 7 AM."))});let u=d=>(d.summary?d.summary.pending:(d.proposals||[]).filter(y=>y.state==="pending").length)>0||(d.conflicts||[]).length||(d.failures||[]).length,l=i==="waiting"?r.filter(u):r,g=r[0];return p.createElement("div",{className:"at-scroll at-disco"},p.createElement("div",{className:"at-disco-inner"},p.createElement("div",{className:"at-disco-bar"},p.createElement("h1",{className:"at-period"},"Discovery"),p.createElement("span",{className:"at-flex"}),p.createElement(Ut,{label:"Show",value:i,onChange:s,options:[{value:"waiting",label:"Waiting for you"},{value:"all",label:"All runs"}]}),p.createElement(G,{icon:"refresh",label:"Refresh",onClick:n})),l.length?null:p.createElement("div",{className:"at-caughtup"},p.createElement(A,{name:"check",size:18}),p.createElement("div",null,p.createElement("div",{className:"at-caughtup-title"},"All caught up"),p.createElement("div",{className:"at-muted"},"Last run: ",qe(g.stream),", ",W(g.day,o)," ",re(g)))),l.map(d=>p.createElement(ka,{key:d.run_id,run:d,filter:i,reload:n}))))}function oe({icon:t,title:e,text:a,action:n}){return p.createElement("div",{className:"at-scroll at-disco"},p.createElement("div",{className:"at-emptystate"},p.createElement("span",{className:"at-emptystate-icon"},p.createElement(A,{name:t,size:22})),p.createElement("h2",null,e),p.createElement("p",null,a),n))}function ka({run:t,filter:e,reload:a}){let{today:n}=H(),o=t.proposals||[],i=e==="waiting"?o.filter(l=>l.state==="pending"):o,s=(t.outcomes||[]).filter(l=>l.status!=="noop"),r=[...(t.conflicts||[]).map(l=>({...l,kind:"conflict"})),...t.failures||[]],u=t.mode&&t.mode!=="production";return p.createElement("article",{className:"at-run"},p.createElement("header",{className:"at-run-head"},p.createElement("div",null,p.createElement("div",{className:"at-run-title"},qe(t.stream)),p.createElement("div",{className:"at-run-sub"},p.createElement("span",null,W(t.day,n),re(t)?` \xB7 ${re(t)}`:""),Ue(t)?p.createElement("span",{className:E(t.degraded&&"is-late")},Ue(t)):null,u?p.createElement("span",{className:"at-badge"},"Test run"):null)),p.createElement("span",{className:"at-flex"}),t.summary&&t.summary.pending?p.createElement("span",{className:"at-count is-accent"},t.summary.pending," waiting"):null),i.length?p.createElement("div",{className:"at-proposals"},i.map(l=>p.createElement(Da,{key:l.proposal_id,p:l,run:t,reload:a,readOnly:u}))):e==="all"&&!o.length?p.createElement("div",{className:"at-run-none"},"No new proposals in this run."):null,s.length?p.createElement(pt,{title:"Updated automatically",count:s.length,className:"at-run-fold"},s.map(l=>p.createElement(Na,{key:l.unit_id,o:l,run:t,reload:a}))):null,r.length?p.createElement(pt,{title:"Needs attention",count:r.length,tone:"late",className:"at-run-fold",defaultOpen:!0},r.map((l,g)=>p.createElement("div",{key:g,className:"at-attn"},p.createElement(A,{name:"alert",size:14}),p.createElement("div",null,p.createElement("div",{className:"at-attn-title"},l.title||(l.kind==="conflict"?"Several tasks match one item":"Research follow-up")),p.createElement("div",{className:"at-muted"},l.kind==="conflict"?"Nothing was changed. Ask Hermes which task this belongs to.":l.reason))))):null,p.createElement(pt,{title:"Run details",className:"at-run-fold is-quiet"},p.createElement("div",{className:"at-details"},(t.coverage||[]).map((l,g)=>p.createElement("div",{key:g,className:"at-detail-row"},p.createElement("span",{className:E("at-statusdot",l.status==="complete"?"is-ok":"is-late")}),p.createElement("span",{className:"at-flex"},l.source_key||l.source||"Source"),p.createElement("span",{className:"at-muted"},l.status==="complete"?"Checked":l.status||"Unknown"))),p.createElement("div",{className:"at-detail-row"},p.createElement("span",{className:"at-muted"},"Run"),p.createElement("span",{className:"at-flex"}),p.createElement("span",{className:"at-mono"},String(t.run_id).slice(0,12))),t.delivery&&t.delivery.state?p.createElement("div",{className:"at-detail-row"},p.createElement("span",{className:"at-muted"},"Digest"),p.createElement("span",{className:"at-flex"}),p.createElement("span",null,wa(t.delivery.state))):null)))}var wa=t=>({delivered:"Sent",host_pending:"Sent by Hermes",prepared:"Prepared",not_prepared:"Not sent",unknown:"Unknown",inflight:"Sending"})[t]||t;function Na({o:t,run:e,reload:a}){let{actions:n,api:o}=H(),i=lt(),[s,r]=p.useState(!1),u=async()=>{r(!0);try{await o.resume(e.run_id,t.unit_id),await a()}catch(g){i(F(g),{tone:"error"})}r(!1)},l=t.status==="complete";return p.createElement("div",{className:"at-outcome"},p.createElement("span",{className:E("at-statusdot",l?"is-ok":"is-late")}),p.createElement("button",{type:"button",className:"at-outcome-title",onClick:()=>t.task_id&&n.open(t.task_id)},t.title),p.createElement("span",{className:"at-flex"}),l?p.createElement("span",{className:"at-muted"},"Updated"):t.resume_action?p.createElement(Y,{size:"sm",onClick:u,disabled:s},s?"Finishing\u2026":"Finish update"):p.createElement("span",{className:"at-muted"},t.status))}function Da({p:t,run:e,reload:a,readOnly:n}){let{api:o,actions:i,today:s,meta:r,store:u}=H(),l=lt(),g=it(),d=t.targets||[],y=t.kind==="selection"||d.length>1,[k,f]=p.useState(t.kind==="new"||!d.length?"create":"update"),[D,b]=p.useState(d.length===1?d[0].task_id:null),T=(r.streams||{})[e.stream]||[],[z,v]=p.useState(t.due||t.due_hint||s),[N,S]=p.useState(t.area||(T.length===1?T[0]:r.default_area)||""),[_,L]=p.useState(null),[J,nt]=p.useState(!1);if(t.state==="approved"||t.state==="complete"){let x=t.result||{},M=t.state==="complete"||x.state==="complete";return p.createElement("div",{className:"at-prop is-resolved"},p.createElement("span",{className:E("at-statusdot",M?"is-ok":"is-late")}),p.createElement("span",{className:"at-prop-resolved"},x.operation==="updated"?"Updated":"Created"," ",p.createElement("button",{type:"button",className:"at-linkish",onClick:()=>x.task_id&&i.open(x.task_id)},x.title||t.title)),p.createElement("span",{className:"at-flex"}),M?p.createElement("span",{className:"at-muted"},t.ref):p.createElement("span",{className:"at-muted"},"Saving\u2026"))}if(t.state==="dismissed"||J)return p.createElement("div",{className:"at-prop is-resolved is-dismissed"},p.createElement("span",{className:"at-prop-resolved"},t.title),p.createElement("span",{className:"at-flex"}),p.createElement("span",{className:"at-muted"},"Dismissed"));let B=async x=>{if(x==="create"&&!N){l("Pick an area first.",{tone:"error"});return}let M=d.find(Q=>Q.task_id===D);if(x==="update"&&!M){l("Pick the task to update.",{tone:"error"});return}let $=x==="create"?{choice:x,due:z,area:N}:{choice:x,target_task_id:M.task_id,expected_revision:M.revision};t.expired&&($.allow_expired=!0),L(x);try{let Et=(await o.approve(t.proposal_id,$)).receipt||{};l(x==="create"?"Task created":"Task updated",Et.task_id?{action:{label:"Open",run:()=>i.open(Et.task_id)}}:{}),await a(),u.refresh()}catch(Q){l(F(Q),{tone:"error"}),(Q.code==="already_resolved"||Q.code==="stale_revision")&&a()}L(null)},j=async()=>{L("dismiss");try{await o.dismiss(t.proposal_id),nt(!0),l("Proposal dismissed"),a()}catch(x){l(F(x),{tone:"error"})}L(null)},Mt=x=>g.open(x.currentTarget,M=>p.createElement(St,{value:z,today:s,onPick:v,close:M}),{width:300}),ht=x=>g.open(x.currentTarget,M=>p.createElement(et,{close:M,items:(r.areas||[]).map($=>({label:$,icon:$===N?"check":void 0,run:()=>S($)}))}),{width:200}),xt=[].concat(t.new_information||[]).filter(Boolean),wt=[].concat(t.source_links||[]).filter(Boolean),ut=t.research_disposition==="uncertain";return p.createElement("div",{className:E("at-prop",t.expired&&"is-expired")},p.createElement("div",{className:"at-prop-head"},p.createElement("span",{className:"at-prop-ref"},t.ref),p.createElement("h3",{className:"at-prop-title"},t.title),p.createElement(G,{icon:"x",label:"Dismiss",className:"at-prop-dismiss",onClick:j,disabled:!!_||n})),t.current_understanding?p.createElement("p",{className:"at-prop-text"},t.current_understanding):null,t.substantive_next_action?p.createElement("div",{className:"at-prop-next"},p.createElement("span",{className:"at-prop-label"},"Next"),p.createElement("span",null,t.substantive_next_action)):null,ut?p.createElement("div",{className:"at-prop-uncertain"},p.createElement(A,{name:"alert",size:14}),p.createElement("span",null,[].concat(t.uncertainty||[]).join(" ")||"Hermes was not sure about this one. Check it before you add it.")):null,wt.length?p.createElement("div",{className:"at-prop-links"},wt.slice(0,4).map((x,M)=>p.createElement(Sa,{key:M,href:x}))):null,d.length?p.createElement("div",{className:E("at-prop-targets",k==="create"&&"is-muted")},p.createElement("div",{className:"at-prop-label"},y?"Could update one of these tasks":"May update an existing task"),d.map(x=>p.createElement("label",{key:x.task_id,className:E("at-target",D===x.task_id&&k==="update"&&"is-on")},y?p.createElement("input",{type:"radio",name:t.proposal_id,checked:D===x.task_id&&k==="update",onChange:()=>{b(x.task_id),f("update")}}):p.createElement(A,{name:"arrowR",size:14}),p.createElement("span",{className:"at-target-main"},p.createElement("span",{className:"at-target-title"},x.title),p.createElement("span",{className:"at-target-meta"},x.area?p.createElement(p.Fragment,null,p.createElement(st,{area:x.area}),x.area):null,V(x)?p.createElement("span",null,W(V(x),s)):null,x.status&&x.status!=="open"?p.createElement("span",null,x.status):null)),p.createElement("button",{type:"button",className:"at-link",onClick:M=>{M.preventDefault(),i.open(x.task_id)}},"Open"))),xt.length?p.createElement("div",{className:"at-prop-addition"},p.createElement("span",{className:"at-prop-label"},"Would add"),p.createElement("ul",null,xt.map((x,M)=>p.createElement("li",{key:M},x)))):null):xt.length?p.createElement("ul",{className:"at-prop-list"},xt.map((x,M)=>p.createElement("li",{key:M},x))):null,p.createElement("div",{className:"at-prop-actions"},k==="create"?p.createElement(p.Fragment,null,p.createElement("button",{type:"button",className:"at-field",onClick:Mt},p.createElement(A,{name:"cal",size:14}),p.createElement("span",null,W(z,s))),p.createElement("button",{type:"button",className:E("at-field",!N&&"is-late"),onClick:ht},p.createElement(st,{area:N}),p.createElement("span",null,N||"Pick area")),p.createElement("span",{className:"at-flex"}),d.length?p.createElement(Y,{variant:"ghost",size:"sm",onClick:()=>f("update"),disabled:!!_},"Update instead"):null,p.createElement(Y,{variant:"primary",size:"sm",icon:"plus",onClick:()=>B("create"),disabled:!!_||n},_==="create"?"Creating\u2026":"Create task")):p.createElement(p.Fragment,null,p.createElement(Y,{variant:"ghost",size:"sm",onClick:()=>f("create"),disabled:!!_},"Create new instead"),p.createElement("span",{className:"at-flex"}),p.createElement(Y,{variant:"primary",size:"sm",icon:"check",onClick:()=>B("update"),disabled:!!_||!D||n},_==="update"?"Updating\u2026":y?"Update selected":"Update task"))),t.expired?p.createElement("div",{className:"at-prop-foot at-muted"},"Expired ",W(t.expires,s).toLowerCase(),". You can still add it."):null)}function Sa({href:t}){let e=t;try{let n=new URL(t).host.replace(/^www\./,"");e=/slack/.test(n)?"Slack":/mail\.google|gmail/.test(n)?"Gmail":/notion/.test(n)?"Notion":/github/.test(n)?"GitHub":n}catch{}return p.createElement("a",{className:"at-srclink",href:t,target:"_blank",rel:"noreferrer noopener"},p.createElement(A,{name:"link",size:12}),e)}import h from"react";var We=[["daily","Every day"],["weekdays","Weekdays"],["every 4 hours","Every 4 hours"],["every 3 hours","Every 3 hours"],["every 2 hours","Every 2 hours"],["hourly","Every hour"]],se=t=>t==="daily"||t==="weekdays";function Ve(t){let e=String(t||"").trim().toLowerCase().match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/);if(!e)return"07:00";let a=Number(e[1])%24;return e[3]==="pm"&&a<12&&(a+=12),e[3]==="am"&&a===12&&(a=0),`${String(a).padStart(2,"0")}:${e[2]||"00"}`}function Ca(t){let[e,a]=t.split(":").map(Number);return`${(e+11)%12+1}:${String(a).padStart(2,"0")} ${e<12?"AM":"PM"}`}function ie({onClose:t,inline:e,narrow:a}){let{api:n}=H(),[o,i]=h.useState(null),[s,r]=h.useState(null),u=h.useCallback(()=>(r(null),n.settings().then(i,r)),[n]);h.useEffect(()=>{u()},[u]);let l=o?h.createElement(za,{data:o,reload:u}):s?h.createElement("div",{className:"at-panel-empty"},h.createElement(A,{name:"alert",size:20}),h.createElement("p",null,F(s)),h.createElement(Y,{onClick:u},"Try again")):h.createElement("div",{className:"at-panel-empty"},h.createElement(Z,{size:18}));return e?h.createElement("div",{className:"at-settings-inline"},l):h.createElement("aside",{className:E("at-panel",a?"is-sheet":"is-side","at-settings"),"aria-label":"Settings"},h.createElement("div",{className:"at-panel-bar"},h.createElement("span",{className:"at-panel-heading"},"Settings"),h.createElement("span",{className:"at-flex"}),h.createElement(G,{icon:"x",label:"Close",onClick:t})),h.createElement("div",{className:"at-panel-body at-scroll"},l))}function za({data:t,reload:e}){let a=t.streams||[],n=t.tasks||{};return h.createElement("div",{className:"at-settings-body"},h.createElement("section",{className:"at-set-sec"},h.createElement("h3",null,"Discovery"),h.createElement("p",{className:"at-muted"},"When each discovery stream reads its sources and proposes tasks."),a.length?a.map(o=>h.createElement(Ta,{key:o.name,s:o,reload:e})):h.createElement("div",{className:"at-set-empty"},"No streams yet. Ask Hermes: ",h.createElement("q",null,"Set up a daily digest from my email at 7 AM."))),h.createElement("section",{className:"at-set-sec"},h.createElement("h3",null,"Tasks"),h.createElement(Ea,{t:n,reload:e})),h.createElement("section",{className:"at-set-sec"},h.createElement("h3",null,"Sync and storage"),h.createElement("div",{className:"at-set-grid"},h.createElement("span",{className:"at-muted"},"Workspace"),h.createElement("span",{className:"at-mono at-break"},n.workspace_root||"Not set up"),h.createElement("span",{className:"at-muted"},"Time zone"),h.createElement("span",null,n.timezone||"Hermes default"),t.sync&&t.sync.git?h.createElement(h.Fragment,null,h.createElement("span",{className:"at-muted"},"Git"),h.createElement("span",null,t.sync.git)):null,t.sync&&t.sync.reminders?h.createElement(h.Fragment,null,h.createElement("span",{className:"at-muted"},"iOS Reminders"),h.createElement("span",null,t.sync.reminders)):null),h.createElement("p",{className:"at-muted at-set-hint"},"To change sources, accounts or areas, ask Hermes in chat, for example ",h.createElement("q",null,"add my team Slack channel to the work digest"),".")))}function Ta({s:t,reload:e}){let{api:a}=H(),n=lt(),o=it(),[i,s]=h.useState(t.frequency||"daily"),[r,u]=h.useState(Ve(t.time||"7 AM")),[l,g]=h.useState(null),d=i!==(t.frequency||"daily")||se(i)&&r!==Ve(t.time||"7 AM"),y=async()=>{g("save");try{let b=await a.patchStream(t.name,se(i)?{frequency:i,time:Ca(r)}:{frequency:i});n(b.message||"Schedule updated"),await e()}catch(b){n(F(b),{tone:"error"})}g(null)},k=async()=>{g("run");try{let b=await a.runStream(t.name);n(b.message||"Discovery run started")}catch(b){n(F(b),{tone:"error"})}g(null)},f=b=>o.open(b.currentTarget,T=>h.createElement(et,{close:T,items:We.map(([z,v])=>({label:v,icon:z===i?"check":void 0,run:()=>s(z)}))}),{width:200}),D=t.setup_blocked_reason||(t.activation_state&&!/active|ok|ready/i.test(t.activation_state)?t.activation_state:"");return h.createElement("div",{className:"at-stream"},h.createElement("div",{className:"at-stream-head"},h.createElement("div",null,h.createElement("div",{className:"at-stream-name"},String(t.name).replace(/\b\w/g,b=>b.toUpperCase())),h.createElement("div",{className:"at-muted"},(t.areas||[]).map(b=>h.createElement("span",{key:b,className:"at-inline-area"},h.createElement(st,{area:b}),b)),t.last_run?h.createElement("span",null," \xB7 last ran ",Ma(t.last_run)):null)),h.createElement("span",{className:"at-flex"}),h.createElement(Y,{size:"sm",variant:"ghost",icon:"play",onClick:k,disabled:!!l},l==="run"?"Starting\u2026":"Run now")),h.createElement("div",{className:"at-stream-sched"},h.createElement("button",{type:"button",className:"at-field",onClick:f},h.createElement(A,{name:"clock",size:14}),h.createElement("span",null,(We.find(([b])=>b===i)||[0,i])[1]),h.createElement(A,{name:"chevD",size:13})),se(i)?h.createElement("label",{className:"at-field at-timefield"},h.createElement("span",{className:"at-muted"},"at"),h.createElement("input",{type:"time",value:r,step:300,onChange:b=>u(b.target.value||r)})):null,t.timezone?h.createElement("span",{className:"at-muted at-tz"},t.timezone.replace(/_/g," ")):null,h.createElement("span",{className:"at-flex"}),d?h.createElement(Y,{size:"sm",variant:"primary",onClick:y,disabled:!!l},l==="save"?"Saving\u2026":"Save"):null),(t.sources||[]).length?h.createElement("div",{className:"at-stream-sources"},(t.sources||[]).map(b=>h.createElement("span",{key:b.name,className:"at-chip",title:b.scope},b.name))):null,D?h.createElement("div",{className:"at-banner at-tone-late"},h.createElement(A,{name:"alert",size:14}),h.createElement("span",null,D)):null)}function Ma(t){let e=typeof t=="number"?new Date(t*(t<1e12?1e3:1)):new Date(t);if(Number.isNaN(e.getTime()))return"";let a=Math.round((Date.now()-e.getTime())/6e4);return a<60?`${Math.max(1,a)} min ago`:a<1440?`${Math.round(a/60)} h ago`:e.toLocaleDateString(void 0,{month:"short",day:"numeric"})}function Ea({t,reload:e}){let{api:a,meta:n}=H(),o=lt(),i=it(),s=async u=>{try{await a.patchTaskSettings(u),o("Saved"),await e()}catch(l){o(F(l),{tone:"error"})}};return h.createElement("div",{className:"at-set-grid"},h.createElement("span",{className:"at-muted"},"Default area"),h.createElement("span",null,h.createElement("button",{type:"button",className:"at-field",onClick:u=>i.open(u.currentTarget,l=>h.createElement(et,{close:l,items:(n.areas||[]).map(g=>({label:g,icon:g===t.default_area?"check":void 0,run:()=>s({default_area:g})}))}),{width:200})},h.createElement(st,{area:t.default_area}),h.createElement("span",null,t.default_area||"None"),h.createElement(A,{name:"chevD",size:13}))),h.createElement("span",{className:"at-muted"},"Research new tasks"),h.createElement("span",null,h.createElement("button",{type:"button",role:"switch","aria-checked":!!t.research_by_default,className:E("at-switch",t.research_by_default&&"is-on"),onClick:()=>s({research_by_default:!t.research_by_default})},h.createElement("i",null))))}var _a=720,$a=3e4;function le(t){return C.createElement(Ce,null,C.createElement(La,{...t}))}function La({transport:t,host:e,initialView:a,settingsOnly:n}){let o=t,i=lt(),s=C.useRef(null),u=ke(s)<_a,l=C.useMemo(()=>be(o),[o]),g=kt(l,Pa),d=kt(l,Aa),[y,k]=C.useState(null),[f,D]=C.useState(null),[b,T]=C.useState(a==="discovery"?"discovery":"tasks"),[z,v]=C.useState(a==="settings"),[N,S]=C.useState(null),[_,L]=ye("prefs",{view:null,area:"",hideDone:!1}),J=_,nt=C.useCallback(I=>L(U=>({...U,...I})),[L]),[B,j]=C.useState(null),[Mt,ht]=C.useState(null),[xt,wt]=C.useState(!1),ut=C.useCallback(()=>o.meta().then(I=>{k(I),D(null),l.setToday(I.today)},D),[o,l]),x=C.useCallback(async()=>{wt(!0);try{let I=await o.runs();j(I.runs||[]),ht(null)}catch(I){ht(I)}wt(!1)},[o]);C.useEffect(()=>{ut(),x()},[ut,x]),C.useEffect(()=>{let I=()=>{ut(),l.refresh(),x()},U=setInterval(()=>{document.visibilityState==="visible"&&I()},$a);return window.addEventListener("focus",I),()=>{clearInterval(U),window.removeEventListener("focus",I)}},[ut,x,l]),C.useEffect(()=>{let I=U=>{let R=U.detail;(R==="discovery"||R==="tasks")&&T(R),R==="settings"&&v(!0)};return window.addEventListener("alchemy-task:open",I),()=>window.removeEventListener("alchemy-task:open",I)},[]);let M=C.useMemo(()=>{let I=P=>P.status==="done"||P.status==="cancelled",U=P=>i(F(P),{tone:"error"}),R=P=>l.mutate(P.task_id,{status:"done",completed:l.getState().today},()=>o.complete(P.task_id)),Nt=P=>l.mutate(P.task_id,{status:"open",completed:null},()=>o.reopen(P.task_id)),Ct=(P,q,tt)=>l.mutate(P.task_id,{scheduled:q,due:tt},()=>o.patch(P.task_id,q===tt?{date:q}:{scheduled:q,due:tt,keep_separate:!0}));return{open:P=>S(P),async toggle(P){try{I(P)?(await Nt(P),i("Marked not done",{undo:()=>R(P).catch(U)})):(await R(P),i(`Done: ${P.title}`,{undo:()=>Nt(P).catch(U)}))}catch(q){U(q)}},async move(P,q){let tt={scheduled:P.scheduled||null,due:P.due||null};if(!(V(P)===q&&(!P.due||P.due===q)))try{await Ct(P,q,q),i(`Moved to ${W(q,l.getState().today)}`,{undo:()=>Ct({...P,scheduled:q,due:q},tt.scheduled||tt.due,tt.due||tt.scheduled).catch(U)})}catch(K){U(K)}},async moveMany(P,q){let tt=P.slice(),K=0;for(let Dt of tt)try{await Ct(Dt,q,q),K++}catch(jt){U(jt);break}K&&i(`Moved ${K} ${K===1?"task":"tasks"} to ${W(q,l.getState().today).toLowerCase()}`,{undo:async()=>{for(let Dt of tt.slice(0,K))try{await Ct({...Dt,scheduled:q,due:q},Dt.scheduled||Dt.due,Dt.due||Dt.scheduled)}catch(jt){U(jt);break}}})},async create({title:P,date:q,area:tt}){try{let K=await o.create({title:P,date:q,area:tt});return K.task&&l.put(K.task),i(K.task&&K.task.research==="pending"?"Added. Hermes is researching it.":"Added",{action:K.task?{label:"Open",run:()=>S(K.task.task_id)}:void 0}),!0}catch(K){return U(K),!1}}}},[o,l,i]),$=C.useCallback((I,U)=>M.move(I,U),[M]),Q=He(B),Et=C.useMemo(()=>({api:o,store:l,meta:y||{},today:g||y&&y.today,prefs:J,setPrefs:nt,actions:M,selectedId:N,narrow:u,host:e}),[o,l,y,g,J,nt,M,N,u,e]);C.useLayoutEffect(()=>{let I=s.current;if(!I)return;let U=()=>{let Nt=getComputedStyle(document.documentElement);Nt.getPropertyValue("--color-foreground").trim()||Nt.getPropertyValue("--ui-text-primary").trim()||(I.style.removeProperty("--at-fg"),I.style.setProperty("--at-fg",getComputedStyle(I).color))};U();let R=new MutationObserver(U);return R.observe(document.documentElement,{attributes:!0,attributeFilter:["class","style","data-theme"]}),()=>R.disconnect()},[]);let[pe,ce]=C.useState(null);C.useLayoutEffect(()=>{let I=s.current;if(!I||n)return;let U=()=>{let R=I.parentElement,Nt=R?R.getBoundingClientRect().height:0;if(e==="desktop"&&Nt>300){ce(null);return}let Ct=I.getBoundingClientRect().top,ue=window.visualViewport&&window.visualViewport.height||window.innerHeight;ce(Math.max(420,Math.round(ue-Math.max(0,Ct)-8)))};return U(),window.addEventListener("resize",U),window.visualViewport&&window.visualViewport.addEventListener("resize",U),()=>{window.removeEventListener("resize",U),window.visualViewport&&window.visualViewport.removeEventListener("resize",U)}},[e,n]);let Ke=!y&&f?C.createElement(Fe,{icon:"alert",title:"Alchemy Task is not responding",text:F(f)}):!y||!Et.today?C.createElement("div",{className:"at-loading"},C.createElement(Z,{size:18})):y.configured===!1?C.createElement(Fe,{icon:"list",title:"Set up your tasks",text:C.createElement(C.Fragment,null,"Alchemy Task is installed but not set up yet. In chat, ask Hermes: ",C.createElement("q",null,"Set up my tasks."))}):n?C.createElement(ie,{inline:!0,narrow:u}):C.createElement(C.Fragment,null,C.createElement("nav",{className:"at-appbar"},C.createElement("div",{className:"at-tabs",role:"tablist"},C.createElement("button",{type:"button",role:"tab","aria-selected":b==="tasks",className:E("at-tab",b==="tasks"&&"is-on"),onClick:()=>T("tasks")},"Tasks"),C.createElement("button",{type:"button",role:"tab","aria-selected":b==="discovery",className:E("at-tab",b==="discovery"&&"is-on"),onClick:()=>T("discovery")},"Discovery",Q?C.createElement("span",{className:"at-badge-dot"},Q):null)),C.createElement("span",{className:"at-flex"}),d?C.createElement(Z,{size:12}):null,C.createElement(G,{icon:"gear",label:"Settings",className:E(z&&"is-on"),onClick:()=>{S(null),v(I=>!I)}})),C.createElement("div",{className:E("at-main",N&&!u&&"has-panel",z&&!u&&"has-panel")},b==="tasks"?C.createElement(Ee,{narrow:u}):C.createElement(Ye,{runs:B,error:Mt,loading:xt,reload:x})),N?C.createElement(Oe,{id:N,narrow:u,onClose:()=>S(null)}):null,z&&!N?C.createElement(ie,{narrow:u,onClose:()=>v(!1)}):null);return C.createElement(Rt.Provider,{value:Et},C.createElement("div",{ref:s,className:E("at-root at-vars",u&&"is-narrow",`host-${e}`,n&&"is-settings-only"),style:pe?{height:pe}:void 0},C.createElement(xe,{onDrop:$},C.createElement(De,{rootRef:s},Ke))))}var Pa=t=>t.today,Aa=t=>t.loading>0;function Fe({icon:t,title:e,text:a}){return C.createElement("div",{className:"at-emptystate is-full"},C.createElement("span",{className:"at-emptystate-icon"},C.createElement(A,{name:t,size:22})),C.createElement("h2",null,e),C.createElement("p",null,a))}var je=`/* Alchemy Task UI. Every color comes from the host theme: the web dashboard's --color-* tokens or the
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
.at-row.is-late:not(.is-done) .at-row-title { color: var(--at-fg); }
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
.at-overdue .at-link { color: var(--at-late); display: none; }
.at-overdue.is-open .at-link, .at-overdue .at-disc-head:hover .at-link, .at-root.is-narrow .at-overdue .at-link { display: inline; }
.at-disc-head { min-width: 0; }
.at-disc-title { white-space: nowrap; }
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
.at-week-body { flex: 1; min-height: 0; overflow-x: hidden; }
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
  min-width: 200px; max-width: 320px; rotate: -1.5deg;
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
  display: block; width: calc(100% - 26px); margin-left: 26px !important; resize: none; overflow: hidden; border: 0; outline: none; background: transparent;
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
.at-root.is-narrow .at-summary-input { margin-left: -10px !important; width: calc(100% + 20px); }
.at-root.is-narrow .at-prop-addition { flex-direction: column; gap: 4px; }

@media (prefers-reduced-motion: reduce) {
  .at-root *, .at-pop, .at-panel, .at-toast { animation: none !important; transition: none !important; }
}
`;var Ge="alchemy-task-ui-styles",An={id:"alchemy-task",name:"Alchemy Task",register(t){if(!document.getElementById(Ge)){let i=document.createElement("style");i.id=Ge,i.textContent=je,document.head.appendChild(i),t.onDispose(()=>i.remove())}let e=ve((i,s,r)=>t.rest(s,r===void 0?{method:i}:{method:i,body:r})),a=null,n=i=>{a=i,Ia.navigate("/alchemy-task"),window.dispatchEvent(new CustomEvent("alchemy-task:open",{detail:i}))},o=()=>de.createElement(le,{transport:e,host:"desktop",initialView:a});t.registerMany([{id:"page",area:Oa,data:{path:"/alchemy-task"},render:()=>de.createElement(o,null)},{id:"nav",area:Ua,data:{path:"/alchemy-task",label:"Tasks",codicon:"checklist"}},{id:"open-tasks",area:Xe,data:{id:"alchemy-task-open",label:"Open tasks",keywords:["tasks","today","calendar","alchemy"],run:()=>n("tasks")}},{id:"open-discovery",area:Xe,data:{id:"alchemy-task-discovery",label:"Review discovery proposals",keywords:["discovery","digest","proposals","alchemy"],run:()=>n("discovery")}}]),typeof t.registerSettingsPage=="function"&&t.registerSettingsPage({id:"settings",title:"Alchemy Task",icon:"checklist",render:()=>de.createElement(le,{transport:e,host:"desktop",settingsOnly:!0})})}};export{An as default};
