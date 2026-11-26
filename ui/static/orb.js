/* The simplex noise function snoise() in the fragment shader below is based on webgl-noise
 * (https://github.com/stegu/webgl-noise), description: Array and textureless GLSL 2D/3D/4D simplex noise functions.
 * Author: Ian McEwan, Ashima Arts. Maintainer: Stefan Gustavson.
 * Copyright (C) 2011 by Ashima Arts (Simplex noise)
 * Copyright (C) 2011-2016 by Stefan Gustavson (Classic noise and others)
 * Distributed under the MIT License:
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
 * documentation files (the "Software"), to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
 * permit persons to whom the Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all copies or substantial portions of
 * the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
 * WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
 * OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
 * OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 */
/* NuOrb-Orb: ein Fragment-Shader auf einem quadratischen Canvas (WebGL1, highp wenn vorhanden).
 * Wichtig: mediump ist auf Adreno/freedreno echtes fp16 (max ~65504) – die Simplex-Noise laeuft dort ueber
 * und liefert NaN -> unsichtbarer Orb. Deshalb highp, Selbsttest per readPixels und Fallback-Kette
 * WebGL -> Canvas 2D -> CSS-Orb ([data-orb]).
 * Nutzung ohne app.js: <canvas id="orb"> in .orb-wrap, Vorfahr mit data-orb="css" und data-state="…";
 * dann Orb.set({state: "idle"|"listening"|"thinking"|"speaking"|"offline"|"error", level: 0..1}), Orb.calm(true|false),
 * Orb.renderer ("webgl"|"2d"|"css"). data-state am Vorfahren steuert nur den CSS-Fallback – beides setzen.
 * Ausgelegt fuer Adreno 618: 2 Noise-Oktaven, adaptive Aufloesung, pausiert bei verdecktem Tab.
 * Fallback: Canvas 2D mit Verlaeufen. API: Orb.set({level, state}), Orb.calm(bool). */
(function () {
  "use strict";
  let canvas = document.getElementById("orb");
  if (!canvas) { window.Orb = { set() {}, calm() {}, get webgl() { return false; }, get renderer() { return "none"; } }; return; }
  // Zustands-/Fallback-Attribute (data-orb, --lvl) landen am naechsten Vorfahren mit data-orb, sonst #app/body.
  // Damit ist orb.js auch ohne app.js nutzbar (z. B. nuorb-admin).
  const appEl = canvas.closest("[data-orb]") || document.getElementById("app") || document.body;
  const STATES = { idle: 0, listening: 1, thinking: 2, speaking: 3, offline: 4, error: 5 };
  const target = { level: 0, listen: 0, think: 0, speak: 0, off: 0, err: 0 };
  const cur = { level: 0, listen: 0, think: 0, speak: 0, off: 0, err: 0 };
  let calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let running = true, t0 = performance.now(), last = 0, time = 0;
  let scale = Math.min(window.devicePixelRatio || 1, 2);
  let slowFrames = 0;

  const VERT = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
  const FRAG = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 uRes; uniform float uT, uLvl, uListen, uThink, uSpeak, uOff, uErr;
vec3 mod289(vec3 x){return x-floor(x*(1./289.))*289.;}
vec4 mod289(vec4 x){return x-floor(x*(1./289.))*289.;}
vec4 perm(vec4 x){return mod289(((x*34.)+1.)*x);}
vec4 tis(vec4 r){return 1.79284291400159-.85373472095314*r;}
float snoise(vec3 v){
 const vec2 C=vec2(1./6.,1./3.);const vec4 D=vec4(0.,.5,1.,2.);
 vec3 i=floor(v+dot(v,C.yyy));vec3 x0=v-i+dot(i,C.xxx);
 vec3 g=step(x0.yzx,x0.xyz);vec3 l=1.-g;vec3 i1=min(g.xyz,l.zxy);vec3 i2=max(g.xyz,l.zxy);
 vec3 x1=x0-i1+C.xxx;vec3 x2=x0-i2+C.yyy;vec3 x3=x0-D.yyy;i=mod289(i);
 vec4 p=perm(perm(perm(i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));
 float n_=.142857142857;vec3 ns=n_*D.wyz-D.xzx;vec4 j=p-49.*floor(p*ns.z*ns.z);
 vec4 x_=floor(j*ns.z);vec4 y_=floor(j-7.*x_);vec4 x=x_*ns.x+ns.yyyy;vec4 y=y_*ns.x+ns.yyyy;vec4 h=1.-abs(x)-abs(y);
 vec4 b0=vec4(x.xy,y.xy);vec4 b1=vec4(x.zw,y.zw);vec4 s0=floor(b0)*2.+1.;vec4 s1=floor(b1)*2.+1.;vec4 sh=-step(h,vec4(0.));
 vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
 vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);
 vec4 nm=tis(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));p0*=nm.x;p1*=nm.y;p2*=nm.z;p3*=nm.w;
 vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.);m=m*m;
 return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));}
void main(){
 vec2 p=(gl_FragCoord.xy-.5*uRes)/(.5*min(uRes.x,uRes.y));
 float r=length(p); float a=atan(p.y,p.x); float t=uT;
 float lvl=uLvl;
 vec3 cyan=vec3(.20,.85,1.);
 vec3 acc=mix(cyan,vec3(.48,.62,1.),uThink*.55);
 acc=mix(acc,vec3(1.,.70,.30),uErr);
 acc=mix(acc,vec3(.42,.47,.52),uOff);
 float energy=.35+.65*lvl+.25*uThink;
 energy*=1.-.55*uOff;
 float R=.50+.012*sin(t*1.1)+.07*lvl*(uListen+uSpeak)-.04*uOff;
 float n=snoise(vec3(p*1.3,t*.18));
 float n2=snoise(vec3(p*2.6+n*.35,t*.30+7.));
 float disp=(.010+.065*lvl+.022*uThink)*n;
 float d=r-(R+disp);
 float inside=smoothstep(.012,-.012,d);
 float q=clamp(r/R,0.,1.);
 float z=sqrt(max(0.,1.-q*q));
 float fres=pow(1.-z,2.2);
 float fil=pow(1.-abs(n2),12.);
 vec3 col=vec3(.004,.03,.05)*inside;
 col+=acc*(fres*1.05+fil*.38*energy*(1.-.6*fres)+.10*z*(.6+.4*n))*inside;
 col+=acc*pow(z,3.)*.22*energy*inside*(.8+.2*sin(t*.9));
 col+=vec3(.85,.97,1.)*pow(z,10.)*.10*energy*inside;
 float o=max(d,0.);
 col+=acc*(exp(-o*5.5)*(.34+.6*lvl)+exp(-o*22.)*.25)*(1.-.5*uOff)*(1.-inside);
 col+=acc*smoothstep(.014,0.,abs(d))*(.65+.35*lvl);
 // HUD-Ringe
 float rot=t*(.04+.9*uThink);
 float r1=smoothstep(.006,0.,abs(r-.78));
 float dash=smoothstep(.45,.55,fract(a*9.549+rot*3.));
 col+=acc*r1*(.16+.34*dash)*(1.-.4*uOff);
 float r2=smoothstep(.005,0.,abs(r-.88));
 float arc=smoothstep(.55,.9,sin(a-t*(.25+2.2*uThink)))+smoothstep(.75,.95,sin(-a*2.-t*(.15+1.4*uThink)))*uThink;
 col+=acc*r2*(.12+.75*arc*(.25+.75*max(uThink,uListen)));
 float tk=step(.82,fract(a*11.459))*smoothstep(.016,.008,abs(r-.955));
 col+=acc*tk*(.16+.4*uListen*lvl);
 float pr=fract(t*.45);
 col+=acc*smoothstep(.02,0.,abs(r-(R+.02+pr*.45)))*(1.-pr)*.5*uListen*(.3+lvl);
 float alpha=clamp(max(inside,max(col.r,max(col.g,col.b))*1.4),0.,1.);
 gl_FragColor=vec4(col,alpha);
}`;

  let gl = null, prog, U = {};
  try {
    gl = canvas.getContext("webgl", { premultipliedAlpha: false, antialias: false, alpha: true, powerPreference: "low-power" });
  } catch (e) { gl = null; }
  if (gl) {
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
    try {
      prog = gl.createProgram();
      gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(prog); gl.useProgram(prog);
      const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(prog, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      for (const n of ["uRes", "uT", "uLvl", "uListen", "uThink", "uSpeak", "uOff", "uErr"]) U[n] = gl.getUniformLocation(prog, n);
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    } catch (e) { console.warn("Orb: WebGL-Shader fehlgeschlagen, nutze 2D", e); gl = null; }
  }
  let ctx2d = null, frames = 0, checked = false;
  function cssOnly(reason) {
    console.warn("Orb: CSS-Fallback –", reason);
    gl = null; ctx2d = null; canvas.dataset.renderer = "css"; appEl.dataset.orb = "css";
  }
  function fallback2d(reason) {
    console.warn("Orb: Canvas-2D-Fallback –", reason);
    const c2 = document.createElement("canvas"); c2.id = "orb"; c2.setAttribute("aria-hidden", "true");
    canvas.replaceWith(c2); canvas = c2; gl = null; frames = 0; checked = false;
    try { ctx2d = canvas.getContext("2d"); } catch (e) { ctx2d = null; }
    if (!ctx2d) return cssOnly("kein 2D-Kontext");
    canvas.dataset.renderer = "2d"; ro.observe(canvas); resize();
  }
  // Selbsttest: in der Mitte muss nach dem Zeichnen deckende Farbe stehen
  function selfCheck() {
    checked = true;
    const w = canvas.width, h = canvas.height;
    try {
      if (gl) {
        const px = new Uint8Array(4);
        gl.readPixels(Math.floor(w / 2), Math.floor(h / 2), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
        if (px[3] < 128) return fallback2d("WebGL zeichnet nichts (Alpha " + px[3] + ")");
      } else if (ctx2d) {
        const d = ctx2d.getImageData(Math.floor(w / 2), Math.floor(h / 2), 1, 1).data;
        if (d[3] < 20) return cssOnly("Canvas 2D zeichnet nichts");
      }
      appEl.dataset.orb = "canvas";
    } catch (e) { if (gl) fallback2d("Selbsttest: " + e.message); else cssOnly("Selbsttest: " + e.message); }
  }
  if (!gl) { try { ctx2d = canvas.getContext("2d"); } catch (e) { ctx2d = null; } }
  canvas.dataset.renderer = gl ? "webgl" : ctx2d ? "2d" : "css";
  if (!gl && !ctx2d) cssOnly("kein Canvas");
  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); fallback2d("Kontext verloren"); });

  function resize() {
    const r = canvas.getBoundingClientRect();
    const w = Math.max(1, Math.round(r.width * scale)), h = Math.max(1, Math.round(r.height * scale));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  }
  const ro = new ResizeObserver(() => resize()); ro.observe(canvas);

  function draw2d(w, h) {
    const c = ctx2d, cx = w / 2, cy = h / 2, s = Math.min(w, h) / 2;
    c.clearRect(0, 0, w, h);
    const R = s * (0.5 + 0.07 * cur.level + 0.012 * Math.sin(time * 1.1));
    const col = cur.off > .5 ? "110,120,130" : cur.err > .5 ? "255,180,80" : "56,217,255";
    let g = c.createRadialGradient(cx, cy, R * .9, cx, cy, R * 1.9);
    g.addColorStop(0, `rgba(${col},${.25 + .4 * cur.level})`); g.addColorStop(1, `rgba(${col},0)`);
    c.fillStyle = g; c.fillRect(0, 0, w, h);
    g = c.createRadialGradient(cx, cy - R * .3, R * .1, cx, cy, R);
    g.addColorStop(0, `rgba(${col},.35)`); g.addColorStop(.7, "rgba(2,12,18,.95)"); g.addColorStop(1, `rgba(${col},.9)`);
    c.beginPath(); c.arc(cx, cy, R, 0, 7); c.fillStyle = g; c.fill();
    c.strokeStyle = `rgba(${col},.35)`; c.lineWidth = Math.max(1, s * .006);
    c.beginPath(); c.arc(cx, cy, s * .78, 0, 7); c.stroke();
    const a = time * (0.25 + 2.2 * cur.think);
    c.strokeStyle = `rgba(${col},.8)`; c.beginPath(); c.arc(cx, cy, s * .88, a, a + 1.1); c.stroke();
  }

  function frame(now) {
    if (!running) return;
    requestAnimationFrame(frame);
    const minDt = calm ? 1000 / 20 : 0;
    if (now - last < minDt) return;
    const dt = Math.min(0.1, (now - (last || now)) / 1000);
    // adaptive Aufloesung: bei dauerhaft langsamen Frames runterskalieren
    if (!calm && last && now - last > 24) { if (++slowFrames > 40 && scale > 1) { scale = Math.max(1, scale - 0.25); slowFrames = 0; resize(); } }
    else slowFrames = Math.max(0, slowFrames - 1);
    last = now;
    time += dt * (calm ? 0.25 : 1);
    const k = 1 - Math.pow(0.0015, dt);       // weiche Uebergaenge der Zustaende
    const kl = 1 - Math.pow(0.00002, dt);     // Pegel reagiert schneller
    for (const key in cur) cur[key] += (target[key] - cur[key]) * (key === "level" ? kl : k);
    const w = canvas.width, h = canvas.height;
    if ((++frames & 63) === 1) canvas.dataset.frames = String(frames);
    if (!gl && !ctx2d) return;
    try {
    if (gl) {
      gl.viewport(0, 0, w, h); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(U.uRes, w, h); gl.uniform1f(U.uT, time);
      gl.uniform1f(U.uLvl, Math.min(1, cur.level * (calm ? .5 : 1)));
      gl.uniform1f(U.uListen, cur.listen); gl.uniform1f(U.uThink, cur.think); gl.uniform1f(U.uSpeak, cur.speak);
      gl.uniform1f(U.uOff, cur.off); gl.uniform1f(U.uErr, cur.err);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    } else draw2d(w, h);
    if (!checked && frames >= 3 && w > 8) selfCheck();
    } catch (e) { if (gl) fallback2d("Zeichenfehler: " + e.message); else cssOnly("Zeichenfehler: " + e.message); }
  }

  document.addEventListener("visibilitychange", () => {
    running = !document.hidden;
    if (running) { last = 0; requestAnimationFrame(frame); }
  });
  resize(); requestAnimationFrame(frame);

  window.Orb = {
    set(o) {
      if (o.level !== undefined) { target.level = Math.max(0, Math.min(1, o.level)); appEl.style.setProperty("--lvl", target.level.toFixed(3)); }
      if (o.state !== undefined) {
        target.listen = o.state === "listening" ? 1 : 0;
        target.think = o.state === "thinking" ? 1 : 0;
        target.speak = o.state === "speaking" ? 1 : 0;
        target.off = o.state === "offline" ? 1 : 0;
        target.err = o.state === "error" ? 1 : 0;
        if (o.state !== "listening" && o.state !== "speaking") target.level = 0;
      }
    },
    calm(v) { calm = !!v; },
    get webgl() { return !!gl; },
    get renderer() { return canvas.dataset.renderer; },
    _forceFallback(kind) { if (kind === "css") cssOnly("Test"); else fallback2d("Test"); },
    get scale() { return scale; },
  };
})();
