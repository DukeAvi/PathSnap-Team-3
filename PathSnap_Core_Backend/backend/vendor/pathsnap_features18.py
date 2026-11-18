"""Add twelve label-free GPS/network predictors to the existing six-feature rows.

Candidate membership, row order, labels, observations and trip folds are preserved.
No route/reference field is read by augment_trip().
"""
from pathlib import Path
import io, json, zipfile
import numpy as np
import pandas as pd
from pyproj import Transformer

SIX = ['distance_m','distance_rank','heading_difference_deg','projection_fraction','segment_length_m','displacement_m']
FEATURE_INFO = [
 ('distance_m','GPS-to-segment projected distance, metres.'),
 ('distance_rank','One-based proximity rank; ties use arc ID.'),
 ('heading_difference_deg','Absolute movement/segment heading difference, degrees; 90 when invalid.'),
 ('projection_fraction','Clipped position along the directed segment, from 0 to 1.'),
 ('segment_length_m','Directed segment length, metres.'),
 ('displacement_m','GPS displacement from preceding retained observation, metres; first=0.'),
 ('heading_valid','1 when displacement >=3 m and 0<time gap<=30 s; otherwise 0.'),
 ('dt_s','Seconds since preceding retained observation; first=0.'),
 ('speed_mps','Displacement divided by positive time gap; first=0.'),
 ('distance_to_from_m','GPS-to-directed-start-node distance, metres.'),
 ('distance_to_to_m','GPS-to-directed-end-node distance, metres.'),
 ('from_out_degree','Outgoing nondegenerate directed arc count at candidate start node.'),
 ('to_in_degree','Incoming nondegenerate directed arc count at candidate end node.'),
 ('from_in_degree','Incoming nondegenerate directed arc count at candidate start node.'),
 ('to_out_degree','Outgoing nondegenerate directed arc count at candidate end node.'),
 ('candidate_count','Number of generated candidates for this GPS observation; no labels used.'),
 ('distance_gap_to_nearest_m','Candidate distance minus minimum candidate distance at the observation.'),
 ('acceleration_mps2','Change in consecutive gap-average speeds divided by current gap; 0 unless both gaps are in (0,30] s.'),
]
FEATURES = [name for name,_ in FEATURE_INFO]
assert len(FEATURES)==18 and len(set(FEATURES))==18

def augment_trip(candidates, observations, nodes, arcs):
    """Returns predictors only; neither labels nor any reference columns are accessed."""
    obs=observations.sort_values(['timestamp','observation_id'],kind='stable')
    lon,lat=obs[['longitude','latitude']].median().to_numpy()
    if not -80<=lat<=84: raise ValueError('Outside supported UTM latitude range')
    if not np.isfinite(nodes).all() or (np.abs(nodes[:,0])>180).any() or (np.abs(nodes[:,1])>90).any():
        raise ValueError('Invalid longitude/latitude node coordinates')
    if not np.isfinite(arcs).all() or not np.equal(arcs,np.floor(arcs)).all(): raise ValueError('Invalid arc node indices')
    arcs=arcs.astype('int64')
    if arcs.min()<0 or arcs.max()>=len(nodes): raise ValueError('Arc node index out of bounds')
    zone=min(60,max(1,int((lon+180)//6)+1)); epsg=(32600 if lat>=0 else 32700)+zone
    tf=Transformer.from_crs(4326,epsg,always_xy=True)
    xy=np.column_stack(tf.transform(nodes[:,0],nodes[:,1]))
    gps=np.column_stack(tf.transform(obs.longitude.to_numpy(),obs.latitude.to_numpy()))
    lengths=np.linalg.norm(xy[arcs[:,1]]-xy[arcs[:,0]],axis=1)
    aid=candidates.arc_id.to_numpy(dtype=int)
    if (aid<0).any() or (aid>=len(arcs)).any(): raise ValueError('Candidate arc ID out of bounds')
    if not np.allclose(lengths[aid],candidates.segment_length_m,rtol=1e-4,atol=.05):
        raise ValueError('Original road geometry does not match prepared candidate features')
    dt=np.r_[0.,np.diff(obs.timestamp.to_numpy(dtype=float))]
    if (dt[1:]<=0).any(): raise ValueError('Non-increasing timestamps')
    movement=np.r_[0.,np.linalg.norm(np.diff(gps,axis=0),axis=1)]
    speed=np.divide(movement,dt,out=np.zeros(len(dt)),where=dt>0)
    previous_dt=np.r_[0.,dt[:-1]]
    previous_speed=np.r_[0.,speed[:-1]]
    acc=np.divide(speed-previous_speed,dt,out=np.zeros(len(dt)),
                  where=(dt>0)&(dt<=30)&(previous_dt>0)&(previous_dt<=30))
    valid=(movement>=3)&(dt>0)&(dt<=30)
    link=pd.Index(obs.observation_id).get_indexer(candidates.observation_id)
    if (link<0).any(): raise ValueError('Unknown observation ID')
    if not np.allclose(movement[link],candidates.displacement_m,rtol=1e-4,atol=.05):
        raise ValueError('GPS ledger does not match prepared displacement')
    active=lengths>1e-6
    out_degree=np.bincount(arcs[active,0],minlength=len(nodes))
    in_degree=np.bincount(arcs[active,1],minlength=len(nodes))
    count=np.bincount(link,minlength=len(obs))
    minimum=np.full(len(obs),np.inf)
    np.minimum.at(minimum,link,candidates.distance_m.to_numpy())
    starts,ends=arcs[aid,0],arcs[aid,1]
    features=candidates[SIX].copy()
    extra={
      'heading_valid':valid[link], 'dt_s':dt[link], 'speed_mps':speed[link],
      'distance_to_from_m':np.linalg.norm(gps[link]-xy[starts],axis=1),
      'distance_to_to_m':np.linalg.norm(gps[link]-xy[ends],axis=1),
      'from_out_degree':out_degree[starts], 'to_in_degree':in_degree[ends],
      'from_in_degree':in_degree[starts], 'to_out_degree':out_degree[ends],
      'candidate_count':count[link],
      'distance_gap_to_nearest_m':np.maximum(0,candidates.distance_m.to_numpy()-minimum[link]),
      'acceleration_mps2':acc[link]}
    for name,values in extra.items(): features[name]=np.asarray(values,dtype='float32')
    x=features[FEATURES].to_numpy(dtype='float32')
    if x.shape!=(len(candidates),18) or not np.isfinite(x).all(): raise ValueError('Expected 18 finite predictors')
    assert np.array_equal(x[:,:6],candidates[SIX].to_numpy(dtype='float32'))
    return features[FEATURES]

def prepare_shared18(core, shared6_zip, network_zip, output_dir):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    target=out/'PathSnap_shared18.zip'
    if target.is_file():
        print('Reusing shared18 archive from this input/source/version-specific run.')
        return target
    train,test,folds,assignments,protocol=core.load_shared(shared6_zip,features=SIX)
    with zipfile.ZipFile(network_zip) as z:
        names=z.namelist()
        for split,ds in [('train',train),('student_test',test)]:
            extras=pd.DataFrame(index=ds.candidates.index,columns=FEATURES[6:],dtype='float32')
            for number,(trip,obs) in enumerate(ds.observations.groupby('trip_id',sort=True),1):
                c=ds.candidates[ds.candidates.trip_id==trip]
                def read(ext):
                    found=[n for n in names if n.replace('\\','/').endswith(f'/{split}/{trip}/{trip}.{ext}')]
                    if len(found)!=1: raise ValueError(f'Missing or ambiguous {split}/{trip}.{ext}')
                    a=np.loadtxt(io.BytesIO(z.read(found[0])),ndmin=2)
                    if a.shape[1]!=2: raise ValueError(f'{ext}: expected two columns')
                    return a
                values=augment_trip(c,obs,read('nodes'),read('arcs'))
                extras.loc[c.index,FEATURES[6:]]=values[FEATURES[6:]].to_numpy()
                if number==1 or number%10==0: print(f'{split}: 18 features prepared for {number} trips',flush=True)
            for name in FEATURES[6:]: ds.candidates[name]=extras[name].to_numpy(dtype='float32')
            assert np.isfinite(ds.candidates[FEATURES].to_numpy()).all()
    data=out/'shared18_inputs'; data.mkdir(exist_ok=True)
    arrays={'features':np.asarray(FEATURES,dtype='U')}
    for split,prefix,ds in [('train','train',train),('student_test','test',test)]:
        arrays[f'X_{prefix}_raw']=ds.candidates[FEATURES].to_numpy(dtype='float32')
        arrays[f'y_{prefix}']=ds.candidates.label.to_numpy(dtype='int8')
        for key in ['trip_id','observation_id','arc_id']:
            arrays[f'{prefix}_{key}']=ds.candidates[key].to_numpy(dtype='U' if key=='trip_id' else 'int64')
        ds.observations.to_csv(data/f'{split}_observations.csv.gz',index=False)
    mapping=assignments.set_index('trip_id').fold
    arrays['fold_id']=train.candidates.trip_id.map(mapping).to_numpy(dtype='int8')
    np.savez_compressed(data/'shared_inputs.npz',**arrays)
    assignments.to_csv(data/'fold_assignments.csv',index=False)
    for f,(fit,valid) in folds.items(): np.savez_compressed(data/f'fold_{f}_indices.npz',fit_idx=fit,valid_idx=valid)
    protocol={**protocol,'features':FEATURES,'schema_version':'shared-eighteen-v1',
      'feature_source':'Six original predictors unchanged; twelve GPS/network predictors derived without reference information.',
      'folds_and_candidates':'Preserved exactly from supplied PathSnap_shared6.zip',
      'feature_count':18,'acceleration_policy':'0 unless current and preceding time gaps are both in (0,30] s'}
    core.save_json(data/'shared_protocol.json',protocol)
    schema=[{'name':n,'definition':d} for n,d in FEATURE_INFO]
    core.save_json(data/'feature_schema.json',schema)
    pd.DataFrame(schema).to_csv(out/'feature_schema_18.csv',index=False)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in data.iterdir(): z.write(p,p.name)
    # The normal loader checks dimensions, label/ID alignment, coverage, and all fixed fold indices.
    core.load_shared(target)
    print('Reusable eighteen-feature input archive saved:',target)
    return target
