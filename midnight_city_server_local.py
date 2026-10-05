from __future__ import annotations
import json, os, re, threading, time, zipfile, io, webbrowser, copy, importlib, sys, difflib
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
try:
 import torch
 from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
 from peft import PeftModel
except Exception:
 torch=AutoTokenizer=AutoModelForCausalLM=BitsAndBytesConfig=PeftModel=None
from persistent_brain import PersistentBrainRuntime
from smart_autonomy import choose as utility_choose, make_inner_thought, reflect_day, schedule_from_reflection, need_pressure, score_candidates
from autonomous_decision import fallback_goal
from interaction_engine import choose_interaction, willingness, label as interaction_label, INTERACTIONS, available_interactions
from social_context import contextual_options, choose_counter_offer, active_lock, set_lock, clear_expired
from ai_constants import (
    LOCATION_ZONES, DATE_LOCATIONS, VALID_GOALS as AI_VALID_GOALS,
    COUPLE_STATUSES, ROMANTIC_THRESHOLDS, meets_romantic,
    nearest_location, travel_minutes as ai_travel_minutes,
)
from family_role_cheker import check_family_role_interaction

ROOT=Path(__file__).resolve().parent; HTML=ROOT/'index.html'; MAP_FILE=ROOT/'world_map_v6.json'
HOT_RELOAD_ACTIVE=globals().get('HOT_RELOAD_ACTIVE',False)
HOT_RELOAD_MTIMES=globals().get('HOT_RELOAD_MTIMES',{})
HTTP_SERVER=globals().get('HTTP_SERVER',None)
MODEL=Path(os.environ.get('MIDNIGHT_BRAIN_MODEL',r'C:\AI\MidnightBrain_v2_MapAgnostic\models\Qwen3-4B-Nymphaea-RP'))
ADAPTER=Path(os.environ.get('MIDNIGHT_BRAIN_ADAPTER',r'C:\AI\MidnightBrain_v2_MapAgnostic\output\MidnightBrain-v3\adapter'))
VERSION='V32.2_MAP_EXPANSION'; MAX_NEW=int(os.environ.get('MIDNIGHT_BRAIN_MAX_NEW_TOKENS','256'))
LOCK=threading.RLock(); BRAIN_LOCK=threading.Lock(); MODEL_OBJ=None; TOKENIZER=None; BRAIN_ERROR=None; BRAIN_EPOCH=0
BRAIN_ACTIVE=set(); BRAIN_PENDING={}; BRAIN_DISPATCHING=False
DIALOGUE_LOCK=threading.RLock(); DIALOGUE_JOBS={}; DIALOGUE_SEQ=0
LOGDIR=ROOT/'logs'; LOGDIR.mkdir(exist_ok=True); LOG=LOGDIR/'midnight_city.log'; EVENTS=LOGDIR/'events.jsonl'; LOGLOCK=threading.Lock()
try: MAP={z['id']:z for z in json.loads(MAP_FILE.read_text(encoding='utf8')).get('semantic_zones',[])}
except Exception: MAP={}
COLLEGE='Midnight City College'
SCHEDULE={0:[(9,10,'Photography Theory'),(10,11,'Digital Photography'),(11,12,'Creative Lab'),(14,15,'Studio Practice'),(15,16,'Studio Practice')],1:[(9,10,'Art History'),(10,11,'Composition'),(11,12,'Visual Culture'),(14,15,'Portfolio Lab'),(15,16,'Portfolio Lab')],2:[(9,10,'Photography Theory'),(10,11,'Lighting'),(11,12,'Creative Lab'),(13,14,'Portfolio Review'),(14,15,'Portfolio Review'),(15,16,'Editing Lab')],3:[(9,10,'Art History'),(10,11,'Portraiture'),(11,12,'Critique'),(14,15,'Editing Lab'),(15,16,'Editing Lab')],4:[(9,10,'Photography Theory'),(10,11,'Digital Photography'),(11,12,'Client Practice'),(13,14,'Portfolio Lab'),(14,15,'Portfolio Lab'),(15,16,'Project Workshop')],5:[],6:[]}
EVENING_SCHEDULE={0:[(18,19,'Evening Computer Science'),(19,20,'Algorithms'),(20,21,'Software Engineering')],1:[(18,19,'Databases'),(19,20,'Networks'),(20,21,'Systems Design')],2:[(18,19,'Algorithms'),(19,20,'Programming Lab'),(20,21,'Project Seminar')],3:[(18,19,'Operating Systems'),(19,20,'Web Engineering'),(20,21,'Systems Lab')],4:[(18,19,'Computer Science Seminar'),(19,20,'Project Workshop'),(20,21,'Project Workshop')],5:[],6:[]}

def schedule_for(c):
 occ=str(c.get('occupation','')).lower()
 if 'evening student' in occ:
  return EVENING_SCHEDULE
 if 'student' in occ:
  return SCHEDULE
 return {}

TEXT={'sleep':'Sleeping','eat_home':'Eating at home','eat_cafe':'Eating at a cafe','shower':'Taking a shower','get_dressed':'Getting dressed','work':'Working','go_to_college':'Going to college','attend_college':'Attending college','study':'Studying','relax_home':'Relaxing at home','watch_tv':'Watching TV','use_phone':'Using phone','gaming':'Gaming','walk':'Going for a walk','exercise':'Exercising','socialize':'Socializing','go_to_club':'Going to Night Club','go_to_rooftop':'Going to Rooftop','go_to_beach':'Going to Beach','go_to_park':'Going to Park','wait_for_date':'Waiting for the date to begin','go_to_studio':'Going to Studio','go_to_cafe':'Going to Cafe','go_home':'Going home','shop':'Shopping','wait':'Observing / waiting','recreation':'Recreating','social_interaction':'Interacting'}
TARGET={'go_to_college':'College','attend_college':'College','go_to_studio':'Studio','work':'Studio','go_to_cafe':'Cafe','eat_cafe':'Cafe','go_to_club':'Night Club','go_to_rooftop':'Rooftop','go_to_beach':'Beach','go_to_park':'Park','go_home':'Apartments','eat_home':'Apartments','shower':'Apartments','get_dressed':'Apartments','sleep':'Apartments','relax_home':'Apartments','watch_tv':'Apartments','use_phone':'Apartments','gaming':'Apartments'}
EFFECT={
'sleep':dict(energy=16,hunger=4,sleepiness=-18,hygiene=-2,fun=2,social_need=1,stress=-7,comfort=7),'eat_home':dict(energy=5,hunger=-55,sleepiness=2,hygiene=-2,fun=5,social_need=1,stress=-2,comfort=5),'eat_cafe':dict(energy=6,hunger=-60,sleepiness=2,hygiene=-2,fun=9,social_need=-7,stress=-4,comfort=4),'shower':dict(energy=-2,hunger=1,sleepiness=1,hygiene=55,fun=2,stress=-8,comfort=10),'get_dressed':dict(energy=-1,hunger=1,hygiene=0,fun=1,stress=-1,comfort=3),'work':dict(energy=-10,hunger=8,sleepiness=7,hygiene=-5,fun=-3,social_need=1,stress=4,comfort=-2),'go_to_college':dict(energy=-3,hunger=3,sleepiness=2,hygiene=-2,fun=1,social_need=-1,stress=1,comfort=2),'attend_college':dict(energy=-7,hunger=6,sleepiness=5,hygiene=-3,fun=2,social_need=-2,stress=3,comfort=0),'study':dict(energy=-6,hunger=5,sleepiness=4,hygiene=-2,fun=-1,social_need=1,stress=2,comfort=2),'relax_home':dict(energy=3,hunger=3,sleepiness=2,hygiene=-1,fun=10,social_need=2,stress=-9,comfort=8),'watch_tv':dict(energy=2,hunger=3,sleepiness=4,hygiene=-1,fun=13,social_need=2,stress=-9,comfort=7),'use_phone':dict(energy=-1,hunger=3,sleepiness=2,hygiene=-1,fun=7,social_need=-5,stress=-1,comfort=2),'gaming':dict(energy=-2,hunger=3,sleepiness=3,hygiene=-1,fun=14,social_need=-3,stress=-5,comfort=5),'recreation':dict(energy=1,hunger=3,sleepiness=2,hygiene=-1,fun=9,social_need=1,stress=-7,comfort=6),'walk':dict(energy=-5,hunger=5,sleepiness=3,hygiene=-3,fun=9,social_need=-3,stress=-7,comfort=3),'socialize':dict(energy=-5,hunger=6,sleepiness=3,hygiene=-3,fun=14,social_need=-28,stress=-8,comfort=3),'go_to_club':dict(energy=-7,hunger=7,sleepiness=5,hygiene=-4,fun=14,social_need=-22,stress=-4,comfort=2),'go_to_rooftop':dict(energy=-3,hunger=4,sleepiness=2,hygiene=-2,fun=7,social_need=-3,stress=-5,comfort=5),'go_to_beach':dict(energy=-4,hunger=5,sleepiness=2,hygiene=-4,fun=10,social_need=-2,stress=-7,comfort=7),'shop':dict(energy=-4,hunger=4,sleepiness=2,hygiene=-2,fun=4,social_need=-2,stress=-2,comfort=5),'go_home':dict(energy=-1,hunger=3,sleepiness=2,hygiene=-1,fun=1,social_need=1,stress=-3,comfort=5),'wait':dict(energy=-1,hunger=5,sleepiness=3,hygiene=-1,fun=-1,social_need=2,stress=1,comfort=1)}
VALID_GOALS=AI_VALID_GOALS

def log_event(event,**data):
 x={'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S'),'event':event,**data}
 try:
  with LOGLOCK: EVENTS.open('a',encoding='utf8').write(json.dumps(x,ensure_ascii=False)+'\n')
 except: pass

def log(msg):
 print('[Midnight City]',msg,flush=True)
 try:
  with LOGLOCK: LOG.open('a',encoding='utf8').write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}\n')
 except: pass

def clock(m): m=int(m)%1440; return f'{m//60:02d}:{m%60:02d}'
def clamp(v): return max(0,min(100,float(v)))
def travel(a,b):
 return ai_travel_minutes(a, b)

def choose_date_destination(current):
    choices=[x for x in DATE_LOCATIONS if x != current]
    # Prefer a natural date venue; never silently keep both NPCs in place.
    order={"Cafe":["Park","Rooftop","Beach"],"Park":["Cafe","Rooftop","Beach"],"Rooftop":["Cafe","Park","Beach"],"Beach":["Cafe","Park","Rooftop"]}
    for x in order.get(current, ["Cafe","Park","Rooftop","Beach"]):
        if x != current: return x
    return choices[0] if choices else "Cafe"

def date_travel_step(src, dst):
    names={"Cafe":"cafe","Park":"park","Rooftop":"rooftop","Beach":"beach","Downtown":"downtown","Night Club":"club"}
    return step("go_to_"+names.get(dst,dst.lower().replace(" ","_")), travel(src,dst), f"Going to {dst} for a date")

def apply_move_in(aid, bid):
    a=STATE['characters'].get(aid); b=STATE['characters'].get(bid)
    if not a or not b: return None
    # Keep the initiator's residence as the shared home; both retain a stable address label.
    shared=a.get('home') or b.get('home') or 'Shared Apartment'
    old_a=a.get('home'); old_b=b.get('home')
    a['home']=shared; b['home']=shared
    a.setdefault('living_together',True); b.setdefault('living_together',True)
    a['living_together']=True; b['living_together']=True
    remember(aid,f'Moved in with {b["name"]} at {shared}.','life_event',1.0)
    remember(bid,f'Moved in with {a["name"]} at {shared}.','life_event',1.0)
    log_event('move_in_completed',character_id=aid,character_name=a['name'],target_id=bid,target_name=b['name'],shared_home=shared,old_home={aid:old_a,bid:old_b},sim_minutes=STATE['sim_minutes'])
    return shared

def obligations(now,c):
 day=(now//1440)%7; hour=(now%1440)/60; out=[]
 for st_h,end_h,title in schedule_for(c).get(day,[]):
  if st_h<=hour<end_h:
   out.append({'type':'college','title':title,'start':st_h,'end':end_h,'urgent':True})
  elif hour<st_h and st_h-hour<=1.25:
   out.append({'type':'college','title':title,'start':st_h,'end':end_h,'urgent':True})
 return out

def personality_prompt(c): return {k:round(float(v),2) for k,v in (c.get('personality') or {}).items()}
def needs(c): return {k:round(float(c.get(k,0)),1) for k in ('hunger','sleepiness','energy','hygiene','stress','fun','social_need')}

def social_place_key(c):
    """Exact social location. Apartments are NOT one shared room: each NPC has a home.
    Public zones (Cafe, College, Park, etc.) are shared meeting spaces.
    """
    loc=str(c.get("location") or "")
    if loc == "Apartments":
        return f"home:{c.get('home','unknown')}"
    return f"public:{loc}"

def can_socially_meet(a, b):
    return social_place_key(a) == social_place_key(b)

def relationship_defaults():
 return {
  'kirill':{
   'anya':{'friendship':82,'trust':88,'attraction':0,'annoyance':2,'respect':72,'last_interaction':None,'status':'sister','family_role':'sister'},
   'natalia':{'friendship':88,'trust':92,'attraction':0,'annoyance':1,'respect':84,'last_interaction':None,'status':'mother','family_role':'mother'},
   'katya':{'friendship':68,'trust':60,'attraction':0,'annoyance':3,'respect':62,'last_interaction':None,'status':'cousin','family_role':'cousin'},
   'sonya':{'friendship':55,'trust':64,'attraction':12,'annoyance':4,'respect':72,'last_interaction':None,'status':'friend','family_role':None},
  },
  'anya':{'kirill':{'friendship':82,'trust':88,'attraction':0,'annoyance':2,'respect':72,'last_interaction':None,'status':'brother','family_role':'brother'}},
  'natalia':{'kirill':{'friendship':88,'trust':92,'attraction':0,'annoyance':1,'respect':84,'last_interaction':None,'status':'son','family_role':'son'}},
  'katya':{'kirill':{'friendship':68,'trust':60,'attraction':0,'annoyance':3,'respect':62,'last_interaction':None,'status':'cousin','family_role':'cousin'}},
  'sonya':{'kirill':{'friendship':55,'trust':64,'attraction':12,'annoyance':4,'respect':72,'last_interaction':None,'status':'friend'}},
 }

def remember(cid, text, kind='episodic', importance=0.5, day=None, sim_minutes=None):
 with LOCK:
  c=STATE['characters'].get(cid)
  if not c: return
  item={'text':str(text)[:500],'kind':kind,'importance':round(float(importance),2),'day':STATE['day'] if day is None else int(day),'time':clock(STATE['sim_minutes'] if sim_minutes is None else sim_minutes)}
  c.setdefault('memory_items',[]).append(item)
  c['memory_items']=c['memory_items'][-40:]
  c.setdefault('episodic_memory',[]).append(item['text'])
  c['episodic_memory']=c['episodic_memory'][-30:]

def relationship_status(a, b, rel):
 """Stable human-readable relationship stage. Romantic status is reached by a real
 kiss milestone; ordinary attraction alone does not silently make them a couple.
 """
 rel = rel or {}
 current = str(rel.get('status') or '')
 if current in {'boyfriend','girlfriend'}:
  return current
 f=float(rel.get('friendship',0)); trust=float(rel.get('trust',0)); attraction=float(rel.get('attraction',0))
 if f >= 35 and trust >= 30:
  return 'friend'
 return 'acquaintance'

def refresh_relationship_status(aid, bid):
 a=STATE['characters'].get(aid); b=STATE['characters'].get(bid)
 if not a or not b: return
 rel=a.setdefault('relationships',{}).setdefault(bid,{})
 new=relationship_status(a,b,rel)
 if rel.get('status') != new:
  old=rel.get('status','acquaintance')
  rel['status']=new
  log_event('relationship_status_changed', character_id=aid, character_name=a['name'],
            target_id=bid, target_name=b['name'], old_status=old, new_status=new,
            sim_minutes=STATE['sim_minutes'])

def update_relationship(aid,bid,friendship=0,trust=0,attraction=0,annoyance=0,respect=0,reason=''):
 with LOCK:
  a=STATE['characters'].get(aid); b=STATE['characters'].get(bid)
  if not a or not b: return
  rel=a.setdefault('relationships',{}).setdefault(bid,{'friendship':50,'trust':50,'attraction':10,'annoyance':0,'respect':50,'last_interaction':None})
  before={k:round(float(rel.get(k,0)),2) for k in ('friendship','trust','attraction','annoyance','respect')}
  for k,v in [('friendship',friendship),('trust',trust),('attraction',attraction),('annoyance',annoyance),('respect',respect)]: rel[k]=round(clamp(rel.get(k,0)+v),2)
  rel['last_interaction']=STATE['sim_minutes']
  after={k:round(float(rel.get(k,0)),2) for k in before}
  delta={k:round(after[k]-before[k],2) for k in before if after[k]!=before[k]}
  if reason: remember(aid,reason,'relationship',0.7)
  BRAIN.note_event(aid,STATE['sim_minutes'],'relationship_change',f'{b["name"]}: {reason}')
  log_event('relationship_changed',character_id=aid,character_name=a['name'],target_id=bid,target_name=b['name'],
            before=before,after=after,delta=delta,reason=reason,sim_minutes=STATE['sim_minutes'])

def initial_characters():
 return {
 'sonya':{'name':'Sonya','gender':'female','age':28,'occupation':'college student + freelance photographer','education':{'college':COLLEGE,'program':'Photography & Visual Media','year':2,'attendance_rate':92,'attended_classes':0,'missed_classes':0},'home':'Apartment 4B','location':'Apartments','action':'Waking up at home','mood':72,'energy':84,'stress':16,'curiosity':64,'social_need':34,'hunger':42,'sleepiness':10,'hygiene':78,'fun':58,'comfort':76,'money':620,'habits':['morning coffee','regular breakfast','weekday college attendance','photography work Mon/Wed/Fri evenings','evening relaxation','usually sleeps around midnight'],'goals':['attend college and keep attendance above 80%','finish current photo project','find a second client','maintain a normal routine'],'memory':['Moved to Midnight City three months ago.','Studies Photography & Visual Media at Midnight City College in person.','Prefers a calm morning before class.'],'personality':{'sociability':.62,'discipline':.68,'impulsiveness':.28,'laziness':.32,'curiosity':.64,'risk_taking':.30,'routine_preference':.58,'social_energy':.60,'work_drive':.60,'spontaneity':.35},'preferences':{'recreation_action':'photography','interests':['photography','coffee','art_galleries','quiet_walks','cinema','social_cafes'],'favorite_places':['Arts & Culture','Cafe Quarter','Grand Leisure Park','Beach'],'recreation_preferences':[{'action':'photography','places':['Arts & Culture','Waterfront & Marina'],'weight':1.0},{'action':'coffee_cafe','places':['Cafe Quarter'],'weight':0.9},{'action':'gallery','places':['Arts & Culture'],'weight':0.8},{'action':'cinema','places':['Downtown'],'weight':0.7},{'action':'walk','places':['Grand Leisure Park','Waterfront & Marina'],'weight':0.7}]},'inner_thoughts':[],'diary':[],'smart_schedule':[],'episodic_memory':[],'last_reflection_day':0},
 'kirill':{'name':'Kirill','gender':'male','age':29,'occupation':'software developer + evening student','education':{'college':COLLEGE,'program':'Computer Science','year':3,'attendance_rate':96,'attended_classes':0,'missed_classes':0},'home':'Apartment 7A','location':'Apartments','action':'Waking up at home','mood':58,'energy':90,'stress':22,'curiosity':78,'social_need':46,'hunger':38,'sleepiness':8,'hygiene':82,'fun':52,'comfort':72,'money':940,'habits':['morning shower','weekday work','coding in the evening','occasional cafe visits','late evening gaming'],'goals':['keep work performance high','finish software project','meet people in the city','maintain a stable routine'],'memory':['Moved to Midnight City recently.','Works as a software developer.','Likes exploring unfamiliar places.','Usually prefers solving problems independently.'],'personality':{'sociability':.48,'discipline':.82,'impulsiveness':.38,'laziness':.24,'curiosity':.78,'risk_taking':.46,'routine_preference':.52,'social_energy':.48,'work_drive':.84,'spontaneity':.42},'preferences':{'recreation_action':'gaming','interests':['programming','gaming','technology','coffee','exploration','cinema','arcades'],'favorite_places':['IT & Offices','Cafe Quarter','Entertainment Quarter','Downtown'],'recreation_preferences':[{'action':'gaming','places':['Entertainment Quarter'],'weight':1.0},{'action':'arcade','places':['Entertainment Quarter'],'weight':0.9},{'action':'coffee_cafe','places':['Cafe Quarter'],'weight':0.8},{'action':'cinema','places':['Downtown'],'weight':0.65},{'action':'explore','places':['Downtown','Waterfront & Marina'],'weight':0.7}]},'inner_thoughts':[],'diary':[],'smart_schedule':[],'episodic_memory':[],'last_reflection_day':0},
 'anya':{'name':'Anya','gender':'female','age':25,'occupation':'nurse + part-time student','education':{'college':COLLEGE,'program':'Healthcare Administration','year':2,'attendance_rate':95,'attended_classes':0,'missed_classes':0},'home':'Apartment 3A','location':'Clinic','action':'Preparing for the day','mood':67,'energy':78,'stress':25,'curiosity':58,'social_need':42,'hunger':35,'sleepiness':12,'hygiene':84,'fun':48,'comfort':70,'money':760,'habits':['early wake-up','morning tea','weekday clinic shifts','calls family regularly','quiet evenings'],'goals':['keep work shifts','finish studies','stay close to family','keep a healthy routine'],'memory':['Kirill is my younger brother.','We are close and talk regularly.'],'personality':{'sociability':.56,'discipline':.84,'impulsiveness':.20,'laziness':.20,'curiosity':.58,'risk_taking':.22,'routine_preference':.78,'social_energy':.55,'work_drive':.78,'spontaneity':.28},'preferences':{'recreation_action':'walk','interests':['walking','fitness','family','cafes','reading','swimming','quiet_recreation'],'favorite_places':['Grand Leisure Park','Gym & Pool','Cafe Quarter','Downtown'],'recreation_preferences':[{'action':'walk','places':['Grand Leisure Park','Waterfront & Marina'],'weight':1.0},{'action':'exercise','places':['Gym & Pool','Sports Complex'],'weight':0.9},{'action':'swimming','places':['Gym & Pool'],'weight':0.8},{'action':'reading','places':['Downtown'],'weight':0.75},{'action':'coffee_cafe','places':['Cafe Quarter'],'weight':0.7}]},'inner_thoughts':[],'diary':[],'smart_schedule':[],'episodic_memory':[],'last_reflection_day':0},
 'natalia':{'name':'Natalia','gender':'female','age':52,'occupation':'school administrator','home':'Apartment 9C','location':'Apartments','action':'Making breakfast','mood':74,'energy':76,'stress':18,'curiosity':52,'social_need':38,'hunger':30,'sleepiness':8,'hygiene':86,'fun':56,'comfort':82,'money':1350,'habits':['early breakfast','weekday work','family calls','evening television','weekend cooking'],'goals':['keep work stable','look after family','maintain the household','have time for herself'],'memory':['Kirill is my son.','Family is very important to me.'],'personality':{'sociability':.72,'discipline':.78,'impulsiveness':.18,'laziness':.28,'curiosity':.52,'risk_taking':.12,'routine_preference':.82,'social_energy':.68,'work_drive':.66,'spontaneity':.24},'preferences':{'recreation_action':'cooking','interests':['cooking','gardening','family','walking','reading','cinema','cafes','quiet_parks'],'favorite_places':['Grand Leisure Park','Downtown','Cafe Quarter','Waterfront & Marina'],'recreation_preferences':[{'action':'cooking','places':['Apartments'],'weight':1.0},{'action':'walk','places':['Grand Leisure Park','Waterfront & Marina'],'weight':0.9},{'action':'reading','places':['Downtown'],'weight':0.75},{'action':'cinema','places':['Downtown'],'weight':0.65},{'action':'coffee_cafe','places':['Cafe Quarter'],'weight':0.65}]},'inner_thoughts':[],'diary':[],'smart_schedule':[],'episodic_memory':[],'last_reflection_day':0},
 'katya':{'name':'Katya','gender':'female','age':26,'occupation':'graphic designer','home':'Apartment 6C','location':'Studio','action':'Working on a design project','mood':63,'energy':82,'stress':29,'curiosity':76,'social_need':49,'hunger':40,'sleepiness':9,'hygiene':80,'fun':61,'comfort':68,'money':880,'habits':['late breakfast','creative work','coffee at cafes','evening walks','weekend family visits'],'goals':['finish client designs','build portfolio','see family regularly','find new creative work'],'memory':['Kirill is my cousin.','We grew up seeing each other at family gatherings.'],'personality':{'sociability':.66,'discipline':.60,'impulsiveness':.42,'laziness':.30,'curiosity':.82,'risk_taking':.48,'routine_preference':.42,'social_energy':.64,'work_drive':.72,'spontaneity':.62},'preferences':{'recreation_action':'design','interests':['graphic_design','art','photography','fashion','cafes','music','walking','galleries'],'favorite_places':['Arts & Culture','Cafe Quarter','Downtown','Waterfront & Marina'],'recreation_preferences':[{'action':'design','places':['Arts & Culture'],'weight':1.0},{'action':'gallery','places':['Arts & Culture'],'weight':0.9},{'action':'coffee_cafe','places':['Cafe Quarter'],'weight':0.85},{'action':'photography','places':['Waterfront & Marina','Arts & Culture'],'weight':0.8},{'action':'walk','places':['Waterfront & Marina','Grand Leisure Park'],'weight':0.7}]},'inner_thoughts':[],'diary':[],'smart_schedule':[],'episodic_memory':[],'last_reflection_day':0},
 }

def fresh_state():
 chars=initial_characters(); rel=relationship_defaults()
 for cid,c in chars.items():
  c['relationships']=copy.deepcopy(rel.get(cid,{}));
  for _oid,_rel in c['relationships'].items(): _rel.setdefault('status','friend')
  c['social_history']=[]; c['conflict_cooldowns']={}; c['living_together']=False; c['romantic_history']={'dates':0,'flirts':0,'hugs':0,'kisses':0,'intimate_encounters':0,'last_romantic_time':None}; c['memory_items']=[{'text':m,'kind':'semantic','importance':0.8,'day':1,'time':'07:30'} for m in c.get('memory',[])]; c['memory_items']=c['memory_items'][-40:]
 now=7*60+30
 return {'sim_minutes':now,'day':1,'running':False,'speed':1,'ai_mode':False,'brain_busy':False,'brain_status':'ready','brain_error':None,'brain_request_seq':0,'brain_status_by_character':{cid:'ready' for cid in chars},'brain_generation':{cid:0 for cid in chars},'last_brain':None,'events':['Simulation ready at 07:30.'],'action_history':[],'journal':[],'characters':chars,'goals':{cid:None for cid in chars},'brain_persistent':True,'brain_online':False,'startup_ready':True,'world_epoch':0,'decision_epoch':0,'smart_reflection_day':{},'pen_influences':[],'next_intentions':{},'day_plans':{},'action_commit':{},'scheduled_events':[],'player_character_id':'kirill','player_mode':True,'player_position':{'x':16.0,'y':25.0},'dialogue_context':None,'dialogue_contexts':{},'dialogue_history':[],'dialogue_histories':{},'selected_target_id':'sonya'}
STATE=fresh_state()

def world_snapshot():
 with LOCK:
  return {'sim_minutes':STATE['sim_minutes'],'day':STATE['day'],'time':clock(STATE['sim_minutes']),'characters':copy.deepcopy(STATE['characters']),'goals':copy.deepcopy(STATE['goals'])}

def load_brain():
 global MODEL_OBJ,TOKENIZER,BRAIN_ERROR
 if MODEL_OBJ is not None:return True
 with BRAIN_LOCK:
  if MODEL_OBJ is not None:return True
  try:
   if AutoTokenizer is None: raise RuntimeError('transformers/torch/peft unavailable')
   log('Brain load: loading tokenizer...'); TOKENIZER=AutoTokenizer.from_pretrained(str(MODEL),trust_remote_code=True)
   if TOKENIZER.pad_token_id is None: TOKENIZER.pad_token=TOKENIZER.eos_token
   log('Brain load: tokenizer ready')
   kwargs={'trust_remote_code':True}
   if torch is not None and torch.cuda.is_available() and BitsAndBytesConfig is not None:
    kwargs['quantization_config']=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.float16,bnb_4bit_use_double_quant=True); kwargs['device_map']='auto'
   else: kwargs['torch_dtype']='auto'; kwargs['device_map']='auto'
   log('Brain load: loading 4-bit base model...'); base=AutoModelForCausalLM.from_pretrained(str(MODEL),**kwargs); log('Brain load: base model ready')
   if ADAPTER.exists() and PeftModel is not None: log('Brain load: loading LoRA adapter...'); MODEL_OBJ=PeftModel.from_pretrained(base,str(ADAPTER)); log('Brain load: LoRA adapter ready')
   else: MODEL_OBJ=base
   BRAIN_ERROR=None; return True
  except Exception as e: BRAIN_ERROR=str(e); log('Brain load ERROR: '+str(e)); return False

def build_prompt(cid):
 with LOCK:
  c=copy.deepcopy(STATE['characters'][cid]); now=STATE['sim_minutes']; goal=STATE['goals'].get(cid)
  other=[]
  for k,x in STATE['characters'].items():
   if k!=cid and x['location']==c['location']:
    rel=(c.get('relationships') or {}).get(k,{})
    opts=contextual_options(c,dict(x,id=k),available_interactions(c,dict(x,id=k),(now%1440)/60),c.get('location'),now)[:6]
    other.append({'id':k,'name':x['name'],'location':x['location'],'action':x['action'],'relationship':rel,'available_interactions':opts})
  hist=[x.get('brain_goal') for x in STATE['action_history'] if x.get('character_id')==cid and x.get('kind')=='goal_started'][-5:]
  schedule=copy.deepcopy(c.get('smart_schedule',[])); thoughts=copy.deepcopy(c.get('inner_thoughts',[]))[-4:]
 ctx=BRAIN.context_for(cid) or {}
 user={'character':c['name'],'clock':clock(now),'day':STATE['day'],'location':c['location'],
       'needs':needs(c),'personality':personality_prompt(c),
       'obligations':obligations(now,c),'nearby_characters':other,'active_goal':goal,
       'recent_goals':hist,'memory':(c.get('memory',[])+[m.get('text','') if isinstance(m,dict) else str(m) for m in c.get('memory_items',[])])[-10:],
       'relationships':copy.deepcopy(c.get('relationships',{})),
       'recent_events':ctx.get('events',[])[-8:],'inner_thoughts':thoughts,'smart_schedule':schedule,
       'player_pen':STATE.get('pen_influences',[])[-3:]}
 system="""You are MidnightBrain, the conscious mind of an autonomous adult NPC.
Think like a life-simulation character, not a task executor. Consider TIME, PLACE,
OCCASION, personality, relationships, memories, obligations and soft needs.
Plan the character's day ahead instead of choosing only the next action.
Create a realistic sequence of 6-10 high-level intentions covering the next part of the day.
Respect fixed obligations, sleep, work/study, needs, personality, relationships and normal life.
The plan is a forecast, not an unbreakable script: player interactions, urgent needs, meetings,
unexpected events and relationship changes can interrupt it. Do not micromanage physical actions.
Never output walking, travelling, showering, dressing, eating at a specific place, opening doors,
or other physical actions. The Goal Executor owns physical behavior.
Each item needs a goal, approximate duration in minutes, and a short first-person thought.
Return ONLY JSON:
{"day_plan":[{"goal":"...","duration_minutes":60,"thought":"..."},...]}
Valid goals: sleep,get_ready,take_care_of_self,eat,attend_obligation,work,study,relax,
socialize,recreation,buy_essentials,personal_goal,wander,wait.
Main sleep should normally be 360-480 minutes.
Do not make every item socialize/recreation; build a believable full day."""
 return system,json.dumps(user,ensure_ascii=False,separators=(',',':'))

def generate_batch(prompts):
 if not load_brain(): raise RuntimeError(BRAIN_ERROR or 'Brain unavailable')
 msgs=[TOKENIZER.apply_chat_template([{'role':'system','content':s},{'role':'user','content':u}],tokenize=False,add_generation_prompt=True) for s,u in prompts]
 old=TOKENIZER.padding_side; TOKENIZER.padding_side='left'
 try:
  x=TOKENIZER(msgs,return_tensors='pt',padding=True,truncation=True).to(MODEL_OBJ.device)
  with torch.inference_mode(): y=MODEL_OBJ.generate(**x,max_new_tokens=MAX_NEW,do_sample=False,pad_token_id=TOKENIZER.pad_token_id)
  n=x['input_ids'].shape[1]; return [TOKENIZER.decode(row[n:],skip_special_tokens=True).strip() for row in y]
 finally: TOKENIZER.padding_side=old

def parse_goal(raw):
 t=str(raw or ''); m=re.search(r'\{.*\}',t,re.S)
 if m:
  try:
   x=json.loads(m.group(0)); g=str(x.get('goal','wait')).strip().lower()
   d=int(x.get('duration_minutes',60)); thought=str(x.get('thought','')).strip()
   return {'goal':g,'duration_minutes':max(10,min(480,d)),'thought':thought,'raw':t}
  except: pass
 return None

def parse_day_plan(raw):
 t=str(raw or ''); m=re.search(r'\{.*\}',t,re.S)
 if not m: return []
 try: x=json.loads(m.group(0))
 except Exception: return []
 items=x.get('day_plan') if isinstance(x,dict) else None
 if not isinstance(items,list): return []
 out=[]
 for item in items:
  if not isinstance(item,dict): continue
  goal=str(item.get('goal','')).strip().lower()
  if goal not in VALID_GOALS: continue
  try: duration=max(10,min(480,int(item.get('duration_minutes',60))))
  except Exception: duration=60
  out.append({'goal':goal,'duration_minutes':duration,'thought':str(item.get('thought','')).strip()})
 return out[:10]

def next_nonrepeat_goal(c, obs, smart_schedule=None):
 recent=[x.get('brain_goal') for x in STATE['action_history'][-12:]
         if x.get('character_id') and x.get('character_name')==c.get('name') and x.get('kind')=='goal_completed']
 return utility_choose(c,STATE['sim_minutes'],obs,[],recent,smart_schedule)

def step(action,duration,text=None):
 return {'action':action,'duration':max(1,int(duration)),'remaining':max(1,int(duration)),
         'text':text or TEXT.get(action,action),'started_at':None,'start_location':None,
         'progress_logged':0}

def build_plan(cid,p,seq,source):
 with LOCK: c=copy.deepcopy(STATE['characters'][cid]); start=STATE['sim_minutes']
 loc=c['location']; g=p['goal']; requested=max(10,min(480,int(p.get('duration_minutes',60)))); steps=[]; target=None
 def go(dst):
  nonlocal loc,target
  if loc!=dst:
   name={'College':'college','Studio':'studio','Cafe':'cafe','Night Club':'club','Rooftop':'rooftop','Beach':'beach','Downtown':'downtown'}.get(dst,'home'); steps.append(step('go_home' if dst=='Apartments' else 'go_to_'+name,travel(loc,dst),f'Going to {dst}')); loc=dst
  target=dst
 if g=='sleep': go('Apartments'); steps.append(step('sleep',420,'Sleeping'))
 elif g=='get_ready':
  go('Apartments');
  if c.get('hygiene',100)<85: steps.append(step('shower',25))
  steps.append(step('get_dressed',10))
  if c.get('hunger',0)>55: steps.append(step('eat_home',25))
 elif g=='take_care_of_self':
  go('Apartments'); steps.append(step('shower',25) if c.get('hygiene',100)<90 else step('relax_home',20))
 elif g=='eat':
  if loc=='Apartments': steps.append(step('eat_home',30)); target='Apartments'
  else: go('Cafe'); steps.append(step('eat_cafe',35))
 elif g=='attend_obligation':
  # One coherent school block; no re-query between classes.
  go('College'); day=(start//1440)%7; hour=start/60%24; schedule=schedule_for(c).get(day,[])
  # Attend only the current/upcoming contiguous class block. Preserve breaks
  # and keep evening students on their own timetable.
  future=[x for x in schedule if x[1]>hour and x[0]>=hour]
  if future:
   first=future[0]; end_hour=first[1]
   for nxt in future[1:]:
    if nxt[0] <= end_hour + 0.01:
     end_hour=max(end_hour,nxt[1])
    else:
     break
   minutes=max(30,int((end_hour-hour)*60))
  else:
   minutes=30
  steps.append(step('attend_college',minutes,'Attending college'))
 elif g=='work': go('Studio'); steps.append(step('work',max(60,min(180,requested))))
 elif g=='study': go('College'); steps.append(step('study',max(60,min(180,requested))))
 elif g=='socialize':
  nearby=[(k,x) for k,x in STATE['characters'].items() if k!=cid and x['location']==loc]
  if nearby:
   hour=(start%1440)/60; ranked=[]
   for oid,other in nearby:
    r=(c.get('relationships') or {}).get(oid,{})
    base=float(r.get('friendship',50))*.55+float(r.get('trust',50))*.20+float(r.get('attraction',10))*.15-float(r.get('annoyance',0))*.50
    ranked.append((base,oid,other))
   ranked.sort(reverse=True,key=lambda x:x[0]); _,oid,other=ranked[0]
   
   contextual=contextual_options(c,dict(other,id=oid),available_interactions(c,dict(other,id=oid),hour),loc,start)
   chosen=contextual[0] if contextual else choose_interaction(c,dict(other,id=oid),hour)
   if chosen:
    steps.append(step('social_interaction',max(5,min(int(requested),int(chosen['minutes']))),interaction_label(chosen['type'],c['name'],other['name'])))
    target=loc
   else: steps.append(step('socialize',max(20,min(60,requested))))
  else:
   go('Night Club'); steps.append(step('socialize',max(30,min(120,requested))))
 elif g=='recreation':
  prefs=c.get('preferences',{}) or {}; choices=prefs.get('recreation_preferences') or []
  choice=None
  if choices:
   ranked=[]
   for item in choices:
    places=item.get('places') or []; w=float(item.get('weight',0.5)) + (0.35 if loc in places else 0)
    ranked.append((w,item))
   ranked.sort(key=lambda x:x[0],reverse=True); choice=ranked[0][1]
  action=(choice or {}).get('action',prefs.get('recreation_action','relax_home')); places=(choice or {}).get('places') or []
  activity_map={'gaming':('Entertainment Quarter','gaming'),'arcade':('Entertainment Quarter','arcade'),'coffee_cafe':('Cafe Quarter','coffee_cafe'),'cinema':('Downtown','cinema'),'walk':('Grand Leisure Park','walk'),'exercise':('Gym & Pool','exercise'),'swimming':('Gym & Pool','swimming'),'reading':('Downtown','reading'),'gallery':('Arts & Culture','gallery'),'photography':('Arts & Culture','photography'),'design':('Arts & Culture','design'),'explore':('Downtown','explore'),'cooking':('Apartments','cooking')}
  dst,act=activity_map.get(action,(places[0] if places else 'Apartments',action))
  if loc!=dst: go(dst)
  text_map={'gaming':'Playing games','arcade':'Playing at the arcade','coffee_cafe':'Having coffee at a cafe','cinema':'Watching a movie','walk':'Taking a walk','exercise':'Working out','swimming':'Swimming','reading':'Reading','gallery':'Visiting an art gallery','photography':'Taking photos','design':'Working on creative designs','explore':'Exploring the city','cooking':'Cooking at home'}
  steps.append(step(act,max(30,min(120,requested)),text_map.get(act,act.replace('_',' ').capitalize())))
 elif g=='buy_essentials': go('Downtown'); steps.append(step('shop',45))
 elif g=='personal_goal': go('Studio'); steps.append(step('work',90,'Working on personal project'))
 elif g=='wander':
  dst='Downtown' if loc!='Downtown' else 'Beach'; go(dst); steps.append(step('walk',max(30,min(90,requested))))
 elif g=='relax':
  if loc!='Apartments' and c.get('energy',100)<45: go('Apartments')
  if loc=='Apartments': steps.append(step('watch_tv' if c.get('personality',{}).get('laziness',.3)>.45 else 'relax_home',max(30,min(90,requested))))
  else: steps.append(step('recreation',max(30,min(90,requested))))
 else: steps.append(step('wait',max(15,min(45,requested))))
 if not steps: steps=[step('wait',15)]
 # Dates are joint activities: pick a real destination and travel there before the social block.
 if g=='socialize' and steps and steps[0]['action']=='social_interaction' and 'Going on a date' in steps[0]['text']:
  dst=choose_date_destination(loc)
  steps.insert(0, date_travel_step(loc,dst))
  target=dst
 total=sum(s['duration'] for s in steps)
 interaction=None
 social_step=next((x for x in steps if x.get('action')=='social_interaction'),None)
 if g=='socialize' and social_step is not None:
  text=social_step['text']
  for oid,other in STATE['characters'].items():
   if oid!=cid and other.get('location')==c.get('location') and other.get('name') in text:
    for k in INTERACTIONS:
     if interaction_label(k,c['name'],other['name'])==text:
      interaction={'target_id':oid,'type':k,'resolved':False,'accepted':None}; break
   if interaction: break
 # A date is a joint commitment: schedule the target's travel immediately so both
 # NPCs can actually meet at the selected venue before acceptance is evaluated.
 if interaction and interaction.get('type')=='date':
  destination=choose_date_destination(c.get('location'))
  target_id=interaction.get('target_id')
  if target_id in STATE['characters'] and not STATE['goals'].get(target_id):
   STATE['goals'][target_id]=make_paired_date_plan(target_id,cid,'date',destination,start)
 return {'id':f'{cid}-{seq}-{int(time.time()*1000)}','goal':g,'label':g.replace('_',' ').title(),'action_text':steps[0]['text'],'brain_intention':g,'action':steps[0]['action'],'start':start,'end':start+total,'duration_minutes':total,'step_index':0,'steps':steps,'target_location':target,'interaction':interaction,'source':source,'brain_request_seq':seq,'started':False,'status':'active'}

def apply_effect(c,action,mins):
 for k,v in EFFECT.get(action,{}).items(): c[k]=clamp(c.get(k,0)+float(v)*mins/60)
 c['hunger']=clamp(c.get('hunger',0)+7*mins/60); c['sleepiness']=clamp(c.get('sleepiness',0)+4*mins/60); c['hygiene']=clamp(c.get('hygiene',100)-2*mins/60)
 if action=='sleep': c['sleepiness']=clamp(c['sleepiness']-22*mins/60)

def make_paired_date_plan(target_id, initiator_id, interaction_type, destination, start_time):
    t=STATE['characters'][target_id]
    src=t.get('location')
    steps=[]
    if src != destination:
        steps.append(date_travel_step(src,destination))
    # The target waits at the venue until the initiator's proposal is accepted;
    # this prevents the target from independently locking the pair before the proposal resolves.
    steps.append(step('wait_for_date',INTERACTIONS.get(interaction_type,{}).get('minutes',90),'Waiting for the date to begin'))
    return {'id':f'{target_id}-paired-{int(time.time()*1000)}','goal':'socialize','label':interaction_label(interaction_type,t['name'],STATE['characters'][initiator_id]['name']),'action_text':steps[0]['text'],'brain_intention':'socialize','action':steps[0]['action'],'start':start_time,'end':start_time+sum(x['duration'] for x in steps),'duration_minutes':sum(x['duration'] for x in steps),'step_index':0,'steps':steps,'target_location':destination,'interaction':{'target_id':initiator_id,'type':interaction_type,'resolved':False,'accepted':None,'paired':True,'primary':False},'source':'paired_social','brain_request_seq':STATE.get('brain_request_seq',0),'started':False,'status':'active'}

def execute_one_minute(cid,plan):
 c=STATE['characters'][cid]; s=plan['steps'][plan['step_index']]; action=s['action']
 if action=='social_interaction' and plan.get('interaction') and not plan['interaction'].get('resolved'):
  clear_expired(STATE, STATE['sim_minutes'])
  inter=plan['interaction']; oid=inter.get('target_id'); other=STATE['characters'].get(oid)
  existing=active_lock(STATE, cid, oid) if oid else None
  if existing and existing.get('initiator') != cid:
   inter['resolved']=True; inter['accepted']=False; inter['reason']='already_engaged'; s['remaining']=1; s['duration']=1
   s['text']=f'{other["name"]} is already talking with someone' if other else 'Interaction unavailable'
   log_event('interaction_busy',character_id=cid,character_name=c['name'],target_id=oid,target_name=other['name'] if other else None,interaction=inter['type'],sim_minutes=STATE['sim_minutes'])
  elif not other or not can_socially_meet(c, other):
   # The social plan became stale while Brain was thinking or while another NPC moved.
   # This is not a rejection and should not spam the journal as a 'missed' interaction.
   inter['resolved']=True; inter['accepted']=False; inter['reason']='target_unavailable_or_moved'; s['remaining']=1; s['duration']=1; s['text']='Social opportunity changed'
   log_event('interaction_replanned',character_id=cid,character_name=c['name'],target_id=oid,
             target_name=other['name'] if other else None,interaction=inter.get('type'),
             reason='target_unavailable_or_moved',sim_minutes=STATE['sim_minutes'])
  else:
   accepted=willingness(other,dict(c,id=cid),inter['type'],(STATE['sim_minutes']%1440)/60)
   alt_opts=contextual_options(other,dict(c,id=cid),available_interactions(other,dict(c,id=cid),(STATE['sim_minutes']%1440)/60),other.get('location'),STATE['sim_minutes'])
   counter=choose_counter_offer(other,c,inter['type'],alt_opts) if accepted < .45 else None
   inter['resolved']=True; inter['accepted']=accepted>=.45; inter['willingness']=round(accepted,3); inter['counter_offer']=counter
   log_event('interaction_proposed',character_id=cid,character_name=c['name'],target_id=oid,target_name=other['name'],interaction=inter['type'],willingness=round(accepted,3),accepted=inter['accepted'],counter_offer=counter,sim_minutes=STATE['sim_minutes'])
   if not inter['accepted']:
    if counter:
     inter['accepted']=True; inter['type']=counter; s['text']=interaction_label(counter,c['name'],other['name']); s['duration']=INTERACTIONS.get(counter,{}).get('minutes',10); s['remaining']=s['duration']
     log_event('interaction_counter_offer',character_id=oid,character_name=other['name'],target_id=cid,target_name=c['name'],interaction=counter,sim_minutes=STATE['sim_minutes'])
    else:
     s['remaining']=1; s['duration']=1; s['text']=f'{other["name"]} declined {inter["type"].replace("_"," ")}'
   if inter['accepted']:
    if inter['type']=='date' and not inter.get('player_initiated'):
     # Joint date: both NPCs receive the same destination and one shared social lock.
     destination=plan.get('target_location') or choose_date_destination(c.get('location'))
     existing_target=STATE['goals'].get(oid)
     # Target should already be traveling from the joint-date setup. If not, create the paired plan now.
     if not existing_target or existing_target.get('source')!='paired_social':
      STATE['goals'][oid]=make_paired_date_plan(oid,cid,'date',destination,STATE['sim_minutes'])
     # Replace the initiator's current social step with travel + date.
     current_duration=INTERACTIONS.get('date',{}).get('minutes',90)
     remaining_steps=[]
     if c.get('location')!=destination:
      remaining_steps.append(date_travel_step(c.get('location'),destination))
     remaining_steps.append(step('social_interaction',current_duration,interaction_label('date',c['name'],other['name'])))
     plan['steps']=remaining_steps; plan['step_index']=0; plan['target_location']=destination
     plan['interaction']=inter
     inter['resolved']=True; inter['accepted']=True; inter['paired']=True; inter['primary']=True
     target_plan=STATE['goals'].get(oid)
     if target_plan and target_plan.get('source')=='paired_social':
      target_plan['interaction']={'target_id':cid,'type':'date','resolved':True,'accepted':True,'paired':True,'primary':False}
      if target_plan.get('step_index',0) < len(target_plan.get('steps',[])):
       target_plan['steps']=target_plan['steps'][:target_plan['step_index']+1] + [step('social_interaction',INTERACTIONS['date']['minutes'],interaction_label('date',other['name'],c['name']))]
       target_plan['steps'][target_plan['step_index']+1]['started_at']=None
       target_plan['steps'][target_plan['step_index']+1]['remaining']=INTERACTIONS['date']['minutes']
       target_plan['action']='social_interaction'; target_plan['action_text']=target_plan['steps'][target_plan['step_index']+1]['text']
     s=plan['steps'][0]
    if not _commit_action_locked(cid, STATE['sim_minutes'], {'goal':'socialize','interaction':inter['type']}, 'interaction'):
     inter['resolved']=True; inter['accepted']=False; s['remaining']=1; s['duration']=1; s['text']='Interaction superseded by another committed action'
     log_event('interaction_duplicate_suppressed',character_id=cid,character_name=c['name'],target_id=oid,target_name=other['name'],interaction=inter['type'],sim_minutes=STATE['sim_minutes'])
     return
    set_lock(STATE,cid,oid,inter['type'],STATE['sim_minutes']+INTERACTIONS.get(inter['type'],{}).get('minutes',10))
    meta=INTERACTIONS.get(inter['type'],{})
    if not inter.get('player_initiated'):
     update_relationship(cid,oid,friendship=meta.get('friendship',0),trust=meta.get('trust',0),attraction=meta.get('attraction',0),annoyance=meta.get('annoyance',0),respect=meta.get('respect',0),reason=f'{inter["type"].replace("_"," ").capitalize()} with {other["name"]}.')
     update_relationship(oid,cid,friendship=meta.get('friendship',0)*.75,trust=meta.get('trust',0)*.75,attraction=meta.get('attraction',0)*.75,annoyance=meta.get('annoyance',0)*.75,respect=meta.get('respect',0)*.75,reason=f'{inter["type"].replace("_"," ").capitalize()} with {c["name"]}.')
     remember(cid,f'{inter["type"].replace("_"," ").capitalize()} with {other["name"]}.','episodic',.8); remember(oid,f'{inter["type"].replace("_"," ").capitalize()} with {c["name"]}.','episodic',.75)
    c['recent_interaction_types']=[inter['type']]+(c.get('recent_interaction_types') or [])[:4]; other['recent_interaction_types']=[inter['type']]+(other.get('recent_interaction_types') or [])[:4]
    # Persist real social history. This is also the source used by the cooldown system;
    # without it, repeated proposals could immediately return after every interaction.
    for who, target, target_id in ((c, other, oid), (other, c, cid)):
     who.setdefault('social_history', []).append({'time':STATE['sim_minutes'],'target_id':target_id,'type':inter['type']})
     who['social_history']=who['social_history'][-80:]
     who.setdefault('romantic_history', {'dates':0,'flirts':0,'hugs':0,'kisses':0,'intimate_encounters':0,'last_romantic_time':None})
     if inter['type'] in {'flirt','romantic_conversation','date','hug','kiss','intimacy'}:
      key={'flirt':'flirts','romantic_conversation':'flirts','date':'dates','hug':'hugs','kiss':'kisses','intimacy':'intimate_encounters'}[inter['type']]
      who['romantic_history'][key]=int(who['romantic_history'].get(key,0))+1
      who['romantic_history']['last_romantic_time']=STATE['sim_minutes']
    c['social_need']=clamp(c.get('social_need',0)-18); other['social_need']=clamp(other.get('social_need',0)-10)
    c['mood']=clamp(c.get('mood',50)+4); other['mood']=clamp(other.get('mood',50)+3)
    log_event('interaction_started',character_id=cid,character_name=c['name'],target_id=oid,target_name=other['name'],interaction=inter['type'],sim_minutes=STATE['sim_minutes'])
 if action=='social_interaction' and plan.get('interaction') and plan['interaction'].get('accepted') and plan['interaction'].get('resolved') and not plan['interaction'].get('started_logged'):
  inter=plan['interaction']; oid=inter.get('target_id'); other=STATE['characters'].get(oid)
  if other:
   inter['started_logged']=True
   log_event('interaction_started',character_id=cid,character_name=c['name'],target_id=oid,target_name=other['name'],interaction=inter.get('type'),sim_minutes=STATE['sim_minutes'])
 if s.get('started_at') is None:
  s['started_at']=STATE['sim_minutes']; s['start_location']=c.get('location')
  log_event('action_start',character_id=cid,character_name=c['name'],sim_minutes=STATE['sim_minutes'],
            goal=plan['goal'],action=action,action_text=s['text'],duration_minutes=s['duration'],
            from_location=c.get('location'),destination=plan.get('target_location'),request_seq=plan['brain_request_seq'])
  STATE['action_history'].append({'start':STATE['sim_minutes'],'end':STATE['sim_minutes']+s['duration'],
    'action':action,'action_text':s['text'],'from_location':c.get('location'),'location':c.get('location'),
    'destination':plan.get('target_location'),'kind':'body_action','character_id':cid,'character_name':c['name'],
    'brain_goal':plan['goal'],'journal_status':'NOW','request_seq':plan['brain_request_seq']})
 s['remaining']=max(0,s['remaining']-1)
 if action.startswith('go_to_') or action=='go_home': c['location']=TARGET.get(action,c['location'])
 apply_effect(c,'socialize' if action=='social_interaction' else action,1)
 if action=='work': c['money']=round(c.get('money',0)+35/60,2)
 if action=='socialize':
  for oid,other in STATE['characters'].items():
   if oid!=cid and other.get('location')==c.get('location'):
    update_relationship(cid,oid,friendship=1.5,trust=.6,annoyance=-.8,reason=f'Spent time socializing with {other["name"]}.')
    remember(cid,f'Positive social time with {other["name"]}.','episodic',0.75)
 if action=='eat_home': c['hunger']=clamp(c['hunger']-55/30)
 if action=='eat_cafe': c['hunger']=clamp(c['hunger']-60/35); c['money']=max(0,c['money']-14/35)
 if action=='shower': c['hygiene']=clamp(c['hygiene']+55/25)
 c['action']=s['text']; plan['action']=action; plan['action_text']=s['text']; plan['started']=True
 elapsed=s['duration']-s['remaining']
 if elapsed>0 and elapsed % 15 == 0 and s.get('progress_logged') != elapsed:
  s['progress_logged']=elapsed
  log_event('action_progress',character_id=cid,character_name=c['name'],sim_minutes=STATE['sim_minutes']+1,
            goal=plan['goal'],action=action,action_text=s['text'],elapsed_minutes=elapsed,
            remaining_minutes=s['remaining'],progress=f'{elapsed}/{s["duration"]}')
 if s['remaining']<=0:
  log_event('action_complete',character_id=cid,character_name=c['name'],sim_minutes=STATE['sim_minutes']+1,
            goal=plan['goal'],action=action,action_text=s['text'],duration_minutes=s['duration'],
            from_location=s.get('start_location'),location=c.get('location'),destination=plan.get('target_location'),
            request_seq=plan['brain_request_seq'])
  if action == 'social_interaction' and plan.get('interaction') and plan['interaction'].get('accepted'):
   inter=plan['interaction']; oid=inter.get('target_id'); other=STATE['characters'].get(oid)
   if other and inter.get('primary', True):
    log_event('interaction_complete',character_id=cid,character_name=c['name'],target_id=oid,target_name=other['name'],interaction=inter.get('type'),sim_minutes=STATE['sim_minutes']+1)
    remember(cid,f'Completed {inter.get("type","interaction").replace("_"," ")} with {other["name"]}.','episodic',.9)
    remember(oid,f'Completed {inter.get("type","interaction").replace("_"," ")} with {c["name"]}.','episodic',.85)
    if inter.get('type')=='move_in_together':
     apply_move_in(cid,oid)
    # A couple status is earned by an actual romantic milestone, not by Attr alone.
    if inter.get('type')=='kiss':
     rel_c=STATE['characters'][cid].setdefault('relationships',{}).setdefault(oid,{})
     rel_o=STATE['characters'][oid].setdefault('relationships',{}).setdefault(cid,{})
     rel_c['status']='boyfriend' if STATE['characters'][oid].get('gender')=='male' else 'girlfriend'
     rel_o['status']='boyfriend' if STATE['characters'][cid].get('gender')=='male' else 'girlfriend'
     log_event('relationship_status_changed',character_id=cid,character_name=c['name'],target_id=oid,target_name=other['name'],
               old_status='friend',new_status=rel_c['status'],reason='kiss',sim_minutes=STATE['sim_minutes']+1)
     log_event('relationship_status_changed',character_id=oid,character_name=other['name'],target_id=cid,target_name=c['name'],
               old_status='friend',new_status=rel_o['status'],reason='kiss',sim_minutes=STATE['sim_minutes']+1)
  plan['step_index']+=1
  if plan['step_index']<len(plan['steps']):
   nxt=plan['steps'][plan['step_index']]; c['action']=nxt['text']; plan['action']=nxt['action']; plan['action_text']=nxt['text']
  else: return True
 return False

def append_action(cid,plan,action_start,action_end,status):
 c=STATE['characters'][cid]; s=plan['steps'][max(0,min(plan['step_index']-1,len(plan['steps'])-1))]
 STATE['action_history'].append({'start':action_start,'end':action_end,'action':s['action'],'action_text':s['text'],'from_location':c['location'],'location':c['location'],'destination':plan.get('target_location'),'kind':'body_action','character_id':cid,'character_name':c['name'],'brain_goal':plan['goal'],'journal_status':status,'request_seq':plan['brain_request_seq']})

def _smart_reflect_if_needed(day):
 with LOCK:
  # End-of-day reflection is deferred for a sleeping character. We never
  # mutate the diary/schedule while the character is physically asleep.
  if STATE.get('smart_reflection_day',{}).get(day): return
  minute=STATE['sim_minutes'] % 1440
  if minute < 23*60: return
  ids=list(STATE['characters'])
  all_done=True
  for cid in ids:
   c=STATE['characters'][cid]
   if int(c.get('last_reflection_day',0))>=day: continue
   plan=STATE['goals'].get(cid)
   if plan and plan.get('action')=='sleep':
    c['reflection_pending_day']=day
    all_done=False
    continue
   events=[x for x in STATE['action_history'] if x.get('character_id')==cid]
   reflection=reflect_day(c,events); diary=reflection.get('text',str(reflection))
   c.setdefault('diary',[]).append({'day':day,'text':diary,'lessons':reflection.get('lessons',[])})
   c['diary']=c['diary'][-14:]
   c['smart_schedule']=schedule_from_reflection(c,STATE['sim_minutes'],reflection)
   c['last_reflection_day']=day
   c.pop('reflection_pending_day',None)
   remember(cid,diary,'reflection',0.8,day,STATE['sim_minutes'])
   for lesson in reflection.get('lessons',[]): remember(cid,lesson,'lesson',0.7,day,STATE['sim_minutes'])
   for k,v in reflection.get('preferences',{}).items(): c.setdefault('preferences',{})[k]=v
   # Reflection changes personality slowly, not abruptly.
   if 'social contact mattered' in reflection.get('lessons',[]): c['personality']['sociability']=clamp(float(c['personality'].get('sociability',.5))*100+1)/100
   if 'leisure helped recover mood' in reflection.get('lessons',[]): c['personality']['routine_preference']=round(clamp(float(c['personality'].get('routine_preference',.5))+.01),3)
   if 'productive time was part of the day' in reflection.get('lessons',[]): c['personality']['discipline']=round(clamp(float(c['personality'].get('discipline',.5))+.008),3)
   log_event('daily_reflection',character_id=cid,character_name=c['name'],day=day,
             diary=diary,smart_schedule=c['smart_schedule'])
  if all(int(STATE['characters'][cid].get('last_reflection_day',0))>=day for cid in ids):
   STATE.setdefault('smart_reflection_day',{})[day]=True

def _reflect_after_wake(cid):
 with LOCK:
  c=STATE['characters'].get(cid)
  if not c: return
  day=int(c.get('reflection_pending_day',0))
  if not day or int(c.get('last_reflection_day',0))>=day: return
  # Only run after the sleep action has actually completed.
  events=[x for x in STATE['action_history'] if x.get('character_id')==cid]
  reflection=reflect_day(c,events); diary=reflection.get('text',str(reflection))
  c.setdefault('diary',[]).append({'day':day,'text':diary,'lessons':reflection.get('lessons',[])})
  c['diary']=c['diary'][-14:]
  c['smart_schedule']=schedule_from_reflection(c,STATE['sim_minutes'],reflection)
  c['last_reflection_day']=day
  c.pop('reflection_pending_day',None)
  remember(cid,diary,'reflection',0.8,day,STATE['sim_minutes'])
  for lesson in reflection.get('lessons',[]): remember(cid,lesson,'lesson',0.7,day,STATE['sim_minutes'])
  for k,v in reflection.get('preferences',{}).items(): c.setdefault('preferences',{})[k]=v
  if 'social contact mattered' in reflection.get('lessons',[]): c['personality']['sociability']=round(clamp(float(c['personality'].get('sociability',.5))+0.01)/1,3)
  if 'leisure helped recover mood' in reflection.get('lessons',[]): c['personality']['routine_preference']=round(clamp(float(c['personality'].get('routine_preference',.5))+0.01),3)
  if 'productive time was part of the day' in reflection.get('lessons',[]): c['personality']['discipline']=round(clamp(float(c['personality'].get('discipline',.5))+0.008),3)
  log_event('daily_reflection',character_id=cid,character_name=c['name'],day=day,
            diary=diary,lessons=reflection.get('lessons',[]),smart_schedule=c['smart_schedule'],deferred=True)

def advance(minutes,source='clock'):
 completed=[]
 for _ in range(max(0,int(minutes))):
  with LOCK:
   if not STATE['running']:
    break
   # One outer iteration is exactly ONE simulation minute, regardless of how
   # many NPCs are active. Previously sim_minutes was incremented inside the
   # NPC loop, so two characters made the world run at 2x time unintentionally.
   now=STATE['sim_minutes']
   tick_end=now+1
   sleep_wakes=[]
   for cid,plan in list(STATE['goals'].items()):
    if not plan:
     continue
    oldidx=int(plan.get('step_index',0) or 0)
    oldsteps=plan.get('steps') or []
    ended = oldsteps[oldidx] if 0 <= oldidx < len(oldsteps) else None
    done=execute_one_minute(cid,plan)
    if ended is not None and oldidx!=int(plan.get('step_index',0) or 0):
     STATE['action_history'].append({'start':ended.get('started_at',now),
       'end':tick_end,'action':ended.get('action','action'),'action_text':ended.get('text',''),
       'from_location':ended.get('start_location',STATE['characters'][cid]['location']),
       'location':STATE['characters'][cid]['location'],'destination':plan.get('target_location'),
       'kind':'body_action','character_id':cid,'character_name':STATE['characters'][cid]['name'],
       'brain_goal':plan.get('goal',''),'journal_status':'DONE','request_seq':plan.get('brain_request_seq')})
    if done:
     goal_name=plan['goal']
     completed.append((cid,goal_name))
     log_event('goal_complete',character_id=cid,character_name=STATE['characters'][cid]['name'],
               sim_minutes=tick_end,goal=goal_name,duration_minutes=tick_end-plan['start'],
               request_seq=plan['brain_request_seq'])
     STATE['action_history'].append({'start':plan['start'],'end':tick_end,'action':goal_name,
       'action_text':plan['label'],'from_location':STATE['characters'][cid]['location'],
       'location':STATE['characters'][cid]['location'],'destination':plan.get('target_location'),
       'kind':'goal_completed','character_id':cid,'character_name':STATE['characters'][cid]['name'],
       'brain_goal':goal_name,'journal_status':'DONE','request_seq':plan['brain_request_seq']})
     c=STATE['characters'][cid]
     remember(cid,f'Completed {goal_name} at {clock(tick_end)}.','outcome',0.55,STATE['day'],tick_end)
     c['last_goal_outcome']={'goal':goal_name,'time':clock(tick_end),'day':STATE['day']}
     STATE['goals'][cid]=None
     # Never leave the body idle while the shared LLM is thinking. Consume a
     # buffered Brain intention first; otherwise choose a deterministic Utility
     # fallback immediately. Brain will continue refining the following goal in
     # the background.
     queued_day=STATE.setdefault('day_plans',{}).get(cid,[])
     if queued_day:
      p_next=queued_day.pop(0)
      STATE['day_plans'][cid]=queued_day
      c_next=copy.deepcopy(STATE['characters'][cid]); now_next=tick_end
      obs_next=obligations(now_next,c_next)
      nearby_next=[dict(x,id=k) for k,x in STATE['characters'].items() if k!=cid and can_socially_meet(x,c_next)]
      recent_next=_recent_goal_ids(cid)
      schedule_next=copy.deepcopy(c_next.get('smart_schedule',[]))
      ranked_next=score_candidates(c_next,now_next,obs_next,nearby_next,recent_next,schedule_next)
      allowed_next={x['goal'] for x in ranked_next[:4]}
      if any(o.get('urgent') for o in obs_next) or p_next.get('goal') not in allowed_next:
       p_next=utility_choose(c_next,now_next,obs_next,nearby_next,recent_next,schedule_next)
      plan_next=build_plan(cid,p_next,STATE.get('brain_request_seq',0),'day_plan')
      STATE['goals'][cid]=plan_next
      STATE['characters'][cid]['action']=plan_next['label']
      STATE['action_history'].append({'start':now_next,'end':plan_next['end'],'action':plan_next['goal'],
        'action_text':plan_next['label'],'from_location':c_next['location'],'location':c_next['location'],
        'destination':plan_next.get('target_location'),'kind':'goal_started','character_id':cid,
        'character_name':c_next['name'],'brain_goal':plan_next['goal'],'brain_intention':plan_next['goal'],
        'thought':p_next.get('thought',''),'journal_status':'PLANNED','request_seq':STATE.get('brain_request_seq',0),
        'source':'day_plan'})
      log_event('day_plan_goal_started',character_id=cid,character_name=c_next['name'],sim_minutes=now_next,
                goal=plan_next['goal'],remaining=len(queued_day),source='day_plan')
      continue
     buffered=STATE.setdefault('next_intentions',{}).pop(cid,None)
     if buffered:
      c_next=copy.deepcopy(STATE['characters'][cid]); now_next=tick_end
      obs_next=obligations(now_next,c_next)
      nearby_next=[dict(x, id=k) for k,x in STATE['characters'].items() if k!=cid and x.get('location')==c_next.get('location')]
      recent_next=_recent_goal_ids(cid)
      schedule_next=copy.deepcopy(c_next.get('smart_schedule',[]))
      ranked_next=score_candidates(c_next,now_next,obs_next,nearby_next,recent_next,schedule_next)
      allowed_next={x['goal'] for x in ranked_next[:4]}
      buffered_goal=buffered.get('goal')
      if buffered_goal not in allowed_next:
       buffered=None
     if buffered:
      p_next={'goal':buffered['goal'],'duration_minutes':int(buffered.get('duration_minutes',60)),'thought':buffered.get('thought','')}
      plan_next=build_plan(cid,p_next,buffered.get('request_seq',STATE.get('brain_request_seq',0)),'brain_buffered')
      STATE['goals'][cid]=plan_next
      log_event('brain_buffered_applied',character_id=cid,character_name=STATE['characters'][cid]['name'],
                sim_minutes=tick_end,goal=p_next['goal'],request_seq=buffered.get('request_seq'))
      # If a buffered intention was applied, wake Brain again so it computes
      # another future intention rather than blocking the current body.
      BRAIN.note_event(cid,tick_end,'goal_completed',f"goal {goal_name} completed; next intention started")
      enqueue_brain(cid,'plan_ahead:next_goal',allow_active=True)
      _dispatch_brain_queue()
     else:
      BRAIN.note_event(cid,tick_end,'goal_completed',f"goal {goal_name} completed")
      start_utility_plan_now(cid,'goal_completed_no_brain_wait')
      enqueue_brain(cid,'plan_ahead:next_goal',allow_active=True)
      _dispatch_brain_queue()
     if goal_name=='sleep':
      sleep_wakes.append(cid)
   # Advance the global clock exactly once for this tick.
   STATE['sim_minutes']=tick_end
   STATE['day']=STATE['sim_minutes']//1440+1
   for cid in sleep_wakes:
    _reflect_after_wake(cid)
  BRAIN.observe(world_snapshot())
  _smart_reflect_if_needed(STATE['day'])
 if completed:
  log_event('goals_completed',characters=[x[0] for x in completed],sim_minutes=STATE['sim_minutes'])

def _recent_goal_ids(cid):
 with LOCK:
  return [x.get('brain_goal') for x in STATE['action_history']
          if x.get('character_id')==cid and x.get('kind')=='goal_completed'][-6:]

def _commit_action_locked(cid, now, plan, source):
 """One authoritative action/goal commit per NPC per simulation minute."""
 key=f"{cid}:{int(now)}"
 committed=STATE.setdefault('action_commit',{})
 old=committed.get(key)
 if old:
  return False
 committed[key]={'goal':plan.get('goal'),'source':source,'committed_at':now}
 # Keep this bounded; AI mode can run for many days.
 if len(committed)>5000:
  cutoff=int(now)-1440
  for k,v in list(committed.items()):
   if int(v.get('committed_at',0)) < cutoff:
    committed.pop(k,None)
 return True

def start_utility_plan_now(cid, reason='utility_fallback'):
 """Instant deterministic autonomy fallback so Brain latency never idles an NPC."""
 with LOCK:
  if cid not in STATE['characters'] or not STATE['running'] or STATE['goals'].get(cid):
   return False
  c=copy.deepcopy(STATE['characters'][cid]); now=STATE['sim_minutes']
  obs=obligations(now,c)
  nearby=[dict(x, id=k) for k,x in STATE['characters'].items() if k!=cid and can_socially_meet(x,c)]
  recent=_recent_goal_ids(cid)
  schedule=copy.deepcopy(c.get('smart_schedule',[]))
  p=utility_choose(c,now,obs,nearby,recent,schedule)
  seq=STATE.get('brain_request_seq',0)
  plan=build_plan(cid,p,seq,'utility_instant')
  if not _commit_action_locked(cid, now, plan, 'utility_instant'):
   return False
  STATE['goals'][cid]=plan
  thought=make_inner_thought(c,p['goal'],now,(p.get('reasons') or ['fast autonomous fallback'])[0])
  c['action']=plan['label']
  c.setdefault('inner_thoughts',[]).append({'day':STATE['day'],'time':clock(now),'text':thought,'goal':p['goal']})
  c['inner_thoughts']=c['inner_thoughts'][-30:]
  STATE['characters'][cid]['inner_thoughts']=c['inner_thoughts']
  STATE['action_history'].append({'start':now,'end':plan['end'],'action':p['goal'],'action_text':plan['label'],
    'from_location':STATE['characters'][cid]['location'],'location':STATE['characters'][cid]['location'],
    'destination':plan.get('target_location'),'kind':'goal_started','character_id':cid,
    'character_name':STATE['characters'][cid]['name'],'brain_goal':p['goal'],'brain_intention':p['goal'],
    'thought':thought,'journal_status':'PLANNED','request_seq':seq,'source':'utility_instant'})
  STATE.setdefault('brain_status_by_character',{})[cid]='goal_active'
  log_event('utility_instant_goal',character_id=cid,character_name=c['name'],sim_minutes=now,
            goal=p['goal'],duration_minutes=plan['duration_minutes'],reason=reason,
            thought=thought,request_seq=seq)
  log_event('inner_thought',character_id=cid,character_name=c['name'],sim_minutes=now,
            goal=p['goal'],thought=thought,source='utility_instant',request_seq=seq)
  log_event('goal_start',character_id=cid,character_name=c['name'],sim_minutes=now,
            goal=p['goal'],duration_minutes=plan['duration_minutes'],source='utility_instant',
            thought=thought,request_seq=seq)
  return True

def _update_brain_ui_locked():
 active=bool(BRAIN_ACTIVE)
 pending=bool(BRAIN_PENDING) or bool(BRAIN.pending_counts())
 STATE['brain_busy']=active
 if active:
  STATE['brain_status']='thinking'
 elif pending:
  STATE['brain_status']='queued'
 elif any(STATE['goals'].values()):
  STATE['brain_status']='goal_active'
 else:
  STATE['brain_status']='ready'
 STATE['brain_online']=MODEL_OBJ is not None and BRAIN_ERROR is None


def enqueue_brain(cid, reason, allow_active=False):
 """Queue one NPC's cognitive wake-up without blocking other NPCs."""
 global BRAIN_PENDING
 with LOCK:
  if cid not in STATE['characters'] or cid == STATE.get('player_character_id','kirill') or not STATE['running']:
   return False
  if STATE['goals'].get(cid) is not None and not allow_active:
   return False
  q=BRAIN_PENDING.setdefault(cid,[])
  # One pending wake per NPC is enough; keep the newest reason.
  if q:
   q[-1]=str(reason)
  else:
   q.append(str(reason))
   log_event('brain_queue',character_id=cid,character_name=STATE['characters'][cid]['name'],
             sim_minutes=STATE['sim_minutes'],reason=str(reason),pending_for_character=len(q))
  STATE.setdefault('brain_status_by_character',{})[cid]='queued'
  _update_brain_ui_locked()
 return True


def _pop_next_brain():
 global BRAIN_PENDING, BRAIN_ACTIVE
 with LOCK:
  for cid in list(STATE['characters']):
   q=BRAIN_PENDING.get(cid)
   if not q:
    continue
   if cid in BRAIN_ACTIVE:
    BRAIN_PENDING.pop(cid,None)
    continue
   reason=q.pop(0)
   if not q:
    BRAIN_PENDING.pop(cid,None)
   BRAIN_ACTIVE.add(cid)
   STATE.setdefault('brain_status_by_character',{})[cid]='thinking'
   _update_brain_ui_locked()
   return cid,reason
 return None


def _dispatch_brain_queue():
 """Start exactly one shared-model inference at a time.

 The model is shared on the GPU, while every NPC has an independent queue and
 cognitive generation. This prevents Alice from blocking or dropping Kirill's
 wake-up while keeping VRAM usage to a single loaded model.
 """
 item=_pop_next_brain()
 if not item:
  return
 cid,reason=item
 threading.Thread(target=choose_goals,args=([cid],reason),daemon=True,name=f'Brain-{cid}').start()


def _finish_brain(cid, error=None):
 with LOCK:
  BRAIN_ACTIVE.discard(cid)
  STATE.setdefault('brain_status_by_character',{})[cid]='error' if error else ('goal_active' if STATE['goals'].get(cid) else 'ready')
  if error:
   STATE['brain_error']=str(error)
  elif not BRAIN_ACTIVE:
   STATE['brain_error']=None
  _update_brain_ui_locked()
 # Dispatch outside the state mutation lock so the next NPC is never lost.
 _dispatch_brain_queue()


def choose_goals(cids,reason='event'):
 global BRAIN_EPOCH
 cids=[cid for cid in cids if cid in STATE['characters']]
 if not cids:
  return
 # Current dispatcher sends one NPC at a time. Keep the function batch-capable
 # for compatibility with older callers.
 with LOCK:
  if not STATE['running'] and reason!='play_bootstrap':
   for cid in cids:
    BRAIN_ACTIVE.discard(cid)
   _update_brain_ui_locked()
   return
  epoch=BRAIN_EPOCH
  seq=None
  now=STATE['sim_minutes']
  start_generation={cid:int(STATE.get('brain_generation',{}).get(cid,0)) for cid in cids}
  STATE['brain_error']=None
  STATE['brain_request_seq']+=1; seq=STATE['brain_request_seq']
 log_event('brain_wakeup',request_seq=seq,reason=reason,characters=cids,sim_minutes=now,
           generations=start_generation)
 try:
  # There is one shared model. The lock makes this safe even if an external
  # caller invokes choose_goals directly instead of using the queue dispatcher.
  with BRAIN_LOCK:
   prompts=[build_prompt(cid) for cid in cids]
   source='llm'
   try:
    raws=generate_batch(prompts)
   except Exception as e:
    source='utility_fallback'; raws=['']*len(cids)
    log_event('brain_fallback',error=str(e),request_seq=seq)
  results=[]
  for cid,raw in zip(cids,raws):
   day_plan=parse_day_plan(raw)
   parsed=(day_plan[0] if day_plan else parse_goal(raw))
   with LOCK:
    c=copy.deepcopy(STATE['characters'][cid])
    obs=obligations(now,c)
    nearby=[dict(x, id=k) for k,x in STATE['characters'].items() if k!=cid and can_socially_meet(x,c)]
    recent=[x.get('brain_goal') for x in STATE['action_history']
            if x.get('character_id')==cid and x.get('kind')=='goal_completed'][-6:]
    schedule=copy.deepcopy(c.get('smart_schedule',[]))
   utility=utility_choose(c,now,obs,nearby,recent,schedule)
   ranked=score_candidates(c,now,obs,nearby,recent,schedule)
   allowed={x['goal'] for x in ranked[:4]}
   if not parsed or parsed['goal'] not in VALID_GOALS or parsed['goal'] not in allowed:
    parsed=utility; source='utility_fallback'
   if not parsed or parsed.get('goal') not in VALID_GOALS:
    parsed=fallback_goal(c, obs); source='simple_fallback'
   if obs and any(o.get('urgent') for o in obs):
    parsed=utility; source='utility_schedule'
   if float(c.get('sleepiness',0)) >= 82 and parsed['goal'] not in ('sleep','attend_obligation'):
    parsed=utility; source='utility_sleep_pressure'
   if not parsed.get('thought'):
    parsed['thought']=make_inner_thought(c,parsed['goal'],now,(parsed.get('reasons') or ['current context'])[0])
   remaining_plan=[dict(x) for x in day_plan[1:] if x.get('goal') in VALID_GOALS] if day_plan else []
   results.append((cid,parsed,source,raw,remaining_plan))

  applied=[]
  stale=[]
  with LOCK:
   # Reset only invalidates a request. Ordinary passage of simulation time does
   # NOT invalidate cognition; the final utility gate below re-checks the world.
   if epoch!=BRAIN_EPOCH or not STATE['running']:
    log_event('brain_stale_dropped',request_seq=seq,reason='world_reset_or_paused',characters=cids)
    return
   for cid,p,src,raw,remaining_plan in results:
    current_generation=int(STATE.get('brain_generation',{}).get(cid,0))
    active_goal=STATE['goals'].get(cid)
    if current_generation!=start_generation.get(cid,0):
     # If the body is already executing a goal, keep the Brain result as a
     # candidate and revalidate it against the current world below.
     if active_goal:
      log_event('brain_generation_changed_revalidated',
                character_id=cid,character_name=STATE['characters'][cid]['name'],
                request_seq=seq,reason='new_cognitive_event',
                start_generation=start_generation.get(cid,0),
                current_generation=current_generation,
                active_goal=active_goal.get('goal'))
     else:
      stale.append(cid)
      log_event('brain_stale_dropped',character_id=cid,request_seq=seq,
                reason='new_cognitive_event_no_active_goal',
                start_generation=start_generation.get(cid,0),
                current_generation=current_generation)
      continue
    # Re-read everything at the exact application moment. The world can move
    # while the model is generating, so the LLM's original intention is only a
    # proposal, never the final authority.
    c_now=copy.deepcopy(STATE['characters'][cid]); now_now=STATE['sim_minutes']
    obs_now=obligations(now_now,c_now)
    nearby_now=[dict(x, id=k) for k,x in STATE['characters'].items() if k!=cid and can_socially_meet(x,c_now)]
    recent_now=[x.get('brain_goal') for x in STATE['action_history']
                if x.get('character_id')==cid and x.get('kind')=='goal_completed'][-6:]
    schedule_now=copy.deepcopy(c_now.get('smart_schedule',[]))
    util_now=utility_choose(c_now,now_now,obs_now,nearby_now,recent_now,schedule_now)
    ranked_now=score_candidates(c_now,now_now,obs_now,nearby_now,recent_now,schedule_now)
    allowed_now={x['goal'] for x in ranked_now[:4]}
    original_goal=p.get('goal')
    if p.get('goal') not in allowed_now:
     p=util_now; src='utility_revalidated'
    if p.get('goal')=='sleep' and now_now%1440 < 22*60 and float(c_now.get('sleepiness',0)) < 90 and float(c_now.get('energy',100)) > 15:
     p=util_now; src='utility_revalidated_sleep_time'
     if p.get('goal')=='sleep':
      p={'goal':'relax','duration_minutes':60,'thought':'','reasons':['before normal bedtime']}
    if p.get('goal')!=original_goal or not p.get('thought'):
     p['thought']=make_inner_thought(c_now,p['goal'],now_now,(p.get('reasons') or ['current context'])[0])
    STATE.setdefault('day_plans',{})[cid]=remaining_plan
    if active_goal:
     # Brain was thinking ahead while the body kept acting. Store only the
     # intention; it will be rebuilt at the next decision boundary and
     # revalidated against the then-current world.
     STATE.setdefault('next_intentions',{})[cid]={
      'goal':p['goal'],'duration_minutes':p.get('duration_minutes',60),
      'thought':p.get('thought',''),'source':src,'request_seq':seq,
      'planned_at':now_now,'utility_rank':allowed_now and list(allowed_now).index(p['goal']) if p.get('goal') in allowed_now else None}
     log_event('brain_intention_buffered',character_id=cid,character_name=c_now['name'],
               sim_minutes=now_now,goal=p['goal'],source=src,request_seq=seq,
               active_goal=active_goal.get('goal'))
     applied.append(cid)
     continue
    plan=build_plan(cid,p,seq,src)
    if not _commit_action_locked(cid, now_now, plan, src):
     stale.append(cid); continue
    STATE['goals'][cid]=plan
    if cid!='kirill': STATE['last_brain']=plan
    c=STATE['characters'][cid]
    thought=p.get('thought') or make_inner_thought(c,p['goal'],now_now)
    c.setdefault('inner_thoughts',[]).append({'day':STATE['day'],'time':clock(now_now),'text':thought,'goal':p['goal']})
    c['inner_thoughts']=c['inner_thoughts'][-30:]
    c.setdefault('episodic_memory',[]).append(f'{clock(now_now)}: {thought}')
    c['episodic_memory']=c['episodic_memory'][-20:]
    STATE['action_history'].append({'start':now_now,'end':plan['end'],'action':plan['goal'],
      'action_text':plan['label'],'from_location':c['location'],'location':c['location'],
      'destination':plan.get('target_location'),'kind':'goal_started','character_id':cid,
      'character_name':c['name'],'brain_goal':plan['goal'],'brain_intention':plan['goal'],
      'thought':thought,'journal_status':'PLANNED','request_seq':seq})
    log_event('inner_thought',character_id=cid,character_name=c['name'],sim_minutes=now_now,
              goal=plan['goal'],thought=thought,source=src,request_seq=seq)
    log_event('goal_start',character_id=cid,character_name=c['name'],sim_minutes=now_now,
              goal=plan['goal'],duration_minutes=plan['duration_minutes'],
              source=src,thought=thought,request_seq=seq)
    STATE.setdefault('brain_status_by_character',{})[cid]='goal_active'
    applied.append(cid)
  log_event('brain_goals_created',request_seq=seq,
            results=[{'character_id':cid,'goal':p['goal'],'source':src,'thought':p.get('thought','')}
                     for cid,p,src,_ in results],applied=applied,stale=stale)
 except Exception as e:
  with LOCK:
   STATE['brain_status']='error'; STATE['brain_error']=str(e)
  log_event('brain_error',request_seq=seq,error=str(e),characters=cids)
 finally:
  for cid in cids:
   _finish_brain(cid)


def on_brain_event(item):
 cid=item['character_id']; reason=item.get('reason','event')
 with LOCK:
  if cid not in STATE['characters'] or cid == STATE.get('player_character_id','kirill') or not STATE['running']:
   return
  # A cognitive event increments this NPC's generation. Simulation time alone
  # does not. Thus a slow LLM response is valid unless something meaningful
  # changed for that specific character while it was thinking.
  STATE.setdefault('brain_generation',{})[cid]=int(STATE.setdefault('brain_generation',{}).get(cid,0))+1
  if STATE['goals'].get(cid) is not None:
   return
 enqueue_brain(cid,reason)
 _dispatch_brain_queue()


BRAIN=PersistentBrainRuntime()
BRAIN.on_rethink=on_brain_event


def request_brain_for_missing(reason):
 with LOCK:
  if not STATE['running']:
   return
  ids=[cid for cid,g in STATE['goals'].items() if not g and cid != STATE.get('player_character_id','kirill')]
 for cid in ids:
  start_utility_plan_now(cid,'request_missing_fast_start')
  enqueue_brain(cid,reason+':plan_ahead',allow_active=True)
 _dispatch_brain_queue()

def public_journal(): return STATE['action_history'][-120:]

def smart_profile(cid):
 with LOCK:
  c=STATE['characters'].get(cid)
  if not c: return None
  return {'character_id':cid,'name':c['name'],'inner_thoughts':copy.deepcopy(c.get('inner_thoughts',[])[-12:]),
          'diary':copy.deepcopy(c.get('diary',[])[-7:]),'smart_schedule':copy.deepcopy(c.get('smart_schedule',[])),'day_plan':copy.deepcopy(STATE.get('day_plans',{}).get(cid,[])),
          'episodic_memory':copy.deepcopy(c.get('episodic_memory',[])[-12:]),'memory_items':copy.deepcopy(c.get('memory_items',[])[-12:]),'relationships':copy.deepcopy(c.get('relationships',{})),'personality':copy.deepcopy(c.get('personality',{}))}

def apply_player_pen(text, character_id=None):
 text=str(text or '').strip()[:500]
 if not text: return False
 with LOCK:
  targets=[character_id] if character_id in STATE['characters'] else list(STATE['characters'])
  STATE.setdefault('pen_influences',[]).append({'day':STATE['day'],'time':clock(STATE['sim_minutes']),'text':text,'targets':targets})
  STATE['pen_influences']=STATE['pen_influences'][-10:]
  for cid in targets:
   c=STATE['characters'][cid]
   c.setdefault('episodic_memory',[]).append(f'Player suggestion: {text}')
   c['episodic_memory']=c['episodic_memory'][-20:]
   BRAIN.note_event(cid,STATE['sim_minutes'],'player_pen',text)
 log_event('player_pen',text=text,characters=targets,sim_minutes=STATE['sim_minutes'])
 return True

def player_move(payload):
 with LOCK:
  cid=STATE.get('player_character_id','kirill')
  p=STATE.setdefault('player_position',{'x':16.0,'y':25.0})
  try:
   p['x']=clamp(float(payload.get('x',p['x'])))
   p['y']=clamp(float(payload.get('y',p['y'])))
  except Exception: pass
  # Keep the simulation character's logical location aligned with the nearest city zone.
  STATE['characters'][cid]['location']=nearest_location(p['x'], p['y'])
  return copy.deepcopy(p)

def mood_label(c):
 v=float(c.get('mood',50) or 50)
 if v >= 82: return 'отличное настроение'
 if v >= 68: return 'хорошее настроение'
 if v >= 52: return 'спокойное настроение'
 if v >= 36: return 'немного усталое настроение'
 if v >= 20: return 'напряжённое настроение'
 return 'плохое настроение'

def dialogue_fallback(c, o, text, now):
 low=text.lower()
 mood=mood_label(o)
 rel=(o.get('relationships') or {}).get(c.get('id','kirill'), {})
 friendship=float(rel.get('friendship',50) or 50); trust=float(rel.get('trust',50) or 50); attraction=float(rel.get('attraction',0) or 0)
 if any(x in low for x in ('как ты','как дела','как настроение')):
  return f'Нормально. У меня {mood}. А ты как?'
 if any(x in low for x in ('что делаешь','чем занимаешься','где ты')):
  return f'Сейчас я в {o.get("location","городе")}. У меня {o.get("action","обычный день")}. '
 if any(x in low for x in ('как относишься ко мне','что думаешь обо мне','нравлюсь ли я','любишь меня')):
  if attraction >= 65 and trust >= 60:
   return 'Ты мне действительно нравишься. Я тебе доверяю и чувствую, что между нами уже есть что-то большее, чем просто дружба.'
  if friendship >= 65 and trust >= 55:
   return 'Ты мне близок. Мне нравится проводить с тобой время, и я хорошо к тебе отношусь. Я пока не хочу торопить наши отношения.'
  if friendship >= 45:
   return 'Ты мне нравишься как человек. Мне комфортно с тобой общаться, и я хочу узнать тебя лучше.'
  return 'Я пока ещё не очень хорошо тебя знаю. Давай сначала побольше пообщаемся.'
 if 'почему' in low: return 'Хороший вопрос. Я постараюсь объяснить, как это ощущается для меня.'
 if '?' in text: return 'Интересный вопрос. Я не хочу отвечать на него формально — дай мне подумать.'
 return 'Я понимаю. Расскажи мне чуть подробнее — мне интересно, что ты об этом думаешь.'

def dialogue_history_for(oid, limit=40):
 with LOCK:
  histories=STATE.get('dialogue_histories',{})
  if isinstance(histories,dict) and oid in histories:
   return copy.deepcopy(histories.get(oid,[])[-limit:])
  return copy.deepcopy([m for m in STATE.get('dialogue_history',[]) if m.get('target_id')==oid][-limit:])

def append_dialogue_message(oid, message):
 with LOCK:
  item=copy.deepcopy(message)
  item['target_id']=oid
  STATE.setdefault('dialogue_history',[]).append(item)
  STATE.setdefault('dialogue_histories',{}).setdefault(oid,[]).append(copy.deepcopy(item))
  STATE['dialogue_histories'][oid]=STATE['dialogue_histories'][oid][-40:]

def generate_dialogue_reply(cid, oid, text, now, dialogue_context=None):
 c=copy.deepcopy(STATE['characters'].get(cid,{})); o=copy.deepcopy(STATE['characters'].get(oid,{}))
 rel=(o.get('relationships') or {}).get(cid,{})
 recent=dialogue_history_for(oid,16)
 active_context=copy.deepcopy(dialogue_context if dialogue_context is not None else STATE.get('dialogue_contexts',{}).get(oid) or STATE.get('dialogue_context'))
 recent_lines=[]
 for m in recent:
  if not isinstance(m,dict): continue
  speaker=m.get('speaker') or o.get('name','NPC')
  msg=str(m.get('text','')).strip()
  if msg: recent_lines.append(f"{'Kirill' if speaker=='Kirill' else o.get('name','NPC')}: {msg}")
 conversation_transcript='\\n'.join(recent_lines[-16:]) or '(conversation has just started)'
 context={'clock':clock(now),'day':STATE.get('day',1),'character':o.get('name','NPC'),'location':o.get('location'),'action':o.get('action'),'mood':mood_label(o),'mood_value':o.get('mood'),'personality':personality_prompt(o),'needs':needs(o),'relationship_to_player':rel,'memory':(o.get('memory',[]) + [m.get('text','') if isinstance(m,dict) else str(m) for m in o.get('memory_items',[])])[-10:],'conversation_transcript':conversation_transcript,'conversation_context':active_context,'previous_npc_message':next((str(m.get('text','')).strip() for m in reversed(recent) if isinstance(m,dict) and m.get('speaker')==o.get('name')),''),'current_player_message':text}
 system=f"""You are {o.get('name','an NPC')} in a life simulation. You are having a normal, continuous, real-life conversation with Kirill.
Act like a real adult person, not like an assistant answering isolated prompts.

Your relationship to Kirill is: {rel.get('family_role') or rel.get('status','friend')}. If this is a family relationship, never flirt or treat it as romantic, even if the player's wording is romantic.

NATURAL HUMAN CONVERSATION:
The conversation is continuous. Every new message is a response to what was said before.
- If Kirill says "Привет", greet him naturally.
- If he says "Как дела?", answer naturally and, when appropriate, ask how he is.
- If he asks where you are, tell him where you are.
- If he asks what you are doing, describe your current activity.
- If he asks a follow-up question, continue the same topic.
- If he changes the subject, naturally switch to the new subject.
- If he says something that does not require a detailed answer, do not invent a long explanation.
- Short messages such as "ага", "да", "нет", "понятно", "прикольно", "и?", "почему?", "как?", "где?", "какой?" must be interpreted from the immediately preceding conversation.
- If Kirill makes a comment rather than asking a question, respond as a person would naturally respond to that comment.
- Do not turn every exchange into a question-and-answer interview. Sometimes react, joke, agree, disagree, add a small relevant detail, or simply acknowledge naturally.

CONVERSATION CONTINUITY:
The conversation_transcript is the actual recent chat. Read it as a normal chat before answering.
The current_player_message is the LAST message from Kirill and must be answered.
The previous_npc_message is what you said immediately before. It is already visible to Kirill.
Do not repeat, copy, or paraphrase previous_npc_message.
If Kirill asks a follow-up, answer the new question or provide the missing information.
A reply that merely repeats your previous message is WRONG.
Do not treat every message as a new conversation.
Do not restart with generic small talk after every message.
Do not constantly introduce new topics.
Do not constantly explain your memories, personality, plans, needs or current activity unless relevant.
Use the character's supplied memory, schedule, location, activity, personality and relationship information when relevant, but conversation always comes first.

CONTEXT:
The field conversation_context describes what you and Kirill are currently doing together and MUST control how short messages are interpreted.
If eating together, interpret "вкусно", "норм", "ещё хочу", "сытно" as comments about the meal.
If walking, interpret short messages as comments about the walk/place.
If on a date, keep replies date-oriented.
If flirting, hugging, arguing, studying together, etc., stay consistent with that activity.
Never reset to generic small talk just because a message is short.

AVOID GENERIC FILLER:
Do not use phrases like "Да, я тебя слушаю", "Продолжай", "Интересный вопрос", "Дай мне подумать", or "Расскажи подробнее" unless a real person would genuinely say them in this situation.
Do not say "не понимаю, что ты имеешь в виду" for ordinary context-dependent words.

BEFORE ANSWERING:
Understand what Kirill just said, what you said immediately before, what topic is being discussed, and whether Kirill is greeting you, answering you, asking a follow-up, changing the subject, joking, disagreeing or making a comment.
Then say what a normal person would naturally say next.
The goal is to continue the conversation naturally, not to provide the most informative possible answer.

Use natural Russian, first person, usually 1-3 sentences. Do not mention AI, prompts, JSON, simulation or game mechanics. Return only the reply text."""
 try:
  if not load_brain(): raise RuntimeError(BRAIN_ERROR or 'brain unavailable')
  prompt=json.dumps(context,ensure_ascii=False,separators=(',',':'))
  with BRAIN_LOCK:
   msgs=[TOKENIZER.apply_chat_template([{'role':'system','content':system},{'role':'user','content':prompt}],tokenize=False,add_generation_prompt=True)]
   old=TOKENIZER.padding_side; TOKENIZER.padding_side='left'
   try:
    x=TOKENIZER(msgs,return_tensors='pt',padding=True,truncation=True).to(MODEL_OBJ.device)
    with torch.inference_mode(): y=MODEL_OBJ.generate(**x,max_new_tokens=min(96,max(48,MAX_NEW)),do_sample=False,pad_token_id=TOKENIZER.pad_token_id)
    n=x['input_ids'].shape[1]; reply=TOKENIZER.decode(y[0][n:],skip_special_tokens=True).strip()
   finally: TOKENIZER.padding_side=old
  reply=re.sub(r'^```(?:text)?|```$','',reply,flags=re.I).strip().strip('\"')
  previous=context.get('previous_npc_message','').strip()
  def too_similar(a,b):
   if not a or not b: return False
   na=re.sub(r'\\W+','',a.lower()); nb=re.sub(r'\\W+','',b.lower())
   return bool(na and na==nb) or difflib.SequenceMatcher(None,a.lower(),b.lower()).ratio()>=0.82
  if too_similar(reply,previous):
   retry_system=system+'\\nCRITICAL RETRY: Your first answer repeated your previous NPC message and was rejected. Give a genuinely new, natural response to Kirill CURRENT message. Answer the current message, not the previous one.'
   with BRAIN_LOCK:
    retry_msgs=[TOKENIZER.apply_chat_template([{'role':'system','content':retry_system},{'role':'user','content':prompt}],tokenize=False,add_generation_prompt=True)]
    old=TOKENIZER.padding_side; TOKENIZER.padding_side='left'
    try:
     x=TOKENIZER(retry_msgs,return_tensors='pt',padding=True,truncation=True).to(MODEL_OBJ.device)
     with torch.inference_mode(): y=MODEL_OBJ.generate(**x,max_new_tokens=min(96,max(48,MAX_NEW)),do_sample=False,pad_token_id=TOKENIZER.pad_token_id)
     n=x['input_ids'].shape[1]; reply=TOKENIZER.decode(y[0][n:],skip_special_tokens=True).strip()
    finally: TOKENIZER.padding_side=old
   reply=re.sub(r'^```(?:text)?|```$','',reply,flags=re.I).strip().strip('"')
 except Exception as e:
  log_event('dialogue_brain_fallback',character_id=cid,target_id=oid,error=str(e),sim_minutes=now)
 return dialogue_fallback(c,o,text,now)

def _new_dialogue_job(cid, oid, text, now):
 global DIALOGUE_SEQ
 with DIALOGUE_LOCK:
  DIALOGUE_SEQ += 1
  job_id=f'dlg-{int(time.time()*1000)}-{DIALOGUE_SEQ}'
  DIALOGUE_JOBS[job_id]={'status':'pending','character_id':cid,'target_id':oid,'text':text,'sim_minutes':now,'reply':None,'error':None,'context':copy.deepcopy(STATE.get('dialogue_contexts',{}).get(oid) or STATE.get('dialogue_context'))}
 return job_id

def _run_dialogue_job(job_id):
 with DIALOGUE_LOCK:
  job=DIALOGUE_JOBS.get(job_id)
  if not job: return
  cid,oid,text,now=job['character_id'],job['target_id'],job['text'],job['sim_minutes']
 try:
  reply=generate_dialogue_reply(cid,oid,text,now,job.get('context'))
  with LOCK:
   c=STATE['characters'].get(cid); o=STATE['characters'].get(oid)
   if not c or not o: raise RuntimeError('unknown_target')
   append_dialogue_message(oid,{'speaker':o['name'],'text':reply,'sim_minutes':now})
   remember(cid,f'Поговорил с {o["name"]}: {text[:120]}','episodic',.45)
   remember(oid,f'{c["name"]} сказал: {text[:120]}','episodic',.45)
   log_event('dialogue_message',character_id=cid,character_name=c['name'],target_id=oid,target_name=o['name'],text=text,reply=reply,sim_minutes=now)
  with DIALOGUE_LOCK:
   job=DIALOGUE_JOBS.get(job_id)
   if job:
    job.update(status='done',reply=reply,sim_minutes=now)
 except Exception as e:
  with DIALOGUE_LOCK:
   job=DIALOGUE_JOBS.get(job_id)
   if job: job.update(status='error',error=str(e))

def start_dialogue_job(cid, oid, text, now):
 job_id=_new_dialogue_job(cid,oid,text,now)
 threading.Thread(target=_run_dialogue_job,args=(job_id,),daemon=True,name=f'Dialogue-{job_id}').start()
 return job_id

def dialogue_status(job_id):
 with DIALOGUE_LOCK:
  job=copy.deepcopy(DIALOGUE_JOBS.get(str(job_id)))
 if not job: return {'ok':False,'status':'missing'}
 out={'ok':True,'status':job['status'],'job_id':str(job_id)}
 if job['status']=='done':
  with LOCK: out['history']=dialogue_history_for(job['target_id'],20)
  out.update({'reply':job.get('reply') or '','speaker':STATE['characters'].get(job['target_id'],{}).get('name','NPC'),'sim_minutes':job.get('sim_minutes',0)})
 elif job['status']=='error': out['error']=job.get('error') or 'dialogue error'
 return out

def player_interaction(payload):
 # Player (Kirill) initiates a social action toward any NPC.
 cid=STATE.get('player_character_id','kirill')
 oid=str(payload.get('target_id','sonya'))
 it=str(payload.get('interaction','talk')).strip().lower()
 # UI labels (RU) + canonical engine type (EN). "talk" maps to small_talk.
 LABEL_TO_TYPE={
  'talk':'small_talk','eat_together':'eat_together','walk_together':'walk_together',
  'date':'date','flirt':'flirt','hug':'hug','kiss':'kiss','intimacy':'intimacy',
  'apologize':'apologize','argue':'argue','small_talk':'small_talk',
 }
 labels={
  'talk':'Поговорить','small_talk':'Поговорить','eat_together':'Пообедать вместе',
  'walk_together':'Погулять вместе','date':'Свидание','flirt':'Флирт','hug':'Обнять',
  'kiss':'Поцеловать','intimacy':'Интимная близость','apologize':'Извиниться','argue':'Поспорить',
 }
 with LOCK:
  c=STATE['characters'].get(cid); o=STATE['characters'].get(oid)
  if not c or not o: return {'ok':False,'reason':'unknown_target'}
  # Prototype: approaching means the player shares the target's social location.
  c['location']=o.get('location',c.get('location'))
  now=STATE['sim_minutes']
  rel=c.setdefault('relationships',{}).setdefault(oid,{
   'friendship':50,'trust':50,'attraction':10,'annoyance':0,'respect':50,'last_interaction':None
  })
  if it not in labels: it='talk'
  engine_type=LABEL_TO_TYPE.get(it,'small_talk')
  hour=(now%1440)/60
  family_decision=check_family_role_interaction(rel, engine_type, o['name'], now)
  if family_decision is not None:
   return family_decision
  # talk/apologize are almost always accepted for UX in the prototype.
  if it in {'talk','apologize'}:
   accepted=.85
  else:
   accepted=willingness(o,dict(c,id=cid),engine_type,hour)
  # Intimacy requires established couple status; otherwise hard-cap willingness.
  if engine_type=='intimacy':
   is_couple=str(rel.get('status','')).lower() in COUPLE_STATUSES
   stats_ok=meets_romantic('intimacy', float(rel.get('friendship',0)), float(rel.get('trust',0)), float(rel.get('attraction',0)))
   if is_couple and stats_ok:
    accepted=max(accepted,.55)
   else:
    accepted=min(accepted,.20)
  ok=accepted>=.45
  if ok:
   # Player actions interrupt the NPC's current autonomous goal. The
   # remaining day plan stays queued and resumes after this interaction.
   old_goal=STATE['goals'].get(oid)
   if old_goal:
    STATE['action_history'].append({'start':old_goal.get('start',now),'end':now,
      'action':old_goal.get('goal','goal'),'action_text':old_goal.get('label',''),
      'from_location':o.get('location'),'location':o.get('location'),'destination':old_goal.get('target_location'),
      'kind':'goal_interrupted','character_id':oid,'character_name':o['name'],
      'brain_goal':old_goal.get('goal',''),'journal_status':'INTERRUPTED','request_seq':old_goal.get('brain_request_seq')})
   duration=INTERACTIONS.get(engine_type,{}).get('minutes',10)
   forced_steps=[step('social_interaction',duration,f'{labels[it]} с {c["name"]}')]
   forced_plan={'id':f'{oid}-player-{int(time.time()*1000)}','goal':'socialize',
     'label':f'{labels[it]} с {c["name"]}','action_text':forced_steps[0]['text'],
     'brain_intention':'player_interaction','action':'social_interaction','start':now,
     'end':now+duration,'duration_minutes':duration,'step_index':0,'steps':forced_steps,
     'target_location':o.get('location'),'interaction':{'target_id':cid,'type':engine_type,
     'resolved':True,'accepted':True,'primary':True,'player_initiated':True},
     'source':'player_interrupt','brain_request_seq':STATE.get('brain_request_seq',0),
     'started':False,'status':'active'}
   STATE['goals'][oid]=forced_plan
   o['action']=forced_plan['label']
   STATE['action_history'].append({'start':now,'end':now+duration,'action':'social_interaction',
     'action_text':forced_plan['label'],'from_location':o.get('location'),'location':o.get('location'),
     'destination':o.get('location'),'kind':'goal_started','character_id':oid,'character_name':o['name'],
     'brain_goal':'socialize','brain_intention':'player_interaction','journal_status':'PLANNED',
     'request_seq':STATE.get('brain_request_seq',0),'source':'player_interrupt'})
   log_event('player_interrupt_plan',character_id=cid,character_name=c['name'],target_id=oid,
             target_name=o['name'],interaction=engine_type,sim_minutes=now,
             interrupted_goal=old_goal.get('goal') if old_goal else None)
   meta=INTERACTIONS.get(engine_type,{})
   update_relationship(
    cid,oid,
    friendship=meta.get('friendship',1.5),trust=meta.get('trust',.5),
    attraction=meta.get('attraction',0),annoyance=meta.get('annoyance',-.3),
    respect=meta.get('respect',0),reason=f'{labels[it]} with {o["name"]}.')
   update_relationship(
    oid,cid,
    friendship=meta.get('friendship',1.5)*.75,trust=meta.get('trust',.5)*.75,
    attraction=meta.get('attraction',0)*.75,annoyance=meta.get('annoyance',-.3)*.75,
    respect=meta.get('respect',0)*.75,reason=f'{labels[it]} with {c["name"]}.')
   remember(cid,f'{labels[it]} with {o["name"]}.','episodic',.85)
   remember(oid,f'{labels[it]} with {c["name"]}.','episodic',.8)
  log_event('player_interaction',character_id=cid,character_name=c['name'],target_id=oid,
            target_name=o['name'],interaction=engine_type,accepted=ok,
            willingness=round(accepted,3),sim_minutes=now)
  STATE['action_history'].append({
   'start':now,'end':now+INTERACTIONS.get(engine_type,{}).get('minutes',10),
   'action':'social_interaction','action_text':f'{labels[it]} с {o["name"]}',
   'location':c.get('location'),'character_id':cid,'character_name':c['name'],
   'target_id':oid,'target_name':o['name'],'interaction_type':engine_type,
   'kind':'player_interaction','journal_status':'DONE'})
  if ok:
   context_labels={
    'small_talk':'Обычный разговор.',
    'eat_together':'Вы сейчас вместе обедаете. Разговор должен естественно касаться еды, вкуса, блюда, аппетита и атмосферы совместного обеда.',
    'walk_together':'Вы сейчас вместе гуляете. Разговор должен учитывать прогулку, место вокруг, погоду и то, что вы видите по пути.',
    'date':'Вы сейчас на свидании. Разговор должен учитывать свидание, атмосферу и отношения между вами.',
    'flirt':'Сейчас между вами лёгкий флирт. Ответы должны быть тёплыми и игривыми, но соответствовать реальным отношениям.',
    'hug':'Вы только что обнялись. Учитывай физическую близость и чувства момента.',
    'kiss':'Вы только что поцеловались. Учитывай этот момент и реальные отношения между вами.',
    'intimacy':'Между вами была интимная близость. Говори только неявно и эмоционально, без графических сексуальных подробностей.',
    'apologize':'Вы сейчас обсуждаете извинение и восстановление отношений.',
    'argue':'Вы сейчас спорите. Ответы должны учитывать причину напряжения и раздражение, а не превращаться в обычный small talk.'
   }
   ctx={'type':engine_type,'label':labels.get(it,engine_type),'description':context_labels.get(engine_type,'Вы сейчас вместе взаимодействуете.'),'started_at':now,'target_id':oid}
   with LOCK:
    STATE['dialogue_context']=ctx
    STATE.setdefault('dialogue_contexts',{})[oid]=ctx
    STATE['selected_target_id']=oid
    append_dialogue_message(oid,{'speaker':c['name'],'text':f'[{labels.get(it,engine_type)}]','sim_minutes':now,'context_type':engine_type})
   return {'ok':True,'accepted':ok,'interaction':engine_type,'target_name':o['name'],'message':f'{o["name"]} готова к разговору.','dialogue_pending':False,'speaker':o['name'],'sim_minutes':now,'dialogue_context':ctx,'target_id':oid,'dialogue_history':dialogue_history_for(oid,20)}
  dialogue=f'{o["name"]}: Не сейчас, ладно?'
  return {'ok':True,'accepted':ok,'interaction':engine_type,'target_name':o['name'],'message':f'{o["name"]}: сейчас не хочет','dialogue':dialogue,'speaker':o['name'],'sim_minutes':now}

def fast_forward(minutes):
 minutes=max(1,min(int(minutes or 1),43200))
 with LOCK:
  was_running=STATE['running']; STATE['running']=True
 try:
  # Run normal simulation so Alice keeps living while the player observes from afar.
  advance(minutes,'player_fast_forward')
 finally:
  with LOCK: STATE['running']=was_running
 log_event('player_fast_forward',minutes=minutes,sim_minutes=STATE['sim_minutes'])
 return {'ok':True,'minutes':minutes,'sim_minutes':STATE['sim_minutes']}

def snapshot():
 with LOCK:
  d=copy.deepcopy(STATE); d['journal']=public_journal(); d['ai_mode']=bool(d['ai_mode']); d['ai_busy']=d['brain_busy']; d['ai_waiting_for_plan']=not any(d['goals'].values()) and not d['brain_busy']; d['ai_plan']=next((d['goals'].get(cid) for cid in d['characters'] if cid!=d.get('player_character_id','kirill') and d['goals'].get(cid)),None) or d.get('last_brain'); d['character_plans']=d['goals']; d['kirill']=d['characters']['kirill']; d['version']=VERSION; d['brain_model_path']=str(MODEL); d['brain_adapter_path']=str(ADAPTER); d['brain_error']=BRAIN_ERROR; d['brain_active_characters']=sorted(BRAIN_ACTIVE); d['brain_pending_characters']=sorted(BRAIN_PENDING); d['brain_generation']=copy.deepcopy(STATE.get('brain_generation',{})); d['next_intentions']=copy.deepcopy(STATE.get('next_intentions',{})); d['last_ai']=d.get('last_brain'); d['smart_profiles']={cid:smart_profile(cid) for cid in d['characters']}; d['interaction_options']={cid:[] for cid in d['characters']}; d['player_character_id']=STATE.get('player_character_id','kirill'); d['player_position']=copy.deepcopy(STATE.get('player_position',{'x':16,'y':25})); d['player_mode']=True; d['dialogue_history']=dialogue_history_for(STATE.get('selected_target_id','sonya'),40); d['dialogue_histories']=copy.deepcopy(STATE.get('dialogue_histories',{})); d['dialogue_context']=copy.deepcopy(STATE.get('dialogue_context')); d['dialogue_contexts']=copy.deepcopy(STATE.get('dialogue_contexts',{})); d['day_plans']=copy.deepcopy(STATE.get('day_plans',{})); d['selected_target_id']=STATE.get('selected_target_id','sonya')
  # Interaction options are calculated on demand when the player opens
  # an interaction menu. Do not recompute every possible interaction while
  # polling /api/state: this holds LOCK and can make player movement wait.
  return d

def reset():
 global STATE,BRAIN_EPOCH,BRAIN_PENDING,BRAIN_ACTIVE
 with LOCK:
  BRAIN_EPOCH+=1
  BRAIN_PENDING={}
  BRAIN_ACTIVE=set()
  STATE=fresh_state()
  STATE['world_epoch']=BRAIN_EPOCH
 BRAIN.reset(); BRAIN.observe(world_snapshot(),emit_events=False); log_event('reset',world_epoch=BRAIN_EPOCH)

def next_event():
 with LOCK:
  if not STATE['running']: return
  now=STATE['sim_minutes']
  plans=[p for p in STATE['goals'].values() if p]
  boundaries=[]
  # The event-driven clock must stop at the NEXT boundary of ANY NPC, not
  # at the end of an entire multi-step goal. This lets overlapping actions
  # interleave correctly: Alice 07:00-12:00 + Kirill 08:00-11:00 becomes
  # 07->08->11->12 rather than one huge jump.
  for p in plans:
   idx=int(p.get('step_index',0)); steps=p.get('steps') or []
   if 0 <= idx < len(steps):
    rem=max(1,int(steps[idx].get('remaining',1)))
    boundaries.append(rem)
   scheduled=p.get('scheduled_start')
   if scheduled is not None and int(scheduled)>now:
    boundaries.append(int(scheduled)-now)
  # Optional world/event boundaries can be registered by other systems.
  for ev in STATE.get('scheduled_events',[]) or []:
   try:
    t=int(ev.get('sim_minutes'))
    if t>now: boundaries.append(t-now)
   except Exception:
    pass
  delta=min(boundaries or [1])
  ai=bool(STATE['ai_mode'])
 advance(max(1,delta),'ai_event' if ai else 'next')
 if ai:
  log_event('ai_event_jump',sim_minutes=STATE['sim_minutes'],jump_minutes=max(1,delta),
            boundary_type='next_npc_action_or_world_event')

def handle_start():
 with LOCK:
  if STATE['running']: return
  STATE['running']=True
  selected_ai=bool(STATE['ai_mode'])
  STATE['brain_status']='loading' if MODEL_OBJ is None else STATE['brain_status']
 log_event('control',action='start',ai_mode=selected_ai,speed=STATE['speed'])
 with LOCK: missing=[cid for cid,g in STATE['goals'].items() if not g]
 for cid in missing:
  if cid == STATE.get('player_character_id','kirill'):
   continue
  start_utility_plan_now(cid,'play_bootstrap_fast_start')
  enqueue_brain(cid,'play_bootstrap:plan_ahead',allow_active=True)
  _dispatch_brain_queue()

def handle_speed(payload):
 with LOCK:
  if str(payload.get('mode','')).lower()=='ai':
   STATE['ai_mode']=True
   # AI is not a numeric speed. It is an event-driven simulation mode.
   # Keep the last normal speed only for display/state compatibility; the
   # simulation loop ignores it while ai_mode is enabled.
  else:
   STATE['ai_mode']=False
   STATE['speed']=max(1,min(16,int(payload.get('speed',1))))
 log_event('control',action='mode',speed=STATE['speed'],ai_mode=STATE['ai_mode'])

def simulation_loop():
 last=time.monotonic(); acc=0.0
 while True:
  time.sleep(.1); now=time.monotonic(); dt=min(1,now-last); last=now
  with LOCK:
   running=STATE['running']; speed=STATE['speed']; ai=STATE['ai_mode']
  if not running: continue
  if ai:
   # Event-driven AI: one loop iteration advances directly to the next
   # action/goal boundary. No artificial 16x clock is involved.
   next_event()
   continue
  acc+=dt*speed
  if acc>=1:
   m=int(acc); acc-=m; advance(m)

def preload_brain():
 with LOCK: STATE['brain_status']='loading'
 log('Brain preload: background load started')
 if load_brain():
  with LOCK: STATE['brain_status']='ready'; STATE['brain_online']=True
  log('Brain preload: READY')
 else:
  with LOCK: STATE['brain_status']='error'

def zip_logs():
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  for p in LOGDIR.glob('*'):
   if p.is_file(): z.write(p,p.name)
 return b.getvalue()

class Handler(BaseHTTPRequestHandler):
 def reply(self,code,data,typ='application/json; charset=utf-8'):
  raw=data if isinstance(data,bytes) else (data.encode('utf8') if isinstance(data,str) else json.dumps(data,ensure_ascii=False).encode('utf8'))
  self.send_response(code); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store')
  if typ=='application/zip': self.send_header('Content-Disposition','attachment; filename=MIDNIGHT_CITY_LOGS.zip')
  self.end_headers(); self.wfile.write(raw)
 def do_GET(self):
  path=self.path.split('?',1)[0]
  if path=='/': return self.reply(200,HTML.read_text(encoding='utf8'),'text/html; charset=utf-8')
  if path=='/assets/midnight_city_map_v6.png':
   try: return self.reply(200,(ROOT/'assets'/'midnight_city_map_v6.png').read_bytes(),'image/png')
   except FileNotFoundError:return self.reply(404,{'error':'map asset not found'})
  if path=='/api/state': return self.reply(200,snapshot())
  if path.startswith('/api/dialogue-status'):
   job_id=self.path.split('job=',1)[1] if 'job=' in self.path else ''
   return self.reply(200,dialogue_status(job_id))
  if path=='/api/test-ai':
   request_brain_for_missing('manual_test')
   return self.reply(200,{'ok':True})
  if path=='/api/download-logs': return self.reply(200,zip_logs(),'application/zip')
  if path=='/api/brain-world': return self.reply(200,BRAIN.all_contexts())
  if path=='/api/smart-profile':
   cid=(self.path.split('?',1)[1] if '?' in self.path else 'sonya').split('=',1)[-1]
   return self.reply(200,smart_profile(cid) or {'error':'unknown character'})
  if path=='/api/brain-stats': return self.reply(200,{'version':VERSION,'online':MODEL_OBJ is not None and BRAIN_ERROR is None,'error':BRAIN_ERROR,'model':str(MODEL),'adapter':str(ADAPTER),'persistent':True})
  return self.reply(404,{'error':'not found'})
 def do_POST(self):
  try: n=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(n) or b'{}')
  except: payload={}
  path=self.path.split('?',1)[0]
  if path=='/api/start': handle_start(); return self.reply(200,{'ok':True})
  if path=='/api/pause':
   with LOCK: STATE['running']=False
   log_event('control',action='pause'); return self.reply(200,{'ok':True})
  if path=='/api/speed': handle_speed(payload); return self.reply(200,{'ok':True})
  if path=='/api/next': next_event(); return self.reply(200,{'ok':True})
  if path=='/api/step':
   with LOCK: ai=STATE['ai_mode']; running=STATE['running']
   if running:
    next_event() if ai else advance(5,'manual_step')
   return self.reply(200,{'ok':True})
  if path=='/api/reset': reset(); return self.reply(200,{'ok':True})
  if path=='/api/pen':
   apply_player_pen(payload.get('text',''),payload.get('character_id'))
   return self.reply(200,{'ok':True})
  if path=='/api/player-move':
   return self.reply(200,{'ok':True,'position':player_move(payload)})
  if path=='/api/player-interaction':
   return self.reply(200,player_interaction(payload))
  if path=='/api/player-dialogue':
   cid=STATE.get('player_character_id','kirill'); oid=str(payload.get('target_id','sonya')); text=str(payload.get('text','')).strip()[:500]
   if not text: return self.reply(200,{'ok':False,'reason':'empty_message'})
   with LOCK:
    c=STATE['characters'].get(cid); o=STATE['characters'].get(oid); now=STATE['sim_minutes']
    if not c or not o: return self.reply(200,{'ok':False,'reason':'unknown_target'})
    append_dialogue_message(oid,{'speaker':c['name'],'text':text,'sim_minutes':now})
   job_id=start_dialogue_job(cid,oid,text,now)
   return self.reply(200,{'ok':True,'pending':True,'job_id':job_id,'speaker':o['name'],'target_name':o['name'],'sim_minutes':now})
  if path=='/api/fast-forward':
   return self.reply(200,fast_forward(payload.get('minutes',60)))
  if path=='/api/ask-all':
   request_brain_for_missing('manual_request')
   return self.reply(200,{'ok':True})
  return self.reply(404,{'error':'not found'})
 def log_message(self,*args): pass

def _project_module_paths():
 """Return loaded Python modules whose source lives in the project root."""
 out={}
 root=ROOT.resolve()
 for name,module in list(sys.modules.items()):
  # __main__ / __mp_main__ are execution aliases, not reloadable modules.
  # Reloading them with importlib.reload() fails because they have no import spec.
  if not module or name in {'__main__','__mp_main__'}:
   continue
  path=getattr(module,'__file__',None)
  if not path or not str(path).endswith('.py'):
   continue
  try:
   p=Path(path).resolve()
  except Exception:
   continue
  try:
   p.relative_to(root)
  except ValueError:
   continue
  out[name]=p
 return out

def capture_hot_reload_mtimes():
 global HOT_RELOAD_MTIMES
 HOT_RELOAD_MTIMES={name: p.stat().st_mtime_ns for name,p in _project_module_paths().items() if p.exists()}
 try: HOT_RELOAD_MTIMES['__main__']=Path(__file__).resolve().stat().st_mtime_ns
 except OSError: pass

def hot_reload_code():
 """Reload changed project .py files while keeping the loaded AI model/VRAM.

 The main module is re-executed into the existing global namespace so the
 HTTP handler and imported symbols point at the new code. The model, tokenizer
 and PersistentBrainRuntime instance are restored afterwards.
 """
 global HOT_RELOAD_ACTIVE,HOT_RELOAD_MTIMES,HTTP_SERVER,MODEL_OBJ,TOKENIZER,BRAIN,BRAIN_ERROR,BRAIN_EPOCH,BRAIN_PENDING,BRAIN_ACTIVE
 old_model=MODEL_OBJ
 old_tokenizer=TOKENIZER
 old_brain=BRAIN
 old_server=HTTP_SERVER
 current=_project_module_paths()
 changed=[name for name,path in current.items() if path.exists() and HOT_RELOAD_MTIMES.get(name)!=path.stat().st_mtime_ns]
 main_path=Path(__file__).resolve()
 if main_path.exists() and HOT_RELOAD_MTIMES.get('__main__')!=main_path.stat().st_mtime_ns:
  changed.append('__main__')
 if not changed:
  log('Console R: no changed Python files detected.')
  return
 log('Console R: changed files: '+', '.join(changed))
 with LOCK:
  STATE['running']=False
  BRAIN_EPOCH+=1
  BRAIN_PENDING={}
  BRAIN_ACTIVE=set()
 try:
  with BRAIN_LOCK:
   importlib.invalidate_caches()
   for name in changed:
    if name in {'__main__','__mp_main__'}:
     continue
    module=sys.modules.get(name)
    if module is None:
     continue
    # Some execution-created modules can have no import spec and cannot be
    # passed to importlib.reload(). They are handled by the main-module
    # re-exec below instead.
    if getattr(module,'__spec__',None) is None:
     log(f'Console R: skipping non-reloadable module {name}')
     continue
    importlib.reload(module)
   HOT_RELOAD_ACTIVE=True
   source=main_path.read_text(encoding='utf8')
   exec(compile(source,str(main_path),'exec'),globals(),globals())
 finally:
  HOT_RELOAD_ACTIVE=False
  MODEL_OBJ=old_model
  TOKENIZER=old_tokenizer
  BRAIN=old_brain
  BRAIN_ERROR=None if old_model is not None else BRAIN_ERROR
  HTTP_SERVER=old_server
  BRAIN.on_rethink=on_brain_event
  if HTTP_SERVER is not None:
   HTTP_SERVER.RequestHandlerClass=Handler
  capture_hot_reload_mtimes()
 reset()
 with LOCK:
  STATE['running']=False
  STATE['brain_status']='ready' if MODEL_OBJ is not None and BRAIN_ERROR is None else 'offline'
  STATE['brain_online']=MODEL_OBJ is not None and BRAIN_ERROR is None
 log('Console R: code reloaded. MidnightBrain model stayed in memory/VRAM.')

def console_control_loop():
 """Development console controls. Press R/r to hot-reload changed Python files."""
 while True:
  try:
   command=input().strip().lower()
  except (EOFError, KeyboardInterrupt):
   return
  if command == 'r':
   try:
    hot_reload_code()
   except Exception as e:
    log(f'Console R: hot reload FAILED: {e!r}')
    print(f'[Midnight City] Hot reload failed: {e}',flush=True)
  elif command:
   log(f'Unknown console command: {command}. Use R to hot-reload changed Python files.')

def main():
 global HTTP_SERVER
 log(f'Starting Midnight City {VERSION}')
 BRAIN.start(); BRAIN.observe(world_snapshot(),emit_events=False)
 threading.Thread(target=simulation_loop,daemon=True,name='SimulationLoop').start()
 try: s=ThreadingHTTPServer(('127.0.0.1',8080),Handler)
 except OSError as e: log(f'HTTP server failed: {e}'); print(f'[Midnight City] ERROR: port 8080 unavailable: {e}',flush=True); return
 HTTP_SERVER=s
 threading.Thread(target=s.serve_forever,daemon=True,name='HTTPServer').start(); log('HTTP server: READY at http://127.0.0.1:8080')
 capture_hot_reload_mtimes()
 try: webbrowser.open('http://127.0.0.1:8080',new=2)
 except Exception: pass
 threading.Thread(target=preload_brain,daemon=True,name='BrainPreload').start()
 log('Startup complete. Waiting for Play.')
 try:
  threading.Thread(target=console_control_loop,daemon=True,name='ConsoleControl').start()
  while True: time.sleep(1)
 except KeyboardInterrupt: s.shutdown(); s.server_close()
if __name__=='__main__' and not HOT_RELOAD_ACTIVE: main()
