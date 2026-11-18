import os, re, uuid, shutil, subprocess, threading, sqlite3, hashlib, hmac, secrets, time, json, math
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

ROOT=Path(os.getenv('DATA_DIR','/tmp/banua_v6'));ROOT.mkdir(parents=True,exist_ok=True)
DB=ROOT/'accounts.sqlite3'
with sqlite3.connect(DB) as c:
 c.execute('CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, salt TEXT, password TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, email TEXT, expires REAL)')
app=FastAPI(title='Banua AI Clipper V6 Ultra Pro')
JOBS={}; LOCK=threading.Lock()
class Credentials(BaseModel):
 email:str
 password:str
class LinkRequest(BaseModel):
 url:str
 count:int=Field(3,ge=1,le=10)
 seconds:int=Field(30,ge=10,le=90)
 ratio:str='9:16'

def run(args,timeout=1800):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError((p.stderr or p.stdout)[-1000:])
 return p.stdout

def auth(authorization):
 token=(authorization or '').removeprefix('Bearer ').strip()
 with sqlite3.connect(DB) as c:
  row=c.execute('SELECT email FROM sessions WHERE token=? AND expires>?',(token,time.time())).fetchone()
 if not row:raise HTTPException(401,'Silakan login kembali')
 return row[0]

def password_hash(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),260000).hex()
@app.post('/api/register')
def register(data:Credentials):
 email=data.email.strip().lower()
 if not re.fullmatch(r'[^@ ]+@[^@ ]+\.[^@ ]+',email) or len(data.password)<8:raise HTTPException(400,'Email valid dan password minimal 8 karakter')
 salt=secrets.token_hex(16)
 try:
  with sqlite3.connect(DB) as c:c.execute('INSERT INTO users VALUES(?,?,?)',(email,salt,password_hash(data.password,salt)))
 except sqlite3.IntegrityError:raise HTTPException(409,'Email sudah terdaftar')
 return {'ok':True}
@app.post('/api/login')
def login(data:Credentials):
 email=data.email.strip().lower()
 with sqlite3.connect(DB) as c:row=c.execute('SELECT salt,password FROM users WHERE email=?',(email,)).fetchone()
 if not row or not hmac.compare_digest(row[1],password_hash(data.password,row[0])):raise HTTPException(401,'Email atau password salah')
 token=secrets.token_urlsafe(36)
 with sqlite3.connect(DB) as c:c.execute('INSERT INTO sessions VALUES(?,?,?)',(token,email,time.time()+86400))
 return {'token':token}
@app.post('/api/logout')
def logout(authorization:str|None=Header(None)):
 token=(authorization or '').removeprefix('Bearer ').strip()
 with sqlite3.connect(DB) as c:c.execute('DELETE FROM sessions WHERE token=?',(token,))
 return {'ok':True}

def update(job,**kw):
 with LOCK:JOBS[job].update(kw)

def transcribe(src):
 try:
  from faster_whisper import WhisperModel
  model=WhisperModel(os.getenv('WHISPER_MODEL','tiny'),device='cpu',compute_type='int8')
  segs,info=model.transcribe(str(src),vad_filter=True)
  return [{'start':float(s.start),'end':float(s.end),'text':s.text.strip()} for s in segs]
 except Exception:return []

def subtitle(segs,start,end,path):
 def stamp(t):
  ms=int(round(t*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
  return f'{h:02}:{m:02}:{s:02},{ms:03}'
 lines=[]
 for s in segs:
  a=max(start,s['start']);b=min(end,s['end'])
  if b>a:lines.extend([str(len(lines)//4+1),f'{stamp(a-start)} --> {stamp(b-start)}',s['text'],''])
 path.write_text('\n'.join(lines),encoding='utf8')

def face_center(src,start):
 try:
  import cv2
  cap=cv2.VideoCapture(str(src));cap.set(cv2.CAP_PROP_POS_MSEC,start*1000)
  ok,frame=cap.read();cap.release()
  if not ok:return .5
  gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
  cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
  faces=cascade.detectMultiScale(gray,1.1,4,minSize=(40,40))
  if len(faces):
   x,y,w,h=max(faces,key=lambda f:f[2]*f[3]);return min(.85,max(.15,(x+w/2)/frame.shape[1]))
 except Exception:pass
 return .5

def clip_filter(src,ratio,start):
 if ratio=='16:9':return 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1'
 if ratio=='1:1':return 'scale=720:720:force_original_aspect_ratio=increase,crop=720:720,setsar=1'
 center=face_center(src,start)
 # Sampled face-aware crop position, not continuous face tracking.
 return f'scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280:x=clip(iw*{center:.3f}-360\\,0\\,iw-720):y=(ih-1280)/2,setsar=1'

def process(job,src,count,seconds,ratio):
 folder=ROOT/job
 try:
  update(job,status='Menganalisis video',progress=10)
  duration=float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(src)]).strip())
  if duration<2:raise ValueError('Video terlalu pendek')
  segs=transcribe(src)
  length=min(seconds,duration)
  candidates=[max(0,(duration-length)*i/max(1,count*2)) for i in range(count*2+1)]
  def score(t):
   relevant=[s for s in segs if s['start']<t+length and s['end']>t]
   words=' '.join(s['text'] for s in relevant)
   density=min(1,len(words.split())/max(1,length*2.5))
   hooks=sum(w in words.lower() for w in ['cara','rahasia','penting','ternyata','tips','jangan','why','how','secret','best'])
   return round(35+40*density+min(20,hooks*5),1) if segs else 0
  selected=[]
  for t in sorted(candidates,key=score,reverse=True):
   if all(abs(t-s)>length*.65 for s in selected):selected.append(t)
   if len(selected)>=count:break
  if not selected:selected=[0]
  clips=[]
  for i,start in enumerate(sorted(selected),1):
   dest=folder/f'clip_{i:02}.mp4'
   vf=clip_filter(src,ratio,start)
   run(['ffmpeg','-nostdin','-y','-ss',str(start),'-i',str(src),'-t',str(length),'-vf',vf,'-c:v','libx264','-preset','ultrafast','-crf','28','-c:a','aac','-movflags','+faststart',str(dest)])
   subtitle(segs,start,start+length,dest.with_suffix('.srt'))
   words=' '.join(s['text'] for s in segs if s['start']<start+length and s['end']>start)
   title=(words[:85].strip() or f'Cuplikan menarik #{i}')
   clips.append({'filename':dest.name,'srt':dest.with_suffix('.srt').name,'score':score(start),'title':title,'caption':f'{title} #Shorts #Reels #BanuaAIClipper','start':round(start,1)})
   update(job,clips=clips.copy(),progress=20+int(75*i/len(selected)),status=f'Klip {i}/{len(selected)} selesai')
  update(job,status='Selesai',progress=100,done=True)
 except Exception as e:update(job,status='Gagal',error=str(e),done=True)

@app.get('/',response_class=HTMLResponse)
def home():return (Path(__file__).parent/'index.html').read_text(encoding='utf8')
@app.get('/health')
def health():return {'ok':True,'ffmpeg':bool(shutil.which('ffmpeg')),'yt_dlp':bool(shutil.which('yt-dlp'))}
@app.post('/api/upload')
async def upload(file:UploadFile=File(...),count:int=Form(3),seconds:int=Form(30),ratio:str=Form('9:16'),authorization:str|None=Header(None)):
 owner=auth(authorization)
 if not (1<=count<=10 and 10<=seconds<=90 and ratio in ('9:16','1:1','16:9')):raise HTTPException(400,'Pengaturan tidak valid')
 if not file.filename.lower().endswith(('.mp4','.mov','.webm','.mkv')):raise HTTPException(400,'Format video tidak didukung')
 job=uuid.uuid4().hex[:12];folder=ROOT/job;folder.mkdir()
 src=folder/'source'+Path(file.filename).suffix.lower() if False else folder/('source'+Path(file.filename).suffix.lower())
 total=0
 with src.open('wb') as out:
  while chunk:=await file.read(1024*1024):
   total+=len(chunk)
   if total>100*1024*1024:
    out.close();shutil.rmtree(folder,ignore_errors=True);raise HTTPException(413,'Batas upload 100 MB')
   out.write(chunk)
 with LOCK:JOBS[job]={'id':job,'owner':owner,'status':'Menunggu','progress':0,'done':False,'error':None,'clips':[]}
 threading.Thread(target=process,args=(job,src,count,seconds,ratio),daemon=True).start()
 return {'id':job}
@app.post('/api/link')
def link(req:LinkRequest,authorization:str|None=Header(None)):
 owner=auth(authorization)
 if not re.match(r'^https?://',req.url) or req.ratio not in ('9:16','1:1','16:9'):raise HTTPException(400,'Link atau rasio tidak valid')
 job=uuid.uuid4().hex[:12];folder=ROOT/job;folder.mkdir()
 with LOCK:JOBS[job]={'id':job,'owner':owner,'status':'Mengambil link','progress':0,'done':False,'error':None,'clips':[]}
 def worker():
  try:
   run(['yt-dlp','--no-playlist','--max-filesize','100M','-f','bv*+ba/b','--merge-output-format','mp4','-o',str(folder/'source.%(ext)s'),req.url])
   src=next((p for p in folder.glob('source.*') if p.suffix in ('.mp4','.mkv','.webm','.mov')),None)
   if src is None:raise RuntimeError('Video tidak tersedia untuk diunduh')
   process(job,src,req.count,req.seconds,req.ratio)
  except Exception as e:update(job,status='Gagal',error=str(e),done=True)
 threading.Thread(target=worker,daemon=True).start()
 return {'id':job}
@app.get('/api/jobs/{job}')
def status(job:str,authorization:str|None=Header(None)):
 owner=auth(authorization)
 if job not in JOBS or JOBS[job]['owner']!=owner:raise HTTPException(404,'Proyek tidak ditemukan')
 return JOBS[job]
@app.get('/api/jobs/{job}/files/{filename}')
def download(job:str,filename:str,token:str=''):
 owner=auth('Bearer '+token)
 if job not in JOBS or JOBS[job]['owner']!=owner or not re.fullmatch(r'clip_\d{2}\.(mp4|srt)',filename):raise HTTPException(404)
 p=ROOT/job/filename
 if not p.is_file():raise HTTPException(404)
 return FileResponse(p,filename=filename)
