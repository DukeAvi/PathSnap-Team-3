"""Compiled Viterbi with the same emissions, transitions and reset policy as supplied."""
import numpy as np
from numba import njit
@njit(cache=True)
def recurrence(indices,arcs,dt,displacement,routes,logp,beta_m,beta_displacement,max_speed,slack):
 n,k=indices.shape
 emissions=np.full((n,k),-np.inf)
 for t in range(n):
  for j in range(k):
   if indices[t,j]>=0: emissions[t,j]=logp[indices[t,j]]
 chosen=np.full(n,-1,np.int64); events=np.zeros(n,np.int64)
 back=np.full((n,k),-1,np.int64);dp=np.full(k,-np.inf)
 active=False;start=0
 for t in range(n):
  has=False
  for j in range(k):
   if indices[t,j]>=0: has=True
  if not has:
   if active:
    state=np.argmax(dp)
    for u in range(t-1,start-1,-1):
     chosen[u]=state;state=back[u,state]
   active=False;events[t]=1;continue
  reset=not active or not (0.<dt[t]<=30.)
  new=np.full(k,-np.inf)
  if not reset:
   beta=beta_m+beta_displacement*displacement[t]
   for j in range(k):
    best=-np.inf;prev=0
    for i in range(k):
     d=routes[t,i,j]
     value=-np.inf
     if np.isfinite(d) and d<=max_speed*dt[t]+slack:
      value=dp[i]-abs(d-displacement[t])/beta
     if value>best:best=value;prev=i
    new[j]=emissions[t,j]+best;back[t,j]=prev
   if not np.isfinite(new).any():reset=True;events[t]=5
  if reset:
   if active:
    state=np.argmax(dp)
    for u in range(t-1,start-1,-1):
     chosen[u]=state;state=back[u,state]
   start=t;dp=emissions[t].copy();back[t,:]=-1
   if events[t]!=5:
    events[t]=2 if t==0 else (3 if dt[t]>30. else 4)
  else:dp=new
  dp-=np.max(dp);active=True
 if active:
  state=np.argmax(dp)
  for u in range(n-1,start-1,-1):chosen[u]=state;state=back[u,state]
 out=np.full(n,-1,np.int64)
 for t in range(n):
  if chosen[t]>=0:out[t]=arcs[t,chosen[t]]
 return out,events

def decode_fast(lattice,p,config):
 arcs,events=recurrence(lattice['indices'],lattice['arcs'],lattice['dt'],lattice['displacement'],lattice['routes'],np.asarray(np.log(np.clip(np.asarray(p),1e-9,1.)),dtype=np.float64),config['beta_m'],config['beta_displacement'],config['max_speed_mps'],config['slack_m'])
 return arcs,np.asarray(['','no_candidates','start','gap_reset','restart','transition_reset'],dtype='<U24')[events]
