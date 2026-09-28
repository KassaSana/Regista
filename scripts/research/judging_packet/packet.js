let storageOk=true;try{localStorage.setItem('regista-test','1');localStorage.removeItem('regista-test');}
catch(e){storageOk=false;}
if(!storageOk){const warning=document.createElement('p');warning.className='warning';
warning.textContent='This browser view cannot save answers. They are kept only while this tab stays '
+'open: press Export answers before closing it.';document.querySelector('main').prepend(warning);}
const key = 'regista-judging-' + document.body.dataset.packet;
function collect(){const data={packet:document.body.dataset.packet,answers:{}};
document.querySelectorAll('input[type=radio]:checked,textarea[name]').forEach(el=>{
if(el.value) data.answers[el.name]=el.value;});return data;}
function save(){try{localStorage.setItem(key,JSON.stringify(collect()));}catch(e){}}
function restore(){let saved=null;try{saved=JSON.parse(localStorage.getItem(key)||'null');}catch(e){}
if(!saved)return;for(const [name,value] of Object.entries(saved.answers)){
const radio=document.querySelector(`input[type=radio][name="${CSS.escape(name)}"][value="${CSS.escape(value)}"]`);
if(radio){radio.checked=true;continue;}
const text=document.querySelector(`textarea[name="${CSS.escape(name)}"]`);if(text)text.value=value;}}
document.addEventListener('change',save);document.addEventListener('input',save);restore();
document.getElementById('make-export').addEventListener('click',()=>{
const out=document.getElementById('export');out.value=JSON.stringify(collect(),null,2);out.select();});
