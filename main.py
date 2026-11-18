import os, re, uuid, json, shutil, subprocess, threading, time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

ROOT=Path('/data') if Path('/data').exists() else Path(__file__).parent/'data'
ROOT.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='Banua AI Clipper V5 Ultra')
JOBS={}
LOCK=threading.Lock()

class Request(BaseModel):
    url: str=Field(min_length=8,max_length=2048)
    count: int=Field(default=5,ge=1,le=20)
    seconds: int=Field(default=30,ge=10,le=120)
    ratio: str='9:16'

def update(job, **fields):
    with LOCK: JOBS[job].update(fields)

def command(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=3600)
    if p.returncode: raise RuntimeError((p.stderr or p.stdout)[-1200:])
    return p.stdout

def process(job, req):
    work=ROOT/job
    try:
        update(job,status='Mengambil video dari tautan…',progress=10)
        command(['yt-dlp','--no-playlist','--max-filesize','1000M','-f','bv*+ba/b','--merge-output-format','mp4','-o',str(work/'source.%(ext)s'),req.url])
        sources=[p for p in work.glob('source.*') if p.suffix.lower() in ('.mp4','.mkv','.webm','.mov')]
        if not sources: raise RuntimeError('File video tidak ditemukan. Tautan mungkin dibatasi platform.')
        source=sources[0]
        dur=float(command(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(source)]).strip())
        if dur < 2: raise RuntimeError('Video terlalu pendek.')
        update(job,status='Membuat klip…',progress=35)
        clips=[]
        length=min(req.seconds,dur)
        starts=[max(0,(dur-length)*(i+.5)/req.count) for i in range(req.count)]
        if req.ratio=='9:16': vf='scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1'
        elif req.ratio=='1:1': vf='scale=720:720:force_original_aspect_ratio=increase,crop=720:720,setsar=1'
        else: vf='scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1'
        for i,start in enumerate(starts,1):
            dest=work/f'clip_{i:02}.mp4'
            command(['ffmpeg','-nostdin','-y','-ss',str(start),'-i',str(source),'-t',str(length),'-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','24','-c:a','aac','-movflags','+faststart',str(dest)])
            clips.append(dest.name)
            update(job,status=f'Membuat klip {i}/{req.count}…',progress=35+int(60*i/req.count),clips=clips.copy())
        update(job,status='Selesai',progress=100,done=True)
    except Exception as exc:
        update(job,status='Gagal',error=str(exc),done=True)

@app.get('/',response_class=HTMLResponse)
def home(): return (Path(__file__).parent/'index.html').read_text(encoding='utf-8')

@app.get('/health')
def health(): return {'ok':True,'ffmpeg':bool(shutil.which('ffmpeg')),'yt_dlp':bool(shutil.which('yt-dlp'))}

@app.post('/api/jobs')
def create(req:Request):
    if not re.match(r'^https?://',req.url,re.I): raise HTTPException(400,'Link harus dimulai dengan http:// atau https://')
    if req.ratio not in ('9:16','1:1','16:9'): raise HTTPException(400,'Rasio tidak valid')
    job=uuid.uuid4().hex[:12]
    (ROOT/job).mkdir()
    with LOCK: JOBS[job]={'id':job,'status':'Menunggu','progress':0,'clips':[],'done':False,'error':None}
    threading.Thread(target=process,args=(job,req),daemon=True).start()
    return {'id':job}

@app.get('/api/jobs/{job}')
def status(job:str):
    if job not in JOBS: raise HTTPException(404,'Proyek tidak ditemukan')
    with LOCK: return JOBS[job].copy()

@app.get('/api/jobs/{job}/files/{filename}')
def file(job:str,filename:str):
    if job not in JOBS or not re.fullmatch(r'clip_\d{2}\.mp4',filename): raise HTTPException(404)
    p=ROOT/job/filename
    if not p.is_file() or filename not in JOBS[job]['clips']: raise HTTPException(404)
    return FileResponse(p,media_type='video/mp4',filename=filename)
