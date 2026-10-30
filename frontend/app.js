// DATA: 지금 화면이 쓰는 검토 결과(서버가 읽은 사진, 또는 서버의 데모 데이터).
let DATA = null;
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const FLOW = ['upload','reading','review','months'];

let rows = [], history = [], shots = [];
// OPENING: 첫 거래 직전 잔액(서버가 사진에서 구한다). 결정: 미정 입금 인덱스 -> '수입' | '차감'
let OPENING = 0, 결정 = {};
let 여는줄 = null;   // 고치기 칸을 연 줄의 번호
let 초점 = null;     // 다시 그린 뒤 초점을 줄 곳(선택자). 없으면 초점이 있던 줄의 버튼으로 간다
// 통장 종류와 보고서 이름은 서버(passbook/classify.py)에서만 정한다. 화면은 받아서 그린다.
let 통장이름 = {};

// 서버의 데모 데이터를 받는다. 서버가 없거나(파일로 연 경우) 실패하면 null을 돌려준다.
// 확인 · 정산 판정도 서버에서만 하므로, 서버 없이 데모를 띄울 수는 없다.
async function fetchDemoReview(){
  try{
    const res = await fetch('/api/review');
    if(!res.ok) return null;
    return await res.json();
  }catch(_){ return null; }
}
// 사진이 실패했을 때 데모 숫자로 바꿔치기하지 않는다. 남의 숫자를 내 통장으로 착각한다.
// 그래서 {data} 또는 {error}를 돌려주고, 호출한 쪽이 안내한다.
const 연결오류 = () => location.protocol === 'file:'
  // 파일(index.html)을 직접 열면 '/api/...'가 file:// 경로가 되어 서버에 닿지 않는다.
  ? '이 화면은 파일로 열면 사진을 읽을 수 없어요. 프로그램(서버)을 켠 뒤 안내된 주소로 열어 주세요.'
  : '사진을 읽는 프로그램(서버)에 연결하지 못했습니다. 프로그램이 켜져 있는지 확인해 주세요.';
const 쉬기 = ms => new Promise(r => setTimeout(r, ms));
const 진행확인간격 = 1500;   // 사진을 읽는 동안 몇 장 읽었는지 서버에 묻는 간격(ms)

// 사진을 작업으로 맡기고, 끝날 때까지 1.5초마다 몇 장 읽었는지 묻는다.
async function readPhotos(files, onProgress){
  let res;
  try{
    const form = new FormData();
    [...files].forEach(f => form.append('files', f));
    res = await fetch('/api/jobs', {method:'POST', body:form});
  }catch(_){ return {error: 연결오류()}; }
  if(!res.ok){
    const detail = await res.json().then(b => b.detail, () => null);
    return {error:`사진을 읽지 못했습니다. ${typeof detail === 'string' ? detail : '다시 시도해 주세요.'}`};
  }
  const {id} = await res.json();
  for(;;){
    await 쉬기(진행확인간격);
    let job;
    try{
      const r = await fetch(`/api/jobs/${id}`);
      if(!r.ok) return {error:'사진을 읽는 중에 연결이 끊겼습니다. 사진을 다시 올려 주세요.'};
      job = await r.json();
    }catch(_){ return {error: 연결오류()}; }
    onProgress(job.읽음, job.전체);
    if(job.상태 === '완료') return {data: job.결과};
    if(job.상태 === '실패') return {error:`사진을 읽지 못했습니다. ${job.오류 || '다시 시도해 주세요.'}`};
  }
}

async function postSettlement(body){
  try{
    const res = await fetch('/api/settlement', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    if(!res.ok) return null;
    return await res.json();
  }catch(_){ return null; }
}

const $ = id => document.getElementById(id);
const won = n => '₩' + n.toLocaleString('ko-KR');
const num = n => n.toLocaleString('ko-KR');
const ymd = d => `${d.slice(0,4)}.${d.slice(4,6)}.${d.slice(6,8)}`;
const md  = d => `${+d.slice(4,6)}월 ${+d.slice(6,8)}일`;

// 고친 뒤 다시 판정한다. 잔액오독 · 거래누락 · 확인필요를 가르는 규칙은 서버(passbook/review.py)
// 한 곳에만 둔다. 화면이 따로 가지면 한쪽만 고쳤을 때 '확인할 곳'이 서로 달라진다.
// 서버에 닿지 않으면 null — 화면이 혼자 판정해 넘어가지 않는다.
async function review(list){
  const body = {시작잔액:OPENING,
    확인함: list.flatMap((r,i) => r.확인됨 ? [i] : []),
    items: list.map(r => ({date:r.date, 적요:r.적요||'', 사용내역:r.사용내역||'',
                           입금:r.입금, 지출:r.지출, 잔액:r.잔액}))};
  try{
    const res = await fetch('/api/recheck', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    if(!res.ok) return null;
    const {items} = await res.json();
    // 날짜 고르기 같은 화면 쪽 표시(새로추가 · 날짜확인 등)는 rows에 있으니 판정만 덧붙인다.
    return items.map((s,i) => ({...list[i], index:i, 상태:s.상태, 기대잔액:s.기대잔액}));
  }catch(_){ return null; }
}
const 판정오류 = '거래 확인은 프로그램(서버)이 켜져 있을 때만 할 수 있습니다. 프로그램이 켜져 있는지 확인해 주세요.';
// 날짜를 아직 고르지 않은 새 거래도 확인할 곳으로 센다. 날짜가 틀리면 다른 달·반기로 들어간다.
const 날짜미정 = x => x.새로추가 && !x.날짜확인;
const 남은확인 = items => items.filter(x => (x.상태!=='정상' && x.상태!=='확인함') || 날짜미정(x)).length;

/* ── 화면 전환 ────────────────────────────── */
function show(name){
  ['upload','reading','review','months'].forEach(s => $('s-'+s).hidden = (s !== name));
  const at = FLOW.indexOf(name);
  [...$('steps').children].forEach((el,i) => {
    el.classList.toggle('on', i === at);
    el.classList.toggle('past', i < at);
  });
  $('restart').hidden = (name === 'upload');
  window.scrollTo({top:0, behavior: REDUCED ? 'auto' : 'smooth'});
}

/* ── 1. 사진 고르기 ────────────────────────── */
const drop = $('drop');
['dragenter','dragover'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add('over'); }));
['dragleave','drop'].forEach(e => drop.addEventListener(e, () => drop.classList.remove('over')));
drop.addEventListener('drop', ev => { ev.preventDefault(); addShots(ev.dataTransfer.files); });
$('file').addEventListener('change', e => addShots(e.target.files));
$('year').value = new Date().getFullYear();
const picked = name => (document.querySelector(`input[name=${name}]:checked`) || {}).value;
const 준비됨 = () => shots.length > 0 && !!picked('account');
async function 통장목록(){
  let list;
  try{
    const res = await fetch('/api/accounts');
    if(!res.ok) throw new Error();
    list = await res.json();
  }catch(_){
    $('accounts').innerHTML = `<p class="tip error" role="alert" style="margin:0">${연결오류()}</p>`;
    return;
  }
  통장이름 = Object.fromEntries(list.map(a => [a.id, a.이름]));
  $('accounts').innerHTML = list.map(a =>
    `<label><input type="radio" name="account" value="${a.id}"><span>${a.이름}</span></label>`).join('');
  $('accounts').querySelectorAll('input').forEach(r => r.addEventListener('change', () => { $('start').disabled = !준비됨(); }));
}
통장목록();

function addShots(files){
  [...files].filter(f => f.type.startsWith('image/')).forEach(f => shots.push(f));
  $('shots').innerHTML = shots.map((f,i) =>
    `<figure class="shot"><img alt="올린 사진 ${i+1}" src="${URL.createObjectURL(f)}"><p>${i+1}장</p></figure>`).join('');
  $('start').disabled = !준비됨();
}
$('start').onclick = async () => {
  // 읽는 중 화면을 먼저 띄운다 — 실제 OCR은 수십 초~수 분 걸릴 수 있어서,
  // 그동안 화면이 멈춘 것처럼 보이면 안 된다. 서버 응답을 받은 뒤 결과를 재생한다.
  $('uploadError').hidden = true;
  enterReading(shots.length);
  const {data, error} = await readPhotos(shots, 진행표시);
  const 실패 = error || (!data.items.length &&
    '사진에서 거래를 하나도 읽지 못했습니다. 통장을 펴 놓고 더 가까이, 흔들리지 않게 다시 찍어 주세요.');
  if(실패){
    $('uploadError').textContent = 실패;
    $('uploadError').hidden = false;
    show('upload');
    return;
  }
  DATA = data;
  playPrinter();
};
$('demo').onclick = async () => {
  // 데모 데이터는 부식비 통장이다
  const 데모통장 = document.querySelector('input[name=account][value=부식비]');
  if(!picked('account') && 데모통장) 데모통장.checked = true;
  $('uploadError').hidden = true;
  enterReading(1);
  const data = await fetchDemoReview();
  if(!data){
    // 사진을 읽을 때와 같이 안내하고 올리기 화면으로 돌아간다.
    $('uploadError').textContent = 연결오류();
    $('uploadError').hidden = false;
    show('upload');
    return;
  }
  DATA = data;
  playPrinter();
};
$('backUpload').onclick = () => show('upload');
$('restart').onclick = () => { shots = []; $('shots').innerHTML = ''; $('start').disabled = !준비됨(); show('upload'); };

/* ── 2. 읽는 중 (도트 프린터처럼 한 줄씩 찍힌다) ── */
// 인식을 기다리는 동안 보여줄 화면. 서버 응답이 오기 전에도 바로 뜬다.
function enterReading(count){
  show('reading');
  $('readCount').textContent = `사진 ${count}장`;
  const printer = $('print'), tasks = [...$('tasks').children];
  tasks.forEach(t => t.className = '');
  tasks[0].classList.add('on');
  printer.innerHTML = `<div class="pending"><p id="readProgress" role="status" aria-live="polite">사진 ${count}장을 읽고 있어요. 잠시만 기다려 주세요.</p>
    <div class="progress" aria-hidden="true"><i id="readBar"></i></div></div>`;
}
// 서버가 알려 준 진행 상황을 보여준다. 다 읽은 장수만 세므로 첫 장이 끝나기 전에는 0장이다.
function 진행표시(읽음, 전체){
  const p = $('readProgress'), bar = $('readBar');
  if(!p || !bar) return;
  p.textContent = 읽음 < 전체 ? `사진 ${전체}장 중 ${읽음}장 읽었어요…` : `사진 ${전체}장을 다 읽었어요. 정리하는 중이에요…`;
  bar.style.width = `${Math.round(읽음 / 전체 * 100)}%`;
}
// 서버 결과(DATA)를 받은 뒤 한 줄씩 찍어 보여주고 검토 화면으로 넘어간다.
function playPrinter(){
  const printer = $('print'), tasks = [...$('tasks').children];
  printer.innerHTML = ''; tasks.forEach(t => t.className = '');

  const lines = DATA.items.map(x =>
    `${String(x.index+1).padStart(2)}  ${x.date}  ${(x.사용내역||'').padEnd(12)}  ` +
    `${x.지출?'-':'+'}${num(x.지출||x.입금).padStart(9)}  ${num(x.잔액).padStart(10)}`);

  if(REDUCED){
    // 읽은 글자가 들어가므로 마크업이 아니라 글자로 넣는다(아래 애니메이션과 같은 방식).
    printer.replaceChildren(...lines.map(l => { const d = document.createElement('div'); d.textContent = l; return d; }));
    tasks.forEach(t => t.classList.add('done'));
    return finishReading();
  }
  let i = 0;
  tasks[0].classList.add('on');
  const timer = setInterval(() => {
    if(i < lines.length){
      const d = document.createElement('div');
      d.textContent = lines[i];
      printer.appendChild(d);
      printer.scrollTop = printer.scrollHeight;
      const stage = Math.min(3, Math.floor(i / (lines.length/3.2)));
      tasks.forEach((t,k) => { t.classList.toggle('on', k===stage); t.classList.toggle('done', k<stage); });
      i++;
    } else {
      clearInterval(timer);
      tasks.forEach(t => { t.classList.remove('on'); t.classList.add('done'); });
      setTimeout(finishReading, 450);
    }
  }, 90);
}
function finishReading(){
  rows = DATA.items.map(i => ({date:i.date, 적요:i.적요, 사용내역:i.사용내역, 입금:i.입금,
    지출:i.지출, 잔액:i.잔액, 거래점:i.거래점, 확인됨:false}));
  OPENING = DATA.시작잔액 ?? 0;
  history = []; 결정 = {}; 여는줄 = null;
  render();
  show('review');
}

/* ── 3. 확인하기 ──────────────────────────── */
// 행을 고치면 인덱스가 바뀔 수 있어(거래 넣기) 미정 입금 결정은 다시 받는다.
function 고치기(fn){ history.push(JSON.parse(JSON.stringify(rows))); fn(); 결정 = {}; render(); }
const 잔액고치기 = (i,v) => 고치기(() => { rows[i].잔액 = v; });
// 금액(과 입금/지출 방향)을 고친다. 차이 = 찍힌 잔액 - 앞 잔액: 양수면 입금, 음수면 지출.
const 금액고치기 = (i,차이) => 고치기(() => { rows[i].입금 = 차이 > 0 ? 차이 : 0; rows[i].지출 = 차이 < 0 ? -차이 : 0; });
const 금액말 = 차이 => `${차이 > 0 ? '입금' : '지출'} ${won(Math.abs(차이))}`;
const 그대로두기 = i => 고치기(() => { rows[i].확인됨 = true; });
const 날짜고르기 = (i,d) => 고치기(() => { rows[i].date = d; rows[i].날짜확인 = true; });
// 새로 넣은 거래의 금액을 고친다. 남은 차이는 다음 줄에서 다시 묻는다(여러 건이 빠졌을 때).
const 넣은금액고치기 = (i,이전,금액) => 고치기(() => {
  const r = rows[i], 지출 = r.지출 > 0;
  r.입금 = 지출 ? 0 : 금액; r.지출 = 지출 ? 금액 : 0;
  r.잔액 = 이전 + r.입금 - r.지출;
});
function 거래넣기(i,차이){
  고치기(() => {
    const 이전 = i === 0 ? OPENING : rows[i-1].잔액;
    const 지출 = 차이 > 0, 금액 = Math.abs(차이);
    // 빠진 거래의 날짜는 앞 줄과 뒷 줄 날짜 사이 어딘가다. 둘이 같으면 그 날짜로 정하고,
    // 다르면 사람이 고르게 한다 — 6/30 거래를 7/01로 넣으면 상반기 집행액이 빠진다.
    const 앞날짜 = 앞날짜찾기(i), 뒷날짜 = rows[i].date;
    const 정해짐 = !앞날짜 || 앞날짜 === 뒷날짜;
    rows.splice(i,0,{date:뒷날짜, 적요:rows[i].적요, 사용내역:'', 입금:지출?0:금액,
      지출:지출?금액:0, 잔액:지출?이전-금액:이전+금액, 거래점:'', 확인됨:false, 새로추가:true,
      날짜확인:정해짐, 날짜범위:[앞날짜 || 뒷날짜, 뒷날짜]});
    초점 = `#m${i}`;   // 넣은 거래에서 다음에 할 일은 가게 이름 적기
  });
}
// 날짜를 아직 안 고른 새 거래의 날짜는 임시값이라 건너뛴다.
function 앞날짜찾기(i){
  let k = i - 1;
  while(k >= 0 && 날짜미정(rows[k])) k--;
  return k < 0 ? null : rows[k].date;
}
// 빈 거래를 i 자리에 넣고 고치기 칸을 연다. 저장하기 전까지는 확인할 곳으로 남는다.
const 줄넣기 = i => 고치기(() => {
  const 앞 = 앞날짜찾기(i), 뒤 = rows[i] ? rows[i].date : 앞;
  rows.splice(i,0,{date:뒤, 적요:'', 사용내역:'', 입금:0, 지출:0, 잔액:i === 0 ? OPENING : rows[i-1].잔액,
    거래점:'', 확인됨:false, 새로추가:true, 날짜확인:false, 날짜범위:[앞 || 뒤, 뒤]});
  여는줄 = i; 초점 = `#ed${i}`;
});
const 줄지우기 = i => 고치기(() => { rows.splice(i,1); 여는줄 = null; });
const 줄저장 = (i,v) => 고치기(() => { Object.assign(rows[i], v, {날짜확인:true}); 여는줄 = null; });
const 올바른날짜 = d => /^20\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$/.test(d);

// 줄을 눌렀을 때 여는 고치기 칸. 날짜 · 내용 · 금액 · 잔액을 고치고, 지우거나 위아래에 거래를 넣는다.
function 고치기칸(x){
  const i = x.index, 이전 = x.기대잔액 - x.입금 + x.지출;
  const e = document.createElement('div');
  e.className = 'fix edit'; e.id = `e${i}`;
  e.innerHTML = `<div class="manual"><div><label for="ed${i}">날짜 (8자리)</label>
      <input type="text" class="figure" id="ed${i}" inputmode="numeric"></div></div>
    <div class="manual"><div><label for="em${i}">내용 (가게 이름)</label><input type="text" id="em${i}"></div></div>
    <fieldset><legend>돈이</legend><div class="choices">
      <label><input type="radio" name="ek${i}" value="지출"${x.입금 ? '' : ' checked'}><span>나갔어요 (지출)</span></label>
      <label><input type="radio" name="ek${i}" value="입금"${x.입금 ? ' checked' : ''}><span>들어왔어요 (입금)</span></label></div></fieldset>
    <div class="manual"><div><label for="ea${i}">금액</label><input type="text" class="figure" id="ea${i}" inputmode="numeric"></div></div>
    <div class="manual"><div><label for="eb${i}">잔액 (통장에 찍힌 값, 비우면 계산)</label>
      <input type="text" class="figure" id="eb${i}" inputmode="numeric"></div></div>
    <p class="why" role="alert" data-a="eerr" hidden></p>
    <div class="acts"><button class="btn" data-a="esave">고친 대로 저장</button></div>
    <details class="more"><summary>다른 방법 보기</summary><div class="acts">
      <button class="btn ghost" data-a="eabove">이 줄 위에 거래 넣기</button>
      <button class="btn ghost" data-a="ebelow">이 줄 아래에 거래 넣기</button>
      <button class="btn ghost" data-a="edel">이 줄 지우기</button></div></details>`;
  // OCR이 읽은 글자에 따옴표가 섞일 수 있어 값은 마크업이 아니라 속성으로 넣는다.
  e.querySelector(`#ed${i}`).value = x.date;
  e.querySelector(`#em${i}`).value = x.사용내역 || '';
  e.querySelector(`#ea${i}`).value = (x.지출 || x.입금) ? num(x.지출 || x.입금) : '';
  e.querySelector(`#eb${i}`).value = x.새로추가 && !x.지출 && !x.입금 ? '' : num(x.잔액);
  const 숫자 = id => { const v = e.querySelector(id).value.replace(/[^\d]/g,''); return v === '' ? null : parseInt(v,10); };
  const 오류 = msg => { const p = e.querySelector('[data-a=eerr]'); p.textContent = msg; p.hidden = false; };
  e.querySelector('[data-a=esave]').onclick = () => {
    const date = e.querySelector(`#ed${i}`).value.replace(/[^\d]/g,'');
    const 금액 = 숫자(`#ea${i}`), 지출 = e.querySelector(`input[name=ek${i}]:checked`).value === '지출';
    if(!올바른날짜(date)) return 오류('날짜를 20260701처럼 8자리로 적어 주세요');
    if(!금액) return 오류('금액을 0보다 큰 숫자로 적어 주세요');
    const 입금값 = 지출 ? 0 : 금액, 지출값 = 지출 ? 금액 : 0;
    const 잔액 = 숫자(`#eb${i}`) ?? 이전 + 입금값 - 지출값;
    줄저장(i, {date, 사용내역:e.querySelector(`#em${i}`).value.trim(), 입금:입금값, 지출:지출값, 잔액});
  };
  e.querySelector('[data-a=eabove]').onclick = () => 줄넣기(i);
  e.querySelector('[data-a=ebelow]').onclick = () => 줄넣기(i + 1);
  e.querySelector('[data-a=edel]').onclick = () => 줄지우기(i);
  return e;
}

let 그리기번호 = 0;   // 판정을 기다리는 사이 또 고치면, 늦게 온 앞 판정은 버린다
async function render(){
  const 번호 = ++그리기번호, items = await review(rows);
  if(번호 !== 그리기번호) return;
  if(!items){
    // 판정 없이 예전 목록을 남겨 두면 고친 뒤의 상태와 다르므로 비운다.
    $('callout').classList.remove('done');
    $('calloutText').textContent = 판정오류;
    $('goFirst').hidden = true;
    $('rows').innerHTML = '';
    return;
  }
  const todo = 남은확인(items);

  $('callout').classList.toggle('done', todo === 0);
  $('calloutText').textContent = todo
    ? `${items.length}건을 읽었습니다. ${todo}군데만 통장과 맞는지 봐 주세요.`
    : `${items.length}건 모두 확인했습니다.`;
  $('goFirst').hidden = todo === 0;
  $('undo').hidden = history.length === 0;

  const ds = items.map(x => x.date).sort();
  $('range').textContent = ds.length ? `${ymd(ds[0])} — ${ymd(ds[ds.length-1])}` : '';

  const box = $('rows');
  // 목록을 통째로 다시 그리면 방금 누른 버튼도 지워져 초점이 맨 위로 간다.
  // 키보드 · 화면 읽기로 쓰는 분이 제자리를 잃지 않게, 초점이 있던 줄을 기억해 두었다가 되돌린다.
  const 있던줄 = document.activeElement?.closest('#rows .row')?.dataset.i;
  box.innerHTML = '';
  items.forEach(x => {
    const 문제 = x.상태!=='정상' && x.상태!=='확인함';
    const row = document.createElement('div');
    row.dataset.i = x.index;
    row.className = 'row' + (문제 || 날짜미정(x) ?' flag':'') + (x.상태==='확인함'?' fixed':'');
    const 열림 = 여는줄 === x.index;
    row.innerHTML = `<button type="button" class="rowline" id="r${x.index}" aria-expanded="${열림}" aria-controls="e${x.index}">
      <i class="num">${x.index+1}</i>
      <i class="date">${날짜미정(x) ? '날짜 고르기' : ymd(x.date)}</i>
      <span class="memo" data-amt="${x.지출?'지출':'입금'} ${won(x.지출||x.입금)}"></span>
      <i class="amt ${x.지출?'out':'in'}">${x.지출?'−':'+'}${won(x.지출||x.입금)}</i>
      <i class="bal">${won(x.잔액)}</i></button>`;
    // 사용내역은 OCR이 읽었거나 사람이 적은 글자라 마크업이 아니라 글자로 넣는다.
    row.querySelector('.memo').textContent = x.사용내역 || '내역 없음';
    row.querySelector('.rowline').onclick = () => { 여는줄 = 열림 ? null : x.index; render(); };
    if(열림) row.appendChild(고치기칸(x));

    if(x.새로추가 && !열림){
      const w = document.createElement('div');
      w.className = 'fix';
      const 방향 = x.지출 ? '지출' : '입금', 이전 = x.기대잔액 - x.입금 + x.지출;
      w.innerHTML = `<div class="manual"><div><label for="m${x.index}">이 거래의 가게 이름을 적어 주세요</label>
        <input type="text" id="m${x.index}" placeholder="예: 바다건어물"></div></div>
        <details class="more"><summary>빠진 거래가 여러 건이에요</summary>
        <p class="why">통장에 찍힌 첫 거래의 ${방향} 금액을 적어 주세요. 남은 금액은 아래 줄에서 다시 여쭤볼게요.</p>
        <div class="manual"><div><label for="n${x.index}">${방향} 금액</label>
        <input type="text" class="figure" id="n${x.index}" inputmode="numeric" placeholder="${x.지출||x.입금}"></div>
        <button class="btn ghost" data-a="nman">이 금액으로</button></div>
        <p class="why" data-a="nerr" hidden>0보다 큰 금액을 숫자로 적어 주세요</p></details>`;
      // 따옴표가 섞이면 value="..." 속성이 잘리므로 값은 속성으로 넣는다(고치기칸과 같은 방식).
      w.querySelector(`#m${x.index}`).value = x.사용내역 || '';
      w.querySelector(`#m${x.index}`).addEventListener('input', e => { rows[x.index].사용내역 = e.target.value; });
      w.querySelector('[data-a=nman]').onclick = () => {
        const v = parseInt(w.querySelector(`#n${x.index}`).value.replace(/[^\d]/g,''),10);
        if(v > 0) 넣은금액고치기(x.index, 이전, v);
        else w.querySelector('[data-a=nerr]').hidden = false;
      };
      if(날짜미정(x)){
        const [앞, 뒤] = x.날짜범위;
        const d = document.createElement('div');
        d.innerHTML = `<p style="margin-top:18px">이 거래는 언제였나요? 통장을 보고 골라 주세요.</p>
          <div class="acts"><button class="btn choice" data-d="${앞}">${md(앞)}</button>
          <button class="btn choice" data-d="${뒤}">${md(뒤)}</button></div>
          <details class="more"><summary>다른 날짜 적기</summary>
          <div class="manual"><div><label for="d${x.index}">${ymd(앞)} ~ ${ymd(뒤)} 사이</label>
          <input type="text" class="figure" id="d${x.index}" inputmode="numeric" placeholder="${ymd(앞)}"></div>
          <button class="btn ghost" data-a="dman">이 날짜로</button></div>
          <p class="why" data-a="derr" hidden>${ymd(앞)}부터 ${ymd(뒤)} 사이의 날짜를 8자리로 적어 주세요</p></details>`;
        d.querySelectorAll('[data-d]').forEach(b => b.onclick = () => 날짜고르기(x.index, b.dataset.d));
        d.querySelector('[data-a=dman]').onclick = () => {
          const v = d.querySelector('input').value.replace(/[^\d]/g,'');
          if(v.length === 8 && 앞 <= v && v <= 뒤) 날짜고르기(x.index, v);
          else d.querySelector('[data-a=derr]').hidden = false;
        };
        w.appendChild(d);
      }
      row.appendChild(w);
    }

    if(문제){
      const 차이 = x.기대잔액 - x.잔액;
      // 찍힌 잔액이 맞다고 볼 때 이 줄의 금액이 얼마여야 하는지. 금액을 잘못 읽었거나
      // 입금/지출 칸을 바꿔 읽은 경우 이 값으로 고치면 앞뒤가 맞는다.
      const 이전 = x.기대잔액 - x.입금 + x.지출, 금액차이 = x.잔액 - 이전;
      const 금액칸 = `<div class="manual"><div><label for="a${x.index}">${x.지출?'지출':'입금'} 금액 직접 적기</label>
          <input type="text" class="figure" id="a${x.index}" inputmode="numeric" placeholder="${x.지출||x.입금}"></div>
          <button class="btn ghost" data-a="aman">이 금액으로</button></div>`;
      const w = document.createElement('div');
      w.className = 'fix';
      if(x.상태==='잔액오독'){
        w.innerHTML = `<p>잔액을 잘못 읽은 것 같아요. 통장에는 <b>${won(x.기대잔액)}</b>으로 찍혀 있을 거예요.</p>
          <div class="acts"><button class="btn" data-a="fix">${won(x.기대잔액)}으로 고치기</button></div>
          <details class="more"><summary>다른 방법 보기</summary>
          <div class="acts"><button class="btn ghost" data-a="keep">통장에 찍힌 값이 맞습니다</button></div>
          <div class="manual"><div><label for="b${x.index}">잔액 직접 적기</label>
          <input type="text" class="figure" id="b${x.index}" inputmode="numeric" placeholder="${x.기대잔액}"></div>
          <button class="btn ghost" data-a="man">이 잔액으로</button></div>
          <p class="why">계산: 앞 잔액 ${won(x.기대잔액 - x.입금 + x.지출)} ${x.지출?'−':'+'} ${won(x.지출||x.입금)} = ${won(x.기대잔액)}</p></details>`;
        w.querySelector('[data-a=fix]').onclick = () => 잔액고치기(x.index, x.기대잔액);
        w.querySelector('[data-a=man]').onclick = () => {
          const v = parseInt(w.querySelector('input').value.replace(/[^\d]/g,''),10);
          if(!isNaN(v)) 잔액고치기(x.index, v);
        };
      } else if(x.상태==='거래누락'){
        // 잔액은 맞는데 계산이 어긋난다: 이 줄의 금액을 잘못 읽었거나, 앞에 거래가 빠졌다.
        // 숫자만으로는 둘을 가를 수 없어 통장을 보고 고르게 한다.
        w.innerHTML = `<p>금액을 잘못 읽었거나, 앞에 거래가 빠진 것 같아요. 통장을 보고 맞는 쪽을 골라 주세요.</p>
          <div class="acts">${금액차이 ? `<button class="btn choice" data-a="amt">이 줄을 ${금액말(금액차이)}으로 고치기</button>` : ''}
          <button class="btn choice" data-a="add">앞에 빠진 ${차이>0?'지출':'입금'} ${won(Math.abs(차이))} 넣기</button></div>
          <details class="more"><summary>다른 방법 보기</summary>
          <div class="acts"><button class="btn ghost" data-a="keep">통장과 똑같습니다</button></div>
          ${금액칸}
          <p class="why">여기까지 계산하면 ${won(x.기대잔액)}인데 통장에는 ${won(x.잔액)}으로 찍혀 있어요</p></details>`;
      } else {
        // 기대잔액은 앞에 빠진 거래를 몰라서, 다음 줄에서 거꾸로 계산한 잔액을 제안한다.
        const nxt = items[x.index+1];
        const 뒤잔액 = nxt ? nxt.잔액 - nxt.입금 + nxt.지출 : null;
        w.innerHTML = `<p>이 줄이 앞뒤와 맞지 않아요. 통장을 보고 틀린 곳을 골라 주세요.</p>
          <div class="acts">${금액차이 ? `<button class="btn choice" data-a="amt">금액이 틀림: ${금액말(금액차이)}</button>` : ''}
          ${뒤잔액 !== null ? `<button class="btn choice" data-a="fix">잔액이 틀림: 통장에는 ${won(뒤잔액)}</button>` : ''}
          <button class="btn choice" data-a="add">앞에 빠진 ${차이>0?'지출':'입금'} ${won(Math.abs(차이))} 넣기</button></div>
          <details class="more"><summary>다른 방법 보기</summary>
          <div class="acts"><button class="btn ghost" data-a="keep">통장과 똑같습니다</button></div>
          ${금액칸}
          <div class="manual"><div><label for="b${x.index}">잔액 직접 적기</label>
          <input type="text" class="figure" id="b${x.index}" inputmode="numeric" placeholder="${x.잔액}"></div>
          <button class="btn ghost" data-a="man">이 잔액으로</button></div></details>`;
        if(뒤잔액 !== null) w.querySelector('[data-a=fix]').onclick = () => 잔액고치기(x.index, 뒤잔액);
        w.querySelector('[data-a=man]').onclick = () => {
          const v = parseInt(w.querySelector(`#b${x.index}`).value.replace(/[^\d]/g,''),10);
          if(!isNaN(v)) 잔액고치기(x.index, v);
        };
      }
      const 넣기버튼 = w.querySelector('[data-a=add]');
      if(넣기버튼) 넣기버튼.onclick = () => 거래넣기(x.index, 차이);
      const 금액버튼 = w.querySelector('[data-a=amt]');
      if(금액버튼) 금액버튼.onclick = () => 금액고치기(x.index, 금액차이);
      const 금액입력 = w.querySelector('[data-a=aman]');
      if(금액입력) 금액입력.onclick = () => {
        const v = parseInt(w.querySelector(`#a${x.index}`).value.replace(/[^\d]/g,''),10);
        if(!isNaN(v)) 금액고치기(x.index, x.지출 ? -v : v);
      };
      w.querySelector('[data-a=keep]').onclick = () => 그대로두기(x.index);
      row.appendChild(w);
    }
    box.appendChild(row);
  });
  // 줄을 지워 번호가 끝을 넘으면 마지막 줄로 간다.
  const 갈곳 = 초점 ? box.querySelector(초점)
    : 있던줄 !== undefined ? $(`r${Math.min(+있던줄, items.length - 1)}`) : null;
  초점 = null;
  if(갈곳) 갈곳.focus();
}

$('goFirst').onclick = () => {
  const el = document.querySelector('.row.flag');
  if(!el) return;
  // 화면만 옮기면 키보드 · 화면 읽기로 쓰는 분은 그 줄까지 다시 찾아가야 하므로 초점도 옮긴다.
  // 스크롤은 아래 scrollIntoView가 맡도록 focus는 스크롤하지 않게 한다.
  el.querySelector('.rowline').focus({preventScroll:true});
  el.scrollIntoView({behavior: REDUCED?'auto':'smooth', block:'center'});
};
$('undo').onclick = () => {
  if(!history.length) return;
  rows = history.pop(); 결정 = {}; 여는줄 = null; render();
  // 더 되돌릴 것이 없으면 버튼이 숨으면서 초점을 잃으므로 첫 확인할 곳(없으면 첫 줄)으로 옮긴다.
  if($('undo').hidden) (document.querySelector('#rows .row.flag .rowline') || $('r0'))?.focus();
};
$('toMonths').onclick = () => { show('months'); renderSettlement(); };
$('backReview').onclick = () => show('review');
$('printMonths').onclick = () => window.print();

/* ── 4. 정산하기 ─────────────────────────── */
// 계산은 서버(passbook/settlement.py) 한 곳에서만 한다. 결정을 바꿀 때마다 다시 묻는다.
async function renderSettlement(){
  const items = await review(rows);
  const account = picked('account'), half = picked('half');
  const year = parseInt($('year').value, 10);
  $('mTitle').textContent = `${통장이름[account]} · ${year}년 ${half} 월별 집행내역`;

  const r = items && await postSettlement({통장:account, 연도:year, 반기:half, 시작잔액:OPENING, 결정,
    items: items.map(x => ({date:x.date, 적요:x.적요||'', 사용내역:x.사용내역||'',
                            입금:x.입금, 지출:x.지출, 잔액:x.잔액}))});
  if(!r){
    $('sCallout').classList.remove('done');
    $('sCalloutText').textContent = '정산은 서버가 켜져 있을 때만 할 수 있습니다.';
    $('pendingSheet').hidden = true; $('report').hidden = true; $('printMonths').disabled = true;
    return;
  }
  const todo = 남은확인(items);

  // 미정 입금
  const 남은결정 = r.미정.filter(p => !p.결정).length;
  $('pendingSheet').hidden = r.미정.length === 0;
  $('pCount').textContent = `${r.미정.length}건`;
  const box = $('pending');
  // 다시 그리면 누른 버튼이 지워져 초점이 맨 위로 간다(확인하기 화면과 같은 문제).
  // 초점이 있던 입금과 버튼을 기억했다가 같은 버튼으로 되돌린다.
  const 있던버튼 = document.activeElement?.closest('#pending .pend [data-v]');
  const 있던입금 = 있던버튼?.closest('.pend').dataset.i, 있던값 = 있던버튼?.dataset.v;
  box.innerHTML = '';
  r.미정.forEach(p => {
    const el = document.createElement('div');
    el.className = 'pend' + (p.결정 ? '' : ' todo');
    el.dataset.i = p.index;
    el.innerHTML = `<span class="what"><i>${md(p.date)}</i><b>+${won(p.금액)}</b></span>
      <span class="acts">
        <button class="btn" data-v="수입" aria-pressed="${p.결정==='수입'}">수입</button>
        <button class="btn" data-v="차감" aria-pressed="${p.결정==='차감'}">집행액에서 빼기</button>
      </span>`;
    // 사용내역은 읽은 글자라 마크업이 아니라 글자로 넣는다.
    el.querySelector('.what b').before(p.사용내역 || '내역 없음');
    el.querySelectorAll('button').forEach(b => b.onclick = () => { 결정[p.index] = b.dataset.v; renderSettlement(); });
    box.appendChild(el);
  });
  if(있던입금 !== undefined) box.querySelector(`.pend[data-i="${있던입금}"] [data-v="${있던값}"]`)?.focus();

  // 남은 일 안내. 완료되기 전에는 숫자를 보여주지 않는다 — 틀린 숫자를 옮겨 적지 않도록.
  const 할일 = [];
  if(todo) 할일.push(`거래 내역에서 확인할 곳 ${todo}군데`);
  if(남은결정) 할일.push(`정해 주실 입금 ${남은결정}건`);
  if(!todo && !r.검산.잔액연쇄) 할일.push('잔액이 이어지지 않는 곳 (거래 내역을 다시 봐 주세요)');
  // 서버 검산이 맞아도, 확인 화면에 남은 곳(날짜를 고르지 않은 거래 등)이 있으면 완료가 아니다.
  const 완료 = r.완료 && !todo;
  $('sCallout').classList.toggle('done', 완료);
  $('sCalloutText').textContent = 완료
    ? '통장 잔액과 맞습니다. 아래 숫자를 보고서에 옮겨 적어 주세요.'
    : `아직 남은 것: ${할일.join(', ') || '확인할 곳'}`;
  $('report').hidden = !완료;
  $('printMonths').disabled = !완료;
  if(!완료) return;

  $('months').innerHTML = r.월별.map(m =>
    `<tr><td>${m.월}월</td><td data-label="수입액">${num(m.수입액)}</td><td data-label="집행액">${num(m.집행액)}</td><td data-label="잔액">${num(m.잔액)}</td></tr>`).join('') +
    `<tr class="total"><td>합계</td><td data-label="수입액">${num(r.합계.수입액)}</td><td data-label="집행액">${num(r.합계.집행액)}</td><td class="none"></td></tr>`;
  const t = r.총괄;
  $('summary').innerHTML =
    `<tr><td>${통장이름[account]}</td><td data-label="예산액">${num(t.예산액)}</td><td data-label="집행액">${num(t.집행액)}</td><td data-label="집행잔액">${num(t.집행잔액)}</td><td data-label="이자">${num(t.이자)}</td></tr>`;

  const c = r.검산, 메모 = [];
  메모.push(`검산: 시작 잔액 ${won(c.시작잔액)} + 수입 ${won(r.합계.수입액)} − 집행 ${won(r.합계.집행액)} = 통장 잔액 ${won(c.통장잔액)}`);
  if(t.이월금) 메모.push(`예산액 ${won(t.예산액)} = 앞 반기에서 넘어온 이월금 ${won(t.이월금)} + 이번 반기 보조금 ${won(t.보조금)}`);
  if(t.기타수입) 메모.push(`보조금·이자가 아닌 수입 ${won(t.기타수입)}은 총괄표에 칸이 없습니다. 비고 칸 등에 따로 적어 주세요.`);
  메모.push('총괄표의 합계 줄은 세 통장을 모두 정산한 뒤 더해서 적어 주세요.');
  $('mNote').innerHTML = 메모.map(x => `<span style="display:block">${x}</span>`).join('');
}

show('upload');
