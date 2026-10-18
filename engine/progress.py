"""Publish counts only on the activity branch; never include search terms or contacts."""
import base64
import json
import os
import time
import urllib.request

class Progress:
    def __init__(self,run_id):
        self.run_id=run_id; self.sha=None; self.last=0; self.disabled=False; self.discovery_done=0; self.discovery_total=0
        self.token=os.getenv('RADAR_PROGRESS_TOKEN'); self.repo=os.getenv('GITHUB_REPOSITORY')
    def call(self,path,method='GET',data=None):
        req=urllib.request.Request('https://api.github.com/repos/'+self.repo+path,method=method,data=json.dumps(data).encode() if data else None,headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=8) as r: return json.load(r)
    def update(self,phase,done=0,total=0,force=False):
        if not self.token or not self.repo or self.disabled or (not force and time.monotonic()-self.last<7): return
        self.last=time.monotonic(); path='/contents/data/search-progress.json'; branch='radar-presence'
        try:
            if not self.sha:
                try:self.call('/git/ref/heads/'+branch)
                except Exception:
                    self.call('/git/refs','POST',{'ref':'refs/heads/'+branch,'sha':os.environ['GITHUB_SHA']})
                try:self.sha=self.call(path+'?ref='+branch)['sha']
                except Exception: pass
            payload={'run_id':self.run_id,'phase':phase,'done':done,'total':total,'at':int(time.time())}
            data={'message':'radar: search progress [skip ci]','branch':branch,'content':base64.b64encode(json.dumps(payload).encode()).decode()}
            if self.sha:data['sha']=self.sha
            self.sha=self.call(path,'PUT',data)['content']['sha']
        except Exception:
            self.sha=None  # Progress is optional; failure must not interrupt the search.
